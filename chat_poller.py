# -*- coding: utf-8 -*-
"""
聊天轮询模块 — 从 War Thunder 8111 端口拉取聊天消息
支持断线检测和自动重连
"""

import json
import time
import threading
import requests

from config import settings

# 语言名 -> emoji 图标
LANG_FLAGS = {
    "en": "\U0001f1ec\U0001f1e7", "ru": "\U0001f1f7\U0001f1fa",
    "zh": "\U0001f1e8\U0001f1f3", "ja": "\U0001f1ef\U0001f1f5",
    "ko": "\U0001f1f0\U0001f1f7", "de": "\U0001f1e9\U0001f1ea",
    "fr": "\U0001f1eb\U0001f1f7", "es": "\U0001f1ea\U0001f1f8",
    "pt": "\U0001f1f5\U0001f1f9", "it": "\U0001f1ee\U0001f1f9",
    "pl": "\U0001f1f5\U0001f1f1", "tr": "\U0001f1f9\U0001f1f7",
}


class ChatPoller:
    """后台轮询 8111 端口，新消息通过 callback 推送到 GUI"""

    def __init__(self, on_new_message, on_status_change=None):
        """
        on_new_message:    callable(msg_dict)
        on_status_change:  callable(is_connected: bool)
        """
        self.on_new_message = on_new_message
        self.on_status_change = on_status_change
        self.last_id = 0
        self._running = False
        self._connected = False
        self._thread = None
        self._fail_count = 0
        self._max_fail = 5  # 连续失败多少次判定为断开
        # 注：以下变量在 CPython GIL 下线程安全，无需显式 Lock

    @property
    def base_url(self):
        host = settings.get("game_host", "localhost")
        port = settings.get("game_port", 8111)
        return f"http://{host}:{port}/gamechat"

    @property
    def is_connected(self):
        return self._connected

    def start(self):
        """启动后台轮询线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止轮询（等待线程结束）"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def reset(self):
        """重置 lastId，重新拉取全部消息"""
        self.last_id = 0

    def _poll_loop(self):
        interval = settings.get("poll_interval", 2)

        while self._running:
            try:
                url = f"{self.base_url}?lastId={self.last_id}"
                resp = requests.get(url, timeout=3)

                if resp.status_code == 200:
                    self._fail_count = 0
                    if not self._connected:
                        self._connected = True
                        self._notify_status(True)

                    messages = resp.json()
                    if isinstance(messages, list):
                        for msg in messages:
                            self.last_id = max(self.last_id, msg.get("id", 0))
                            self.on_new_message(msg)

                elif resp.status_code == 404:
                    # 游戏正在运行但未进入对战 — 不算断开
                    self._fail_count = 0
                    self.last_id = 0  # 重置：新对战的 ID 从 0 开始
                    if not self._connected:
                        self._connected = True
                        self._notify_status(True)

                else:
                    self._on_fail()

            except (requests.ConnectionError, requests.Timeout):
                self._on_fail()
            except json.JSONDecodeError as e:
                # Malformed response body — the HTTP connection is healthy,
                # so do NOT increment fail_count. Just skip this poll cycle.
                print(f"[chat_poller] JSON decode error (skipping): {e}")
            except (KeyError, TypeError) as e:
                # Unexpected response structure — also not a connection problem.
                print(f"[chat_poller] Response structure error (skipping): {e}")
            except Exception:
                self._on_fail()

            # 断线后退避等待
            delay = interval
            if self._fail_count > 0:
                delay = min(interval + self._fail_count * 2, 30)
            time.sleep(delay)

    def _on_fail(self):
        self._fail_count += 1
        if self._fail_count >= self._max_fail and self._connected:
            self._connected = False
            self._notify_status(False)

    def _notify_status(self, connected):
        if self.on_status_change:
            try:
                self.on_status_change(connected)
            except RuntimeError:
                # Tkinter may raise RuntimeError when the widget is destroyed
                # during shutdown; this is benign and can be silenced.
                pass
            except Exception:
                import traceback
                print("[chat_poller] Unhandled exception in on_status_change callback:")
                traceback.print_exc()


def get_lang_flag(lang_code: str) -> str:
    """语言代码 -> emoji 国旗"""
    return LANG_FLAGS.get(lang_code, "\U0001f310")
