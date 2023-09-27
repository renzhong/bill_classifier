#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import logging
import chardet
import codecs
import csv

from util import is_chinese_equal, str2timestamp
from bill_item import BillType, BillItem

logger = logging.getLogger(__name__)

class BaseBill:
    file_path: str
    owner: str
    bill_type: str

    def __init__(self, bill_file):
        self.file_path = bill_file.file_name
        self.owner = bill_file.bill_owner
        self.bill_type = 'default'

    def parse_from_file(self):
        pass

class AliPayBill(BaseBill):
    bill_time_format: str
    def __init__(self, bill_file):
        super().__init__(bill_file)
        self.bill_time_format = '%Y-%m-%d %H:%M:%S'
        self.bill_type = 'AliPay'

    def get_bill_rows(self):
        # 使用chardet检测文件的编码
        with open(self.file_path, 'rb') as f:
            result = chardet.detect(f.read())
            file_encoding = result['encoding']

        bill_rows = []
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
                        bill_rows.append(row)

        return bill_rows

    def parse_from_file(self, bill_item_list):
        bill_rows = self.get_bill_rows()

        for row in bill_rows:
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
    bill_time_format: str
    def __init__(self, bill_file):
        super().__init__(bill_file)
        self.bill_time_format = '%Y-%m-%d %H:%M:%S'
        self.bill_type = 'WeChat'

    def get_bill_rows(self):
        # 使用chardet检测文件的编码
        with open(self.file_path, 'rb') as f:
            result = chardet.detect(f.read())
            file_encoding = result['encoding']

        bill_rows = []

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
                        bill_rows.append(row)

        return bill_rows

    def parse_from_file(self, bill_item_list):
        bill_rows = self.get_bill_rows()

        for row in bill_rows:
            amount = float(row[5].lstrip(chr(165)))  # 去除 '¥' 符号
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

            if (len(row[0]) == 19):
                bill_time = str2timestamp(row[0], "%Y-%m-%d %H:%M:%S")
            else:
                bill_time = str2timestamp(row[0], "%Y/%m/%d %H:%M")

            if is_chinese_equal(bill_type_name, '收入'):
                bill_type = BillType.INCOME
            elif is_chinese_equal(bill_type_name, '支出'):
                bill_type = BillType.EXPENSE
            elif is_chinese_equal(bill_type_name, '不计支出'):
                bill_type = BillType.OTHER

            bill_item = BillItem(amount, payee, item_name, bill_type, order_id, bill_time, "wechat", self.owner)
            bill_item_list.append(bill_item)
