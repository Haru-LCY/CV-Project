from __future__ import annotations

import csv
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results" / "experiments"
MANUAL_DIR = RESULTS_DIR / "manual_templates"
OUTPUT_PATH = RESULTS_DIR / "report_experiment_averages.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number):
        return None
    return number


def stats(values: list[float]) -> dict[str, float | int | None]:
    cleaned = [value for value in values if value is not None and not math.isnan(value)]
    if not cleaned:
        return {"count": 0, "mean": None, "min": None, "max": None, "std": None}
    return {
        "count": len(cleaned),
        "mean": round(statistics.mean(cleaned), 6),
        "min": round(min(cleaned), 6),
        "max": round(max(cleaned), 6),
        "std": round(statistics.pstdev(cleaned), 6) if len(cleaned) > 1 else 0.0,
    }


def acceptance_rate(rows: list[dict[str, str]]) -> float | None:
    if not rows:
        return None
    accepted = sum(1 for row in rows if str(row.get("accepted", "")).strip().lower() in {"yes", "true", "1"})
    return round(accepted / len(rows), 6)


def set_id_from_path(path: str) -> str:
    match = re.search(r"(set_\d+)", path.replace("\\", "/"))
    return match.group(1) if match else "unknown"


def group_rows(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key, "")), []).append(row)
    return dict(sorted(grouped.items()))


def numeric_field_summary(rows: list[dict[str, str]], fields: list[str]) -> dict[str, dict[str, float | int | None]]:
    result: dict[str, dict[str, float | int | None]] = {}
    for field in fields:
        result[field] = stats([value for value in (parse_float(row.get(field)) for row in rows) if value is not None])
    return result


def expression_automatic_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    non_reference = [row for row in rows if row.get("expression") != row.get("reference_expression")]
    by_set = {}
    for set_id, set_rows in group_rows(non_reference, "character_group").items():
        by_set[set_id] = {
            "num_compared_expressions": len(set_rows),
            "centered_rgb_cosine": stats([parse_float(row.get("centered_rgb_cosine")) for row in set_rows if parse_float(row.get("centered_rgb_cosine")) is not None]),
            "average_hash_similarity": stats([parse_float(row.get("average_hash_similarity")) for row in set_rows if parse_float(row.get("average_hash_similarity")) is not None]),
        }
    by_expression = {}
    for expression, expr_rows in group_rows(non_reference, "expression").items():
        by_expression[expression] = {
            "centered_rgb_cosine": stats([parse_float(row.get("centered_rgb_cosine")) for row in expr_rows if parse_float(row.get("centered_rgb_cosine")) is not None]),
            "average_hash_similarity": stats([parse_float(row.get("average_hash_similarity")) for row in expr_rows if parse_float(row.get("average_hash_similarity")) is not None]),
        }
    return {
        "num_rows": len(rows),
        "num_sets": len({row.get("character_group") for row in rows}),
        "num_non_reference_rows": len(non_reference),
        "reference_expressions": sorted({row.get("reference_expression", "") for row in rows}),
        "overall": {
            "centered_rgb_cosine": stats([parse_float(row.get("centered_rgb_cosine")) for row in non_reference if parse_float(row.get("centered_rgb_cosine")) is not None]),
            "average_hash_similarity": stats([parse_float(row.get("average_hash_similarity")) for row in non_reference if parse_float(row.get("average_hash_similarity")) is not None]),
        },
        "by_expression": by_expression,
        "by_set": by_set,
    }


def expression_manual_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    for row in rows:
        row["set_id"] = set_id_from_path(row.get("image_path", ""))
    fields = ["identity_score_1_5", "expression_score_1_5", "artifact_score_1_5"]
    by_set = {}
    for set_id, set_rows in group_rows(rows, "set_id").items():
        by_set[set_id] = {
            "num_images": len(set_rows),
            "acceptance_rate": acceptance_rate(set_rows),
            **numeric_field_summary(set_rows, fields),
        }
    by_expression = {}
    for expression, expr_rows in group_rows(rows, "expression").items():
        by_expression[expression] = {
            "num_images": len(expr_rows),
            "acceptance_rate": acceptance_rate(expr_rows),
            **numeric_field_summary(expr_rows, fields),
        }
    return {
        "num_rows": len(rows),
        "num_sets": len({row.get("set_id") for row in rows}),
        "acceptance_rate": acceptance_rate(rows),
        "overall": numeric_field_summary(rows, fields),
        "by_expression": by_expression,
        "by_set": by_set,
    }


def background_automatic_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    fields = [
        "foreground_alpha_sum",
        "opaque_white_pixel_ratio",
        "background_residue_ratio",
        "core_character_loss_ratio",
        "foreground_area_change_ratio",
        "boundary_alpha_mae",
        "suspicious_hole_components",
        "white_residue_near_boundary_ratio",
    ]
    by_method = {}
    for method, method_rows in group_rows(rows, "method").items():
        by_method[method] = {
            "num_rows": len(method_rows),
            "metrics": numeric_field_summary(method_rows, fields),
        }
    by_set_method = {}
    for row in rows:
        row["set_id"] = row.get("character_group") or set_id_from_path(row.get("source_path", ""))
    for set_id, set_rows in group_rows(rows, "set_id").items():
        by_set_method[set_id] = {}
        for method, method_rows in group_rows(set_rows, "method").items():
            by_set_method[set_id][method] = {
                "num_rows": len(method_rows),
                "metrics": numeric_field_summary(method_rows, fields),
            }
    return {
        "num_rows": len(rows),
        "num_sets": len({row.get("set_id") for row in rows}),
        "source_types": sorted({row.get("source_type", "") for row in rows}),
        "by_method": by_method,
        "by_set_method": by_set_method,
    }


def background_manual_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    for row in rows:
        row["set_id"] = set_id_from_path(row.get("source_path", ""))
    fields = [
        "white_residue_score_1_5",
        "edge_quality_score_1_5",
        "character_preservation_score_1_5",
        "compositing_quality_score_1_5",
    ]
    by_method = {}
    for method, method_rows in group_rows(rows, "method").items():
        by_method[method] = {
            "num_rows": len(method_rows),
            "acceptance_rate": acceptance_rate(method_rows),
            "scores": numeric_field_summary(method_rows, fields),
        }
    by_set_method = {}
    for set_id, set_rows in group_rows(rows, "set_id").items():
        by_set_method[set_id] = {}
        for method, method_rows in group_rows(set_rows, "method").items():
            by_set_method[set_id][method] = {
                "num_rows": len(method_rows),
                "acceptance_rate": acceptance_rate(method_rows),
                "scores": numeric_field_summary(method_rows, fields),
            }
    return {
        "num_rows": len(rows),
        "num_sets": len({row.get("set_id") for row in rows}),
        "by_method": by_method,
        "by_set_method": by_set_method,
    }


def runtime_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    fields = ["average_cpu_percent", "average_gpu_percent", "average_memory_mb"]
    return {
        "num_rows": len(rows),
        "overall": numeric_field_summary(rows, fields),
        "by_scenario": rows,
        "note": "Contains only the manually measured runtime resource-utility measurements.",
    }


def main() -> int:
    generation = read_json(RESULTS_DIR / "generated_image_sets_generation_summary.json")
    generated_rows = read_csv(RESULTS_DIR / "generated_image_sets_summary.csv")
    expression_auto = read_csv(RESULTS_DIR / "expression_consistency_summary.csv")
    expression_manual = read_csv(MANUAL_DIR / "expression_manual_scores.csv")
    background_auto = read_csv(RESULTS_DIR / "background_postprocessing_metrics.csv")
    background_manual = read_csv(MANUAL_DIR / "background_manual_scores.csv")
    runtime_rows = read_csv(MANUAL_DIR / "runtime_interaction_manual_entry.csv")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "generation_summary": "results/experiments/generated_image_sets_generation_summary.json",
            "generated_sets": "results/experiments/generated_image_sets_summary.csv",
            "expression_automatic": "results/experiments/expression_consistency_summary.csv",
            "expression_manual": "results/experiments/manual_templates/expression_manual_scores.csv",
            "background_automatic": "results/experiments/background_postprocessing_metrics.csv",
            "background_manual": "results/experiments/manual_templates/background_manual_scores.csv",
            "runtime_manual": "results/experiments/manual_templates/runtime_interaction_manual_entry.csv",
        },
        "dataset": {
            "requested_count": generation.get("requested_count"),
            "completed_count": generation.get("completed_count"),
            "failed_count": generation.get("failed_count"),
            "num_image_rows": len(generated_rows),
            "expressions": sorted({row.get("expression", "") for row in generated_rows}),
        },
        "expression_consistency": {
            "automatic": expression_automatic_summary(expression_auto),
            "manual_llm_judge": expression_manual_summary(expression_manual),
        },
        "white_background_postprocessing": {
            "automatic": background_automatic_summary(background_auto),
            "manual_llm_judge": background_manual_summary(background_manual),
        },
        "runtime_interaction": runtime_summary(runtime_rows),
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
