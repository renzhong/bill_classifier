#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
import configparser
import argparse

from feishu import FeishuSheetAPI
from feishu_auth import FeishuAuthError, get_valid_user_access_token
from category import BillType, ClassifyAlg, Lifecycle
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
        if item.lifecycle == Lifecycle.UNPROCESSED:
            count += 1
    logging.debug("unprocessed item size:{}".format(count))

def debug_bill_item_list(prefix, bill_item_list):
    logging.info("-------{} size:{}--------".format(prefix, len(bill_item_list)))
    for bill_item in bill_item_list:
        logging.info(bill_item)

def _reorder_with_groups(items):
    """同 group_id 的 item 按 bill_time 升序紧邻输出。

    遍历输入顺序，遇到 group_id 非空的 item，立刻把同组所有成员按 bill_time
    依次输出（去重）。组内排序基于 bill_time，避免成员被分桶（不同 classify_alg）
    打散后顺序错乱。
    """
    by_group = {}
    for it in items:
        g = getattr(it, 'group_id', None)
        if g:
            by_group.setdefault(g, []).append(it)
    for members in by_group.values():
        members.sort(key=lambda x: x.bill_time)

    out = []
    seen_ids = set()
    for it in items:
        if id(it) in seen_ids:
            continue
        g = getattr(it, 'group_id', None)
        if g:
            for member in by_group.get(g, []):
                if id(member) not in seen_ids:
                    out.append(member)
                    seen_ids.add(id(member))
        else:
            out.append(it)
            seen_ids.add(id(it))
    return out


# CLASSIFIED 类的展示顺序（按 classify_alg 二级分组）
_CLASSIFIED_ALG_ORDER = (
    ClassifyAlg.MATCH,
    ClassifyAlg.REGULAR,
    ClassifyAlg.WET_MARKET,
    ClassifyAlg.FOLLOW,
    ClassifyAlg.GPT,
)


def split_for_output(bill_item_list):
    """按 lifecycle 一级 + classify_alg 二级分流，返回 (主表 list, 收入 list, 右侧提醒 list)。

    主表展示顺序：
        CLASSIFIED 按 classify_alg：MATCH → REGULAR → WET_MARKET → FOLLOW → GPT
        → UNPROCESSED（等人工标）
        → CROSS_MONTH_REFUND（跨月退款，左侧主表保留 + 右侧也展示一份）
        → SKIPPED（被各种 reason 跳过的）
        → INCOME 类（最底部，按 bill_type=INCOME 单独分组）

    最后对主表应用 group_id 紧邻重排（同组按 bill_time 升序聚合）。
    右侧提醒：所有挂了 cross_month_origin 的条目（这些条目同时仍在左侧主表）。
    """
    classified_buckets = {alg: [] for alg in _CLASSIFIED_ALG_ORDER}
    unprocessed_data = []
    cross_month_data = []
    skipped_data = []
    income_data = []

    for it in bill_item_list:
        # bill_type=INCOME 的 item 已被 non_expense_skip 标 SKIPPED；
        # 但视觉上分组为"收入"放底部，所以这里优先按 bill_type 判断。
        if it.bill_type == BillType.INCOME:
            income_data.append(it)
            continue
        # SKIPPED / CROSS_MONTH_REFUND 是终态展示分组，先于按 classify_alg 分桶。
        # （注意：skip_keywords 把 classify_alg 标 MATCH 但 lifecycle=SKIPPED，
        #   必须先按 lifecycle 拦截，否则会被错误归到 MATCH bucket。）
        if it.lifecycle == Lifecycle.SKIPPED:
            skipped_data.append(it)
            continue
        if it.lifecycle == Lifecycle.CROSS_MONTH_REFUND:
            cross_month_data.append(it)
            continue
        bucket = classified_buckets.get(it.classify_alg)
        if bucket is not None:
            bucket.append(it)
        else:
            # 包括 classify_alg=None（真未分类）以及 MERGED 等中间态
            unprocessed_data.append(it)

    main_data = []
    for alg in _CLASSIFIED_ALG_ORDER:
        main_data.extend(classified_buckets[alg])
    main_data.extend(unprocessed_data)
    main_data.extend(cross_month_data)
    main_data.extend(skipped_data)
    main_data.extend(income_data)

    main_data = _reorder_with_groups(main_data)

    right_extra = [it for it in bill_item_list if getattr(it, 'cross_month_origin', None)]
    return main_data, income_data, right_extra


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

    # 拆分数据。原则：
    #   左侧（主表）= 所有账单条目（按 lifecycle 一级分流 + CLASSIFIED 内按
    #     classify_alg 二级分组）。只有在 merge_payee / merge_refund /
    #     taobao_balance_merge 中"被合并掉"的条目才会从 list 里移除，
    #     单条账单不因为"也要在右侧出现"而被排除。
    #   右侧（补充列）= 独立的提醒块，从左侧条目额外摘出展示，不影响左侧完整性。
    main_data, income_data, right_extra_data = split_for_output(bill_item_list)

    bill_item_dict = {
        "expense": main_data,
        "income": income_data,
        "right_extra": right_extra_data,
    }

    record_to_feishu(bill_config.feishu_config, bill_item_dict)
