"""淘宝购物金合并：同月内充值 + 退款按核心订单号合并为一条净支出。

数据现象（来自实际淘宝账单）：
- 充值条目：item_name 含 "购物金"（如 "戴维贝拉购物金 充值享折上折【充1000得1030】"），
  bill_type=支出
- 退款条目：item_name 以 "退款-" 开头并含 "购物金"，bill_type=不计收支
- 同一次充值的多次部分退款共享"核心订单号"，但完整 order_id 不同，所以
  现有 merge_refund（按完整 order_id 合并）合不上

order_id 格式（实测，bill.py 用支付宝商家订单号 row[1]）：
- 充值条目：`T200P<19位数字>`，如 `T200P2613628093127195986`，payee="购物金"
- 退款条目：`<19位数字>_<18位数字>`（两段），如 `2613032798634195986_217847532514198659`，
            payee="<店铺名脱敏>"（如 da**店）
- 退款 advance 类：三段 `<prefix>_<core>_advance`（罕见，row[0] 形式才有）
- 含 '*' 形式：罕见（row[0] 形式），`...131*<core>_<sub>`

**关联规则**：充值 oid 去掉 T200P 前缀 = 退款 oid 第一段 = "核心订单号"。
普通条目 / 余额宝收益等无核心 → 提取失败不参与合并。

逻辑：
- 在 merge_refund 之后跑：merge_refund 已合掉了同 order_id 的支出+退款，
  没合上的购物金条目（核心相同但 order_id 不同）由本 step 处理
- 仅识别 item_name 含 "购物金" 的条目（充值或退款）作为候选
- 按核心订单号分组：
    - 既有充值又有退款 → 同月闭合，合并：保留充值条目的第一条，
      amount = 充值总额 - 退款总额，taobao_balance_extra 写入余额说明，
      net=0 时整条 SKIP
    - 只有退款（充值在上月）→ 不动，留给策略 3 (cross_month_unified)
    - 只有充值（同月还没退或不退）→ 不动
- 不能提取核心订单号的条目原样保留

举例（同月）：
- 充值 1000 + 退款 100 + 退款 31 = 净 869 → 一条 869 的"购物金消费余额: 869.00"
- 充值 1000 + 退款 1000 = 净 0 → SKIP
- 上月充值 1000，本月退款 100 → 本月只看到退款，不动
"""

import logging
from typing import Dict, List, Optional

from bill_item import BillItem, BillType
from category import Lifecycle, SkipReason
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


_PURCHASE_KEYWORD = "购物金"
_REFUND_PREFIX = "退款-"
_T200P_PREFIX = "T200P"
_MIN_CORE_LEN = 10  # 核心订单号至少 10 位数字（防止短数字 collision）


def _extract_core_order_id(order_id: str) -> Optional[str]:
    """从 order_id 中提取核心订单号；提取失败返回 None 表示不参与合并。

    优先级：
        1. 充值订单 `T200P<digits>` → 去前缀
        2. row[0] 形式 `...*<core>_<sub>` → '*' 后下划线前段
        3. 退款两段 `<core>_<sub>` → 下划线第 1 段
        4. row[0] 三段 `<prefix>_<core>_<sub|advance>` → 下划线第 2 段

    样本：
        "T200P2613628093127195986"                      -> "2613628093127195986"
        "2613032798634195986_217847532514198659"        -> "2613032798634195986"
        "...131*3007421472149123455_236787279472125534" -> "3007421472149123455"
        "...129_3007448761561123455_235695216446125534" -> "3007448761561123455"
        "...232_3015081734490123455_advance"            -> "3015081734490123455"
        "2025102722001401601448284988"                  -> None
    """
    if not order_id:
        return None
    # 1. 充值订单 T200P<digits>
    if order_id.startswith(_T200P_PREFIX):
        rest = order_id[len(_T200P_PREFIX):]
        if rest.isdigit() and len(rest) >= _MIN_CORE_LEN:
            return rest
        return None
    # 2. row[0] 形式：含 '*'
    if "*" in order_id:
        after_star = order_id.split("*", 1)[1]
        core = after_star.split("_", 1)[0]
        if core.isdigit() and len(core) >= _MIN_CORE_LEN:
            return core
        return None
    # 3 / 4. 下划线分段
    parts = order_id.split("_")
    if len(parts) == 2:
        # 退款 row[1]：<core>_<sub>
        if parts[0].isdigit() and len(parts[0]) >= _MIN_CORE_LEN:
            return parts[0]
        return None
    if len(parts) >= 3:
        # row[0] 三段：<prefix>_<core>_<sub|advance>
        if parts[1].isdigit() and len(parts[1]) >= _MIN_CORE_LEN:
            return parts[1]
    return None


def _is_balance_recharge(item: BillItem) -> bool:
    """购物金充值条目（支出 + item_name 含购物金 + 不以 "退款-" 开头）。"""
    if item.bill_type != BillType.EXPENSE:
        return False
    if not item.item_name or _PURCHASE_KEYWORD not in item.item_name:
        return False
    if item.item_name.startswith(_REFUND_PREFIX):
        return False
    return True


def _is_balance_refund(item: BillItem) -> bool:
    """购物金退款条目（item_name 以 "退款-" 开头 + 含购物金）。"""
    if not item.item_name or _PURCHASE_KEYWORD not in item.item_name:
        return False
    return item.item_name.startswith(_REFUND_PREFIX)


class TaobaoBalanceMerge(Step):
    """同月内：按核心订单号合并购物金充值 + 退款，净额覆盖充值条目。

    跨月场景（充值/退款分散在不同月）由策略 3 (cross_month_unified) 处理。
    """

    name = "taobao_balance_merge"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        groups: Dict[str, List[BillItem]] = {}
        rest: List[BillItem] = []

        for item in items:
            if not (_is_balance_recharge(item) or _is_balance_refund(item)):
                rest.append(item)
                continue
            core = _extract_core_order_id(item.order_id)
            if core is None:
                # 提取不到核心订单号 → 不参与合并，保留原样
                rest.append(item)
                continue
            groups.setdefault(core, []).append(item)

        merged: List[BillItem] = []
        for core, group in groups.items():
            recharges = [g for g in group if _is_balance_recharge(g)]
            refunds = [g for g in group if _is_balance_refund(g)]

            if not recharges or not refunds:
                # 只充值或只退款 → 留给策略 3 / 不动
                merged.extend(group)
                continue

            recharge_total = sum(g.amount for g in recharges)
            refund_total = sum(g.amount for g in refunds)
            net = round(recharge_total - refund_total, 2)

            primary = recharges[0]
            primary.amount = net
            primary.taobao_balance_extra = f"购物金消费余额: {net:.2f}"
            if net == 0:
                primary.lifecycle = Lifecycle.SKIPPED
                primary.skip_reason = SkipReason.ZERO_AMOUNT
            merged.append(primary)

            logger.info(
                "taobao_balance_merge core=%s recharge=%.2f refund=%.2f net=%.2f group_size=%d",
                core, recharge_total, refund_total, net, len(group),
            )

        out = rest + merged
        out.sort(key=lambda it: it.bill_time)
        logger.info("after taobao_balance_merge bill item:%d", len(out))
        return out
