"""对外保留的入口；真正的实现已拆到 classifiers/ 与 pipeline.py。"""

from pipeline import run_pipeline


def bill_strategy(bill_item_list, bill_config):
    items = run_pipeline(bill_item_list, bill_config)
    return True, items
