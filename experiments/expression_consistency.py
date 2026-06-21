from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    FIGURES_DIR,
    MANUAL_TEMPLATES_DIR,
    RESULTS_DIR,
    checkerboard,
    ensure_output_dirs,
    fit_on_canvas,
    group_assets,
    load_experiment_config,
    load_label_font,
    load_preferred_image_assets,
    relative_path,
    write_text,
)


REFERENCE_PRIORITY = ("neutral", "idle", "happy", "display")


def prepared_rgb(image: Image.Image, size: tuple[int, int] = (128, 128)) -> Image.Image:
    rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    side = max(rgba.width, rgba.height)
    square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    square.alpha_composite(rgba, ((side - rgba.width) // 2, (side - rgba.height) // 2))
    rgb = Image.new("RGB", square.size, (255, 255, 255))
    rgb.paste(square, mask=square.getchannel("A"))
    return rgb.resize(size, Image.Resampling.LANCZOS)


def centered_rgb_cosine(a: Image.Image, b: Image.Image) -> float:
    arr_a = np.asarray(prepared_rgb(a), dtype=np.float32) / 255.0
    arr_b = np.asarray(prepared_rgb(b), dtype=np.float32) / 255.0
    vec_a = (arr_a - arr_a.mean(axis=(0, 1), keepdims=True)).reshape(-1)
    vec_b = (arr_b - arr_b.mean(axis=(0, 1), keepdims=True)).reshape(-1)
    denom = float(np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
    if denom <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, float(np.dot(vec_a, vec_b) / denom)))


def average_hash_bits(image: Image.Image, size: int = 16) -> np.ndarray:
    gray = prepared_rgb(image, (size, size)).convert("L")
    arr = np.asarray(gray, dtype=np.float32)
    return arr > float(arr.mean())


def ahash_similarity(a: Image.Image, b: Image.Image) -> float:
    bits_a = average_hash_bits(a)
    bits_b = average_hash_bits(b)
    return 1.0 - float(np.count_nonzero(bits_a != bits_b)) / float(bits_a.size)


def choose_reference(assets, reference_priority: tuple[str, ...]) -> object:
    by_expression = {asset.expression.lower(): asset for asset in assets}
    for expression in reference_priority:
        if expression in by_expression:
            return by_expression[expression]
    return assets[0]


def draw_expression_grid(grouped, output_path: Path) -> None:
    max_columns = max((len(items) for items in grouped.values()), default=1)
    cell_size = (220, 360)
    label_height = 42
    header_height = 42
    gap = 14
    margin = 18
    font = load_label_font(22)
    small_font = load_label_font(17)

    width = margin * 2 + max_columns * cell_size[0] + (max_columns - 1) * gap
    row_height = header_height + cell_size[1] + label_height + gap
    height = margin * 2 + len(grouped) * row_height
    canvas = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(canvas)

    y = margin
    for group_key, assets in grouped.items():
        label = f"{assets[0].character_name} ({assets[0].source_kind})"
        draw.text((margin, y), label, fill=(32, 32, 32), font=font)
        y += header_height
        for col, asset in enumerate(assets):
            x = margin + col * (cell_size[0] + gap)
            bg = checkerboard(cell_size, block=18)
            thumb = fit_on_canvas(asset.image, cell_size, bg)
            canvas.paste(thumb, (x, y))
            draw.rectangle((x, y, x + cell_size[0] - 1, y + cell_size[1] - 1), outline=(210, 210, 210))
            draw.text((x + 8, y + cell_size[1] + 8), asset.expression, fill=(45, 45, 45), font=small_font)
        y += cell_size[1] + label_height + gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def main() -> int:
    ensure_output_dirs()
    config = load_experiment_config().get("expression", {})
    reference_priority = tuple(config.get("reference_priority") or REFERENCE_PRIORITY)
    assets = load_preferred_image_assets(save_images=True)
    grouped = group_assets(assets)

    result_csv = RESULTS_DIR / "expression_consistency_summary.csv"
    result_json = RESULTS_DIR / "expression_consistency_summary.json"
    manual_csv = MANUAL_TEMPLATES_DIR / "expression_manual_scores.csv"
    figure_path = FIGURES_DIR / "expression_consistency_grid.png"
    summary_md = RESULTS_DIR / "expression_consistency_summary.md"

    rows: list[dict[str, object]] = []
    manual_rows: list[dict[str, object]] = []

    if not grouped:
        write_text(
            RESULTS_DIR / "expression_input_README.md",
            """# Expression Consistency Input Format

No generated emotion images were found in `config.json` or `character_cards/*.json`.

Place generated expression images in character-specific folders, for example:

```text
experiments/input/expression_images/<character_id>/happy.png
experiments/input/expression_images/<character_id>/sad.png
experiments/input/expression_images/<character_id>/angry.png
```

Then extend `experiments/common.py` or convert the images into the existing character-card
`emotion_images` format before rerunning the experiment.
""",
        )
        with manual_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "image_path",
                    "expression",
                    "identity_score_1_5",
                    "expression_score_1_5",
                    "artifact_score_1_5",
                    "accepted",
                    "notes",
                ],
            )
            writer.writeheader()
        return 0

    for group_key, group_items in grouped.items():
        reference = choose_reference(group_items, reference_priority)
        similarities: list[float] = []
        for asset in group_items:
            cosine = 1.0 if asset is reference else centered_rgb_cosine(reference.image, asset.image)
            ahash = 1.0 if asset is reference else ahash_similarity(reference.image, asset.image)
            if asset is not reference:
                similarities.append(cosine)
            row = {
                "character_group": group_key,
                "character_id": asset.character_id,
                "character_name": asset.character_name,
                "source_kind": asset.source_kind,
                "source_path": asset.source_path,
                "reference_expression": reference.expression,
                "expression": asset.expression,
                "image_path": relative_path(asset.image_path) if asset.image_path else "",
                "centered_rgb_cosine": round(cosine, 6),
                "average_hash_similarity": round(ahash, 6),
            }
            rows.append(row)
            manual_rows.append(
                {
                    "image_path": row["image_path"],
                    "expression": asset.expression,
                    "identity_score_1_5": "",
                    "expression_score_1_5": "",
                    "artifact_score_1_5": "",
                    "accepted": "",
                    "notes": "",
                }
            )
        if not similarities:
            similarities.append(1.0)

    with result_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with manual_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(manual_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manual_rows)

    draw_expression_grid(grouped, figure_path)

    grouped_scores: dict[str, list[float]] = {}
    for row in rows:
        if row["expression"] == row["reference_expression"]:
            continue
        grouped_scores.setdefault(str(row["character_group"]), []).append(float(row["centered_rgb_cosine"]))

    character_summaries = []
    for group_key, values in grouped_scores.items():
        if not values:
            continue
        character_summaries.append(
            {
                "character_group": group_key,
                "mean_centered_rgb_cosine": round(statistics.mean(values), 6),
                "min_centered_rgb_cosine": round(min(values), 6),
                "num_compared_expressions": len(values),
            }
        )

    payload = {
        "method": "alpha-cropped centered RGB cosine similarity and average-hash similarity",
        "limitation": "This is a lightweight visual proxy, not a learned identity model.",
        "num_characters": len(grouped),
        "num_images": len(rows),
        "character_summaries": character_summaries,
    }
    result_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    overall_values = [
        float(row["centered_rgb_cosine"])
        for row in rows
        if row["expression"] != row["reference_expression"] and not math.isnan(float(row["centered_rgb_cosine"]))
    ]
    overall_mean = statistics.mean(overall_values) if overall_values else 1.0
    summary_lines = [
        "# Expression Consistency Evaluation",
        "",
        "## Method",
        "",
        "The script loads generated emotion sprites from the 20-set experiment dataset when it exists; otherwise it "
        "falls back to `config.json` and `character_cards/*.json`. "
        "Because no CLIP or DINO dependency is present in the uv environment, it uses a lightweight proxy: "
        "each transparent sprite is cropped to its alpha bounding box, composited on white, resized to 128x128, "
        "then compared to the reference expression with centered RGB cosine similarity. A 16x16 average-hash "
        "similarity is reported as a second simple check.",
        "",
        "The available assets do not contain `neutral` or `idle`; the script therefore uses `happy` as the reference "
        "when present. This matches the generation pipeline, where `happy` is generated first and the other emotions "
        "are generated from it as references.",
        "",
        "## Results",
        "",
        f"- Characters evaluated: {len(grouped)}",
        f"- Images evaluated: {len(rows)}",
        f"- Mean centered RGB cosine over non-reference expressions: {overall_mean:.4f}",
        f"- CSV summary: `{relative_path(result_csv)}`",
        f"- LLM-as-a-judge scoring template: `{relative_path(manual_csv)}`",
        f"- Visual grid: `{relative_path(figure_path)}`",
        "",
        "## Limitations",
        "",
        "These metrics mainly measure low-level visual similarity after alignment. They are useful for this highly "
        "consistent generated asset set, but they do not replace LLM-as-a-judge review of identity, expression clarity, "
        "or small facial artifacts. LLM-as-a-judge scores should be entered in the provided CSV if subjective acceptance "
        "rates are needed for the report.",
        "",
    ]
    write_text(summary_md, "\n".join(summary_lines))

    print(f"Wrote {relative_path(result_csv)}")
    print(f"Wrote {relative_path(result_json)}")
    print(f"Wrote {relative_path(manual_csv)}")
    print(f"Wrote {relative_path(figure_path)}")
    print(f"Wrote {relative_path(summary_md)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
