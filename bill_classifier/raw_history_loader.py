"""加载历史月份的原始账单 csv 文件，返回 BillItem 列表（含 order_id）。

被策略 3 (cross_month_unified) 使用，用于反查跨月孤儿退款的原支出条目。

为什么用原始 csv 而不是飞书"账单明细"sheet：
    飞书 sheet 没有 order_id 列，无法做支付宝 order_id 核心段反查。
    Dropbox 下原始 csv 一直存在（202304~），路径稳定，复用 bill.py 的解析逻辑。

文件命名约定（与 zc.ini 中 bill1~bill4 一致）：
    /Users/caowx/Library/CloudStorage/Dropbox/账单/<YYYYMM>/<owner>_<source>.csv
    owner ∈ {zrz, cwx}，source ∈ {alipay, wechat}
"""

import logging
import os
from typing import List, Tuple

from bill import AliPayBill, WeChatBill
from bill_file import BillFile
from bill_item import BillItem

logger = logging.getLogger(__name__)


DEFAULT_BILL_ROOT = "/Users/caowx/Library/CloudStorage/Dropbox/账单"
DEFAULT_OWNERS = ("zrz", "cwx")
DEFAULT_SOURCES = ("alipay", "wechat")


class RawHistoryLoader:
    """从 Dropbox 路径下加载指定月份的原始账单 csv，解析为 BillItem 列表。"""

    def __init__(self,
                 bill_root: str = DEFAULT_BILL_ROOT,
                 owners=DEFAULT_OWNERS,
                 sources=DEFAULT_SOURCES):
        self.bill_root = bill_root
        self.owners = tuple(owners)
        self.sources = tuple(sources)

    def load_months(self, year_months: List[Tuple[int, int]]) -> List[BillItem]:
        items: List[BillItem] = []
        for y, m in year_months:
            items.extend(self._load_month(y, m))
        return items

    def _load_month(self, year: int, month: int) -> List[BillItem]:
        month_dir = os.path.join(self.bill_root, f"{year}{month:02d}")
        if not os.path.isdir(month_dir):
            logger.debug("month dir not found: %s", month_dir)
            return []

        items: List[BillItem] = []
        for owner in self.owners:
            for source in self.sources:
                fname = f"{owner}_{source}.csv"
                path = os.path.join(month_dir, fname)
                if not os.path.isfile(path):
                    continue
                try:
                    bill_file = BillFile(path, owner, source)
                    if source == "alipay":
                        bill = AliPayBill(bill_file)
                    else:
                        bill = WeChatBill(bill_file)
                    file_items: List[BillItem] = []
                    bill.parse_from_file(file_items)
                    items.extend(file_items)
                except Exception:
                    logger.exception("加载原始账单失败: %s", path)
        logger.info("raw history %d-%02d: %d items", year, month, len(items))
        return items
