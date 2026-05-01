from category import ExpenseCategory
from classifiers.skip_keywords import SkipKeywords

from helpers import make_context, make_item


def test_default_blacklist_marks_skip():
    a = make_item(item_name="余额宝-自动转入")
    b = make_item(item_name="转账备注:微信转账")
    c = make_item(item_name="正常商品")
    SkipKeywords().run([a, b, c], make_context())
    assert a.category == ExpenseCategory.SKIP
    assert b.category == ExpenseCategory.SKIP
    assert c.category == ExpenseCategory.UNKNOWN


def test_already_categorized_skipped():
    a = make_item(item_name="余额宝-自动转入")
    a.category = ExpenseCategory.CATERING
    SkipKeywords().run([a], make_context())
    assert a.category == ExpenseCategory.CATERING


def test_custom_names():
    a = make_item(item_name="自定义跳过")
    SkipKeywords(names=["自定义跳过"]).run([a], make_context())
    assert a.category == ExpenseCategory.SKIP
