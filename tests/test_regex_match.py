from category import CategoryInfo, ClassifyAlg, ExpenseCategory, Lifecycle
from classifiers.regex_match import RegexMatch

from helpers import make_context, make_item


def _info():
    info = CategoryInfo()
    info.item_category_dict = {}
    info.payee_category_dict = {}
    info.item_category_regular_dict = {"地铁": ExpenseCategory.TRANSPORTATION}
    info.payee_category_regular_dict = {"麦当劳": ExpenseCategory.CATERING}
    return info


def test_item_substring_hit():
    item = make_item(item_name="北京地铁充值")
    RegexMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.TRANSPORTATION
    assert item.classify_alg == ClassifyAlg.REGULAR


def test_payee_substring_hit_when_item_miss():
    item = make_item(item_name="商品", payee="麦当劳金辉店")
    RegexMatch().run([item], make_context(info=_info()))
    assert item.category == ExpenseCategory.CATERING


def test_already_categorized_skipped():
    item = make_item(item_name="地铁充值")
    item.lifecycle = Lifecycle.SKIPPED
    RegexMatch().run([item], make_context(info=_info()))
    assert item.lifecycle == Lifecycle.SKIPPED


def test_loader_failure_only_skips_this_step():
    item = make_item(item_name="地铁充值")
    RegexMatch().run([item], make_context(info=None, ok=False))
    assert item.lifecycle == Lifecycle.UNPROCESSED


def test_first_match_wins():
    """item_name 命中后不再尝试 payee 表。"""
    info = _info()
    info.payee_category_regular_dict = {"地铁": ExpenseCategory.HOME_CONSTRUCTION}
    item = make_item(item_name="北京地铁充值", payee="某地铁公司")
    RegexMatch().run([item], make_context(info=info))
    assert item.category == ExpenseCategory.TRANSPORTATION
