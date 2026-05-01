import logging
from typing import List, Optional

from bill_config import BillConfig
from bill_item import BillItem
from category import CategoryInfo
from classifier_gpt import GPTClassifier
from classifiers import DEFAULT_STEPS, STEP_REGISTRY, CategoryInfoLoader, Context, Step
from feishu import FeishuSheetAPI

logger = logging.getLogger(__name__)


def _default_category_info_fetch(bill_config: BillConfig):
    """触发飞书 IO 拉取分类配置；保留原 InitCategoryInfo 的语义。"""
    feishu_cfg = bill_config.feishu_config
    feishu_api = FeishuSheetAPI(feishu_cfg.user_access_token, feishu_cfg.category_sheet_token)

    info = CategoryInfo()
    range_name = '125297'

    ok, info.payee_category_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!A:B')
    if not ok:
        logger.error("获取分类信息失败")
        return False, None

    ok, info.item_category_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!D:E')
    if not ok:
        logger.error("获取分类信息失败")
        return False, None

    ok, info.payee_category_regular_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!G:H')
    if not ok:
        logger.error("获取分类信息失败")
        return False, None

    ok, info.item_category_regular_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!J:K')
    if not ok:
        logger.error("获取分类信息失败")
        return False, None

    return True, info


def build_steps(disabled: Optional[List[str]] = None) -> List[Step]:
    disabled_set = set(disabled or [])
    steps: List[Step] = []
    for name in DEFAULT_STEPS:
        if name in disabled_set:
            logger.info("step {} disabled by config".format(name))
            continue
        steps.append(STEP_REGISTRY[name]())
    return steps


def run_pipeline(
    items: List[BillItem],
    bill_config: BillConfig,
    steps: Optional[List[Step]] = None,
    category_info_loader: Optional[CategoryInfoLoader] = None,
    gpt_classifier_factory=None,
) -> List[BillItem]:
    """主入口：按 disabled_steps 配置组装 step 列表，依次执行。"""

    if steps is None:
        disabled = getattr(bill_config, "strategy_config", None)
        disabled_list = disabled.disabled_steps if disabled else []
        steps = build_steps(disabled_list)

    if category_info_loader is None:
        category_info_loader = CategoryInfoLoader(
            fetch=lambda: _default_category_info_fetch(bill_config)
        )

    if gpt_classifier_factory is None:
        gpt_classifier_factory = lambda: GPTClassifier(bill_config.gpt_config.current_model)

    ctx = Context(
        bill_config=bill_config,
        category_info_loader=category_info_loader,
        gpt_classifier_factory=gpt_classifier_factory,
    )

    for step in steps:
        items = step.run(items, ctx)
        logger.info("after step {} bill item:{}".format(step.name, len(items)))

    return items
