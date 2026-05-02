"""测试辅助：构造 BillItem / Context，无需真实飞书或 GPT。"""

from typing import List, Optional

from bill_item import BillItem
from category import BillType, CategoryInfo
from classifiers.base import CategoryInfoLoader, Context


def make_item(
    amount: float = 10.0,
    payee: str = "p",
    item_name: str = "i",
    bill_type: BillType = BillType.EXPENSE,
    order_id: str = "",
    bill_time: float = 0.0,
    bill_source: str = "alipay",
    owner: str = "u",
) -> BillItem:
    return BillItem(
        amount=amount,
        payee=payee,
        item_name=item_name,
        bill_type=bill_type,
        order_id=order_id,
        bill_time=bill_time,
        bill_source=bill_source,
        owner=owner,
    )


def make_loader(info: Optional[CategoryInfo] = None, ok: bool = True) -> CategoryInfoLoader:
    """ok=False 时模拟飞书 IO 失败。"""

    def fetch():
        return ok, info

    return CategoryInfoLoader(fetch=fetch)


def make_context(
    info: Optional[CategoryInfo] = None,
    ok: bool = True,
    gpt_classifier=None,
    bill_config=None,
) -> Context:
    return Context(
        bill_config=bill_config,
        category_info_loader=make_loader(info=info, ok=ok),
        gpt_classifier_factory=lambda: gpt_classifier,
    )


class FakeGPTClassifier:
    """记录调用并按预设规则返回的 GPT 分类器替身。"""

    def __init__(self, responses: Optional[dict] = None, default: str = ""):
        self.calls: List[tuple] = []
        self._responses = responses or {}
        self._default = default
        self._token_count = 0

    def call(self, item_name, payee, amount, timestamp):
        self.calls.append((item_name, payee, amount, timestamp))
        self._token_count += 1
        return self._responses.get((item_name, payee), self._default)

    def get_token_count(self):
        return self._token_count
