"""
RSTao-Tool 在线激活服务器
FastAPI + SQLite，支持激活码验证、黑名单、次数限制、激活码管理
"""

import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# 确保可以导入公共模块
sys.path.insert(0, str(Path(__file__).parent.parent))
from common.crypto import generate_machine_code_hash
from common.license_crypto import (
    create_license_payload,
    load_private_key_from_env,
    private_key_matches_public,
    sign_license_payload,
)

# --- 轻量版：使用内置 http.server 避免额外依赖 ---
# 生产环境建议升级为 FastAPI + uvicorn

DB_PATH = Path(__file__).parent / "activation.db"


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS activation_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            license_type TEXT NOT NULL DEFAULT 'permanent',
            max_activations INTEGER NOT NULL DEFAULT 1,
            current_activations INTEGER NOT NULL DEFAULT 0,
            expire_days INTEGER DEFAULT NULL,
            expire_date TEXT DEFAULT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS activation_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activation_code TEXT NOT NULL,
            device_fingerprint TEXT NOT NULL,
            machine_code_hash TEXT NOT NULL,
            license_key TEXT NOT NULL,
            activated_at TEXT NOT NULL DEFAULT (datetime('now')),
            ip_address TEXT DEFAULT '',
            FOREIGN KEY (activation_code) REFERENCES activation_codes(code)
        );

        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT NOT NULL,
            reason TEXT DEFAULT '',
            blocked_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_blacklist_identifier ON blacklist(identifier);

        CREATE TABLE IF NOT EXISTS admin_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ====================== HTTP 服务器 ======================
import http.server
import urllib.parse

ACTIVATION_SERVER_PORT = 18080


class ActivationHandler(http.server.BaseHTTPRequestHandler):
    """激活服务器请求处理器"""

    def log_message(self, format, *args):
        """自定义日志格式"""
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.client_address[0]} - {format % args}"
        )

    def _send_json(self, status_code: int, data: dict):
        """发送 JSON 响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.headers.get("Origin", "")
        allowed = (
            origin
            if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
            else "http://localhost"
        )
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_body(self) -> dict:
        """读取请求体"""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def _require_admin(self) -> bool:
        """验证管理员权限"""
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"success": False, "message": "未授权访问"})
            return False
        token = auth[7:]
        conn = get_db()
        row = conn.execute("SELECT id FROM admin_tokens WHERE token = ?", (token,)).fetchone()
        conn.close()
        if not row:
            self._send_json(403, {"success": False, "message": "无效的管理员令牌"})
            return False
        return True

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        origin = self.headers.get("Origin", "")
        allowed = (
            origin
            if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")
            else "http://localhost"
        )
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        """处理 POST 请求"""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/activate":
            self._handle_activate()
        elif parsed.path == "/api/admin/generate":
            if self._require_admin():
                self._handle_admin_generate()
        elif parsed.path == "/api/admin/revoke":
            if self._require_admin():
                self._handle_admin_revoke()
        elif parsed.path == "/api/admin/blacklist":
            if self._require_admin():
                self._handle_admin_blacklist()
        elif parsed.path == "/api/admin/token":
            self._handle_admin_create_token()
        else:
            self._send_json(404, {"success": False, "message": "接口不存在"})

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/health":
            self._send_json(
                200, {"status": "ok", "server": "RSTao-Tool Activation Server", "version": "2.0"}
            )
        elif parsed.path == "/api/admin/codes":
            if self._require_admin():
                self._handle_admin_list_codes()
        elif parsed.path == "/api/admin/records":
            if self._require_admin():
                self._handle_admin_list_records()
        elif parsed.path == "/api/admin/blacklist":
            if self._require_admin():
                self._handle_admin_list_blacklist()
        else:
            self._send_json(404, {"success": False, "message": "接口不存在"})

    # ====================== 核心接口 ======================

    def _handle_activate(self):
        # 处理激活请求：POST /api/activate
        try:
            body = self._read_body()
            activation_code = body.get("activation_code", "").strip()
            device_fingerprint = body.get("device_fingerprint", "").strip()
            machine_code = body.get("machine_code", "").strip()
            machine_code_hash = body.get(
                "machine_code_hash", ""
            ).strip() or generate_machine_code_hash(machine_code)

            if not activation_code or not device_fingerprint:
                self._send_json(400, {"success": False, "message": "缺少必要参数"})
                return

            conn = get_db()

            # 1. 检查黑名单
            identifiers = [device_fingerprint, machine_code_hash, activation_code]
            for ident in identifiers:
                if ident:
                    row = conn.execute(
                        "SELECT id FROM blacklist WHERE identifier = ?", (ident,)
                    ).fetchone()
                    if row:
                        conn.close()
                        self._send_json(
                            403, {"success": False, "message": "该设备或激活码已被列入黑名单"}
                        )
                        return

            # 2. 查询激活码
            code_row = conn.execute(
                "SELECT * FROM activation_codes WHERE code = ? AND is_active = 1",
                (activation_code,),
            ).fetchone()

            if not code_row:
                conn.close()
                self._send_json(404, {"success": False, "message": "激活码无效或已作废"})
                return

            # 3. 检查激活次数限制
            if code_row["current_activations"] >= code_row["max_activations"]:
                conn.close()
                self._send_json(
                    403,
                    {
                        "success": False,
                        "message": f"激活码已达最大激活次数（{code_row['max_activations']}次）",
                    },
                )
                return

            # 4. 检查是否已激活过该设备
            existing = conn.execute(
                "SELECT id FROM activation_records WHERE activation_code = ? AND device_fingerprint = ?",
                (activation_code, device_fingerprint),
            ).fetchone()
            if existing:
                # 返回已有密钥
                record = conn.execute(
                    "SELECT license_key FROM activation_records WHERE id = ?", (existing["id"],)
                ).fetchone()
                conn.close()
                self._send_json(
                    200,
                    {
                        "success": True,
                        "message": "设备已激活，返回已有许可",
                        "license_key": record["license_key"],
                    },
                )
                return

            # 5. 计算过期时间
            license_type = code_row["license_type"]
            if license_type == "permanent":
                expire_dt = datetime(2099, 12, 31)
            elif license_type == "days":
                days = code_row["expire_days"] or 365
                expire_dt = datetime.now() + timedelta(days=days)
            elif license_type == "date":
                expire_str = code_row["expire_date"]
                expire_dt = (
                    datetime.strptime(expire_str, "%Y-%m-%d")
                    if expire_str
                    else datetime.now() + timedelta(days=365)
                )
            else:
                expire_dt = datetime.now() + timedelta(days=365)

            expire_ts = expire_dt.timestamp()
            expire_date_str = expire_dt.strftime("%Y-%m-%d %H:%M:%S")

            # 6. 生成 v2 签名授权，客户端只使用内置公钥验签
            private_key = load_private_key_from_env()
            if not private_key or not private_key_matches_public(private_key):
                conn.close()
                self._send_json(500, {"success": False, "message": "服务器授权私钥未配置或不匹配"})
                return
            payload = create_license_payload(
                machine_code=machine_code or device_fingerprint.split("_")[-1],
                expire_ts=expire_ts,
                license_type=license_type,
            )
            license_key = sign_license_payload(payload, private_key)

            # 7. 记录激活
            conn.execute(
                "INSERT INTO activation_records (activation_code, device_fingerprint, machine_code_hash, license_key, ip_address) VALUES (?, ?, ?, ?, ?)",
                (
                    activation_code,
                    device_fingerprint,
                    machine_code_hash,
                    license_key,
                    self.client_address[0],
                ),
            )
            conn.execute(
                "UPDATE activation_codes SET current_activations = current_activations + 1 WHERE code = ?",
                (activation_code,),
            )
            conn.commit()
            conn.close()

            print(
                f"[ACTIVATE] 激活成功 | 设备: {device_fingerprint[:16]}... | 过期: {expire_date_str}"
            )
            self._send_json(
                200,
                {
                    "success": True,
                    "message": "激活成功",
                    "license_key": license_key,
                    "expire_date": expire_date_str,
                },
            )

        except Exception as e:
            print(f"[ERROR] 激活失败: {e}")
            self._send_json(500, {"success": False, "message": f"服务器内部错误: {str(e)}"})

    # ====================== 管理接口 ======================

    def _handle_admin_generate(self):
        """生成激活码：POST /api/admin/generate"""
        body = self._read_body()
        license_type = body.get("license_type", "permanent")
        max_activations = int(body.get("max_activations", 1))
        expire_days = body.get("expire_days")
        expire_date = body.get("expire_date")
        notes = body.get("notes", "")

        # 生成16位激活码
        code = secrets.token_hex(8).upper()

        conn = get_db()
        conn.execute(
            "INSERT INTO activation_codes (code, license_type, max_activations, expire_days, expire_date, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (code, license_type, max_activations, expire_days, expire_date, notes),
        )
        conn.commit()
        conn.close()

        print(f"[ADMIN] 生成激活码: {code} | 类型: {license_type}")
        self._send_json(200, {"success": True, "code": code, "message": "激活码生成成功"})

    def _handle_admin_revoke(self):
        """作废激活码：POST /api/admin/revoke"""
        body = self._read_body()
        code = body.get("code", "").strip()
        if not code:
            self._send_json(400, {"success": False, "message": "缺少激活码"})
            return

        conn = get_db()
        conn.execute("UPDATE activation_codes SET is_active = 0 WHERE code = ?", (code,))
        conn.commit()
        conn.close()

        print(f"[ADMIN] 作废激活码: {code}")
        self._send_json(200, {"success": True, "message": "激活码已作废"})

    def _handle_admin_blacklist(self):
        """黑名单管理：POST /api/admin/blacklist"""
        body = self._read_body()
        action = body.get("action", "add")
        identifier = body.get("identifier", "").strip()
        reason = body.get("reason", "")

        if not identifier:
            self._send_json(400, {"success": False, "message": "缺少标识符"})
            return

        conn = get_db()
        if action == "add":
            conn.execute(
                "INSERT OR IGNORE INTO blacklist (identifier, reason) VALUES (?, ?)",
                (identifier, reason),
            )
            conn.commit()
            conn.close()
            print(f"[ADMIN] 添加黑名单: {identifier}")
            self._send_json(200, {"success": True, "message": f"已添加黑名单: {identifier}"})
        elif action == "remove":
            conn.execute("DELETE FROM blacklist WHERE identifier = ?", (identifier,))
            conn.commit()
            conn.close()
            print(f"[ADMIN] 移除黑名单: {identifier}")
            self._send_json(200, {"success": True, "message": f"已移除黑名单: {identifier}"})
        else:
            conn.close()
            self._send_json(400, {"success": False, "message": "无效操作，支持 add/remove"})

    def _handle_admin_create_token(self):
        """创建管理员令牌：POST /api/admin/token（首次无需鉴权）"""
        # 安全检查：如果已有token且无鉴权，则拒绝
        # 速率限制：每IP 每小时最多2次
        client_ip = self.client_address[0]
        now = time.time()
        rate_key = f"token_req_{client_ip}"
        if not hasattr(self.__class__, "_rate_limits"):
            self.__class__._rate_limits = {}
        if rate_key in self.__class__._rate_limits:
            last_time, count = self.__class__._rate_limits[rate_key]
            if now - last_time < 3600:
                if count >= 2:
                    self._send_json(429, {"success": False, "message": "请求过于频繁，请稍后再试"})
                    return
                self.__class__._rate_limits[rate_key] = (last_time, count + 1)
            else:
                self.__class__._rate_limits[rate_key] = (now, 1)
        else:
            self.__class__._rate_limits[rate_key] = (now, 1)

        conn = get_db()
        existing = conn.execute("SELECT COUNT(*) as cnt FROM admin_tokens").fetchone()
        if existing["cnt"] > 0:
            # 需要鉴权
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                conn.close()
                self._send_json(401, {"success": False, "message": "已有管理员，需要Bearer令牌"})
                return
            token = auth[7:]
            row = conn.execute("SELECT id FROM admin_tokens WHERE token = ?", (token,)).fetchone()
            if not row:
                conn.close()
                self._send_json(403, {"success": False, "message": "无效的管理员令牌"})
                return

        new_token = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO admin_tokens (token, description) VALUES (?, ?)", (new_token, "管理员令牌")
        )
        conn.commit()
        conn.close()
        print(f"[ADMIN] 创建管理员令牌")
        self._send_json(200, {"success": True, "token": new_token, "message": "请妥善保管此令牌"})

    def _handle_admin_list_codes(self):
        """列出激活码：GET /api/admin/codes"""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM activation_codes ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        conn.close()
        codes = [dict(r) for r in rows]
        self._send_json(200, {"success": True, "codes": codes})

    def _handle_admin_list_records(self):
        """列出激活记录：GET /api/admin/records"""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM activation_records ORDER BY activated_at DESC LIMIT 100"
        ).fetchall()
        conn.close()
        records = [dict(r) for r in rows]
        self._send_json(200, {"success": True, "records": records})

    def _handle_admin_list_blacklist(self):
        """列出黑名单：GET /api/admin/blacklist"""
        conn = get_db()
        rows = conn.execute("SELECT * FROM blacklist ORDER BY blocked_at DESC").fetchall()
        conn.close()
        blacklist = [dict(r) for r in rows]
        self._send_json(200, {"success": True, "blacklist": blacklist})


def run_server(port: int = ACTIVATION_SERVER_PORT):
    """启动激活服务器"""
    init_db()
    server = http.server.HTTPServer(
        ("127.0.0.1", port), ActivationHandler
    )  # localhost only for security
    print(f"=" * 50)
    print(f"  RSTao-Tool 激活服务器 v2.0")
    print(f"  监听端口: {port}")
    print(f"  健康检查: http://localhost:{port}/api/health")
    print(f"=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.shutdown()


if __name__ == "__main__":
    run_server()
