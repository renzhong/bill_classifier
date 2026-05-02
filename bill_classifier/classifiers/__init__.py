from classifiers.base import Step, Context, CategoryInfoLoader
from classifiers.meican_filter import MeicanFilter
from classifiers.merge_payee import MergePayee
from classifiers.merge_refund import MergeRefund
from classifiers.taobao_balance_merge import TaobaoBalanceMerge
from classifiers.cross_month_unified import CrossMonthUnified
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
    "exact_match",
    "regex_match",
    "skip_keywords",
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
