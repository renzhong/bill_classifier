"""单向相邻推断：美团账单链 + 非美团锚点。

用户场景（买券 + 用券 + 补餐费）：
- 在饭店结账时先买 1 张或多张美团结账券（payee=美团 / 美团平台商户）
- 买券操作通常在 5 分钟内连续完成
- 最后用券 + 微信/支付宝补差额支付剩余餐费（非美团 payee，餐厅名）

逻辑：
- 触发：UNKNOWN item，payee in {"美团", "美团平台商户"}
- 链式扩展：从触发条目开始，每步取下一条紧邻账单（按 bill_time 升序）
    - 紧邻账单仍是美团 + UNPROCESSED → 加入链，把 cursor 重置到这条美团；
      新窗口为 (cursor_time, cursor_time + 5min]，继续扩展
    - 紧邻账单非美团 → 这条是锚点候选，停止扩展
    - 紧邻账单超出 cursor + 5min → 链失败，无锚点
- 命中：链中所有美团 item 的 category = 锚点 category，classify_alg = FOLLOW，
  共享 group_id（基于锚点 order_id 或 bill_time），便于输出层紧邻显示

前置：items 已按 bill_time 升序（pipeline 中 merge_payee / merge_refund 都做过排序）。
实施位置：在 exact_match / regex_match / wet_market 之后、gpt 之前。

举例（W=5min）：
- M0@12:00, A@12:03 (MATCH 餐饮) → group [M0, A]
- M0@12:00, M1@12:01, A@12:04 (MATCH) → group [M0, M1, A]
- M0@12:00, M1@12:03, A@12:07 (MATCH) → group [M0, M1, A]
  （A 不在 M0 原始 5min 窗口内，但通过 M1 的窗口 12:03-12:08 可达）
- M0@12:00（5min 内无任何账单）→ 链失败，M0 留 UNPROCESSED
"""

import logging
from typing import List

from bill_item import BillItem
from category import ClassifyAlg, Lifecycle
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


WINDOW_SECONDS = 300  # 5 分钟
TRIGGER_PAYEES = ("美团", "美团平台商户")


class NeighborInference(Step):
    """美团账单链 + 5min 内非美团锚点 → 整组承袭锚点 category。"""

    name = "neighbor_inference"

    def __init__(self, window_seconds: int = WINDOW_SECONDS):
        self._window = window_seconds

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        if not items:
            return items

        n = len(items)
        marked_count = 0
        i = 0
        while i < n:
            item = items[i]
            if item.lifecycle != Lifecycle.UNPROCESSED:
                i += 1
                continue
            if item.payee not in TRIGGER_PAYEES:
                i += 1
                continue

            chain = [i]
            cursor_idx = i
            anchor_idx = None

            while True:
                cursor_time = items[cursor_idx].bill_time
                next_idx = cursor_idx + 1
                if next_idx >= n or items[next_idx].bill_time > cursor_time + self._window:
                    break  # 窗口内无下一条，链失败

                next_item = items[next_idx]
                if (
                    next_item.payee in TRIGGER_PAYEES
                    and next_item.lifecycle == Lifecycle.UNPROCESSED
                ):
                    chain.append(next_idx)
                    cursor_idx = next_idx
                    continue

                # 第一条非美团 / 已分类美团 → 锚点候选
                anchor_idx = next_idx
                break

            if anchor_idx is None:
                i += 1
                continue

            anchor_item = items[anchor_idx]
            group_id = (
                f"nbr:{anchor_item.order_id}"
                if anchor_item.order_id
                else f"nbr:t{int(anchor_item.bill_time)}"
            )
            for ci in chain:
                c = items[ci]
                # 仅作"跟随锚点"的标记：写 category / FOLLOW / group_id，
                # lifecycle 保持原状（UNPROCESSED）。下游消费时不要依赖
                # lifecycle == CLASSIFIED 来判断这类条目。
                c.category = anchor_item.category
                c.classify_alg = ClassifyAlg.FOLLOW
                c.group_id = group_id
                marked_count += 1
            anchor_item.group_id = group_id

            i = anchor_idx + 1  # 跳过已成组的所有 item

        logger.debug("neighbor_inference 标记 item size:{}".format(marked_count))
        return items
