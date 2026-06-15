# WT Chat Translator — Bug 分析与修复

> 排除 #6（翻译 API 无重试机制），共 14 项问题。

---

## #1 [严重] `_translation_threads` 死代码

**文件**: `main.py:56`  
**问题**: `on_close` 中 `getattr(app, "_translation_threads", [])` 的 `_translation_threads` 从未被赋值，始终为空列表，等待逻辑完全不生效。关闭窗口时翻译线程被直接杀死。

**修复**: 删除死代码，直接依赖 `ThreadPoolExecutor.shutdown`：

```python
def on_close():
    app._shutting_down = True
    poller.stop()
    app._executor.shutdown(wait=True, timeout=8)
    app.destroy()
```

---

## #2 [中等] 手动翻译绕过线程池

**文件**: `gui.py:290`  
**问题**: `_on_translate_click` 用 `threading.Thread` 直接启动翻译，不受 `_executor` 管理，快速连续点击会创建大量瞬时线程。

**修复**: 统一提交到 `_executor`：

```python
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
```

---

## #3 [中等] `max_lines` 闭包陈旧引用

**文件**: `gui.py:226-228`  
**问题**: `_append_message` 中 `max_lines` 在回调入队时捕获，回调执行时若设置已变，仍使用旧值。

**修复**: 回调内重新读取：

```python
def _append_message(self, msg_dict, original, translated):
    entry = {...}
    self.recent_messages.append(entry)
    if len(self.recent_messages) > settings.get("max_chat_lines", 3):
        self.recent_messages = self.recent_messages[-settings.get("max_chat_lines", 3):]
    self._refresh_msgs()
```

---

## #4 [低] 关闭时多余 UI 更新

**文件**: `gui.py:204`  
**问题**: `_process_pending` 尾部 `after(500)` 回调可能在 `_shutting_down = True` 之后执行，虽然函数体开头有检查，但在此之前状态栏已被设为"已连接"。

**修复**: 将 status 更新移到 `_shutting_down` 检查之后：

```python
def _process_pending(self):
    if self._shutting_down:
        return
    with self._lock:
        msgs = self._pending_messages[:]
        self._pending_messages.clear()
    if msgs:
        self.status_label.configure(text="已连接 ", fg=GOOD)
        for msg in msgs:
            self._executor.submit(self._translate_and_add, msg)
    self.root.after(500, self._process_pending)
```

---

## #5 [严重] DeepSeek API URL 可能非标准

**文件**: `translator.py:29`  
**问题**: URL 为 `https://api.deepseek.com/chat/completions`，缺少 `/v1/` 前缀。官方 OpenAI 兼容端点为 `https://api.deepseek.com/v1/chat/completions`，当前 URL 可能随时失效。

**修复**:

```python
"url": "https://api.deepseek.com/v1/chat/completions",
```

---

## #7 [中等] 消息截断在翻译之前

**文件**: `gui.py:215-216`  
**问题**: 原文被截断后才送入翻译器，可能在单词中间断开，导致翻译质量下降。

**修复**: 先翻译再截断显示：

```python
def _translate_and_add(self, msg_dict):
    original = msg_dict.get("msg", "").strip()
    if not original:
        return
    translated = translate_to_chinese(original)
    self.root.after(0, lambda: self._append_message(msg_dict, original, translated))

def _append_message(self, msg_dict, original, translated):
    max_len = settings.get("max_msg_length", 200)
    display_original = original[:max_len] + "..." if len(original) > max_len else original
    display_translated = translated[:max_len] + "..." if len(translated) > max_len else translated
    # 用 display_original / display_translated 渲染
```

---

## #8 [中等] 翻译缓存不含后端信息

**文件**: `translator.py:179, 205`  
**问题**: 缓存 key 仅含文本和目标语言，切换后端后旧缓存仍被命中，不同后端产出不同译文时用户看到的是旧结果。

**修复**: 将后端名称加入缓存 key：

```python
cache_key = f"{backend}:to_cn:{text}"
cache_key = f"{backend}:from_cn:{target_lang}:{text}"
```

---

## #9 [低] 缓存淘汰代码可读性差

**文件**: `translator.py:194, 220`  
**问题**: `_cache_to_cn.pop(next(iter(_cache_to_cn)))` 依赖 Python 3.7+ 字典插入顺序实现 FIFO，语义不明显。

**修复**: 改用 `collections.OrderedDict`：

```python
from collections import OrderedDict
_cache_to_cn = OrderedDict()

def translate_to_chinese(text: str) -> str:
    ...
    if len(_cache_to_cn) >= MAX_CACHE_SIZE:
        _cache_to_cn.popitem(last=False)
    _cache_to_cn[cache_key] = result
```

---

## #10 [中等] 失败阈值硬编码 + `max_fail` 死代码

**文件**: `chat_poller.py:71, 121`  
**问题**: `_poll_loop` 中定义了 `max_fail = 5` 但从未使用；`_on_fail` 中阈值 `5` 硬编码。修改 `max_fail` 不会生效。

**修复**: 提取为实例属性，统一引用：

```python
def __init__(self, ...):
    ...
    self._max_fail = 5

def _on_fail(self):
    self._fail_count += 1
    if self._fail_count >= self._max_fail and self._connected:
        ...
```

删除 `_poll_loop` 中的 `max_fail = 5`。

---

## #11 [低] 线程间共享变量无同步

**文件**: `chat_poller.py:87-88`  
**问题**: `last_id`、`_connected`、`_fail_count` 在轮询线程写入，主线程可读，无显式同步。在 CPython GIL 下实际安全，但代码层面不严谨。

**修复**: 添加 `threading.Lock` 保护读写，或在注释中明确标注依赖 CPython GIL。

---

## #12 [中等] 原子写入残留 `.tmp` 文件

**文件**: `config.py:96-101`  
**问题**: `os.replace` 失败时 `.tmp` 不会被清理，多次失败会累积垃圾文件。

**修复**: 添加 `finally` 清理：

```python
def _atomic_save(data):
    tmp = SETTINGS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
```

---

## #13 [低] 备份文件命名 TOCTOU

**文件**: `config.py:82-87`  
**问题**: 递增后缀 `.bak1` / `.bak2` 的 while 检查存在极低概率的竞态。

**修复**: 改用时间戳避免冲突：

```python
import time
backup = SETTINGS_FILE + f".{int(time.time())}.bak"
```

---

## #14 [中等] 纯汉字日文误判为中文

**文件**: `translator.py:237-238`  
**问题**: 检测顺序 `ru → zh → ja → ko → en`，日文汉字和中文汉字范围重叠，不含假名的日文（如 `"敵機発見"`）被误判为 zh。

**修复**: 优先检测假名，缩小中文判断范围：

```python
ja = sum(1 for c in text if '\u3040' <= c <= '\u30ff')  # 假名
if ja > 0:
    return "ja"
zh = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
if zh > n * 0.3:
    return "zh"
```

---

## #15 [低] 韩文 Unicode 范围写法不规范

**文件**: `translator.py:234`  
**问题**: `'힯'` (U+D7AF) 不是标准韩文音节上限，标准上限为 `'힣'` (U+D7A3)。

**修复**:

```python
ko = sum(1 for c in text if '가' <= c <= '힣')
```