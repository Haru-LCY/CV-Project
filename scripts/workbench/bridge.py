from __future__ import annotations

import json
import traceback
from typing import Any

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from scripts.character_traits import clean_traits, dimensions_from_legacy_traits, normalize_dimensions
from scripts.workbench.cards import CharacterCardRepository
from scripts.workbench.profile_payload import profile_payload
from scripts.workbench.workers import CharacterGenerationWorker


class CharacterWorkbenchBridge(QObject):
    generationStarted = pyqtSignal()
    generationFinished = pyqtSignal(str)
    generationFailed = pyqtSignal(str)
    previewStale = pyqtSignal()
    cardSaved = pyqtSignal(str)
    cardSaveFailed = pyqtSignal(str)

    def __init__(
        self,
        dialog: "CharacterCreatorDialog",
        options: dict,
        api_client: Any,
        default_options: dict,
        default_user_name: str,
        card_repository: CharacterCardRepository | None = None,
    ) -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.options = options
        self.api_client = api_client
        self.default_options = default_options
        self.default_user_name = default_user_name
        self.card_repository = card_repository or CharacterCardRepository()
        self.generation_worker: CharacterGenerationWorker | None = None

    @pyqtSlot(result=str)
    def getInitialState(self) -> str:
        defaults = self.options.get("defaults") or self.default_options.get("defaults", {})
        state = {
            "options": self.options,
            "defaults": defaults,
            "userName": self.api_client.user_name or self.default_user_name,
            "historyCards": self.card_repository.history_card_summaries(),
        }
        return json.dumps(state, ensure_ascii=False)

    @pyqtSlot(result=str)
    def getHistoryCards(self) -> str:
        return json.dumps(self.card_repository.history_card_summaries(), ensure_ascii=False)

    @pyqtSlot(str)
    def startGeneration(self, payload_json: str) -> None:
        if self.generation_worker is not None:
            return
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            self.generationFailed.emit(f"参数解析失败：{exc}")
            return

        self.dialog.preview_profile = None
        self.dialog.preview_is_current = False
        self.dialog.preview_user_name = payload.get("user_name") or self.default_user_name
        self.generationStarted.emit()
        raw_appearance_traits = payload.get("appearance_traits") or self.default_options["defaults"]["appearance_traits"]
        raw_personality_traits = (
            payload.get("personality_traits") or self.default_options["defaults"]["personality_traits"]
        )
        appearance_traits = clean_traits(raw_appearance_traits)
        personality_traits = clean_traits(raw_personality_traits)
        personality_dimensions = normalize_dimensions(payload.get("personality_dimensions"))
        if not personality_dimensions:
            personality_dimensions = dimensions_from_legacy_traits(raw_personality_traits)
        appearance_style_dimensions = normalize_dimensions(payload.get("appearance_style_dimensions"))

        self.generation_worker = CharacterGenerationWorker(
            api_client=self.api_client,
            user_name=self.dialog.preview_user_name,
            appearance_traits=appearance_traits,
            personality_traits=personality_traits,
            identity_traits=payload.get("identity_traits") or [],
            style=payload.get("style") or self.default_options["defaults"]["style"],
            personality_dimensions=personality_dimensions,
            appearance_style_dimensions=appearance_style_dimensions,
            parent=self,
        )
        self.generation_worker.finished.connect(self.on_generation_finished)
        self.generation_worker.start()

    def on_generation_finished(self, profile: Any, error: str | None) -> None:
        self.generation_worker = None
        if error or profile is None:
            self.dialog.preview_profile = None
            self.dialog.preview_is_current = False
            self.generationFailed.emit(error or "unknown error")
            return

        self.dialog.preview_profile = profile
        self.dialog.preview_is_current = True
        self.generationFinished.emit(json.dumps(profile_payload(profile), ensure_ascii=False))

    @pyqtSlot()
    def markStale(self) -> None:
        if self.dialog.preview_profile is None:
            return
        self.dialog.preview_is_current = False
        self.previewStale.emit()

    @pyqtSlot()
    def applyCharacter(self) -> None:
        if self.dialog.preview_profile is None or not self.dialog.preview_is_current:
            self.generationFailed.emit("请先生成预览，再应用角色。")
            return
        self.dialog.accept()

    @pyqtSlot()
    def saveCharacterCard(self) -> None:
        if self.dialog.preview_profile is None or not self.dialog.preview_is_current:
            self.cardSaveFailed.emit("请先生成预览，再保存角色卡。")
            return
        try:
            path = self.card_repository.save(self.dialog.preview_profile)
            self.cardSaved.emit(str(path))
        except Exception as exc:
            traceback.print_exc()
            self.cardSaveFailed.emit(f"{type(exc).__name__}: {exc}")

    @pyqtSlot(str)
    def loadHistoryCard(self, path: str) -> None:
        try:
            profile = self.card_repository.load(path)
            self.dialog.preview_profile = profile
            self.dialog.preview_is_current = True
            self.dialog.preview_user_name = self.api_client.user_name or self.default_user_name
            self.generationFinished.emit(json.dumps(profile_payload(profile), ensure_ascii=False))
        except Exception as exc:
            traceback.print_exc()
            self.generationFailed.emit(f"加载历史角色失败：{type(exc).__name__}: {exc}")

    @pyqtSlot()
    def cancel(self) -> None:
        self.dialog.reject()
