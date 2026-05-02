"""硬编码 item_name 黑名单：命中即标 SKIP。

逻辑：
- 一些转账类的 item_name 在飞书分类表里没维护，但又确定不算开销
  （资金搬运、内部转账等），用一个 in-memory 列表直接判 SKIP
- 仅对仍是 UNPROCESSED 的 item 生效；不看 bill_type
- 默认黑名单见 SKIP_ITEM_NAMES；构造时可传 names 覆盖

实施位置：cross_month_unified 之后、non_expense_skip 之前。
理由：黑名单是基于 item_name 的硬规则，应优先于 bill_type 判断生效。
比如"余额宝-自动转入" bill_type 通常是"不计收支"(OTHER)，如果排在
non_expense_skip 之后，会被前者以 NON_EXPENSE 的理由先 SKIP 掉，
本 step 的 BLACKLIST 标签就永远打不出来。

举例（默认黑名单：余额宝-自动转入、转账备注:微信转账）：
- item_name="余额宝-自动转入" → SKIP + BLACKLIST
- item_name="转账备注:微信转账" → SKIP + BLACKLIST
- item_name="正常商品名" → 保持 UNPROCESSED，留给后续 step
"""

import logging
from typing import List

from bill_item import BillItem
from category import ClassifyAlg, Lifecycle, SkipReason
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
            if item.lifecycle != Lifecycle.UNPROCESSED:
                continue
            if item.item_name in self._names:
                item.lifecycle = Lifecycle.SKIPPED
                item.skip_reason = SkipReason.BLACKLIST
                item.classify_alg = ClassifyAlg.MATCH
                count += 1
        logger.info("extra skip item size:{}".format(count))
        return items
