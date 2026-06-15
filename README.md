# WT Chat Translator

War Thunder 游戏聊天实时翻译工具。读取 `localhost:8111` 接口，自动翻译游戏内聊天消息为中文，支持翻译消息为俄语/英语并复制

## 功能

- 实时显示最近 3 条游戏聊天 → 自动翻译为中文
- 手动输入中文 → 翻译为英文或俄文，一键复制
- 多后端：DeepSeek V4 / 硅基流动（免费）/ Microsoft Translator
- 自带 `mock_server.py` 离线测试

## 使用

```bash
pip install requests
python main.py
```

首次运行在设置中填入 API Key：[DeepSeek](https://platform.deepseek.com) / [硅基流动](https://cloud.siliconflow.cn) / [Azure Translator](https://portal.azure.com)

## 文件

```
├── main.py           # 入口
├── gui.py            # tkinter 窗口
├── chat_poller.py    # 8111 轮询 + 断线重连
├── translator.py     # 翻译（LLM + 离线语言检测）
├── config.py         # 配置 + settings.json
├── mock_server.py    # 本地模拟 8111
├── run.bat           # 双击启动（无控制台）
└── requirements.txt  # requests
```

## 测试

```bash
python mock_server.py      # 终端 1
python main.py             # 终端 2（设置中端口改为 8112）
```

## 打包

```bash
python -m PyInstaller --onefile --noconsole --name "WT_Chat_Translator" main.py
```

## 鸣谢

8111 API 信息来源 [lucasvmx/WarThunder-localhost-documentation](https://github.com/lucasvmx/WarThunder-localhost-documentation)
