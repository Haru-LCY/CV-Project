from __future__ import annotations

import sys
import textwrap

from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QStyle, QToolButton

from Murasame import utils
from Murasame.macos_window import apply_top_layer
from Murasame.paths import resource_path
from scripts.character_runtime import avatar_values_for_emotion
from scripts.pet_api import PetApiClient
from scripts.pet_defaults import DEFAULT_EXPRESSION_LAYERS, DEFAULT_FGIMAGE_TARGET, GENERATED_AVATAR_SCALE
from scripts.pet_workers import ApiWorker, ToolActionWorker
from scripts.profile import CharacterProfile, PetResponse
from scripts.workbench.dialog import CharacterCreatorDialog


def wrap_text(text: str, width: int = 12) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False))


class DesktopPet(QLabel):
    settings_requested = pyqtSignal()

    DISPLAY_PRESETS = {
        "compact": {"visible_ratio": 0.35, "text_x_offset": 120, "text_y_offset": 15},
        "balanced": {"visible_ratio": 0.45, "text_x_offset": 140, "text_y_offset": 20},
        "standard": {"visible_ratio": 0.6, "text_x_offset": 150, "text_y_offset": 25},
        "full": {"visible_ratio": 1.0, "text_x_offset": 160, "text_y_offset": -100},
    }

    def __init__(self, api_client: PetApiClient, character: CharacterProfile) -> None:
        super().__init__()
        self.api_client = api_client
        self.character = character
        self.latest_response = character.greeting or "主人，你好呀！"
        self.input_mode = False
        self.input_buffer = ""
        self.preedit_text = ""
        self.display_text = ""
        self.full_text = ""
        self.typing_prefix = ""
        self._typing_index = 0
        self.offset: QPoint | None = None
        self.touch_head = False
        self.head_press_x: int | None = None
        self.llm_worker: ApiWorker | None = None
        self.tool_worker: ToolActionWorker | None = None
        self.pending_tool_action: dict | None = None
        self.screen_worker = None
        self.character_dialog: CharacterCreatorDialog | None = None
        self.settings_button_size = self._scaled_value(34)
        self.confirm_button_size = QSize(self._scaled_value(66), self._scaled_value(30))

        config = utils.get_config()
        display_config = config.get("display", {})
        preset_name = display_config.get("preset", "balanced")
        if preset_name == "custom":
            preset = display_config.get("custom", {})
        else:
            preset = self.DISPLAY_PRESETS.get(preset_name, self.DISPLAY_PRESETS["balanced"])
        self.visible_ratio = float(preset.get("visible_ratio", 0.45))
        self.text_x_offset_default = int(preset.get("text_x_offset", 140))
        self.text_y_offset_default = int(preset.get("text_y_offset", 20))

        window_type = Qt.Window if sys.platform == "win32" else Qt.Tool
        self.setWindowFlags(Qt.FramelessWindowHint | window_type | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.text_font = QFont()
        self.text_font.setFamily("思源黑体 CN Bold")
        QFontDatabase.addApplicationFont(str(resource_path("思源黑体Bold.otf")))
        self.text_font.setPointSize(self._scaled_value(24))
        self.text_x_offset = 0
        self.text_y_offset = 0
        self.settings_button = self._create_control_button("角色设置")
        self.settings_button.setIcon(QIcon(str(resource_path("icon.png"))))
        self.settings_button.setIconSize(QSize(self._scaled_value(20), self._scaled_value(20)))
        self.settings_button.clicked.connect(self.settings_requested.emit)

        self.exit_button = self._create_control_button("退出")
        self.exit_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        self.exit_button.setIconSize(QSize(self._scaled_value(18), self._scaled_value(18)))
        self.exit_button.clicked.connect(QApplication.instance().quit)

        self.confirm_tool_button = self._create_tool_choice_button("确认", "确认执行")
        self.confirm_tool_button.clicked.connect(self.confirm_pending_tool_action)
        self.reject_tool_button = self._create_tool_choice_button("拒绝", "拒绝执行")
        self.reject_tool_button.clicked.connect(self.reject_pending_tool_action)
        self._hide_tool_choice_buttons()

        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self._typing_step)
        self.typing_interval = 40
        self.top_layer_timer = QTimer()
        self.top_layer_timer.timeout.connect(self.ensure_top_layer)
        self.top_layer_timer.start(3000)
        self.mousePressEvent = self.start_move
        self.mouseMoveEvent = self.on_move
        avatar_url, avatar_base64 = avatar_values_for_emotion(character, "happy")
        self._set_avatar(
            image_url=avatar_url,
            image_base64=avatar_base64,
            layers=character.expression_layers or DEFAULT_EXPRESSION_LAYERS,
            fgimage_target=character.fgimage_target,
        )

    def ensure_top_layer(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        apply_top_layer(self, level="screensaver")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.ensure_top_layer)
        QTimer.singleShot(250, self.ensure_top_layer)

    def _create_control_button(self, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setFixedSize(self.settings_button_size, self.settings_button_size)
        button.setFocusPolicy(Qt.NoFocus)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            """
            QToolButton {
                background: rgba(255, 255, 255, 210);
                border: 1px solid rgba(80, 48, 60, 120);
                border-radius: 8px;
                padding: 4px;
            }
            QToolButton:hover {
                background: rgba(255, 246, 250, 240);
                border-color: rgba(80, 48, 60, 190);
            }
            """
        )
        return button

    def _create_tool_choice_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setFixedSize(self.confirm_button_size)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            """
            QToolButton {
                background: rgba(44, 22, 28, 225);
                color: white;
                border: 1px solid rgba(255, 255, 255, 210);
                border-radius: 10px;
                padding: 4px 10px;
                font-weight: 700;
            }
            QToolButton:hover {
                background: rgba(90, 45, 58, 240);
            }
            """
        )
        return button

    def _scale_factor(self) -> float:
        app = QApplication.instance()
        if app and hasattr(app, "devicePixelRatio"):
            return float(app.devicePixelRatio())
        screen = app.primaryScreen() if app else None
        return float(screen.devicePixelRatio()) if screen else 1.0

    def _scaled_value(self, value: int) -> int:
        scale = self._scale_factor()
        return int(value / scale) if scale > 1.0 else value

    def event(self, event: QEvent) -> bool:
        if self.screen_worker is None:
            return super().event(event)
        if event.type() == QEvent.WindowActivate:
            self.screen_worker.should_capture = False
        elif event.type() == QEvent.WindowDeactivate:
            self.input_mode = False
            self.show_text(self.latest_response, typing=True)
            self.screen_worker.should_capture = True
        return super().event(event)

    def cvimg_to_qpixmap(self, cv_img) -> QPixmap:
        import cv2

        cv_img_bgra = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2BGRA)
        height, width, _ = cv_img_bgra.shape
        qimg = QImage(cv_img_bgra.data, width, height, 4 * width, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    def _apply_pixmap(self, pixmap: QPixmap, scale_multiplier: float = 1.0) -> None:
        scale = self._scale_factor()
        divisor = int(scale * 2) if scale > 1.0 else 2
        target_width = max(1, int(pixmap.width() * scale_multiplier / divisor))
        target_height = max(1, int(pixmap.height() * scale_multiplier / divisor))
        pixmap = pixmap.scaled(
            target_width,
            target_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        self._position_control_buttons()
        self.update()

    def _position_control_buttons(self) -> None:
        if not hasattr(self, "settings_button") or not hasattr(self, "exit_button"):
            return
        margin = self._scaled_value(8)
        gap = self._scaled_value(8)
        visible_height = max(self.settings_button_size + margin * 2, int(self.height() * self.visible_ratio))
        total_width = self.settings_button_size * 2 + gap
        x = max(margin, self.width() - total_width - margin)
        y = max(margin, min(visible_height - self.settings_button_size - margin, visible_height // 2))
        self.settings_button.move(x, y)
        self.exit_button.move(x + self.settings_button_size + gap, y)
        self.settings_button.raise_()
        self.exit_button.raise_()
        self._position_tool_choice_buttons()

    def _position_tool_choice_buttons(self) -> None:
        if not hasattr(self, "confirm_tool_button") or not hasattr(self, "reject_tool_button"):
            return
        margin = self._scaled_value(10)
        gap = self._scaled_value(8)
        visible_height = max(self.confirm_button_size.height() + margin * 2, int(self.height() * self.visible_ratio))
        total_width = self.confirm_button_size.width() * 2 + gap
        x = max(margin, min(self.text_x_offset_default, self.width() - total_width - margin))
        y = max(margin, visible_height - self.confirm_button_size.height() - margin)
        self.confirm_tool_button.move(x, y)
        self.reject_tool_button.move(x + self.confirm_button_size.width() + gap, y)
        self.confirm_tool_button.raise_()
        self.reject_tool_button.raise_()

    def _show_tool_choice_buttons(self) -> None:
        self._position_tool_choice_buttons()
        self.confirm_tool_button.show()
        self.reject_tool_button.show()
        self.confirm_tool_button.raise_()
        self.reject_tool_button.raise_()

    def _hide_tool_choice_buttons(self) -> None:
        if hasattr(self, "confirm_tool_button"):
            self.confirm_tool_button.hide()
        if hasattr(self, "reject_tool_button"):
            self.reject_tool_button.hide()

    def _set_avatar(
        self,
        image_url: str | None = None,
        image_base64: str | None = None,
        layers: list[int] | None = None,
        fgimage_target: str = DEFAULT_FGIMAGE_TARGET,
    ) -> None:
        if image_url or image_base64:
            try:
                image_path = self.api_client.download_image(
                    image_url,
                    image_base64,
                    self.character.character_id or self.character.name,
                )
                if image_path:
                    pixmap = QPixmap(image_path)
                    if not pixmap.isNull():
                        self._apply_pixmap(pixmap, GENERATED_AVATAR_SCALE)
                        return
            except Exception as exc:
                print(f"Avatar image loading failed: {exc}")

        fallback_layers = layers or DEFAULT_EXPRESSION_LAYERS
        try:
            from Murasame import generate

            cv_img = generate.generate_fgimage(target=fgimage_target, embeddings_layers=fallback_layers)
            self._apply_pixmap(self.cvimg_to_qpixmap(cv_img))
        except Exception as exc:
            print(f"Local expression loading failed: {exc}")

    def set_character(self, character: CharacterProfile) -> None:
        self.character = character
        self.latest_response = character.greeting or self.latest_response
        avatar_url, avatar_base64 = avatar_values_for_emotion(character, "happy")
        self._set_avatar(
            image_url=avatar_url,
            image_base64=avatar_base64,
            layers=character.expression_layers or DEFAULT_EXPRESSION_LAYERS,
            fgimage_target=character.fgimage_target,
        )
        self.show_text(self.latest_response, typing=True)

    def start_move(self, event) -> None:
        if event.button() == Qt.LeftButton:
            visible_height = int(self.height() * self.visible_ratio)
            if event.y() < visible_height // 2:
                self.touch_head = True
                self.head_press_x = event.x()
                self.setCursor(Qt.OpenHandCursor)
            elif event.y() > int(visible_height * 0.7) or self._text_clicked(event.pos()):
                self.begin_text_input()
        if event.button() == Qt.MiddleButton:
            self.offset = event.pos()
            self.setCursor(Qt.SizeAllCursor)

    def begin_text_input(self) -> None:
        self.typing_timer.stop()
        self.input_mode = True
        self.input_buffer = ""
        self.preedit_text = ""
        self.display_text = f"【 {self.api_client.user_name} 】\n  ..."
        self.activateWindow()
        self.setFocus(Qt.MouseFocusReason)
        self.updateMicroFocus()
        self.update()

    def _text_clicked(self, pos) -> bool:
        if not self.display_text:
            return False
        rect = self.rect().adjusted(
            self.text_x_offset,
            self.text_y_offset,
            self.text_x_offset,
            -self.rect().height() // 2 + self.text_y_offset,
        )
        return rect.adjusted(-20, -20, 20, 20).contains(pos)

    def on_move(self, event) -> None:
        if self.touch_head and self.head_press_x is not None and event.buttons() & Qt.LeftButton:
            if abs(event.x() - self.head_press_x) > 50:
                self.start_api_worker("head_touch", f"{self.api_client.user_name}摸了摸你的头")
                self.touch_head = False
                self.head_press_x = None
        if self.offset is not None and event.buttons() == Qt.MiddleButton:
            self.move(self.pos() + event.pos() - self.offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self.offset = None
        if event.button() == Qt.LeftButton:
            self.touch_head = False
            self.head_press_x = None
        self.setCursor(Qt.ArrowCursor)

    def show_text(self, text: str, x_offset: int | None = None, y_offset: int | None = None, typing: bool = True) -> None:
        self.text_x_offset = self._scaled_value(x_offset if x_offset is not None else self.text_x_offset_default)
        self.text_y_offset = self._scaled_value(y_offset if y_offset is not None else self.text_y_offset_default)
        self.typing_prefix = f"【 {self.character.name} 】\n  "
        if typing:
            self.full_text = text
            self.display_text = self.typing_prefix
            self._typing_index = 0
            self.typing_timer.start(self.typing_interval)
        else:
            self.display_text = text
            self.typing_timer.stop()
            self.update()

    def _typing_step(self) -> None:
        if self._typing_index < len(self.full_text):
            self.display_text = self.typing_prefix + self.full_text[: self._typing_index + 1]
            self._typing_index += 1
            self.update()
        else:
            self.typing_timer.stop()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.display_text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setFont(self.text_font)
        rect = self.rect().adjusted(
            self.text_x_offset,
            self.text_y_offset,
            self.text_x_offset,
            -self.rect().height() // 2 + self.text_y_offset,
        )
        align_flag = Qt.AlignLeft | Qt.AlignBottom
        border_size = max(1, self._scaled_value(2))
        painter.setPen(QColor(44, 22, 28))
        for dx, dy in [
            (-border_size, 0),
            (border_size, 0),
            (0, -border_size),
            (0, border_size),
            (border_size, -border_size),
            (border_size, border_size),
            (-border_size, -border_size),
            (-border_size, border_size),
        ]:
            painter.drawText(rect.translated(dx, dy), align_flag, self.display_text)
        painter.setPen(Qt.white)
        painter.drawText(rect, align_flag, self.display_text)
        painter.end()

    def inputMethodQuery(self, query):
        cursor_rectangle_query = getattr(Qt, "ImCursorRectangle", Qt.ImMicroFocus)
        if query in (Qt.ImMicroFocus, cursor_rectangle_query):
            rect = self.rect().adjusted(
                self.text_x_offset,
                self.text_y_offset,
                self.text_x_offset,
                -self.rect().height() // 2 + self.text_y_offset,
            )
            return QRect(rect.bottomLeft(), QSize(1, 30))
        if query == Qt.ImEnabled:
            return self.input_mode
        if query == Qt.ImCursorPosition:
            return len(self.input_buffer)
        if query == Qt.ImSurroundingText:
            return self.input_buffer
        if query == Qt.ImCurrentSelection:
            return ""
        return super().inputMethodQuery(query)

    def inputMethodEvent(self, event) -> None:
        if not self.input_mode:
            super().inputMethodEvent(event)
            return
        if event.commitString():
            self.input_buffer += event.commitString()
        self.preedit_text = event.preeditString()
        self.display_text = f"【 {self.api_client.user_name} 】\n  「{wrap_text(self.input_buffer + self.preedit_text)}」"
        self.updateMicroFocus()
        self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if not self.input_mode:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            text = self.input_buffer.strip()
            self.input_mode = False
            self.preedit_text = ""
            self.clearFocus()
            if text:
                self.start_api_worker("user_text", text)
            event.accept()
            return
        if event.key() == Qt.Key_Backspace and not self.preedit_text:
            self.input_buffer = self.input_buffer[:-1]
        elif event.text() and not self.preedit_text and not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
            self.input_buffer += event.text()
        wrapped = wrap_text(self.input_buffer)
        if not wrapped.strip():
            self.display_text = f"【 {self.api_client.user_name} 】\n  ..."
        else:
            self.display_text = f"【 {self.api_client.user_name} 】\n  「{wrapped}」"
        self.updateMicroFocus()
        self.update()
        event.accept()

    def start_api_worker(self, event: str, text: str, screenshot_base64: str | None = None) -> None:
        if self.llm_worker and self.llm_worker.isRunning():
            if event == "screen_context":
                return
        self.llm_worker = ApiWorker(self.api_client, event, text, screenshot_base64)
        self.llm_worker.finished.connect(self.on_api_result)
        self.llm_worker.start()

    def on_api_result(self, result: PetResponse | None, error: str | None) -> None:
        if error or result is None:
            self.show_text(f"【 系统错误 】\n  {error or 'unknown error'}", typing=False)
            return
        if result.session_id:
            self.api_client.session_id = result.session_id
        if result.tool_action:
            self._handle_tool_action(result)
            return
        self._show_pet_response(result)

    def _show_pet_response(self, result: PetResponse) -> None:
        if not result.tool_action:
            self.pending_tool_action = None
            self._hide_tool_choice_buttons()
        self.latest_response = f"「{wrap_text(result.text)}」"
        self.show_text(self.latest_response, typing=True)
        self.input_buffer = ""
        self.preedit_text = ""
        emotion_image_url, emotion_image_base64 = avatar_values_for_emotion(self.character, result.emotion)
        if emotion_image_url or emotion_image_base64:
            self._set_avatar(
                image_url=emotion_image_url,
                image_base64=emotion_image_base64,
                layers=self.character.expression_layers,
                fgimage_target=self.character.fgimage_target,
            )

    def _handle_tool_action(self, result: PetResponse) -> None:
        action = result.tool_action or {}
        if action.get("type") != "trash_files":
            self._show_pet_response(
                PetResponse(text="工具动作不受支持，我没有执行。", emotion="sad", session_id=self.api_client.session_id)
            )
            return

        files = action.get("files") if isinstance(action.get("files"), list) else []
        names = [str(file_info.get("name")) for file_info in files if isinstance(file_info, dict) and file_info.get("name")]
        if not names:
            self._show_pet_response(PetResponse(text="没有有效文件可操作，我不会执行。", emotion="sad"))
            return
        preview_names = "、".join(names[:4])
        if len(names) > 4:
            preview_names += f" 等 {len(names)} 个文件"
        self.pending_tool_action = action
        self.latest_response = f"「{wrap_text(f'{result.text} 将移到废纸篓：{preview_names}。要确认吗？')}」"
        self.show_text(self.latest_response, typing=True)
        self.input_buffer = ""
        self.preedit_text = ""
        self._show_tool_choice_buttons()

    def confirm_pending_tool_action(self) -> None:
        action = self.pending_tool_action
        if not action:
            self._show_pet_response(PetResponse(text="没有待确认的操作。", emotion="sad"))
            return
        self.pending_tool_action = None
        self._hide_tool_choice_buttons()
        self.show_text("【 系统 】\n  正在移到废纸篓...", typing=False)
        self.tool_worker = ToolActionWorker(self.api_client, action)
        self.tool_worker.finished.connect(self.on_tool_action_result)
        self.tool_worker.start()

    def reject_pending_tool_action(self) -> None:
        self.pending_tool_action = None
        self._hide_tool_choice_buttons()
        self._show_pet_response(PetResponse(text="已拒绝，没有移动任何文件。", emotion="happy"))

    def on_tool_action_result(self, result: PetResponse | None, error: str | None) -> None:
        if error or result is None:
            self.show_text(f"【 系统错误 】\n  {error or 'unknown error'}", typing=False)
            return
        if result.session_id:
            self.api_client.session_id = result.session_id
        self._show_pet_response(result)
