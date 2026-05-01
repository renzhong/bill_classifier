"""菜场扩散：以已精确匹配的「买菜」item 为锚点，1 小时窗口内的
其他 UNKNOWN item 一并标为「买菜」。

逻辑：
- 去菜场（新发地、农贸市场等）一次会在不同摊位连刷多笔支付宝。
  这些摊位 payee / item_name 五花八门，单看任何一条都很难分类。
- 解决：找一个**可信锚点**（已被 ExactMatch 标为
  ExpenseCategory.BUY_VEGETABLES 且 ClassifyAlg.MATCH 的 item），
  以它的 bill_time 为中心，前后各 BUY_VEGETABLES_TIME_RANGE 秒
  （3600s = 1 小时）窗口内还是 UNKNOWN 的 item 都判为买菜，
  classify_alg 标 ClassifyAlg.WET_MARKET
- 锚点必须是 MATCH，不能是 REGULAR——精确匹配最可信，模糊匹配
  偶尔误命中，一旦把模糊匹配也当锚点，错一条会把周围一堆 UNKNOWN
  全带偏
- 已经被分类（非 UNKNOWN）的 item 不会被覆盖
- 前置条件：items 已按 bill_time 升序排列（pipeline 中 merge_payee
  / merge_refund 都会排序）

举例：
- 12:00~12:30 在菜场连刷 4 笔，其中 12:10 的「XX 菜摊」精确匹配到
  「买菜」分类——这条作为锚点，剩下 3 笔 UNKNOWN 都被标为买菜
- 14:00 的「肯德基」和 12:30 的菜摊锚点相距 1.5 小时，超出窗口，
  不会被误判为买菜
"""

import logging
from typing import List

from bill_item import BillItem, ClassifyAlg
from category import ExpenseCategory
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)

# 已是 BUY_VEGETABLES 的 item 前后多少秒内的 UNKNOWN item 也判为买菜
BUY_VEGETABLES_TIME_RANGE = 3600


class WetMarket(Step):
    """以"已精确匹配为买菜"的 item 为锚点，把 1 小时窗口内的 UNKNOWN item
    一并标为买菜。要求 items 已按 bill_time 升序排列。
    """

    name = "wet_market"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        mark_count = 0
        s = 0
        e = 0
        for i, anchor in enumerate(items):
            if anchor.category != ExpenseCategory.BUY_VEGETABLES or anchor.classify_alg != ClassifyAlg.MATCH:
                continue

            bill_time = anchor.bill_time
            while s < i and bill_time - items[s].bill_time > BUY_VEGETABLES_TIME_RANGE:
                s += 1
            while e + 1 < len(items) and items[e + 1].bill_time - bill_time < BUY_VEGETABLES_TIME_RANGE:
                e += 1

            for j in range(s, e + 1):
                if j == i:
                    continue
                if items[j].category == ExpenseCategory.UNKNOWN:
                    items[j].category = ExpenseCategory.BUY_VEGETABLES
                    items[j].classify_alg = ClassifyAlg.WET_MARKET
                    mark_count += 1

        logger.debug("时间段买菜标记 item size:{}".format(mark_count))
        return items
