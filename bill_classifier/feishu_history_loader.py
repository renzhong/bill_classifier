"""拉取飞书"账单明细 YYYYMM" sheet 的历史数据，带本地 csv cache。

被策略 1 (history_payee) 与策略 3 (cross_month_unified) 共享。

Sheet 列结构（A~K，无表头，第 1 行即数据）：
    A 金额(number) | B 分类 | C payee | D item_name | E 账单类型 | F 时间(string) |
    G 来源 | H 账单人 | I 分类算法 | J 日常·额外(常空) | K 新加列(常空)

23 年表 I 列可能为空（老数据未记录分类算法），其它列保持一致。
"""

import csv
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Iterator, List, Optional

import requests

from feishu import FeishuSheetAPI

logger = logging.getLogger(__name__)


# 飞书 sheet token 不是私密密钥（共享 URL 即可见），加 pragma 跳过 detect-secrets
YEAR_SHEET_TOKEN = {
    2023: "shtcnsqbKMuExxV1Eryr2fAS8hh",  # pragma: allowlist secret
    2024: "N63SsTTpMhbKgDteGYjcEmu2nDb",  # pragma: allowlist secret
    2025: "NQ6hsZttrh4hU3tNDcRc7Aqsnsd",  # pragma: allowlist secret
    2026: "OjoKwUtrPi5uqgkxgbfccYHWn5f",  # pragma: allowlist secret
}


def _default_cache_root() -> str:
    """默认 cache 根目录：worktree 根下 .cache/bill_classifier/history。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get(
        "BILL_CLASSIFIER_CACHE_ROOT",
        os.path.join(here, "..", ".cache", "bill_classifier", "history"),
    )


@dataclass
class HistoryItem:
    """飞书账单明细 sheet 的一行。amount/bill_time 都用原始字符串/数字保留。"""

    amount: float
    category: str
    payee: str
    item_name: str
    bill_type: str  # 支出 / 收入 / 不计支出
    bill_time: str  # YYYY-MM-DD HH:MM:SS
    bill_source: str  # alipay / wechat
    owner: str  # zrz / cwx
    classify_alg: Optional[str] = None  # 完全匹配/模糊匹配/菜场模式/GPT模式/无法识别


def _coerce_amount(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_to_item(row: list) -> Optional[HistoryItem]:
    """把一行转成 HistoryItem；列不齐 / 解析失败返回 None。"""
    if not row:
        return None

    # 列右侧不齐时 pad 成至少 9 列
    cells = list(row) + [None] * max(0, 9 - len(row))

    amount = _coerce_amount(cells[0])
    if amount is None:
        return None
    category = (cells[1] or "").strip() if isinstance(cells[1], str) else cells[1]
    payee = (cells[2] or "").strip() if isinstance(cells[2], str) else ""
    item_name = (cells[3] or "").strip() if isinstance(cells[3], str) else ""
    bill_type = (cells[4] or "").strip() if isinstance(cells[4], str) else ""
    bill_time = (cells[5] or "").strip() if isinstance(cells[5], str) else ""
    bill_source = (cells[6] or "").strip() if isinstance(cells[6], str) else ""
    owner = (cells[7] or "").strip() if isinstance(cells[7], str) else ""
    classify_alg = cells[8] if len(cells) > 8 else None
    if isinstance(classify_alg, str):
        classify_alg = classify_alg.strip() or None

    return HistoryItem(
        amount=amount,
        category=category if isinstance(category, str) else "",
        payee=payee,
        item_name=item_name,
        bill_type=bill_type,
        bill_time=bill_time,
        bill_source=bill_source,
        owner=owner,
        classify_alg=classify_alg,
    )


class FeishuHistoryLoader:
    """加载某个月的"账单明细 YYYYMM" sheet。

    懒加载 + 本地 csv cache：第一次调 feishu API，后续从 cache 读。
    """

    SHEET_NAME_FMT = "账单明细 {year}{month:02d}"

    def __init__(self, user_access_token: str, cache_root: Optional[str] = None,
                 sheet_token_map: Optional[dict] = None):
        self.user_access_token = user_access_token
        self.cache_root = os.path.abspath(cache_root or _default_cache_root())
        self.sheet_token_map = sheet_token_map or YEAR_SHEET_TOKEN
        # 同一 sheet_token 的 sheet_info 缓存到内存
        self._sheet_info_mem: dict = {}

    def cache_path(self, year: int, month: int) -> str:
        return os.path.join(self.cache_root, f"{year}", f"{month:02d}.csv")

    def load_month(self, year: int, month: int, refresh: bool = False) -> List[HistoryItem]:
        """读某年某月的"账单明细 YYYYMM"。先 cache，未命中或 refresh=True 才打飞书。"""
        path = self.cache_path(year, month)
        if not refresh and os.path.exists(path):
            return self._read_cache(path)

        items = self._fetch_from_feishu(year, month)
        if items is None:
            # 飞书读取失败，但如果 cache 还在就降级用 cache
            if os.path.exists(path):
                logger.warning("年月 %d-%02d 飞书拉取失败，降级用 cache", year, month)
                return self._read_cache(path)
            return []

        self._write_cache(path, items)
        return items

    def load_months(self, year_months: List[tuple], refresh: bool = False) -> List[HistoryItem]:
        """批量加载，year_months 是 [(year, month), ...]。"""
        out: List[HistoryItem] = []
        for y, m in year_months:
            out.extend(self.load_month(y, m, refresh=refresh))
        return out

    def _get_sheet_info(self, sheet_token: str) -> dict:
        if sheet_token in self._sheet_info_mem:
            return self._sheet_info_mem[sheet_token]
        api = FeishuSheetAPI(self.user_access_token, sheet_token)
        info = api.GetSheetInfo()
        self._sheet_info_mem[sheet_token] = info
        return info

    def _fetch_from_feishu(self, year: int, month: int) -> Optional[List[HistoryItem]]:
        sheet_token = self.sheet_token_map.get(year)
        if not sheet_token:
            logger.error("年份 %d 没有配对的 sheet_token", year)
            return None

        info = self._get_sheet_info(sheet_token)
        sheet_name = self.SHEET_NAME_FMT.format(year=year, month=month)
        if sheet_name not in info:
            logger.warning("sheet_token=%s 中找不到 sheet '%s'", sheet_token[:8], sheet_name)
            return None

        sheet_id = info[sheet_name]["sheet_id"]
        url = (
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/"
            f"{sheet_token}/values/{sheet_id}!A:I"
        )
        headers = {"Authorization": f"Bearer {self.user_access_token}"}
        params = {"valueRenderOption": "ToString"}
        # 简单重试一次
        for attempt in range(2):
            try:
                r = requests.get(url, headers=headers, params=params, timeout=30)
                if r.status_code != 200:
                    logger.error("fetch %s status=%d body=%s",
                                 sheet_name, r.status_code, r.text[:200])
                    if attempt == 0:
                        time.sleep(0.5)
                        continue
                    return None
                data = r.json()
                if data.get("code") != 0:
                    logger.error("fetch %s code=%s msg=%s", sheet_name, data.get("code"), data.get("msg"))
                    return None
                values = (data.get("data") or {}).get("valueRange", {}).get("values") or []
                items: List[HistoryItem] = []
                for row in values:
                    item = _row_to_item(row)
                    if item is not None:
                        items.append(item)
                logger.info("fetched %s rows=%d items=%d", sheet_name, len(values), len(items))
                return items
            except requests.RequestException:
                logger.exception("fetch %s 网络异常 attempt=%d", sheet_name, attempt)
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return None
        return None

    def _read_cache(self, path: str) -> List[HistoryItem]:
        items: List[HistoryItem] = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    items.append(HistoryItem(
                        amount=float(row["amount"]),
                        category=row.get("category", ""),
                        payee=row.get("payee", ""),
                        item_name=row.get("item_name", ""),
                        bill_type=row.get("bill_type", ""),
                        bill_time=row.get("bill_time", ""),
                        bill_source=row.get("bill_source", ""),
                        owner=row.get("owner", ""),
                        classify_alg=row.get("classify_alg") or None,
                    ))
                except (KeyError, ValueError):
                    logger.warning("cache 行解析失败: %s", row)
        return items

    def _write_cache(self, path: str, items: List[HistoryItem]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "amount", "category", "payee", "item_name", "bill_type",
                    "bill_time", "bill_source", "owner", "classify_alg",
                ],
            )
            writer.writeheader()
            for it in items:
                writer.writerow(asdict(it))


if __name__ == "__main__":
    import argparse
    import configparser
    from feishu_auth import get_valid_user_access_token

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--config_file", default="/Users/caowx/github/bill_classifier/config/zc.ini")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config_file)
    token = get_valid_user_access_token(config, args.config_file)

    loader = FeishuHistoryLoader(token)
    items = loader.load_month(args.year, args.month, refresh=args.refresh)
    print(f"loaded {len(items)} items for {args.year}-{args.month:02d}")
    if items:
        print("first 3:")
        for it in items[:3]:
            print(" ", it)
