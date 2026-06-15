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
from scripts.desktop_tools import desktop_root_from_config, trash_files
from scripts.memory_runtime import MemoryStore, sanitize_memory_text
from scripts.pet_defaults import DEFAULT_CHARACTER_OPTIONS, DEFAULT_VL_MODEL
from scripts.pet_tools import PetToolExecutor, native_tools_for_event, tool_choice_for_event
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
        self.tool_executor = PetToolExecutor(self.desktop_root, self.vl_model, self._post_chat)

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
        tools = native_tools_for_event(event) if self._agent_tools_enabled() else []
        tool_choice = tool_choice_for_event(event, bool(screenshot_base64))
        if event == "screen_context" and screenshot_base64 and not tools:
            model = self.vl_model
            user_text = messages[-1]["content"]
            messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": screenshot_base64}},
                    {"type": "text", "text": user_text},
                ],
            }

        if tools:
            return self._respond_with_tool_loop(event, text, messages, model, tools, tool_choice, screenshot_base64)

        response = self._post_chat(
            model,
            messages,
            temperature=0.85,
        )
        message = response.json()["choices"][0]["message"]
        return self._pet_response_from_message(event, text, message)

    def _pet_response_from_message(
        self,
        event: str,
        text: str,
        message: dict[str, Any],
        pending_action: dict | None = None,
        desktop_summary_fallback: str = "",
    ) -> PetResponse:
        content_value = message.get("content") or ""
        content = content_value if isinstance(content_value, str) else json.dumps(content_value, ensure_ascii=False)
        data = parse_reply_content(content)
        reply_text = data.get("text") or content.strip()
        emotion = normalize_emotion(data.get("emotion"))
        desktop_summary = str(data.get("desktop_summary") or desktop_summary_fallback).strip()
        self._remember_turn(event, text, reply_text, desktop_summary)
        return PetResponse(
            text=reply_text,
            emotion=emotion,
            session_id=self.session_id,
            tool_action=pending_action,
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

    def _post_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> requests.Response:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "top_p": 1,
            "presence_penalty": 0,
            "frequency_penalty": 0,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        response = requests.post(
            f"{API_BASE_URL}/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._get_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response

    def _agent_tools_enabled(self) -> bool:
        if not isinstance(self.agent_tools_config, dict):
            return True
        return bool(self.agent_tools_config.get("enabled", True))

    def _respond_with_tool_loop(
        self,
        event: str,
        text: str,
        messages: list[dict],
        model: str,
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] | None,
        screenshot_base64: str | None,
    ) -> PetResponse:
        pending_action: dict | None = None
        desktop_summary_fallback = ""
        current_model = model
        current_tool_choice = tool_choice
        max_tool_rounds = 6

        for _ in range(max_tool_rounds):
            response = self._post_chat(
                current_model,
                messages,
                temperature=0.85,
                tools=tools,
                tool_choice=current_tool_choice,
            )
            message = response.json()["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return self._pet_response_from_message(
                    event,
                    text,
                    message,
                    pending_action=pending_action,
                    desktop_summary_fallback=desktop_summary_fallback,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            image_messages: list[dict[str, Any]] = []
            for tool_call in tool_calls:
                execution = self.tool_executor.execute(tool_call, screenshot_base64)
                if execution.action:
                    pending_action = execution.action
                if execution.desktop_summary:
                    desktop_summary_fallback = execution.desktop_summary
                if execution.image_url:
                    image_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": execution.image_url}},
                                {"type": "text", "text": execution.image_prompt or "这是工具返回的图片，请继续回答用户。"},
                            ],
                        }
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tool_call.get("id") or execution.name),
                        "name": execution.name,
                        "content": json.dumps(execution.result, ensure_ascii=False),
                    }
                )
            messages.extend(image_messages)

            current_tool_choice = "auto"
            if image_messages:
                current_model = self.vl_model

        guard_message = {
            "role": "assistant",
            "content": json.dumps(
                {
                    "text": "工具调用次数太多了，我先停下来，避免继续循环。",
                    "emotion": "sad",
                    "desktop_summary": desktop_summary_fallback,
                },
                ensure_ascii=False,
            ),
        }
        return self._pet_response_from_message(
            event,
            text,
            guard_message,
            pending_action=pending_action,
            desktop_summary_fallback=desktop_summary_fallback,
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
