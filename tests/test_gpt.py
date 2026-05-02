from types import SimpleNamespace

from category import ClassifyAlg, ExpenseCategory, Lifecycle
from classifiers.gpt import GPTStep

from helpers import FakeGPTClassifier, make_context, make_item


def _bill_config(call_limit=-1):
    """构造仅含 GPTStep 用到的 call_limit 字段的最小 BillConfig 替身。"""
    return SimpleNamespace(gpt_config=SimpleNamespace(call_limit=call_limit))


def test_unknown_item_classified_via_gpt():
    item = make_item(item_name="某商品", payee="某店", amount=12.3, bill_time=1)
    fake = FakeGPTClassifier(default="餐饮")
    ctx = make_context(gpt_classifier=fake, bill_config=_bill_config())
    GPTStep().run([item], ctx)
    assert item.category == ExpenseCategory.CATERING
    assert item.classify_alg == ClassifyAlg.GPT
    assert fake.calls == [("某商品", "某店", 12.3, 1)]


def test_already_categorized_skipped_no_call():
    item = make_item(item_name="x", payee="y")
    item.lifecycle = Lifecycle.SKIPPED
    fake = FakeGPTClassifier(default="餐饮")
    GPTStep().run([item], make_context(gpt_classifier=fake, bill_config=_bill_config()))
    assert fake.calls == []
    assert item.lifecycle == Lifecycle.SKIPPED


def test_meituan_payee_skipped():
    a = make_item(payee="美团")
    b = make_item(payee="美团平台商户")
    fake = FakeGPTClassifier(default="餐饮")
    GPTStep().run([a, b], make_context(gpt_classifier=fake, bill_config=_bill_config()))
    assert fake.calls == []
    assert a.lifecycle == Lifecycle.UNPROCESSED
    assert b.lifecycle == Lifecycle.UNPROCESSED


def test_jd_with_order_id_in_name_skipped():
    a = make_item(payee="京东", item_name="商品-订单编号:12345")
    b = make_item(payee="京东", item_name="正常商品名")
    fake = FakeGPTClassifier(default="餐饮")
    GPTStep().run([a, b], make_context(gpt_classifier=fake, bill_config=_bill_config()))
    assert len(fake.calls) == 1
    assert a.lifecycle == Lifecycle.UNPROCESSED
    assert b.category == ExpenseCategory.CATERING


def test_call_limit_caps_invocations():
    items = [make_item(item_name=f"i{i}", payee=f"p{i}") for i in range(5)]
    fake = FakeGPTClassifier(default="餐饮")
    GPTStep().run(items, make_context(gpt_classifier=fake, bill_config=_bill_config(call_limit=2)))
    assert len(fake.calls) == 2
    assert sum(1 for it in items if it.category == ExpenseCategory.CATERING) == 2


def test_unknown_response_text_does_not_set_category():
    item = make_item(item_name="x", payee="y")
    fake = FakeGPTClassifier(default="不是合法分类的随便字符串")
    GPTStep().run([item], make_context(gpt_classifier=fake, bill_config=_bill_config()))
    assert item.lifecycle == Lifecycle.UNPROCESSED


def test_empty_response_does_not_set_category():
    item = make_item(item_name="x", payee="y")
    fake = FakeGPTClassifier(default="")
    GPTStep().run([item], make_context(gpt_classifier=fake, bill_config=_bill_config()))
    assert item.lifecycle == Lifecycle.UNPROCESSED


def test_no_classifier_skips_step():
    item = make_item(item_name="x", payee="y")
    GPTStep().run([item], make_context(gpt_classifier=None, bill_config=_bill_config()))
    assert item.lifecycle == Lifecycle.UNPROCESSED
