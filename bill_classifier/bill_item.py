#!/usr/bin/env python
# -*- coding: utf-8 -*-

from category import BillType, ClassifyAlg, ExpenseCategory, Lifecycle
from util import timestamp2str


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
        # 业务分类（None 表示未分类；展示用 category_display() 派生字符串）
        self.category = None
        # 哪个分类 step 完成（None 表示未分类）
        self.classify_alg = None
        # 生命周期：各 step 根据 lifecycle 判断"是否处理过"
        self.lifecycle = Lifecycle.UNPROCESSED
        self.skip_reason = None             # SkipReason，仅 lifecycle == SKIPPED 时填
        # 策略上下文字段（按需由各 step 写入，默认 None 对其它 step 透明）
        self.group_id = None                # 通用分组 ID，输出时按 group_id 聚合并按 bill_time 排序
        self.taobao_balance_extra = None    # 策略 2：购物金合并后追加的说明文本
        self.cross_month_origin = None      # 策略 3：跨月退款关联到的原支出条目 dict
        # 合并标记（由 merge_refund / taobao_balance_merge 设置）
        self.is_merged = False              # 是否由合并 step 产生
        self.merged_from = []               # 合并前的子条目快照，按 bill_time 升序

    def category_display(self) -> str:
        """飞书表格'分类'列展示值（按 bill_type / lifecycle 派生）。"""
        if self.bill_type == BillType.INCOME:
            return ExpenseCategory.INCOME.to_str()
        if self.lifecycle == Lifecycle.CLASSIFIED and self.category is not None:
            return self.category.to_str()
        if self.lifecycle == Lifecycle.CROSS_MONTH_REFUND:
            return ExpenseCategory.REFUND.to_str()
        if self.lifecycle == Lifecycle.SKIPPED:
            return ExpenseCategory.SKIP.to_str()
        return ExpenseCategory.UNKNOWN.to_str()  # UNPROCESSED

    def classify_alg_display(self) -> str:
        return (self.classify_alg or ClassifyAlg.UNKNOWN).to_str()

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
            self.category_display()
        )
