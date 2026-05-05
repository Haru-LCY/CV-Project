# MurasamePet Client

这是 MurasamePet 的桌面客户端。客户端只负责本机交互和展示，不再加载 LLM、Qwen-VL、GPT-SoVITS 或任何模型权重。

## 职责边界

客户端保留：

- PyQt 桌宠窗口、置顶、拖拽、托盘菜单。
- 文本输入、摸头事件、屏幕截图采集。
- 本地立绘图层合成和展示。
- 播放服务端返回的音频。
- 调用远端 MurasamePet Server API。

客户端不再包含：

- FastAPI 服务。
- Qwen / Qwen-VL / MLX / PyTorch / LoRA 模型加载。
- GPT-SoVITS 服务和预训练模型。
- ModelScope 下载脚本。
- OpenRouter/Ollama 路由逻辑。
- 翻译、情绪识别、TTS、表情层选择等 AI 编排逻辑。

## 运行

先启动 MurasamePet Server，并确认服务端提供：

```http
POST /v1/pet/respond
```

安装客户端依赖并启动：

```bash
uv sync
uv run python pet.py
```

## 配置

编辑 `config.json`：

```json
{
    "enable_vl": true,
    "client": {
        "api_base_url": "http://127.0.0.1:28565",
        "session_id": "local-user",
        "timeout_seconds": 120
    },
    "display": {
        "preset": "balanced"
    }
}
```

字段说明：

- `enable_vl`: 是否允许客户端采集屏幕截图并发送给服务端。
- `client.api_base_url`: MurasamePet Server 地址。
- `client.session_id`: 会话标识，服务端可据此维护上下文。
- `client.timeout_seconds`: 请求超时时间。
- `display.preset`: 桌宠显示预设，可选 `compact`、`balanced`、`standard`、`full`、`custom`。

## 服务端接口约定

客户端调用：

```http
POST /v1/pet/respond
```

请求示例：

```json
{
    "session_id": "local-user",
    "event": "user_text",
    "text": "你好",
    "screenshot": null
}
```

`event` 可为：

- `user_text`: 用户主动输入。
- `head_touch`: 摸头交互。
- `screen_context`: 屏幕截图上下文。

响应示例：

```json
{
    "text": "主人，找本座有什么事呀？",
    "expression_layers": [1717, 1475, 1261],
    "audio_url": "/v1/audio/xxx.wav",
    "audio_base64": null,
    "session_id": "local-user"
}
```

`audio_url` 和 `audio_base64` 二选一即可；如果都没有，客户端只显示文本和切换表情。

## 项目结构

```text
.
├── pet.py                  # 桌面客户端入口
├── config.json             # 客户端配置
├── Murasame/
│   ├── generate.py         # 本地 PNG 图层合成
│   └── utils.py            # 读取客户端配置
├── fgimages/               # 立绘图层素材
├── icon.png                # 托盘图标
└── 思源黑体Bold.otf         # 显示字体
```

## macOS 权限

如果启用视觉功能，需要给运行 `pet.py` 的终端或 Python 授予屏幕录制权限：

系统设置 -> 隐私与安全性 -> 屏幕录制。
