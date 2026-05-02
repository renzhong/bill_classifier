#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum


class BillType(Enum):
    INCOME = "收入"
    EXPENSE = "支出"
    OTHER = "不计支出"

    def to_str(self) -> str:
        return self.value


class ClassifyAlg(Enum):
    MATCH = "完全匹配"
    REGULAR = "模糊匹配"
    WET_MARKET = "菜场模式"
    GPT = "GPT模式"
    FOLLOW = "跟随账单"           # neighbor_inference 命中时打的标
    MERGED = "已合并"              # merge_refund / taobao_balance_merge 合并产生且金额 > 0；
                                   #   是中间态，会被后续分类 step（MATCH/REGULAR/GPT）覆盖
    FULL_REFUND = "完全退款"       # 合并后金额 < 0.01，lifecycle=SKIPPED 的终态
    COMPANY_SUBSIDY = "公司补贴"   # meican_filter 识别为工作日餐补时打的标
    UNKNOWN = "无法识别"           # 仅展示用，BillItem.classify_alg 仍以 None 表示未分类

    def to_str(self) -> str:
        return self.value


class ExpenseCategory(Enum):
    """业务分类 + B 列状态展示值。

    14 个业务分类由分类 step 写入 BillItem.category。
    4 个状态展示值（UNKNOWN/SKIP/REFUND/INCOME）仅用于：
        - 飞书 B 列下拉枚举（detail_sheet 动态生成）
        - BillItem.category_display() 按 lifecycle / bill_type 派生展示
    不会被任何 step 写入 BillItem.category（保留 phase5 的"状态走 lifecycle"原则）。
    """
    # 业务分类
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
    # 状态展示值
    UNKNOWN = "unknown"
    SKIP = "skip"
    REFUND = "退款"
    INCOME = "收入"

    def to_str(self) -> str:
        return self.value


_STATE_CATEGORY_VALUES = frozenset({
    ExpenseCategory.UNKNOWN.value,
    ExpenseCategory.SKIP.value,
    ExpenseCategory.REFUND.value,
    ExpenseCategory.INCOME.value,
})


def is_state_category_value(value: str) -> bool:
    """判断飞书表里的某行 category 字段是否是状态展示值（不应被 step 当业务分类使用）。"""
    return value in _STATE_CATEGORY_VALUES

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
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.info(list(ExpenseCategory))
