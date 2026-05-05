import json


def get_config() -> dict:
    with open("./config.json", "r", encoding="utf-8") as f:
        return json.load(f)
