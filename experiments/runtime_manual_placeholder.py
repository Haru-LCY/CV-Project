from __future__ import annotations

import csv
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent))

from common import MANUAL_TEMPLATES_DIR, RESULTS_DIR, ensure_output_dirs, relative_path, write_text  # noqa: E402


SCENARIOS = [
    "application_startup",
    "idle_animation",
    "left_click_head_touch",
    "text_input_or_chat",
    "middle_button_drag",
    "continuous_short_run",
]

FIELDS = [
    "scenario",
    "date",
    "hardware_os",
    "app_version_or_commit",
    "duration_seconds",
    "startup_time_seconds",
    "average_cpu_percent",
    "peak_cpu_percent",
    "average_memory_mb",
    "peak_memory_mb",
    "approx_fps_or_update_rate",
    "interaction_latency_ms",
    "stability_notes",
    "visible_lag_notes",
    "accepted_for_daily_use",
]


def main() -> int:
    ensure_output_dirs()
    csv_path = MANUAL_TEMPLATES_DIR / "runtime_interaction_manual_entry.csv"
    md_path = RESULTS_DIR / "runtime_interaction_manual_placeholder.md"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for scenario in SCENARIOS:
            row = {field: "" for field in FIELDS}
            row["scenario"] = scenario
            writer.writerow(row)

    write_text(
        md_path,
        f"""# Runtime and Interaction Evaluation Placeholder

Automatic runtime profiling was intentionally not run for this experiment. Fill in
the resource-utility CSV manually after using the desktop pet application:

`{relative_path(csv_path)}`

Suggested procedure:

1. Start the app with `uv run --no-sync python -m scripts.pet_app`.
2. Record startup time until the pet is visible.
3. Observe idle animation and normal interaction for the scenarios listed in the CSV.
4. Enter CPU, memory, approximate update rate, latency, and stability notes from your preferred system monitor.

No runtime numbers are reported here until the resource-utility checks are manually measured.
""",
    )

    print(f"Wrote {relative_path(csv_path)}")
    print(f"Wrote {relative_path(md_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
