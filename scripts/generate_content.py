#!/usr/bin/env python3
"""
AI手札 — 内容生成器 (Step 1)
基于真实新闻数据调用 MiniMax API 生成结构化分析报告
"""

import json
import os
import sys
import argparse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_config():
    with open(ROOT / "config" / "settings.json", encoding="utf-8") as f:
        return json.load(f)

def load_prompt_template():
    with open(ROOT / "templates" / "daily-report-prompt.md", encoding="utf-8") as f:
        return f.read()

def load_tracking():
    with open(ROOT / "config" / "tracking_sources.json", encoding="utf-8") as f:
        return json.load(f)

def count_existing_reports() -> int:
    data_dir = ROOT / "data" / "daily-workflow"
    if not data_dir.exists():
        return 0
    return sum(1 for d in data_dir.iterdir()
               if d.is_dir() and (d / "report.json").exists())

def build_people_knowledge(tracking: dict) -> str:
    kb = tracking.get("knowledge_base", {})
    lines = []

    sections = [
        ("L1 AI实验室核心人物", kb.get("l1_practitioners", {}).get("ai_lab_leaders", [])),
        ("L1 AI Coding 实践者", kb.get("l1_practitioners", {}).get("ai_coding", [])),
        ("L1 大模型研究者", kb.get("l1_practitioners", {}).get("llm_researchers", [])),
        ("L1 企业AI/Agent", kb.get("l1_practitioners", {}).get("enterprise_ai", [])),
        ("L1 中国AI核心人物", kb.get("l1_practitioners", {}).get("china_ai", [])),
        ("L1 中国AI Coding", kb.get("l1_practitioners", {}).get("china_ai_coding", [])),
        ("L1 AI安全", kb.get("l1_practitioners", {}).get("ai_safety", [])),
        ("L3 战略决策者", kb.get("l3_decision_makers", [])),
    ]

    for title, people in sections:
        if people:
            lines.append(f"### {title}")
            for p in people:
                lines.append(f"- {p}")
            lines.append("")

    return "\n".join(lines)

def attempt_json_repair(text: str):
    """尝试修复被截断的 JSON 响应"""
    import re

    # 确保以 { 开头
    start = text.find('{')
    if start == -1:
        return None
    text = text[start:]

    # 多轮尝试修复
    for attempt in range(10):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            msg = str(e).lower()
            pos = e.pos if hasattr(e, 'pos') else len(text)

            # 截断在字符串中间 — 关闭引号并补全结构
            if "unterminated string" in msg:
                text = text[:pos] + '"'
                continue

            # 缺少逗号或值
            if "expecting ',' delimiter" in msg or "expecting value" in msg:
                # 尝试从截断点往回找到最后一个完整的对象/数组
                text = text[:pos].rstrip().rstrip(',')
                continue

            # 其他情况: 尝试暴力补全括号
            break

    # 暴力补全：计算未关闭的括号
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape = False

    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            open_braces += 1
        elif ch == '}':
            open_braces -= 1
        elif ch == '[':
            open_brackets += 1
        elif ch == ']':
            open_brackets -= 1

    # 如果在字符串中，先关闭它
    if in_string:
        text += '"'

    # 移除末尾不完整的键值对（如 "key": "incomple ）
    # 先尝试去掉最后一个不完整的 item
    text = text.rstrip()
    # 移除末尾悬挂的逗号
    text = re.sub(r',\s*$', '', text)

    # 补全括号
    text += ']' * max(0, open_brackets)
    text += '}' * max(0, open_braces)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 最后手段：逐字符回退找到最后一个可解析的点
    for i in range(len(text), max(0, len(text) - 500), -1):
        snippet = text[:i].rstrip().rstrip(',')
        # 重新计算括号
        ob, osb = 0, 0
        ins = False
        esc = False
        for ch in snippet:
            if esc:
                esc = False
                continue
            if ch == '\\' and ins:
                esc = True
                continue
            if ch == '"':
                ins = not ins
                continue
            if ins:
                continue
            if ch == '{': ob += 1
            elif ch == '}': ob -= 1
            elif ch == '[': osb += 1
            elif ch == ']': osb -= 1

        if ins:
            snippet += '"'
        snippet = re.sub(r',\s*$', '', snippet)
        snippet += ']' * max(0, osb) + '}' * max(0, ob)
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue

    return None


def generate_content(target_date: str, config: dict) -> dict:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        print("MINIMAX_API_KEY 环境变量未设置")
        print("请运行: export MINIMAX_API_KEY=your-key-here")
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print("openai 包未安装，请运行: pip install openai")
        sys.exit(1)

    raw_path = ROOT / "data" / "daily-workflow" / target_date / "raw_news.json"
    if not raw_path.exists():
        print(f"原始新闻数据不存在: {raw_path}")
        print("请先运行: python scripts/collect_news.py")
        sys.exit(1)

    with open(raw_path, encoding="utf-8") as f:
        raw_news = json.load(f)

    tracking = load_tracking()
    people_knowledge = build_people_knowledge(tracking)

    system_prompt = load_prompt_template()
    system_prompt = system_prompt.replace("{PEOPLE_KNOWLEDGE}", people_knowledge)

    client = OpenAI(api_key=api_key, base_url="https://api.minimax.chat/v1")
    day_number = count_existing_reports() + 1

    news_items = raw_news.get("items", [])

    max_input_items = config.get("news_collection", {}).get("max_input_items", 40)
    if len(news_items) > max_input_items:
        print(f"  新闻条目 {len(news_items)} 超过上限 {max_input_items}，截取前 {max_input_items} 条")
        news_items = news_items[:max_input_items]

    news_json = json.dumps(news_items, ensure_ascii=False, indent=2)

    user_message = f"""今天是 {target_date}，这是 AI手札 第 {day_number} 天。

以下是今天采集到的 {len(news_items)} 条真实新闻数据：

{news_json}

请基于以上数据生成今日日报 JSON。严格按照 schema 输出。
只分析提供的数据，不要编造任何不在上述列表中的新闻或 URL。
如果某个板块没有相关新闻，设 has_news: false。
每个板块最多选取3条最重要的新闻，确保输出JSON完整不截断。

输出纯 JSON，不要 markdown code block，不要 <think> 标签。"""

    print(f"正在调用 MiniMax API ({config['model']})...")
    print(f"  输入新闻: {len(news_items)} 条")

    message = client.chat.completions.create(
        model=config["model"],
        max_tokens=16384,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )

    response_text = message.choices[0].message.content
    if response_text is None:
        print("API 返回空内容")
        if hasattr(message.choices[0], 'finish_reason'):
            print(f"  finish_reason: {message.choices[0].finish_reason}")
        sys.exit(1)

    response_text = response_text.strip()

    if "<think>" in response_text:
        think_end = response_text.find("</think>")
        if think_end != -1:
            response_text = response_text[think_end + len("</think>"):].strip()

    if response_text.startswith("```"):
        lines = response_text.split("\n")
        json_lines = []
        inside = False
        for line in lines:
            if line.startswith("```") and not inside:
                inside = True
                continue
            elif line.startswith("```") and inside:
                break
            elif inside:
                json_lines.append(line)
        response_text = "\n".join(json_lines)

    try:
        report = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败，尝试修复截断...")
        report = attempt_json_repair(response_text)
        if report is None:
            print(f"JSON 修复失败: {e}")
            try:
                print(f"原始响应前200字: {response_text[:200]}")
            except UnicodeEncodeError:
                print(f"原始响应前200字(ascii): {response_text[:200].encode('ascii', 'replace').decode()}")
            err_path = ROOT / "data" / "daily-workflow" / target_date / "raw_response.txt"
            err_path.write_text(response_text, encoding="utf-8")
            print(f"完整响应已保存到: {err_path}")
            sys.exit(1)
        print("  JSON 修复成功")

    report["date"] = target_date
    report["day_number"] = day_number
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    config = load_config()
    report = generate_content(args.date, config)

    output_dir = ROOT / "data" / "daily-workflow" / args.date
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "report.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"日报 JSON 已保存: {output_path}")
    print(f"   标题: {report.get('title', 'N/A')}")
    print(f"   标签: {', '.join(report.get('tags', []))}")
    boards = report.get("boards", [])
    active = sum(1 for b in boards if b.get("has_news"))
    print(f"   板块: {active}/{len(boards)} 有新闻")

if __name__ == "__main__":
    main()
