#!/usr/bin/env python3

import argparse
import configparser
import logging
import sys

from feishu_auth import (
    FeishuAuthError,
    apply_token_data_to_config,
    format_shell_exports,
    get_user_info,
    load_feishu_auth_config,
    poll_device_token,
    request_device_authorization,
    save_config,
)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="通过飞书 OAuth Device Flow 获取 user_access_token")
    parser.add_argument("--config_file", default="config/config.ini", help="配置文件路径")
    parser.add_argument("--scope", default="", help="请求的 scope，默认读取 config.ini 中的 feishu.scope")
    parser.add_argument("--print-shell", action="store_true", help="输出 export 语句，便于 eval 使用")
    parser.add_argument("--no-write-config", action="store_true", help="只获取 token，不写回 config.ini")
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config_file)
    auth_config = load_feishu_auth_config(config)
    scope = args.scope or auth_config["scope"]

    try:
        device_data = request_device_authorization(auth_config["app_id"], auth_config["app_secret"], scope)
        print("请在浏览器中打开以下链接完成授权:\n")
        print(device_data["verification_uri_complete"])
        print("")
        token_data = poll_device_token(
            auth_config["app_id"],
            auth_config["app_secret"],
            device_data["device_code"],
            device_data["interval"],
            device_data["expires_in"],
        )
        user_info = get_user_info(token_data["access_token"])
        apply_token_data_to_config(config, token_data, user_info)

        if not args.no_write_config:
            save_config(config, args.config_file)
            print(f"授权成功，token 已写入 {args.config_file}")
        else:
            print("授权成功，未写入 config.ini")

        if user_info.get("user_name") or user_info.get("user_open_id"):
            print(f"当前用户: {user_info.get('user_name', '')} ({user_info.get('user_open_id', '')})")

        if args.print_shell:
            print("")
            print(format_shell_exports(token_data))
    except FeishuAuthError as err:
        logging.error(str(err))
        sys.exit(1)
    except KeyboardInterrupt:
        logging.error("登录已取消")
        sys.exit(1)


if __name__ == "__main__":
    main()
