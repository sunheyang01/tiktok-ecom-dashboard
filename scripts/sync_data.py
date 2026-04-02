"""数据同步脚本：从飞书电子表格读取电商数据 → 写入多维表格"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ===== 配置 =====
# 源：飞书电子表格（用机器人应用读取）
SOURCE_APP_ID = os.environ.get("FEISHU_BOT_APP_ID", "cli_a94c27d2af38dbb5")
SOURCE_APP_SECRET = os.environ.get("FEISHU_BOT_APP_SECRET", "KZzghjmQbtdVl2fWoR5febQmBxtaxyQM")
SPREADSHEET_TOKEN = "ESvospoJ4hJngatBAUfcHQ62nwc"

# 8 个人的 sheet
SHEETS = [
    ("成畅", "Hd1IUC"), ("旭婷", "7tvEHa"), ("子凌", "it0tzH"),
    ("鹏祥", "inxlLo"), ("赵毅", "PIxlAe"), ("一凡", "5nnKTH"),
    ("心怡", "JU74JM"), ("兆镭", "n8BxMT"),
]

# 目标：飞书多维表格（用数据应用写入）
TARGET_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a74fd73a38eb100c")
TARGET_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "XZlgk2JSUQnmNYE1vprvjfPldWlyRqrw")
BITABLE_APP_TOKEN = "Bkspw46VYiVs1Bkly3hchgRfnFc"
BITABLE_TABLE_ID = "tblKWqac7SVi8p8d"

# 只要 3.26 之后的数据（序列号 > 46107）
DATE_CUTOFF_SERIAL = 46107  # 2026-03-26
DATE_CUTOFF_STR = "2026-03-26"

# 列索引映射（基于统一表头）
COL = {
    "日期": 0,       # A
    "组别": 1,       # B
    "持有人": 2,     # C
    "账号名称": 3,   # D
    "账号ID": 4,     # E
    "区域": 5,       # F
    "类别": 6,       # G
    "状态": 7,       # H (启动日期/停更/封禁)
    "电商出单": 13,  # N
    "GMV": 14,       # O
    "佣金": 15,      # P
    "提现金额": 16,  # Q
    "冻结金额": 17,  # R
}

BASE_URL = "https://open.feishu.cn/open-apis"


def get_token(app_id, app_secret):
    """获取 tenant_access_token"""
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["tenant_access_token"]


def excel_serial_to_date(serial):
    """Excel 序列号转日期字符串"""
    if isinstance(serial, (int, float)) and serial > 40000:
        dt = datetime(1899, 12, 30) + timedelta(days=int(serial))
        return dt.strftime("%Y-%m-%d")
    return None


def parse_text_date(text):
    """解析文本日期，如 '3.27', '4.1', '3.27-30' 等"""
    import re
    text = text.strip()
    year = datetime.now().year

    # 匹配 "月.日-日" 或 "月.日" 格式，取第一个日期
    m = re.match(r'(\d{1,2})[.\-/](\d{1,2})', text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                pass

    # 匹配 "YYYY-MM-DD" 或 "YYYY/MM/DD"
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def safe_float(val):
    """安全转浮点数"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace(",", "").replace("$", "").replace("¥", "").strip()
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0
    return 0


def safe_int(val):
    """安全转整数"""
    return int(safe_float(val))


def get_cell(row, idx):
    """安全获取单元格值"""
    if idx < len(row):
        return row[idx]
    return None


def parse_status(val):
    """解析账号状态"""
    if val is None:
        return "正常"
    s = str(val).strip()
    if not s:
        return "正常"
    # 如果是日期（启动日期），说明账号正常
    if isinstance(val, (int, float)) and val > 40000:
        return "正常"
    # 检查状态关键词
    s_lower = s.lower()
    for keyword in ["封", "ban", "封号", "被封"]:
        if keyword in s_lower:
            return "封禁"
    for keyword in ["停更", "停"]:
        if keyword in s_lower:
            return "停更"
    for keyword in ["掉窗"]:
        if keyword in s_lower:
            return "掉窗"
    for keyword in ["受限", "限制"]:
        if keyword in s_lower:
            return "受限"
    # 如果看起来是日期字符串
    if any(c.isdigit() for c in s) and ('.' in s or '-' in s or '/' in s):
        return "正常"
    return s


def read_sheet(token, sheet_id, sheet_name):
    """读取一个 sheet 的电商数据"""
    print(f"  读取 [{sheet_name}]...")

    # 读取全部数据（最多5000行）
    req = urllib.request.Request(
        f"{BASE_URL}/sheets/v2/spreadsheets/{SPREADSHEET_TOKEN}/values/{sheet_id}!A1:R5000",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            values = result.get("data", {}).get("valueRange", {}).get("values", [])
    except urllib.error.HTTPError as e:
        print(f"    ❌ 读取失败: HTTP {e.code}")
        return []

    if len(values) < 2:
        print(f"    空表")
        return []

    # 第一遍：填充日期（处理合并单元格）
    # 日期只出现在每组的第一行，后续行日期为空，需要向上继承
    current_date_serial = None
    current_date_str = None
    row_dates = []  # (date_str, date_serial) for each data row

    for row in values[1:]:
        date_val = get_cell(row, COL["日期"])
        if isinstance(date_val, (int, float)) and date_val > 40000:
            # Excel 序列号日期
            current_date_serial = date_val
            current_date_str = excel_serial_to_date(date_val)
        elif isinstance(date_val, (int, float)) and 0 < date_val < 13:
            # 文本日期被解析为 float，如 1.8 = 1月8日, 4.2 = 4月2日
            month = int(date_val)
            day = round((date_val - month) * 100)  # 1.8 -> 8, 1.11 -> 11
            if day == 0:
                day = int(str(date_val).split('.')[-1]) if '.' in str(date_val) else 1
            try:
                year = datetime.now().year
                dt = datetime(year, month, day)
                current_date_serial = (dt - datetime(1899, 12, 30)).days
                current_date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass  # 无效日期，保持上一个
        elif isinstance(date_val, str) and date_val.strip():
            s = date_val.strip()
            if "SUM" not in s and "合计" not in s:
                # 尝试解析文本日期如 "3.27-30", "4.1"
                current_date_str = parse_text_date(s)
                current_date_serial = None
                if current_date_str:
                    try:
                        dt = datetime.strptime(current_date_str, "%Y-%m-%d")
                        current_date_serial = (dt - datetime(1899, 12, 30)).days
                    except ValueError:
                        pass
        row_dates.append((current_date_str, current_date_serial))

    # 第二遍：筛选电商数据
    rows = []
    for i, row in enumerate(values[1:], start=2):
        # 筛选类别含"电商"
        category = get_cell(row, COL["类别"])
        if not category or "电商" not in str(category):
            continue

        # 获取继承后的日期
        date_str, date_serial = row_dates[i - 2]

        # 筛选日期 > 3.26
        if date_serial is not None:
            # Excel 序列号日期
            if date_serial <= DATE_CUTOFF_SERIAL:
                continue
        elif date_str:
            # 文本日期，尝试解析判断
            # 跳过汇总行
            if "SUM" in str(date_str) or "合计" in str(date_str):
                continue
            # 文本日期暂时保留，后续分析脚本会处理格式
        else:
            continue  # 无日期跳过

        if not date_str:
            continue

        # 提取数据
        account_name = get_cell(row, COL["账号名称"]) or ""
        account_id = get_cell(row, COL["账号ID"]) or ""
        account = str(account_id) if account_id else str(account_name)
        if not account.strip():
            continue

        owner = get_cell(row, COL["持有人"]) or sheet_name  # 没有持有人就用sheet名
        status = parse_status(get_cell(row, COL["状态"]))

        # 有些 sheet 把状态写在"名称"列（如兆镭的"被封"）
        name_str = str(account_name).strip() if account_name else ""
        if status == "正常" and name_str:
            name_status = parse_status(name_str)
            if name_status != "正常" and name_status != name_str:
                status = name_status
                # 名称列是状态词时，用账号ID作为名称
                account_name = account_id or account_name

        record = {
            "账号": account.strip(),
            "名称": str(account_name).strip() if account_name else account.strip(),
            "日期": date_str,
            "归属人": str(owner).strip(),
            "账号状态": status,
            "电商出单": str(safe_int(get_cell(row, COL["电商出单"]))),
            "GMV": str(safe_float(get_cell(row, COL["GMV"]))),
            "佣金": str(safe_float(get_cell(row, COL["佣金"]))),
            "提现金额": str(safe_float(get_cell(row, COL["提现金额"]))),
            "冻结金额": str(safe_float(get_cell(row, COL["冻结金额"]))),
        }
        rows.append(record)

    print(f"    ✅ 筛选出 {len(rows)} 条电商数据（3.26后）")
    return rows


def get_existing_records(token):
    """获取多维表格已有记录，用于去重"""
    records = []
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
        items = data.get("items", [])
        for item in items:
            fields = item.get("fields", {})
            key = f"{fields.get('账号', '')}_{fields.get('日期', '')}"
            records.append({"key": key, "record_id": item["record_id"]})
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return records


def write_to_bitable(token, new_records):
    """批量写入多维表格（自动去重）"""
    # 获取已有记录
    print("\n[同步] 检查已有数据...")
    existing = get_existing_records(token)
    existing_keys = {r["key"] for r in existing}
    print(f"  多维表格已有 {len(existing)} 条记录")

    # 过滤重复
    to_insert = []
    for rec in new_records:
        key = f"{rec['账号']}_{rec['日期']}"
        if key not in existing_keys:
            to_insert.append(rec)
        else:
            pass  # 已存在，跳过

    if not to_insert:
        print("  无新数据需要写入")
        return 0

    print(f"  新增 {len(to_insert)} 条，开始写入...")

    # 分批写入（每批最多500条）
    total = 0
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
            total += count
            if code != 0:
                print(f"    ❌ 批次写入失败: {result.get('msg')}")
            else:
                print(f"    ✅ 批次写入 {count} 条")

    return total


def main():
    print(f"[{datetime.now()}] 开始数据同步...")

    # 1. 获取源表 token（机器人应用）
    print("\n[步骤1] 获取源表访问权限...")
    source_token = get_token(SOURCE_APP_ID, SOURCE_APP_SECRET)
    print("  ✅ 源表 token 获取成功")

    # 2. 从所有 sheet 读取电商数据
    print("\n[步骤2] 扫描电商数据...")
    all_records = []
    for sheet_name, sheet_id in SHEETS:
        records = read_sheet(source_token, sheet_id, sheet_name)
        all_records.extend(records)

    print(f"\n[汇总] 共获取 {len(all_records)} 条电商数据")
    if not all_records:
        print("[完成] 无新电商数据，退出")
        return

    # 打印预览
    print("\n[预览] 前5条:")
    for r in all_records[:5]:
        print(f"  {r['日期']} | {r['账号']} | {r['归属人']} | {r['账号状态']} | GMV={r['GMV']} | 出单={r['电商出单']}")

    # 3. 获取目标表 token（数据应用）
    print("\n[步骤3] 获取多维表格写入权限...")
    target_token = get_token(TARGET_APP_ID, TARGET_APP_SECRET)
    print("  ✅ 多维表格 token 获取成功")

    # 4. 写入多维表格
    print("\n[步骤4] 写入多维表格...")
    count = write_to_bitable(target_token, all_records)
    print(f"\n[{datetime.now()}] 同步完成！新增 {count} 条记录")


if __name__ == "__main__":
    main()
