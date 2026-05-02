"""把 bill_type ∈ {INCOME, OTHER} 的条目标 SKIPPED + NON_EXPENSE。

把这个职责从 `exact_match` 中拆出来：
- 旧设计：exact_match 顺手把 bill_type != EXPENSE 的 item 标 SKIP，跟分类职责混在一起
- 新设计：独立 step `non_expense_skip` 负责把非支出（INCOME / OTHER）标 SKIPPED，
         分类 step 只关心 UNPROCESSED 的 EXPENSE

实施位置：cross_month_unified 之后、exact_match 之前。
理由：cross_month_unified 已经把"跨月退款"挑出来标 CROSS_MONTH_REFUND（这些是
OTHER 类的合法条目，需要在右侧提醒），non_expense_skip 跑到它们时
lifecycle != UNPROCESSED 会自动跳过，不会误覆盖。

举例：
- bill_type=INCOME（工资、转账收）→ SKIPPED + NON_EXPENSE
- bill_type=OTHER（不计支出 / 余额宝收益）→ SKIPPED + NON_EXPENSE
- bill_type=OTHER 但已被 cross_month_unified 标 CROSS_MONTH_REFUND → 跳过不动
- bill_type=EXPENSE → 不动，留给 exact_match 等分类 step 处理
"""

import logging
from typing import List

from bill_item import BillItem, BillType
from category import ExpenseCategory, Lifecycle, SkipReason
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


class NonExpenseSkip(Step):
    """非支出条目（INCOME / OTHER）标 SKIPPED + NON_EXPENSE。"""

    name = "non_expense_skip"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        count = 0
        for item in items:
            if item.lifecycle != Lifecycle.UNPROCESSED:
                continue
            if item.bill_type == BillType.EXPENSE:
                continue
            item.category = ExpenseCategory.SKIP  # 双写：迁移期保留旧字段
            item.lifecycle = Lifecycle.SKIPPED
            item.skip_reason = SkipReason.NON_EXPENSE
            count += 1
        logger.info("non_expense_skip 标记数:%d", count)
        return items
