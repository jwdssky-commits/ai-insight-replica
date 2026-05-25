#!/usr/bin/env python3
"""
AI手札 — 新闻采集器 (Step 0)
从 RSS/API 采集真实 AI 新闻
零外部依赖：仅使用 Python stdlib
"""

import json
import os
import re
import ssl
import sys
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_config():
    with open(ROOT / "config" / "settings.json", encoding="utf-8") as f:
        return json.load(f)

def load_tracking():
    with open(ROOT / "config" / "tracking_sources.json", encoding="utf-8") as f:
        return json.load(f)

def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "AI-Insight-Bot/1.0 (news aggregator)",
        "Accept": "application/xml, application/rss+xml, application/atom+xml, application/json, text/xml, */*",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---- RSS Collector ----

def parse_rss_date(date_str):
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def make_cutoff(target_date: str, lookback_hours: int) -> datetime:
    """基于目标日期计算 cutoff，确保采集的是前一天的新闻"""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # 日报日期当天的 00:00 UTC 往前推 lookback_hours
    return target_dt - timedelta(hours=lookback_hours)

def make_upper_bound(target_date: str) -> datetime:
    """target_date 当天结束：次日 00:00 UTC，过滤比目标日期还新的新闻"""
    return datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)

def is_out_of_range(pub_date_str: str, cutoff: datetime, upper: datetime) -> bool:
    """判断新闻是否超出采集范围（太旧或太新）"""
    parsed = parse_rss_date(pub_date_str)
    if not parsed:
        return False  # 无日期信息，保留
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < cutoff or parsed >= upper

def collect_rss(feeds, lookback_hours, max_per_source=10, target_date=None):
    items = []
    cutoff = make_cutoff(target_date, lookback_hours) if target_date else datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    upper = make_upper_bound(target_date) if target_date else datetime.now(timezone.utc) + timedelta(hours=1)

    for feed in feeds:
        name = feed["name"]
        url = feed["url"]
        boards = feed.get("boards", [])
        lang = feed.get("lang", "en")

        try:
            xml_text = fetch_url(url)
            root = ET.fromstring(xml_text)
        except Exception as e:
            print(f"  [WARN] RSS 失败 {name}: {e}")
            continue

        feed_items = []

        # RSS 2.0: channel/item
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = item.findtext("pubDate") or item.findtext("dc:date")
            desc = (item.findtext("description") or "").strip()

            if not title or not link:
                continue

            if is_out_of_range(pub_date, cutoff, upper):
                continue

            feed_items.append({
                "title": title,
                "url": link,
                "source": f"{name} (RSS)",
                "published": pub_date or "",
                "summary": desc[:300] if desc else "",
                "board_hints": boards,
                "lang": lang,
            })

        # Atom: entry (with namespace)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            published = entry.findtext("atom:published", namespaces=ns) or entry.findtext("atom:updated", namespaces=ns) or ""
            summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()

            if not title or not link:
                continue

            if is_out_of_range(published, cutoff, upper):
                continue

            feed_items.append({
                "title": title,
                "url": link,
                "source": f"{name} (RSS)",
                "published": published,
                "summary": summary[:300] if summary else "",
                "board_hints": boards,
                "lang": lang,
            })

        # Also try without namespace for Atom feeds
        if not feed_items:
            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                title = (title_el.text or "").strip() if title_el is not None else ""
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href", "") if link_el is not None else ""
                pub_el = entry.find("{http://www.w3.org/2005/Atom}published")
                upd_el = entry.find("{http://www.w3.org/2005/Atom}updated")
                published = ""
                if pub_el is not None and pub_el.text:
                    published = pub_el.text.strip()
                elif upd_el is not None and upd_el.text:
                    published = upd_el.text.strip()
                sum_el = entry.find("{http://www.w3.org/2005/Atom}summary")
                summary = (sum_el.text or "").strip() if sum_el is not None else ""

                if not title or not link:
                    continue

                parsed_date = parse_rss_date(published)
                if parsed_date and parsed_date.tzinfo and (parsed_date < cutoff or parsed_date >= upper):
                    continue

                feed_items.append({
                    "title": title,
                    "url": link,
                    "source": f"{name} (RSS)",
                    "published": published,
                    "summary": summary[:300] if summary else "",
                    "board_hints": boards,
                    "lang": lang,
                })

        items.extend(feed_items[:max_per_source])
        print(f"  [OK] {name}: {len(feed_items[:max_per_source])} 条")
        time.sleep(0.3)

    return items


# ---- Hacker News Collector ----

def collect_hackernews(config, lookback_hours, max_items, target_date=None):
    items = []
    keywords = config.get("keywords", ["AI", "LLM"])
    min_points = config.get("min_points", 50)
    boards = config.get("boards", [])

    if target_date:
        cutoff_ts = int(make_cutoff(target_date, lookback_hours).timestamp())
        upper_ts = int(make_upper_bound(target_date).timestamp())
    else:
        cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp())
        upper_ts = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

    for keyword in keywords[:5]:
        try:
            encoded = urllib.parse.quote(keyword)
            url = f"https://hn.algolia.com/api/v1/search_by_date?query={encoded}&tags=story&numericFilters=points>={min_points},created_at_i>={cutoff_ts},created_at_i<{upper_ts}&hitsPerPage=5"
            data = json.loads(fetch_url(url))

            for hit in data.get("hits", []):
                title = hit.get("title", "")
                story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                points = hit.get("points", 0)
                created = hit.get("created_at", "")

                if not title:
                    continue

                items.append({
                    "title": f"{title} ({points}pts)",
                    "url": story_url,
                    "source": "Hacker News (API)",
                    "published": created,
                    "summary": f"HN热度: {points}分",
                    "board_hints": boards,
                    "lang": "en",
                })

            time.sleep(0.5)
        except Exception as e:
            print(f"  [WARN] HN 搜索 '{keyword}' 失败: {e}")
            continue

    seen_urls = set()
    deduped = []
    for item in items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            deduped.append(item)

    result = deduped[:max_items]
    print(f"  [OK] Hacker News: {len(result)} 条")
    return result


# ---- GitHub Collector ----

def collect_github(repos, lookback_hours, max_items, target_date=None):
    items = []
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"User-Agent": "AI-Insight-Bot/1.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if target_date:
        cutoff = make_cutoff(target_date, lookback_hours)
        upper = make_upper_bound(target_date)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        upper = datetime.now(timezone.utc) + timedelta(hours=1)

    for repo_info in repos[:15]:
        repo = repo_info["repo"]
        boards = repo_info.get("boards", [])

        try:
            url = f"https://api.github.com/repos/{repo}/releases?per_page=3"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                releases = json.loads(resp.read().decode())

            for rel in releases:
                pub = rel.get("published_at", "")
                if is_out_of_range(pub, cutoff, upper):
                        continue

                name = rel.get("name") or rel.get("tag_name", "")
                html_url = rel.get("html_url", "")
                body = (rel.get("body") or "")[:300]

                if not name or not html_url:
                    continue

                items.append({
                    "title": f"[{repo}] {name}",
                    "url": html_url,
                    "source": f"GitHub ({repo})",
                    "published": pub,
                    "summary": body,
                    "board_hints": boards,
                    "lang": "en",
                })

            time.sleep(0.3)
        except Exception as e:
            print(f"  [WARN] GitHub {repo}: {e}")
            continue

    result = items[:max_items]
    print(f"  [OK] GitHub: {len(result)} 条")
    return result


# ---- Sogou WeChat Collector ----

def collect_wechat(accounts, lookback_hours, max_per_account=5, target_date=None):
    """通过搜狗微信搜索采集公众号文章"""
    items = []

    for account in accounts:
        name = account["name"]
        query = account.get("query", name)
        boards = account.get("boards", [])
        lang = account.get("lang", "zh")

        try:
            encoded = urllib.parse.quote(query)
            url = f"https://weixin.sogou.com/weixin?type=2&query={encoded}&ie=utf8"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=15, context=ssl._create_unverified_context()) as resp:
                data = resp.read().decode("utf-8", errors="replace")

            # Extract articles: <h3><a href=...>Title</a></h3>
            articles = re.findall(
                r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>',
                data, re.DOTALL
            )

            feed_items = []
            for i, (link, title_html) in enumerate(articles[:max_per_account]):
                title = re.sub(r"<[^>]+>", "", title_html).strip()
                if not title:
                    continue

                # Resolve sogou redirect URL
                if link.startswith("/"):
                    link = "https://weixin.sogou.com" + link

                feed_items.append({
                    "title": title,
                    "url": link,
                    "source": f"{name} (微信)",
                    "published": "",
                    "summary": f"来源: {name}公众号",
                    "board_hints": boards,
                    "lang": lang,
                })

            items.extend(feed_items)
            print(f"  [OK] {name}: {len(feed_items)} 条")
            time.sleep(1.0)  # Be polite to sogou

        except Exception as e:
            print(f"  [WARN] 微信 {name}: {e}")
            continue

    return items


# ---- Dedup ----

def dedup_items(items):
    seen = set()
    result = []
    for item in items:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            result.append(item)
    return result


# ---- Main ----

def main():
    parser = argparse.ArgumentParser(description="AI手札 新闻采集器")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    config = load_config()
    tracking = load_tracking()
    nc = config.get("news_collection", {})
    lookback = nc.get("lookback_hours", 28)
    max_per = nc.get("max_items_per_source", 10)
    timeout = nc.get("timeout_seconds", 30)

    print(f"新闻采集开始 — {args.date}")
    print(f"  回溯: {lookback}小时, 每源上限: {max_per}")

    all_items = []

    # 1. RSS feeds
    print("\n[RSS 采集]")
    rss_items = collect_rss(tracking.get("rss_feeds", []), lookback, max_per, target_date=args.date)
    all_items.extend(rss_items)

    # 2. Hacker News
    print("\n[Hacker News 采集]")
    hn_items = collect_hackernews(tracking.get("hackernews", {}), lookback, max_per, target_date=args.date)
    all_items.extend(hn_items)

    # 3. GitHub releases
    print("\n[GitHub 采集]")
    gh_items = collect_github(tracking.get("github_repos", []), lookback, max_per, target_date=args.date)
    all_items.extend(gh_items)

    # 4. WeChat public accounts (via Sogou)
    print("\n[微信公众号 采集]")
    wx_items = collect_wechat(tracking.get("wechat_accounts", []), lookback, max_per, target_date=args.date)
    all_items.extend(wx_items)

    # Dedup
    all_items = dedup_items(all_items)

    # Enforce max
    max_total = nc.get("max_total_items", 80)
    if len(all_items) > max_total:
        all_items = all_items[:max_total]

    output = {
        "date": args.date,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "item_count": len(all_items),
        "items": all_items,
    }

    output_dir = ROOT / "data" / "daily-workflow" / args.date
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "raw_news.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n采集完成: {len(all_items)} 条新闻")
    print(f"保存到: {output_path}")

    if len(all_items) < nc.get("min_total_items", 5):
        print(f"[WARN] 采集数量不足 (最低 {nc.get('min_total_items', 5)})")


if __name__ == "__main__":
    main()
