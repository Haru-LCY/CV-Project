# 从固定丛雨桌宠改造成可选萌属性的人设桌宠计划

## 总结

当前客户端已经从本地模型逻辑中拆出，只负责 PyQt 展示、输入、截图、音频播放和 API 调用。本次改造的目标是把固定角色“丛雨”扩展为可配置角色：用户选择外貌、性格、身份、画风和称呼后，由服务端生成人设与人设图，客户端保存 `character_id` 并在后续对话、摸头、屏幕上下文事件中携带该角色上下文。

AI 编排、性格生成、图像生成、表情选择、TTS、视觉理解等缺失逻辑全部由服务端 API 提供，客户端不加载任何模型权重。

## 已实现的客户端改造

- 新增角色配置：`config.json` 的 `character.character_id`、`character.user_name`、`character.auto_open_creator`。
- 新增角色 API 客户端方法：
  - `GET /v1/character/options`
  - `POST /v1/character/generate`
  - `GET /v1/character/{character_id}`
  - `POST /v1/character/regenerate-image`
  - `POST /v1/pet/respond` 增加 `character_id` 和 `user_name`
- 新增 HTML/CSS/JS 角色生成工作台，`character_workbench.py` 只作为 PyQt WebEngine 容器和 Python bridge。
- 工作台支持选择外貌、性格、身份、画风和用户称呼，并预览角色名、问候语、人设文本和人设图。
- `pet.py` 只负责桌宠入口、托盘菜单、对话请求和展示逻辑，不再内嵌工作台 UI 实现。
- 角色生成改为两阶段：先 `生成预览`，确认后再 `应用角色` 并写入本地配置。
- 桌宠类从固定 `Murasame` 改为通用 `DesktopPet`，展示名称来自当前角色。
- 服务端返回 `display_image_url` 或 `display_image_base64` 时优先展示生成图；没有生成图时保留旧 `expression_layers` 本地图层兜底。
- 托盘菜单新增 `角色设置`、`重新生成人设图`、`清空记忆`、`退出`。

## 服务端接口约定

`GET /v1/character/options` 返回：

```json
{
    "appearance_traits": ["棕发", "蓝瞳", "中长发", "校服", "清纯"],
    "personality_traits": ["温柔治愈系", "认真优等生系"],
    "identity_traits": ["同班同学", "学妹", "图书委员"],
    "styles": ["anime_desktop_pet"],
    "defaults": {
        "appearance_traits": ["棕发", "蓝瞳", "中长发", "校服", "清纯"],
        "personality_traits": ["温柔治愈系", "认真优等生系"],
        "identity_traits": ["同班同学"],
        "style": "anime_desktop_pet"
    }
}
```

`POST /v1/character/generate` 请求：

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

响应：

```json
{
    "character_id": "char_xxx",
    "name": "角色名",
    "persona": "角色设定文本",
    "greeting": "初始问候语",
    "display_image_url": "/v1/character/char_xxx/image/main.png",
    "session_id": "local-user"
}
```

`POST /v1/pet/respond` 请求在原字段基础上增加：

```json
{
    "character_id": "char_xxx",
    "user_name": "用户"
}
```

响应优先返回：

```json
{
    "text": "回复文本",
    "character_name": "角色名",
    "display_image_url": "/v1/character/char_xxx/image/expression_happy.png",
    "audio_url": "/v1/audio/xxx.wav",
    "session_id": "local-user"
}
```

兼容旧响应字段：

```json
{
    "expression_layers": [1717, 1475, 1261]
}
```

## 后续服务端工作

- 实现外貌、性格、身份标签到 persona prompt 的生成逻辑。
- 实现透明背景人设图生成，并保证输出适合桌宠展示的 PNG/WebP。
- 实现角色持久化，支持通过 `character_id` 读取人设、图片和会话状态。
- 在 `/v1/pet/respond` 中根据角色人设生成回复、表情图或旧版 `expression_layers`、音频。
- 为 `regenerate-image` 保持同一人设，只重生图像，不重置记忆。

## 测试计划

- 启动时没有 `character_id`：展示旧图层兜底，并自动弹出角色设置窗口。
- 角色生成预览成功：弹窗显示角色名、人设文本、问候语和人设图，但还不修改当前桌宠。
- 点击应用角色：`config.json` 写入 `character_id` 和 `user_name`，桌宠切换到生成图和角色名。
- 取消弹窗：不写入配置，不修改当前桌宠。
- 对话、摸头、屏幕上下文：请求体都携带 `character_id` 和 `user_name`。
- 服务端返回图片：客户端下载并缓存到系统临时目录后展示。
- 服务端只返回旧 `expression_layers`：客户端继续用 `fgimages` 合成立绘。
- 服务端不可用：客户端不崩溃，角色设置窗口使用本地默认选项，生成失败时弹出错误提示。
