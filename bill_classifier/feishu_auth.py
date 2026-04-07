import base64
import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

DEVICE_AUTHORIZATION_URL = "https://accounts.feishu.cn/oauth/v1/device_authorization"
OAUTH_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
DEFAULT_SCOPE = "offline_access sheets:spreadsheet"
REFRESH_AHEAD_SECONDS = 300


class FeishuAuthError(Exception):
    pass


def _safe_get(config, section, option, fallback=""):
    if config.has_option(section, option):
        return config.get(section, option)
    return fallback


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_feishu_auth_config(config):
    return {
        "app_id": os.getenv("FEISHU_APP_ID") or _safe_get(config, "feishu", "app_id"),
        "app_secret": os.getenv("FEISHU_APP_SECRET") or _safe_get(config, "feishu", "app_secret"),
        "user_access_token": os.getenv("FEISHU_USER_ACCESS_TOKEN") or _safe_get(config, "feishu", "user_access_token"),
        "refresh_token": os.getenv("FEISHU_REFRESH_TOKEN") or _safe_get(config, "feishu", "refresh_token"),
        "token_expires_at": _to_int(os.getenv("FEISHU_TOKEN_EXPIRES_AT") or _safe_get(config, "feishu", "token_expires_at"), 0),
        "refresh_token_expires_at": _to_int(os.getenv("FEISHU_REFRESH_TOKEN_EXPIRES_AT") or _safe_get(config, "feishu", "refresh_token_expires_at"), 0),
        "scope": os.getenv("FEISHU_SCOPE") or _safe_get(config, "feishu", "scope", DEFAULT_SCOPE),
        "user_open_id": _safe_get(config, "feishu", "user_open_id"),
        "user_name": _safe_get(config, "feishu", "user_name"),
    }


def request_device_authorization(app_id, app_secret, scope=DEFAULT_SCOPE):
    if not app_id or not app_secret:
        raise FeishuAuthError("缺少飞书 app_id 或 app_secret，请在 config.ini 或环境变量中配置")

    final_scope = scope or DEFAULT_SCOPE
    if "offline_access" not in final_scope.split():
        final_scope = f"{final_scope} offline_access".strip()

    basic_auth = base64.b64encode(f"{app_id}:{app_secret}".encode("utf-8")).decode("utf-8")
    response = requests.post(
        DEVICE_AUTHORIZATION_URL,
        data={"client_id": app_id, "scope": final_scope},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_auth}",
        },
        timeout=30,
    )
    data = response.json()
    if response.status_code >= 400 or data.get("error"):
        raise FeishuAuthError(data.get("error_description") or data.get("error") or "设备授权失败")

    return {
        "device_code": data["device_code"],
        "user_code": data.get("user_code", ""),
        "verification_uri": data.get("verification_uri", ""),
        "verification_uri_complete": data.get("verification_uri_complete") or data.get("verification_uri", ""),
        "expires_in": int(data.get("expires_in", 240)),
        "interval": int(data.get("interval", 5)),
        "scope": final_scope,
    }


def poll_device_token(app_id, app_secret, device_code, interval, expires_in):
    deadline = time.time() + expires_in
    current_interval = max(int(interval), 1)

    while time.time() < deadline:
        time.sleep(current_interval)
        response = requests.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": app_id,
                "client_secret": app_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        data = response.json()
        error = data.get("error")

        if not error and data.get("access_token"):
            now = int(time.time())
            token_expires_in = int(data.get("expires_in", 7200))
            refresh_token_expires_in = int(data.get("refresh_token_expires_in", 604800))
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", ""),
                "scope": data.get("scope", ""),
                "token_expires_at": now + token_expires_in,
                "refresh_token_expires_at": now + refresh_token_expires_in,
                "expires_in": token_expires_in,
                "refresh_token_expires_in": refresh_token_expires_in,
            }

        if error == "authorization_pending":
            continue
        if error == "slow_down":
            current_interval = min(current_interval + 5, 60)
            continue
        if error in ("access_denied", "expired_token", "invalid_grant"):
            raise FeishuAuthError(data.get("error_description") or error)

        raise FeishuAuthError(data.get("error_description") or error or "轮询 token 失败")

    raise FeishuAuthError("授权超时，请重新执行登录")


def refresh_user_access_token(app_id, app_secret, refresh_token):
    if not app_id or not app_secret or not refresh_token:
        raise FeishuAuthError("缺少 refresh token 刷新所需配置")

    response = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": app_id,
            "client_secret": app_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = response.json()

    if data.get("error") or (data.get("code") not in (None, 0)):
        raise FeishuAuthError(data.get("error_description") or data.get("msg") or data.get("error") or "刷新 user_access_token 失败")

    now = int(time.time())
    token_expires_in = int(data.get("expires_in", 7200))
    refresh_token_expires_in = int(data.get("refresh_token_expires_in", 0))
    refresh_expires_at = now + refresh_token_expires_in if refresh_token_expires_in > 0 else 0

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or refresh_token,
        "scope": data.get("scope", ""),
        "token_expires_at": now + token_expires_in,
        "refresh_token_expires_at": refresh_expires_at,
        "expires_in": token_expires_in,
        "refresh_token_expires_in": refresh_token_expires_in,
    }


def get_user_info(access_token):
    response = requests.get(
        USER_INFO_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )
    data = response.json()
    if data.get("code") != 0:
        raise FeishuAuthError(data.get("msg") or "获取用户信息失败")

    user_data = data.get("data", {})
    return {
        "user_open_id": user_data.get("open_id", ""),
        "user_name": user_data.get("name", ""),
    }


def get_valid_user_access_token(config, config_file=None):
    auth_config = load_feishu_auth_config(config)
    env_access_token = os.getenv("FEISHU_USER_ACCESS_TOKEN")
    if env_access_token:
        return env_access_token

    now = int(time.time())
    access_token = auth_config["user_access_token"]
    token_expires_at = auth_config["token_expires_at"]
    if access_token and (token_expires_at == 0 or now < token_expires_at - REFRESH_AHEAD_SECONDS):
        return access_token

    refresh_token = auth_config["refresh_token"]
    refresh_token_expires_at = auth_config["refresh_token_expires_at"]
    can_refresh = (
        auth_config["app_id"]
        and auth_config["app_secret"]
        and refresh_token
        and (refresh_token_expires_at == 0 or now < refresh_token_expires_at)
    )
    if can_refresh:
        token_data = refresh_user_access_token(auth_config["app_id"], auth_config["app_secret"], refresh_token)
        user_info = {
            "user_open_id": auth_config["user_open_id"],
            "user_name": auth_config["user_name"],
        }
        apply_token_data_to_config(config, token_data, user_info)
        if config_file:
            save_config(config, config_file)
        return token_data["access_token"]

    raise FeishuAuthError(
        "缺少有效的 user_access_token。请先执行 `python3 feishu_login.py --config_file=config/config.ini` 完成授权"
    )


def apply_token_data_to_config(config, token_data, user_info=None):
    if not config.has_section("feishu"):
        config.add_section("feishu")

    config.set("feishu", "user_access_token", token_data.get("access_token", ""))
    config.set("feishu", "refresh_token", token_data.get("refresh_token", ""))
    config.set("feishu", "token_expires_at", str(token_data.get("token_expires_at", 0)))
    config.set("feishu", "refresh_token_expires_at", str(token_data.get("refresh_token_expires_at", 0)))
    if token_data.get("scope"):
        config.set("feishu", "scope", token_data["scope"])

    if user_info:
        if user_info.get("user_open_id"):
            config.set("feishu", "user_open_id", user_info["user_open_id"])
        if user_info.get("user_name"):
            config.set("feishu", "user_name", user_info["user_name"])


def save_config(config, config_file):
    with open(config_file, "w", encoding="utf-8") as file_obj:
        config.write(file_obj)


def format_shell_exports(token_data):
    exports = {
        "FEISHU_USER_ACCESS_TOKEN": token_data.get("access_token", ""),
        "FEISHU_REFRESH_TOKEN": token_data.get("refresh_token", ""),
        "FEISHU_TOKEN_EXPIRES_AT": str(token_data.get("token_expires_at", 0)),
        "FEISHU_REFRESH_TOKEN_EXPIRES_AT": str(token_data.get("refresh_token_expires_at", 0)),
    }
    return "\n".join(
        f"export {key}={json.dumps(value)}" for key, value in exports.items() if value
    )
