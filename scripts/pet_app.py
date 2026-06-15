from __future__ import annotations

import sys

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon

from Murasame import utils
from Murasame.paths import resource_path
from scripts.pet_actions import (
    clear_history,
    clear_long_term_memory,
    load_initial_character,
    open_character_settings,
    regenerate_character_image,
)
from scripts.pet_api import PetApiClient
from scripts.pet_widget import DesktopPet
from scripts.pet_workers import ScreenWorker


def main(argv: list[str] | None = None) -> int:
    configure_windows_app_id()
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv if argv is None else argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("MurasamePet")
    app.setWindowIcon(QIcon(str(resource_path("icon.png"))))

    api_client = PetApiClient()
    desktop_pet = DesktopPet(api_client, load_initial_character(api_client))
    desktop_pet.settings_requested.connect(lambda: open_character_settings(desktop_pet, api_client))

    screen = app.primaryScreen()
    screen_geometry = screen.availableGeometry()
    x = screen_geometry.width() - desktop_pet.width() - 20
    y = max(0, screen_geometry.height() - int(desktop_pet.height() * desktop_pet.visible_ratio) - 80)
    desktop_pet.move(x, y)
    desktop_pet.show()

    tray_icon = QSystemTrayIcon(QIcon(str(resource_path("icon.png"))), parent=app)
    tray_menu = QMenu()
    character_action = QAction("角色设置")
    character_action.triggered.connect(desktop_pet.settings_requested.emit)
    regenerate_image_action = QAction("重新生成人设图")
    regenerate_image_action.triggered.connect(lambda: regenerate_character_image(desktop_pet, api_client))
    clear_action = QAction("清空本轮对话")
    clear_action.triggered.connect(lambda: clear_history(desktop_pet, api_client))
    clear_long_term_action = QAction("清空长期记忆")
    clear_long_term_action.triggered.connect(lambda: clear_long_term_memory(desktop_pet, api_client))
    exit_action = QAction("退出")
    exit_action.triggered.connect(app.quit)
    tray_menu.addAction(character_action)
    tray_menu.addAction(regenerate_image_action)
    tray_menu.addAction(clear_action)
    tray_menu.addAction(clear_long_term_action)
    tray_menu.addAction(exit_action)
    tray_icon.setContextMenu(tray_menu)
    tray_icon.show()

    desktop_pet.show_text(desktop_pet.latest_response, typing=True)
    auto_open = utils.get_config().get("character", {}).get("auto_open_creator", True)
    if not api_client.character_profile.character_id and auto_open:
        QTimer.singleShot(500, lambda: open_character_settings(desktop_pet, api_client))

    screen_worker = ScreenWorker(api_client)
    desktop_pet.screen_worker = screen_worker
    if utils.get_config().get("enable_vl", True):
        screen_worker.screen_result.connect(
            lambda screenshot: desktop_pet.start_api_worker("screen_context", "", screenshot) if screenshot else None
        )
        screen_worker.start()
        app.aboutToQuit.connect(screen_worker.stop)

    return app.exec_()


def configure_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MurasamePet.Client")
    except Exception as exc:
        print(f"Failed to set Windows AppUserModelID: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
