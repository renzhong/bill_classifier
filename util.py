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


