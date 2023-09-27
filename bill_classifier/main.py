#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import os  # noqa
import logging
import datetime
import sys
import configparser
import argparse
import openai

from feishu import FeishuSheetAPI
from category import ExpenseCategory, expense_category_mapping, CategoryInfo
from bill_item import BillType, BillItem, ClassifyAlg
from bill import AliPayBill, WeChatBill
from typing import List
from classifier_gpt import GPTClassifier
from bill_config import BillConfig
from bill_file import BillFile

BUY_VEGETABLES_TIME_RANGE = 3600

logger = logging.getLogger(__name__)

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
        if item.category != ExpenseCategory.UNKNOWN:
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
            if items[j].category == ExpenseCategory.BUY_VEGETABLES:
                item.category = ExpenseCategory.BUY_VEGETABLES
                item.classify_alg = ClassifyAlg.WET_MARKET
                mark_count += 1
                break
    logging.debug("时间段买菜标记 item size:{}".format(mark_count))

    # 策略 3
    mark_count = 0
    classifier = GPTClassifier()
    call_limit = bill_config.gpt_config.call_limit
    for i, item in enumerate(items):
        if call_limit >= 0 and mark_count == call_limit:
            break

        if item.category != ExpenseCategory.UNKNOWN:
            continue

        # 过滤一些无法识别的数据
        if item.payee == '美团' or item.payee == '美团平台商户':
            continue

        text = classifier.call(item.item_name, item.payee)
        logging.info("gpt classifier:{} {} -> {}".format(item.item_name, item.payee, text))
        if len(text) == 0:
            continue

        if text not in expense_category_mapping:
            continue

        item.category = expense_category_mapping[text]
        item.classify_alg = ClassifyAlg.GPT
        mark_count += 1

    logging.debug("GPT标记 item size:{}".format(mark_count))

    return True

def GetMonth():
    now = datetime.datetime.now()  # 获取当前日期时间
    month_str = ''
    if now.day >= 15:  # 如果今天是每个月的最后3天或最后一天
        month_str = now.strftime('%Y%m')  # 输出当前年月字符串，格式为YYYYMM
    else:  # 如果今天是每个月的前10天
        last_month = now - datetime.timedelta(days=20)  # 计算上个月的日期时间
        month_str = last_month.strftime('%Y%m')  # 输出上个月的年月字符串，格式为YYYYMM

    return month_str

def record_to_feishu(feishu_config, bill_item_dict):
    user_access_token = feishu_config.user_access_token
    bill_sheet_token = feishu_config.bill_sheet_token

    feishu_sheet_api = FeishuSheetAPI(user_access_token, bill_sheet_token)
    sheet_info = feishu_sheet_api.GetSheetInfo()

    month_str = GetMonth()
    sheet_name = "账单明细 " + month_str

    sheet_id = ''
    if sheet_name not in sheet_info:
        ret,sheet_id = feishu_sheet_api.AddNewSheet(sheet_name, len(sheet_info))
        if not ret:
            return False
    else:
        sheet_id = sheet_info[sheet_name]['sheet_id']

    bill_size = 0
    if "expense" in bill_item_dict:
        bill_size = bill_size + len(bill_item_dict['expense'])

    if bill_size > 200:
        add_rows = (bill_size // 100 + 1) * 100
        feishu_sheet_api.AddRows(sheet_id, add_rows)

    validation_range = "{}!B1:B{}".format(sheet_id, bill_size)
    feishu_sheet_api.AddDataValidation(sheet_id, validation_range, feishu_sheet_api.category_color_dict)
    validation_range = "{}!I1:I{}".format(sheet_id, bill_size)
    feishu_sheet_api.AddDataValidation(sheet_id, validation_range, feishu_sheet_api.alg_color_dict)

    sheet_range = "{}!A1:I{}".format(sheet_id, bill_size)
    feishu_sheet_api.RecordBillItem(sheet_range, bill_item_dict['expense'])

    check_start_row = 1
    if 'income' in bill_item_dict:
        check_end_row = check_start_row + len(bill_item_dict['income']) - 1
        sheet_range = "{}!K{}:S{}".format(sheet_id, check_start_row, check_end_row)
        feishu_sheet_api.RecordBillItem(sheet_range, bill_item_dict['income'])
        check_start_row = check_end_row + 2

    month_detail_sheet_id = sheet_info['月度明细']['sheet_id']
    feishu_sheet_api.UpdateMonthSheetInfo(month_detail_sheet_id, sheet_name, len(bill_item_dict['expense']))

def check_unknown_items(bill_item_list):
    count = 0
    for item in bill_item_list:
        if item.category == ExpenseCategory.UNKNOWN:
            count += 1
    logging.debug("unknown category item size:{}".format(count))

def debug_bill_item_list(prefix, bill_item_list):
    logging.info("-------{} size:{}--------".format(prefix, len(bill_item_list)))
    for bill_item in bill_item_list:
        logging.info(bill_item)

def load_bill_file(config):
    i = 1
    bill_files = []
    while (1):
        section_name = f'bill{i}'
        if not config.has_section(section_name):
            break
        file_name = config.get(section_name, "name")
        bill_type = config.get(section_name, "type")
        bill_owner = config.get(section_name, "owner")

        bill_file = BillFile(file_name, bill_owner, bill_type)
        bill_files.append(bill_file)
        i = i + 1

    return bill_files


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', help='配置文件路径')
    args = parser.parse_args()
    logging.debug("args config_file:{}".format(args.config_file))

    config = configparser.ConfigParser()
    config.read(args.config_file)

    # https://open.feishu.cn/api-explorer/cli_a4d9e0b5c9bd100b
    bill_config = BillConfig(config)

    openai.api_key = bill_config.gpt_config.api_key

    bill_files = load_bill_file(config)
    logging.debug("bill_files:{}".format(len(bill_files)))

    bill_item_list = []

    for bill_file in bill_files:
        bill = None
        logging.debug("bill_file: {} {} {}".format(bill_file.file_name, bill_file.bill_owner, bill_file.bill_type))
        if bill_file.bill_type == "alipay":
            bill = AliPayBill(bill_file)
        elif bill_file.bill_type == "wechat":
            bill = WeChatBill(bill_file)

        item_list = []
        bill.parse_from_file(item_list)

        logging.info("{} {} bill item:{}".format(bill.owner, bill.bill_type, len(item_list)))

        bill_item_list.extend(item_list)

    logging.info("all bill item:{}".format(len(bill_item_list)))

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
    if not ret:
        sys.exit()

    if logger.isEnabledFor(logging.DEBUG):
        check_unknown_items(bill_item_list)
    logging.info("after category bill item:{}".format(len(bill_item_list)))

    # 拆分数据
    income_data = []
    expense_data = []
    other_data = []
    skip_data = []
    unknown_data = []
    gpt_data = []
    regular_data = []
    wet_market_data = []
    for bill_item in bill_item_list:
        if bill_item.bill_type == BillType.INCOME:
            income_data.append(bill_item)
        elif bill_item.bill_type == BillType.OTHER:
            other_data.append(bill_item)
        else:  # EXPENSE
            if bill_item.category == ExpenseCategory.UNKNOWN:
                unknown_data.append(bill_item)
            elif bill_item.classify_alg == ClassifyAlg.GPT:
                gpt_data.append(bill_item)
            elif bill_item.classify_alg == ClassifyAlg.REGULAR:
                regular_data.append(bill_item)
            elif bill_item.classify_alg == ClassifyAlg.WET_MARKET:
                wet_market_data.append(bill_item)
            elif bill_item.category == ExpenseCategory.BUY_VEGETABLES:
                wet_market_data.append(bill_item)
            elif bill_item.category == ExpenseCategory.SKIP:
                skip_data.append(bill_item)
            else:
                if bill_item.amount == 0.0:
                    skip_data.append(bill_item)
                else:
                    expense_data.append(bill_item)

    expense_data.extend(regular_data)
    expense_data.extend(wet_market_data)
    expense_data.extend(gpt_data)
    expense_data.extend(unknown_data)
    expense_data.extend(other_data)
    expense_data.extend(skip_data)
    expense_data.extend(income_data)

    bill_item_dict = {
        "expense": expense_data,
        "income": income_data,
    }

    record_to_feishu(bill_config.feishu_config, bill_item_dict)
