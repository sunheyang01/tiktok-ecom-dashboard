#!/bin/bash
# MCN爬虫每日定时任务：抓取EU数据 → 同步到飞书多维表格
# macOS launchd 每天早上9点执行

set -e

LOG_DIR="$HOME/Desktop/电商数据分析/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/mcn_sync_$(date '+%Y%m%d').log"

echo "[$(date)] ===== MCN同步任务开始 =====" >> "$LOG_FILE"

# 1. 运行MCN爬虫（抓取昨天的数据）
MCN_DIR="$HOME/Desktop/tiktok-mcn-scraper"
if [ -d "$MCN_DIR" ]; then
    echo "[$(date)] 运行MCN爬虫..." >> "$LOG_FILE"
    cd "$MCN_DIR"
    python3 scripts/run_scheduler.py --mode daily >> "$LOG_FILE" 2>&1 || {
        echo "[$(date)] 爬虫运行失败，继续同步已有数据" >> "$LOG_FILE"
    }
else
    echo "[$(date)] 爬虫目录不存在: $MCN_DIR，跳过抓取" >> "$LOG_FILE"
fi

# 2. 同步爬虫数据到飞书多维表格
SYNC_DIR="$HOME/Desktop/电商数据分析/scripts"
echo "[$(date)] 同步数据到飞书..." >> "$LOG_FILE"
cd "$SYNC_DIR"
python3 sync_mcn.py 3 >> "$LOG_FILE" 2>&1

echo "[$(date)] ===== MCN同步任务完成 =====" >> "$LOG_FILE"
