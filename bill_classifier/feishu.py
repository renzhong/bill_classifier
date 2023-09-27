import requests
import json
import datetime
import logging
from category import expense_category_mapping

logger = logging.getLogger(__name__)

def timestamp2str(t):
    dt_object = datetime.datetime.fromtimestamp(t)
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")

class FeishuSheetAPI:
    category_color_dict = {
        "水电物业": "#BACEFD",
        "餐饮": "#FED4A4",
        "买菜": "#F76964",
        "交通": "#F8E6AB",
        "日常开支": "#A9EFE6",
        "服装鞋帽": "#FDE2E2",
        "护肤品": "#ECE2FE",
        "人情往来": "#D9F5D6",
        "休闲娱乐": "#F8DEF8",
        "杂项": "#EEF6C6",
        "家庭建设": "#BACEFD",
        "医疗": "#FED4A4",
        "大件": "#F76964",
        "养车": "#F8E6AB",
        "unknown": "#A9EFE6",
        "skip": "#FDE2E2",
        "退款": "#ECE2FE",
        "收入": "#D9F5D6"
    }

    alg_color_dict = {
        "完全匹配": "#BACEFD",
        "模糊匹配": "#FED4A4",
        "菜场模式": "#F76964",
        "GPT模式": "#F8E6AB",
        "无法识别": "#A9EFE6"
    }

    def __init__(self, user_access_token, sheet_token):
        self.user_access_token = user_access_token
        self.sheet_token = sheet_token

    def GetSheetInfo(self):
        url = "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{}/sheets/query".format(self.sheet_token)

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.get(url, headers=headers)

        rsp = json.loads(response.text)

        if rsp['code'] != 0:
            logging.error("GetSheetCount error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return {}

        if 'data' not in rsp or 'sheets' not in rsp['data']:
            logging.error("GetSheetCount response format error rsp:{}".format(rsp))
            return {}

        sheet_info = {}
        for sheet in rsp['data']['sheets']:
            title = sheet['title']
            sheet_id = sheet['sheet_id']
            sheet_info[title] = {
                "sheet_id": sheet_id
            }

        return sheet_info

    def AddNewSheet(self, sheet_name, index):
        logging.info("新增 sheet : {}".format(sheet_name))
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/sheets_batch_update".format(self.sheet_token)

        data = {
            "requests":[
                {
                    "addSheet": {
                        "properties": {
                            "title": sheet_name,
                            "index": index
                        }
                    }
                }]
        }

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.post(url, json=data, headers=headers)

        rsp = json.loads(response.text)

        if rsp['code'] != 0:
            logging.error("AddNewSheet error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False, ""
        else:
            if 'data' not in rsp or 'replies' not in rsp['data']:
                logging.error("AddNewSheet response format error rsp:", rsp)
                return False, ""

            replies = rsp['data']['replies']
            if len(replies) == 0:
                logging.error("AddNewSheet response format error rsp:", rsp)
                return False, ""

            reply = replies[0]
            if 'addSheet' not in reply or \
                    'properties' not in reply['addSheet'] or \
                    'sheetId' not in reply['addSheet']['properties']:
                logging.error("AddNewSheet response format error rsp:", rsp)
                return False, ""

            return True, reply['addSheet']['properties']['sheetId']

    def AddRows(self, sheet_id, add_rows):
        logging.info("表内增加空白行: {}".format(add_rows))
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/dimension_range".format(self.sheet_token)

        data = {
            "dimension":{
                "sheetId": sheet_id,
                "majorDimension": "ROWS",
                "length": add_rows
            }
        }

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.post(url, json=data, headers=headers)

        rsp = json.loads(response.text)

        if rsp['code'] != 0:
            logging.error("AddRows error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False
        else:
            return True

    def AddDataValidation(self, sheet_id, validation_range, validation_dict):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/dataValidation".format(self.sheet_token)

        data = {
            "range": validation_range,
            "dataValidationType": "list",
            "dataValidation":{
                "conditionValues": list(validation_dict.keys()),
                "options": {
                    "highlightValidData": True,
                    "colors": list(validation_dict.values())
                }
            }
        }

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.post(url, json=data, headers=headers)

        rsp = json.loads(response.text)

        if rsp['code'] != 0:
            logging.error("AddDataValidation error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False
        else:
            return True

    def RecordBillItem(self, sheet_range, bill_item_list):
        logging.info("记录账单数据 sheet_range:{} list size:{}".format(sheet_range, len(bill_item_list)))
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values".format(self.sheet_token)

        data = {
            "valueRange": {
                "range": sheet_range,
                "values": []
            }
        }

        for item in bill_item_list:
            line_data = [
                item.amount,
                item.category.to_str(),
                item.payee,
                item.item_name,
                item.bill_type.value,
                timestamp2str(item.bill_time),
                item.bill_source,
                item.owner,
                item.classify_alg.to_str()
            ]

            data['valueRange']['values'].append(line_data)

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.put(url, json=data, headers=headers)

        rsp = json.loads(response.text)
        if rsp['code'] != 0:
            logging.error("RecordBillItem error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False
        else:
            return True

    def UpdateMonthSheetData(self, month_sheet_id, detail_sheet_name, column, row_size):
        logging.info("更新月度表:{} column:{} row_size:{}".format(detail_sheet_name, column, row_size))
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values".format(self.sheet_token)

        value_range = "{}!{}2:{}18".format(month_sheet_id, column, column)

        data = {
            "valueRange": {
                "range": value_range,
                "values": []
            }
        }

        for line in range(2, 18):
            data['valueRange']['values'].append(
                [{
                    "type": "formula",
                    "text": "=SUMIF('{}'!B1:B{}, A{}, '{}'!A1:A{})".format(detail_sheet_name, row_size, line, detail_sheet_name, row_size)
                }])

        data['valueRange']['values'].append(
            [{
                "type": "formula",
                "text": "=SUM({}2:{}15) - {}16".format(column, column, column)
            }])

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.put(url, json=data, headers=headers)

        rsp = json.loads(response.text)
        if rsp['code'] != 0:
            logging.error("UpdateMonthSheetInfo error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False
        else:
            return True

    def UpdateMonthSheetFormatter(self, month_sheet_id, column):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/styles_batch_update".format(self.sheet_token)

        value_range = "{}!{}2:{}17".format(month_sheet_id, column, column)

        data_str = '{{"data":[{{"ranges": "{}", "style": {{"formatter": "#,##0"}}}}]}}'.format(value_range)
        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        # 发送请求并获取响应
        response = requests.put(url, data=data_str, headers=headers)

        rsp = json.loads(response.text)
        if rsp['code'] != 0:
            logging.error("UpdateMonthSheetFormatter error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False
        else:
            return True

    def UpdateMonthSheetInfo(self, month_sheet_id, detail_sheet_name, row_size):
        now = datetime.datetime.now()  # 获取当前日期时间
        month_int = now.month
        if now.day < 15:
            last_month = now - datetime.timedelta(days=20)  # 计算上个月的日期时间
            month_int = last_month.month

        column = chr(ord('A') + month_int)

        self.UpdateMonthSheetFormatter(month_sheet_id, column)
        self.UpdateMonthSheetData(month_sheet_id, detail_sheet_name, column, row_size)

    def GetCategoryClassificationInfo(self, value_range):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values/{}".format(self.sheet_token, value_range)

        # 设置请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.user_access_token
        }

        params = {
            "valueRenderOption": "ToString"
        }

        response = requests.get(url, params=params, headers=headers)
        rsp = json.loads(response.text)

        if rsp['code'] != 0:
            logging.error("GetCategoryClassificationInfo error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False, {}

        values = rsp['data']['valueRange']['values']
        value_map = {}
        for value in values[1:]:
            key = value[0]
            category = expense_category_mapping[value[1]]
            value_map[key] = category

        return True, value_map


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    user_access_token = "u-fifoFx5btdxqPwSe0dTDgLlk6bfh1lHFgwG0h4ow2ARM"
    sheet_token = "HwSRs3mvOhHUu6tY70mcFBnRnDe"
    feishu_sheet_api = FeishuSheetAPI(user_access_token, sheet_token)
    feishu_sheet_api.GetCategoryClassificationInfo('125297!A:B')
