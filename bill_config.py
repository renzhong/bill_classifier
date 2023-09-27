import configparser

class FeishuConfig:
    user_access_token: str
    bill_sheet_token: str
    category_sheet_token: str

    def __init__(self):
        pass

class GPTConfig:
    api_key: str
    call_limit: int

    def __init__(self):
        pass


class BillConfig:
    feishu_config: FeishuConfig
    gpt_config: GPTConfig

    def __init__(self, config):
        self.feishu_config = FeishuConfig()
        self.feishu_config.user_access_token = config.get('feishu', 'user_access_token')
        self.feishu_config.bill_sheet_token = config.get('feishu', 'bill_sheet_token')
        self.feishu_config.category_sheet_token = config.get('feishu', 'category_sheet_token')

        self.gpt_config = GPTConfig()
        self.gpt_config.api_key = config.get('gpt', 'api_key')
        self.gpt_config.call_limit = int(config.get('gpt', 'call_limit'))

