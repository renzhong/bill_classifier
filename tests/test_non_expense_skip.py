from bill_item import BillType
from category import ExpenseCategory, Lifecycle, SkipReason
from classifiers.non_expense_skip import NonExpenseSkip

from helpers import make_context, make_item


def test_expense_item_unchanged():
    item = make_item(bill_type=BillType.EXPENSE)
    NonExpenseSkip().run([item], make_context())
    assert item.lifecycle == Lifecycle.UNPROCESSED
    assert item.skip_reason is None


def test_income_item_marked_skipped():
    item = make_item(bill_type=BillType.INCOME)
    NonExpenseSkip().run([item], make_context())
    assert item.lifecycle == Lifecycle.SKIPPED
    assert item.skip_reason == SkipReason.NON_EXPENSE


def test_other_item_marked_skipped():
    item = make_item(bill_type=BillType.OTHER)
    NonExpenseSkip().run([item], make_context())
    assert item.lifecycle == Lifecycle.SKIPPED
    assert item.skip_reason == SkipReason.NON_EXPENSE


def test_already_skipped_not_overridden():
    """已被前面 step 标 SKIPPED 的不被覆盖。"""
    item = make_item(bill_type=BillType.OTHER)
    item.lifecycle = Lifecycle.SKIPPED
    item.skip_reason = SkipReason.FILTER  # 假设之前 meican_filter 标的
    NonExpenseSkip().run([item], make_context())
    # skip_reason 不被改写
    assert item.skip_reason == SkipReason.FILTER


def test_cross_month_refund_not_overridden():
    """已被 cross_month_unified 标 CROSS_MONTH_REFUND 的不被覆盖（即使 bill_type=OTHER）。"""
    item = make_item(bill_type=BillType.OTHER)
    item.lifecycle = Lifecycle.CROSS_MONTH_REFUND
    item.cross_month_origin = {"payee": "x", "amount": 1.0, "bill_time": 0,
                                "item_name": "y", "order_id": "", "bill_source": "wechat", "owner": ""}
    NonExpenseSkip().run([item], make_context())
    assert item.lifecycle == Lifecycle.CROSS_MONTH_REFUND
    assert item.skip_reason is None
    assert item.cross_month_origin is not None


def test_classified_not_overridden():
    """理论上 non_expense_skip 跑在分类 step 前，但防御式测试。"""
    item = make_item(bill_type=BillType.EXPENSE)
    item.lifecycle = Lifecycle.CLASSIFIED
    item.category = ExpenseCategory.CATERING
    NonExpenseSkip().run([item], make_context())
    assert item.lifecycle == Lifecycle.CLASSIFIED
    assert item.category == ExpenseCategory.CATERING


def test_mixed_bill_types_correctly_split():
    expense = make_item(bill_type=BillType.EXPENSE)
    income = make_item(bill_type=BillType.INCOME)
    other = make_item(bill_type=BillType.OTHER)
    NonExpenseSkip().run([expense, income, other], make_context())
    assert expense.lifecycle == Lifecycle.UNPROCESSED
    assert income.lifecycle == Lifecycle.SKIPPED
    assert other.lifecycle == Lifecycle.SKIPPED


def test_step_registered_in_pipeline():
    from classifiers import DEFAULT_STEPS, STEP_REGISTRY
    assert "non_expense_skip" in DEFAULT_STEPS
    assert "non_expense_skip" in STEP_REGISTRY
    # 位置：cross_month_unified 之后、exact_match 之前
    idx_cm = DEFAULT_STEPS.index("cross_month_unified")
    idx_nes = DEFAULT_STEPS.index("non_expense_skip")
    idx_em = DEFAULT_STEPS.index("exact_match")
    assert idx_cm < idx_nes < idx_em
