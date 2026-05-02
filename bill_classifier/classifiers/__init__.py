from classifiers.base import Step, Context, CategoryInfoLoader
from classifiers.meican_filter import MeicanFilter
from classifiers.merge_payee import MergePayee
from classifiers.merge_refund import MergeRefund
from classifiers.taobao_balance_merge import TaobaoBalanceMerge
from classifiers.cross_month_unified import CrossMonthUnified
from classifiers.non_expense_skip import NonExpenseSkip
from classifiers.exact_match import ExactMatch
from classifiers.regex_match import RegexMatch
from classifiers.skip_keywords import SkipKeywords
from classifiers.wet_market import WetMarket
from classifiers.neighbor_inference import NeighborInference
from classifiers.gpt import GPTStep

DEFAULT_STEPS = [
    "meican_filter",
    "merge_payee",
    "merge_refund",
    "taobao_balance_merge",
    "cross_month_unified",
    # skip_keywords 在 non_expense_skip 之前：让黑名单只看 item_name，
    # 不被 bill_type=OTHER 的条目提前 SKIP 掉（典型：余额宝-自动转入）。
    "skip_keywords",
    "non_expense_skip",
    "exact_match",
    "regex_match",
    "wet_market",
    "neighbor_inference",
    "gpt",
]

STEP_REGISTRY = {
    "meican_filter": MeicanFilter,
    "merge_payee": MergePayee,
    "merge_refund": MergeRefund,
    "taobao_balance_merge": TaobaoBalanceMerge,
    "cross_month_unified": CrossMonthUnified,
    "non_expense_skip": NonExpenseSkip,
    "exact_match": ExactMatch,
    "regex_match": RegexMatch,
    "skip_keywords": SkipKeywords,
    "wet_market": WetMarket,
    "neighbor_inference": NeighborInference,
    "gpt": GPTStep,
}

__all__ = [
    "Step",
    "Context",
    "CategoryInfoLoader",
    "DEFAULT_STEPS",
    "STEP_REGISTRY",
]
