"""飞书多维表格数据客户端"""
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse


class FeishuClient:
    """飞书 API 客户端，用于读取多维表格数据"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id=None, app_secret=None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "cli_a74fd73a38eb100c")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "XZlgk2JSUQnmNYE1vprvjfPldWlyRqrw")
        self._token = None
        self._token_expire = 0

    def _request(self, method, path, data=None, headers=None):
        url = f"{self.BASE_URL}{path}"
        _headers = {"Content-Type": "application/json; charset=utf-8"}
        if headers:
            _headers.update(headers)
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"HTTP Error {e.code}: {error_body}")
            raise

    @property
    def token(self):
        if time.time() < self._token_expire and self._token:
            return self._token
        resp = self._request("POST", "/auth/v3/tenant_access_token/internal", {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        })
        self._token = resp.get("tenant_access_token")
        self._token_expire = time.time() + resp.get("expire", 7200) - 60
        print(f"[FeishuClient] 获取 token 成功")
        return self._token

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def list_records(self, app_token, table_id, page_size=500):
        """分页读取多维表格全部记录"""
        records = []
        page_token = None
        while True:
            params = f"page_size={page_size}"
            if page_token:
                params += f"&page_token={page_token}"
            path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records?{params}"
            resp = self._request("GET", path, headers=self._auth_headers())
            data = resp.get("data", {})
            items = data.get("items", [])
            records.extend(items)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
        print(f"[FeishuClient] 共读取 {len(records)} 条记录")
        return records

    def parse_records(self, records):
        """将飞书记录解析为标准字典列表"""
        rows = []
        for rec in records:
            fields = rec.get("fields", {})
            row = {}
            for key, val in fields.items():
                # 处理飞书字段类型
                if isinstance(val, list):
                    # 人员、多选等
                    texts = []
                    for item in val:
                        if isinstance(item, dict):
                            texts.append(item.get("text", item.get("name", str(item))))
                        else:
                            texts.append(str(item))
                    row[key] = ", ".join(texts)
                elif isinstance(val, dict):
                    row[key] = val.get("text", val.get("name", str(val)))
                else:
                    row[key] = val
            rows.append(row)
        return rows


def send_feishu_message(webhook_url, title, content_lines):
    """通过飞书机器人 webhook 发送富文本消息"""
    post_content = []
    for line in content_lines:
        if isinstance(line, str):
            post_content.append([{"tag": "text", "text": line}])
        elif isinstance(line, list):
            post_content.append(line)

    msg = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": post_content
                }
            }
        }
    }
    data = json.dumps(msg).encode()
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode())
        print(f"[飞书消息] 发送结果: {result}")
        return result
