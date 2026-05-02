"""跨月统一识别：本月孤儿退款条目反查 6 个月历史原支出，关联成功移到右侧列。

涵盖三种孤儿场景：
1. 跨月退款（支付宝、微信）—— 上月已扣款，本月才看到反向收入条目
2. 跨月购物金退款（淘宝）—— 上月充值在本月之前，本月只看到退款
3. 跨月小红书 / 抖音退货 —— 待样本验证后细化

反查规则（按渠道分流，从严）：
- 支付宝：order_id 核心段相等优先（同 _extract_core_order_id 算法）；
        失败时 fallback 到 (payee+amount+source) 严格相等且候选唯一
- 微信：transaction_id 不共享，只能用 (payee 剥离 "-退款" + amount 严格相等) +
        候选唯一才关联。多候选不处理（保持 OTHER 不计支出 + 警告日志）

输出：
- 关联成功：item.cross_month_origin = {payee, amount, bill_time, item_name, order_id, ...}
            原 bill_type / category 不变（OTHER 不计支出，月度汇总不算它）
            该 item 仍留在主表（左右分区原则），同时由输出层从 cross_month_origin
            非空摘出来，在右侧"提醒块"再展示一份
- 关联失败：保留现状（OTHER），后续 exact_match 会标 SKIP

实施位置：taobao_balance_merge 之后、exact_match 之前。同月合并都跑完之后再做跨月识别。

举例：
- 微信本月孤儿条目：payee="北京大学国际医院"  amount=50  bill_type=OTHER  item_name="...退款..."
  反查 6 个月历史：上月有 payee="北京大学国际医院" amount=50 EXPENSE → 唯一候选 → 关联
- 微信本月孤儿条目：payee="某店铺"  amount=10  bill_type=OTHER
  反查到历史 3 条 amount=10 → 多候选 → 不处理
"""

import datetime
import logging
from typing import Callable, Dict, List, Optional, Tuple

from bill_item import BillItem, BillType
from category import Lifecycle
from classifiers.base import Context, Step
from classifiers.taobao_balance_merge import _extract_core_order_id

logger = logging.getLogger(__name__)


HISTORY_WINDOW_MONTHS = 6
WECHAT_REFUND_SUFFIX = "-退款"


HistoryLoaderFn = Callable[[List[Tuple[int, int]]], List[BillItem]]


def _months_before(year: int, month: int, count: int) -> List[Tuple[int, int]]:
    """返回 (year, month) 之前 count 个月的列表（从最近往前）。"""
    out: List[Tuple[int, int]] = []
    y, m = year, month
    for _ in range(count):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out.append((y, m))
    return out


def _is_orphan_refund(item: BillItem) -> bool:
    """孤立反向条目（退款/不计收支类反向收入）识别。

    经过 merge_refund / taobao_balance_merge 之后，仍然是 OTHER 的"退款"类条目，
    通常都是跨月孤儿。
    """
    if item.bill_type != BillType.OTHER:
        return False
    if "退款" in (item.item_name or ""):
        return True
    if (item.payee or "").endswith(WECHAT_REFUND_SUFFIX):
        return True
    return False


def _normalize_payee(orphan_payee: str) -> str:
    """把微信"-退款"后缀剥掉，得到原 payee。"""
    payee = orphan_payee or ""
    if payee.endswith(WECHAT_REFUND_SUFFIX):
        return payee[:-len(WECHAT_REFUND_SUFFIX)]
    return payee


def _make_origin(h: BillItem) -> Dict:
    """把历史原支出条目打包成 dict 挂到孤儿的 cross_month_origin 上。"""
    return {
        "payee": h.payee,
        "amount": h.amount,
        "bill_time": h.bill_time,
        "item_name": h.item_name,
        "order_id": h.order_id,
        "bill_source": h.bill_source,
        "owner": h.owner,
    }


def _build_indexes(history: List[BillItem]):
    """对历史 EXPENSE 条目建索引（核心订单号 / payee+amount+source）。"""
    core_oid_index: Dict[str, List[BillItem]] = {}
    payee_amount_index: Dict[Tuple[str, float, str], List[BillItem]] = {}

    for h in history:
        if h.bill_type != BillType.EXPENSE:
            continue
        if h.order_id:
            core = _extract_core_order_id(h.order_id)
            if core:
                core_oid_index.setdefault(core, []).append(h)
        key = (h.payee, h.amount, h.bill_source)
        payee_amount_index.setdefault(key, []).append(h)

    return core_oid_index, payee_amount_index


class CrossMonthUnified(Step):
    """跨月孤儿退款条目识别 + 反查 + 标到 right_extra。"""

    name = "cross_month_unified"

    def __init__(self,
                 history_loader: Optional[HistoryLoaderFn] = None,
                 history_months: int = HISTORY_WINDOW_MONTHS):
        self._history_loader = history_loader
        self._history_months = history_months

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        if not items:
            return items

        orphans = [it for it in items if _is_orphan_refund(it)]
        if not orphans:
            return items

        # 推算当前月（用 items 里最大 bill_time）
        max_t = max(it.bill_time for it in items)
        dt = datetime.datetime.fromtimestamp(max_t)
        history_months = _months_before(dt.year, dt.month, self._history_months)

        history = self._load_history(history_months)
        if not history:
            logger.warning("cross_month_unified 跳过：历史数据为空")
            return items

        core_oid_index, payee_amount_index = _build_indexes(history)

        match_count = 0
        ambiguous_count = 0
        for orphan in orphans:
            origin, status = self._lookup(orphan, core_oid_index, payee_amount_index)
            if origin is not None:
                orphan.cross_month_origin = origin
                orphan.lifecycle = Lifecycle.CROSS_MONTH_REFUND
                match_count += 1
            elif status == "ambiguous":
                ambiguous_count += 1
                logger.info(
                    "cross_month_unified 多候选不关联: payee=%s amount=%s source=%s",
                    orphan.payee, orphan.amount, orphan.bill_source,
                )

        logger.info(
            "cross_month_unified orphans=%d matched=%d ambiguous=%d",
            len(orphans), match_count, ambiguous_count,
        )
        return items

    def _load_history(self, months: List[Tuple[int, int]]) -> List[BillItem]:
        if self._history_loader is not None:
            try:
                return self._history_loader(months)
            except Exception:
                logger.exception("注入的 history_loader 调用失败")
                return []
        # 默认走 raw_history_loader
        try:
            from raw_history_loader import RawHistoryLoader
            return RawHistoryLoader().load_months(months)
        except Exception:
            logger.exception("默认 raw history loader 失败")
            return []

    def _lookup(self, orphan: BillItem, core_oid_index, payee_amount_index):
        """返回 (origin_or_None, status)：status ∈ {hit, ambiguous, miss}。"""
        if orphan.bill_source == "alipay":
            # 支付宝：先 order_id 核心段
            core = _extract_core_order_id(orphan.order_id)
            if core is not None:
                candidates = core_oid_index.get(core, [])
                if len(candidates) == 1:
                    return _make_origin(candidates[0]), "hit"
                if len(candidates) > 1:
                    # 多候选取最近一笔（bill_time 最大）
                    return _make_origin(max(candidates, key=lambda h: h.bill_time)), "hit"
            return self._payee_amount_lookup(orphan, payee_amount_index)
        # 微信 / 其它：只能 payee+amount，且必须唯一
        return self._payee_amount_lookup(orphan, payee_amount_index)

    def _payee_amount_lookup(self, orphan: BillItem, payee_amount_index):
        payee = _normalize_payee(orphan.payee)
        candidates = payee_amount_index.get((payee, orphan.amount, orphan.bill_source), [])
        if len(candidates) == 1:
            return _make_origin(candidates[0]), "hit"
        if len(candidates) > 1:
            return None, "ambiguous"
        return None, "miss"
