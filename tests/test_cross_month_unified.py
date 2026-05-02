import datetime

from bill_item import BillType
from category import ExpenseCategory
from classifiers.cross_month_unified import (
    CrossMonthUnified,
    _is_orphan_refund,
    _months_before,
    _normalize_payee,
)

from helpers import make_context, make_item


# 用 2025-10 当本月做测试，6 个月前 = 2025-04
CUR_YEAR, CUR_MONTH = 2025, 10
CUR_TIME = datetime.datetime(CUR_YEAR, CUR_MONTH, 15, 12, 0).timestamp()
LAST_TIME = datetime.datetime(CUR_YEAR, CUR_MONTH - 1, 15, 12, 0).timestamp()
TWO_MONTH_AGO = datetime.datetime(CUR_YEAR, CUR_MONTH - 2, 15, 12, 0).timestamp()


# ---------- 工具函数 ----------


def test_months_before_simple():
    assert _months_before(2025, 10, 3) == [(2025, 9), (2025, 8), (2025, 7)]


def test_months_before_cross_year():
    assert _months_before(2025, 2, 3) == [(2025, 1), (2024, 12), (2024, 11)]


def test_normalize_payee_strips_refund_suffix():
    assert _normalize_payee("北京大学国际医院-退款") == "北京大学国际医院"
    assert _normalize_payee("美团-退款") == "美团"
    assert _normalize_payee("普通商家") == "普通商家"
    assert _normalize_payee("") == ""


# ---------- _is_orphan_refund ----------


def test_orphan_refund_recognized_by_item_name():
    item = make_item(item_name="退款-某商品", bill_type=BillType.OTHER)
    assert _is_orphan_refund(item) is True


def test_orphan_refund_recognized_by_payee_suffix():
    item = make_item(payee="美团-退款", item_name="美团", bill_type=BillType.OTHER)
    assert _is_orphan_refund(item) is True


def test_orphan_refund_not_other_type_skipped():
    item = make_item(item_name="退款", bill_type=BillType.EXPENSE)
    assert _is_orphan_refund(item) is False


def test_orphan_refund_normal_other_skipped():
    item = make_item(item_name="收益发放", bill_type=BillType.OTHER)
    assert _is_orphan_refund(item) is False


# ---------- 反查（依赖 mock loader）----------


def _make_loader(history_items):
    def fn(months):
        return list(history_items)
    return fn


def _orphan_alipay_refund(amount, payee, oid="", t=CUR_TIME, item_name="退款-商品"):
    return make_item(
        amount=amount, payee=payee, item_name=item_name,
        bill_type=BillType.OTHER, order_id=oid,
        bill_time=t, bill_source="alipay",
    )


def _orphan_wechat_refund(amount, payee, t=CUR_TIME, item_name="商家-退款"):
    """微信跨月退款典型形态：payee 含 -退款 后缀，item_name 也是 payee 重复或'退款'。"""
    return make_item(
        amount=amount, payee=payee, item_name=item_name,
        bill_type=BillType.OTHER, order_id="wechat_refund_id_1",
        bill_time=t, bill_source="wechat",
    )


def _history_expense(amount, payee, source, oid="", t=LAST_TIME, item_name="某商品"):
    return make_item(
        amount=amount, payee=payee, item_name=item_name,
        bill_type=BillType.EXPENSE, order_id=oid,
        bill_time=t, bill_source=source,
    )


def test_alipay_order_id_core_match_relinks_to_right_extra():
    """支付宝跨月退款：order_id 核心段反查到唯一原支出。"""
    orphan = _orphan_alipay_refund(
        amount=100,
        payee="淘宝商家",
        oid="2025102023001101601400100131*3007421472149123455_236787279472125534",
    )
    history_origin = _history_expense(
        amount=300, payee="淘宝商家", source="alipay",
        oid="2025091523001101601400100131_3007421472149123455_advance",
    )
    step = CrossMonthUnified(history_loader=_make_loader([history_origin]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is not None
    assert orphan.cross_month_origin is not None
    assert orphan.cross_month_origin["amount"] == 300
    assert orphan.cross_month_origin["payee"] == "淘宝商家"


def test_alipay_order_id_no_match_falls_back_to_payee_amount():
    """支付宝 order_id 提取不到核心 → fallback (payee+amount) 唯一命中。"""
    orphan = _orphan_alipay_refund(
        amount=50, payee="某店铺", oid="simple_oid_no_underscore",
    )
    history_origin = _history_expense(
        amount=50, payee="某店铺", source="alipay", oid="hist_oid_001",
    )
    step = CrossMonthUnified(history_loader=_make_loader([history_origin]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is not None
    assert orphan.cross_month_origin["bill_time"] == history_origin.bill_time


def test_alipay_multiple_core_candidates_picks_latest():
    """支付宝核心段多候选 → 取最近一笔（bill_time 最大）。"""
    orphan = _orphan_alipay_refund(
        amount=50, payee="淘宝", oid="...*3007421472149123455_22",
    )
    older = _history_expense(
        amount=100, payee="淘宝", source="alipay",
        oid="aaa_3007421472149123455_advance", t=TWO_MONTH_AGO,
    )
    newer = _history_expense(
        amount=200, payee="淘宝", source="alipay",
        oid="bbb_3007421472149123455_advance", t=LAST_TIME,
    )
    step = CrossMonthUnified(history_loader=_make_loader([older, newer]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin["amount"] == 200
    assert orphan.cross_month_origin["bill_time"] == newer.bill_time


def test_wechat_unique_payee_amount_match_relinks():
    """微信跨月退款：(payee 剥后缀+amount) 唯一命中。"""
    orphan = _orphan_wechat_refund(amount=50, payee="北京大学国际医院-退款")
    history_origin = _history_expense(
        amount=50, payee="北京大学国际医院", source="wechat",
        oid="historic_wechat_oid",
    )
    step = CrossMonthUnified(history_loader=_make_loader([history_origin]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is not None
    assert orphan.cross_month_origin["payee"] == "北京大学国际医院"


def test_wechat_multiple_candidates_not_relinked():
    """微信多候选 → 不关联（保持 OTHER）。"""
    orphan = _orphan_wechat_refund(amount=50, payee="某店-退款")
    h1 = _history_expense(amount=50, payee="某店", source="wechat", oid="o1", t=LAST_TIME)
    h2 = _history_expense(amount=50, payee="某店", source="wechat", oid="o2", t=TWO_MONTH_AGO)
    step = CrossMonthUnified(history_loader=_make_loader([h1, h2]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is None
    assert orphan.cross_month_origin is None


def test_no_history_match_keeps_orphan_unchanged():
    """完全没匹配 → cross_month_origin 仍为 None。"""
    orphan = _orphan_wechat_refund(amount=99, payee="陌生店家-退款")
    history_origin = _history_expense(amount=50, payee="某店", source="wechat")
    step = CrossMonthUnified(history_loader=_make_loader([history_origin]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is None
    assert orphan.cross_month_origin is None


def test_amount_must_match_strictly():
    """部分退款（金额不等）不关联。"""
    orphan = _orphan_wechat_refund(amount=30, payee="某店-退款")
    history_origin = _history_expense(amount=50, payee="某店", source="wechat")
    step = CrossMonthUnified(history_loader=_make_loader([history_origin]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is None


def test_source_must_match_alipay_history_doesnt_help_wechat_orphan():
    """微信孤儿不能关联到支付宝历史（即使 payee+amount 匹配）。"""
    orphan = _orphan_wechat_refund(amount=50, payee="某店-退款")
    alipay_history = _history_expense(amount=50, payee="某店", source="alipay")
    step = CrossMonthUnified(history_loader=_make_loader([alipay_history]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is None


def test_history_must_be_expense_not_other():
    """历史中的 OTHER / INCOME 条目不参与反查。"""
    orphan = _orphan_wechat_refund(amount=50, payee="某店-退款")
    other_in_history = make_item(
        amount=50, payee="某店", item_name="某",
        bill_type=BillType.OTHER, order_id="x", bill_time=LAST_TIME,
        bill_source="wechat",
    )
    step = CrossMonthUnified(history_loader=_make_loader([other_in_history]))
    step.run([orphan], make_context())

    assert orphan.cross_month_origin is None


def test_no_orphans_no_history_loader_call():
    """没孤儿条目时不应该调用 history_loader。"""
    called = {"count": 0}

    def loader(months):
        called["count"] += 1
        return []

    normal = make_item(amount=10, item_name="正常消费", bill_type=BillType.EXPENSE)
    step = CrossMonthUnified(history_loader=loader)
    step.run([normal], make_context())
    assert called["count"] == 0


def test_empty_items_returns_empty_unchanged():
    step = CrossMonthUnified(history_loader=_make_loader([]))
    assert step.run([], make_context()) == []


def test_multiple_orphans_independent_lookup():
    """多个孤儿条目各自独立反查。"""
    orphan1 = _orphan_wechat_refund(amount=50, payee="医院-退款")
    orphan2 = _orphan_wechat_refund(amount=20, payee="美团-退款")
    h1 = _history_expense(amount=50, payee="医院", source="wechat", oid="o1")
    h2 = _history_expense(amount=20, payee="美团", source="wechat", oid="o2")
    step = CrossMonthUnified(history_loader=_make_loader([h1, h2]))
    step.run([orphan1, orphan2], make_context())

    assert orphan1.cross_month_origin is not None
    assert orphan2.cross_month_origin is not None


def test_history_loader_exception_does_not_break_pipeline():
    """history_loader 抛异常 → step 跳过，不影响其它 items。"""

    def bad_loader(months):
        raise RuntimeError("io fail")

    orphan = _orphan_wechat_refund(amount=50, payee="某店-退款")
    normal = make_item(amount=10, item_name="正常消费", bill_type=BillType.EXPENSE)
    step = CrossMonthUnified(history_loader=bad_loader)
    out = step.run([orphan, normal], make_context())

    assert orphan.cross_month_origin is None
    assert orphan in out and normal in out
