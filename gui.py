# -*- coding: utf-8 -*-
"""
GUI 模块 — tkinter 原生控件，暗色主题，grid 网格布局
"""

import tkinter as tk
from tkinter import messagebox
import threading
import concurrent.futures

from config import settings, save_settings, TARGET_LANGS, WINDOW_TITLE
from translator import translate_to_chinese, translate_from_chinese, detect_language
from chat_poller import get_lang_flag

# ── 颜色方案 ──────────────────────────────
BG   = "#2b2b2b"   # 主背景
BG2  = "#333333"   # 次级背景（输入框、结果区）
BG3  = "#1e1e1e"   # 更深背景（消息区）
FG   = "#d0d0d0"   # 主文字
FG2  = "#a0a0a0"   # 次要文字
ACC  = "#ff8800"   # 强调色
GOOD = "#44cc66"   # 连接成功
BLUE = "#6699dd"   # 友方
RED  = "#ee5555"   # 敌方


class TranslatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        w = settings.get("window_width", 520)
        h = settings.get("window_height", 450)
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(280, 240)
        self.root.configure(bg=BG)

        self._wrap_width = 420  # 动态更新
        self._resize_after_id = None  # 防抖
        self._canvas_resize_after_id = None
        self._shutting_down = False
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="translator")
        self._settings_dlg = None  # 防止同时打开多个设置窗口

        self.recent_messages = []
        self._pending_messages = []
        self._lock = threading.Lock()
        self._last_translation = ""

        self._build_ui()

        # 窗口大小变化时动态更新 wraplength
        self.root.bind("<Configure>", self._on_resize)
        self.msg_canvas.bind("<Configure>", self._on_canvas_resize)

        self._process_pending()

    def _on_resize(self, event):
        """窗口大小变化时更新文字换行宽度（防抖，扣除同行按钮宽度）"""
        if event.widget == self.root:
            # settings_btn ~52px + copy_btn ~50px + 间距 ~10px = ~112px
            self._wrap_width = max(120, event.width - 60 - 112)
            if self._resize_after_id is not None:
                self.root.after_cancel(self._resize_after_id)
            self._resize_after_id = self.root.after(80, self._apply_resize_wrap)

    def _apply_resize_wrap(self):
        self._resize_after_id = None
        if self.placeholder.winfo_exists():
            self.placeholder.configure(wraplength=self._wrap_width)
        self.result_label.configure(wraplength=self._wrap_width)

    def _on_canvas_resize(self, event):
        """Canvas 宽度变化时让 inner frame 匹配（防抖）"""
        if self._canvas_resize_after_id is not None:
            self.root.after_cancel(self._canvas_resize_after_id)
        self._canvas_resize_after_id = self.root.after(80, lambda w=event.width: self._apply_canvas_resize(w))

    def _apply_canvas_resize(self, width):
        self._canvas_resize_after_id = None
        self.msg_canvas.itemconfigure("inner", width=width)

    # ════════════════════════════════════════════
    #  UI 构建
    # ════════════════════════════════════════════

    def _build_ui(self):
        # ── 消息标题栏 ──
        header = tk.Frame(self.root, bg=BG2)
        header.pack(fill="x", padx=6, pady=(6, 0))

        tk.Label(header, text="  游戏聊天消息", bg=BG2, fg=FG,
                 font=("Microsoft YaHei", 10, "bold")).pack(side="left", pady=4)

        self.status_label = tk.Label(header, text="等待游戏连接 ",
                                     bg=BG2, fg=ACC,
                                     font=("Microsoft YaHei", 8))
        self.status_label.pack(side="right", padx=8, pady=4)

        # ── 底部区域（输入 + 设置按钮，先 pack 防止缩小窗口时被剪裁） ──
        bottom_container = tk.Frame(self.root, bg=BG)
        bottom_container.pack(side="bottom", fill="x", padx=6, pady=(0, 6))

        # ── 消息滚动区（最后 pack，缩小窗口时先压缩这里） ──
        msg_bg = tk.Frame(self.root, bg=BG3, bd=0)
        msg_bg.pack(fill="both", expand=True, padx=6, pady=0)

        self.msg_canvas = tk.Canvas(msg_bg, bg=BG3, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(msg_bg, orient="vertical", command=self.msg_canvas.yview,
                          bg=BG2, troughcolor=BG3, activebackground=BG2)
        self.msg_inner = tk.Frame(self.msg_canvas, bg=BG3)
        self.msg_inner.bind("<Configure>",
            lambda e: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all")))
        self.msg_canvas.create_window((0, 0), window=self.msg_inner, anchor="nw", tags="inner")
        self.msg_canvas.configure(yscrollcommand=sb.set)
        self.msg_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 没消息时的提示
        self.placeholder = tk.Label(self.msg_inner,
            text="等待 War Thunder 进入对战...\n游戏聊天消息将显示在此处并翻译为中文",
            bg=BG3, fg="#555555", font=("Microsoft YaHei", 10), justify="center")
        self.placeholder.pack(pady=40)

        # ── 输入区（两行布局） ──
        input_frame = tk.Frame(bottom_container, bg=BG)
        input_frame.pack(fill="x")

        # Row 1: 输入框 + 翻译按钮 + 语言选择
        row1 = tk.Frame(input_frame, bg=BG)
        row1.pack(fill="x", pady=(0, 3))

        self.input_entry = tk.Entry(row1, bg=BG2, fg=FG, insertbackground=FG,
                                     font=("Microsoft YaHei", 10), relief="flat", bd=0)
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 4))
        self.input_entry.bind("<Return>", lambda e: self._on_translate_click())

        self.translate_btn = tk.Button(row1, text="翻译", bg=BG2, fg=FG,
                                        font=("Microsoft YaHei", 9),
                                        command=self._on_translate_click,
                                        relief="flat", bd=0, padx=12, pady=3,
                                        activebackground="#555555", activeforeground=FG)
        self.translate_btn.pack(side="right", padx=(4, 0))

        self.lang_var = tk.StringVar(value="英文")
        for label, code in TARGET_LANGS.items():
            tk.Radiobutton(row1, text=label, variable=self.lang_var, value=label,
                           bg=BG, fg=FG, selectcolor=BG2,
                           activebackground=BG, activeforeground=FG,
                           font=("Microsoft YaHei", 9),
                           command=self._on_translate_click).pack(side="right", padx=(4, 0))

        # Row 2: 译文结果 + 复制 + 设置
        row2 = tk.Frame(input_frame, bg=BG)
        row2.pack(fill="x")

        self.result_label = tk.Label(row2, text="译文将显示在此处",
                                      bg=BG2, fg="#777777",
                                      font=("Microsoft YaHei", 10),
                                      anchor="w", justify="left",
                                      wraplength=self._wrap_width, padx=6, pady=3)
        self.result_label.pack(side="left", fill="x", expand=True)

        self.settings_btn = tk.Button(row2, text="设置", bg=BG2, fg=FG2,
                                       font=("Microsoft YaHei", 8),
                                       command=self._open_settings,
                                       relief="flat", bd=0, padx=8, pady=2,
                                       activebackground="#555555", activeforeground=FG)
        self.settings_btn.pack(side="right", padx=(2, 0))

        self.copy_btn = tk.Button(row2, text="复制", bg=BG2, fg=FG2,
                                   font=("Microsoft YaHei", 8),
                                   command=self._on_copy_result,
                                   relief="flat", bd=0, padx=8, pady=2,
                                   activebackground="#555555", activeforeground=FG2)
        self.copy_btn.pack(side="right", padx=(2, 0))

    # ════════════════════════════════════════════
    #  消息处理
    # ════════════════════════════════════════════

    def on_new_message(self, msg_dict):
        with self._lock:
            self._pending_messages.append(msg_dict)
            if len(self._pending_messages) > 100:
                self._pending_messages = self._pending_messages[-100:]

    def on_connection_change(self, connected):
        """8111 连接状态变化回调（来自子线程，用 after 转主线程）"""
        self.root.after(0, lambda: self._set_status(connected))

    def _set_status(self, connected):
        if connected:
            self.status_label.configure(text="已连接 ", fg=GOOD)
        else:
            self.status_label.configure(text="连接断开 ", fg=RED)

    def _process_pending(self):
        if self._shutting_down:
            return
        with self._lock:
            msgs = self._pending_messages[:]
            self._pending_messages.clear()
        if msgs and not self._shutting_down:
            self.status_label.configure(text="已连接 ", fg=GOOD)
            for msg in msgs:
                if self._shutting_down:
                    break
                self._executor.submit(self._translate_and_add, msg)
        self.root.after(500, self._process_pending)

    def _translate_and_add(self, msg_dict):
        """子线程中执行翻译，完成后由主线程更新列表"""
        if self._shutting_down:
            return
        original = msg_dict.get("msg", "").strip()
        if not original:
            return

        translated = translate_to_chinese(original)
        if self._shutting_down:
            return
        self.root.after(0, lambda: self._append_message(msg_dict, original, translated))

    def _append_message(self, msg_dict, original, translated):
        """主线程更新消息列表（线程安全）"""
        max_len = settings.get("max_msg_length", 200)
        display_original = original[:max_len] + "..." if len(original) > max_len else original
        display_translated = translated[:max_len] + "..." if len(translated) > max_len else translated

        entry = {"msg_dict": msg_dict, "original": display_original, "translated": display_translated}
        self.recent_messages.append(entry)
        max_lines = settings.get("max_chat_lines", 3)
        if len(self.recent_messages) > max_lines:
            self.recent_messages = self.recent_messages[-max_lines:]
        self._refresh_msgs()

    def _refresh_msgs(self):
        if self.placeholder.winfo_exists():
            self.placeholder.pack_forget()
        for w in self.msg_inner.winfo_children():
            w.destroy()

        for entry in self.recent_messages:
            md = entry["msg_dict"]
            original = entry["original"]
            translated = entry["translated"]
            lang = detect_language(original)
            flag = get_lang_flag(lang)

            item = tk.Frame(self.msg_inner, bg=BG3)
            item.pack(fill="x", pady=(6, 0))

            # 发送者名 + 频道
            sender = md.get("sender", "?")
            is_enemy = md.get("enemy", False)
            sc = RED if is_enemy else BLUE
            mode = md.get("mode", "")
            header_text = f"  {sender}"
            if mode:
                header_text += f" [{mode}]"
            tk.Label(item, text=header_text, bg=BG3, fg=sc,
                     font=("Microsoft YaHei", 8, "bold"), anchor="w").pack(anchor="w")

            # 原文
            tk.Label(item, text=f"  {flag} [{lang.upper()}] {original}",
                     bg=BG3, fg=FG2, font=("Microsoft YaHei", 9),
                     anchor="w", wraplength=420, justify="left").pack(anchor="w")

            # 译文
            tk.Label(item, text=f"  {translated}",
                     bg=BG3, fg=FG, font=("Microsoft YaHei", 11),
                     anchor="w", wraplength=420, justify="left").pack(anchor="w")

            # 分隔线
            tk.Frame(item, bg="#444444", height=1).pack(fill="x", pady=(6, 0))

        self.msg_canvas.yview_moveto(1.0)

    # ════════════════════════════════════════════
    #  用户操作
    # ════════════════════════════════════════════

    def _on_translate_click(self):
        text = self.input_entry.get().strip()
        if not text:
            return
        target_code = TARGET_LANGS.get(self.lang_var.get(), "en")
        self.result_label.configure(text="翻译中...", fg=ACC)
        self._executor.submit(self._do_translate_and_show, text, target_code)

    def _do_translate_and_show(self, text, target_code):
        result = translate_from_chinese(text, target_code)
        display = result or "[空译文]"
        color = FG if result else FG2
        self.root.after(0, lambda d=display, c=color: self.result_label.configure(text=d, fg=c))

    def _on_copy_result(self):
        text = self.result_label.cget("text")
        if text and text not in ("译文将显示在此处", "翻译中..."):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
            except tk.TclError:
                self.copy_btn.configure(text="复制失败", fg=RED)
                self.root.after(2000, lambda: self.copy_btn.configure(text="复制", fg=FG2))
                return
            self.copy_btn.configure(text="已复制", fg=GOOD)
            self.root.after(2000, lambda: self.copy_btn.configure(text="复制", fg=FG2))

    def mainloop(self):
        self.root.mainloop()

    def destroy(self):
        self._executor.shutdown(wait=False)
        self.root.destroy()

    # ════════════════════════════════════════════
    #  设置对话框（纯 tkinter，无 ttk）
    # ════════════════════════════════════════════

    def _open_settings(self):
        if self._settings_dlg and self._settings_dlg.winfo_exists():
            self._settings_dlg.lift()
            return
        dlg = tk.Toplevel(self.root)
        self._settings_dlg = dlg
        dlg.title("设置")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        dlg.grab_set()

        def _on_settings_close():
            self._settings_dlg = None
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", _on_settings_close)

        # 使用 grid 布局
        padx = (16, 8); pady = 6

        # --- 翻译后端 ---
        tk.Label(dlg, text="翻译后端:", bg=BG, fg=FG, font=("Microsoft YaHei", 9),
                 anchor="e").grid(row=0, column=0, sticky="e", padx=padx, pady=pady)

        backend_var = tk.StringVar(value=settings.get("translation_backend", "deepseek"))
        be = tk.OptionMenu(dlg, backend_var, "deepseek", "siliconflow", "microsoft",
                           command=lambda _: None)
        be.configure(bg=BG2, fg=FG, font=("Microsoft YaHei", 9),
                     relief="flat", bd=0, activebackground=BG2, activeforeground=FG,
                     indicatoron=False, width=18, anchor="w")
        be["menu"].configure(bg=BG2, fg=FG, font=("Microsoft YaHei", 9),
                             activebackground="#555555", activeforeground=FG,
                             relief="flat", bd=0)
        be.grid(row=0, column=1, sticky="ew", pady=pady)

        # --- API Key ---
        tk.Label(dlg, text="API Key:", bg=BG, fg=FG, font=("Microsoft YaHei", 9),
                 anchor="e").grid(row=1, column=0, sticky="e", padx=padx, pady=pady)

        key_var = tk.StringVar(value=settings.get("translation_api_key", ""))
        tk.Entry(dlg, textvariable=key_var, show="*", width=40,
                 bg=BG2, fg=FG, insertbackground=FG, relief="flat", bd=0,
                 font=("Consolas", 9)).grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=pady, ipady=3)

        # --- 动态标签（根据后端切换） ---
        extra_label = tk.Label(dlg, text="模型:", bg=BG, fg=FG,
                               font=("Microsoft YaHei", 9), anchor="e")
        extra_label.grid(row=2, column=0, sticky="e", padx=padx, pady=pady)

        extra_val = settings.get("llm_model", "") or settings.get("azure_region", "deepseek-v4-flash")
        extra_var = tk.StringVar(value=extra_val)
        extra_entry = tk.Entry(dlg, textvariable=extra_var, width=26,
                               bg=BG2, fg=FG, insertbackground=FG,
                               relief="flat", bd=0, font=("Consolas", 9))
        extra_entry.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=pady, ipady=3)

        def _on_backend_change(*args):
            """切换后端时更新标签和占位文本"""
            bk = backend_var.get()
            if bk == "microsoft":
                extra_label.configure(text="Azure Region:")
                sv = settings.get("azure_region", "eastasia")
            else:
                extra_label.configure(text="模型:")
                sv = settings.get("llm_model", "deepseek-v4-flash")
            extra_var.set(sv)

        backend_var.trace_add("write", _on_backend_change)

        # --- 轮询间隔 ---
        tk.Label(dlg, text="轮询间隔(秒):", bg=BG, fg=FG, font=("Microsoft YaHei", 9),
                 anchor="e").grid(row=3, column=0, sticky="e", padx=padx, pady=pady)

        poll_var = tk.StringVar(value=str(settings.get("poll_interval", 2)))
        tk.Entry(dlg, textvariable=poll_var, width=26,
                 bg=BG2, fg=FG, insertbackground=FG, relief="flat", bd=0,
                 font=("Microsoft YaHei", 10)).grid(row=3, column=1, sticky="ew", padx=(0, 16), pady=pady, ipady=3)

        # --- 显示消息数 ---
        tk.Label(dlg, text="显示消息数:", bg=BG, fg=FG, font=("Microsoft YaHei", 9),
                 anchor="e").grid(row=4, column=0, sticky="e", padx=padx, pady=pady)

        lines_var = tk.StringVar(value=str(settings.get("max_chat_lines", 3)))
        tk.Entry(dlg, textvariable=lines_var, width=26,
                 bg=BG2, fg=FG, insertbackground=FG, relief="flat", bd=0,
                 font=("Microsoft YaHei", 10)).grid(row=4, column=1, sticky="ew", padx=(0, 16), pady=pady, ipady=3)

        # --- 保存/取消 ---
        bf = tk.Frame(dlg, bg=BG)
        bf.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 12))

        def on_save():
            settings["translation_backend"] = backend_var.get()
            settings["translation_api_key"] = key_var.get()
            ev = extra_var.get().strip()
            if backend_var.get() == "microsoft":
                settings["azure_region"] = ev
            else:
                settings["llm_model"] = ev if ev else "deepseek-v4-flash"

            # 输入校验（不再悄悄吞错）
            try:
                pv = float(poll_var.get())
                if pv < 0.5:
                    raise ValueError
                settings["poll_interval"] = pv
            except ValueError:
                messagebox.showwarning("输入错误", "轮询间隔请输入 >= 0.5 的数字", parent=dlg)
                return

            try:
                lv = int(lines_var.get())
                if lv < 1:
                    raise ValueError
                settings["max_chat_lines"] = lv
            except ValueError:
                messagebox.showwarning("输入错误", "显示消息数请输入 >= 1 的整数", parent=dlg)
                return

            save_settings(settings)
            # 立即应用新消息数
            if len(self.recent_messages) > lv:
                self.recent_messages = self.recent_messages[-lv:]
            self._refresh_msgs()
            _on_settings_close()

        tk.Button(bf, text="保存", command=on_save, bg=BG2, fg=FG,
                  font=("Microsoft YaHei", 10), relief="flat", bd=0,
                  padx=20, pady=4,
                  activebackground="#555555", activeforeground=FG).pack(side="right", padx=4)
        tk.Button(bf, text="取消", command=_on_settings_close, bg=BG, fg=FG2,
                  font=("Microsoft YaHei", 10), relief="flat", bd=0,
                  padx=16, pady=4,
                  activebackground="#555555", activeforeground=FG2).pack(side="right", padx=4)

        # 让 column 1 可扩展
        dlg.columnconfigure(1, weight=1)
