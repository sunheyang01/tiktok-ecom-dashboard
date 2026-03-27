"""数据分析脚本：拉取飞书数据 → 分析 → 生成JSON + 发送报告"""
import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

from feishu_client import FeishuClient

# ===== 配置 =====
APP_TOKEN = "Bkspw46VYiVs1Bkly3hchgRfnFc"  # 多维表格 app_token
TABLE_ID = "tblKWqac7SVi8p8d"
CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "oc_c4c7c8a6c2ebaf0a7f563d15a5327f6f")

# 机器人应用凭证（与数据读取应用分开）
BOT_APP_ID = os.environ.get("FEISHU_BOT_APP_ID", "cli_a94c27d2af38dbb5")
BOT_APP_SECRET = os.environ.get("FEISHU_BOT_APP_SECRET", "KZzghjmQbtdVl2fWoR5febQmBxtaxyQM")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "data")

# 关键指标
METRICS = ["GMV", "佣金", "提现金额", "冻结金额", "电商出单"]

# 历史基线数据 (3.27之前的累计总数)
BASELINE = {
    "电商出单": 1481,
    "GMV": 18750.85,
    "佣金": 3001.07,
    "冻结金额": 173.57,
}


def fetch_data():
    """从飞书拉取数据"""
    client = FeishuClient()
    records = client.list_records(APP_TOKEN, TABLE_ID)
    rows = client.parse_records(records)
    print(f"[分析] 解析得到 {len(rows)} 行数据")
    return rows


def normalize_rows(rows):
    """标准化数据：统一日期格式，数值转换"""
    for row in rows:
        # 日期处理：飞书可能返回时间戳(ms)或字符串
        date_val = row.get("日期", "")
        if isinstance(date_val, (int, float)):
            # 毫秒时间戳
            row["日期"] = datetime.fromtimestamp(date_val / 1000).strftime("%Y-%m-%d")
        elif isinstance(date_val, str) and date_val:
            # 尝试统一格式
            parsed = False
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%m.%d", "%m-%d", "%m/%d"):
                try:
                    dt = datetime.strptime(date_val.strip(), fmt)
                    # 对于没有年份的格式，补当前年份
                    if dt.year == 1900:
                        dt = dt.replace(year=datetime.now().year)
                    row["日期"] = dt.strftime("%Y-%m-%d")
                    parsed = True
                    break
                except ValueError:
                    continue
            if not parsed:
                row["日期"] = ""  # 无法解析的日期置空

        # 数值字段转换
        for m in METRICS:
            val = row.get(m, 0)
            if isinstance(val, str):
                val = val.replace(",", "").replace("¥", "").replace("$", "").strip()
                try:
                    val = float(val) if "." in val else int(val)
                except (ValueError, TypeError):
                    val = 0
            row[m] = val or 0
    return rows


def build_daily_summary(rows):
    """按日期汇总"""
    daily = defaultdict(lambda: defaultdict(float))
    daily_accounts = defaultdict(list)

    for row in rows:
        date = row.get("日期", "")
        if not date:
            continue
        for m in METRICS:
            daily[date][m] += row[m]
        daily_accounts[date].append(row)

    return dict(daily), dict(daily_accounts)


def build_account_summary(rows):
    """按账号汇总"""
    accounts = defaultdict(lambda: {"total": defaultdict(float), "daily": defaultdict(lambda: defaultdict(float))})

    for row in rows:
        acct = row.get("账号", "未知")
        date = row.get("日期", "")
        for m in METRICS:
            accounts[acct]["total"][m] += row[m]
            if date:
                accounts[acct]["daily"][date][m] += row[m]
        # 保留归属人和状态
        accounts[acct]["归属人"] = row.get("归属人", "")
        accounts[acct]["账号状态"] = row.get("账号状态", "")

    return dict(accounts)


def calc_change(current, previous):
    """计算变化率"""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 2)


def generate_report(daily_summary, daily_accounts, account_summary, rows):
    """生成当日分析报告文本"""
    sorted_dates = sorted(daily_summary.keys())
    if not sorted_dates:
        return "暂无数据", []

    today = sorted_dates[-1]
    today_data = daily_summary[today]

    # 日环比
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_data = daily_summary.get(yesterday, {})

    # 周同比
    last_week = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    last_week_data = daily_summary.get(last_week, {})

    lines = []
    lines.append(f"📊 TikTok 电商日报 | {today}")
    lines.append("=" * 40)
    lines.append("")

    # 总览
    lines.append("【今日总览】")
    for m in METRICS:
        val = today_data.get(m, 0)
        if m in ("GMV", "佣金", "提现金额", "冻结金额"):
            lines.append(f"  {m}: ${val:,.2f}")
        else:
            lines.append(f"  {m}: {int(val)}")

    lines.append("")

    # 日环比
    lines.append("【日环比】(vs 昨日)")
    for m in METRICS:
        curr = today_data.get(m, 0)
        prev = yesterday_data.get(m, 0)
        change = calc_change(curr, prev)
        arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
        lines.append(f"  {m}: {arrow} {abs(change)}%")

    lines.append("")

    # 周同比
    lines.append("【周同比】(vs 上周同日)")
    for m in METRICS:
        curr = today_data.get(m, 0)
        prev = last_week_data.get(m, 0)
        change = calc_change(curr, prev)
        arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
        lines.append(f"  {m}: {arrow} {abs(change)}%")

    lines.append("")

    # 账号明细
    today_rows = daily_accounts.get(today, [])
    if today_rows:
        lines.append("【账号明细】")
        # 按GMV排序
        today_rows.sort(key=lambda x: x.get("GMV", 0), reverse=True)
        for row in today_rows:
            acct = row.get("账号", "未知")
            owner = row.get("归属人", "")
            status = row.get("账号状态", "")
            gmv = row.get("GMV", 0)
            commission = row.get("佣金", 0)
            orders = int(row.get("电商出单", 0))
            lines.append(f"  {acct} ({owner}) [{status}]")
            lines.append(f"    GMV: ${gmv:,.2f} | 佣金: ${commission:,.2f} | 出单: {orders}")

    lines.append("")
    lines.append(f"📈 完整数据看板: https://sunheyang01.github.io/tiktok-ecom-dashboard/")

    return today, lines


def export_json(rows, daily_summary, account_summary):
    """导出 JSON 供 H5 看板使用"""
    os.makedirs(DOCS_DIR, exist_ok=True)

    # 计算累计总数 = 基线 + 当前所有数据之和
    current_totals = {}
    for m in METRICS:
        current_totals[m] = sum(r.get(m, 0) for r in rows)
    cumulative = {}
    for m in METRICS:
        cumulative[m] = BASELINE.get(m, 0) + current_totals[m]

    # 全量数据
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": rows,
        "daily_summary": {k: dict(v) for k, v in daily_summary.items()},
        "account_summary": {},
        "metrics": METRICS,
        "baseline": BASELINE,
        "cumulative": cumulative,
    }

    # 处理 account_summary
    for acct, info in account_summary.items():
        output["account_summary"][acct] = {
            "归属人": info.get("归属人", ""),
            "账号状态": info.get("账号状态", ""),
            "total": dict(info["total"]),
            "daily": {k: dict(v) for k, v in info["daily"].items()},
        }

    filepath = os.path.join(DOCS_DIR, "dashboard.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[导出] JSON 已保存至 {filepath}")
    return filepath


def main():
    print(f"[{datetime.now()}] 开始数据分析...")

    # 1. 拉取数据
    rows = fetch_data()
    if not rows:
        print("[警告] 无数据，退出")
        sys.exit(0)

    # 2. 标准化
    rows = normalize_rows(rows)

    # 3. 汇总分析
    daily_summary, daily_accounts = build_daily_summary(rows)
    account_summary = build_account_summary(rows)

    # 4. 导出 JSON
    export_json(rows, daily_summary, account_summary)

    # 5. 生成报告
    today, report_lines = generate_report(daily_summary, daily_accounts, account_summary, rows)
    report_text = "\n".join(report_lines)
    print("\n" + report_text)

    # 6. 通过机器人应用发送飞书群消息
    if CHAT_ID:
        bot = FeishuClient(app_id=BOT_APP_ID, app_secret=BOT_APP_SECRET)
        bot.send_message(
            CHAT_ID,
            f"TikTok 电商日报 | {today}",
            report_lines
        )
        print("[完成] 飞书群消息已发送")
    else:
        print("[跳过] 未配置 FEISHU_CHAT_ID，不发送消息")

    print(f"[{datetime.now()}] 分析完成")


if __name__ == "__main__":
    main()
