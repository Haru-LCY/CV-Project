from __future__ import annotations

import re
from typing import Any


LEGACY_STRENGTH_PATTERN = re.compile(r"^(.*)\(强度([1-5])/5\)$")
LEGACY_STRENGTH_SUFFIX = re.compile(r"\(强度[1-5]/5\)$")


def clean_traits(traits: Any) -> list[str]:
    if not isinstance(traits, list):
        return []
    result = []
    for trait in traits:
        text = LEGACY_STRENGTH_SUFFIX.sub("", str(trait).strip())
        if text:
            result.append(text)
    return result


def clean_trait_list(traits: list[str] | None) -> list[str] | None:
    if not traits:
        return traits
    return clean_traits(traits)


def dimensions_from_legacy_traits(traits: Any) -> dict[str, int]:
    if not isinstance(traits, list):
        return {}
    result: dict[str, int] = {}
    for trait in traits:
        match = LEGACY_STRENGTH_PATTERN.search(str(trait).strip())
        if match:
            result[match.group(1).strip()] = int(match.group(2))
    return result


def normalize_dimensions(dimensions: Any) -> dict[str, int]:
    if not isinstance(dimensions, dict):
        return {}
    result: dict[str, int] = {}
    for trait, strength in dimensions.items():
        trait_text = str(trait).strip()
        if not trait_text:
            continue
        try:
            strength_value = int(strength)
        except (TypeError, ValueError):
            strength_value = 3
        result[trait_text] = min(5, max(1, strength_value))
    return result


def format_dimension_guidance(dimensions: dict[str, int] | None, label: str) -> str:
    if not dimensions:
        return ""
    buckets = {
        1: "只作为很轻的底色",
        2: "作为辅助倾向",
        3: "自然体现",
        4: "明显体现",
        5: "作为主要取向",
    }
    lines = [f"{label}创作取向："]
    for trait, strength in dimensions.items():
        lines.append(f"- {trait}：{buckets.get(strength, '自然体现')}")
    return "\n".join(lines)
