from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from hashlib import sha1
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results" / "experiments"
FIGURES_DIR = RESULTS_DIR / "figures"
EXTRACTED_ASSETS_DIR = RESULTS_DIR / "extracted_assets"
MANUAL_TEMPLATES_DIR = RESULTS_DIR / "manual_templates"
CONFIG_PATH = PROJECT_ROOT / "experiments" / "config.json"
GENERATED_IMAGE_SETS_DIR = RESULTS_DIR / "generated_image_sets"

PREFERRED_EMOTION_ORDER = (
    "neutral",
    "idle",
    "happy",
    "sad",
    "angry",
    "surprised",
    "sleepy",
    "shy",
)


@dataclass
class ImageAsset:
    group_key: str
    character_id: str
    character_name: str
    source_kind: str
    source_path: str
    expression: str
    image: Image.Image
    image_path: Path | None = None


def ensure_output_dirs() -> None:
    for path in (RESULTS_DIR, FIGURES_DIR, EXTRACTED_ASSETS_DIR, MANUAL_TEMPLATES_DIR, GENERATED_IMAGE_SETS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_experiment_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def slugify(value: str | None, fallback: str = "item") -> str:
    text = (value or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._")
    if slug:
        return slug[:80]
    digest = sha1(text.encode("utf-8")).hexdigest()[:10] if text else "unknown"
    return f"{fallback}_{digest}"


def strip_data_uri(value: str) -> str:
    value = value.strip()
    if value.startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value


def decode_base64_image(value: str) -> Image.Image:
    raw = base64.b64decode(strip_data_uri(value))
    with Image.open(BytesIO(raw)) as image:
        return image.convert("RGBA")


def encode_png_base64(image: Image.Image) -> str:
    output = BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def extract_image_base64(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload if payload.strip() else None
    if not isinstance(payload, dict):
        return None
    for key in (
        "display_image_base64",
        "image_base64",
        "base64",
        "image_src",
        "display_image_url",
        "url",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            if key in {"display_image_url", "url"} and not value.startswith("data:image/"):
                continue
            return value
    return None


def _profile_records() -> list[tuple[dict[str, Any], str, str]]:
    records: list[tuple[dict[str, Any], str, str]] = []
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        character = data.get("character")
        if isinstance(character, dict):
            records.append((character, "config", relative_path(config_path)))

    cards_dir = PROJECT_ROOT / "character_cards"
    if cards_dir.exists():
        for path in sorted(cards_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                records.append((data, "character_card", relative_path(path)))
    return records


def load_generated_image_assets(save_images: bool = False) -> list[ImageAsset]:
    ensure_output_dirs()
    assets: list[ImageAsset] = []
    for profile, source_kind, source_path in _profile_records():
        character_id = str(profile.get("character_id") or "")
        character_name = str(profile.get("name") or character_id or Path(source_path).stem)
        group_seed = f"{source_kind}_{character_id or character_name or source_path}"
        group_key = slugify(group_seed, "character")

        emotion_payloads: dict[str, Any] = {}
        raw_emotions = profile.get("emotion_images")
        if isinstance(raw_emotions, dict):
            emotion_payloads.update(raw_emotions)
        if not emotion_payloads:
            display_payload = profile.get("display_image_base64") or profile.get("display_image_url")
            if display_payload:
                emotion_payloads["display"] = display_payload

        for expression in sorted(emotion_payloads, key=emotion_sort_key):
            image_base64 = extract_image_base64(emotion_payloads[expression])
            if not image_base64:
                continue
            image = decode_base64_image(image_base64)
            asset = ImageAsset(
                group_key=group_key,
                character_id=character_id,
                character_name=character_name,
                source_kind=source_kind,
                source_path=source_path,
                expression=expression,
                image=image,
            )
            if save_images:
                output_dir = EXTRACTED_ASSETS_DIR / "sprites" / group_key
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{slugify(expression, 'emotion')}.png"
                image.save(output_path)
                asset.image_path = output_path
            assets.append(asset)
    return assets


def load_experiment_generated_image_assets(save_images: bool = False) -> list[ImageAsset]:
    ensure_output_dirs()
    assets: list[ImageAsset] = []
    for manifest_path in sorted(GENERATED_IMAGE_SETS_DIR.glob("set_*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        set_id = str(manifest.get("set_id") or manifest_path.parent.name)
        character_id = str(manifest.get("character_id") or set_id)
        character_name = str(manifest.get("character_name") or set_id)
        expressions = manifest.get("expressions") if isinstance(manifest.get("expressions"), dict) else {}
        for expression in sorted(expressions, key=emotion_sort_key):
            payload = expressions.get(expression)
            if not isinstance(payload, dict) or not payload.get("sprite_path"):
                continue
            sprite_path = resolve_project_path(str(payload["sprite_path"]))
            if not sprite_path.exists():
                continue
            with Image.open(sprite_path) as image:
                rgba = image.convert("RGBA")
            asset = ImageAsset(
                group_key=set_id,
                character_id=character_id,
                character_name=character_name,
                source_kind="generated_experiment_set",
                source_path=relative_path(manifest_path),
                expression=expression,
                image=rgba,
                image_path=sprite_path,
            )
            if save_images:
                output_dir = EXTRACTED_ASSETS_DIR / "sprites" / set_id
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{slugify(expression, 'emotion')}.png"
                rgba.save(output_path)
                asset.image_path = output_path
            assets.append(asset)
    return assets


def load_preferred_image_assets(save_images: bool = False) -> list[ImageAsset]:
    generated = load_experiment_generated_image_assets(save_images=save_images)
    if generated:
        return generated
    return load_generated_image_assets(save_images=save_images)


def emotion_sort_key(expression: str) -> tuple[int, str]:
    lowered = expression.lower()
    try:
        return (PREFERRED_EMOTION_ORDER.index(lowered), lowered)
    except ValueError:
        return (len(PREFERRED_EMOTION_ORDER), lowered)


def group_assets(assets: Iterable[ImageAsset]) -> dict[str, list[ImageAsset]]:
    grouped: dict[str, list[ImageAsset]] = {}
    for asset in assets:
        grouped.setdefault(asset.group_key, []).append(asset)
    for values in grouped.values():
        values.sort(key=lambda item: emotion_sort_key(item.expression))
    return dict(sorted(grouped.items()))


def load_label_font(size: int) -> ImageFont.ImageFont:
    font_path = PROJECT_ROOT / "思源黑体Bold.otf"
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def checkerboard(size: tuple[int, int], block: int = 16) -> Image.Image:
    image = Image.new("RGB", size, (238, 238, 238))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(206, 206, 206))
    return image


def composite_rgba(image: Image.Image, background: Image.Image | tuple[int, int, int]) -> Image.Image:
    rgba = image.convert("RGBA")
    if isinstance(background, tuple):
        canvas = Image.new("RGB", rgba.size, background)
    else:
        canvas = background.convert("RGB").resize(rgba.size)
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


def fit_on_canvas(
    image: Image.Image,
    size: tuple[int, int],
    background: Image.Image | tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    thumb = image.convert("RGBA")
    thumb.thumbnail(size, Image.Resampling.LANCZOS)
    if isinstance(background, tuple):
        canvas = Image.new("RGB", size, background)
    else:
        canvas = background.convert("RGB").resize(size)
    x = (size[0] - thumb.width) // 2
    y = (size[1] - thumb.height) // 2
    canvas.paste(thumb, (x, y), thumb.getchannel("A"))
    return canvas


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
