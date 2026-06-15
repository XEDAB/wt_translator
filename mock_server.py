# -*- coding: utf-8 -*-
"""
模拟 War Thunder 8111 端口服务器 — 用于离线测试

用法：
    python mock_server.py              # 默认端口 8111
    python mock_server.py 8112         # 自定义端口

测试数据：模拟国际服多人聊天（中/英/俄/日/韩多语种）
"""

import json
import time
import threading
import random
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8111

# ── 测试聊天数据 ──────────────────────────────────────
CHAT_MESSAGES = []  # 共享 list，线程安全由 GIL 保护


def _next_id():
    """Generate a time-based monotonically-increasing message ID.

    Mimics the real War Thunder 8111 API where message IDs are roughly
    monotonic with time.  The random suffix prevents collisions when two
    messages are generated within the same millisecond.
    """
    return int(time.time() * 1000) + random.randint(0, 999)


# 初始种子消息
SEED_MESSAGES = [
    {"msg": "hi", "sender": "Tsuki_Kirei", "enemy": False, "mode": "所有人"},
    {"msg": "pve?", "sender": "Tsuki_Kirei", "enemy": False, "mode": "所有人"},
    {"msg": "yes", "sender": "xiafancao", "enemy": True, "mode": "所有人"},
    {"msg": "注意该坐标位置！[D1]", "sender": "diandian226", "enemy": False, "mode": "友军"},
    {"msg": "Attack point A!", "sender": "Deathskyz", "enemy": False, "mode": "友军"},
    {"msg": "Привет всем", "sender": "Ivan_99", "enemy": True, "mode": "所有人"},
    {"msg": "进攻 A 点！", "sender": "不动的大图书馆", "enemy": False, "mode": "友军"},
    {"msg": "我炸H1机场 油库", "sender": "Tsuki_Kirei", "enemy": False, "mode": "所有人"},
    {"msg": "H1 runway is black now", "sender": "Deathskyz", "enemy": False, "mode": "所有人"},
    {"msg": "このゲームは面白い", "sender": "Tanaka_J5", "enemy": True, "mode": "所有人"},
    {"msg": "안녕하세요 팀", "sender": "Kim_AF", "enemy": True, "mode": "所有人"},
    {"msg": "居民区还是要炸的", "sender": "Tsuki_Kirei", "enemy": False, "mode": "所有人"},
    {"msg": "Guten Tag", "sender": "Hans_Panzer", "enemy": True, "mode": "所有人"},
    {"msg": "Самолёт сбит! Выхожу", "sender": "Ivan_99", "enemy": True, "mode": "所有人"},
    {"msg": "Thanks for the cover!", "sender": "Deathskyz", "enemy": False, "mode": "友军"},
]


def init_messages():
    """初始化基础消息"""
    base_time = int(time.time()) - len(SEED_MESSAGES) * 15
    for i, m in enumerate(SEED_MESSAGES):
        mid = _next_id()
        CHAT_MESSAGES.append({
            "id": mid,
            "msg": m["msg"],
            "sender": m["sender"],
            "enemy": m["enemy"],
            "mode": m["mode"],
            "time": base_time + i * 15 + random.randint(0, 9),
        })


NEW_MSGS_POOL = [
    ("Need help at B3!", "Deathskyz", False, "友军"),
    ("收到，马上来", "不动的大图书馆", False, "友军"),
    ("Nice kill!", "Tsuki_Kirei", False, "所有人"),
    ("Вас сбили?", "Ivan_99", True, "所有人"),
    ("Да, PGZ09 попал", "Sokol_RU", True, "所有人"),
    ("Watch out for SPAA at C4", "Deathskyz", False, "友军"),
    ("小心防空!", "diandian226", False, "友军"),
    ("Bombing sector F6", "Tsuki_Kirei", False, "所有人"),
    ("Good luck everyone", "Deathskyz", False, "所有人"),
    ("GG wp", "xiafancao", True, "所有人"),
    ("敵機発見！北から接近中", "Tanaka_J5", True, "所有人"),
    ("Понял, отступаю", "Sokol_RU", True, "所有人"),
    ("机场修好了，可以降落了", "Tsuki_Kirei", False, "友军"),
    ("Copy that, landing", "Deathskyz", False, "友军"),
]


def inject_random_message():
    """后台线程：每隔一段时间注入一条模拟消息"""
    while True:
        time.sleep(random.randint(20, 40))  # 20-40 秒一次，模拟真实聊天节奏
        msg = random.choice(NEW_MSGS_POOL)
        mid = _next_id()
        CHAT_MESSAGES.append({
            "id": mid,
            "msg": msg[0],
            "sender": msg[1],
            "enemy": msg[2],
            "mode": msg[3],
            "time": int(time.time()),
        })
        line = msg[0][:40]
        print(f"  [mock] injected #{mid}: {line}")


# ── HTTP Handler ──────────────────────────────────────


class MockHandler(BaseHTTPRequestHandler):
    # Match the real War Thunder 8111 server which runs on CivetWeb
    server_version = "CivetWeb/1.15"
    sys_version = ""

    def do_GET(self):
        path = self.path.split("?")[0]
        params = {}
        if "?" in self.path:
            from urllib.parse import parse_qs, urlparse
            params = parse_qs(urlparse(self.path).query)

        if path == "/gamechat":
            last_id = int(params.get("lastId", [0])[0])
            # 只返回 id > lastId 的消息
            new_msgs = [m for m in CHAT_MESSAGES if m["id"] > last_id]
            self._json_response(new_msgs)

        elif path == "/map_obj.json":
            self._json_response(_make_map_objects())

        elif path == "/map_info.json":
            self._json_response({
                "grid_size": [65536.0, 65536.0],
                "grid_steps": [8192.0, 8192.0],
                "grid_zero": [-32768.0, 32768.0],
                "map_generation": 3,
                "map_max": [32768.0, 32768.0],
                "map_min": [-32768.0, -32768.0],
                "valid": True,
            })

        elif path == "/mission.json":
            self._json_response({
                "objectives": [
                    {"primary": True, "status": "in_progress", "text": "摧毁敌方载具部队：C6"},
                    {"primary": True, "status": "undefined", "text": "保护我方侦察机：A2"},
                ],
                "status": "running",
            })

        elif path == "/indicators":
            self._json_response({
                "valid": True, "army": "air", "type": "su_34",
                "speed": 0.85, "altitude_hour": 5432,
                "compass": 180.0, "g_meter": 2.5, "aoa": 5.3,
            })

        elif path == "/state":
            self._json_response({
                "valid": True, "H, m": 5432, "TAS, km/h": 1100,
                "IAS, km/h": 850, "M": 0.92,
            })

        elif path == "/hudmsg":
            last_evt = int(params.get("lastEvt", [0])[0])
            last_dmg = int(params.get("lastDmg", [0])[0])
            self._json_response({"events": [], "damage": []})

        else:
            self._json_response({"error": "not found"}, 404)

    def _json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # 客户端断开，正常行为

    def log_message(self, format, *args):
        # 精简日志
        print(f"  [{args[0]}] {args[1]} {args[2]}")


def _make_map_objects():
    """生成模拟地图对象（采样）"""
    return [
        {"type": "aircraft", "color": "#043FFF", "blink": 2, "icon": "Player",
         "x": 0.5, "y": 0.6, "dx": 0.0, "dy": 1.0},
        {"type": "airfield", "color": "#174DFF", "blink": 0, "icon": "none",
         "sx": 0.92, "sy": 0.89, "ex": 0.88, "ey": 0.90},
        {"type": "ground_model", "color": "#f00C00", "icon": "SPAA",
         "x": 0.3, "y": 0.4},
    ]


# ── 启动 ──────────────────────────────────────────────


def main():
    print("Mock War Thunder Server")
    print(f"   URL: http://localhost:{PORT}")
    print(f"   Endpoints: /gamechat, /map_obj.json, /map_info.json, /mission.json, /indicators, /state, /hudmsg")
    print()

    init_messages()
    print(f"   [init] {len(CHAT_MESSAGES)} seed messages loaded")

    # 后台注入线程
    injector = threading.Thread(target=inject_random_message, daemon=True)
    injector.start()

    try:
        server = HTTPServer(("0.0.0.0", PORT), MockHandler)
    except OSError:
        print(f"\n   错误：端口 {PORT} 已被占用，无法启动服务器。")
        print(f"   请检查 War Thunder 是否正在运行（游戏占用端口 8111），"
              f"或使用其他端口：python mock_server.py 8112")
        sys.exit(1)

    print(f"   服务器已启动，按 Ctrl+C 停止")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n   服务器已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
