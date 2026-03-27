"""
飞书电商数据分析 - 配置文件
"""
import os

# ========== 飞书应用凭证 ==========
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "cli_a74fd73a38eb100c")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "XZlgk2JSUQnmNYE1vprvjfPldWlyRqrw")

# ========== 飞书多维表格 ==========
# 从 wiki 链接中提取的参数
WIKI_TOKEN = "Bkspw46VYiVs1Bkly3hchgRfnFc"
TABLE_ID = "tblKWqac7SVi8p8d"
VIEW_ID = "vewo476Vun"

# ========== 飞书机器人 Webhook ==========
# 需要在飞书群中添加自定义机器人，获取 webhook 地址
FEISHU_BOT_WEBHOOK = os.getenv("FEISHU_BOT_WEBHOOK", "")

# ========== 飞书 API 地址 ==========
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
FEISHU_TOKEN_URL = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
FEISHU_WIKI_NODE_URL = f"{FEISHU_BASE_URL}/wiki/v2/spaces/get_node"

# ========== 数据字段映射 ==========
FIELD_MAPPING = {
    "账号": "account",
    "日期": "date",
    "归属人": "owner",
    "账号状态": "status",
    "电商出单": "orders",
    "GMV": "gmv",
    "佣金": "commission",
    "提现金额": "withdrawal",
    "冻结金额": "frozen",
}

# 需要分析的核心指标
CORE_METRICS = ["gmv", "commission", "withdrawal", "frozen", "orders"]
CORE_METRICS_CN = {
    "gmv": "GMV",
    "commission": "佣金",
    "withdrawal": "提现金额",
    "frozen": "冻结金额",
    "orders": "电商出单",
}

# ========== 输出路径 ==========
DATA_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "sales_data.json")
