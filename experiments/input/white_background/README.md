# White-Background Source Images

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
