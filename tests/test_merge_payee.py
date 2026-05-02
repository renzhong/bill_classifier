from category import Lifecycle
from classifiers.merge_payee import MergePayee

from helpers import make_context, make_item


def test_regex_rule_merges_same_owner():
    items = [
        make_item(item_name="余额宝-XX收益发放", amount=1.5, owner="A", bill_time=1),
        make_item(item_name="余额宝-YY收益发放", amount=2.5, owner="A", bill_time=2),
        make_item(item_name="余额宝-ZZ收益发放", amount=3.0, owner="B", bill_time=3),
    ]
    out = MergePayee().run(items, make_context())
    by_owner = {it.owner: it for it in out}
    assert by_owner["A"].amount == 4.0
    assert by_owner["B"].amount == 3.0
    assert len(out) == 2


def test_match_rule_merges_by_payee_target():
    items = [
        make_item(payee="北京轨道交通路网管理有限公司", amount=10, owner="A"),
        make_item(payee="北京轨道交通路网管理有限公司", amount=5, owner="A"),
        make_item(payee="星巴克", amount=30, owner="A"),
    ]
    out = MergePayee().run(items, make_context())
    metro = [it for it in out if it.payee == "北京轨道交通路网管理有限公司"]
    starbucks = [it for it in out if it.payee == "星巴克"]
    assert len(metro) == 1
    assert metro[0].amount == 15
    assert len(starbucks) == 1
    assert starbucks[0].amount == 30


def test_already_categorized_items_skipped():
    """非 UNKNOWN 的 item 不参与合并。"""
    a = make_item(item_name="余额宝-X收益发放", amount=1, owner="A")
    b = make_item(item_name="余额宝-Y收益发放", amount=2, owner="A")
    b.lifecycle = Lifecycle.SKIPPED
    out = MergePayee().run([a, b], make_context())
    assert len(out) == 2
    # b 原样保留
    assert any(it is b and it.amount == 2 for it in out)


def test_output_sorted_by_bill_time():
    items = [
        make_item(payee="x", bill_time=10),
        make_item(payee="x", bill_time=1),
        make_item(payee="x", bill_time=5),
    ]
    out = MergePayee().run(items, make_context())
    assert [it.bill_time for it in out] == [1, 5, 10]


def test_unknown_rule_type_is_noop():
    items = [make_item(payee="x"), make_item(payee="y")]
    step = MergePayee(rules=[{"type": "weird", "col": "payee"}])
    out = step.run(items, make_context())
    assert len(out) == 2
