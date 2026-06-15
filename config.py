# -*- coding: utf-8 -*-
"""
WT Chat Translator — 配置常量
"""

# ── 游戏数据源 ──────────────────────
GAME_HOST = "localhost"
GAME_PORT = 8111
GAME_CHAT_URL = f"http://{GAME_HOST}:{GAME_PORT}/gamechat"
POLL_INTERVAL = 2          # 轮询间隔（秒）

# ── 翻译 API 设置（可在 settings.json 中覆盖） ──
TRANSLATION_BACKEND = "deepseek"       # deepseek / siliconflow(免费) / microsoft
TRANSLATION_API_KEY = ""              # API Key
AZURE_REGION = "eastasia"             # 仅 microsoft 后端需要
LLM_MODEL = "deepseek-v4-flash"       # 仅 LLM 后端（deepseek/siliconflow）

# 反向翻译的目标语言
TARGET_LANGS = {
    "英文": "en",
    "俄文": "ru",
}

# ── 显示设置 ──────────────────────
MAX_CHAT_LINES = 3          # 显示最近 N 条聊天消息
MAX_MSG_LENGTH = 200        # 单条消息最大显示字符数（超出截断）

# ── 窗口外观 ──────────────────────
WINDOW_TITLE = "WT 聊天翻译器"
WINDOW_WIDTH = 520
WINDOW_HEIGHT = 450
APPEARANCE_MODE = "dark"    # dark / light / system
COLOR_THEME = "blue"        # blue / green / dark-blue

# 字体
FONT_FAMILY = "Microsoft YaHei"
FONT_SIZE_ORIGINAL = 11     # 原文
FONT_SIZE_TRANSLATED = 13   # 译文
FONT_SIZE_INPUT = 12        # 输入框

# 颜色
COLOR_ORIGINAL = "#888888"        # 原文颜色（灰色）
COLOR_TRANSLATED = "#E0E0E0"      # 译文颜色（亮白）
COLOR_SEPARATOR = "#444444"       # 分隔线颜色
COLOR_WAITING = "#FFAA00"         # 等待连接提示颜色

# ── 用户配置文件 ──────────────────
import json, os, sys, time

def _app_dir():
    """获取应用根目录（兼容 PyInstaller exe 和直接运行脚本）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(__file__)

SETTINGS_FILE = os.path.join(_app_dir(), "settings.json")

DEFAULT_SETTINGS = {
    "translation_backend": TRANSLATION_BACKEND,
    "translation_api_key": TRANSLATION_API_KEY,
    "azure_region": AZURE_REGION,
    "llm_model": LLM_MODEL,
    "poll_interval": POLL_INTERVAL,
    "max_chat_lines": MAX_CHAT_LINES,
    "max_msg_length": MAX_MSG_LENGTH,
    "window_width": WINDOW_WIDTH,
    "window_height": WINDOW_HEIGHT,
    "game_host": GAME_HOST,
    "game_port": GAME_PORT,
}

def load_settings():
    """加载用户设置（若损坏或不存在则恢复默认）"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = {**DEFAULT_SETTINGS, **saved}
            return merged, False
        except (json.JSONDecodeError, ValueError, OSError):
            # 文件损坏 → 备份并重建
            backup = SETTINGS_FILE + f".{int(time.time())}.bak"
            os.rename(SETTINGS_FILE, backup)
    # 创建默认
    _atomic_save(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS), True

def save_settings(settings):
    """保存用户设置到文件（原子写入）"""
    _atomic_save(settings)

def _atomic_save(data):
    """temp + rename，防止写入中断导致文件损坏"""
    tmp = SETTINGS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def needs_save(settings):
    """内存中的设置是否与磁盘不同"""
    if not os.path.exists(SETTINGS_FILE):
        return True
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            disk = json.load(f)
    except Exception:
        return True
    return settings != disk

# 程序启动
settings, settings_just_created = load_settings()
