"""LLM 兜底：把仍是 UNKNOWN 的 item 丢给 LLM 分类。

逻辑：
- 经过前面所有 step 还是 UNKNOWN 的 item，作为最后一步交给 LLM
- LLM 返回的字符串若能在 expense_category_mapping 中找到对应枚举值，
  就采纳，classify_alg 标 ClassifyAlg.GPT；否则保留 UNKNOWN
- 显式跳过的场景（LLM 也无能为力，省 token）：
    - payee 是「美团」/「美团平台商户」（item_name 全是订单号，无上下文）
    - payee 是「京东」且 item_name 含「订单编号」（同上）
- 支持 call_limit：累计成功标记次数到达 call_limit 就停（防止失控烧钱）；
  call_limit < 0 表示不限制
- ctx.gpt_classifier_factory() 返回的 classifier 必须实现 .call() 和
  可选的 .get_token_count()；测试时可注入 fake

举例：
- item_name="某商品", payee="某店" → LLM 返回"餐饮" → CATERING
- payee="美团", item_name=任意 → 不调用 LLM，保持 UNKNOWN
- payee="京东", item_name="商品-订单编号:12345" → 不调用 LLM
- LLM 返回的字符串不在 ExpenseCategory 里 → 保持 UNKNOWN
- call_limit=2 时，前 2 条命中后停止处理后续 item
"""

import logging
import re
from typing import List

from bill_item import BillItem
from category import ClassifyAlg, Lifecycle, expense_category_mapping
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


class GPTStep(Step):
    """用 LLM 给剩余 UNKNOWN item 做兜底分类。

    会跳过：
    - 美团 / 美团平台商户（无足够上下文）
    - 京东 + item_name 含"订单编号"（同上）
    """

    name = "gpt"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        classifier = ctx.gpt_classifier_factory()
        call_limit = ctx.bill_config.gpt_config.call_limit
        mark_count = 0

        for item in items:
            if call_limit >= 0 and mark_count == call_limit:
                break
            if item.lifecycle != Lifecycle.UNPROCESSED:
                continue

            if item.payee == '美团' or item.payee == '美团平台商户':
                continue
            if item.payee == '京东' and re.search(r"订单编号", item.item_name):
                continue

            text = classifier.call(item.item_name, item.payee, item.amount, item.bill_time)
            logger.info("gpt classifier:{} {} -> {}".format(item.item_name, item.payee, text))
            if not text:
                continue
            if text not in expense_category_mapping:
                continue

            item.category = expense_category_mapping[text]
            item.classify_alg = ClassifyAlg.GPT
            item.lifecycle = Lifecycle.CLASSIFIED
            mark_count += 1

        if hasattr(classifier, "get_token_count"):
            logger.info("gpt cost token:{}".format(classifier.get_token_count()))
        logger.debug("GPT标记 item size:{}".format(mark_count))
        return items
