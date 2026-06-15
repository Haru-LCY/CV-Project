from __future__ import annotations

from dataclasses import dataclass


DEFAULT_CHARACTER_NAME = "丛雨"
DEFAULT_USER_NAME = "用户"
DEFAULT_FGIMAGE_TARGET = "ムラサメb"


@dataclass
class PetResponse:
    text: str
    emotion: str | None = None
    session_id: str | None = None
    tool_action: dict | None = None


@dataclass
class CharacterProfile:
    character_id: str | None = None
    name: str = DEFAULT_CHARACTER_NAME
    persona: str = ""
    greeting: str = "主人，你好呀！"
    display_image_url: str | None = None
    display_image_base64: str | None = None
    expression_layers: list[int] | None = None
    fgimage_target: str = DEFAULT_FGIMAGE_TARGET
    emotion_images: dict | None = None
    appearance_traits: list[str] | None = None
    personality_traits: list[str] | None = None
    identity_traits: list[str] | None = None
    personality_dimensions: dict[str, int] | None = None
    appearance_style_dimensions: dict[str, int] | None = None
    advanced_settings: dict | None = None
    custom_attributes: list[dict] | None = None
    style: str | None = None
