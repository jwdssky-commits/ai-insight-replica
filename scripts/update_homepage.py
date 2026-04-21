#!/usr/bin/env python3
"""
AI手札 — 主页更新器 (Step 4)
更新 index.html: 注入新日报卡片、更新日历数据、更新统计数字
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

def update_homepage(target_date: str):
    index_path = ROOT / "public" / "index.html"
    card_path = ROOT / "data" / "daily-workflow" / target_date / "card.html"

    if not index_path.exists():
        print(f"index.html 不存在: {index_path}")
        sys.exit(1)

    html = index_path.read_text(encoding="utf-8")
    changes = []

    # 1. Remove existing card for same date (prevent duplicates)
    existing_card_pattern = rf'<a class="daily-card" href="daily-{re.escape(target_date)}\.html">.*?</a>'
    old_count = len(re.findall(existing_card_pattern, html, re.DOTALL))
    if old_count > 0:
        html = re.sub(existing_card_pattern, '', html, flags=re.DOTALL)
        changes.append(f"移除 {old_count} 条旧卡片")

    # 2. Inject new daily card at top of daily list
    if card_path.exists():
        card_html = card_path.read_text(encoding="utf-8")
        marker = '<div class="daily-list" id="dailyList">'
        if marker in html:
            html = html.replace(marker, marker + "\n" + card_html, 1)
            changes.append("注入新日报卡片")

    # 2. Update calendar reportsData
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    month_key = dt.strftime("%Y-%m")
    day = dt.day

    pattern = r"(const reportsData = \{)(.*?)(\};)"
    match = re.search(pattern, html, re.DOTALL)
    if match:
        data_block = match.group(2)
        month_pattern = rf"'{month_key}':\s*\[([\d,\s]*)\]"
        month_match = re.search(month_pattern, data_block)

        if month_match:
            existing_days = month_match.group(1)
            days_list = [int(d.strip()) for d in existing_days.split(",") if d.strip()]
            if day not in days_list:
                days_list.append(day)
                days_list.sort()
                new_days = ",".join(str(d) for d in days_list)
                new_month = f"'{month_key}': [{new_days}]"
                old_month = month_match.group(0)
                data_block = data_block.replace(old_month, new_month)
                html = html[:match.start(2)] + data_block + html[match.end(2):]
                changes.append(f"日历更新: {month_key} 添加 {day}日")
        else:
            days_str = str(day)
            new_entry = f"\n    '{month_key}': [{days_str}],"
            data_block = new_entry + data_block
            html = html[:match.start(2)] + data_block + html[match.end(2):]
            changes.append(f"日历新增月份: {month_key}")

    # 3. Update stat numbers
    data_dir = ROOT / "data" / "daily-workflow"
    total_reports = sum(1 for d in data_dir.iterdir()
                       if d.is_dir() and (d / "report.json").exists()) if data_dir.exists() else 0

    stat_pattern = r'(<div class="stat-number green" id="stat-reports">)\d+(</div>)'
    html = re.sub(stat_pattern, rf'\g<1>{total_reports}\2', html)

    days_pattern = r'(<div class="stat-number red" id="stat-days">)\d+(</div>)'
    html = re.sub(days_pattern, rf'\g<1>{total_reports}\2', html)

    changes.append(f"统计更新: {total_reports} 篇日报")

    # 4. Write back
    index_path.write_text(html, encoding="utf-8")
    print("主页更新完成:")
    for c in changes:
        print(f"   - {c}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    update_homepage(args.date)

if __name__ == "__main__":
    main()
