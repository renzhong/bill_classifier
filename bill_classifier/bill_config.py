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


class ModelConfig:
    """单个模型调用配置（OpenAI 兼容协议）。

    一个 ModelConfig 描述了向某个 OpenAI 兼容服务发起调用所需的全部信息：
    服务端点（base_url）、调用时填入的模型名（model_name）、鉴权信息（api_key/api_secret）。
    不同厂商（OpenAI、通义千问、豆包、Gemini OpenAI 兼容端点等）只要协议一致，
    就只在这几个字段上有差异。
    """

    name: str
    base_url: str
    model_name: str
    api_key: str
    api_secret: str

    def __init__(self, name: str = "", base_url: str = "", model_name: str = "",
                 api_key: str = "", api_secret: str = ""):
        self.name = name
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self.api_secret = api_secret


class GPTConfig:
    call_limit: int
    active_model: str
    models: dict

    def __init__(self):
        self.call_limit = -1
        self.active_model = ""
        self.models = {}

    @property
    def current_model(self) -> ModelConfig:
        if self.active_model not in self.models:
            raise ValueError(
                f"active_model={self.active_model!r} 未在 [model.*] 中定义，"
                f"已知模型配置: {list(self.models.keys())}"
            )
        return self.models[self.active_model]


class StrategyConfig:
    """pipeline 行为配置，目前只支持禁用某些 step。"""

    disabled_steps: list

    def __init__(self):
        self.disabled_steps = []


# 模型配置 section 的前缀，例如 [model.qwen3_max]
_MODEL_SECTION_PREFIX = "model."


class BillConfig:
    feishu_config: FeishuConfig
    gpt_config: GPTConfig
    strategy_config: StrategyConfig

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
        self.gpt_config.call_limit = int(config.get('gpt', 'call_limit', fallback='-1'))
        self.gpt_config.active_model = config.get('gpt', 'active_model')

        for section in config.sections():
            if not section.startswith(_MODEL_SECTION_PREFIX):
                continue
            name = section[len(_MODEL_SECTION_PREFIX):]
            if not name:
                raise ValueError(f"非法的模型配置 section: [{section}]")
            self.gpt_config.models[name] = ModelConfig(
                name=name,
                base_url=config.get(section, 'base_url'),
                model_name=config.get(section, 'model_name'),
                api_key=config.get(section, 'api_key'),
                api_secret=config.get(section, 'api_secret', fallback=''),
            )

        if self.gpt_config.active_model not in self.gpt_config.models:
            raise ValueError(
                f"[gpt].active_model={self.gpt_config.active_model!r} 未对应任何 "
                f"[model.*] section，已加载: {list(self.gpt_config.models.keys())}"
            )

        self.strategy_config = StrategyConfig()
        raw_disabled = config.get('strategy', 'disabled_steps', fallback='').strip()
        if raw_disabled:
            self.strategy_config.disabled_steps = [
                s.strip() for s in raw_disabled.split(',') if s.strip()
            ]
