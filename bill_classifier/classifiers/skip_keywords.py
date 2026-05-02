"""硬编码 item_name 黑名单：命中即标 SKIP。

逻辑：
- 一些转账类的 item_name 在飞书分类表里没维护，但又确定不算开销
  （资金搬运、内部转账等），用一个 in-memory 列表直接判 SKIP
- 仅对仍是 UNKNOWN 的 item 生效
- 默认黑名单见 SKIP_ITEM_NAMES；构造时可传 names 覆盖

举例（默认黑名单：余额宝-自动转入、转账备注:微信转账）：
- item_name="余额宝-自动转入" → SKIP（资金从余额转到余额宝，不算开销）
- item_name="转账备注:微信转账" → SKIP
- item_name="正常商品名" → 保持 UNKNOWN，留给后续 step
"""

import logging
from typing import List

from bill_item import BillItem
from category import ExpenseCategory, Lifecycle, SkipReason
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)

SKIP_ITEM_NAMES = [
    "余额宝-自动转入",
    "转账备注:微信转账",
]


class SkipKeywords(Step):
    """硬编码的 item_name 黑名单，命中即标 SKIP。"""

    name = "skip_keywords"

    def __init__(self, names: List[str] = None):
        self._names = names if names is not None else SKIP_ITEM_NAMES

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        count = 0
        for item in items:
            if item.lifecycle != Lifecycle.UNPROCESSED or item.category != ExpenseCategory.UNKNOWN:
                continue
            if item.item_name in self._names:
                item.category = ExpenseCategory.SKIP  # 双写
                item.lifecycle = Lifecycle.SKIPPED
                item.skip_reason = SkipReason.BLACKLIST
                count += 1
        logger.info("extra skip item size:{}".format(count))
        return items
