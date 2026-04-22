#!/usr/bin/env python3
"""
AI手札 — 每日编排器 (Orchestrator)
5-step state machine: Generate → Validate → Render → Update → Deploy

Usage:
    python scripts/orchestrator.py [--date YYYY-MM-DD] [--step N] [--force]
"""

import json
import os
import sys
import subprocess
import logging
from datetime import datetime, date
from pathlib import Path

# ---- Config ----
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "settings.json"

with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = json.load(f)

DATA_DIR = ROOT / CONFIG["paths"]["data_dir"]
FLAGS_DIR = ROOT / CONFIG["paths"]["flags_dir"]

STEPS = [
    {"id": 0, "name": "collect",   "script": "collect_news.py",     "desc": "新闻采集"},
    {"id": 1, "name": "generate",  "script": "generate_content.py", "desc": "AI 内容分析"},
    {"id": 2, "name": "validate",  "script": "quality_gate.py",     "desc": "质量门检查"},
    {"id": 3, "name": "render",    "script": "render_html.py",      "desc": "JSON → HTML 渲染"},
    {"id": 4, "name": "deploy",    "script": "update_homepage.py",  "desc": "主页更新"},
    {"id": 5, "name": "push",      "script": "deploy.sh",           "desc": "Git 推送部署"},
]

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("orchestrator")

# ---- State Management ----
def get_state_path(target_date: str) -> Path:
    d = DATA_DIR / target_date
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"

def load_state(target_date: str) -> dict:
    p = get_state_path(target_date)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {
        "date": target_date,
        "current_step": 0,
        "steps_completed": [],
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "status": "pending",
        "errors": [],
        "retries": 0
    }

def save_state(target_date: str, state: dict):
    p = get_state_path(target_date)
    with open(p, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

# ---- Flag Management ----
def set_flag(step_id: int, target_date: str):
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)
    flag = FLAGS_DIR / f"step{step_id}-{target_date}.flag"
    flag.write_text(datetime.now().isoformat())

def has_flag(step_id: int, target_date: str) -> bool:
    flag = FLAGS_DIR / f"step{step_id}-{target_date}.flag"
    return flag.exists()

def clear_flags(target_date: str):
    if FLAGS_DIR.exists():
        for f in FLAGS_DIR.glob(f"*-{target_date}.flag"):
            f.unlink()

# ---- Step Execution ----
def run_step(step: dict, target_date: str, state: dict) -> bool:
    step_id = step["id"]
    script = step["script"]
    desc = step["desc"]

    log.info(f"{'='*50}")
    log.info(f"Step {step_id}/5: {desc}")
    log.info(f"{'='*50}")

    if has_flag(step_id, target_date):
        log.info("  已完成（跳过）")
        return True

    script_path = ROOT / "scripts" / script
    if not script_path.exists():
        log.error(f"  脚本不存在: {script_path}")
        state["errors"].append(f"Step {step_id}: script not found: {script}")
        return False

    if script.endswith(".py"):
        cmd = [sys.executable, str(script_path), "--date", target_date]
    elif script.endswith(".sh"):
        cmd = ["bash", str(script_path), target_date]
    else:
        cmd = [str(script_path), target_date]

    step_timeout = 7800 if step["name"] == "generate" else 300

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=step_timeout, cwd=str(ROOT)
        )

        if result.stdout:
            for line in result.stdout.strip().split("\n")[-5:]:
                log.info(f"  > {line}")

        if result.returncode != 0:
            log.error(f"  失败 (exit code {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-3:]:
                    log.error(f"  stderr: {line}")
            state["errors"].append(f"Step {step_id}: exit code {result.returncode}")
            return False

        set_flag(step_id, target_date)
        log.info("  完成")
        return True

    except subprocess.TimeoutExpired:
        log.error(f"  超时 ({step_timeout}s)")
        state["errors"].append(f"Step {step_id}: timeout")
        return False
    except Exception as e:
        log.error(f"  异常: {e}")
        state["errors"].append(f"Step {step_id}: {str(e)}")
        return False

# ---- Main ----
def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI手札 每日编排器")
    parser.add_argument("--date", default=date.today().isoformat(), help="目标日期 YYYY-MM-DD")
    parser.add_argument("--step", type=int, default=0, help="从指定步骤开始 (1-5)")
    parser.add_argument("--force", action="store_true", help="强制重新执行所有步骤")
    args = parser.parse_args()

    target_date = args.date
    log.info(f"AI手札 编排器启动 - {target_date}")
    log.info(f"   根目录: {ROOT}")

    if args.force:
        log.info("   强制模式 - 清除所有 flags")
        clear_flags(target_date)

    state = load_state(target_date)
    state["status"] = "running"
    save_state(target_date, state)

    start_step = args.step

    for step in STEPS:
        if step["id"] < start_step:
            continue

        state["current_step"] = step["id"]
        save_state(target_date, state)

        ok = run_step(step, target_date, state)
        if ok:
            if step["id"] not in state["steps_completed"]:
                state["steps_completed"].append(step["id"])
        else:
            retried = False
            for attempt in range(CONFIG.get("max_retries", 2)):
                log.info(f"  重试 {attempt+1}/{CONFIG['max_retries']}...")
                state["retries"] += 1
                if run_step(step, target_date, state):
                    if step["id"] not in state["steps_completed"]:
                        state["steps_completed"].append(step["id"])
                    retried = True
                    break

            if not retried:
                state["status"] = "failed"
                state["finished_at"] = datetime.now().isoformat()
                save_state(target_date, state)
                log.error(f"编排器失败于 Step {step['id']}")
                sys.exit(1)

    state["status"] = "completed"
    state["finished_at"] = datetime.now().isoformat()
    save_state(target_date, state)
    log.info("编排器完成 - 所有6步通过!")

if __name__ == "__main__":
    main()
