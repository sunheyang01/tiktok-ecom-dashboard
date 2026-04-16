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
    """从MCN爬虫SQLite读取最近N天的数据"""
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 读取最近N天的数据（含达人名称）
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT dm.*, c.creator_name, c.tiktok_handle
        FROM daily_metrics dm
        JOIN creators c ON dm.creator_id = c.creator_id
        WHERE dm.date >= ?
          AND dm.creator_id NOT LIKE 'test%'
        ORDER BY dm.date, c.creator_name
    """, (start_date,)).fetchall()

    records = []
    for row in rows:
        r = dict(row)
        # 达人名称：优先用 tiktok_handle，否则用 creator_name
        name = r.get("creator_name", "")
        creator_id = r.get("creator_id", "")

        record = {
            "账号": name or creator_id,
            "名称": name,
            "日期": r["date"],
            "归属人": "-",
            "账号状态": "正常",
            "区域": "EU",
            "电商出单": str(r.get("order_count", 0)),
            "GMV": str(r.get("gmv", 0)),
            "佣金": str(r.get("withdrawable_commission", 0)),
            "提现金额": str(r.get("withdrawable_commission", 0)),
            "冻结金额": "0",
            "播放量": str(r.get("play_count", 0)),
            "完播率": str(round(r.get("completion_rate", 0) * 100, 2)) if r.get("completion_rate") else "0",
            "CTR": str(round(r.get("product_ctr", 0) * 100, 2)) if r.get("product_ctr") else "0",
            "CTOR": str(round(r.get("product_ctor", 0) * 100, 2)) if r.get("product_ctor") else "0",
            # 基础/达人/机构佣金不存飞书：analyze.py 在生成 dashboard.json 时
            # 直接从本地 SQLite order_details 表合并（merge_order_commissions）
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
