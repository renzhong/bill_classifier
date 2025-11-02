#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from feishu import FeishuSheetAPI, FeishuUnit
from category import ExpenseCategory, ExtraPayCategory
from bill_item import ClassifyAlg

logger = logging.getLogger(__name__)

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
            [alg.value for alg in ClassifyAlg]
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

    def fill_income_data(self, bill_item_list):
        """填充收入数据到页面（在支出数据右侧，间隔一列）"""
        start_pos = FeishuUnit('2', 'A')
        # +2: 两块数据要间隔 1 列
        income_pos = FeishuUnit(start_pos.GetRow(), start_pos.GetCol(offset=self.data_col_size - 1 + 2))

        bill_size = len(bill_item_list)
        logger.info("income item 数量: {}".format(bill_size))

        sheet_range = "{}!{}{}:{}{}".format(
            self.sheet_id,
            income_pos.GetCol(),
            income_pos.GetRow(),
            income_pos.GetCol(offset=self.data_col_size - 1),
            income_pos.GetRow(offset=bill_size - 1)
        )
        logger.info("income_item sheet_range:{}".format(sheet_range))

        return self.feishu_api.RecordBillItem(sheet_range, bill_item_list)

