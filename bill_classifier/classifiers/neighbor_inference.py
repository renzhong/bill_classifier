"""相邻账单推断：UNKNOWN 的"低信息量"item 看后 5 分钟内的 MATCH 锚点。

逻辑：
- 触发条件：UNKNOWN item，且属于"低信息量"类型：
    - payee in {美团, 美团平台商户, 大众点评, 京东, 京东商家}，或
    - item_name 含订单号特征（"美团订单-" / "订单编号" / 纯长串数字 ≥20 位）
- 锚点：item bill_time 之后 NEIGHBOR_WINDOW_SECONDS 内（单向，往后看）
- 锚点条件：classify_alg == ClassifyAlg.MATCH（仅精确匹配；REGULAR /
  WET_MARKET 不算锚点，避免链式污染）
- 严格 1 条：窗口内 0 条 或 ≥2 条 MATCH 锚点 → 不处理（保持 UNKNOWN）
- 命中：当前 item.category = 锚点 category，classify_alg = ClassifyAlg.NEIGHBOR
- 共享 neighbor_group：当前 item 与锚点都设置同一个 group ID，便于输出层把同组紧邻
- 前置条件：items 已按 bill_time 升序（pipeline 中 merge_payee / merge_refund 都会排序）

举例：
- T0=12:00 美团团购 100 (UNKNOWN payee=美团)，T0+3min=12:03 微信支付餐厅 28 (MATCH 餐饮)
  → 美团团购被标"餐饮"，classify_alg=NEIGHBOR；两者共享 neighbor_group
- T0=12:00 美团 100，窗口内 0 条 MATCH → 不处理
- T0=12:00 美团 100，窗口内 2 条 MATCH（不同 category）→ 不处理
- T0=12:00 美团 100，窗口前面 5min 有 MATCH → 不处理（单向，只看后面）
- T0=12:00 美团 100，5min+1s 后有 MATCH → 不处理（超窗口）
"""

import logging
import re
from typing import List, Optional

from bill_item import BillItem, ClassifyAlg
from category import ExpenseCategory, Lifecycle
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


# 单向窗口：当前 item 之后多少秒内的 MATCH 锚点会被参考
NEIGHBOR_WINDOW_SECONDS = 300  # 5 分钟

# 低信息量 payee 白名单
LOW_INFO_PAYEES = {
    "美团",
    "美团平台商户",
    "大众点评",
    "京东",
    "京东商家",
}

# 订单号特征：item_name 含这些片段的也算低信息量
_ORDER_PATTERNS = [
    r"美团订单-",
    r"订单编号",
    r"^\d{20,}$",  # 纯 20 位以上的数字
]
_ORDER_RE = re.compile("|".join(_ORDER_PATTERNS))


def _is_low_info(item: BillItem) -> bool:
    if item.payee in LOW_INFO_PAYEES:
        return True
    if item.item_name and _ORDER_RE.search(item.item_name):
        return True
    return False


def _make_group_id(anchor: BillItem) -> str:
    if anchor.order_id:
        return f"nbr:{anchor.order_id}"
    return f"nbr:t{int(anchor.bill_time)}"


class NeighborInference(Step):
    """对 UNKNOWN 的低信息量 item，看 +0..+5min 窗口内是否唯一 1 条 MATCH 锚点。"""

    name = "neighbor_inference"

    def __init__(self, window_seconds: int = NEIGHBOR_WINDOW_SECONDS,
                 low_info_payees: Optional[set] = None):
        self._window = window_seconds
        self._low_info_payees = low_info_payees or LOW_INFO_PAYEES

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        n = len(items)
        mark_count = 0

        for i, item in enumerate(items):
            if item.lifecycle != Lifecycle.UNPROCESSED or item.category != ExpenseCategory.UNKNOWN:
                continue
            if not self._is_target(item):
                continue

            # 单向：从 i+1 开始往后扫，直到超出窗口
            anchors: List[BillItem] = []
            for j in range(i + 1, n):
                if items[j].bill_time - item.bill_time > self._window:
                    break
                if items[j].classify_alg == ClassifyAlg.MATCH:
                    anchors.append(items[j])
                    if len(anchors) > 1:
                        break  # 已经 ≥2 条，不必继续

            if len(anchors) != 1:
                continue

            anchor = anchors[0]
            item.category = anchor.category
            item.classify_alg = ClassifyAlg.NEIGHBOR
            item.lifecycle = Lifecycle.CLASSIFIED
            group_id = _make_group_id(anchor)
            item.neighbor_group = group_id
            anchor.neighbor_group = group_id
            mark_count += 1

        logger.debug("neighbor_inference 标记 item size:{}".format(mark_count))
        return items

    def _is_target(self, item: BillItem) -> bool:
        if item.payee in self._low_info_payees:
            return True
        if item.item_name and _ORDER_RE.search(item.item_name):
            return True
        return False
