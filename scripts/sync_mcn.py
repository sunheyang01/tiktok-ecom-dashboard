"""MCN爬虫数据同步：从本地SQLite读取EU区数据 → 写入飞书多维表格"""
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ===== 配置 =====
# MCN爬虫SQLite数据库路径（与爬虫项目共用同一个db）
MCN_DB_PATH = os.environ.get(
    "MCN_DB_PATH",
    os.path.expanduser("~/zewenkanban/tiktok-mcn-scraper/data/tiktok_mcn.db")
)

# 飞书多维表格（写入目标，与美区数据同一张表）
APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a74fd73a38eb100c")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "XZlgk2JSUQnmNYE1vprvjfPldWlyRqrw")
BITABLE_APP_TOKEN = "Bkspw46VYiVs1Bkly3hchgRfnFc"
BITABLE_TABLE_ID = "tblKWqac7SVi8p8d"

BASE_URL = "https://open.feishu.cn/open-apis"


def get_token():
    """获取飞书 tenant_access_token"""
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["tenant_access_token"]


def read_mcn_data(db_path, days_back=1):
    """从MCN爬虫SQLite读取最近N天的数据。

    新口径 (2026-04-17 起)：
      - GMV / 电商出单 / 佣金 ← 从 order_details 表聚合（只算 settle_status=2 待确认）
          · GMV = sum(sku_sale_price × item_count)  即"佣金 GMV"
          · 电商出单 = SKU 行数（一个多SKU订单算多条）
          · 佣金 = sum(cos_base_amount) 即预计基础佣金
      - 播放量 / 完播率 / CTR / CTOR ← 继续从 daily_metrics 读（达人分析页）
      - 提现金额 ← 不存飞书：payouts 表是 MCN 机构整体打款，不按账号拆分，
        由 analyze.py 在 dashboard.json 里单独展示
    """
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # 1) 基础内容指标（播放量等）——来自达人分析页
    content_rows = conn.execute("""
        SELECT dm.creator_id, dm.date, c.creator_name, c.tiktok_handle,
               dm.play_count, dm.completion_rate, dm.product_ctr, dm.product_ctor
        FROM daily_metrics dm
        JOIN creators c ON dm.creator_id = c.creator_id
        WHERE dm.date >= ? AND dm.creator_id NOT LIKE 'test%'
    """, (start_date,)).fetchall()

    # 2) 订单聚合（GMV / 出单 / 佣金）——来自财务页订单，按(creator_id, order_date)
    order_aggs = conn.execute("""
        SELECT o.creator_id, o.order_date as date, c.creator_name,
               COUNT(*) as sku_rows,
               SUM(o.gmv) as gmv,
               SUM(o.cos_base_amount) as cos_base
        FROM order_details o
        JOIN creators c ON o.creator_id = c.creator_id
        WHERE o.order_date >= ?
          AND o.settle_status = 2
          AND o.creator_id NOT LIKE 'test%'
        GROUP BY o.creator_id, o.order_date
    """, (start_date,)).fetchall()
    order_map = {(r["creator_id"], r["date"]): dict(r) for r in order_aggs}

    # 合并：以 (creator_id, date) 为键
    merged = {}
    for r in content_rows:
        key = (r["creator_id"], r["date"])
        merged[key] = {
            "creator_id": r["creator_id"],
            "date": r["date"],
            "creator_name": r["creator_name"],
            "tiktok_handle": r["tiktok_handle"],
            "play_count": r["play_count"] or 0,
            "completion_rate": r["completion_rate"] or 0,
            "product_ctr": r["product_ctr"] or 0,
            "product_ctor": r["product_ctor"] or 0,
            "gmv": 0,
            "order_count": 0,
            "cos_base": 0,
        }
    # 订单数据覆盖 GMV/出单/佣金
    for (cid, d), agg in order_map.items():
        key = (cid, d)
        if key not in merged:
            # 有订单但 daily_metrics 没记录（少见）：用订单表的 creator_name 补
            merged[key] = {
                "creator_id": cid, "date": d,
                "creator_name": agg["creator_name"], "tiktok_handle": "",
                "play_count": 0, "completion_rate": 0,
                "product_ctr": 0, "product_ctor": 0,
                "gmv": 0, "order_count": 0, "cos_base": 0,
            }
        merged[key]["gmv"] = agg["gmv"] or 0
        merged[key]["order_count"] = agg["sku_rows"] or 0
        merged[key]["cos_base"] = agg["cos_base"] or 0

    records = []
    for (cid, d), r in sorted(merged.items(), key=lambda x: (x[0][1], x[0][0])):
        name = r["creator_name"]
        record = {
            "账号": name or cid,
            "名称": name,
            "日期": d,
            "归属人": "-",
            "账号状态": "正常",
            "区域": "EU",
            "电商出单": str(r["order_count"]),
            "GMV": str(round(r["gmv"], 2)),
            "佣金": str(round(r["cos_base"], 2)),  # = 预计基础佣金
            "提现金额": "0",  # 新口径：MCN整体打款走 payouts 表，不按账号分
            "冻结金额": "0",
            "播放量": str(r["play_count"]),
            "完播率": str(round(r["completion_rate"] * 100, 2)) if r["completion_rate"] else "0",
            "CTR": str(round(r["product_ctr"] * 100, 2)) if r["product_ctr"] else "0",
            "CTOR": str(round(r["product_ctor"] * 100, 2)) if r["product_ctor"] else "0",
        }
        records.append(record)

    conn.close()
    print(f"[MCN] 读取 {len(records)} 条EU区数据（{start_date} 起）")
    return records


def get_existing_records(token):
    """获取多维表格已有记录的 {key: record_id} 映射"""
    records_map = {}
    page_token = None
    while True:
        params = "page_size=500"
        if page_token:
            params += f"&page_token={page_token}"
        req = urllib.request.Request(
            f"{BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records?{params}",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        data = result.get("data", {})
        for item in data.get("items", []):
            fields = item.get("fields", {})
            key = f"{fields.get('账号', '')}_{fields.get('日期', '')}"
            records_map[key] = item.get("record_id", "")
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return records_map


def write_to_bitable(token, records):
    """批量写入飞书多维表格：新记录插入，已有记录更新（upsert）"""
    print("\n[同步] 检查已有数据...")
    existing = get_existing_records(token)
    print(f"  多维表格已有 {len(existing)} 条记录")

    to_insert = []
    to_update = []
    for rec in records:
        key = f"{rec['账号']}_{rec['日期']}"
        if key in existing:
            to_update.append({"record_id": existing[key], "fields": rec})
        else:
            to_insert.append(rec)

    print(f"  新增 {len(to_insert)} 条，更新 {len(to_update)} 条")

    total_new = 0
    total_upd = 0

    # ---- 批量插入 ----
    for i in range(0, len(to_insert), 500):
        batch = to_insert[i:i+500]
        body = {"records": [{"fields": rec} for rec in batch]}
        req = urllib.request.Request(
            f"{BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/batch_create",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            code = result.get("code", -1)
            count = len(result.get("data", {}).get("records", []))
            total_new += count
            if code != 0:
                print(f"    ❌ 插入批次失败: {result.get('msg')}")
            else:
                print(f"    ✅ 插入 {count} 条")

    # ---- 批量更新 ----
    for i in range(0, len(to_update), 500):
        batch = to_update[i:i+500]
        body = {"records": batch}
        req = urllib.request.Request(
            f"{BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/batch_update",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            code = result.get("code", -1)
            count = len(result.get("data", {}).get("records", []))
            total_upd += count
            if code != 0:
                print(f"    ❌ 更新批次失败: {result.get('msg')}")
            else:
                print(f"    ✅ 更新 {count} 条")

    return total_new + total_upd


def main():
    # 支持传入天数参数，默认同步昨天的数据
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"[{datetime.now()}] MCN爬虫数据同步（最近{days_back}天）...")

    # 1. 从SQLite读取
    records = read_mcn_data(MCN_DB_PATH, days_back)
    if not records:
        print("[完成] 无EU区数据，退出")
        return

    # 预览
    print("\n[预览] 前3条:")
    for r in records[:3]:
        print(f"  {r['日期']} | {r['名称']} | GMV={r['GMV']} | 出单={r['电商出单']} | 播放={r['播放量']}")

    # 2. 写入飞书
    token = get_token()
    count = write_to_bitable(token, records)
    print(f"\n[{datetime.now()}] 同步完成！新增 {count} 条EU区记录")


if __name__ == "__main__":
    main()
