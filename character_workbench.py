from __future__ import annotations

import base64
import json
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import cv2
from PyQt5.QtCore import QObject, QThread, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from Murasame import generate


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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.api_client = api_client
        self.user_name = user_name
        self.appearance_traits = appearance_traits
        self.personality_traits = personality_traits
        self.identity_traits = identity_traits
        self.style = style

    def run(self) -> None:
        try:
            profile = self.api_client.generate_character(
                user_name=self.user_name,
                appearance_traits=self.appearance_traits,
                personality_traits=self.personality_traits,
                identity_traits=self.identity_traits,
                style=self.style,
            )
            self.finished.emit(profile, None)
        except Exception as exc:
            traceback.print_exc()
            self.finished.emit(None, f"{type(exc).__name__}: {exc}")


class CharacterWorkbenchBridge(QObject):
    generationStarted = pyqtSignal()
    generationFinished = pyqtSignal(str)
    generationFailed = pyqtSignal(str)
    previewStale = pyqtSignal()

    def __init__(
        self,
        dialog: "CharacterCreatorDialog",
        options: dict,
        api_client: Any,
        default_options: dict,
        default_user_name: str,
    ) -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.options = options
        self.api_client = api_client
        self.default_options = default_options
        self.default_user_name = default_user_name
        self.generation_worker: CharacterGenerationWorker | None = None

    @pyqtSlot(result=str)
    def getInitialState(self) -> str:
        defaults = self.options.get("defaults") or self.default_options.get("defaults", {})
        state = {
            "options": self.options,
            "defaults": defaults,
            "userName": self.api_client.user_name or self.default_user_name,
        }
        return json.dumps(state, ensure_ascii=False)

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

        self.generation_worker = CharacterGenerationWorker(
            api_client=self.api_client,
            user_name=self.dialog.preview_user_name,
            appearance_traits=payload.get("appearance_traits") or self.default_options["defaults"]["appearance_traits"],
            personality_traits=payload.get("personality_traits")
            or self.default_options["defaults"]["personality_traits"],
            identity_traits=payload.get("identity_traits") or self.default_options["defaults"]["identity_traits"],
            style=payload.get("style") or self.default_options["defaults"]["style"],
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
        self.generationFinished.emit(json.dumps(self._profile_payload(profile), ensure_ascii=False))

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
    def cancel(self) -> None:
        self.dialog.reject()

    def _profile_payload(self, profile: Any) -> dict:
        return {
            "character_id": profile.character_id,
            "name": profile.name,
            "persona": profile.persona,
            "greeting": profile.greeting,
            "image_src": self._profile_image_src(profile),
        }

    def _profile_image_src(self, profile: Any) -> str | None:
        if profile.display_image_base64:
            return f"data:image/png;base64,{profile.display_image_base64}"
        if profile.display_image_url:
            if urlparse(profile.display_image_url).scheme:
                return profile.display_image_url
            return urljoin(f"{self.api_client.base_url}/", profile.display_image_url.lstrip("/"))
        if profile.expression_layers:
            try:
                cv_img = generate.generate_fgimage(
                    target=profile.fgimage_target,
                    embeddings_layers=profile.expression_layers,
                )
                ok, encoded = cv2.imencode(".png", cv_img)
                if ok:
                    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
            except Exception:
                traceback.print_exc()
        return None


class CharacterCreatorDialog(QDialog):
    def __init__(
        self,
        options: dict,
        api_client: Any,
        default_options: dict,
        default_user_name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("角色生成工作台")
        self.resize(1040, 720)
        self.preview_profile = None
        self.preview_is_current = False
        self.preview_user_name = api_client.user_name or default_user_name

        try:
            from PyQt5.QtWebChannel import QWebChannel
            from PyQt5.QtWebEngineWidgets import QWebEngineView
        except ModuleNotFoundError as exc:
            QMessageBox.critical(
                parent,
                "缺少依赖",
                "HTML 工作台需要安装 PyQtWebEngine。\n\n请运行：uv sync\n\n"
                f"当前错误：{type(exc).__name__}: {exc}",
            )
            raise

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView(self)
        layout.addWidget(self.web_view)

        self.bridge = CharacterWorkbenchBridge(self, options, api_client, default_options, default_user_name)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("characterWorkbench", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        html_path = Path(__file__).resolve().parent / "ui" / "character_workbench.html"
        self.web_view.load(QUrl.fromLocalFile(str(html_path)))
