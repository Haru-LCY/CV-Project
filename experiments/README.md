# Experiment Pipeline

This folder contains reproducible experiment scripts for the desktop pet project.
The scripts do not modify the application runtime. Generated results are written
to `results/experiments/`.

Run all available experiments:

```powershell
uv run --no-sync python experiments/run_all.py
```

Shared settings are documented in `experiments/config.json`.

Generate the 20-set API dataset requested for the experiments:

```powershell
uv run --no-sync python experiments/generate_image_sets.py --count 20
```

This creates raw white-background source images and processed transparent sprites
under `results/experiments/generated_image_sets/`. The generator resumes from
complete manifests, so rerunning the command skips completed sets unless
`--force` is passed.

Run individual experiments:

```powershell
uv run --no-sync python experiments/expression_consistency.py
uv run --no-sync python experiments/background_postprocessing.py
uv run --no-sync python experiments/runtime_manual_placeholder.py
```

## Experiment 1: Expression Consistency

Input is inferred from `config.json` and `character_cards/*.json`, using each
profile's `emotion_images` field only when no generated experiment dataset is
present. After running `experiments/generate_image_sets.py`, the 20 generated
sets are used instead. Since no `neutral` or `idle` image is stored, the script
uses `happy` as the reference expression.

The automatic metric is intentionally lightweight: alpha-cropped centered RGB
cosine similarity plus average-hash similarity. This is enough for the current
highly consistent generated sprites, but the generated CSV should be used for
LLM-as-a-judge identity, expression, and artifact scores.

Outputs:

- `results/experiments/expression_consistency_summary.csv`
- `results/experiments/expression_consistency_summary.json`
- `results/experiments/expression_consistency_summary.md`
- `results/experiments/figures/expression_consistency_grid.png`
- `results/experiments/manual_templates/expression_manual_scores.csv`

## Experiment 2: White-Background Post-Processing

The project post-processing pipeline is in
`scripts/workbench/image_processing.py`. It detects near-white background from
the image border, builds an alpha mask, crops to foreground, and adds a standee
outline.

The API generator stores raw white-background portraits under
`results/experiments/generated_image_sets/`. If you have additional source
images, place them under:

```text
experiments/input/white_background/
```

When that folder is empty, the script runs a documented proxy experiment by
compositing the stored transparent sprites onto white and checking whether the
naive threshold baseline and the project flood-fill alpha step recover the
stored alpha mask.

Outputs:

- `results/experiments/background_postprocessing_metrics.csv`
- `results/experiments/background_postprocessing_summary.json`
- `results/experiments/background_postprocessing_summary.md`
- `results/experiments/figures/background_postprocessing_examples.png`
- `results/experiments/figures/background_composites.png`
- `results/experiments/manual_templates/background_manual_scores.csv`

## Experiment 3: Runtime and Interaction

Per request, this experiment is a manual-entry placeholder for resource-utility
checks only. CPU, GPU, memory, and interaction observations must be measured
manually; no app launch, profiling, or interaction simulation is performed by
the script.

Outputs:

- `results/experiments/manual_templates/runtime_interaction_manual_entry.csv`
- `results/experiments/runtime_interaction_manual_placeholder.md`
