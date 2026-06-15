# MurasamePet Client

MurasamePet Client 是一个 PyQt 桌面宠物应用。它直接调用外部 OpenAI 兼容接口完成角色对话、角色生成、桌面视觉观察、长期记忆和本地工具调用，不依赖本地服务端。

## 功能概览

- 桌面宠物窗口：置顶显示、拖拽、文本输入、摸头互动、系统托盘菜单。
- 角色系统：内置角色设置工作台，可生成角色卡、立绘和情绪图。
- 对话回复：按角色卡、人设、记忆和最近上下文生成简短中文回复。
- 视觉观察：启用后按配置间隔读取屏幕，默认 30 秒一次。
- 长期记忆：保存文字对话和桌面观察摘要，后续回复前检索注入。
- Native tool calls：把本地能力作为 `tools` 发给模型，由模型按需连续调用。
- 本地工具：网页搜索、桌面文件整理、图片删除确认、屏幕读取、摄像头拍照。

## 运行

需要 Python `>=3.10,<3.13`。推荐使用 `uv`：

```bash
uv sync
uv run python -m scripts.pet_app
```

Windows 下也可以直接使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m scripts.pet_app
```

API key 支持两种方式：

```bash
export API_KEY="your_api_key"
```

或在应用数据目录放置 `apikey.md`，内容为 API key。开发模式下，项目根目录中的 `apikey.md` 会被复制到用户数据目录。

首次启动时，如果没有角色卡，应用会自动打开角色设置窗口。完成角色生成并应用后，配置会写入用户数据目录的 `config.json`。

## 操作

- 左键上半部分：拖动或触发摸头互动。
- 左键下半部分 / 回车：开始输入。
- 系统托盘菜单：角色设置、重新生成人设图、清空本轮对话、清空长期记忆、退出。
- 出现工具确认时：使用鼠标点击“同意 / 拒绝”，或用上下键切换、回车确认、Esc 拒绝。

## 配置

默认配置来自 `Murasame/utils.py` 中的 `DEFAULT_CONFIG`，运行时会合并到用户数据目录的 `config.json`。

关键字段：

- `enable_vl`: 是否启用桌面视觉观察。
- `client.timeout_seconds`: 外部 API 超时时间。
- `vl.model`: 多模态观察模型，默认 `qwen3-vl-flash`。
- `vl.interval_seconds`: 屏幕观察间隔，最低 5 秒，默认 30 秒。
- `vl.max_width`: 截图上传前最大宽度。
- `vl.jpeg_quality`: 截图 JPEG 质量，范围 35-95。
- `display.preset`: 显示预设，可选 `compact`、`balanced`、`standard`、`full`、`custom`。
- `memory.enabled`: 是否启用长期记忆。
- `memory.top_k`: 每次回复检索的记忆条数。
- `memory.storage_path`: 本地 JSONL 记忆文件路径。
- `agent_tools.enabled`: 是否启用本地工具。
- `agent_tools.desktop_root`: 桌面工具允许操作的根目录，默认 `~/Desktop`。
- `agent_tools.delete_requires_confirmation`: 删除类操作是否要求用户确认。
- `character.*`: 当前角色卡、情绪图、外貌标签、性格标签和用户称呼。

## API 模型

模型常量在 `scripts/workbench/constants.py`：

- `API_BASE_URL`: 外部 API 基址。
- `DESCRIPTION_MODEL`: 普通文本对话、整理计划和角色描述模型。
- `IMAGE_MODEL`: 角色图片生成模型。

普通对话使用 `DESCRIPTION_MODEL`。屏幕读取、桌面图片匹配和摄像头照片分析使用 `vl.model`。接口请求使用 OpenAI 兼容的 chat completions 格式，包括多模态 `image_url` 和 native `tools`。

角色回复期望模型输出 JSON：

```json
{
  "text": "回复文本",
  "emotion": "happy"
}
```

`emotion` 支持 `happy`、`angry`、`shy`、`sad`。屏幕观察还可以返回 `desktop_summary`，用于长期记忆，不直接展示给用户。

## Native Tools

工具定义和执行逻辑在 `scripts/pet_tools.py`。`scripts/pet_api.py` 会把工具 schema 发送给模型，并在模型返回 `tool_calls` 后执行工具。工具结果会继续回传给模型，支持连续调用，最多 6 轮，避免无限循环。

当前工具：

- `open_google_search`: 打开 Google 搜索结果页。
- `organize_desktop`: 枚举桌面直接文件，移动到固定白名单分类文件夹。
- `find_desktop_images_for_trash`: 生成桌面图片缩略图索引，用视觉模型匹配图片，返回待确认的废纸篓计划。
- `read_screen`: 读取当前屏幕截图并生成观察摘要。定时桌面观察也通过该工具完成。
- `take_camera_shot`: 使用 OpenCV 从摄像头拍照，保存到 `~/Pictures/shot.jpg`，并把图片发回模型继续分析。

安全边界：

- 桌面文件工具只处理 `agent_tools.desktop_root` 下的直接文件。
- 不递归处理文件夹。
- 分类目标必须来自固定白名单。
- 删除不会直接执行；模型只能生成待确认计划，用户确认后才移到废纸篓。
- 摄像头工具只在模型明确调用 `take_camera_shot` 时运行。

## 打包

同步 build extra 后运行：

```bash
uv sync --extra build
uv run python -m scripts.build_executable
```

Windows 下可使用：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_executable
```

常用参数：

```bash
python -m scripts.build_executable --onefile
python -m scripts.build_executable --console
python -m scripts.build_executable --dry-run
```

默认输出：

- Windows: `dist/MurasamePet/MurasamePet.exe`
- macOS: `dist/MurasamePet.app`

打包不会内置 `apikey.md`。发布版本需要用户通过环境变量或应用数据目录提供 API key。

## 项目结构

- `scripts/pet_app.py`: 应用入口、窗口、托盘、屏幕 worker 启动。
- `scripts/pet_widget.py`: 桌宠窗口、输入、绘制和工具确认交互。
- `scripts/pet_api.py`: API client、对话流程、工具循环、记忆写入。
- `scripts/pet_tools.py`: native tool schema 和本地工具执行。
- `scripts/desktop_tools.py`: 桌面文件、安全路径、截图和浏览器搜索辅助函数。
- `scripts/memory_runtime.py`: 长期记忆检索和本地 JSONL 兜底。
- `scripts/workbench/`: 角色生成工作台。
- `Murasame/`: 本地图层合成立绘和配置路径工具。

## 平台权限

- 屏幕读取可能需要系统屏幕录制权限。
- 摄像头拍照可能需要摄像头权限。
- macOS 打包应用的数据目录通常在 `~/Library/Application Support/MurasamePet/`。
- Windows 打包应用的数据目录通常在 `%APPDATA%\MurasamePet\`。
