from bill_item import BillType
from category import ExpenseCategory, Lifecycle
from classifiers.taobao_balance_merge import (
    TaobaoBalanceMerge,
    _extract_core_order_id,
)

from helpers import make_context, make_item


# ---------- 核心订单号提取 ----------


def test_extract_core_t200p_charge_format():
    """充值订单 row[1] 真实形态：T200P + 19 位数字。"""
    assert _extract_core_order_id("T200P2613628093127195986") == "2613628093127195986"
    assert _extract_core_order_id("T200P2836266062041123455") == "2836266062041123455"


def test_extract_core_t200p_short_returns_none():
    assert _extract_core_order_id("T200P12345") is None
    assert _extract_core_order_id("T200Pabcdef") is None


def test_extract_core_refund_two_segments_format():
    """退款 row[1] 真实形态：<core>_<sub> 两段。"""
    oid = "2613032798634195986_217847532514198659"
    assert _extract_core_order_id(oid) == "2613032798634195986"


def test_extract_core_format_with_star():
    """row[0] 形式（罕见）：含 '*'。"""
    oid = "2025102023001101601400100131*3007421472149123455_236787279472125534"
    assert _extract_core_order_id(oid) == "3007421472149123455"


def test_extract_core_format_underscore_three_segments():
    """row[0] 三段形式（罕见）：取中间段。"""
    oid = "2025102023001101601403564129_3007448761561123455_235695216446125534"
    assert _extract_core_order_id(oid) == "3007448761561123455"


def test_extract_core_format_underscore_advance():
    oid = "2025102323001101601423912232_3015081734490123455_advance"
    assert _extract_core_order_id(oid) == "3015081734490123455"


def test_extract_core_simple_order_id_returns_none():
    """普通支付宝交易号无下划线无 T200P 无 * → 提取失败。"""
    assert _extract_core_order_id("2025102722001401601448284988") is None


def test_extract_core_short_or_non_digit_returns_none():
    assert _extract_core_order_id("foo_bar_baz") is None
    assert _extract_core_order_id("abc_12345") is None  # 第一段非数字
    assert _extract_core_order_id("") is None
    assert _extract_core_order_id(None) is None


# ---------- 合并行为 ----------


def _recharge(amount, core, t=0.0, payee="购物金"):
    """造一条充值条目（真实形态：payee=购物金，oid=T200P<core>）。"""
    return make_item(
        amount=amount,
        payee=payee,
        item_name="戴维贝拉购物金 充值享折上折【充1000得1030】",
        bill_type=BillType.EXPENSE,
        order_id=f"T200P{core}",
        bill_time=t,
    )


def _refund(amount, core, sub, t=0.0, payee="da**店"):
    """造一条退款条目（真实形态：payee=店铺名脱敏，oid=<core>_<sub>）。"""
    return make_item(
        amount=amount,
        payee=payee,
        item_name="退款-戴维贝拉购物金 充值享折上折【充1000得1030】",
        bill_type=BillType.OTHER,
        order_id=f"{core}_{sub}",
        bill_time=t,
    )


def test_recharge_full_refund_marks_skip():
    core = "3007421472149123455"
    rc = _recharge(1000, core, t=10)
    rf = _refund(1000, core, "236787279472125534", t=20)
    out = TaobaoBalanceMerge().run([rc, rf], make_context())

    assert len(out) == 1
    assert out[0] is rc  # 保留充值条目作为合并载体
    assert out[0].amount == 0
    assert out[0].lifecycle == Lifecycle.SKIPPED
    assert out[0].taobao_balance_extra == "购物金消费余额: 0.00"


def test_recharge_partial_refund_keeps_net():
    core = "3007421472149123455"
    rc = _recharge(1000, core, t=10)
    rf1 = _refund(125.64, core, "236787279472125534", t=20)
    rf2 = _refund(5.36, core, "236751492385125534", t=30)
    out = TaobaoBalanceMerge().run([rc, rf1, rf2], make_context())

    assert len(out) == 1
    assert out[0].amount == 869.00
    # 余额说明里也是净额
    assert out[0].taobao_balance_extra == "购物金消费余额: 869.00"
    # 净额非 0 不打 SKIP
    assert out[0].lifecycle == Lifecycle.UNPROCESSED


def test_only_refund_no_recharge_left_alone():
    """跨月场景：本月只看到退款，充值在上月 → 留给策略 3。"""
    core = "3007421472149123455"
    rf1 = _refund(125.64, core, "236787279472125534", t=10)
    rf2 = _refund(83.71, core, "236751492385125534", t=20)
    out = TaobaoBalanceMerge().run([rf1, rf2], make_context())

    # 两条退款原样保留，不合并
    assert len(out) == 2
    assert all(it.amount in (125.64, 83.71) for it in out)
    assert all(it.taobao_balance_extra is None for it in out)


def test_only_recharge_no_refund_left_alone():
    """同月只充值不退 → 不动。"""
    core = "3007421472149123455"
    rc = _recharge(1000, core, t=10)
    out = TaobaoBalanceMerge().run([rc], make_context())
    assert len(out) == 1
    assert out[0].amount == 1000
    assert out[0].taobao_balance_extra is None


def test_non_balance_items_unchanged():
    """非购物金 item 完全不动。"""
    a = make_item(amount=10, item_name="拿铁", bill_time=10)
    b = make_item(amount=20, item_name="奶粉", bill_time=20)
    out = TaobaoBalanceMerge().run([a, b], make_context())
    assert out == [a, b]
    assert all(it.taobao_balance_extra is None for it in out)


def test_two_independent_cores_each_merged_separately():
    rc1 = _recharge(1000, "3007421472149123455", t=10)
    rf1 = _refund(200, "3007421472149123455", "236787272534", t=20)
    rc2 = _recharge(500, "3008407116227123455", t=30)
    rf2 = _refund(100, "3008407116227123455", "236784939777", t=40)
    out = TaobaoBalanceMerge().run([rc1, rf1, rc2, rf2], make_context())
    assert len(out) == 2
    nets = sorted(it.amount for it in out)
    assert nets == [400.0, 800.0]


def test_balance_item_without_extractable_core_left_alone():
    """购物金 item 但 order_id 提取不到核心 → 不参与合并，保留原样。"""
    bad = make_item(
        amount=1000,
        item_name="购物金充值",
        bill_type=BillType.EXPENSE,
        order_id="20251022001401601",  # 没有下划线 / 星号
        bill_time=10,
    )
    out = TaobaoBalanceMerge().run([bad], make_context())
    assert len(out) == 1
    assert out[0] is bad
    assert out[0].amount == 1000
    assert out[0].taobao_balance_extra is None


def test_output_sorted_by_bill_time():
    a = make_item(amount=10, item_name="A", bill_time=30)
    b = make_item(amount=10, item_name="B", bill_time=10)
    rc = _recharge(1000, "3007421472149123455", t=20)
    rf = _refund(100, "3007421472149123455", "236787272534", t=40)
    out = TaobaoBalanceMerge().run([a, b, rc, rf], make_context())
    times = [it.bill_time for it in out]
    assert times == sorted(times)


def test_recharge_with_multiple_recharges_summed():
    """同 core 多笔充值（罕见，但理论上可能）—— 也按总额计算。"""
    core = "3007421472149123455"
    rc1 = _recharge(500, core, t=10)
    rc2 = _recharge(500, core, t=15)
    rf = _refund(200, core, "236787272534", t=20)
    out = TaobaoBalanceMerge().run([rc1, rc2, rf], make_context())
    # 合并后只剩 1 条（保留 rc1）
    assert len(out) == 1
    assert out[0] is rc1
    assert out[0].amount == 800.0


def test_balance_keyword_outside_taobao_format_not_merged():
    """item_name 含 '购物金' 但 order_id 不像淘宝（提取不到 core） → 不合并。"""
    rc = make_item(
        amount=1000,
        item_name="某购物金充值",
        bill_type=BillType.EXPENSE,
        order_id="abcdef",  # 提取不到
        bill_time=10,
    )
    rf = make_item(
        amount=200,
        item_name="退款-某购物金",
        bill_type=BillType.OTHER,
        order_id="ghijkl",  # 提取不到
        bill_time=20,
    )
    out = TaobaoBalanceMerge().run([rc, rf], make_context())
    # 两条都保留原样
    assert len(out) == 2
    assert all(it.taobao_balance_extra is None for it in out)
