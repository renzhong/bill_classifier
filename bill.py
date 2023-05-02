#!/usr/bin/env python
# -*- coding: utf-8 -*-

import csv
import re
import codecs
import os
import chardet
import pandas as pd
from openpyxl import load_workbook
from datetime import datetime
import time

from typing import List

from enum import Enum

BUY_VEGETABLES_TIME_RANGE = 3600

def str2timestamp(time_str, time_format):
    if len(time_str) == 0:
        return time.time()

    dt_obj = datetime.strptime(time_str, time_format)
    return dt_obj.timestamp()

def timestamp2str(t):
    dt_object = datetime.fromtimestamp(t)
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")

class BillType(Enum):
    INCOME = "收入"
    EXPENSE = "支出"
    OTHER = "不计支出"

    def to_str(self) -> str:
        return self.value

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
    SKIP = "skip" # skip

    def to_str(self) -> str:
        return self.value

item_category_dict = {
    "便利蜂购物": ExpenseCategory.CATERING,
    "手机充值": ExpenseCategory.WATER_ELECTRICITY_PROPERTY,
    "余额宝-自动转入": ExpenseCategory.SKIP,
    "转账备注:微信转账": ExpenseCategory.SKIP,
}

payee_category_dict = {
    "北京轨道交通路网管理有限公司": ExpenseCategory.TRANSPORTATION,
    "柒一拾壹（北京）有限公司": ExpenseCategory.CATERING,
    "老牛海鲜大世界店西23号": ExpenseCategory.BUY_VEGETABLES,
    "水果店": ExpenseCategory.BUY_VEGETABLES,
    "保定手擀面": ExpenseCategory.BUY_VEGETABLES,
    "春意盎然蔬菜店": ExpenseCategory.BUY_VEGETABLES,
    "亿口豆腐": ExpenseCategory.BUY_VEGETABLES,
    "五肉联冷鲜肉": ExpenseCategory.BUY_VEGETABLES,
    "App Store & Apple Music": ExpenseCategory.WATER_ELECTRICITY_PROPERTY,
    "抖音生活服务商家": ExpenseCategory.CATERING,
    "门店名称改为晋南面馆": ExpenseCategory.CATERING,
    "燕龙水务": ExpenseCategory.WATER_ELECTRICITY_PROPERTY,
    "水平有限": ExpenseCategory.CATERING,
    "国网北京市电力公司": ExpenseCategory.WATER_ELECTRICITY_PROPERTY,
    "肉卷也疯狂": ExpenseCategory.CATERING,
    "滴滴出行": ExpenseCategory.TRANSPORTATION,
    "嘀嗒出行": ExpenseCategory.TRANSPORTATION,
    "好功夫盲人按摩": ExpenseCategory.LEISURE_ENTERTAINMENT,
    "云洗驿站": ExpenseCategory.VEHICLE_MAINTENANCE,
    "北京春雨天下软件有限公司": ExpenseCategory.MEDICAL,
    "叮咚买菜": ExpenseCategory.BUY_VEGETABLES,
    "iCloud 由云上贵州运营": ExpenseCategory.WATER_ELECTRICITY_PROPERTY
}

payee_category_regular_dict = {
    "面馆": ExpenseCategory.CATERING,
    "麻辣烫": ExpenseCategory.CATERING,
    "医院": ExpenseCategory.MEDICAL,
    "生鲜": ExpenseCategory.BUY_VEGETABLES,
    "星巴克": ExpenseCategory.CATERING,
    "麦当劳": ExpenseCategory.CATERING,
    "达美乐": ExpenseCategory.CATERING,
    "中石化": ExpenseCategory.TRANSPORTATION,
    "廖记": ExpenseCategory.CATERING,
    "养车": ExpenseCategory.VEHICLE_MAINTENANCE,
    "宜家": ExpenseCategory.HOME_CONSTRUCTION,
    "元气寿司": ExpenseCategory.CATERING,
    "UNIQLO": ExpenseCategory.CLOTHING_SHOES_HATS,
    "涿州中煤华谊汽车": ExpenseCategory.VEHICLE_MAINTENANCE,
    "螺蛳粉": ExpenseCategory.CATERING,
    "停车场": ExpenseCategory.TRANSPORTATION
}

item_category_regular_dict = {
    "停车": ExpenseCategory.TRANSPORTATION,
    "外卖订单": ExpenseCategory.CATERING,
    "药": ExpenseCategory.MEDICAL,
    "牙膏": ExpenseCategory.DAILY_EXPENSES,
    "纸巾": ExpenseCategory.DAILY_EXPENSES,
    "阿玛尼": ExpenseCategory.SKINCARE_PRODUCTS,
    "花呗自动还款": ExpenseCategory.SKIP,
    "饿了么超级吃货卡": ExpenseCategory.CATERING

}

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
        self.category = ExpenseCategory.UNKNOWN

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

class BaseBill:
    def __init__(self, file_path):
        self.file_path = file_path

    def parse_from_file(self):
        pass

def is_chinese_equal(s1: str, s2: str) -> bool:
    """判断两个中文字符串是否相等，忽略空格"""
    return s1.strip().encode('utf-8') == s2.strip().encode('utf-8')

class AliPayBill(BaseBill):
    def __init__(self, file_path, owner, bill_time_format):
        self.file_path = file_path
        self.owner = owner
        self.bill_time_format = bill_time_format
    
    def parse_from_file(self, bill_item_list):
        # 使用chardet检测文件的编码
        with open(self.file_path, 'rb') as f:
            result = chardet.detect(f.read())
            file_encoding = result['encoding']

        # 使用csv模块读取CSV文件，并自动根据文件编码进行解码
        with codecs.open(self.file_path, 'r', encoding=file_encoding) as f:
            reader = csv.reader(f)

            # 初始化标志变量
            print_flag = False

            # 循环读取每一行并打印指定列
            for row in reader:
                row = [col.strip() for col in row]
                if row[0].startswith('------'):
                    # 如果读到了第一个"------"行，将标志变量设置为True
                    if not print_flag:
                        print_flag = True
                    # 如果读到了第二个"------"行，将标志变量设置为False，并停止打印
                    else:
                        print_flag = False
                        break
                else:
                    # 如果标志变量为True，打印当前行
                    if print_flag:
                        if is_chinese_equal(row[0], "交易号"):
                            continue
                        amount = row[9]
                        payee = row[7]
                        item_name = row[8]
                        bill_type_name = row[10]
                        order_id = row[1]
                        bill_time = str2timestamp(row[3], self.bill_time_format)
                        if is_chinese_equal(bill_type_name, '收入'):
                            bill_type = BillType.INCOME
                        elif is_chinese_equal(bill_type_name, '支出'):
                            bill_type = BillType.EXPENSE
                        elif is_chinese_equal(bill_type_name, '不计收支'):
                            bill_type = BillType.OTHER
                        
                        bill_item = BillItem(float(amount), payee, item_name, bill_type, order_id, bill_time, "alipay", self.owner)
                        bill_item_list.append(bill_item)

class WeChatBill(BaseBill):
    def __init__(self, file_path, owner, bill_time_format):
        self.file_path = file_path
        self.owner = owner
        self.bill_time_format = bill_time_format

    def parse_from_file(self, bill_item_list):
        # 使用chardet检测文件的编码
        with open(self.file_path, 'rb') as f:
            result = chardet.detect(f.read())
            file_encoding = result['encoding']

        # 使用csv模块读取CSV文件，并自动根据文件编码进行解码
        with codecs.open(self.file_path, 'r', encoding=file_encoding) as f:
            reader = csv.reader(f)

            # 初始化标志变量
            print_flag = False

            # 循环读取每一行并打印指定列
            for row in reader:
                row = [col.strip() for col in row]
                if row[0].startswith('------'):
                    # 如果读到了第一个"------"行，将标志变量设置为True
                    if not print_flag:
                        print_flag = True
                    # 如果读到了第二个"------"行，将标志变量设置为False，并停止打印
                    else:
                        print_flag = False
                        break
                else:
                    # 如果标志变量为True，打印当前行
                    if print_flag:
                        if is_chinese_equal(row[0], "交易时间"):
                            continue
                        amount = float(row[5].lstrip(chr(165))) # 去除 '¥' 符号
                        payee = row[2]
                        item_name = row[3]
                        bill_type_name = row[4]
                        order_id = row[8]
                        bill_stat = row[7]
                        if bill_stat.startswith("已退款"):
                            pattern = r"￥(\d+\.\d+)"
                            match = re.search(pattern, bill_stat)
                            if match:
                                number = float(match.group(1))
                                amount = amount - number

                        bill_time = str2timestamp(row[0], self.bill_time_format)
                        if is_chinese_equal(bill_type_name, '收入'):
                            bill_type = BillType.INCOME
                        elif is_chinese_equal(bill_type_name, '支出'):
                            bill_type = BillType.EXPENSE
                        elif is_chinese_equal(bill_type_name, '不计支出'):
                            bill_type = BillType.OTHER
                        
                        bill_item = BillItem(amount, payee, item_name, bill_type, order_id, bill_time, "wechat", self.owner)
                        bill_item_list.append(bill_item)

def merge_items(bill_item_list: List[BillItem]) -> List[BillItem]:
    order_items = {}
    merged_items = []
    for item in bill_item_list:
        if not item.order_id:
            item.category = ExpenseCategory.SKIP
            merged_items.append(item)
            continue

        if item.order_id not in order_items:
            order_items[item.order_id] = []
        order_items[item.order_id].append(item)

    for order_id, items in order_items.items():
        if len(items) == 1:
            merged_items.append(items[0])
        else:
            for item in items:
                print("order list:", item)
            # split the items into two lists: expense items and refund items
            expense_items = []
            refund_items = []
            for item in items:
                if item.bill_type == BillType.OTHER and '退款' in item.item_name:
                    refund_items.append(item)
                else:
                    expense_items.append(item)

            # merge expense items
            if expense_items:
                merged_item = expense_items[0]
                for item in expense_items[1:]:
                    merged_item.amount += item.amount
                # merged_items.append(merged_item)

                # refund expense items
                for item in refund_items:
                    merged_item.amount -= item.amount

                if merged_item.amount == 0.0:
                    merged_item.category = ExpenseCategory.SKIP

                merged_items.append(merged_item)
                print("merge item:", merged_item)
            else:
                for item in refund_items:
                    print("merge all refund_item", item)
                    merged_items.append(item)


    return merged_items

def categorize_items(items: List[BillItem]) -> List[BillItem]:
    # set expense category for each item
    for item in items:
        if item.category != ExpenseCategory.UNKNOWN:
            continue

        if item.item_name in item_category_dict:
            item.category = item_category_dict[item.item_name]
            continue

        if item.payee in payee_category_dict:
            item.category = payee_category_dict[item.payee]
            continue

        # check if item_name contains "外卖订单"
        item_reg_match = False
        for item_reg, category in item_category_regular_dict.items():
            if item_reg in item.item_name:
                item.category = category
                item_reg_match = True
                break
        if item_reg_match:
            continue

        payee_reg_match = False
        for payee_reg, category in payee_category_regular_dict.items():
            if payee_reg in item.payee:
                item.category = category
                payee_reg_match = True
                break
        if payee_reg_match:
            continue

        pass

    # 策略 2
    s = 0
    e = 0
    for i, item in enumerate(items):
        if item.category != ExpenseCategory.UNKNOWN:
            continue
        bill_time = item.bill_time
        while True:
            if s == i:
                break
            if bill_time - items[s].bill_time > BUY_VEGETABLES_TIME_RANGE:
                s+=1
            else:
                break
        while True:
            if e+1 >= len(items):
                break
            if items[e+1].bill_time - bill_time < BUY_VEGETABLES_TIME_RANGE:
                e+=1
            else:
                break

        for j in range(s, e):
            if j == i: 
                continue
            if items[j].category == ExpenseCategory.BUY_VEGETABLES:
                item.category = ExpenseCategory.BUY_VEGETABLES
                break

def record_to_excel(bill_item_list):
    # 输入到 excel
    #   1. 按照大类划分，每个大类 x 列
    #       a. 金额
    #       b. 名称
    #   2. 退款数据 
    #   3. 无法识别的大类
    #   4. 大类汇总金额
    #   5. 月份汇总金额
    
    file_name = os.path.expanduser('~/Downloads/3.xlsx')
    sheet_name = "月度明细"

    expense_data = []
    income_data = []
    unknown_data = []
    other_data = []
    skip_data = []
    for bill_item in bill_item_list:
        if bill_item.bill_type == BillType.INCOME:
            income_data.append({
                "金额": bill_item.amount,
                "类别": bill_item.category.value,
                "交易对象": bill_item.payee,
                "商品名称": bill_item.item_name,
                "收支类型": bill_item.bill_type.value,
                "订单号": bill_item.order_id,
                "订单发生时间": timestamp2str(bill_item.bill_time),
                "订单来源": bill_item.bill_source,
                "Owner": bill_item.owner
            })
        elif bill_item.bill_type == BillType.OTHER:
            other_data.append({
                "金额": bill_item.amount,
                "类别": bill_item.category.value,
                "交易对象": bill_item.payee,
                "商品名称": bill_item.item_name,
                "收支类型": bill_item.bill_type.value,
                "订单号": bill_item.order_id,
                "订单发生时间": timestamp2str(bill_item.bill_time),
                "订单来源": bill_item.bill_source,
                "Owner": bill_item.owner
            })
        else:
            if bill_item.category == ExpenseCategory.UNKNOWN:
                unknown_data.append({
                    "金额": bill_item.amount,
                    "类别": bill_item.category.value,
                    "交易对象": bill_item.payee,
                    "商品名称": bill_item.item_name,
                    "收支类型": bill_item.bill_type.value,
                    "订单号": bill_item.order_id,
                    "订单发生时间": timestamp2str(bill_item.bill_time),
                    "订单来源": bill_item.bill_source,
                    "Owner": bill_item.owner
                })
            elif bill_item.category == ExpenseCategory.SKIP:
                skip_data.append({
                    "金额": bill_item.amount,
                    "类别": bill_item.category.value,
                    "交易对象": bill_item.payee,
                    "商品名称": bill_item.item_name,
                    "收支类型": bill_item.bill_type.value,
                    "订单号": bill_item.order_id,
                    "订单发生时间": timestamp2str(bill_item.bill_time),
                    "订单来源": bill_item.bill_source,
                    "Owner": bill_item.owner
                })
            else:
                if bill_item.amount == 0.0:
                    skip_data.append({
                        "金额": bill_item.amount,
                        "类别": bill_item.category.value,
                        "交易对象": bill_item.payee,
                        "商品名称": bill_item.item_name,
                        "收支类型": bill_item.bill_type.value,
                        "订单号": bill_item.order_id,
                        "订单发生时间": timestamp2str(bill_item.bill_time),
                        "订单来源": bill_item.bill_source,
                        "Owner": bill_item.owner
                    })
                else:
                    expense_data.append({
                        "金额": bill_item.amount,
                        "类别": bill_item.category.value,
                        "交易对象": bill_item.payee,
                        "商品名称": bill_item.item_name,
                        "收支类型": bill_item.bill_type.value,
                        "订单号": bill_item.order_id,
                        "订单发生时间": timestamp2str(bill_item.bill_time),
                        "订单来源": bill_item.bill_source,
                        "Owner": bill_item.owner
                    })
    expense_df = pd.DataFrame(expense_data)
    income_df = pd.DataFrame(income_data)
    skip_df = pd.DataFrame(skip_data)
    unknown_df = pd.DataFrame(unknown_data)
    other_df = pd.DataFrame(other_data)

    n_rows = expense_df.shape[0] + unknown_df.shape[0]

    writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
    expense_df.to_excel(writer, sheet_name=sheet_name, index=False, )
    unknown_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow = len(expense_data)+1, header=False)
    other_df.to_excel(writer, sheet_name=sheet_name, index=False, startcol = 10)
    income_df.to_excel(writer, sheet_name=sheet_name, index=False, startcol = 20)
    skip_df.to_excel(writer, sheet_name=sheet_name, index=False, startcol = 10, startrow = len(other_data) + 5)

    workbook = writer.book
    worksheet = writer.sheets[sheet_name]

    source = [category.value for category in ExpenseCategory]

    # for i in range(n_rows):
    worksheet.data_validation('B2:B'+str(1+n_rows), {'validate' : 'list', 'source': source})

    # worksheet.column_dimensions['A'].width = 20
    worksheet.set_column('A:A', 15)
    worksheet.set_column('B:B', 15)
    worksheet.set_column('C:D', 30)
    worksheet.set_column('E:E', 15)
    # worksheet.set_column('A:A', 15)

    workbook.close()

if __name__ == "__main__":
    bill_item_list = []

    zrz_alipay_file = os.path.expanduser('~/Downloads/账单/四月/zrz_alipay.csv')
    zrz_wechat_file = os.path.expanduser('~/Downloads/账单/四月/zrz_wc.csv')
    cwx_alipay_file = os.path.expanduser('~/Downloads/账单/四月/cwx_alipay.csv')
    cwx_wechat_file = os.path.expanduser('~/Downloads/账单/四月/cwx_wc.csv')

    zrz_alipay_bill = AliPayBill(zrz_alipay_file, "zrz", '%Y-%m-%d %H:%M:%S')
    zrz_alipay_bill.parse_from_file(bill_item_list)

    zrz_wechat_bill = WeChatBill(zrz_wechat_file, "zrz", '%Y-%m-%d %H:%M:%S')
    zrz_wechat_bill.parse_from_file(bill_item_list)

    cwx_alipay_bill = AliPayBill(cwx_alipay_file, "cwx", '%Y-%m-%d %H:%M:%S')
    cwx_alipay_bill.parse_from_file(bill_item_list)

    cwx_wechat_bill = WeChatBill(cwx_wechat_file, "cwx", '%Y-%m-%d %H:%M:%S')
    cwx_wechat_bill.parse_from_file(bill_item_list)

    print("---normal--------", len(bill_item_list))
    for bill_item in bill_item_list:
        print(bill_item)

    # 分析数据
    #   1. 合并退款
    uniq_bill_item_list = merge_items(bill_item_list)
    print("---uniq--------", len(uniq_bill_item_list))
    for bill_item in uniq_bill_item_list:
        print(bill_item)

    sorted_bill_items = sorted(uniq_bill_item_list, key=lambda item: item.bill_time)
    print("---sort--------", len(sorted_bill_items))
    for bill_item in sorted_bill_items:
        print(bill_item)

    #   2. 划分到某个大类
    categorize_items(sorted_bill_items)

    # for bill_item in uniq_bill_item_list:
    #     print(bill_item)
    record_to_excel(uniq_bill_item_list)

