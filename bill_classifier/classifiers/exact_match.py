"""精确字典匹配：先按 item_name 查表，再按 payee 查表。

逻辑：
- 飞书分类表里维护两张精确匹配字典：
    - item_category_dict: item_name → ExpenseCategory
    - payee_category_dict: payee → ExpenseCategory
- 对每条 UNKNOWN 的支出 item：
    1. item_name 命中 item_category_dict → 取对应 category
    2. 否则 payee 命中 payee_category_dict → 取对应 category
    3. 都不命中 → 留给后续 step
- 命中后 classify_alg 标 ClassifyAlg.MATCH（这是 wet_market 锚点的判定条件）
- 非支出（INCOME / OTHER）直接标 SKIP

依赖飞书 IO 拉取的 CategoryInfo；拉取失败时只跳过本 step，
其他规则不受影响（ctx.category_info_loader 失败时返回 (False, None)）。

举例（飞书表配置：item="地铁单程票" → 交通；payee="星巴克" → 餐饮）：
- item_name="地铁单程票", payee="任意" → TRANSPORTATION
- item_name="未知商品", payee="星巴克" → CATERING
- item_name="未知", payee="未知" → 留给 regex_match / GPT
- bill_type=INCOME 的工资记录 → SKIP
"""

import logging
from typing import List

from bill_item import BillItem
from category import BillType, ClassifyAlg, Lifecycle, SkipReason
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


class ExactMatch(Step):
    """先按 item_name，再按 payee 做精确字典匹配。

    依赖飞书拉取的分类配置；拉取失败时只跳过本 step，不影响其他规则。
    """

    name = "exact_match"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        ok, info = ctx.category_info_loader.get()
        if not ok or info is None:
            logger.error("exact_match 跳过：CategoryInfo 加载失败")
            return items

        mark_count = 0
        for item in items:
            # 已被前置 step 处理过的（含 non_expense_skip 标的 SKIPPED 和
            # cross_month_unified 标的 CROSS_MONTH_REFUND）跳过
            if item.lifecycle != Lifecycle.UNPROCESSED:
                continue
            # 防御：理论上 non_expense_skip 已把非支出标 SKIPPED，不会到这里
            if item.bill_type != BillType.EXPENSE:
                item.lifecycle = Lifecycle.SKIPPED
                item.skip_reason = SkipReason.NON_EXPENSE
                continue

            if item.item_name in info.item_category_dict:
                item.category = info.item_category_dict[item.item_name]
                item.classify_alg = ClassifyAlg.MATCH
                item.lifecycle = Lifecycle.CLASSIFIED
                mark_count += 1
                continue

            if item.payee in info.payee_category_dict:
                item.category = info.payee_category_dict[item.payee]
                item.classify_alg = ClassifyAlg.MATCH
                item.lifecycle = Lifecycle.CLASSIFIED
                mark_count += 1

        logger.debug("exact_match 标记 item size:{}".format(mark_count))
        return items
