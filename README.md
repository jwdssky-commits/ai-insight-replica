# AI手札 — Hermes & OpenClaw 深度追踪平台

手绘风格 AI 项目追踪网站，方案C全自动化架构。

## 快速开始

```bash
# 1. 安装依赖
pip install anthropic

# 2. 设置 API Key
export ANTHROPIC_API_KEY=your-key-here

# 3. 手动运行一次
python scripts/orchestrator.py

# 4. 安装定时任务 (每天08:00自动运行)
# Windows:
scripts\install-scheduler.bat
# Linux/macOS:
bash scripts/install-scheduler.sh
```

## 项目结构

```
ai-insight-replica/
├── public/                    # GitHub Pages 部署目录
│   └── index.html            # 主页 (Hand-Drawn 风格 SPA)
├── scripts/
│   ├── orchestrator.py       # 5步编排器 (状态机)
│   ├── generate_content.py   # Step 1: Claude API 内容生成
│   ├── quality_gate.py       # Step 2: 质量门检查
│   ├── render_html.py        # Step 3: JSON → HTML 渲染
│   ├── update_homepage.py    # Step 4: 主页注入 + 日历更新
│   ├── deploy.sh             # Step 5: Git push 部署
│   ├── install-scheduler.bat # Windows 定时任务
│   └── install-scheduler.sh  # Linux/macOS crontab
├── templates/
│   ├── daily-report-prompt.md    # AI 生成提示词
│   └── daily-report-schema.json  # JSON Schema
├── config/
│   └── settings.json         # 全局配置
├── data/
│   ├── daily-workflow/       # 每日数据 (按日期)
│   └── flags/                # 步骤完成标志
└── .github/workflows/
    ├── deploy-pages.yml      # GitHub Pages 部署
    └── daily-update.yml      # 每日自动更新 (cron)
```

## 自动化流水线

```
08:00 触发
  ↓
Step 1: generate_content.py — Claude API 生成日报 JSON
  ↓
Step 2: quality_gate.py — 字段/字数/格式/标签检查
  ↓
Step 3: render_html.py — JSON → HTML 卡片 + 独立页面
  ↓
Step 4: update_homepage.py — 注入卡片、更新日历数据
  ↓
Step 5: deploy.sh — git commit + push → GitHub Pages
```

## 配置

`config/settings.json` 关键字段:
- `anthropic_model`: Claude 模型版本
- `quality_gate`: 质量检查规则
- `deploy.auto_push`: 是否自动推送

GitHub Secret: `ANTHROPIC_API_KEY`
