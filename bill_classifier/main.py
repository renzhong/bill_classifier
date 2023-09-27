#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os  # noqa
import logging
import datetime
import sys
import configparser
import argparse
import openai

from feishu import FeishuSheetAPI
from category import ExpenseCategory
from bill_item import BillType, ClassifyAlg
from bill import AliPayBill, WeChatBill
from bill_config import BillConfig
from bill_file import BillFile
from strategy import bill_strategy

logger = logging.getLogger(__name__)

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

    bill_config = BillConfig(config)

    openai.api_key = bill_config.gpt_config.api_key

    bill_files = load_bill_file(config)
    logging.debug("bill_files:{}".format(len(bill_files)))

    bill_item_list = []

    for bill_file in bill_files:
        bill = None
        if bill_file.bill_type == "alipay":
            bill = AliPayBill(bill_file)
        elif bill_file.bill_type == "wechat":
            bill = WeChatBill(bill_file)

        item_list = []
        bill.parse_from_file(item_list)

        logging.info("{} {} bill item:{}".format(bill.owner, bill.bill_type, len(item_list)))

        bill_item_list.extend(item_list)

    logging.info("all bill item:{}".format(len(bill_item_list)))

    ret = bill_strategy(bill_item_list, bill_config)
    if not ret:
        sys.exit()

    # # 分析数据
    # #   1. 合并退款
    # bill_item_list = merge_refund_items(bill_item_list)
    # logging.info("after merge refund bill item:{}".format(len(bill_item_list)))

    # #   2. 合并余额宝收益
    # bill_item_list = merge_balance_items(bill_item_list)
    # logging.info("after balance bill item:{}".format(len(bill_item_list)))

    # bill_item_list = sorted(bill_item_list, key=lambda item: item.bill_time)

    # #   2. 划分到某个大类
    # ret = categorize_items(bill_item_list, bill_config)
    # if not ret:
    #     sys.exit()

    # if logger.isEnabledFor(logging.DEBUG):
    #     check_unknown_items(bill_item_list)
    # logging.info("after category bill item:{}".format(len(bill_item_list)))

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
