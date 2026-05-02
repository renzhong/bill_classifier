"""按 payee / item_name 把同一 owner 名下的多条记录合并成一条。

逻辑：
- 一些消费会按笔次拆成多条，但语义上属于同一笔（典型：余额宝按日发放
  收益、轨道交通按程结算、同一家店多次小额扫码等）
- 对每条规则（MERGE_PAYEE_INFO 中的一项）：
    - type=regex：用正则去匹配 col 字段（item_name 或 payee）
    - type=match：col 字段精确等于 target
- 同一 owner 名下命中的记录，金额累加到首条上，其他丢弃
- 仅对 category 仍为 UNKNOWN 的记录生效；已分类的不参与合并

输出按 bill_time 升序，给后续依赖排序的 step 用。

举例（同一 owner A）：
- "余额宝-XX收益发放" 1.5 + "余额宝-YY收益发放" 2.5 → 一条 4.0
- 「北京轨道交通路网管理有限公司」3 笔 5/3/2 元 → 一条 10 元
- 不同 owner 的记录不会跨 owner 合并
"""

import logging
import re
from typing import List

from bill_item import BillItem
from category import ExpenseCategory, Lifecycle
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)

# 同一 owner 下，符合规则的多条 item 会被金额合并为 1 条。
MERGE_PAYEE_INFO = [
    {
        "pattern": "^余额宝.*收益发放$",
        "col": "item_name",
        "type": "regex",
    },
    {
        "target": "北京轨道交通路网管理有限公司",
        "col": "payee",
        "type": "match",
    },
    {
        "target": "北京金辉大厦烘焙店",
        "col": "payee",
        "type": "match",
    },
    {
        "pattern": "^高德地图总部-美餐餐厅.*$",
        "col": "payee",
        "type": "regex",
    },
    {
        "pattern": "^.*李邵男$",
        "col": "payee",
        "type": "regex",
    },
]


def _merge_one_rule(items: List[BillItem], rule: dict) -> List[BillItem]:
    col = rule.get("col")
    match_type = rule.get("type")
    if match_type == "regex":
        pattern = rule.get("pattern")
    elif match_type == "match":
        target = rule.get("target")
    else:
        return items

    group_items: dict = {}
    last_items: List[BillItem] = []

    for item in items:
        # 已被前置 step 处理过的 item 不参与合并（双写期：检查任一即可）
        if item.lifecycle != Lifecycle.UNPROCESSED or item.category != ExpenseCategory.UNKNOWN:
            last_items.append(item)
            continue

        if match_type == "regex":
            hit = bool(re.match(pattern, getattr(item, col)))
        else:  # match
            hit = getattr(item, col) == target

        if hit:
            group_items.setdefault(item.owner, []).append(item)
        else:
            last_items.append(item)

    for owner, group in group_items.items():
        if not group:
            continue
        merged = group[0]
        total = merged.amount
        for it in group[1:]:
            total += it.amount
        merged.amount = total
        logger.info(f"{owner} merge items {merged.payee}:{merged.item_name} for {len(group)}")
        last_items.append(merged)

    return last_items


class MergePayee(Step):
    """按 payee/item_name 把同 owner 下的多条记录合并为一条。"""

    name = "merge_payee"

    def __init__(self, rules: List[dict] = None):
        self._rules = rules if rules is not None else MERGE_PAYEE_INFO

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        for rule in self._rules:
            items = _merge_one_rule(items, rule)
        logger.info("after merge payee bill item:{}".format(len(items)))
        items = sorted(items, key=lambda it: it.bill_time)
        return items
