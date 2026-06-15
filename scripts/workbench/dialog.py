from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from Murasame.paths import resource_path
from scripts.workbench.bridge import CharacterWorkbenchBridge


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
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
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

        html_path = resource_path("ui", "character_workbench.html")
        self.web_view.loadFinished.connect(
            lambda ok: print(f"Character workbench loaded: ok={ok}, url={self.web_view.url().toString()}")
        )
        self.web_view.load(QUrl.fromLocalFile(str(html_path)))
