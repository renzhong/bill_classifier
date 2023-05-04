#!/usr/bin/env python
# -*- coding: utf-8 -*-

from openpyxl import load_workbook
import pandas as pd

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


