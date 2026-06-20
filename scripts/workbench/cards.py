from __future__ import annotations

import json
import re
import shutil
import traceback
import uuid
from pathlib import Path
from typing import Any

from Murasame.paths import seed_character_cards
from scripts.character_traits import clean_traits, dimensions_from_legacy_traits, normalize_dimensions
from scripts.profile import CharacterProfile as GeneratedCharacterProfile


class CharacterCardRepository:
    def cards_dir(self) -> Path:
        return seed_character_cards()

    def save(self, profile: Any) -> Path:
        cards_dir = self.cards_dir()
        cards_dir.mkdir(parents=True, exist_ok=True)
        filename = self.safe_card_filename(getattr(profile, "name", None), getattr(profile, "character_id", None))
        path = cards_dir / filename
        self.write(path, self.character_card_payload(profile))
        return path

    def import_external(self, source: str) -> Path:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"角色卡文件不存在：{source}")
        if source_path.suffix.lower() != ".json":
            raise ValueError("只能导入 .json 角色卡文件")

        with source_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("角色卡 JSON 顶层必须是对象")

        profile = self.profile_from_card(data)
        cards_dir = self.cards_dir()
        cards_dir.mkdir(parents=True, exist_ok=True)
        resolved_cards_dir = cards_dir.resolve()
        if source_path.is_relative_to(resolved_cards_dir):
            return source_path

        filename = self.safe_card_filename(profile.name, profile.character_id)
        target_path = self.available_card_path(cards_dir / filename)
        shutil.copy2(source_path, target_path)
        return target_path

    def load(self, path: str) -> GeneratedCharacterProfile:
        card_path = self.resolve_card_path(path)
        with card_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        profile = self.profile_from_card(data)
        self.upgrade_card_dimensions(card_path, profile)
        return profile

    def write(self, path: Path, payload: dict) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
            f.write("\n")

    def character_card_payload(self, profile: Any) -> dict:
        return {
            "schema_version": 2,
            "character_id": getattr(profile, "character_id", None),
            "name": getattr(profile, "name", ""),
            "persona": getattr(profile, "persona", ""),
            "greeting": getattr(profile, "greeting", ""),
            "fgimage_target": getattr(profile, "fgimage_target", "ムラサメb"),
            "appearance_traits": getattr(profile, "appearance_traits", None) or [],
            "personality_traits": getattr(profile, "personality_traits", None) or [],
            "identity_traits": getattr(profile, "identity_traits", None) or [],
            "personality_dimensions": getattr(profile, "personality_dimensions", None) or {},
            "appearance_style_dimensions": getattr(profile, "appearance_style_dimensions", None) or {},
            "advanced_settings": getattr(profile, "advanced_settings", None) or {},
            "custom_attributes": getattr(profile, "custom_attributes", None) or [],
            "trait_dimensions": {
                "personality": getattr(profile, "personality_dimensions", None) or {},
                "appearance_style": getattr(profile, "appearance_style_dimensions", None) or {},
            },
            "style": getattr(profile, "style", None),
            "display_image_base64": getattr(profile, "display_image_base64", None),
            "emotion_images": getattr(profile, "emotion_images", None) or {},
        }

    def safe_card_filename(self, name: str | None, character_id: str | None) -> str:
        safe_name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name or "character").strip("._")
        safe_id = re.sub(r"[^\w.-]+", "_", character_id or uuid.uuid4().hex[:12]).strip("._")
        return f"{safe_name or 'character'}_{safe_id or uuid.uuid4().hex[:12]}.json"

    def available_card_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        for index in range(2, 1000):
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise FileExistsError(f"无法为角色卡生成未占用文件名：{path.name}")

    def history_card_summaries(self) -> list[dict]:
        cards_dir = self.cards_dir()
        if not cards_dir.exists():
            return []
        summaries = []
        for path in sorted(cards_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                summaries.append(
                    {
                        "path": str(path),
                        "filename": path.name,
                        "name": data.get("name") or path.stem,
                        "greeting": data.get("greeting") or "",
                    }
                )
            except Exception:
                traceback.print_exc()
        return summaries

    def resolve_card_path(self, path: str) -> Path:
        cards_dir = self.cards_dir().resolve()
        card_path = Path(path)
        if not card_path.is_absolute():
            card_path = cards_dir / card_path
        card_path = card_path.resolve()
        if cards_dir not in card_path.parents or card_path.suffix.lower() != ".json":
            raise ValueError("角色卡路径不在 character_cards 目录中")
        return card_path

    def upgrade_card_dimensions(self, path: Path, profile: GeneratedCharacterProfile) -> None:
        self.write(path, self.character_card_payload(profile))

    def profile_from_card(self, data: dict) -> GeneratedCharacterProfile:
        trait_dimensions = data.get("trait_dimensions") if isinstance(data.get("trait_dimensions"), dict) else {}
        raw_personality_traits = data.get("personality_traits") or []
        personality_dimensions = normalize_dimensions(
            data.get("personality_dimensions") or trait_dimensions.get("personality")
        )
        if not personality_dimensions:
            personality_dimensions = dimensions_from_legacy_traits(raw_personality_traits)
        return GeneratedCharacterProfile(
            character_id=data.get("character_id") or f"local-{uuid.uuid4().hex[:12]}",
            name=data.get("name") or "角色",
            persona=data.get("persona") or "",
            greeting=data.get("greeting") or "你好呀。",
            display_image_base64=data.get("display_image_base64"),
            expression_layers=data.get("expression_layers"),
            fgimage_target=data.get("fgimage_target") or "ムラサメb",
            emotion_images=data.get("emotion_images") or {},
            appearance_traits=clean_traits(data.get("appearance_traits") or []),
            personality_traits=clean_traits(raw_personality_traits),
            identity_traits=data.get("identity_traits") or [],
            personality_dimensions=personality_dimensions,
            appearance_style_dimensions=normalize_dimensions(
                data.get("appearance_style_dimensions") or trait_dimensions.get("appearance_style")
            ),
            advanced_settings=data.get("advanced_settings") or {},
            custom_attributes=data.get("custom_attributes") or data.get("customAttributes") or [],
            style=data.get("style"),
        )
