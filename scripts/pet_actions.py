from __future__ import annotations

import traceback

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from Murasame import utils
from Murasame.macos_window import apply_top_layer
from scripts.pet_api import PetApiClient
from scripts.pet_defaults import DEFAULT_CHARACTER_OPTIONS, DEFAULT_EXPRESSION_LAYERS
from scripts.pet_widget import DesktopPet
from scripts.profile import CharacterProfile, DEFAULT_USER_NAME
from scripts.workbench.dialog import CharacterCreatorDialog
from scripts.workbench.generator import LocalCharacterGenerator


def clear_history(parent, api_client: PetApiClient) -> None:
    api_client.session_id = utils.get_config().get("client", {}).get("session_id", "local-user")
    api_client.history.clear()
    parent.latest_response = "本轮对话已经清空了。"
    parent.show_text(parent.latest_response, typing=True)

def clear_long_term_memory(parent, api_client: PetApiClient) -> None:
    api_client.memory.clear_user(api_client.memory.config.user_id)
    parent.latest_response = "长期记忆已经清空了。"
    parent.show_text(parent.latest_response, typing=True)

def load_initial_character(api_client: PetApiClient) -> CharacterProfile:
    if api_client.character_profile.character_id or api_client.character_profile.persona:
        return api_client.character_profile
    return CharacterProfile(expression_layers=DEFAULT_EXPRESSION_LAYERS)

def get_character_options(api_client: PetApiClient) -> dict:
    try:
        return api_client.get_character_options()
    except Exception as exc:
        print(f"Failed to load character options: {exc}")
        return DEFAULT_CHARACTER_OPTIONS

def open_character_settings(parent: DesktopPet, api_client: PetApiClient) -> None:
    print("Character settings requested")

    def show_character_dialog(dialog: CharacterCreatorDialog) -> None:
        dialog.showNormal()
        dialog.raise_()
        dialog.activateWindow()
        top_layer_applied = apply_top_layer(dialog, level="screensaver")
        print(
            "Character settings dialog shown: "
            f"visible={dialog.isVisible()}, top_layer={top_layer_applied}"
        )

    existing_dialog = getattr(parent, "character_dialog", None)
    if existing_dialog is not None and existing_dialog.isVisible():
        parent.hide()
        show_character_dialog(existing_dialog)
        QTimer.singleShot(250, lambda: show_character_dialog(existing_dialog))
        return

    dialog = CharacterCreatorDialog(
        get_character_options(api_client),
        api_client,
        DEFAULT_CHARACTER_OPTIONS,
        DEFAULT_USER_NAME,
    )
    print("Character settings dialog created")
    parent.character_dialog = dialog

    def apply_preview_profile() -> None:
        if dialog.preview_profile is None:
            return
        api_client.remember_character(dialog.preview_profile, dialog.preview_user_name)
        parent.set_character(dialog.preview_profile)

    def clear_dialog_reference() -> None:
        if getattr(parent, "character_dialog", None) is dialog:
            parent.character_dialog = None
        parent.show()
        parent.ensure_top_layer()

    dialog.accepted.connect(apply_preview_profile)
    dialog.finished.connect(lambda _result: clear_dialog_reference())
    parent.hide()
    show_character_dialog(dialog)
    QTimer.singleShot(0, lambda: show_character_dialog(dialog))
    QTimer.singleShot(250, lambda: show_character_dialog(dialog))

def regenerate_character_image(parent: DesktopPet, api_client: PetApiClient) -> None:
    profile = api_client.character_profile
    if not (profile.appearance_traits and profile.personality_traits and profile.style):
        QMessageBox.information(parent, "缺少角色设定", "请先在角色设置中生成并应用角色。")
        return
    try:
        regenerated = LocalCharacterGenerator(timeout=int(api_client.timeout)).generate(
            user_name=api_client.user_name,
            appearance_traits=profile.appearance_traits,
            personality_traits=profile.personality_traits,
            identity_traits=profile.identity_traits,
            style=profile.style,
            personality_dimensions=profile.personality_dimensions,
            appearance_style_dimensions=profile.appearance_style_dimensions,
        )
        api_client.remember_character(regenerated, api_client.user_name)
        parent.set_character(regenerated)
    except Exception as exc:
        traceback.print_exc()
        QMessageBox.warning(parent, "重新生成人设图失败", f"{type(exc).__name__}: {exc}")
