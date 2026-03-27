"""
主入口 - 电商数据分析流水线
1. 从飞书多维表格拉取数据
2. 分析数据，生成看板 JSON
3. 生成当日文字报告
4. 通过飞书机器人发送报告
"""
import sys
import json
import os
from datetime import datetime

from feishu_client import FeishuClient
from analyzer import DataAnalyzer
from config import DATA_OUTPUT_PATH


def main():
    print(f"\n{'='*50}")
    print(f"🚀 TikTok 电商数据分析 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # 1. 初始化飞书客户端
    client = FeishuClient()

    # 2. 拉取全部数据
    print("📥 正在从飞书多维表格拉取数据...")
    try:
        records = client.fetch_all_records()
    except Exception as e:
        print(f"❌ 数据拉取失败: {e}")
        sys.exit(1)

    if not records:
        print("⚠️ 未获取到任何数据，请检查多维表格是否有数据")
        sys.exit(0)

    # 3. 数据分析
    print("\n📊 正在分析数据...")
    analyzer = DataAnalyzer(records)

    # 4. 导出看板数据
    print("\n📤 正在生成看板数据...")
    dashboard_data = analyzer.export_dashboard_json()
    print(f"   总记录数: {dashboard_data['total_records']}")
    print(f"   账号总数: {dashboard_data['total_accounts']}")
    print(f"   数据范围: {dashboard_data['date_range']['start']} ~ {dashboard_data['date_range']['end']}")

    # 5. 生成当日报告
    today = datetime.now().strftime("%Y-%m-%d")
    dates = analyzer.get_all_dates_sorted()

    # 使用最新有数据的日期
    report_date = today if today in analyzer.date_data else (dates[-1] if dates else today)
    print(f"\n📝 正在生成 {report_date} 日报...")
    report = analyzer.generate_daily_report(report_date)

    # 6. 发送飞书消息
    print("\n📨 正在发送飞书消息...")
    client.send_bot_message(report)

    print(f"\n{'='*50}")
    print("✅ 全部任务完成!")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
