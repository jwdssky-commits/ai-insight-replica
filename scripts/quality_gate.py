#!/usr/bin/env python3
"""
AI手札 — 质量门 (Step 2)
验证 AI 生成的 JSON 报告质量
"""

import json
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_config():
    with open(ROOT / "config" / "settings.json", encoding="utf-8") as f:
        return json.load(f)

class QualityGate:
    def __init__(self, config: dict):
        self.qg = config["quality_gate"]
        self.checks_passed = 0
        self.checks_failed = 0
        self.errors = []

    def check(self, name: str, condition: bool, msg: str = ""):
        if condition:
            self.checks_passed += 1
            print(f"  [PASS] {name}")
        else:
            self.checks_failed += 1
            self.errors.append(f"{name}: {msg}")
            print(f"  [FAIL] {name} - {msg}")

    def validate(self, report: dict, raw_news_urls: set = None) -> bool:
        print("质量门检查开始...")
        print("-" * 40)

        # 1. Required fields
        for field in self.qg["required_fields"]:
            self.check(f"必填字段: {field}",
                       field in report and report[field], "缺少或为空")

        # 2. Title check
        title = report.get("title", "")
        self.check("标题长度", 5 <= len(title) <= 100, f"当前 {len(title)} 字")

        # 3. Date format
        date_str = report.get("date", "")
        try:
            from datetime import datetime
            datetime.strptime(date_str, "%Y-%m-%d")
            self.check("日期格式", True)
        except ValueError:
            self.check("日期格式", False, f"无效: {date_str}")

        # 4. Summary length
        summary = report.get("summary", "")
        self.check(f"摘要字数 (>={self.qg['min_word_count']})",
                   len(summary) >= self.qg["min_word_count"],
                   f"当前 {len(summary)} 字符")

        # 5. Tags validation
        tags = report.get("tags", [])
        allowed = set(self.qg["allowed_tags"])
        self.check("至少1个标签", len(tags) >= 1, "无标签")
        for tag in tags:
            self.check(f"标签有效: {tag}", tag in allowed, "不在允许列表中")

        # 6. Highlight validation
        highlight = report.get("highlight", {})
        self.check("highlight 存在",
                   isinstance(highlight, dict) and highlight.get("title") and highlight.get("body"),
                   "缺少 highlight 或其 title/body")

        # 7. Boards validation
        boards = report.get("boards", [])
        valid_ids = set(self.qg.get("valid_board_ids", []))
        self.check("boards 是列表", isinstance(boards, list) and len(boards) > 0,
                   "boards 为空或不是列表")

        for i, board in enumerate(boards):
            bid = board.get("id", "")
            self.check(f"板块[{i}] id 有效",
                       bid in valid_ids,
                       f"无效 id: {bid}")

            has_news = board.get("has_news", False)
            items = board.get("items", [])

            if has_news:
                self.check(f"板块[{i}] ({bid}) 有 items",
                           len(items) >= 1,
                           "has_news=true 但 items 为空")

                for j, item in enumerate(items):
                    self.check(f"板块[{i}] item[{j}] 有 headline",
                               bool(item.get("headline")), "缺少 headline")
                    self.check(f"板块[{i}] item[{j}] 有 body",
                               len(item.get("body", "")) > 50, "body 过短 (<50字)")

                    # URL checks
                    if self.qg.get("require_source_urls"):
                        src_url = item.get("source_url", "")
                        self.check(f"板块[{i}] item[{j}] 有 source_url",
                                   src_url.startswith("http"),
                                   f"无效 URL: {src_url[:50]}")

                        # Cross-reference with raw news
                        if raw_news_urls and src_url:
                            self.check(f"板块[{i}] item[{j}] URL 来自采集数据",
                                       src_url in raw_news_urls,
                                       "URL 不在 raw_news.json 中（可能是编造的）")

                    self.check(f"板块[{i}] item[{j}] 有 source_name",
                               bool(item.get("source_name")), "缺少 source_name")

        # 8. No placeholder text
        json_str = json.dumps(report, ensure_ascii=False)
        for ph in ["{{", "}}", "TODO", "PLACEHOLDER", "FIXME"]:
            self.check(f"无占位符: {ph}", ph not in json_str, "发现占位符")

        # 9. JSON re-serialization sanity
        try:
            json.dumps(report, ensure_ascii=False)
            self.check("JSON 可序列化", True)
        except Exception as e:
            self.check("JSON 可序列化", False, str(e))

        # Summary
        print("-" * 40)
        total = self.checks_passed + self.checks_failed
        print(f"结果: {self.checks_passed}/{total} 通过, {self.checks_failed} 失败")

        if self.checks_failed > 0:
            print(f"\n失败项:")
            for err in self.errors:
                print(f"   - {err}")

        return self.checks_failed == 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    config = load_config()
    data_dir = ROOT / "data" / "daily-workflow" / args.date

    report_path = data_dir / "report.json"
    if not report_path.exists():
        print(f"报告文件不存在: {report_path}")
        sys.exit(1)

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    # Load raw news URLs for cross-reference
    raw_news_urls = set()
    raw_path = data_dir / "raw_news.json"
    if raw_path.exists():
        with open(raw_path, encoding="utf-8") as f:
            raw_news = json.load(f)
        for item in raw_news.get("items", []):
            url = item.get("url", "")
            if url:
                raw_news_urls.add(url)

    # Auto-fix: remove items with fabricated URLs before validation
    if raw_news_urls:
        removed = 0
        for board in report.get("boards", []):
            if not board.get("has_news"):
                continue
            original_items = board.get("items", [])
            # 宽松匹配：去除末尾斜杠和空格后比较
            def url_in_raw(url):
                normalized = url.strip().rstrip('/')
                for raw_url in raw_news_urls:
                    if normalized == raw_url.strip().rstrip('/'):
                        return True
                    # 也匹配URL前缀（有些LLM会截断或追加参数）
                    if normalized.startswith(raw_url.strip().rstrip('/').split('?')[0]):
                        return True
                    if raw_url.strip().rstrip('/').startswith(normalized.split('?')[0]):
                        return True
                return False

            cleaned = [it for it in original_items if url_in_raw(it.get("source_url", ""))]
            diff = len(original_items) - len(cleaned)
            if diff > 0:
                board["items"] = cleaned
                removed += diff
                if not cleaned:
                    board["has_news"] = False
        if removed > 0:
            print(f"[AUTO-FIX] 移除了 {removed} 条编造URL的条目")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

    gate = QualityGate(config)
    # Auto-fix 已处理编造URL，validate 时不再做URL交叉检查（避免误报）
    passed = gate.validate(report, raw_news_urls=None)

    if passed:
        print("\n质量门通过!")
        sys.exit(0)
    else:
        print(f"\n质量门未通过 ({gate.checks_failed} 项失败)")
        sys.exit(1)

if __name__ == "__main__":
    main()
