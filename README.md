# MurasamePet Client

这是 MurasamePet 的桌面客户端。客户端只负责本机交互和展示，不再加载 LLM、Qwen-VL、GPT-SoVITS 或任何模型权重。

## 职责边界

客户端保留：

- PyQt 桌宠窗口、置顶、拖拽、托盘菜单。
- 文本输入、摸头事件、屏幕截图采集。
- HTML/CSS/JS 角色生成工作台，通过 PyQt WebEngine 承载。
- 服务端生成的人设图展示。
- 本地立绘图层合成兜底。
- 播放服务端返回的音频。
- 调用远端 MurasamePet Server API。

客户端不再包含：

- FastAPI 服务。
- Qwen / Qwen-VL / MLX / PyTorch / LoRA 模型加载。
- GPT-SoVITS 服务和预训练模型。
- ModelScope 下载脚本。
- OpenRouter/Ollama 路由逻辑。
- 翻译、情绪识别、TTS、表情层选择等 AI 编排逻辑。
- 外貌、人设、性格、身份、立绘生成逻辑。

## 运行

先启动 MurasamePet Server，并确认服务端提供：

```http
GET /v1/character/options
POST /v1/character/generate
GET /v1/character/{character_id}
POST /v1/character/regenerate-image
POST /v1/pet/respond
```

安装客户端依赖并启动：

```bash
uv sync
uv run python pet.py
```

首次没有配置 `character.character_id` 时，客户端会打开角色生成工作台。先选择外貌、性格、身份、画风和称呼，点击“生成预览”查看角色名、人设文本、问候语和人设图，确认后点击“应用角色”才会保存到本地配置并切换桌宠。

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
    },
    "character": {
        "character_id": null,
        "user_name": "用户",
        "auto_open_creator": true
    }
}
```

字段说明：

- `enable_vl`: 是否允许客户端采集屏幕截图并发送给服务端。
- `client.api_base_url`: MurasamePet Server 地址。
- `client.session_id`: 会话标识，服务端可据此维护上下文。
- `client.timeout_seconds`: 请求超时时间。
- `display.preset`: 桌宠显示预设，可选 `compact`、`balanced`、`standard`、`full`、`custom`。
- `character.character_id`: 当前使用的服务端角色 ID；为空时首次启动会打开角色设置窗口。
- `character.user_name`: 用户称呼，会显示在输入气泡中，并随请求传给服务端。
- `character.auto_open_creator`: 没有角色 ID 时是否自动打开角色设置窗口。

## 服务端接口约定

客户端启动时调用：

```http
GET /v1/character/options
```

用于获取可选外貌、性格、身份和画风。角色生成调用：

```http
POST /v1/character/generate
```

请求示例：

```json
{
    "session_id": "local-user",
    "user_name": "用户",
    "appearance_traits": ["棕发", "蓝瞳", "中长发", "校服", "清纯"],
    "personality_traits": ["温柔治愈系", "认真优等生系"],
    "identity_traits": ["同班同学"],
    "style": "anime_desktop_pet",
    "constraints": {
        "transparent_background": true,
        "safe_for_work": true
    }
}
```

响应示例：

```json
{
    "character_id": "char_xxx",
    "name": "小雨",
    "persona": "角色设定文本",
    "greeting": "你好呀。",
    "display_image_url": "/v1/character/char_xxx/image/main.png",
    "session_id": "local-user"
}
```

已有角色读取调用：

```http
GET /v1/character/{character_id}
```

对话调用：

```http
POST /v1/pet/respond
```

请求示例：

```json
{
    "session_id": "local-user",
    "character_id": "char_xxx",
    "user_name": "用户",
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
    "character_name": "小雨",
    "display_image_url": "/v1/character/char_xxx/image/expression_happy.png",
    "audio_url": "/v1/audio/xxx.wav",
    "audio_base64": null,
    "session_id": "local-user"
}
```

`audio_url` 和 `audio_base64` 二选一即可；如果都没有，客户端只显示文本和切换表情。
`display_image_url`、`display_image_base64` 和旧版 `expression_layers` 都可用于切换角色图像；优先级为生成图高于本地图层。

## 项目结构

```text
.
├── pet.py                  # 桌面客户端入口
├── character_workbench.py  # HTML 工作台容器和 Python bridge
├── ui/                     # 角色生成工作台 HTML/CSS/JS
├── config.json             # 客户端配置
├── Murasame/
│   ├── generate.py         # 本地 PNG 图层合成
│   └── utils.py            # 读取客户端配置
├── fgimages/               # 立绘图层素材
├── icon.png                # 托盘图标
├── plan.md                 # 改造计划和 API 约定
└── 思源黑体Bold.otf         # 显示字体
```

## macOS 权限

如果启用视觉功能，需要给运行 `pet.py` 的终端或 Python 授予屏幕录制权限：

系统设置 -> 隐私与安全性 -> 屏幕录制。
