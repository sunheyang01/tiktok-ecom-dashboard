"""
飞书 API 客户端
- 获取 tenant_access_token
- 从 wiki 获取多维表格 app_token
- 读取多维表格数据
- 通过机器人发送消息
"""
import json
import time
import requests
from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_URL,
    FEISHU_TOKEN_URL, WIKI_TOKEN, TABLE_ID, VIEW_ID,
    FEISHU_BOT_WEBHOOK, FIELD_MAPPING
)


class FeishuClient:
    def __init__(self):
        self._token = None
        self._token_expire = 0
        self._app_token = None

    @property
    def tenant_access_token(self):
        """获取/刷新 tenant_access_token"""
        if self._token and time.time() < self._token_expire:
            return self._token

        resp = requests.post(FEISHU_TOKEN_URL, json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
        })
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取 token 失败: {data}")

        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 7200) - 60
        print(f"✅ 获取 tenant_access_token 成功")
        return self._token

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json",
        }

    def get_app_token(self):
        """从 wiki 节点获取多维表格的 app_token"""
        if self._app_token:
            return self._app_token

        url = f"{FEISHU_BASE_URL}/wiki/v2/spaces/get_node"
        resp = requests.get(url, headers=self.headers, params={"token": WIKI_TOKEN})
        data = resp.json()

        if data.get("code") != 0:
            raise Exception(f"获取 wiki 节点失败: {data}")

        node = data["data"]["node"]
        self._app_token = node["obj_token"]
        print(f"✅ 获取 app_token 成功: {self._app_token}")
        return self._app_token

    def fetch_all_records(self):
        """
        分页读取多维表格全部数据
        返回: list[dict] — 每条记录的字段数据
        """
        app_token = self.get_app_token()
        url = f"{FEISHU_BASE_URL}/bitable/v1/apps/{app_token}/tables/{TABLE_ID}/records"

        all_records = []
        page_token = None
        page_size = 500

        while True:
            params = {"view_id": VIEW_ID, "page_size": page_size}
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, headers=self.headers, params=params)
            data = resp.json()

            if data.get("code") != 0:
                raise Exception(f"读取表格数据失败: {data}")

            items = data.get("data", {}).get("items", [])
            for item in items:
                fields = item.get("fields", {})
                record = self._normalize_record(fields)
                if record:
                    all_records.append(record)

            has_more = data.get("data", {}).get("has_more", False)
            page_token = data.get("data", {}).get("page_token")

            if not has_more:
                break

        print(f"✅ 共读取 {len(all_records)} 条记录")
        return all_records

    def _normalize_record(self, fields):
        """将飞书字段转换为标准化字典"""
        record = {}
        for cn_name, en_name in FIELD_MAPPING.items():
            value = fields.get(cn_name)
            if value is None:
                value = fields.get(cn_name, "")

            # 处理飞书特殊数据格式
            if isinstance(value, dict):
                # 日期字段可能是时间戳
                value = value.get("value", value.get("text", str(value)))
            elif isinstance(value, list):
                # 多选/人员字段
                if len(value) > 0 and isinstance(value[0], dict):
                    value = value[0].get("text", value[0].get("name", str(value[0])))
                else:
                    value = str(value[0]) if value else ""

            # 日期字段特殊处理（飞书可能返回毫秒时间戳）
            if en_name == "date" and isinstance(value, (int, float)):
                from datetime import datetime
                # 飞书时间戳是毫秒
                ts = value / 1000 if value > 1e12 else value
                value = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

            # 数值字段转换
            if en_name in ("orders", "gmv", "commission", "withdrawal", "frozen"):
                try:
                    value = float(value) if value else 0.0
                except (ValueError, TypeError):
                    value = 0.0

            record[en_name] = value

        return record

    def send_bot_message(self, content: str):
        """通过飞书群机器人 Webhook 发送消息"""
        if not FEISHU_BOT_WEBHOOK:
            print("⚠️  未配置飞书机器人 Webhook，跳过发送")
            print("=" * 50)
            print(content)
            print("=" * 50)
            return False

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "📊 TikTok 电商日报"
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content
                    }
                ]
            }
        }

        resp = requests.post(FEISHU_BOT_WEBHOOK, json=payload)
        data = resp.json()

        if data.get("code") == 0 or data.get("StatusCode") == 0:
            print("✅ 飞书消息发送成功")
            return True
        else:
            print(f"❌ 飞书消息发送失败: {data}")
            return False
