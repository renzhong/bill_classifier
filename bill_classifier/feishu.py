import requests
import json
import datetime
import logging
from itertools import cycle
from category import expense_category_mapping, ExpenseCategory
from bill_item import ClassifyAlg
from util import GetMonthInt

logger = logging.getLogger(__name__)

def timestamp2str(t):
    dt_object = datetime.datetime.fromtimestamp(t)
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")

class FeishuUnit:
    row = '1'
    col = 'A'
    def __init__(self, row, col):
        self.row = row
        self.col = col

    def GetCol(self, offset=0):
        if offset == 0:
            return self.col
        new_col_int = ord(self.col) - ord('A') + 1 + offset
        new_col = chr(ord('A') + new_col_int - 1)

        return new_col

    def GetRow(self, offset=0):
        if offset == 0:
            return self.row
        new_row = int(self.row) + offset

        return str(new_row)

class FeishuSheetAPI:
    unit_color = [
        "#BACEFD", "#FED4A4", "#F76964", "#F8E6AB", "#A9EFE6",
        "#FDE2E2", "#ECE2FE", "#D9F5D6", "#F8DEF8", "#EEF6C6"
    ]

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

    def AddCols(self, sheet_id, add_cols):
        logging.info("表内增加空白列: {}".format(add_cols))
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/dimension_range".format(self.sheet_token)

        data = {
            "dimension":{
                "sheetId": sheet_id,
                "majorDimension": "COLUMNS",
                "length": add_cols
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
            logging.error("AddCols error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False
        else:
            return True

    def AddDataValidation(self, sheet_id, validation_range, validation_keys):
        # TODO: 是否需要 AddRows
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/dataValidation".format(self.sheet_token)

        cycled_listc = cycle(self.unit_color)
        validation_colors = [next(cycled_listc) for _ in validation_keys]
        data = {
            "range": validation_range,
            "dataValidationType": "list",
            "dataValidation":{
                "conditionValues": list(validation_keys),
                "options": {
                    "highlightValidData": True,
                    "colors": list(validation_colors)
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

    def UpdateMonthSheetData(self, month_sheet_id, detail_sheet_name, column, row_size, line_title):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values".format(self.sheet_token)

        start_line = 2
        end_line = start_line + len(line_title) - 1
        value_range = "{}!{}{}:{}{}".format(month_sheet_id, column, start_line, column, end_line)

        logging.info("更新月度表:{} column:{} row_size:{} range:{}".format(detail_sheet_name, column, row_size, value_range))

        data = {
            "valueRange": {
                "range": value_range,
                "values": []
            }
        }

        # 找到退款行
        refund_line = -1
        skip_line = -1  # skip 以上都是统计项
        for index, title in enumerate(line_title):
            if title == '退款':
                refund_line = start_line + index
            if title == 'skip':
                skip_line = start_line + index

        for line in range(start_line, end_line + 1):
            title = line_title[line - start_line]
            if title == '合计':
                # 所有账单包括(unknown) - 退款
                data['valueRange']['values'].append(
                    [{
                        "type": "formula",
                        "text": "=SUM({}{}:{}{}) - {}{}".format(column, start_line, column, skip_line - 1, column, refund_line)
                    }])
            else:
                data['valueRange']['values'].append(
                    [{
                        "type": "formula",
                        "text": "=SUMIF('{}'!B1:B{}, A{}, '{}'!A1:A{})".format(detail_sheet_name, row_size, line, detail_sheet_name, row_size)
                    }])
        print(data)

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

    def GetMonthSheetInfoLineTitle(self, month_sheet_id):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values/{}".format(self.sheet_token, "{}!A:A".format(month_sheet_id))

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
        titles = []
        for value in values[1:]:
            key = str(value[0])
            titles.append(key)

        return titles

    def UpdateMonthSheetFormatter(self, month_sheet_id, column, line_title):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/styles_batch_update".format(self.sheet_token)

        start_line = 2
        end_line = start_line + len(line_title) - 1
        value_range = "{}!{}{}:{}{}".format(month_sheet_id, column, start_line, column, end_line)

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
        column = chr(ord('A') + GetMonthInt())

        line_title = self.GetMonthSheetInfoLineTitle(month_sheet_id)

        for category in ExpenseCategory:
            if category.value not in line_title:
                logging.error("月度表中缺失分类项:{}".format(category.value))

        self.UpdateMonthSheetFormatter(month_sheet_id, column, line_title)
        self.UpdateMonthSheetData(month_sheet_id, detail_sheet_name, column, row_size, line_title)

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
            key = str(value[0])
            category = expense_category_mapping[value[1]]
            value_map[key] = category

        return True, value_map

    def GetClassificationTestData(self, value_range):
        url = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{}/values/{}".format(self.sheet_token, value_range)
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
            logging.error("GetClassificationTestData error code:{} msg:{}".format(rsp['code'], rsp['msg']))
            return False, []

        values = rsp['data']['valueRange']['values']
        test_data_list = []
        print("line:{}".format(len(values)))
        for value in values:
            # 检查 value 是否是数组，是否有 8 个元素
            if len(value) != 8:
                logging.error("GetClassificationTestData error value:{}".format(value))
                continue
            test_data = {
                "amount": value[0],
                "category": value[1],
                "payee": value[2],
                "item_name": value[3],
                "bill_type": value[4],
                "bill_time": value[5],
                "bill_source": value[6],
                "owner": value[7],
            }
            test_data_list.append(test_data)

        return True, test_data_list

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    user_access_token = "u-eBcLOqIKJflbkFLUvmBtdR013mVl5g2NWq00ggW009ve"
    sheet_token = "OxRdst6mhhclLGtOYTncmRenncb"
    feishu_sheet_api = FeishuSheetAPI(user_access_token, sheet_token)
    # feishu_sheet_api.AddDataValidation('4uqqJy', '4uqqJy!J1:J30', [category.value for category in ExpenseCategory])
    # line_title = feishu_sheet_api.UpdateMonthSheetInfo('qzQYh1', '账单明细 202311', 200)
    # print(line_title)

    # test_data_list = feishu_sheet_api.GetClassificationTestData('ad3acc!A1:A100')
    test_data_list = feishu_sheet_api.GetClassificationTestData('ad3acc')
    print(test_data_list)
