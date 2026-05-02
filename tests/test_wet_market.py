from category import ClassifyAlg, ExpenseCategory, Lifecycle
from classifiers.wet_market import WetMarket

from helpers import make_context, make_item

ANCHOR_T = 10000
WINDOW = 3600  # BUY_VEGETABLES_TIME_RANGE


def _anchor():
    a = make_item(item_name="买菜锚点", bill_time=ANCHOR_T)
    a.category = ExpenseCategory.BUY_VEGETABLES
    a.classify_alg = ClassifyAlg.MATCH
    return a


def test_unknown_within_window_marked_buy_vegetables():
    left = make_item(item_name="近前", bill_time=ANCHOR_T - 100)
    items = [left, _anchor(), make_item(item_name="远后", bill_time=ANCHOR_T + 99999)]
    WetMarket().run(items, make_context())
    assert left.category == ExpenseCategory.BUY_VEGETABLES
    assert left.classify_alg == ClassifyAlg.WET_MARKET


def test_unknown_after_anchor_within_window_marked():
    """窗口右侧的 item 也应被标（修复了原代码 range(s, e) 漏右边界的 bug）。"""
    anchor = _anchor()
    right_close = make_item(item_name="近后1", bill_time=ANCHOR_T + 100)
    right_close2 = make_item(item_name="近后2", bill_time=ANCHOR_T + 200)
    WetMarket().run([anchor, right_close, right_close2], make_context())
    assert right_close.category == ExpenseCategory.BUY_VEGETABLES
    assert right_close.classify_alg == ClassifyAlg.WET_MARKET
    assert right_close2.category == ExpenseCategory.BUY_VEGETABLES
    assert right_close2.classify_alg == ClassifyAlg.WET_MARKET


def test_window_includes_both_sides_of_anchor():
    """同时验证锚点左右两侧 UNKNOWN item 都被标。"""
    left = make_item(item_name="近前", bill_time=ANCHOR_T - 100)
    right = make_item(item_name="近后", bill_time=ANCHOR_T + 100)
    WetMarket().run([left, _anchor(), right], make_context())
    assert left.category == ExpenseCategory.BUY_VEGETABLES
    assert right.category == ExpenseCategory.BUY_VEGETABLES


def test_unknown_outside_window_not_marked():
    far = make_item(item_name="远前", bill_time=ANCHOR_T - WINDOW - 100)
    items = [far, _anchor(), make_item(bill_time=ANCHOR_T + 99999)]
    WetMarket().run(items, make_context())
    assert far.lifecycle == Lifecycle.UNPROCESSED


def test_anchor_with_non_match_alg_does_not_trigger():
    anchor = make_item(item_name="也是买菜但不是 MATCH", bill_time=ANCHOR_T)
    anchor.category = ExpenseCategory.BUY_VEGETABLES
    anchor.classify_alg = ClassifyAlg.REGULAR
    near = make_item(item_name="附近", bill_time=ANCHOR_T - 100)
    WetMarket().run([near, anchor], make_context())
    assert near.lifecycle == Lifecycle.UNPROCESSED


def test_already_categorized_in_window_not_overwritten():
    near = make_item(item_name="近前", bill_time=ANCHOR_T - 100)
    near.category = ExpenseCategory.CATERING
    near.lifecycle = Lifecycle.CLASSIFIED
    WetMarket().run([near, _anchor()], make_context())
    assert near.category == ExpenseCategory.CATERING


def test_no_anchor_no_change():
    a = make_item(bill_time=100)
    b = make_item(bill_time=200)
    WetMarket().run([a, b], make_context())
    assert a.lifecycle == Lifecycle.UNPROCESSED
    assert b.lifecycle == Lifecycle.UNPROCESSED
