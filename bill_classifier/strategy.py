import logging
import re

from feishu import FeishuSheetAPI
from bill_item import BillType, BillItem, ClassifyAlg
from typing import List
from bill_config import BillConfig
from category import ExpenseCategory, expense_category_mapping, CategoryInfo
from classifier_gpt import GPTClassifier

logger = logging.getLogger(__name__)

BUY_VEGETABLES_TIME_RANGE = 3600

def merge_refund_items(bill_item_list: List[BillItem]) -> List[BillItem]:
    logging.debug("合并退款账单 origin size:{}".format(len(bill_item_list)))
    order_items = {}
    merged_items = []
    for item in bill_item_list:
        if not item.order_id:
            item.category = ExpenseCategory.SKIP
            merged_items.append(item)
            logging.debug("退款记录丢失原始账单: {}".format(item))
            continue

        if item.order_id not in order_items:
            order_items[item.order_id] = []
        order_items[item.order_id].append(item)

    for order_id, items in order_items.items():
        if len(items) == 1:
            merged_items.append(items[0])
        else:
            # split the items into two lists: expense items and refund items
            expense_items = []
            refund_items = []
            for item in items:
                if item.bill_type == BillType.OTHER and '退款' in item.item_name:
                    refund_items.append(item)
                else:
                    expense_items.append(item)

            # merge expense items
            debug_str = ''
            if len(expense_items) > 0:
                # expense items 有大于 1 的情况，例如淘宝的预付款&尾款订单就会有两条 order id 相同的 item
                merged_item = expense_items[0]
                debug_str = debug_str + str(expense_items[0].amount)
                for item in expense_items[1:]:
                    merged_item.amount += item.amount
                    debug_str = debug_str + " + " + str(item.amount)

                # refund expense items
                for item in refund_items:
                    merged_item.amount -= item.amount
                    debug_str = debug_str + " - " + str(item.amount)

                if merged_item.amount == 0.0:
                    merged_item.category = ExpenseCategory.SKIP

                merged_items.append(merged_item)
                logging.debug("合并退款账单项: {} {} {} = {}".format(merged_item.order_id, merged_item.item_name, debug_str, merged_item.amount))
            else:
                for item in refund_items:
                    merged_items.append(item)

    return merged_items

def merge_balance_items(bill_item_list: List[BillItem]) -> List[BillItem]:
    regex_pattern = r'^余额宝.*收益发放$'

    balance_items = {}
    last_items = []

    for item in bill_item_list:
        # 如果 item_name 匹配正则表达式，则将它的金额加入 balance_items 列表
        if re.match(regex_pattern, item.item_name):
            if item.owner in balance_items:
                balance_items[item.owner].append(item)
            else:
                balance_items[item.owner] = [item]
        else:
            last_items.append(item)

    for owner, items in balance_items.items():
        logging.debug("{} has {} balance item".format(owner, len(items)))

        if len(items) == 0:
            continue
        merge_item = items[0]
        amount = 0
        for item in items[1:]:
            amount = amount + item.amount
        merge_item.amount = amount
        logging.debug("{} balance item:{}".format(owner, merge_item))
        last_items.append(merge_item)

    return last_items

def InitCategoryInfo(user_access_token: str, sheet_token: str):
    category_info = CategoryInfo()

    feishu_api = FeishuSheetAPI(user_access_token, sheet_token)

    range_name = '125297'

    ret, category_info.payee_category_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!A:B')
    if not ret:
        logging.error("获取分类信息失败")
        return False, {}

    ret, category_info.item_category_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!D:E')
    if not ret:
        logging.error("获取分类信息失败")
        return False, {}

    ret, category_info.payee_category_regular_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!G:H')
    if not ret:
        logging.error("获取分类信息失败")
        return False, {}

    ret, category_info.item_category_regular_dict = feishu_api.GetCategoryClassificationInfo(range_name + '!J:K')
    if not ret:
        logging.error("获取分类信息失败")
        return False, {}

    return True, category_info


def categorize_items(items: List[BillItem], bill_config: BillConfig) -> List[BillItem]:
    # debug info
    marked_item_count = 0
    mark_skip_count = 0
    mark_count = 0

    # set expense category for each item
    # 策略 1
    ret, category_info = InitCategoryInfo(bill_config.feishu_config.user_access_token, bill_config.feishu_config.category_sheet_token)
    if not ret:
        logging.error("获取分类信息失败")
        return False

    for item in items:
        if item.category != ExpenseCategory.UNKNOWN:
            marked_item_count += 1
            continue

        if item.bill_type != BillType.EXPENSE:
            item.category = ExpenseCategory.SKIP
            continue

        # 处理完全匹配
        if item.item_name in category_info.item_category_dict:  # noqa: F405
            item.category = category_info.item_category_dict[item.item_name]  # noqa: F405
            item.classify_alg = ClassifyAlg.MATCH
            mark_count += 1
            continue

        if item.payee in category_info.payee_category_dict:  # noqa: F405
            item.category = category_info.payee_category_dict[item.payee]  # noqa: F405
            item.classify_alg = ClassifyAlg.MATCH
            mark_count += 1
            continue

        # 处理正则匹配
        item_reg_match = False
        for item_reg, category in category_info.item_category_regular_dict.items():  # noqa: F405
            if item_reg in item.item_name:
                item.category = category
                item.classify_alg = ClassifyAlg.REGULAR
                item_reg_match = True
                mark_count += 1
                break
        if item_reg_match:
            continue

        payee_reg_match = False
        for payee_reg, category in category_info.payee_category_regular_dict.items():  # noqa: F405
            if payee_reg in item.payee:
                item.category = category
                item.classify_alg = ClassifyAlg.REGULAR
                payee_reg_match = True
                mark_count += 1
                break
        if payee_reg_match:
            continue

    logging.debug("after regex match item size:{}".format(len(items)))
    logging.debug("计算 category 前已标记过 category 的 item size:{}".format(marked_item_count))
    logging.debug("计算 category 时标记为 skip 的 item size:{}".format(mark_skip_count))
    logging.debug("计算 category 时标记为有效值的 item size:{}".format(mark_count))

    mark_count = 0
    # 策略 2
    s = 0
    e = 0
    for i, item in enumerate(items):
        # 只处理 完全匹配的买菜账单
        if item.category != ExpenseCategory.BUY_VEGETABLES or item.classify_alg != ClassifyAlg.MATCH:
            continue

        bill_time = item.bill_time
        while True:
            if s == i:
                break
            if bill_time - items[s].bill_time > BUY_VEGETABLES_TIME_RANGE:
                s += 1
            else:
                break
        while True:
            if e + 1 >= len(items):
                break
            if items[e + 1].bill_time - bill_time < BUY_VEGETABLES_TIME_RANGE:
                e += 1
            else:
                break

        for j in range(s, e):
            if j == i:
                continue
            if items[j].category == ExpenseCategory.UNKNOWN:
                items[j].category = ExpenseCategory.BUY_VEGETABLES
                items[j].classify_alg = ClassifyAlg.WET_MARKET
                mark_count += 1

    logging.debug("时间段买菜标记 item size:{}".format(mark_count))

    # 策略 3
    mark_count = 0
    classifier = GPTClassifier(bill_config.gpt_config.api_key)
    call_limit = bill_config.gpt_config.call_limit
    for i, item in enumerate(items):
        if call_limit >= 0 and mark_count == call_limit:
            break

        if item.category != ExpenseCategory.UNKNOWN:
            continue

        # 过滤一些无法识别的数据
        if item.payee == '美团' or item.payee == '美团平台商户':
            continue

        pattern = r"订单编号"
        if item.payee == '京东' and re.search(pattern, item.item_name):
            continue

        text = classifier.call(item.item_name, item.payee, item.amount, item.bill_time)
        logging.info("gpt classifier:{} {} -> {}".format(item.item_name, item.payee, text))
        if len(text) == 0:
            continue

        if text not in expense_category_mapping:
            continue

        item.category = expense_category_mapping[text]
        item.classify_alg = ClassifyAlg.GPT
        mark_count += 1
    logging.info("gpt cost token:{}".format(classifier.get_token_count()))
    logging.debug("GPT标记 item size:{}".format(mark_count))

    return True



def bill_strategy(bill_item_list, bill_config):
    # 分析数据
    #   1. 合并退款
    bill_item_list = merge_refund_items(bill_item_list)
    logging.info("after merge refund bill item:{}".format(len(bill_item_list)))

    #   2. 合并余额宝收益
    bill_item_list = merge_balance_items(bill_item_list)
    logging.info("after balance bill item:{}".format(len(bill_item_list)))

    bill_item_list = sorted(bill_item_list, key=lambda item: item.bill_time)

    #   2. 划分到某个大类
    ret = categorize_items(bill_item_list, bill_config)
    logging.info("after categorize bill item:{}".format(len(bill_item_list)))

    return ret, bill_item_list
