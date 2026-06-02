import json
import os


DEFAULT_CONFIG = {
    "enable_vl": True,
    "client": {
        "api_base_url": "http://127.0.0.1:28565",
        "session_id": "local-user",
        "timeout_seconds": 120,
    },
    "display": {
        "preset": "balanced",
        "custom": {
            "visible_ratio": 0.4,
            "text_x_offset": 140,
            "text_y_offset": 20,
        },
    },
    "character": {
        "character_id": None,
        "user_name": "用户",
        "auto_open_creator": True,
    },
}


def _merge_defaults(base: dict, overrides: dict) -> dict:
    result = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_defaults(result[key], value)
        else:
            result[key] = value
    return result


def get_config() -> dict:
    with open("./config.json", "r", encoding="utf-8") as f:
        return _merge_defaults(DEFAULT_CONFIG, json.load(f))


def save_config(config: dict) -> None:
    path = "./config.json"
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
        f.write("\n")
    os.replace(tmp_path, path)
