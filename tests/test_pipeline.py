from types import SimpleNamespace

import pipeline
from bill_item import ClassifyAlg
from category import CategoryInfo, ExpenseCategory
from classifiers.base import CategoryInfoLoader

from helpers import FakeGPTClassifier, make_item


def _info_with_metro_match():
    info = CategoryInfo()
    info.item_category_dict = {"地铁": ExpenseCategory.TRANSPORTATION}
    info.payee_category_dict = {}
    info.item_category_regular_dict = {}
    info.payee_category_regular_dict = {}
    return info


def _bill_config(disabled=None, call_limit=-1):
    return SimpleNamespace(
        gpt_config=SimpleNamespace(call_limit=call_limit),
        strategy_config=SimpleNamespace(disabled_steps=disabled or []),
    )


def test_default_pipeline_routes_through_exact_match_then_gpt():
    items = [
        make_item(item_name="地铁", payee="北京地铁", order_id="O1"),
        make_item(item_name="未知商品", payee="未知店", order_id="O2"),
    ]
    fake_gpt = FakeGPTClassifier(default="餐饮")
    out = pipeline.run_pipeline(
        items,
        bill_config=_bill_config(),
        category_info_loader=CategoryInfoLoader(fetch=lambda: (True, _info_with_metro_match())),
        gpt_classifier_factory=lambda: fake_gpt,
    )
    by_name = {it.item_name: it for it in out}
    assert by_name["地铁"].category == ExpenseCategory.TRANSPORTATION
    assert by_name["地铁"].classify_alg == ClassifyAlg.MATCH
    assert by_name["未知商品"].category == ExpenseCategory.CATERING
    assert by_name["未知商品"].classify_alg == ClassifyAlg.GPT


def test_disabled_gpt_step_leaves_unknown():
    items = [make_item(item_name="未知商品", payee="未知店", order_id="O1")]
    fake_gpt = FakeGPTClassifier(default="餐饮")
    out = pipeline.run_pipeline(
        items,
        bill_config=_bill_config(disabled=["gpt"]),
        category_info_loader=CategoryInfoLoader(fetch=lambda: (True, _info_with_metro_match())),
        gpt_classifier_factory=lambda: fake_gpt,
    )
    assert out[0].category == ExpenseCategory.UNKNOWN
    assert fake_gpt.calls == []


def test_category_info_load_failure_only_breaks_dependent_steps():
    """飞书 IO 失败：exact_match / regex_match 跳过，gpt 等仍能跑。"""
    items = [make_item(item_name="未知商品", payee="未知店", order_id="O1")]
    fake_gpt = FakeGPTClassifier(default="餐饮")
    fetches = []

    def failing_fetch():
        fetches.append(1)
        return False, None

    out = pipeline.run_pipeline(
        items,
        bill_config=_bill_config(),
        category_info_loader=CategoryInfoLoader(fetch=failing_fetch),
        gpt_classifier_factory=lambda: fake_gpt,
    )
    assert out[0].category == ExpenseCategory.CATERING
    assert out[0].classify_alg == ClassifyAlg.GPT
    # exact_match 和 regex_match 共享 loader，只触发一次 fetch
    assert len(fetches) == 1


def test_build_steps_filters_disabled():
    steps = pipeline.build_steps(disabled=["gpt", "wet_market"])
    names = [s.name for s in steps]
    assert "gpt" not in names
    assert "wet_market" not in names
    assert "exact_match" in names


def test_strategy_module_exposes_bill_strategy():
    """对外签名不变：main.py 的 import 与调用方式仍可用。"""
    import strategy
    assert callable(strategy.bill_strategy)
