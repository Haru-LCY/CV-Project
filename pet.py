from __future__ import annotations

import base64
import hashlib
import os
import sys
import tempfile
import textwrap
import traceback
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlparse

import cv2
import pyautogui
import requests
from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PyQt5.QtMultimedia import QSound
from PyQt5.QtWidgets import QAction, QApplication, QLabel, QMenu, QSystemTrayIcon

from Murasame import generate, utils

screen_worker = None


def wrap_text(text: str, width: int = 12) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False))


@dataclass
class PetResponse:
    text: str
    expression_layers: list[int]
    audio_url: str | None = None
    audio_base64: str | None = None
    session_id: str | None = None


class PetApiClient:
    def __init__(self) -> None:
        config = utils.get_config()
        client_config = config.get("client", {})
        self.base_url = client_config.get("api_base_url", "http://127.0.0.1:28565").rstrip("/")
        self.session_id = client_config.get("session_id", "local-user")
        self.timeout = float(client_config.get("timeout_seconds", 120))

    def respond(self, event: str, text: str, screenshot_base64: str | None = None) -> PetResponse:
        payload = {
            "session_id": self.session_id,
            "event": event,
            "text": text,
        }
        if screenshot_base64:
            payload["screenshot"] = screenshot_base64

        response = requests.post(
            f"{self.base_url}/v1/pet/respond",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return PetResponse(
            text=data.get("text") or data.get("raw_text") or "",
            expression_layers=data.get("expression_layers") or [1717, 1475, 1261],
            audio_url=data.get("audio_url"),
            audio_base64=data.get("audio_base64"),
            session_id=data.get("session_id") or self.session_id,
        )

    def download_audio(self, result: PetResponse) -> str | None:
        if result.audio_base64:
            audio_bytes = base64.b64decode(result.audio_base64)
            return self._write_audio(audio_bytes, result.text)
        if not result.audio_url:
            return None

        audio_url = result.audio_url
        if not urlparse(audio_url).scheme:
            audio_url = urljoin(f"{self.base_url}/", audio_url.lstrip("/"))
        response = requests.get(audio_url, timeout=self.timeout)
        response.raise_for_status()
        return self._write_audio(response.content, result.audio_url)

    def _write_audio(self, audio_bytes: bytes, key: str) -> str:
        voices_dir = os.path.join(tempfile.gettempdir(), "murasame_pet_voices")
        os.makedirs(voices_dir, exist_ok=True)
        filename = hashlib.md5(key.encode("utf-8")).hexdigest() + ".wav"
        path = os.path.join(voices_dir, filename)
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path


class Murasame(QLabel):
    DISPLAY_PRESETS = {
        "compact": {"visible_ratio": 0.35, "text_x_offset": 120, "text_y_offset": 15},
        "balanced": {"visible_ratio": 0.45, "text_x_offset": 140, "text_y_offset": 20},
        "standard": {"visible_ratio": 0.6, "text_x_offset": 150, "text_y_offset": 25},
        "full": {"visible_ratio": 1.0, "text_x_offset": 160, "text_y_offset": -100},
    }

    def __init__(self, api_client: PetApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.latest_response = "主人，你好呀！"
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

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_macos_window_level()

        self.text_font = QFont()
        self.text_font.setFamily("思源黑体 CN Bold")
        QFontDatabase.addApplicationFont("./思源黑体Bold.otf")
        self.text_font.setPointSize(self._scaled_value(24))
        self.text_x_offset = 0
        self.text_y_offset = 0

        self.typing_timer = QTimer()
        self.typing_timer.timeout.connect(self._typing_step)
        self.typing_interval = 40

        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.mousePressEvent = self.start_move
        self.mouseMoveEvent = self.on_move
        self._set_expression([1717, 1475, 1261])

    def _setup_macos_window_level(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from AppKit import NSFloatingWindowLevel
            from objc import objc_object
            from ctypes import c_void_p

            def set_level() -> None:
                try:
                    view = objc_object(c_void_p=c_void_p(int(self.winId())))
                    window = view.window()
                    if window:
                        window.setLevel_(NSFloatingWindowLevel)
                except Exception as exc:
                    print(f"Failed to set macOS window level: {exc}")

            QTimer.singleShot(100, set_level)
        except Exception:
            pass

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
        global screen_worker
        if screen_worker is None:
            return super().event(event)
        if event.type() == QEvent.WindowActivate:
            screen_worker.should_capture = False
        elif event.type() == QEvent.WindowDeactivate:
            self.input_mode = False
            self.show_text(self.latest_response, typing=True)
            screen_worker.should_capture = True
        return super().event(event)

    def cvimg_to_qpixmap(self, cv_img) -> QPixmap:
        cv_img_bgra = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2BGRA)
        height, width, _ = cv_img_bgra.shape
        qimg = QImage(cv_img_bgra.data, width, height, 4 * width, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)

    def _set_expression(self, layers: list[int]) -> None:
        cv_img = generate.generate_fgimage(target="ムラサメb", embeddings_layers=layers)
        pixmap = self.cvimg_to_qpixmap(cv_img)
        scale = self._scale_factor()
        divisor = int(scale * 2) if scale > 1.0 else 2
        pixmap = pixmap.scaled(
            pixmap.width() // divisor,
            pixmap.height() // divisor,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        self.update()

    def start_move(self, event) -> None:
        if event.button() == Qt.LeftButton:
            visible_height = int(self.height() * self.visible_ratio)
            if event.y() < visible_height // 2:
                self.touch_head = True
                self.head_press_x = event.x()
                self.setCursor(Qt.OpenHandCursor)
            elif event.y() > int(visible_height * 0.7) or self._text_clicked(event.pos()):
                self.input_mode = True
                self.input_buffer = ""
                self.display_text = "【 LemonQu 】\n  ..."
                self.update()
        if event.button() == Qt.MiddleButton:
            self.offset = event.pos()
            self.setCursor(Qt.SizeAllCursor)

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
                self.start_api_worker("head_touch", "主人摸了摸你的头")
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
        self.typing_prefix = "【 丛雨 】\n  "
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
        if query == Qt.ImMicroFocus:
            rect = self.rect().adjusted(
                self.text_x_offset,
                self.text_y_offset,
                self.text_x_offset,
                -self.rect().height() // 2 + self.text_y_offset,
            )
            return QRect(self.mapToGlobal(rect.bottomLeft()), QSize(1, 30))
        return super().inputMethodQuery(query)

    def inputMethodEvent(self, event) -> None:
        if not self.input_mode:
            super().inputMethodEvent(event)
            return
        if event.commitString():
            self.input_buffer += event.commitString()
        self.preedit_text = event.preeditString()
        self.display_text = f"【 LemonQu 】\n  「{wrap_text(self.input_buffer + self.preedit_text)}」"
        self.update()

    def keyPressEvent(self, event) -> None:
        if not self.input_mode:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            text = self.input_buffer.strip()
            self.input_mode = False
            if text:
                self.start_api_worker("user_text", text)
            return
        if event.key() == Qt.Key_Backspace and not self.preedit_text:
            self.input_buffer = self.input_buffer[:-1]
        elif event.text() and not self.preedit_text:
            self.input_buffer += event.text()
        wrapped = wrap_text(self.input_buffer)
        self.display_text = "【 LemonQu 】\n  ..." if not wrapped.strip() else f"【 LemonQu 】\n  「{wrapped}」"
        self.update()

    def start_api_worker(self, event: str, text: str, screenshot_base64: str | None = None) -> None:
        self.llm_worker = ApiWorker(self.api_client, event, text, screenshot_base64)
        self.llm_worker.finished.connect(self.on_api_result)
        self.llm_worker.start()

    def on_api_result(self, result: PetResponse | None, error: str | None) -> None:
        if error or result is None:
            self.show_text(f"【 系统错误 】\n  {error or 'unknown error'}", typing=False)
            return
        if result.session_id:
            self.api_client.session_id = result.session_id
        if result.audio_url or result.audio_base64:
            try:
                audio_path = self.api_client.download_audio(result)
                if audio_path:
                    QSound.play(audio_path)
            except Exception as exc:
                print(f"Audio playback failed: {exc}")
        self.latest_response = f"「{wrap_text(result.text)}」"
        self.show_text(self.latest_response, typing=True)
        self.input_buffer = ""
        self.preedit_text = ""
        self._set_expression(result.expression_layers)


class ScreenWorker(QThread):
    screen_result = pyqtSignal(str)

    def __init__(self, api_client: PetApiClient, parent=None) -> None:
        super().__init__(parent)
        self.api_client = api_client
        self.running = True
        self.should_capture = False

    def run(self) -> None:
        while self.running:
            if self.should_capture:
                try:
                    screenshot = pyautogui.screenshot()
                    buffered = BytesIO()
                    screenshot.save(buffered, format="PNG")
                    encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    self.screen_result.emit(encoded)
                except Exception:
                    traceback.print_exc()
            self.sleep(30)

    def stop(self) -> None:
        self.running = False


class ApiWorker(QThread):
    finished = pyqtSignal(object, object)

    def __init__(self, api_client: PetApiClient, event: str, text: str, screenshot_base64: str | None = None) -> None:
        super().__init__()
        self.api_client = api_client
        self.event = event
        self.text = text
        self.screenshot_base64 = screenshot_base64

    def run(self) -> None:
        try:
            result = self.api_client.respond(self.event, self.text, self.screenshot_base64)
            self.finished.emit(result, None)
        except Exception as exc:
            traceback.print_exc()
            self.finished.emit(None, f"{type(exc).__name__}: {exc}")


def clear_history(parent, api_client: PetApiClient) -> None:
    api_client.session_id = utils.get_config().get("client", {}).get("session_id", "local-user")
    parent.latest_response = "记忆已经清空了。"
    parent.show_text(parent.latest_response, typing=True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    api_client = PetApiClient()
    murasame = Murasame(api_client)

    screen = app.primaryScreen()
    screen_geometry = screen.availableGeometry()
    x = screen_geometry.width() - murasame.width() - 20
    y = screen_geometry.height() - int(murasame.height() * murasame.visible_ratio)
    murasame.move(x, y)
    murasame.show()

    tray_icon = QSystemTrayIcon(QIcon("icon.png"), parent=app)
    tray_menu = QMenu()
    clear_action = QAction("Clear History")
    clear_action.triggered.connect(lambda: clear_history(murasame, api_client))
    exit_action = QAction("Exit")
    exit_action.triggered.connect(app.quit)
    tray_menu.addAction(clear_action)
    tray_menu.addAction(exit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.show()

    murasame.show_text(murasame.latest_response, typing=True)

    screen_worker = ScreenWorker(api_client)
    if utils.get_config().get("enable_vl", True):
        screen_worker.screen_result.connect(
            lambda screenshot: murasame.start_api_worker("screen_context", "", screenshot)
        )
        screen_worker.start()

    sys.exit(app.exec_())
