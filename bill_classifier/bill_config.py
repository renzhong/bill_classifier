# import configparser

class FeishuConfig:
    app_id: str
    app_secret: str
    user_access_token: str
    refresh_token: str
    token_expires_at: int
    refresh_token_expires_at: int
    scope: str
    user_open_id: str
    user_name: str
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
        self.feishu_config.app_id = config.get('feishu', 'app_id', fallback='')
        self.feishu_config.app_secret = config.get('feishu', 'app_secret', fallback='')
        self.feishu_config.user_access_token = config.get('feishu', 'user_access_token', fallback='')
        self.feishu_config.refresh_token = config.get('feishu', 'refresh_token', fallback='')
        self.feishu_config.token_expires_at = config.getint('feishu', 'token_expires_at', fallback=0)
        self.feishu_config.refresh_token_expires_at = config.getint('feishu', 'refresh_token_expires_at', fallback=0)
        self.feishu_config.scope = config.get('feishu', 'scope', fallback='')
        self.feishu_config.user_open_id = config.get('feishu', 'user_open_id', fallback='')
        self.feishu_config.user_name = config.get('feishu', 'user_name', fallback='')
        self.feishu_config.bill_sheet_token = config.get('feishu', 'bill_sheet_token', fallback='')
        self.feishu_config.category_sheet_token = config.get('feishu', 'category_sheet_token', fallback='')

        self.gpt_config = GPTConfig()
        self.gpt_config.api_key = config.get('gpt', 'api_key')
        self.gpt_config.call_limit = int(config.get('gpt', 'call_limit'))
