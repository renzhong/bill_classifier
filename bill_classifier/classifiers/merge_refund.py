"""按 order_id 合并退款条目，金额相抵；零额标 SKIP。

逻辑：
- 同一笔订单可能产生多条 item（淘宝预付款 + 尾款，部分 / 全额退款）
- 按 order_id 分组：
    - 1 条：原样保留
    - 多条：拆成 expense_items（正常支出）和 refund_items
      （bill_type=OTHER 且 item_name 含「退款」）
        - expense_items 累加为净支出，再扣掉 refund_items 总额
        - 净支出为 0 → 标 SKIP
        - 只有 refund_items（找不到原支出）→ 退款条目原样保留
- 无 order_id 的记录直接标 SKIP
  （已知问题：会丢掉微信红包 / 转账等，TODO.md 已记录）

输出按 bill_time 升序。

举例：
- order O1：预付款 10 + 尾款 30 → 一条 40
- order O2：商品 20 - 商品退款 20 → 一条 0，标 SKIP
- order O3：商品 20 - 退款 5 → 一条 15
- 无 order_id 的微信红包 → 标 SKIP
"""

import logging
from typing import List

from bill_item import BillItem, BillType
from category import ExpenseCategory
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)


class MergeRefund(Step):
    """按 order_id 把退款条目与原支出合并：金额相抵，零额标 SKIP。"""

    name = "merge_refund"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        logger.debug("合并退款账单 origin size:{}".format(len(items)))

        order_items: dict = {}
        merged_items: List[BillItem] = []

        for item in items:
            if not item.order_id:
                # 无 order_id 当前直接判 SKIP；TODO.md 已记账后续要修
                item.category = ExpenseCategory.SKIP
                merged_items.append(item)
                logger.debug("退款记录丢失原始账单: {}".format(item))
                continue
            order_items.setdefault(item.order_id, []).append(item)

        for order_id, group in order_items.items():
            if len(group) == 1:
                merged_items.append(group[0])
                continue

            expense_items: List[BillItem] = []
            refund_items: List[BillItem] = []
            for item in group:
                if item.bill_type == BillType.OTHER and '退款' in item.item_name:
                    refund_items.append(item)
                else:
                    expense_items.append(item)

            if not expense_items:
                merged_items.extend(refund_items)
                continue

            # 多条 expense（如淘宝预付款 + 尾款）先累加，再扣退款
            merged = expense_items[0]
            debug_str = str(merged.amount)
            for it in expense_items[1:]:
                merged.amount += it.amount
                debug_str += " + " + str(it.amount)
            for it in refund_items:
                merged.amount -= it.amount
                debug_str += " - " + str(it.amount)

            if merged.amount == 0.0:
                merged.category = ExpenseCategory.SKIP

            merged_items.append(merged)
            logger.debug(
                "合并退款账单项: {} {} {} = {}".format(
                    merged.order_id, merged.item_name, debug_str, merged.amount
                )
            )

        merged_items = sorted(merged_items, key=lambda it: it.bill_time)
        logger.info("after merge refund bill item:{}".format(len(merged_items)))
        return merged_items
