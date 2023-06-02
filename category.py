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
    "哈啰出行": ExpenseCategory.TRANSPORTATION,
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

remove_item_dict = {
    "iCloud 由云上贵州运营": True,
    "北京轨道交通路网管理有限公司": True
}


