#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum

class ExpenseCategory(Enum):
    """业务分类（仅业务含义，不含状态值）。

    "未分类 / 跳过 / 退款 / 收入"等状态语义由 Lifecycle 表达；
    展示层通过 BillItem.category_display() 派生表格字符串。
    """
    WATER_ELECTRICITY_PROPERTY = '水电物业'
    CATERING = '餐饮'
    BUY_VEGETABLES = '买菜'
    TRANSPORTATION = '交通'
    DAILY_EXPENSES = '日常开支'
    CLOTHING_SHOES_HATS = '服装鞋帽'
    SKINCARE_PRODUCTS = '护肤品'
    SOCIAL_INTERCOURSE = '人情往来'
    LEISURE_ENTERTAINMENT = '休闲娱乐'
    COMPANY = '公司'
    HOME_CONSTRUCTION = '家庭建设'
    MEDICAL = '医疗'
    VEHICLE_MAINTENANCE = '养车'
    CHILD = "育儿"

    def to_str(self) -> str:
        return self.value

class ExtraPayCategory(Enum):
    DAILY = '日常开支'
    EXTRA = '额外开支'

    def to_str(self) -> str:
        return self.value


class Lifecycle(Enum):
    """BillItem 在 pipeline 中的处理状态。

    每个 step 处理完一条 item 后，应该把 lifecycle 推进到对应状态。
    后续 step 通过 lifecycle != UNPROCESSED 判断"是否已处理"。
    """
    UNPROCESSED = "未处理"           # 默认初始状态
    SKIPPED = "跳过"                # 不计入开销，具体原因看 skip_reason
    CROSS_MONTH_REFUND = "跨月退款"  # 关联到上月原支出，左侧主表保留 + 右侧提醒
    CLASSIFIED = "已分类"            # 已被分类为某 ExpenseCategory，看 category / classify_alg

    def to_str(self) -> str:
        return self.value


class SkipReason(Enum):
    """lifecycle == SKIPPED 时记录的原因，便于审计与未来调整。"""
    FILTER = "filter"                # meican_filter：工作日餐补
    BLACKLIST = "blacklist"          # skip_keywords：item_name 黑名单
    NON_EXPENSE = "non_expense"      # bill_type ∈ {INCOME, OTHER} 不计入主表合计
    ZERO_AMOUNT = "zero_amount"      # merge_refund / taobao_balance_merge 净额为 0
    REFUND_NO_ORIG = "refund_no_orig"  # merge_refund 无 order_id（已知 bug，保持原行为）

    def to_str(self) -> str:
        return self.value


expense_category_mapping = {category.value: category for category in ExpenseCategory}

class CategoryInfo:
    item_category_dict = {}
    payee_category_dict = {}
    item_category_regular_dict = {}
    payee_category_regular_dict = {}

    def __init__(self):
        pass

if __name__ == "__main__":
    print(ExpenseCategory.keys())
