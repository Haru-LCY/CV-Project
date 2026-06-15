from __future__ import annotations

import traceback
from typing import Any

from PyQt5.QtCore import QThread, pyqtSignal

from scripts.workbench.generator import LocalCharacterGenerator


class CharacterGenerationWorker(QThread):
    finished = pyqtSignal(object, object)

    def __init__(
        self,
        api_client: Any,
        user_name: str,
        appearance_traits: list[str],
        personality_traits: list[str],
        identity_traits: list[str],
        style: str,
        personality_dimensions: dict[str, int] | None = None,
        appearance_style_dimensions: dict[str, int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.api_client = api_client
        self.user_name = user_name
        self.appearance_traits = appearance_traits
        self.personality_traits = personality_traits
        self.identity_traits = identity_traits
        self.style = style
        self.personality_dimensions = personality_dimensions or {}
        self.appearance_style_dimensions = appearance_style_dimensions or {}

    def run(self) -> None:
        try:
            profile = LocalCharacterGenerator().generate(
                user_name=self.user_name,
                appearance_traits=self.appearance_traits,
                personality_traits=self.personality_traits,
                identity_traits=self.identity_traits,
                style=self.style,
                personality_dimensions=self.personality_dimensions,
                appearance_style_dimensions=self.appearance_style_dimensions,
            )
            self.finished.emit(profile, None)
        except Exception as exc:
            traceback.print_exc()
            self.finished.emit(None, f"API 生成失败：{type(exc).__name__}: {exc}")
