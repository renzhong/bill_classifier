#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from feishu import FeishuSheetAPI, FeishuUnit, timestamp2str
from category import ExpenseCategory, ExtraPayCategory
from category import ClassifyAlg

logger = logging.getLogger(__name__)


# 右侧补充列起始相对偏移：主表 10 列 (offset 0..9) + 1 列空 → offset 11 = L 列
RIGHT_EXTRA_COL_OFFSET = 11
RIGHT_EXTRA_COL_SIZE = 4  # 标签 / 时间 / 金额 / 关联说明
RIGHT_EXTRA_HEADERS = ["类型", "时间", "金额", "关联说明"]


def _right_extra_label(item) -> str:
    """根据 BillItem 的 cross_month_origin 推 label。"""
    origin = getattr(item, 'cross_month_origin', None)
    if origin:
        origin_item_name = origin.get('item_name') or ''
        if '购物金' in origin_item_name:
            return "购物金跨月"
        return "跨月退款"
    return "其它"


def _right_extra_ref(item) -> str:
    """关联说明文字。"""
    origin = getattr(item, 'cross_month_origin', None)
    if not origin:
        return ""
    try:
        dt = timestamp2str(origin['bill_time'])
    except Exception:
        dt = "?"
    payee = origin.get('payee', '')
    amount = origin.get('amount', 0.0) or 0.0
    return f"原支出: {dt} {payee} {amount:.2f}"

class DetailSheet:
    """消费明细页面类，负责处理每月账单明细页面的构建和数据填充"""

    def __init__(self, sheet_token, sheet_id, user_access_token, sheet_name):
        """初始化页面描述信息"""
        self.sheet_token = sheet_token
        self.sheet_id = sheet_id
        self.feishu_api = FeishuSheetAPI(user_access_token, sheet_token)
        self.sheet_name = sheet_name

        # 列偏移量定义
        self.category_col_offset = 1  # 分类列偏移
        self.alg_col_offset = 8  # 分类算法列偏移
        self.extra_pay_col_offset = 9  # 日常/额外支持列偏移
        self.data_col_size = 10  # 数据列总大小

        # 列标题定义（可选，用于后续扩展）
        self.column_titles = [
            "金额",      # 0
            "分类",      # 1
            "收款人(payee)",      # 2
            "账单名称(item_name)",  # 3
            "账单类型",  # 4
            "时间",      # 5
            "来源",      # 6
            "账单人",    # 7
            "分类算法",  # 8
            "日常/额外支持"  # 9
        ]

    def get_sheet_name(self, month_str):
        """获取sheet名称"""
        return self.sheet_name

    def init_sheet(self, bill_size):
        """构建页面：设置枚举值、数据类型、背景色等"""
        header_pos = FeishuUnit('1', 'A')

        # 动态扩展空白行
        if bill_size > 200:
            add_rows = (bill_size // 100 + 1) * 100
            self.feishu_api.AddRows(self.sheet_id, add_rows)

        # 设置表头
        header_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            header_pos.GetCol(),
            header_pos.GetRow(),
            header_pos.GetCol(offset=len(self.column_titles) - 1),
            header_pos.GetRow()
        )
        logger.info("写入表头 range:{}".format(header_range))
        header_values = [self.column_titles]
        self.feishu_api.WriteValues(self.sheet_id, header_range, header_values)

        start_pos = FeishuUnit('2', 'A')

        # 设置分类列为枚举
        validation_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            start_pos.GetCol(offset=self.category_col_offset),
            start_pos.GetRow(),
            start_pos.GetCol(offset=self.category_col_offset),
            start_pos.GetRow(offset=bill_size - 1)
        )
        logger.info("category validation_range:{}".format(validation_range))
        self.feishu_api.AddDataValidation(
            self.sheet_id,
            validation_range,
            [category.value for category in ExpenseCategory]
        )

        # 设置分类算法列为枚举
        validation_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            start_pos.GetCol(offset=self.alg_col_offset),
            start_pos.GetRow(),
            start_pos.GetCol(offset=self.alg_col_offset),
            start_pos.GetRow(offset=bill_size - 1)
        )
        logger.info("alg validation_range:{}".format(validation_range))
        self.feishu_api.AddDataValidation(
            self.sheet_id,
            validation_range,
            [alg.value for alg in ClassifyAlg],
            color_overrides={ClassifyAlg.UNKNOWN.value: "#FCFCFC"},
        )

        # 设置日常/额外支持列为枚举
        validation_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            start_pos.GetCol(offset=self.extra_pay_col_offset),
            start_pos.GetRow(),
            start_pos.GetCol(offset=self.extra_pay_col_offset),
            start_pos.GetRow(offset=bill_size - 1)
        )
        logger.info("extra_pay validation_range:{}".format(validation_range))
        self.feishu_api.AddDataValidation(
            self.sheet_id,
            validation_range,
            [category.value for category in ExtraPayCategory]
        )

    def fill_data(self, bill_item_list, start_pos=None):
        """填充账单数据到页面"""
        if start_pos is None:
            start_pos = FeishuUnit('2', 'A')

        bill_size = len(bill_item_list)
        sheet_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            start_pos.GetCol(),
            start_pos.GetRow(),
            start_pos.GetCol(offset=self.data_col_size - 1),  # -1: offset 比长度小 1
            start_pos.GetRow(offset=bill_size - 1)
        )
        logger.info("bill_item sheet_range:{}".format(sheet_range))

        return self.feishu_api.RecordBillItem(sheet_range, bill_item_list)

    def fill_right_extra(self, items):
        """右侧补充列：4 列 [类型 / 时间 / 金额 / 关联说明]。

        items 中应都是带 cross_month_origin 标记的条目（策略 3 标记的跨月退款等）。
        起始列 = L（主表 10 列 + 间隔 1 列）。
        """
        if not items:
            return True

        bill_size = len(items)
        # 表头写在第 1 行
        header_pos = FeishuUnit('1', 'A')
        header_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            header_pos.GetCol(offset=RIGHT_EXTRA_COL_OFFSET), header_pos.GetRow(),
            header_pos.GetCol(offset=RIGHT_EXTRA_COL_OFFSET + RIGHT_EXTRA_COL_SIZE - 1),
            header_pos.GetRow(),
        )
        self.feishu_api.WriteValues(self.sheet_id, header_range, [list(RIGHT_EXTRA_HEADERS)])

        # 数据从第 2 行开始
        start_pos = FeishuUnit('2', 'A')
        sheet_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            start_pos.GetCol(offset=RIGHT_EXTRA_COL_OFFSET), start_pos.GetRow(),
            start_pos.GetCol(offset=RIGHT_EXTRA_COL_OFFSET + RIGHT_EXTRA_COL_SIZE - 1),
            start_pos.GetRow(offset=bill_size - 1),
        )
        logger.info("right_extra sheet_range:{} size:{}".format(sheet_range, bill_size))

        values = []
        for it in items:
            try:
                dt = timestamp2str(it.bill_time)
            except Exception:
                dt = "?"
            values.append([
                _right_extra_label(it),
                dt,
                it.amount,
                _right_extra_ref(it),
            ])

        return self.feishu_api.WriteValues(self.sheet_id, sheet_range, values)
