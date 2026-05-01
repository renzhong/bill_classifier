from classifiers.base import Step, Context, CategoryInfoLoader
from classifiers.meican_filter import MeicanFilter
from classifiers.merge_payee import MergePayee
from classifiers.merge_refund import MergeRefund
from classifiers.exact_match import ExactMatch
from classifiers.regex_match import RegexMatch
from classifiers.skip_keywords import SkipKeywords
from classifiers.wet_market import WetMarket
from classifiers.gpt import GPTStep

DEFAULT_STEPS = [
    "meican_filter",
    "merge_payee",
    "merge_refund",
    "exact_match",
    "regex_match",
    "skip_keywords",
    "wet_market",
    "gpt",
]

STEP_REGISTRY = {
    "meican_filter": MeicanFilter,
    "merge_payee": MergePayee,
    "merge_refund": MergeRefund,
    "exact_match": ExactMatch,
    "regex_match": RegexMatch,
    "skip_keywords": SkipKeywords,
    "wet_market": WetMarket,
    "gpt": GPTStep,
}

__all__ = [
    "Step",
    "Context",
    "CategoryInfoLoader",
    "DEFAULT_STEPS",
    "STEP_REGISTRY",
]
