#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os  # noqa
import logging
import datetime
import sys
import configparser
import argparse

from feishu import FeishuSheetAPI
from feishu_auth import FeishuAuthError, get_valid_user_access_token
from category import ExpenseCategory
from bill_item import BillType, ClassifyAlg
from bill import AliPayBill, WeChatBill
from bill_config import BillConfig
from bill_file import BillFile
from strategy import bill_strategy
from util import GetMonth
from detail_sheet import DetailSheet
from summary_sheet import SummarySheet

logger = logging.getLogger(__name__)

def record_to_feishu(feishu_config, bill_item_dict):
    user_access_token = feishu_config.user_access_token
    bill_sheet_token = feishu_config.bill_sheet_token

    feishu_sheet_api = FeishuSheetAPI(user_access_token, bill_sheet_token)
    sheet_info = feishu_sheet_api.GetSheetInfo()

    # 创建或获取消费明细页面
    month_str = GetMonth()
    sheet_name = "账单明细 " + month_str

    sheet_id = ''
    if sheet_name not in sheet_info:
        ret, sheet_id = feishu_sheet_api.AddNewSheet(sheet_name, len(sheet_info))
        if not ret:
            return False
    else:
        sheet_id = sheet_info[sheet_name]['sheet_id']

    # 初始化页面类
    detail_sheet = DetailSheet(bill_sheet_token, sheet_id, user_access_token, sheet_name)
    summary_sheet = SummarySheet(bill_sheet_token, sheet_id, user_access_token)
    
    # 处理支出数据
    bill_size = 0
    if "expense" in bill_item_dict:
        bill_size = len(bill_item_dict['expense'])
    logging.info("expense item 数量: {}".format(bill_size))

    # 构建明细页面（设置枚举值等）
    if bill_size > 0:
        detail_sheet.init_sheet(bill_size)

        # 填充支出数据
        detail_sheet.fill_data(bill_item_dict['expense'])

    # 右侧补充列（策略 3 cross_month_unified 标记的跨月退款 / 购物金跨月退）
    right_extra = bill_item_dict.get('right_extra') or []
    if right_extra:
        logging.info("right_extra item 数量: {}".format(len(right_extra)))
        detail_sheet.fill_right_extra(right_extra)

    # 更新汇总页面
    expense_size = len(bill_item_dict.get('expense', []))
    month_detail_sheet_id = sheet_info["月度明细"]['sheet_id']
    summary_sheet.fill_data(
        feishu_sheet_api,
        month_detail_sheet_id,
        sheet_name,
        expense_size
    )

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

def _reorder_with_neighbor_groups(items):
    """策略 4 输出方案 A：同 neighbor_group 的 item 紧邻输出。

    遍历输入顺序，遇到 neighbor_group 非空的 item，紧跟着把同组其他成员
    一起输出（去重）。锚点的 classify_alg 仍保留 MATCH，只调整顺序。
    """
    by_group = {}
    for it in items:
        g = getattr(it, 'neighbor_group', None)
        if g:
            by_group.setdefault(g, []).append(it)

    out = []
    seen_ids = set()
    for it in items:
        if id(it) in seen_ids:
            continue
        out.append(it)
        seen_ids.add(id(it))
        g = getattr(it, 'neighbor_group', None)
        if g:
            for other in by_group.get(g, []):
                if id(other) not in seen_ids:
                    out.append(other)
                    seen_ids.add(id(other))
    return out


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
    try:
        bill_config.feishu_config.user_access_token = get_valid_user_access_token(config, args.config_file)
    except FeishuAuthError as err:
        logging.error(str(err))
        sys.exit(1)

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

    ret, bill_item_list = bill_strategy(bill_item_list, bill_config)
    if not ret:
        sys.exit()

    logging.info("标记类型后 item:{}".format(len(bill_item_list)))

    # 拆分数据
    income_data = []
    expense_data = []
    other_data = []
    skip_data = []
    unknown_data = []
    gpt_data = []
    regular_data = []
    wet_market_data = []
    right_extra_data = []
    for bill_item in bill_item_list:
        # 策略 3 标记的跨月退款等：display_section='right_extra' 优先分流到右侧列
        if getattr(bill_item, 'display_section', None) == 'right_extra':
            right_extra_data.append(bill_item)
            continue
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
    # 策略 4：同 neighbor_group 的 item 紧邻输出（方案 A）
    expense_data = _reorder_with_neighbor_groups(expense_data)

    bill_item_dict = {
        "expense": expense_data,
        "income": income_data,
        "right_extra": right_extra_data,
    }

    record_to_feishu(bill_config.feishu_config, bill_item_dict)
