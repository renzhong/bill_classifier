from category import BillType, ClassifyAlg, Lifecycle
from classifiers.merge_refund import MergeRefund

from helpers import make_context, make_item


def test_no_order_id_passthrough():
    item = make_item(amount=10, order_id="")
    out = MergeRefund().run([item], make_context())
    assert len(out) == 1
    assert out[0] is item
    assert out[0].lifecycle == Lifecycle.UNPROCESSED
    assert out[0].skip_reason is None


def test_single_item_with_order_id_passthrough():
    item = make_item(amount=10, order_id="O1")
    out = MergeRefund().run([item], make_context())
    assert len(out) == 1
    assert out[0] is item
    assert out[0].lifecycle == Lifecycle.UNPROCESSED
    assert out[0].is_merged is False


def test_expense_minus_refund_zero_marks_skip():
    expense = make_item(amount=20, order_id="O1", item_name="商品", bill_time=10)
    refund = make_item(
        amount=20,
        order_id="O1",
        item_name="商品退款",
        bill_type=BillType.OTHER,
        bill_time=20,
    )
    out = MergeRefund().run([expense, refund], make_context())
    assert len(out) == 1
    assert out[0].amount == 0
    assert out[0].lifecycle == Lifecycle.SKIPPED
    assert out[0].classify_alg == ClassifyAlg.FULL_REFUND
    assert out[0].is_merged is True
    assert [it.bill_time for it in out[0].merged_from] == [10, 20]


def test_partial_refund_keeps_remainder():
    expense = make_item(amount=20, order_id="O1", item_name="商品", bill_time=10)
    refund = make_item(
        amount=5,
        order_id="O1",
        item_name="商品退款",
        bill_type=BillType.OTHER,
        bill_time=20,
    )
    out = MergeRefund().run([expense, refund], make_context())
    assert len(out) == 1
    assert out[0].amount == 15
    assert out[0].lifecycle == Lifecycle.UNPROCESSED
    assert out[0].classify_alg == ClassifyAlg.MERGED
    assert out[0].is_merged is True
    assert [it.bill_time for it in out[0].merged_from] == [10, 20]


def test_two_expenses_same_order_id_summed():
    """淘宝预付款 + 尾款会用同一 order_id。"""
    a = make_item(amount=10, order_id="O1", item_name="预付款")
    b = make_item(amount=30, order_id="O1", item_name="尾款")
    out = MergeRefund().run([a, b], make_context())
    assert len(out) == 1
    assert out[0].amount == 40


def test_only_refund_items_no_expense_kept_as_is():
    r1 = make_item(amount=5, order_id="O1", item_name="退款", bill_type=BillType.OTHER)
    r2 = make_item(amount=3, order_id="O1", item_name="退款", bill_type=BillType.OTHER)
    out = MergeRefund().run([r1, r2], make_context())
    assert len(out) == 2


def test_output_sorted_by_bill_time():
    items = [
        make_item(amount=1, order_id="A", bill_time=30),
        make_item(amount=1, order_id="B", bill_time=10),
        make_item(amount=1, order_id="C", bill_time=20),
    ]
    out = MergeRefund().run(items, make_context())
    assert [it.bill_time for it in out] == [10, 20, 30]
