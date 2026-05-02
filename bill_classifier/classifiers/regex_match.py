"""substring 包含匹配：先 item_name，再 payee。

逻辑：
- 飞书分类表里有两列「模糊匹配」字典，名字叫"regular"但实际存的
  是关键词，匹配方式是 substring 包含（不是真正的正则）：
    - item_category_regular_dict: 关键词 → category
    - payee_category_regular_dict: 关键词 → category
- 对每条 UNKNOWN item：
    1. 遍历 item_category_regular_dict，第一个被 item.item_name 包含的
       关键词命中
    2. 否则遍历 payee_category_regular_dict，同样取第一个命中
    3. 都不命中 → 留给后续 step
- 命中后 classify_alg 标 ClassifyAlg.REGULAR
  （注意：MATCH 才能当 wet_market 锚点，REGULAR 不行）

依赖飞书 IO；失败时只跳过本 step。

举例（表里有 "地铁" → 交通，"麦当劳" → 餐饮）：
- item_name="北京地铁充值"  → 包含"地铁"，TRANSPORTATION
- item_name="商品", payee="麦当劳金辉店" → 包含"麦当劳"，CATERING
- item_name 命中后不再尝试 payee 表（first match wins）
"""

import logging
from typing import List

from bill_item import BillItem, ClassifyAlg
from category import ExpenseCategory, Lifecycle
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


class RegexMatch(Step):
    """飞书"模糊匹配"列其实是 substring 包含匹配（保留原语义）。

    依赖飞书拉取的分类配置；拉取失败时只跳过本 step。
    """

    name = "regex_match"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        ok, info = ctx.category_info_loader.get()
        if not ok or info is None:
            logger.error("regex_match 跳过：CategoryInfo 加载失败")
            return items

        mark_count = 0
        for item in items:
            if item.lifecycle != Lifecycle.UNPROCESSED or item.category != ExpenseCategory.UNKNOWN:
                continue

            matched = False
            for needle, category in info.item_category_regular_dict.items():
                if needle in item.item_name:
                    item.category = category
                    item.classify_alg = ClassifyAlg.REGULAR
                    item.lifecycle = Lifecycle.CLASSIFIED
                    mark_count += 1
                    matched = True
                    break
            if matched:
                continue

            for needle, category in info.payee_category_regular_dict.items():
                if needle in item.payee:
                    item.category = category
                    item.classify_alg = ClassifyAlg.REGULAR
                    item.lifecycle = Lifecycle.CLASSIFIED
                    mark_count += 1
                    break

        logger.debug("regex_match 标记 item size:{}".format(mark_count))
        return items
