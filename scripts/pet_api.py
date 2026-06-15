from __future__ import annotations

import json

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
                "temperature": 0.85,
                "top_p": 1,
                "presence_penalty": 0,
                "frequency_penalty": 0,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
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

    def _get_api_key(self) -> str:
        if not self.api_key:
            self.api_key = LocalCharacterGenerator(timeout=int(self.timeout)).api_key
        return self.api_key

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
