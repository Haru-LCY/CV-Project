from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def profile_payload(profile: Any) -> dict:
    return {
        "character_id": profile.character_id,
        "name": profile.name,
        "persona": profile.persona,
        "greeting": profile.greeting,
        "image_src": profile_image_src(profile),
        "emotion_images": emotion_images_payload(profile),
        "personality_dimensions": getattr(profile, "personality_dimensions", None) or {},
        "appearance_style_dimensions": getattr(profile, "appearance_style_dimensions", None) or {},
        "advanced_settings": getattr(profile, "advanced_settings", None) or {},
        "custom_attributes": getattr(profile, "custom_attributes", None) or [],
    }


def profile_image_src(profile: Any) -> str | None:
    return image_src_from_values(
        getattr(profile, "display_image_url", None),
        getattr(profile, "display_image_base64", None),
    )


def emotion_images_payload(profile: Any) -> dict:
    result = {}
    emotion_images = getattr(profile, "emotion_images", None) or {}
    for emotion in ("happy", "angry", "shy", "sad"):
        src = None
        image = emotion_images.get(emotion) if isinstance(emotion_images, dict) else None
        if isinstance(image, str):
            src = image_src_from_values(image, None)
        elif isinstance(image, dict):
            src = image.get("image_src") or image_src_from_values(
                image.get("display_image_url") or image.get("url"),
                image.get("display_image_base64") or image.get("base64"),
            )
        if src:
            result[emotion] = {"image_src": src}
    return result


def image_src_from_values(image_url: str | None, image_base64: str | None) -> str | None:
    if image_base64:
        return f"data:image/png;base64,{image_base64}"
    if image_url:
        if image_url.startswith("data:") or urlparse(image_url).scheme:
            return image_url
    return None
