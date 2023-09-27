#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum

class ExpenseCategory(Enum):
    UNKNOWN = 'unknown'
    WATER_ELECTRICITY_PROPERTY = '水电物业'  # 水电物业
    CATERING = '餐饮'  # 餐饮
    BUY_VEGETABLES = '买菜'  # 买菜
    TRANSPORTATION = '交通'  # 交通
    DAILY_EXPENSES = '日常开支'  # 日常开支
    CLOTHING_SHOES_HATS = '服装鞋帽'  # 服装鞋帽
    SKINCARE_PRODUCTS = '护肤品'  # 护肤品
    SOCIAL_INTERCOURSE = '人情往来'  # 人情往来
    LEISURE_ENTERTAINMENT = '休闲娱乐'  # 休闲娱乐
    MISCELLANEOUS = '杂项'  # 杂项
    HOME_CONSTRUCTION = '家庭建设'  # 家庭建设
    MEDICAL = '医疗'  # 医疗
    LARGE_ITEM = '大件'  # 大件
    VEHICLE_MAINTENANCE = '养车'  # 养车
    SKIP = "skip"  # skip
    INCOME = "收入"  # 收入

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
