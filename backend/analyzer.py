"""
数据分析模块
- 日环比 (Day-over-Day)
- 周同比 (Week-over-Week, 与上周同日对比)
- 账号维度汇总
- 人员维度汇总
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from config import CORE_METRICS, CORE_METRICS_CN, DATA_OUTPUT_PATH


class DataAnalyzer:
    def __init__(self, records: list):
        self.records = records
        self.date_data = defaultdict(list)      # {date: [records]}
        self.account_data = defaultdict(list)    # {account: [records]}
        self.owner_data = defaultdict(list)      # {owner: [records]}
        self._organize_data()

    def _organize_data(self):
        """按日期、账号、归属人组织数据"""
        for r in self.records:
            date = r.get("date", "")
            account = r.get("account", "")
            owner = r.get("owner", "")

            if date:
                self.date_data[date].append(r)
            if account:
                self.account_data[account].append(r)
            if owner:
                self.owner_data[owner].append(r)

    def get_all_dates_sorted(self):
        """获取所有日期，排序"""
        dates = sorted(self.date_data.keys())
        return dates

    def get_date_summary(self, date: str) -> dict:
        """获取某天的汇总数据"""
        records = self.date_data.get(date, [])
        summary = {metric: 0.0 for metric in CORE_METRICS}
        summary["account_count"] = len(set(r["account"] for r in records))

        for r in records:
            for metric in CORE_METRICS:
                summary[metric] += float(r.get(metric, 0))

        return summary

    def get_account_date_summary(self, date: str) -> list:
        """获取某天各账号的明细数据"""
        records = self.date_data.get(date, [])
        result = []
        for r in records:
            item = {
                "account": r.get("account", ""),
                "owner": r.get("owner", ""),
                "status": r.get("status", ""),
            }
            for metric in CORE_METRICS:
                item[metric] = float(r.get(metric, 0))
            result.append(item)
        return result

    def calc_day_over_day(self, target_date: str) -> dict:
        """
        计算日环比 (与前一天对比)
        返回: {metric: {value, prev_value, change, change_pct}}
        """
        target = datetime.strptime(target_date, "%Y-%m-%d")
        prev_date = (target - timedelta(days=1)).strftime("%Y-%m-%d")

        current = self.get_date_summary(target_date)
        previous = self.get_date_summary(prev_date)

        result = {}
        for metric in CORE_METRICS:
            cur_val = current[metric]
            prev_val = previous[metric]
            change = cur_val - prev_val
            change_pct = (change / prev_val * 100) if prev_val != 0 else 0

            result[metric] = {
                "value": cur_val,
                "prev_value": prev_val,
                "change": change,
                "change_pct": round(change_pct, 2),
            }
        return result

    def calc_week_over_week(self, target_date: str) -> dict:
        """
        计算周同比 (与上周同日对比)
        返回: {metric: {value, prev_value, change, change_pct}}
        """
        target = datetime.strptime(target_date, "%Y-%m-%d")
        prev_date = (target - timedelta(days=7)).strftime("%Y-%m-%d")

        current = self.get_date_summary(target_date)
        previous = self.get_date_summary(prev_date)

        result = {}
        for metric in CORE_METRICS:
            cur_val = current[metric]
            prev_val = previous[metric]
            change = cur_val - prev_val
            change_pct = (change / prev_val * 100) if prev_val != 0 else 0

            result[metric] = {
                "value": cur_val,
                "prev_value": prev_val,
                "change": change,
                "change_pct": round(change_pct, 2),
            }
        return result

    def calc_account_comparison(self, target_date: str) -> list:
        """
        计算每个账号的日环比和周同比
        """
        target = datetime.strptime(target_date, "%Y-%m-%d")
        prev_day = (target - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_week = (target - timedelta(days=7)).strftime("%Y-%m-%d")

        # 按账号+日期索引
        account_date_map = defaultdict(lambda: defaultdict(dict))
        for r in self.records:
            account_date_map[r.get("account", "")][r.get("date", "")] = r

        today_records = self.date_data.get(target_date, [])
        results = []

        for r in today_records:
            account = r.get("account", "")
            item = {
                "account": account,
                "owner": r.get("owner", ""),
                "status": r.get("status", ""),
                "metrics": {}
            }

            prev_day_r = account_date_map.get(account, {}).get(prev_day, {})
            prev_week_r = account_date_map.get(account, {}).get(prev_week, {})

            for metric in CORE_METRICS:
                cur_val = float(r.get(metric, 0))
                day_prev = float(prev_day_r.get(metric, 0))
                week_prev = float(prev_week_r.get(metric, 0))

                day_change = cur_val - day_prev
                day_pct = (day_change / day_prev * 100) if day_prev != 0 else 0
                week_change = cur_val - week_prev
                week_pct = (week_change / week_prev * 100) if week_prev != 0 else 0

                item["metrics"][metric] = {
                    "value": cur_val,
                    "day_change_pct": round(day_pct, 2),
                    "week_change_pct": round(week_pct, 2),
                }

            results.append(item)

        # 按 GMV 降序排列
        results.sort(key=lambda x: x["metrics"]["gmv"]["value"], reverse=True)
        return results

    def generate_full_dashboard_data(self) -> dict:
        """
        生成 H5 看板所需的完整数据 JSON
        """
        dates = self.get_all_dates_sorted()

        # 1. 每日汇总趋势
        daily_trend = []
        for date in dates:
            summary = self.get_date_summary(date)
            summary["date"] = date
            daily_trend.append(summary)

        # 2. 每日各账号明细
        daily_account_detail = {}
        for date in dates:
            daily_account_detail[date] = self.get_account_date_summary(date)

        # 3. 账号汇总排名 (全部时间)
        account_totals = []
        for account, records in self.account_data.items():
            total = {"account": account, "owner": "", "status": ""}
            for metric in CORE_METRICS:
                total[metric] = sum(float(r.get(metric, 0)) for r in records)

            if records:
                total["owner"] = records[-1].get("owner", "")
                total["status"] = records[-1].get("status", "")
                total["days_active"] = len(set(r.get("date", "") for r in records))

            account_totals.append(total)

        account_totals.sort(key=lambda x: x["gmv"], reverse=True)

        # 4. 归属人汇总
        owner_totals = []
        for owner, records in self.owner_data.items():
            total = {"owner": owner}
            for metric in CORE_METRICS:
                total[metric] = sum(float(r.get(metric, 0)) for r in records)
            total["account_count"] = len(set(r.get("account", "") for r in records))
            owner_totals.append(total)

        owner_totals.sort(key=lambda x: x["gmv"], reverse=True)

        # 5. 最新日期的环比/同比
        latest_comparison = {}
        if dates:
            latest_date = dates[-1]
            latest_comparison = {
                "date": latest_date,
                "day_over_day": self.calc_day_over_day(latest_date),
                "week_over_week": self.calc_week_over_week(latest_date),
                "account_detail": self.calc_account_comparison(latest_date),
            }

        # 6. 账号趋势数据 (每个账号每天的数据)
        account_trends = {}
        for account, records in self.account_data.items():
            sorted_records = sorted(records, key=lambda x: x.get("date", ""))
            account_trends[account] = []
            for r in sorted_records:
                item = {"date": r.get("date", "")}
                for metric in CORE_METRICS:
                    item[metric] = float(r.get(metric, 0))
                account_trends[account].append(item)

        return {
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_records": len(self.records),
            "total_accounts": len(self.account_data),
            "total_owners": len(self.owner_data),
            "date_range": {"start": dates[0] if dates else "", "end": dates[-1] if dates else ""},
            "daily_trend": daily_trend,
            "daily_account_detail": daily_account_detail,
            "account_totals": account_totals,
            "owner_totals": owner_totals,
            "latest_comparison": latest_comparison,
            "account_trends": account_trends,
        }

    def generate_daily_report(self, target_date: str = None) -> str:
        """
        生成当日文字报告 (飞书 Markdown 格式)
        """
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        dates = self.get_all_dates_sorted()
        if target_date not in self.date_data:
            return f"⚠️ {target_date} 暂无数据"

        summary = self.get_date_summary(target_date)
        dod = self.calc_day_over_day(target_date)
        wow = self.calc_week_over_week(target_date)
        account_detail = self.calc_account_comparison(target_date)

        def arrow(pct):
            if pct > 0:
                return f"📈 +{pct}%"
            elif pct < 0:
                return f"📉 {pct}%"
            else:
                return "➡️ 0%"

        def fmt_num(val):
            if val >= 10000:
                return f"{val/10000:.2f}万"
            return f"{val:,.2f}"

        lines = []
        lines.append(f"**📅 {target_date} TikTok 电商日报**\n")

        # 整体概览
        lines.append("---\n**🏷️ 整体概览**\n")
        lines.append(f"活跃账号数：**{summary['account_count']}**\n")

        for metric in CORE_METRICS:
            cn_name = CORE_METRICS_CN[metric]
            val = summary[metric]
            day_pct = dod[metric]["change_pct"]
            week_pct = wow[metric]["change_pct"]

            lines.append(
                f"**{cn_name}**：{fmt_num(val)}　"
                f"日环比 {arrow(day_pct)}　"
                f"周同比 {arrow(week_pct)}"
            )

        # TOP 账号
        lines.append("\n---\n**🏆 账号排行 (按GMV)**\n")
        for i, item in enumerate(account_detail[:10], 1):
            m = item["metrics"]
            gmv_val = fmt_num(m["gmv"]["value"])
            gmv_day = arrow(m["gmv"]["day_change_pct"])
            lines.append(
                f"{i}. **{item['account']}** ({item['owner']})\n"
                f"　　GMV: {gmv_val} {gmv_day} | "
                f"出单: {int(m['orders']['value'])} | "
                f"佣金: {fmt_num(m['commission']['value'])}"
            )

        # 异常提醒
        lines.append("\n---\n**⚠️ 异常关注**\n")
        anomalies = []
        for item in account_detail:
            m = item["metrics"]
            # GMV 日环比下降超过 30%
            if m["gmv"]["day_change_pct"] < -30 and m["gmv"]["value"] > 0:
                anomalies.append(
                    f"- {item['account']}：GMV 日环比下降 {abs(m['gmv']['day_change_pct'])}%"
                )
            # 冻结金额大于提现金额
            if m["frozen"]["value"] > m["withdrawal"]["value"] and m["frozen"]["value"] > 0:
                anomalies.append(
                    f"- {item['account']}：冻结金额({fmt_num(m['frozen']['value'])}) > 提现金额({fmt_num(m['withdrawal']['value'])})"
                )

        if anomalies:
            lines.extend(anomalies)
        else:
            lines.append("暂无异常 ✅")

        lines.append(f"\n---\n[📊 查看完整数据看板](https://sunheyang01.github.io/tiktok-ecom-dashboard/)")

        return "\n".join(lines)

    def export_dashboard_json(self):
        """导出看板数据到 JSON 文件"""
        data = self.generate_full_dashboard_data()
        os.makedirs(os.path.dirname(DATA_OUTPUT_PATH), exist_ok=True)
        with open(DATA_OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 看板数据已导出: {DATA_OUTPUT_PATH}")
        return data
