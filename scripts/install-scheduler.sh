#!/bin/bash
# AI手札 — Linux/macOS 定时任务安装
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="$(which python3)"
ORCHESTRATOR="$SCRIPT_DIR/orchestrator.py"

echo "===================================="
echo " AI手札 - 安装每日定时任务"
echo "===================================="
echo "项目目录: $PROJECT_DIR"
echo "Python: $PYTHON"

CRON_CMD="0 8 * * * cd $PROJECT_DIR && $PYTHON $ORCHESTRATOR >> $PROJECT_DIR/data/cron.log 2>&1"

if crontab -l 2>/dev/null | grep -q "orchestrator.py"; then
    echo "已存在 crontab 条目，更新中..."
    crontab -l 2>/dev/null | grep -v "orchestrator.py" | { cat; echo "$CRON_CMD"; } | crontab -
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
fi

echo ""
echo "定时任务创建成功!"
echo "   执行时间: 每天 08:00"
echo "   日志文件: $PROJECT_DIR/data/cron.log"
echo ""
echo "管理命令:"
echo "   查看: crontab -l"
echo "   手动运行: cd $PROJECT_DIR && python3 scripts/orchestrator.py"
