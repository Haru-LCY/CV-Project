from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    FIGURES_DIR,
    MANUAL_TEMPLATES_DIR,
    PROJECT_ROOT,
    RESULTS_DIR,
    checkerboard,
    composite_rgba,
    encode_png_base64,
    ensure_output_dirs,
    fit_on_canvas,
    load_generated_image_assets,
    load_experiment_config,
    load_experiment_generated_image_assets,
    load_label_font,
    relative_path,
    resolve_project_path,
    slugify,
    write_text,
)
from scripts.workbench.image_processing import DesktopPetImageProcessor, make_desktop_pet_standee  # noqa: E402


INPUT_DIR = PROJECT_ROOT / "experiments" / "input" / "white_background"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def near_white_mask(rgb: np.ndarray, min_value: int = 245, max_chroma: int = 30) -> np.ndarray:
    channel_min = rgb.min(axis=2)
    channel_max = rgb.max(axis=2)
    return (channel_min >= min_value) & ((channel_max - channel_min) <= max_chroma)


def naive_white_threshold_alpha(image: Image.Image) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"))
    alpha = np.where(near_white_mask(rgb, min_value=245, max_chroma=24), 0, 255).astype(np.uint8)
    return Image.fromarray(alpha)


def apply_alpha(image: Image.Image, alpha: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


def white_composite(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    canvas.alpha_composite(rgba)
    return canvas


def final_standee_from_source(source: Image.Image) -> Image.Image:
    result_base64 = make_desktop_pet_standee(encode_png_base64(source.convert("RGB")))
    from common import decode_base64_image

    return decode_base64_image(result_base64)


def alpha_metrics(source: Image.Image, output_alpha: Image.Image, truth_alpha: Image.Image | None) -> dict[str, float | int | str]:
    out = np.asarray(output_alpha.resize(source.size), dtype=np.uint8)
    rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    output_fg = out > 10

    if truth_alpha is None:
        opaque = output_fg
        near_white = near_white_mask(rgb, min_value=235, max_chroma=42)
        kernel = np.ones((7, 7), dtype=np.uint8)
        fg_binary = output_fg.astype(np.uint8)
        dilated = cv2.dilate(fg_binary, kernel, iterations=1).astype(bool)
        eroded = cv2.erode(fg_binary, kernel, iterations=1).astype(bool)
        boundary = dilated & ~eroded

        not_fg = ~output_fg
        num_labels, labels = cv2.connectedComponents(not_fg.astype(np.uint8), connectivity=8)
        border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
        hole_components = 0
        for label in range(1, num_labels):
            if label in border_labels:
                continue
            if int(np.count_nonzero(labels == label)) >= 8:
                hole_components += 1

        return {
            "foreground_alpha_sum": round(float(out.sum() / 255.0), 3),
            "opaque_white_pixel_ratio": round(float(np.count_nonzero(opaque & near_white) / max(1, np.count_nonzero(opaque))), 6),
            "background_residue_ratio": "",
            "core_character_loss_ratio": "",
            "foreground_area_change_ratio": "",
            "boundary_alpha_mae": "",
            "suspicious_hole_components": hole_components,
            "white_residue_near_boundary_ratio": round(
                float(np.count_nonzero(output_fg & boundary & near_white) / max(1, np.count_nonzero(output_fg & boundary))),
                6,
            ),
        }

    truth = np.asarray(truth_alpha.resize(source.size), dtype=np.uint8)
    truth_fg = truth > 10
    truth_core = truth > 128
    near_white = near_white_mask(rgb, min_value=235, max_chroma=42)

    kernel = np.ones((7, 7), dtype=np.uint8)
    truth_binary = truth_fg.astype(np.uint8)
    dilated = cv2.dilate(truth_binary, kernel, iterations=1).astype(bool)
    eroded = cv2.erode(truth_binary, kernel, iterations=1).astype(bool)
    boundary = dilated & ~eroded
    outside_boundary = boundary & ~truth_fg

    lost_core = truth_core & ~output_fg
    components = 0
    if np.any(lost_core):
        components = int(cv2.connectedComponents(lost_core.astype(np.uint8), connectivity=8)[0] - 1)

    truth_area = max(1.0, float(truth.sum() / 255.0))
    output_area = float(out.sum() / 255.0)
    boundary_mae = 0.0
    if np.any(boundary):
        boundary_mae = float(np.mean(np.abs(out[boundary].astype(np.float32) - truth[boundary].astype(np.float32)) / 255.0))

    return {
        "foreground_alpha_sum": round(output_area, 3),
        "opaque_white_pixel_ratio": round(float(np.count_nonzero(output_fg & near_white) / max(1, np.count_nonzero(output_fg))), 6),
        "background_residue_ratio": round(float(np.count_nonzero(output_fg & ~truth_fg) / max(1, np.count_nonzero(~truth_fg))), 6),
        "core_character_loss_ratio": round(float(np.count_nonzero(lost_core) / max(1, np.count_nonzero(truth_core))), 6),
        "foreground_area_change_ratio": round(float((output_area - truth_area) / truth_area), 6),
        "boundary_alpha_mae": round(boundary_mae, 6),
        "suspicious_hole_components": components,
        "white_residue_near_boundary_ratio": round(
            float(np.count_nonzero(output_fg & outside_boundary & near_white) / max(1, np.count_nonzero(outside_boundary))),
            6,
        ),
    }


def complex_background(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, (232, 238, 244))
    draw = ImageDraw.Draw(image)
    colors = [(86, 120, 155), (232, 176, 92), (106, 154, 120), (188, 96, 120)]
    stripe_w = max(18, size[0] // 8)
    for idx, x in enumerate(range(-size[1], size[0] + size[1], stripe_w)):
        color = colors[idx % len(colors)]
        draw.polygon([(x, 0), (x + stripe_w, 0), (x + stripe_w + size[1], size[1]), (x + size[1], size[1])], fill=color)
    overlay = Image.new("RGBA", size, (255, 255, 255, 85))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], max(24, size[0] // 10)):
        draw.line((x, 0, x, size[1]), fill=(250, 250, 250), width=2)
    for y in range(0, size[1], max(24, size[1] // 10)):
        draw.line((0, y, size[0], y), fill=(250, 250, 250), width=2)
    return image


def draw_method_grid(examples: list[dict[str, object]], output_path: Path) -> None:
    if not examples:
        return
    columns = [
        ("synthetic source", "source"),
        ("naive threshold", "naive"),
        ("flood-fill alpha", "final_alpha"),
        ("final standee", "standee"),
    ]
    cell_size = (190, 260)
    header_h = 42
    row_label_w = 170
    gap = 10
    margin = 16
    font = load_label_font(17)
    small_font = load_label_font(14)
    width = margin * 2 + row_label_w + len(columns) * cell_size[0] + (len(columns) - 1) * gap
    height = margin * 2 + header_h + len(examples) * (cell_size[1] + gap)
    canvas = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(canvas)

    x0 = margin + row_label_w
    for col, (label, _) in enumerate(columns):
        draw.text((x0 + col * (cell_size[0] + gap), margin), label, fill=(35, 35, 35), font=font)

    y = margin + header_h
    for row, example in enumerate(examples):
        draw.text((margin, y + 10), str(example["label"])[:18], fill=(45, 45, 45), font=small_font)
        for col, (_, key) in enumerate(columns):
            x = x0 + col * (cell_size[0] + gap)
            image = example[key]
            bg = checkerboard(cell_size, block=16)
            thumb = fit_on_canvas(image, cell_size, bg)
            canvas.paste(thumb, (x, y))
            draw.rectangle((x, y, x + cell_size[0] - 1, y + cell_size[1] - 1), outline=(210, 210, 210))
        y += cell_size[1] + gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def draw_composite_grid(sprite: Image.Image, output_path: Path) -> None:
    backgrounds = [
        ("black", Image.new("RGB", sprite.size, (0, 0, 0))),
        ("gray", Image.new("RGB", sprite.size, (130, 130, 130))),
        ("checker", checkerboard(sprite.size, block=18)),
        ("complex", complex_background(sprite.size)),
    ]
    cell_size = (210, 280)
    label_h = 36
    margin = 16
    gap = 12
    font = load_label_font(17)
    width = margin * 2 + len(backgrounds) * cell_size[0] + (len(backgrounds) - 1) * gap
    height = margin * 2 + cell_size[1] + label_h
    canvas = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(canvas)
    for idx, (label, bg) in enumerate(backgrounds):
        x = margin + idx * (cell_size[0] + gap)
        composite = composite_rgba(sprite, bg)
        canvas.paste(fit_on_canvas(composite.convert("RGBA"), cell_size, (255, 255, 255)), (x, margin))
        draw.text((x + 8, margin + cell_size[1] + 8), label, fill=(35, 35, 35), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def input_readme() -> None:
    readme = INPUT_DIR / "README.md"
    write_text(
        readme,
        """# White-Background Source Images

The repository currently stores post-processed transparent sprites in `config.json`
and `character_cards/*.json`, but it does not store the original white-background
portraits returned by the image model.

For a direct evaluation, place original source portraits here:

```text
experiments/input/white_background/<character_or_case_name>.png
```

Use PNG, JPEG, or WebP files with a pure or near-white background. The experiment
script will process these images with the naive baseline and the project pipeline.
If this folder is empty, the script runs a clearly marked proxy experiment by
compositing the stored transparent sprites onto white backgrounds and measuring
whether the removal methods recover the original alpha mask.
""",
    )


def load_real_white_sources(input_dir: Path) -> list[dict[str, object]]:
    if not input_dir.exists():
        return []
    sources: list[dict[str, object]] = []
    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
        source = white_composite(rgba)
        sources.append(
            {
                "group_key": slugify(path.stem, "source"),
                "character_id": "",
                "character_name": path.stem,
                "expression": path.stem,
                "source": source,
                "truth_alpha": None,
                "source_type": "real_white_background_input",
                "reported_source_path": relative_path(path),
                "label": path.stem,
            }
        )
    return sources


def load_generated_white_sources() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for asset in load_experiment_generated_image_assets(save_images=False):
        manifest = json.loads(resolve_project_path(asset.source_path).read_text(encoding="utf-8"))
        expression_payload = manifest.get("expressions", {}).get(asset.expression, {})
        source_value = expression_payload.get("source_path") if isinstance(expression_payload, dict) else None
        if not source_value:
            continue
        source_path = resolve_project_path(str(source_value))
        if not source_path.exists():
            continue
        with Image.open(source_path) as image:
            source = white_composite(image.convert("RGBA"))
        cases.append(
            {
                "group_key": asset.group_key,
                "character_id": asset.character_id,
                "character_name": asset.character_name,
                "expression": asset.expression,
                "source": source,
                "truth_alpha": None,
                "source_type": "generated_white_background_source",
                "reported_source_path": relative_path(source_path),
                "label": f"{asset.character_name} {asset.expression}",
            }
        )
    return cases


def proxy_sources_from_sprites() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for asset in load_generated_image_assets(save_images=True):
        source = white_composite(asset.image)
        cases.append(
            {
                "group_key": asset.group_key,
                "character_id": asset.character_id,
                "character_name": asset.character_name,
                "expression": asset.expression,
                "source": source,
                "truth_alpha": asset.image.getchannel("A"),
                "source_type": "synthetic_white_composite_from_processed_sprite",
                "reported_source_path": "",
                "label": f"{asset.character_name} {asset.expression}",
            }
        )
    return cases


def main() -> int:
    ensure_output_dirs()
    input_readme()
    config = load_experiment_config().get("background", {})
    input_dir = PROJECT_ROOT / str(config.get("source_input_dir") or "experiments/input/white_background")
    processor = DesktopPetImageProcessor()
    output_root = RESULTS_DIR / "background_postprocessing"
    output_root.mkdir(parents=True, exist_ok=True)

    real_sources = load_real_white_sources(input_dir)
    generated_sources = load_generated_white_sources()
    cases = real_sources or generated_sources or proxy_sources_from_sprites()
    source_note = (
        "Direct experiment: real white-background source portraits were loaded from the configured input directory."
        if real_sources
        else (
            "Direct experiment: white-background source portraits generated by experiments/generate_image_sets.py were used."
            if generated_sources
            else "Proxy experiment: transparent stored sprites were composited onto white because original white-background generated portraits are not stored in the repository."
        )
    )
    examples: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []

    for case in cases:
        source = case["source"]
        truth_alpha = case["truth_alpha"]
        expression = str(case["expression"])
        base_dir = output_root / str(case["group_key"]) / slugify(expression, "expression")
        base_dir.mkdir(parents=True, exist_ok=True)

        source_path = base_dir / "synthetic_white_source.png"
        source.save(source_path)
        reported_source_path = str(case["reported_source_path"]) or relative_path(source_path)

        naive_alpha = naive_white_threshold_alpha(source)
        naive = apply_alpha(source, naive_alpha)
        naive_path = base_dir / "naive_threshold.png"
        naive.save(naive_path)

        final_alpha = processor._white_background_alpha(source)
        final_alpha_image = apply_alpha(source, final_alpha)
        final_alpha_cropped = processor._crop_to_alpha(final_alpha_image, padding=28)
        final_alpha_path = base_dir / "final_flood_fill_alpha.png"
        final_alpha_cropped.save(final_alpha_path)

        standee = final_standee_from_source(source)
        standee_path = base_dir / "final_standee.png"
        standee.save(standee_path)

        for method, alpha, visual_path in (
            ("naive_white_threshold", naive_alpha, naive_path),
            ("project_flood_fill_alpha", final_alpha, final_alpha_path),
        ):
            metrics = alpha_metrics(source, alpha, truth_alpha)
            row = {
                "character_group": case["group_key"],
                "character_id": case["character_id"],
                "character_name": case["character_name"],
                "expression": expression,
                "source_type": case["source_type"],
                "source_path": reported_source_path,
                "working_source_path": relative_path(source_path),
                "method": method,
                "output_path": relative_path(visual_path),
                **metrics,
            }
            rows.append(row)

        if len(examples) < 6:
            examples.append(
                {
                    "label": case["label"],
                    "source": source,
                    "naive": naive,
                    "final_alpha": final_alpha_cropped,
                    "standee": standee,
                }
            )

        if len(examples) == 1:
            draw_composite_grid(standee, FIGURES_DIR / "background_composites.png")

    metrics_csv = RESULTS_DIR / "background_postprocessing_metrics.csv"
    manual_csv = MANUAL_TEMPLATES_DIR / "background_manual_scores.csv"
    summary_json = RESULTS_DIR / "background_postprocessing_summary.json"
    summary_md = RESULTS_DIR / "background_postprocessing_summary.md"
    figure_path = FIGURES_DIR / "background_postprocessing_examples.png"
    draw_method_grid(examples, figure_path)

    if rows:
        with metrics_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        with metrics_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["source_path", "method", "notes"])
            writer.writeheader()

    with manual_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_path",
                "method",
                "white_residue_score_1_5",
                "edge_quality_score_1_5",
                "character_preservation_score_1_5",
                "compositing_quality_score_1_5",
                "accepted",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_path": row["source_path"],
                    "method": row["method"],
                    "white_residue_score_1_5": "",
                    "edge_quality_score_1_5": "",
                    "character_preservation_score_1_5": "",
                    "compositing_quality_score_1_5": "",
                    "accepted": "",
                    "notes": "",
                }
            )

    method_summary: dict[str, dict[str, float]] = {}
    for method in sorted({str(row["method"]) for row in rows}):
        method_rows = [row for row in rows if row["method"] == method]
        numeric_keys = [
            "foreground_alpha_sum",
            "opaque_white_pixel_ratio",
            "background_residue_ratio",
            "core_character_loss_ratio",
            "foreground_area_change_ratio",
            "boundary_alpha_mae",
            "suspicious_hole_components",
            "white_residue_near_boundary_ratio",
        ]
        method_summary[method] = {}
        for key in numeric_keys:
            values = [float(row[key]) for row in method_rows if row[key] != ""]
            if values:
                method_summary[method][f"mean_{key}"] = round(statistics.mean(values), 6)

    summary_json.write_text(
        json.dumps(
            {
                "source_note": source_note,
                "num_sources": len(cases),
                "num_real_sources": len(real_sources),
                "methods": method_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    metrics_heading = "Aggregate Metrics" if (real_sources or generated_sources) else "Aggregate Proxy Metrics"
    source_method_text = (
        "For this run, user-provided white-background source portraits were loaded from "
        "`experiments/input/white_background/`."
        if real_sources
        else (
            "For this run, the script used raw white-background source portraits generated by "
            "`experiments/generate_image_sets.py`."
            if generated_sources
            else "For this run, no real source portraits were available, so it used a proxy: each stored transparent "
            "sprite was composited onto a white background, then processed by a naive white-threshold baseline and "
            "the project's flood-fill alpha step. The original stored alpha is used as pseudo-ground truth. These "
            "numbers are reproducible but should be reported as proxy metrics, not as a direct evaluation on raw "
            "generator outputs."
        )
    )
    summary_lines = [
        "# White-Background Post-Processing Evaluation",
        "",
        "## Method",
        "",
        "The project pipeline is implemented in `scripts/workbench/image_processing.py`: it flood-fills near-white "
        "pixels connected to the image border, blurs the background mask, inverts it to alpha, crops to the alpha "
        "bounds, and adds a desktop-pet standee outline.",
        "",
        source_method_text,
        "",
        "## Outputs",
        "",
        f"- Metrics CSV: `{relative_path(metrics_csv)}`",
        f"- LLM-as-a-judge scoring template: `{relative_path(manual_csv)}`",
        f"- Method comparison figure: `{relative_path(figure_path)}`",
        f"- Composite background figure: `{relative_path(FIGURES_DIR / 'background_composites.png')}`",
        f"- Real input instructions: `{relative_path(INPUT_DIR / 'README.md')}`",
        "",
        f"## {metrics_heading}",
        "",
    ]
    for method, values in method_summary.items():
        summary_lines.append(f"### {method}")
        if values:
            for key, value in values.items():
                summary_lines.append(f"- {key}: {value}")
        else:
            summary_lines.append("- No numeric proxy metrics available.")
        summary_lines.append("")
    summary_lines.extend(
        [
            "## Limitations",
            "",
            "The automatic metrics are alpha-mask proxies. They help compare methods consistently, but near-white "
            "clothing, facial highlights, and fine hair boundaries should still be checked with LLM-as-a-judge review "
            "in the generated figures and scoring CSV.",
            "",
        ]
    )
    write_text(summary_md, "\n".join(summary_lines))

    print(f"Wrote {relative_path(metrics_csv)}")
    print(f"Wrote {relative_path(summary_json)}")
    print(f"Wrote {relative_path(summary_md)}")
    print(f"Wrote {relative_path(figure_path)}")
    print(f"Wrote {relative_path(FIGURES_DIR / 'background_composites.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
