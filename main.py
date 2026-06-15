# -*- coding: utf-8 -*-
"""
WT Chat Translator — 入口

用法:
    python main.py              # 启动翻译窗口
    pythonw main.py             # 无黑色控制台窗口
    python main.py --no-poll    # 仅反向翻译，不连接游戏
"""

import sys
import tkinter as tk

from config import settings, settings_just_created, save_settings, needs_save


def main():
    # 仅首次或配置变化时写入
    if settings_just_created or needs_save(settings):
        try:
            save_settings(settings)
        except (IOError, OSError) as e:
            print(f"无法写入配置文件: {e}", file=sys.stderr)
            sys.exit(1)

    from gui import TranslatorApp
    from chat_poller import ChatPoller

    try:
        app = TranslatorApp()
    except tk.TclError as e:
        print(
            "\n无法初始化图形界面。\n"
            "本程序需要图形显示环境才能运行。\n"
            "请直接在桌面运行（不要通过远程桌面/SSH 无会话模式）。\n"
            f"\n错误详情: {e}\n",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"启动失败: {e}", file=sys.stderr)
        sys.exit(1)

    if "--no-poll" not in sys.argv:
        poller = ChatPoller(
            on_new_message=app.on_new_message,
            on_status_change=app.on_connection_change,
        )
        poller.start()

        def on_close():
            app._shutting_down = True
            poller.stop()
            app._executor.shutdown(wait=False)
            app.destroy()

        app.root.protocol("WM_DELETE_WINDOW", on_close)

    app.mainloop()


if __name__ == "__main__":
    main()
