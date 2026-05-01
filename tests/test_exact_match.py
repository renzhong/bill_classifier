from bill_item import BillType, ClassifyAlg
from category import CategoryInfo, ExpenseCategory
from classifiers.exact_match import ExactMatch

from helpers import make_context, make_item


def _info():
    info = CategoryInfo()
    info.item_category_dict = {"地铁单程票": ExpenseCategory.TRANSPORTATION}
    info.payee_category_dict = {"星巴克": ExpenseCategory.CATERING}
    info.item_category_regular_dict = {}
    info.payee_category_regular_dict = {}
    return info


def test_item_name_hit_marks_match():
    item = make_item(item_name="地铁单程票")
    ExactMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.TRANSPORTATION
    assert item.classify_alg == ClassifyAlg.MATCH


def test_payee_hit_when_item_name_miss():
    item = make_item(item_name="未知商品", payee="星巴克")
    ExactMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.CATERING


def test_non_expense_marked_skip():
    item = make_item(item_name="工资", bill_type=BillType.INCOME)
    ExactMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.SKIP


def test_already_categorized_skipped():
    item = make_item(item_name="地铁单程票")
    item.category = ExpenseCategory.SKIP
    ExactMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.SKIP


def test_loader_failure_only_skips_this_step():
    """飞书 IO 失败时，只本 step 跳过，item 状态不变。"""
    item = make_item(item_name="地铁单程票")
    ExactMatch().run([item], make_context(info=None, ok=False))
    assert item.category == ExpenseCategory.UNKNOWN
    assert item.classify_alg == ClassifyAlg.UNKNOWN


def test_no_match_leaves_unknown():
    item = make_item(item_name="未知", payee="未知")
    ExactMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.UNKNOWN
