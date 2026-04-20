#!/usr/bin/env python3
"""
AI手札 — 内容生成器 (Step 1)
基于真实新闻数据调用 MiniMax API 生成结构化分析报告
"""

import json
import os
import re
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

def score_news_item(item: dict) -> float:
    """
    为新闻计算优先级分数，确保重要新闻不会因截断而丢失。
    分数越高越优先。
    """
    score = 0.0
    source = item.get("source", "")
    title = item.get("title", "")
    summary = item.get("summary", "")

    # ---- 1. 来源权重 (0-30分) ----
    # L1: AI 实验室官方博客 — 最高优先级
    ai_lab_sources = ["OpenAI", "Anthropic", "Google AI", "DeepMind", "Meta AI"]
    for lab in ai_lab_sources:
        if lab.lower() in source.lower():
            score += 30
            break
    else:
        # L2: 开发者工具官方博客
        dev_sources = ["Cursor", "LangChain", "Hugging Face"]
        for dev in dev_sources:
            if dev.lower() in source.lower():
                score += 22
                break
        else:
            # L3: 主流科技媒体
            media_sources = ["TechCrunch", "The Verge", "IEEE", "Simon Willison"]
            for media in media_sources:
                if media.lower() in source.lower():
                    score += 18
                    break
            else:
                # L4: 中文科技媒体
                cn_sources = ["jiqizhixin", "机器之心", "qbitai", "量子位", "36kr", "36氪"]
                for cn in cn_sources:
                    if cn.lower() in source.lower():
                        score += 15
                        break
                else:
                    # L5: Hacker News / GitHub / ArXiv
                    if "Hacker News" in source:
                        score += 12
                    elif "GitHub" in source:
                        score += 10
                    elif "ArXiv" in source or "arxiv" in source:
                        score += 8
                    else:
                        score += 5

    # ---- 2. HN 热度分数 (0-25分) ----
    # 从标题中提取 (251pts) 或 summary 中提取 "HN热度: 251分"
    pts_match = re.search(r'\((\d+)pts?\)', title)
    if not pts_match:
        pts_match = re.search(r'HN热度:\s*(\d+)分', summary)
    if pts_match:
        hn_points = int(pts_match.group(1))
        # 50分起步(min_points)，500+ 封顶
        score += min(25, hn_points / 20)

    # ---- 3. 关键词加权 (0-15分) ----
    high_impact_keywords = [
        # 重大产品发布
        "launch", "released", "发布", "推出", "上线",
        # 融资/IPO
        "IPO", "融资", "估值", "acquisition", "收购",
        # 重大模型
        "GPT", "Claude", "Gemini", "Llama",
        # 行业事件
        "breakthrough", "突破", "首次", "首个", "first",
    ]
    title_lower = (title + " " + summary).lower()
    keyword_hits = sum(1 for kw in high_impact_keywords if kw.lower() in title_lower)
    score += min(15, keyword_hits * 5)

    # ---- 4. 板块覆盖 hint (0-5分) ----
    # 有明确板块标注的新闻更有用
    board_hints = item.get("board_hints", [])
    if board_hints:
        score += min(5, len(board_hints) * 2.5)

    return score


def prioritize_news(news_items: list, max_items: int) -> list:
    """
    智能排序并截取新闻列表：
    1. 按优先级分数排序
    2. 确保来源多样性（同一来源最多占 40%）
    3. 确保板块覆盖（每个板块至少保留一定比例）
    """
    if len(news_items) <= max_items:
        return news_items

    # 计算每条新闻的分数
    scored = [(score_news_item(item), i, item) for i, item in enumerate(news_items)]
    scored.sort(key=lambda x: (-x[0], x[1]))  # 分数降序，同分保持原顺序

    # 第一轮：按分数取 top items，但限制单一来源占比
    selected = []
    source_counts = {}
    max_per_source = max(3, int(max_items * 0.4))  # 单一来源最多占 40%

    # 按板块统计需求
    board_selected = {}

    for score_val, idx, item in scored:
        if len(selected) >= max_items:
            break

        source_key = item.get("source", "unknown").split("(")[0].strip()
        current_count = source_counts.get(source_key, 0)

        if current_count >= max_per_source:
            continue  # 该来源已满，跳过

        selected.append(item)
        source_counts[source_key] = current_count + 1

        for hint in item.get("board_hints", []):
            board_selected[hint] = board_selected.get(hint, 0) + 1

    # 如果还没选满（因为来源限制跳过了一些），从剩余中补充
    if len(selected) < max_items:
        selected_set = set(id(item) for item in selected)
        for score_val, idx, item in scored:
            if len(selected) >= max_items:
                break
            if id(item) not in selected_set:
                selected.append(item)

    return selected


def attempt_json_repair(text: str):
    """尝试修复被截断的 JSON 响应"""

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

    news_items = raw_news.get("items", [])

    max_input_items = config.get("news_collection", {}).get("max_input_items", 40)
    if len(news_items) > max_input_items:
        print(f"  新闻条目 {len(news_items)} 超过上限 {max_input_items}，按优先级筛选")
        news_items = prioritize_news(news_items, max_input_items)
        print(f"  筛选后保留 {len(news_items)} 条（已按重要性排序）")

    news_json = json.dumps(news_items, ensure_ascii=False, indent=2)

    user_message = f"""今天是 {target_date}。

以下是今天采集到的 {len(news_items)} 条真实新闻数据：

{news_json}

请基于以上数据生成今日日报 JSON。严格按照 schema 输出。
只分析提供的数据，不要编造任何不在上述列表中的新闻或 URL。
如果某个板块没有相关新闻，设 has_news: false。
每个板块最多选取2条最重要的新闻，body 控制在100字以内。
务必确保输出的 JSON 完整，不要被截断。宁可内容简短也不要 JSON 不完整。

输出纯 JSON，不要 markdown code block，不要 <think> 标签。"""

    print(f"正在调用 MiniMax API ({config['model']})...")
    print(f"  输入新闻: {len(news_items)} 条")

    max_api_retries = 12  # 最多重试12次，每次等10分钟，共2小时
    for api_attempt in range(1, max_api_retries + 1):
        try:
            message = client.chat.completions.create(
                model=config["model"],
                max_tokens=128000,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            )
            break
        except Exception as e:
            err_msg = str(e)
            is_overloaded = "529" in err_msg or "overloaded" in err_msg.lower()
            if is_overloaded and api_attempt < max_api_retries:
                wait_min = 10
                print(f"  API 过载 (529)，第 {api_attempt}/{max_api_retries} 次重试，等待 {wait_min} 分钟...")
                import time
                time.sleep(wait_min * 60)
                continue
            else:
                print(f"  API 调用失败: {e}")
                if api_attempt >= max_api_retries:
                    print("  已达最大重试次数，放弃")
                sys.exit(1)

    response_text = message.choices[0].message.content
    finish_reason = getattr(message.choices[0], 'finish_reason', None)

    if finish_reason == 'length':
        print(f"  警告: 模型输出被截断 (finish_reason=length)，尝试减少输入重新生成...")
        reduced_items = news_items[:len(news_items) // 2]
        reduced_json = json.dumps(reduced_items, ensure_ascii=False, indent=2)
        reduced_msg = f"""今天是 {target_date}。

以下是今天采集到的 {len(reduced_items)} 条真实新闻数据：

{reduced_json}

请基于以上数据生成今日日报 JSON。严格按照 schema 输出。
只分析提供的数据，不要编造任何不在上述列表中的新闻或 URL。
如果某个板块没有相关新闻，设 has_news: false。
每个板块最多选取2条最重要的新闻，确保输出JSON完整不截断。

输出纯 JSON，不要 markdown code block，不要 <think> 标签。"""

        print(f"  减少到 {len(reduced_items)} 条重试...")
        for api_attempt in range(1, max_api_retries + 1):
            try:
                message = client.chat.completions.create(
                    model=config["model"],
                    max_tokens=128000,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": reduced_msg}
                    ]
                )
                break
            except Exception as e:
                err_msg = str(e)
                is_overloaded = "529" in err_msg or "overloaded" in err_msg.lower()
                if is_overloaded and api_attempt < max_api_retries:
                    wait_min = 10
                    print(f"  API 过载 (529)，第 {api_attempt}/{max_api_retries} 次重试，等待 {wait_min} 分钟...")
                    import time
                    time.sleep(wait_min * 60)
                    continue
                else:
                    print(f"  API 调用失败: {e}")
                    sys.exit(1)
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
