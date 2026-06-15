from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from Murasame import utils
from scripts.character_runtime import parse_reply_content
from scripts.desktop_tools import (
    ALLOWED_CATEGORY_FOLDERS,
    build_image_contact_sheet,
    capture_desktop_data_uri,
    list_desktop_files,
    metadata_for_entries,
    move_files,
    open_google_search,
    selected_entries,
)
from scripts.workbench.constants import DESCRIPTION_MODEL


PostChat = Callable[..., Any]


@dataclass
class ToolExecution:
    name: str
    result: dict[str, Any]
    action: dict | None = None
    desktop_summary: str = ""
    image_url: str = ""
    image_prompt: str = ""


def native_tools_for_event(event: str) -> list[dict[str, Any]]:
    read_screen_tool = {
        "type": "function",
        "function": {
            "name": "read_screen",
            "description": "读取当前桌面截图并返回可见内容摘要。定时桌面观察事件应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "可选。希望重点观察的内容，例如当前任务、窗口、文档或用户提到的目标。",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    }
    if event == "screen_context":
        return [read_screen_tool]
    if event != "user_text":
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": "open_google_search",
                "description": "当用户明确要求搜索、查询或打开网页搜索时，用浏览器打开 Google 搜索结果页。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "要搜索的关键词或问题，不包含额外寒暄。",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "organize_desktop",
                "description": "按用户要求整理桌面直接文件，把文件移动到固定白名单分类文件夹。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": "用户的整理要求。工具会自行读取桌面直接文件并生成安全移动计划。",
                        }
                    },
                    "required": ["instruction"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_desktop_images_for_trash",
                "description": "查找桌面上符合描述的图片文件，返回待用户确认的移入废纸篓计划；工具不会直接删除。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "要查找并准备移入废纸篓的图片内容描述。",
                        }
                    },
                    "required": ["description"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_camera_shot",
                "description": "当用户要求看看摄像头、拍照、自拍或用相机观察时，调用默认摄像头拍摄一张照片并交给模型查看。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "camera_index": {
                            "type": "integer",
                            "description": "摄像头编号，默认 0。",
                        },
                        "warmup_frames": {
                            "type": "integer",
                            "description": "拍摄前丢弃的预热帧数，默认 10。",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        read_screen_tool,
    ]


def tool_choice_for_event(event: str, has_screenshot: bool) -> str | dict[str, Any] | None:
    if event == "screen_context" and has_screenshot:
        return {"type": "function", "function": {"name": "read_screen"}}
    return "auto"


def tool_call_name(tool_call: dict[str, Any]) -> str:
    function = tool_call.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return str(tool_call.get("name") or "")


def tool_call_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function")
    raw_arguments = function.get("arguments") if isinstance(function, dict) else tool_call.get("arguments")
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str) or not raw_arguments.strip():
        return {}
    try:
        data = json.loads(raw_arguments)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


class PetToolExecutor:
    def __init__(self, desktop_root: Path, vl_model: str, post_chat: PostChat) -> None:
        self.desktop_root = desktop_root
        self.vl_model = vl_model
        self._post_chat = post_chat

    def execute(self, tool_call: dict[str, Any], screenshot_base64: str | None) -> ToolExecution:
        name = tool_call_name(tool_call)
        arguments = tool_call_arguments(tool_call)
        try:
            if name == "open_google_search":
                return ToolExecution(name, self._open_google_search(str(arguments.get("query") or "")))
            if name == "organize_desktop":
                return ToolExecution(name, self._organize_desktop(str(arguments.get("instruction") or "")))
            if name == "find_desktop_images_for_trash":
                result, action = self._plan_desktop_image_trash(str(arguments.get("description") or ""))
                return ToolExecution(name, result, action=action)
            if name == "read_screen":
                result = self._read_screen(str(arguments.get("focus") or ""), screenshot_base64)
                summary = str(result.get("desktop_summary") or result.get("observation") or "").strip()
                return ToolExecution(name, result, desktop_summary=summary)
            if name == "take_camera_shot":
                result, image_url = self._take_camera_shot(
                    arguments.get("camera_index"),
                    arguments.get("warmup_frames"),
                )
                prompt = "这是 take_camera_shot 工具刚刚通过摄像头拍摄的照片。请结合这张图片和用户请求继续回复。"
                return ToolExecution(name, result, image_url=image_url, image_prompt=prompt)
        except Exception as exc:
            return ToolExecution(name, {"status": "error", "message": f"{type(exc).__name__}: {exc}"})
        return ToolExecution(name, {"status": "error", "message": f"未知工具：{name}"})

    def _open_google_search(self, query: str) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {"status": "error", "message": "搜索内容不能为空。"}
        url = open_google_search(query)
        return {"status": "success", "message": f"已打开网页搜索：{query}", "query": query, "url": url}

    def _plan_desktop_image_trash(self, description: str) -> tuple[dict[str, Any], dict | None]:
        image_entries = list_desktop_files(self.desktop_root, images_only=True)
        if not image_entries:
            return {"status": "empty", "message": "桌面上没有可识别的图片文件。"}, None
        sheet = build_image_contact_sheet(image_entries)
        if not sheet:
            return {"status": "error", "message": "桌面图片缩略图生成失败，没有删除任何东西。"}, None

        query = description.strip() or "用户要求删除的图片"
        prompt = f"""
你需要从一张桌面图片缩略图索引表中，找出符合用户描述的图片编号。
用户描述：{query}
候选文件：
{json.dumps(metadata_for_entries(image_entries), ensure_ascii=False)}

只输出 JSON，不要 Markdown。格式：
{{"matches": [{{"id": 1, "confidence": 0.0, "reason": "简短理由"}}]}}
规则：
- 只有图片内容明显符合描述时才加入 matches。
- confidence 取 0 到 1。
- 不确定时返回空 matches。
""".strip()
        response = self._post_chat(
            self.vl_model,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": sheet}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            temperature=0.1,
        )
        content = response.json()["choices"][0]["message"].get("content") or ""
        data = parse_reply_content(content)
        matches = data.get("matches") if isinstance(data, dict) else []
        ids: list[int] = []
        if isinstance(matches, list):
            for match in matches:
                if not isinstance(match, dict):
                    continue
                try:
                    confidence = float(match.get("confidence", 0))
                    match_id = int(match.get("id"))
                except (TypeError, ValueError):
                    continue
                if confidence >= 0.65:
                    ids.append(match_id)
        selected = selected_entries(image_entries, ids)
        if not selected:
            return {
                "status": "no_match",
                "message": "没找到足够确定符合描述的图片，没有删除任何东西。",
                "description": query,
            }, None

        files = [{"name": entry.name, "path": str(entry.path)} for entry in selected]
        action = {"type": "trash_files", "files": files}
        return {
            "status": "requires_confirmation",
            "message": f"找到了 {len(files)} 个可能符合描述的图片，需要用户确认后才会移到废纸篓。",
            "description": query,
            "files": [{"name": file_info["name"]} for file_info in files],
        }, action

    def _organize_desktop(self, instruction: str) -> dict[str, Any]:
        entries = list_desktop_files(self.desktop_root, images_only=False)
        if not entries:
            return {"status": "empty", "message": "桌面上没有需要整理的直接文件。"}
        prompt = f"""
你是桌面文件整理器。请根据用户要求、文件名和扩展名，把桌面文件移动到固定分类文件夹。
用户要求：{instruction}
允许的分类文件夹：{sorted(ALLOWED_CATEGORY_FOLDERS)}
文件列表：
{json.dumps(metadata_for_entries(entries), ensure_ascii=False)}

只输出 JSON，不要 Markdown。格式：
{{"moves": [{{"source": "原文件名.ext", "category": "图片"}}]}}
规则：
- source 必须完全等于文件列表中的 name。
- category 必须来自允许的分类文件夹。
- 不要移动不确定的文件。
- 不要创建允许列表外的文件夹。
""".strip()
        response = self._post_chat(
            DESCRIPTION_MODEL,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.json()["choices"][0]["message"].get("content") or ""
        data = parse_reply_content(content)
        moves = data.get("moves") if isinstance(data, dict) else []
        if not isinstance(moves, list):
            moves = []
        moved = move_files(self.desktop_root, moves)
        if not moved:
            return {"status": "no_moves", "message": "没有生成安全可执行的整理计划，所以没有移动文件。"}
        categories = sorted({target.parent.name for _, target in moved})
        return {
            "status": "success",
            "message": f"已整理 {len(moved)} 个文件，放进了 {len(categories)} 个分类文件夹：{'、'.join(categories)}。",
            "moved_count": len(moved),
            "categories": categories,
            "files": [{"source": source.name, "target": str(target)} for source, target in moved],
        }

    def _read_screen(self, focus: str, screenshot_base64: str | None) -> dict[str, Any]:
        config = utils.get_config().get("vl", {})
        screenshot = screenshot_base64 or capture_desktop_data_uri(
            max(320, int(config.get("max_width", 1280))),
            max(35, min(95, int(config.get("jpeg_quality", 75)))),
        )
        if not screenshot:
            return {"status": "error", "message": "没有可用截图。", "observation": "", "desktop_summary": ""}
        prompt = f"""
你正在作为桌宠的屏幕读取工具读取当前桌面截图。
观察重点：{focus.strip() or "当前任务、应用窗口、文档和用户活动"}

只输出 JSON，不要 Markdown。格式：
{{"observation": "给角色看的简短可见内容摘要", "desktop_summary": "值得长期记住的一句话，没有则为空字符串"}}
规则：
- 只描述截图中明确可见的内容。
- 不要转录大段文字，不要输出密码、密钥、身份证号等敏感内容。
- 不要猜测截图外的信息。
""".strip()
        response = self._post_chat(
            self.vl_model,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": screenshot}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            temperature=0.1,
        )
        content = response.json()["choices"][0]["message"].get("content") or ""
        data = parse_reply_content(content)
        observation = str(data.get("observation") or data.get("text") or content).strip()
        desktop_summary = str(data.get("desktop_summary") or "").strip()
        return {
            "status": "success",
            "observation": observation,
            "desktop_summary": desktop_summary,
        }

    def _take_camera_shot(self, camera_index: Any, warmup_frames: Any) -> tuple[dict[str, Any], str]:
        try:
            index = int(camera_index) if camera_index is not None else 0
        except (TypeError, ValueError):
            index = 0
        try:
            warmup = int(warmup_frames) if warmup_frames is not None else 10
        except (TypeError, ValueError):
            warmup = 10
        warmup = max(0, min(warmup, 30))

        out = Path.home() / "Pictures" / "shot.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)

        import cv2

        cap = cv2.VideoCapture(index)
        try:
            for _ in range(warmup):
                cap.read()
            ret, frame = cap.read()
        finally:
            cap.release()

        if not ret:
            return {
                "status": "error",
                "message": "摄像头拍摄失败。",
                "camera_index": index,
            }, ""
        if not cv2.imwrite(str(out), frame):
            return {
                "status": "error",
                "message": "摄像头照片保存失败。",
                "camera_index": index,
                "path": str(out),
            }, ""

        encoded = base64.b64encode(out.read_bytes()).decode("ascii")
        return {
            "status": "success",
            "message": "摄像头照片已拍摄，并已发送给模型查看。",
            "camera_index": index,
            "path": str(out),
            "image_attached": True,
        }, f"data:image/jpeg;base64,{encoded}"
