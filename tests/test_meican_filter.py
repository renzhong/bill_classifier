import datetime

from category import BillType, ClassifyAlg, Lifecycle
from classifiers.meican_filter import MeicanFilter

from helpers import make_context, make_item


def _ts(year=2025, month=1, day=6, hour=18, minute=0):
    """2025-01-06 是周一。"""
    return datetime.datetime(year, month, day, hour, minute).timestamp()


def test_weekday_18_marked_skip():
    item = make_item(payee="高德地图总部-美餐餐厅A区", bill_time=_ts(hour=18))
    MeicanFilter().run([item], make_context())
    assert item.lifecycle == Lifecycle.SKIPPED
    assert item.classify_alg == ClassifyAlg.COMPANY_SUBSIDY


def test_weekday_21_marked_skip():
    item = make_item(payee="高德地图总部-美餐餐厅B区", bill_time=_ts(hour=21))
    MeicanFilter().run([item], make_context())
    assert item.lifecycle == Lifecycle.SKIPPED


def test_weekday_19_not_marked():
    item = make_item(payee="高德地图总部-美餐餐厅A区", bill_time=_ts(hour=19))
    MeicanFilter().run([item], make_context())
    assert item.lifecycle == Lifecycle.UNPROCESSED


def test_weekend_18_not_marked():
    item = make_item(
        payee="高德地图总部-美餐餐厅A区",
        bill_time=_ts(year=2025, month=1, day=11, hour=18),  # 周六
    )
    MeicanFilter().run([item], make_context())
    assert item.lifecycle == Lifecycle.UNPROCESSED


def test_other_payee_untouched():
    item = make_item(payee="星巴克", bill_time=_ts(hour=18))
    MeicanFilter().run([item], make_context())
    assert item.lifecycle == Lifecycle.UNPROCESSED


def test_returns_same_list_object():
    items = [make_item(payee="a")]
    out = MeicanFilter().run(items, make_context())
    assert out is items


def test_income_in_window_also_marked_when_payee_matches():
    """当前实现不区分 bill_type，落在窗口就标 SKIP（保留原行为）。"""
    item = make_item(
        payee="高德地图总部-美餐餐厅",
        bill_type=BillType.INCOME,
        bill_time=_ts(hour=18),
    )
    MeicanFilter().run([item], make_context())
    assert item.lifecycle == Lifecycle.SKIPPED
