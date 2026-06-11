# MurasamePet Client

这是一个 PyQt 桌宠客户端。项目不再调用本地 MurasamePet Server；角色生成和对话回复都由客户端直接调用外部 API。

## 功能

- PyQt 桌宠窗口、置顶、拖拽、托盘菜单。
- 文本输入、摸头事件和桌面上下文定时事件。
- HTML/CSS/JS 角色生成工作台，通过 PyQt WebEngine 承载。
- 直接调用 `deepseek-v4-flash` 生成人设描述和桌宠回复。
- 启用 `enable_vl` 时，低频截取桌面并调用 `qwen3-vl-flash` 生成桌面观察回复。
- 直接调用 `gemini-3.1-flash-image-preview` 生成角色立绘和情感图。
- 角色卡、人设图 base64 和用户称呼保存到 `config.json`。
- 没有生成图时，使用 `fgimages` 本地图层合成立绘兜底。

项目不再包含或依赖：

- 本地 MurasamePet Server。
- FastAPI 服务。
- GPT-SoVITS 或服务端音频接口。
- 本地服务端角色和对话接口。

## 运行

准备 API key，二选一：

```bash
export API_KEY="your_api_key"
```

或在项目根目录创建 `apikey.md`，写入 API key。

安装依赖并启动：

```bash
uv sync
uv run python pet.py
```

首次没有角色卡时，客户端会打开角色生成工作台。选择外貌、性格、身份、画风和称呼后点击“生成预览”，确认后点击“应用角色”，角色卡会保存到 `config.json`，后续对话会按该角色卡的语气回复。

## 配置

`config.json` 示例：

```json
{
    "enable_vl": true,
    "client": {
        "session_id": "local-user",
        "timeout_seconds": 120
    },
    "vl": {
        "model": "qwen3-vl-flash",
        "interval_seconds": 30,
        "max_width": 1280,
        "jpeg_quality": 75
    },
    "display": {
        "preset": "balanced"
    },
    "character": {
        "character_id": null,
        "name": "丛雨",
        "persona": "",
        "greeting": "主人，你好呀！",
        "display_image_base64": null,
        "emotion_images": null,
        "appearance_traits": null,
        "personality_traits": null,
        "identity_traits": null,
        "style": null,
        "user_name": "用户",
        "auto_open_creator": true
    }
}
```

字段说明：

- `enable_vl`: 是否启用桌面视觉观察。启用后会低频截取桌面并上传到视觉模型接口。
- `client.session_id`: 本地会话标识。
- `client.timeout_seconds`: 外部 API 请求超时时间。
- `vl.model`: 桌面视觉观察使用的模型，默认 `qwen3-vl-flash`。
- `vl.interval_seconds`: 桌面观察间隔秒数，最低按 5 秒处理。
- `vl.max_width`: 截图上传前的最大宽度，超过会等比压缩。
- `vl.jpeg_quality`: 截图 JPEG 压缩质量，范围按 35-95 处理。
- `display.preset`: 桌宠显示预设，可选 `compact`、`balanced`、`standard`、`full`、`custom`。
- `character.*`: 当前角色卡、图片、情感图和生成选项。
- `character.user_name`: 用户称呼，会显示在输入气泡中，也会传给回复 API。
- `character.auto_open_creator`: 没有角色卡时是否自动打开角色设置窗口。

## API 使用

角色生成和对话回复共用 `character_workbench.py` 中的：

- `API_BASE_URL`
- `DESCRIPTION_MODEL`
- `IMAGE_MODEL`

普通对话会使用 `DESCRIPTION_MODEL`。桌面视觉观察会沿用同一个 `API_BASE_URL` 和 API key，使用 `vl.model`，并按 OpenAI 兼容多模态格式发送截图 `image_url`。

对话回复会把当前角色名、人设、问候语、用户称呼和最近对话历史放入提示词，并要求 API 返回：

```json
{
    "text": "回复文本",
    "emotion": "happy"
}
```

`emotion` 可为 `happy`、`angry`、`shy`、`sad`。如果当前角色卡保存了对应情感图，桌宠会切换到对应图片。
