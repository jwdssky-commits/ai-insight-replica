#!/usr/bin/env python3
"""
AI手札 — HTML 渲染器 (Step 3)
将 JSON 日报转为 Hand-Drawn 风格 HTML 片段
保持手绘风格，支持五大板块 + 可点击来源链接
"""

import json
import sys
import html
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BOARD_STYLES = {
    "大模型": {"emoji": "🧠", "color": "green", "bg": "#e8f5e9"},
    "AI Coding": {"emoji": "💻", "color": "blue", "bg": "#e3f2fd"},
    "AI应用": {"emoji": "🚀", "color": "pink", "bg": "#fce4ec"},
    "AI行业": {"emoji": "📊", "color": "yellow", "bg": "#fff9c4"},
    "企业AI转型": {"emoji": "🏢", "color": "orange", "bg": "#fff3e0"},
}

IMPORTANCE_BADGE = {
    "high": "🔥 重要",
    "medium": "📰 新闻",
    "low": "📝 速览",
}


def render_daily_card(report: dict) -> str:
    date_str = html.escape(report["date"])
    day_number = report.get("day_number", "?")
    title = html.escape(report["title"])
    summary = html.escape(report["summary"])
    tags = report.get("tags", [])

    tag_class_map = {
        "大模型": "green", "AI Coding": "blue", "AI应用": "pink",
        "AI行业": "yellow", "企业AI转型": "orange",
        "模型发布": "green", "产品发布": "blue", "融资": "yellow",
        "开源": "green", "安全": "red", "评测": "blue",
        "Agent": "blue", "芯片": "orange", "机器人": "orange", "热点": "hot",
    }

    tags_html = ""
    for tag in tags:
        cls = tag_class_map.get(tag, "")
        prefix = "🔥 " if tag == "热点" else ""
        tags_html += f'<span class="tag {cls}">{prefix}{html.escape(tag)}</span>\n'

    return f"""
                <a class="daily-card" href="daily-{date_str}.html">
                    <div class="tape"></div>
                    <div class="daily-card-date">✎ {date_str} · 第{day_number}天</div>
                    <h3 class="daily-card-title">{title}</h3>
                    <div class="daily-card-summary">{summary}</div>
                    <div class="daily-card-tags">
                        {tags_html.strip()}
                    </div>
                </a>"""


def render_full_report_page(report: dict) -> str:
    date_str = html.escape(report["date"])
    day_number = report.get("day_number", "?")
    title = html.escape(report["title"])
    boards = report.get("boards", [])
    highlight = report.get("highlight", {})

    # Highlight post-it
    highlight_html = ""
    if highlight.get("title"):
        hl_title = html.escape(highlight["title"])
        hl_body = html.escape(highlight.get("body", ""))
        hl_url = html.escape(highlight.get("source_url", ""))
        link_html = f'<a href="{hl_url}" target="_blank" class="source-link">📎 查看原文</a>' if hl_url else ""
        highlight_html = f'''
    <div class="postit-box pink">
        <div class="postit-title">🔥 今日头条</div>
        <div class="postit-body">
            <p><strong>{hl_title}</strong></p>
            <p>{hl_body}</p>
            {link_html}
        </div>
    </div>'''

    # Board sections
    boards_html = ""
    for board in boards:
        bid = board.get("id", "")
        has_news = board.get("has_news", False)
        items = board.get("items", [])
        style = BOARD_STYLES.get(bid, {"emoji": "📋", "color": "green", "bg": "#e8f5e9"})

        if not has_news or not items:
            continue

        # Board header post-it
        boards_html += f'''
    <div class="postit-box {style["color"]}" style="background: {style["bg"]};">
        <div class="postit-title">{style["emoji"]} {html.escape(bid)}</div>
        <div class="postit-body"><p>{len(items)} 条新闻</p></div>
    </div>'''

        # Individual news items
        for item in items:
            headline = html.escape(item.get("headline", ""))
            body = item.get("body", "")
            source_url = html.escape(item.get("source_url", ""))
            source_name = html.escape(item.get("source_name", ""))
            importance = item.get("importance", "medium")
            badge = IMPORTANCE_BADGE.get(importance, "📰 新闻")
            entities = item.get("related_entities", [])

            paragraphs = body.split("\n")
            body_html = "".join(f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip())

            entities_html = ""
            if entities:
                ent_tags = " ".join(f'<span class="entity-tag">{html.escape(e)}</span>' for e in entities[:5])
                entities_html = f'<div class="entity-tags">{ent_tags}</div>'

            title_html = f'<a href="{source_url}" target="_blank" class="news-title-link">{headline}</a>' if source_url else headline

            source_link_html = ""
            if source_url and source_name:
                source_link_html = f'<a href="{source_url}" target="_blank" class="source-link">📎 {source_name}</a>'
            elif source_name:
                source_link_html = f'<span class="source-link">📎 {source_name}</span>'

            boards_html += f'''
        <div class="report-section">
            <div class="report-section-badge">{badge}</div>
            <h3 class="report-section-title">{title_html}</h3>
            <div class="report-section-body">{body_html}</div>
            {entities_html}
            {source_link_html}
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI手札 · {title}</title>
<link href="https://fonts.googleapis.com/css2?family=Kalam:wght@400;700&family=Patrick+Hand&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
<style>
body {{ font-family: 'Patrick Hand', 'Noto Sans SC', cursive; color: #2d2d2d; background-color: #fdfbf7;
  background-image: radial-gradient(#e5e0d8 1px, transparent 1px); background-size: 24px 24px;
  line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 40px 24px; }}
.report-header {{ text-align: center; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 3px dashed #e5e0d8; }}
.report-date {{ font-family: 'Kalam', cursive; color: #ff4d4d; font-size: 0.9rem; }}
.report-title {{ font-family: 'Kalam', cursive; font-size: clamp(1.5rem, 4vw, 2.2rem); font-weight: 700; margin: 8px 0; }}
.report-section {{ background: #fff; border: 2px solid #2d2d2d; border-radius: 12px 185px 12px 185px / 185px 12px 185px 12px;
  padding: 24px; margin-bottom: 20px; box-shadow: 3px 3px 0 0 rgba(45,45,45,0.12); }}
.report-section-badge {{ font-size: 0.8rem; display: inline-block; padding: 2px 10px;
  border: 2px solid #2d2d2d; border-radius: 50px 10px 50px 10px / 10px 50px 10px 50px; margin-bottom: 8px; }}
.report-section-title {{ font-family: 'Kalam', cursive; font-size: 1.2rem; font-weight: 700; margin-bottom: 12px; }}
.report-section-body {{ font-family: 'Noto Sans SC', sans-serif; font-size: 0.92rem; line-height: 1.8; }}
.report-section-body p {{ margin-bottom: 8px; }}
.postit-box {{ padding: 16px 24px; border: 2px solid #2d2d2d; border-radius: 30px 4px 28px 4px / 4px 28px 4px 30px;
  box-shadow: 3px 3px 0 0 rgba(45,45,45,0.12); margin: 20px 0; }}
.postit-box.green {{ background: #e8f5e9; }}
.postit-box.blue {{ background: #e3f2fd; }}
.postit-box.pink {{ background: #fce4ec; }}
.postit-box.yellow {{ background: #fff9c4; }}
.postit-box.orange {{ background: #fff3e0; }}
.postit-title {{ font-family: 'Kalam', cursive; font-weight: 700; margin-bottom: 8px; }}
.postit-body {{ font-family: 'Noto Sans SC', sans-serif; font-size: 0.88rem; line-height: 1.7; }}
.postit-body p {{ margin-bottom: 4px; }}
.source-link {{ font-family: 'Patrick Hand', cursive; font-size: 0.82rem; color: #2d5da1;
  border-bottom: 2px dashed #2d5da1; text-decoration: none; display: inline-block; margin-top: 8px; }}
.source-link:hover {{ text-decoration: line-through; }}
.news-title-link {{ color: #2d5da1; text-decoration: none; border-bottom: 2px dashed #2d5da1; }}
.news-title-link:hover {{ text-decoration: line-through; }}
.entity-tags {{ margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }}
.entity-tag {{ font-family: 'Noto Sans SC', sans-serif; font-size: 0.75rem; padding: 2px 8px;
  border: 1px solid #e5e0d8; border-radius: 50px 10px 50px 10px / 10px 50px 10px 50px; color: #666; background: #fdfbf7; }}
.back-link {{ display: inline-block; margin-top: 24px; font-family: 'Patrick Hand', cursive;
  color: #2d5da1; text-decoration: none; border-bottom: 2px dashed #2d5da1; }}
.back-link:hover {{ text-decoration: line-through; }}
</style>
</head>
<body>
    <div class="report-header">
        <div class="report-date">✎ {date_str} · AI手札第{day_number}天</div>
        <h1 class="report-title">{title}</h1>
    </div>
    {highlight_html}
    {boards_html}
    <a href="index.html" class="back-link">← 返回 AI手札 首页</a>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    report_path = ROOT / "data" / "daily-workflow" / args.date / "report.json"
    if not report_path.exists():
        print(f"报告文件不存在: {report_path}")
        sys.exit(1)

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    # 1. Render daily card snippet
    card_html = render_daily_card(report)
    card_path = ROOT / "data" / "daily-workflow" / args.date / "card.html"
    card_path.write_text(card_html, encoding="utf-8")
    print(f"日报卡片 HTML 已保存: {card_path}")

    # 2. Render full report page
    full_html = render_full_report_page(report)
    page_path = ROOT / "public" / f"daily-{args.date}.html"
    page_path.write_text(full_html, encoding="utf-8")
    print(f"完整日报页面已保存: {page_path}")

if __name__ == "__main__":
    main()
