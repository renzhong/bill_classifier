#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from feishu import FeishuSheetAPI, FeishuUnit
from category import ExpenseCategory
from util import GetMonthInt

logger = logging.getLogger(__name__)

class SummarySheet:
    """汇总页面类，负责处理按月汇总的账单数据页面"""

    def __init__(self, sheet_token, sheet_id, user_access_token):
        """初始化页面描述信息"""
        self.sheet_name = "月度明细"
        self.start_line = 2  # 数据起始行（第1行是标题）
        self.sheet_token = sheet_token
        self.sheet_id = sheet_id
        self.feishu_api = FeishuSheetAPI(user_access_token, sheet_token)
        self.expense_category_size = len(ExpenseCategory)
        self.extra_pay_line = self.expense_category_size + 2 # 第一行为空 + category 的行数
        self.summary_line = self.expense_category_size + 3 # 第一行为空 + category 的行数 + 额外花费行

    def get_sheet_name(self):
        """获取sheet名称"""
        return self.sheet_name

    def get_line_titles(self, feishu_sheet_api, month_sheet_id):
        """获取汇总页面的行标题列表"""
        return feishu_sheet_api.GetMonthSheetInfoLineTitle(month_sheet_id)

    def validate_categories(self, line_title):
        """验证所有分类项是否存在于行标题中"""
        missing_categories = []
        for category in ExpenseCategory:
            if category.value not in line_title:
                missing_categories.append(category.value)
                logger.error("月度表中缺失分类项:{}".format(category.value))

        return len(missing_categories) == 0

    def init_sheet(self):
        """初始化汇总表：表头、第一列、背景色"""
        logger.info("初始化汇总表: {}".format(self.sheet_id))

        # 确保有足够的列（至少13列：A列+12个月）
        self.feishu_api.AddCols(self.sheet_id, 13)

        # 1. 初始化表头：第一列空，第二列是"一月"，第三列是"二月"，依次递增，最后是"十二月"
        month_names = ["", "一月", "二月", "三月", "四月", "五月", "六月",
                      "七月", "八月", "九月", "十月", "十一月", "十二月"]
        header_range = "{}!A1:M1".format(self.sheet_id)
        header_values = [month_names]
        logger.info("写入表头 range:{}".format(header_range))
        self.feishu_api.WriteValues(self.sheet_id, header_range, header_values)

        # 2. 写入第一列
        start_pos = FeishuUnit('1', 'A')
        validation_range = "{}!A{}:A{}".format(self.sheet_id,
                                start_pos.GetRow(offset = 1), start_pos.GetRow(offset = self.expense_category_size))
        print(f"category range:{validation_range}")
        self.feishu_api.AddDataValidation(self.sheet_id, validation_range, [category.value for category in ExpenseCategory])

        first_col_range = "{}!A{}:A{}".format(self.sheet_id,
                                start_pos.GetRow(offset = 1), start_pos.GetRow(offset = self.expense_category_size))
        first_col_data = [[category.value] for category in ExpenseCategory]
        self.feishu_api.WriteValues(self.sheet_id, first_col_range, first_col_data)
        print(f"category value:{first_col_range}")

        extra_pay_col_range = "{}!A{}:A{}".format(self.sheet_id,
                                start_pos.GetRow(offset = self.extra_pay_line - 1), start_pos.GetRow(offset = self.extra_pay_line - 1))
        extra_pay_col_data = [["额外开支"]]
        self.feishu_api.WriteValues(self.sheet_id, extra_pay_col_range, extra_pay_col_data)
        print(f"extra pay range:{extra_pay_col_range}")

        summary_col_range = "{}!A{}:A{}".format(self.sheet_id,
                                start_pos.GetRow(offset = self.summary_line - 1), start_pos.GetRow(offset = self.summary_line - 1))
        summary_col_data = [["合计"]]
        self.feishu_api.WriteValues(self.sheet_id, summary_col_range, summary_col_data)
        print(f"summary range:{summary_col_range}")

        # 3. 设置每行的背景色：白色和#D5F6F2交替
        # 从第2行开始设置（第1行是表头，不需要设置）
        header_color = "#DEE0E3"
        white_color = "#FFFFFF"
        alt_color = "#D5F6F2"

        # 为每一行设置背景色（从A列到M列）
        ranges_white = []
        ranges_alt = []
        background_start = int(start_pos.GetRow(offset = 1))
        background_end = int(start_pos.GetRow(offset = self.summary_line - 1))
        for row in range(background_start, background_end + 1):
            row_range = "{}!A{}:T{}".format(self.sheet_id, row, row)
            # 偶数行用白色，奇数行用#D5F6F2（从第2行开始，第2行索引为0）
            if row % 2 == 0:
                ranges_white.append(row_range)
            else:
                ranges_alt.append(row_range)

        # 设置白色背景
        self.feishu_api.SetBackgroundColor(self.sheet_id, f"{self.sheet_id}!A1:T1", header_color)
        if ranges_white:
            logger.info("设置白色背景行数: {}".format(len(ranges_white)))
            self.feishu_api.SetBackgroundColor(self.sheet_id, ranges_white, white_color)
        # 设置交替背景色
        if ranges_alt:
            logger.info("设置交替背景色行数: {}".format(len(ranges_alt)))
            self.feishu_api.SetBackgroundColor(self.sheet_id, ranges_alt, alt_color)

        # 对 一月到12月， 第二行到 first_col_end_row 行的这个区域，设置 style 为
        style_info = {
            "formatter": "#,##0"
        }
        value_range = "{}!B2:M{}".format(self.sheet_id, self.summary_line - 1)
        self.feishu_api.UpdateStyleInfo(value_range, style_info)

    def fill_data(self, feishu_sheet_api, month_sheet_id, detail_sheet_name, row_size):
        """填充汇总数据：使用公式计算各分类的汇总"""
        column = self._get_current_month_column()
        line_title = self.get_line_titles(feishu_sheet_api, month_sheet_id)

        # 验证分类完整性
        self.validate_categories(line_title)

        # 更新数据（使用公式）
        return feishu_sheet_api.UpdateMonthSheetData(
            month_sheet_id,
            detail_sheet_name,
            column,
            row_size,
            line_title
        )

    def _get_current_month_column(self):
        """获取当前月份对应的列字母"""
        return chr(ord('A') + GetMonthInt())

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # 注意：实际使用时需要传入真实的 sheet_id 和 feishu_api
    doc_id = "SOl6wAbL9iLFE0kvPgJcD3aHndg"
    sheet_id = "NPJSfF"
    user_token = "u-f0vmJQGFl6ErGYeo9.xK0d4g4apM40gVNo0001CG2bM8"

    summary_sheet = SummarySheet(doc_id, sheet_id, user_token)
    summary_sheet.init_sheet()
    # summary_sheet.init_sheet()
    print("SummarySheet 类已创建，需要在 main.py 中使用")
