from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from Murasame import utils
from scripts.character_runtime import (
    avatar_values_for_emotion,
    build_reply_messages,
    normalize_emotion,
    parse_reply_content,
    write_image_to_cache,
)
from scripts.character_traits import clean_trait_list, dimensions_from_legacy_traits
from scripts.desktop_tools import (
    ALLOWED_CATEGORY_FOLDERS,
    build_image_contact_sheet,
    delete_query_from_text,
    desktop_root_from_config,
    list_desktop_files,
    metadata_for_entries,
    move_files,
    selected_entries,
    trash_files,
)
from scripts.memory_runtime import MemoryStore, sanitize_memory_text
from scripts.pet_defaults import DEFAULT_CHARACTER_OPTIONS, DEFAULT_VL_MODEL
from scripts.profile import CharacterProfile, DEFAULT_CHARACTER_NAME, DEFAULT_FGIMAGE_TARGET, DEFAULT_USER_NAME, PetResponse
from scripts.workbench.constants import API_BASE_URL, DESCRIPTION_MODEL
from scripts.workbench.generator import LocalCharacterGenerator


class PetApiClient:
    def __init__(self) -> None:
        config = utils.get_config()
        client_config = config.get("client", {})
        vl_config = config.get("vl", {})
        character_config = config.get("character", {})
        self.session_id = client_config.get("session_id", "local-user")
        self.timeout = float(client_config.get("timeout_seconds", 120))
        self.vl_model = vl_config.get("model") or DEFAULT_VL_MODEL
        self.agent_tools_config = config.get("agent_tools", {})
        self.desktop_root = desktop_root_from_config(config)
        self.character_id = character_config.get("character_id")
        self.user_name = character_config.get("user_name") or DEFAULT_USER_NAME
        self.character_profile = self._character_from_config(character_config)
        self.memory = MemoryStore.from_config(config)
        self.api_key: str | None = None
        self.history: list[dict[str, str]] = []

    def get_character_options(self) -> dict:
        options = json.loads(json.dumps(DEFAULT_CHARACTER_OPTIONS, ensure_ascii=False))
        defaults = options.setdefault("defaults", {})
        profile = self.character_profile
        if profile.appearance_traits:
            defaults["appearance_traits"] = profile.appearance_traits
        if profile.personality_traits:
            defaults["personality_traits"] = profile.personality_traits
        if profile.personality_dimensions:
            defaults["personality_dimensions"] = profile.personality_dimensions
        if profile.appearance_style_dimensions:
            defaults["appearance_style_dimensions"] = profile.appearance_style_dimensions
        if profile.advanced_settings:
            defaults["advanced_settings"] = profile.advanced_settings
        if profile.custom_attributes:
            defaults["custom_attributes"] = profile.custom_attributes
        if profile.style:
            defaults["style"] = profile.style
        return options

    def respond(self, event: str, text: str, screenshot_base64: str | None = None) -> PetResponse:
        if event == "user_text" and self._agent_tools_enabled():
            tool_response = self._maybe_handle_desktop_tool(text)
            if tool_response is not None:
                self._remember_turn(event, text, tool_response.text)
                return tool_response

        memory_query = self._memory_query(event, text)
        retrieved_memories = self.memory.search(memory_query, self.memory.config.user_id, self.memory.config.top_k)
        messages = build_reply_messages(
            self.character_profile,
            self.user_name,
            self.history,
            event,
            text,
            bool(screenshot_base64),
            retrieved_memories,
        )
        model = DESCRIPTION_MODEL
        if event == "screen_context" and screenshot_base64:
            model = self.vl_model
            user_text = messages[-1]["content"]
            messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": screenshot_base64}},
                    {"type": "text", "text": user_text},
                ],
            }

        response = self._post_chat(
            model,
            messages,
            temperature=0.85,
        )
        content = response.json()["choices"][0]["message"]["content"]
        data = parse_reply_content(content)
        reply_text = data.get("text") or content.strip()
        emotion = normalize_emotion(data.get("emotion"))
        desktop_summary = str(data.get("desktop_summary") or "").strip()
        self._remember_turn(event, text, reply_text, desktop_summary)
        return PetResponse(
            text=reply_text,
            emotion=emotion,
            session_id=self.session_id,
        )

    def download_image(self, image_url: str | None, image_base64: str | None, key: str) -> str | None:
        return write_image_to_cache(image_url, image_base64, key)

    def confirm_tool_action(self, action: dict[str, Any]) -> PetResponse:
        action_type = action.get("type")
        if action_type != "trash_files":
            return PetResponse(text="这个工具动作不认识，我没有执行。", emotion="sad", session_id=self.session_id)
        files = action.get("files")
        if not isinstance(files, list):
            return PetResponse(text="删除列表格式不对，我没有执行。", emotion="sad", session_id=self.session_id)
        safe_paths: list[str] = []
        for file_info in files:
            if not isinstance(file_info, dict):
                continue
            path = Path(str(file_info.get("path") or "")).resolve()
            if path.parent == self.desktop_root and path.exists() and path.is_file():
                safe_paths.append(str(path))
        trashed = trash_files(safe_paths)
        if not trashed:
            reply = "没有文件被移到废纸篓。"
            emotion = "sad"
        else:
            reply = f"已把 {len(trashed)} 个文件移到废纸篓。"
            emotion = "happy"
        self._remember_turn("desktop_tool", "confirm_trash", reply)
        return PetResponse(text=reply, emotion=emotion, session_id=self.session_id)

    def _get_api_key(self) -> str:
        if not self.api_key:
            self.api_key = LocalCharacterGenerator(timeout=int(self.timeout)).api_key
        return self.api_key

    def _post_chat(self, model: str, messages: list[dict], temperature: float = 0.2) -> requests.Response:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._get_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "top_p": 1,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response

    def _agent_tools_enabled(self) -> bool:
        if not isinstance(self.agent_tools_config, dict):
            return True
        return bool(self.agent_tools_config.get("enabled", True))

    def _maybe_handle_desktop_tool(self, text: str) -> PetResponse | None:
        normalized = text.strip().lower()
        if not normalized or "桌面" not in text:
            return None
        if self._looks_like_delete_image_request(text):
            return self._plan_desktop_image_trash(text)
        if self._looks_like_organize_request(text):
            return self._organize_desktop(text)
        return None

    def _looks_like_delete_image_request(self, text: str) -> bool:
        return any(token in text for token in ("删除", "删掉", "移除", "丢掉", "清理")) and any(
            token in text for token in ("图片", "照片", "图")
        )

    def _looks_like_organize_request(self, text: str) -> bool:
        return any(token in text for token in ("整理", "分类", "归类", "收拾")) and any(
            token in text for token in ("文件", "东西", "桌面")
        )

    def _plan_desktop_image_trash(self, text: str) -> PetResponse:
        image_entries = list_desktop_files(self.desktop_root, images_only=True)
        if not image_entries:
            return PetResponse(text="桌面上没有可识别的图片文件。", emotion="sad", session_id=self.session_id)
        sheet = build_image_contact_sheet(image_entries)
        if not sheet:
            return PetResponse(text="桌面图片缩略图生成失败，我没有删除任何东西。", emotion="sad", session_id=self.session_id)

        query = delete_query_from_text(text)
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
        content = response.json()["choices"][0]["message"]["content"]
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
            return PetResponse(text="没找到足够确定符合描述的图片，我没有删除任何东西。", emotion="sad", session_id=self.session_id)

        files = [{"name": entry.name, "path": str(entry.path)} for entry in selected]
        return PetResponse(
            text=f"我找到了 {len(files)} 个可能符合描述的图片，需要你确认后才会移到废纸篓。",
            emotion="happy",
            session_id=self.session_id,
            tool_action={"type": "trash_files", "files": files},
        )

    def _organize_desktop(self, text: str) -> PetResponse:
        entries = list_desktop_files(self.desktop_root, images_only=False)
        if not entries:
            return PetResponse(text="桌面上没有需要整理的直接文件。", emotion="happy", session_id=self.session_id)
        prompt = f"""
你是桌面文件整理器。请根据用户要求、文件名和扩展名，把桌面文件移动到固定分类文件夹。
用户要求：{text}
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
        content = response.json()["choices"][0]["message"]["content"]
        data = parse_reply_content(content)
        moves = data.get("moves") if isinstance(data, dict) else []
        if not isinstance(moves, list):
            moves = []
        moved = move_files(self.desktop_root, moves)
        if not moved:
            return PetResponse(text="没有生成安全可执行的整理计划，所以我没有移动文件。", emotion="sad", session_id=self.session_id)
        categories = sorted({target.parent.name for _, target in moved})
        return PetResponse(
            text=f"已整理 {len(moved)} 个文件，放进了 {len(categories)} 个分类文件夹：{'、'.join(categories)}。",
            emotion="happy",
            session_id=self.session_id,
        )

    def _remember_turn(self, event: str, user_text: str, reply_text: str, desktop_summary: str = "") -> None:
        short_term_user_text = user_text or event
        self.history.extend(
            [
                {"role": "user", "content": short_term_user_text},
                {"role": "assistant", "content": json.dumps({"text": reply_text}, ensure_ascii=False)},
            ]
        )
        self.history = self.history[-12:]
        metadata = {
            "event": event,
            "session_id": self.session_id,
            "user_id": self.memory.config.user_id,
        }
        if event == "screen_context":
            summary = desktop_summary or reply_text
            self.memory.add_desktop_observation(summary, reply_text, metadata)
            return
        self.memory.add_turn(user_text or event, reply_text, metadata)

    def _memory_query(self, event: str, text: str) -> str:
        if event == "screen_context":
            return "桌面观察 当前任务 应用 文档"
        if text.strip():
            return sanitize_memory_text(text)
        return event

    def _character_from_config(self, data: dict) -> CharacterProfile:
        return CharacterProfile(
            character_id=data.get("character_id") or data.get("id") or self.character_id,
            name=data.get("name") or data.get("character_name") or DEFAULT_CHARACTER_NAME,
            persona=data.get("persona") or "",
            greeting=data.get("greeting") or "主人，你好呀！",
            display_image_url=data.get("display_image_url"),
            display_image_base64=data.get("display_image_base64"),
            expression_layers=data.get("expression_layers"),
            fgimage_target=data.get("fgimage_target") or DEFAULT_FGIMAGE_TARGET,
            emotion_images=data.get("emotion_images"),
            appearance_traits=clean_trait_list(data.get("appearance_traits")),
            personality_traits=clean_trait_list(data.get("personality_traits")),
            identity_traits=data.get("identity_traits"),
            personality_dimensions=data.get("personality_dimensions")
            or (data.get("trait_dimensions") or {}).get("personality")
            or dimensions_from_legacy_traits(data.get("personality_traits")),
            appearance_style_dimensions=data.get("appearance_style_dimensions")
            or (data.get("trait_dimensions") or {}).get("appearance_style"),
            advanced_settings=data.get("advanced_settings") or {},
            custom_attributes=data.get("custom_attributes") or data.get("customAttributes") or [],
            style=data.get("style"),
        )

    def remember_character(self, profile: CharacterProfile, user_name: str) -> None:
        config = utils.get_config()
        character_config = config.setdefault("character", {})
        character_config["character_id"] = profile.character_id
        character_config["name"] = profile.name
        character_config["persona"] = profile.persona
        character_config["greeting"] = profile.greeting
        character_config["display_image_url"] = profile.display_image_url
        character_config["display_image_base64"] = profile.display_image_base64
        character_config["expression_layers"] = profile.expression_layers
        character_config["fgimage_target"] = profile.fgimage_target
        character_config["emotion_images"] = profile.emotion_images
        character_config["appearance_traits"] = profile.appearance_traits
        character_config["personality_traits"] = profile.personality_traits
        character_config["identity_traits"] = profile.identity_traits
        character_config["personality_dimensions"] = profile.personality_dimensions
        character_config["appearance_style_dimensions"] = profile.appearance_style_dimensions
        character_config["advanced_settings"] = profile.advanced_settings
        character_config["custom_attributes"] = profile.custom_attributes
        character_config["trait_dimensions"] = {
            "personality": profile.personality_dimensions or {},
            "appearance_style": profile.appearance_style_dimensions or {},
        }
        character_config["style"] = profile.style
        character_config["user_name"] = user_name or DEFAULT_USER_NAME
        utils.save_config(config)
        self.character_id = profile.character_id
        self.user_name = user_name or DEFAULT_USER_NAME
        self.character_profile = profile
        self.history.clear()
