"""美餐餐厅工作日补贴时段过滤。

逻辑：
- payee 匹配 `^高德地图总部-美餐餐厅.*$` 的 item
- 且时间落在工作日（周一~周五）的 18:00~18:59 或 21:00~21:59
- 标记为 SKIP（这是公司餐补 / 加班餐补，不算个人开销）

不命中条件的不变（保持 UNKNOWN，留给后续 step）。

举例：
- 周三 18:30，「高德地图总部-美餐餐厅A区」消费 30 元 → SKIP
- 周三 19:30，同地点 30 元 → 不在窗口，UNKNOWN
- 周六 18:30，同地点 30 元 → 非工作日，UNKNOWN
- 周三 18:30，「星巴克」消费 → payee 不匹配，UNKNOWN
"""

import datetime
import logging
import re
from typing import List

from bill_item import BillItem
from category import Lifecycle, SkipReason
from classifiers.base import Context, Step

logger = logging.getLogger(__name__)

PAYEE_PATTERN = r'^高德地图总部-美餐餐厅.*$'


class MeicanFilter(Step):

    name = "meican_filter"

    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        mark_skip_count = 0
        for item in items:
            if not re.match(PAYEE_PATTERN, item.payee):
                continue

            dt = datetime.datetime.fromtimestamp(item.bill_time)
            is_weekday = dt.weekday() < 5
            is_work_hour = dt.hour == 18 or dt.hour == 21

            if is_weekday and is_work_hour:
                item.lifecycle = Lifecycle.SKIPPED
                item.skip_reason = SkipReason.FILTER
                mark_skip_count += 1

        logger.info("美餐餐厅工作日18点标记为skip的item数量:{}".format(mark_skip_count))
        return items
