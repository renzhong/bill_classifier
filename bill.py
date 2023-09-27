#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum
from category import ExpenseCategory
from util import timestamp2str

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
    UNKNOWN = "无法识别"

    def to_str(self) -> str:
        return self.value

class BillItem:
    amount: float
    bill_time: float
    def __init__(self, amount, payee, item_name, bill_type, order_id, bill_time, bill_source="unknown", owner=""):
        self.amount = amount            # 金额
        self.payee = payee              # 交易对象
        self.item_name = item_name      # 商品名称
        self.bill_type = bill_type      # 收支类型（收入/支出/其他）
        self.order_id = order_id        # 订单号
        self.bill_time = bill_time      # 订单发生时间
        self.bill_source = bill_source  # 订单来源（alipay/wechat）
        self.owner = owner              # 账单人（zrz/cwx）
        self.category = ExpenseCategory.UNKNOWN # 分类
        self.classify_alg = ClassifyAlg.UNKNOWN # 识别模式

    def __str__(self):
        return """
Amount: {}
    Payee: {}
    Item Name: {}
    Bill Type: {}
    order_id: {}
    bill_time: {}
    bill_source: {}
    owner: {}
    category: {}""".format(
            self.amount, self.payee, self.item_name, self.bill_type.name,
            self.order_id, timestamp2str(self.bill_time), self.bill_source, self.owner,
            self.category.to_str()
        )
