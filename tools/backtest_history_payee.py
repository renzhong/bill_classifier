"""策略 1 (history_payee) 回测脚本。

跑法：
    /Users/caowx/github/bill_classifier/venv/bin/python3 \
        tools/backtest_history_payee.py \
        --config_file /Users/caowx/github/bill_classifier/config/zc.ini

输出：
    - stdout: 报告表（markdown）
    - tools/backtest_results/report.md
    - tools/backtest_results/mismatch_<month>_<mode>_<threshold>.csv：命中但分类错的条目

回测设计（已与用户对齐 PRD）：
    测试月: 2025-07 ~ 2025-12（共 6 个月）
    mode:
        fixed_6m   - 用测试月之前的 6 个月作 history
        cumulative - 用 2024-01 到测试月之前的所有月份作 history
    阈值组合: (count>=K, ratio>=R)，跑 4 组对比
    指标:
        coverage    = 命中数 / 当月评测目标数
        precision   = 命中且与实际一致 / 命中数
        coverage_wt / precision_wt - 微信转账子集（最关心场景）

约束（从 PRD 派生）：
    - history_map 构建时仅纳入 bill_type='支出' 且 category∈真实分类 的条目
    - 当月评测目标也限定 bill_type='支出' 且 category∈真实分类
    - payee 完全相等匹配
    - owner 默认不分组（main 跑两份对比，分组的报告附加）
"""

import argparse
import configparser
import csv
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# bill_classifier/ 加入 path 才能导入 loader 和 auth
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "bill_classifier"))

from feishu_auth import get_valid_user_access_token  # noqa: E402
from feishu_history_loader import FeishuHistoryLoader, HistoryItem  # noqa: E402


logger = logging.getLogger(__name__)


REAL_CATEGORIES = {
    "水电物业", "餐饮", "买菜", "交通", "日常开支", "服装鞋帽", "护肤品",
    "人情往来", "休闲娱乐", "公司", "家庭建设", "医疗", "养车", "育儿",
}


THRESHOLDS = [
    {"name": "c2_r80", "min_count": 2, "min_ratio": 0.80},
    {"name": "c3_r80", "min_count": 3, "min_ratio": 0.80},
    {"name": "c3_r90", "min_count": 3, "min_ratio": 0.90},
    {"name": "c5_r80", "min_count": 5, "min_ratio": 0.80},
]


MODES = ["fixed_6m", "cumulative"]

TEST_MONTHS: List[Tuple[int, int]] = [(2025, m) for m in range(7, 13)]


@dataclass
class HistoryEntry:
    dominant_category: str
    total_count: int
    dominant_count: int
    dominant_ratio: float


def is_wechat_transfer(item: HistoryItem) -> bool:
    """识别微信转账场景（用户最关心的子集）。"""
    if item.bill_source != "wechat":
        return False
    return "转账" in (item.item_name or "")


def build_history_map(items: List[HistoryItem],
                      min_count: int,
                      min_ratio: float,
                      group_by_owner: bool = False) -> Dict:
    """从 history items 构建 payee -> HistoryEntry 映射。

    group_by_owner=True 时返回 (payee, owner) -> HistoryEntry
    仅纳入 bill_type='支出' 且 category∈REAL_CATEGORIES 的条目
    阈值过滤后返回
    """
    counter: Dict = defaultdict(Counter)
    for it in items:
        if it.bill_type != "支出":
            continue
        if it.category not in REAL_CATEGORIES:
            continue
        if not it.payee:
            continue
        key = (it.payee, it.owner) if group_by_owner else it.payee
        counter[key][it.category] += 1

    result: Dict = {}
    for key, cat_counts in counter.items():
        total = sum(cat_counts.values())
        if total < min_count:
            continue
        dom_cat, dom_count = cat_counts.most_common(1)[0]
        ratio = dom_count / total if total else 0.0
        if ratio < min_ratio:
            continue
        result[key] = HistoryEntry(
            dominant_category=dom_cat,
            total_count=total,
            dominant_count=dom_count,
            dominant_ratio=ratio,
        )
    return result


def filter_test_targets(items: List[HistoryItem]) -> List[HistoryItem]:
    """当月评测目标：支出 + 真实分类。"""
    return [
        it for it in items
        if it.bill_type == "支出" and it.category in REAL_CATEGORIES
    ]


def evaluate_one(history_map: Dict,
                 targets: List[HistoryItem],
                 group_by_owner: bool) -> Tuple[Dict, List[Dict]]:
    """对当月评测对象算 coverage / precision；返回指标 + 错配明细。"""
    hit_total = hit_correct = 0
    wt_total = wt_hit = wt_correct = 0
    mismatches: List[Dict] = []

    for it in targets:
        in_wt = is_wechat_transfer(it)
        if in_wt:
            wt_total += 1
        key = (it.payee, it.owner) if group_by_owner else it.payee
        entry = history_map.get(key)
        if entry is None:
            continue
        hit_total += 1
        if in_wt:
            wt_hit += 1
        if entry.dominant_category == it.category:
            hit_correct += 1
            if in_wt:
                wt_correct += 1
        else:
            mismatches.append({
                "payee": it.payee,
                "owner": it.owner,
                "amount": it.amount,
                "item_name": it.item_name,
                "bill_time": it.bill_time,
                "bill_source": it.bill_source,
                "predicted": entry.dominant_category,
                "actual": it.category,
                "history_total": entry.total_count,
                "history_dominant_count": entry.dominant_count,
                "history_ratio": round(entry.dominant_ratio, 3),
            })

    metrics = {
        "target_total": len(targets),
        "hit": hit_total,
        "hit_correct": hit_correct,
        "coverage": (hit_total / len(targets)) if targets else 0.0,
        "precision": (hit_correct / hit_total) if hit_total else 0.0,
        "wt_target_total": wt_total,
        "wt_hit": wt_hit,
        "wt_hit_correct": wt_correct,
        "wt_coverage": (wt_hit / wt_total) if wt_total else 0.0,
        "wt_precision": (wt_correct / wt_hit) if wt_hit else 0.0,
    }
    return metrics, mismatches


def build_history_window(loader: FeishuHistoryLoader,
                         test_year: int, test_month: int,
                         mode: str) -> List[HistoryItem]:
    """按 mode 构建截止 (test_year, test_month) 之前的历史月份列表并加载。"""
    months: List[Tuple[int, int]] = []
    if mode == "fixed_6m":
        # 测试月之前的 6 个月
        y, m = test_year, test_month
        for _ in range(6):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            months.append((y, m))
        months.reverse()
    elif mode == "cumulative":
        # 24 年 1 月起到测试月之前
        y, m = 2024, 1
        while (y, m) < (test_year, test_month):
            months.append((y, m))
            m += 1
            if m == 13:
                m = 1
                y += 1
    else:
        raise ValueError(f"unknown mode: {mode}")
    return loader.load_months(months)


def fmt_pct(x: float) -> str:
    return f"{x*100:5.1f}%"


def write_mismatches(out_dir: str, year: int, month: int, mode: str,
                     th_name: str, mismatches: List[Dict],
                     limit: int = 30) -> Optional[str]:
    if not mismatches:
        return None
    fname = f"mismatch_{year}{month:02d}_{mode}_{th_name}.csv"
    path = os.path.join(out_dir, fname)
    fields = ["payee", "owner", "amount", "item_name", "bill_time", "bill_source",
              "predicted", "actual", "history_total", "history_dominant_count", "history_ratio"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in mismatches[:limit]:
            w.writerow(row)
    return path


def render_report(rows: List[Dict], group_by_owner: bool) -> str:
    label = "分 owner" if group_by_owner else "不分 owner"
    lines = [f"## {label}", ""]
    lines.append("| 月份 | mode | 阈值 | 目标数 | 命中 | 正确 | coverage | precision | wt 子集 (cov / prec) |")
    lines.append("|------|------|------|--------|------|------|----------|-----------|----------------------|")
    for r in rows:
        ym = f"{r['year']}-{r['month']:02d}"
        m = r["metrics"]
        wt = f"{fmt_pct(m['wt_coverage'])} / {fmt_pct(m['wt_precision'])} (n={m['wt_target_total']}/{m['wt_hit']})"
        lines.append(
            f"| {ym} | {r['mode']} | {r['threshold']} | "
            f"{m['target_total']} | {m['hit']} | {m['hit_correct']} | "
            f"{fmt_pct(m['coverage'])} | {fmt_pct(m['precision'])} | {wt} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_backtest(token: str, group_by_owner: bool) -> List[Dict]:
    loader = FeishuHistoryLoader(token)
    rows: List[Dict] = []
    out_dir = os.path.join(HERE, "backtest_results")
    os.makedirs(out_dir, exist_ok=True)

    for (year, month) in TEST_MONTHS:
        target_items = loader.load_month(year, month)
        targets = filter_test_targets(target_items)
        logger.info("test month %d-%02d: total=%d targets=%d",
                    year, month, len(target_items), len(targets))

        for mode in MODES:
            history = build_history_window(loader, year, month, mode)
            for th in THRESHOLDS:
                history_map = build_history_map(
                    history, min_count=th["min_count"], min_ratio=th["min_ratio"],
                    group_by_owner=group_by_owner,
                )
                metrics, mismatches = evaluate_one(history_map, targets, group_by_owner)
                # 错配 dump（仅 group_by_owner=False，避免重复 csv）
                if not group_by_owner:
                    write_mismatches(out_dir, year, month, mode, th["name"], mismatches)
                rows.append({
                    "year": year,
                    "month": month,
                    "mode": mode,
                    "threshold": th["name"],
                    "metrics": metrics,
                })
    return rows


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_file", default="/Users/caowx/github/bill_classifier/config/zc.ini")
    parser.add_argument("--refresh_cache", action="store_true",
                        help="忽略本地 cache，强制重新拉飞书")
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config_file)
    token = get_valid_user_access_token(config, args.config_file)

    if args.refresh_cache:
        # 简单实现：删 cache 目录后重跑
        from feishu_history_loader import _default_cache_root
        import shutil
        cache_dir = _default_cache_root()
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            logger.info("已清空 cache: %s", cache_dir)

    print("=== 不分 owner ===", flush=True)
    rows_no_owner = run_backtest(token, group_by_owner=False)
    no_owner_md = render_report(rows_no_owner, group_by_owner=False)
    print(no_owner_md, flush=True)

    print("\n=== 按 owner 分组 ===", flush=True)
    rows_by_owner = run_backtest(token, group_by_owner=True)
    by_owner_md = render_report(rows_by_owner, group_by_owner=True)
    print(by_owner_md, flush=True)

    # 写入报告文件
    out_dir = os.path.join(HERE, "backtest_results")
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# history_payee 回测报告\n\n")
        f.write(no_owner_md)
        f.write("\n\n")
        f.write(by_owner_md)
    print(f"\n报告已写入: {report_path}")
    print(f"错配明细在: {out_dir}/mismatch_*.csv")


if __name__ == "__main__":
    main()
