#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import time

def is_chinese_equal(s1: str, s2: str) -> bool:
    """判断两个中文字符串是否相等，忽略空格"""
    return s1.strip().encode('utf-8') == s2.strip().encode('utf-8')

def str2timestamp(time_str, time_format):
    if len(time_str) == 0:
        return time.time()

    dt_obj = datetime.datetime.strptime(time_str, time_format)
    return dt_obj.timestamp()

def timestamp2str(t):
    dt_object = datetime.datetime.fromtimestamp(t)
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")


def GetMonth():
    now = datetime.datetime.now()  # 获取当前日期时间
    month_str = ''
    if now.day >= 20:  # 如果今天是每个月的最后10天
        month_str = now.strftime('%Y%m')  # 输出当前年月字符串，格式为YYYYMM
    else:  # 如果今天是每个月的前20天
        last_month = now - datetime.timedelta(days=21)  # 计算上个月的日期时间
        month_str = last_month.strftime('%Y%m')  # 输出上个月的年月字符串，格式为YYYYMM

    return month_str

def GetMonthInt():
    now = datetime.datetime.now()  # 获取当前日期时间
    month_int = now.month
    if now.day >= 20:
        return month_int
    else:
        last_month = now - datetime.timedelta(days=21)  # 计算上个月的日期时间
        month_int = last_month.month
        return month_int
