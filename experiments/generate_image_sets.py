from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, TypeVar

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    GENERATED_IMAGE_SETS_DIR,
    RESULTS_DIR,
    decode_base64_image,
    ensure_output_dirs,
    load_experiment_config,
    relative_path,
)
from scripts.workbench.constants import EMOTION_SPECS, REFERENCE_EMOTIONS  # noqa: E402
from scripts.workbench.generator import LocalCharacterGenerator  # noqa: E402
from scripts.workbench.image_processing import make_desktop_pet_standee  # noqa: E402


T = TypeVar("T")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


CHARACTER_SPECS = [
    {
        "name": "春奈",
        "appearance_traits": ["黑发", "蓝瞳", "长直发", "校服", "清纯"],
        "personality_traits": ["温柔治愈系", "认真优等生系"],
        "identity_traits": ["同桌伙伴"],
        "style": "anime_desktop_pet",
        "persona": "黑色长发、蓝色眼睛的清爽少女，穿深色校服，性格温和认真，常用安静的陪伴感回应用户。",
    },
    {
        "name": "柚希",
        "appearance_traits": ["棕发", "绿瞳", "短发", "休闲私服", "活泼"],
        "personality_traits": ["元气少女系", "天然系"],
        "identity_traits": ["日常伙伴"],
        "style": "anime_desktop_pet",
        "persona": "棕色短发、绿色眼睛的活泼少女，穿轻便私服，语气明亮自然，像随时准备一起完成小任务。",
    },
    {
        "name": "白音",
        "appearance_traits": ["银白发", "紫瞳", "中长发", "连衣裙", "优雅"],
        "personality_traits": ["三无冷淡系", "温柔治愈系"],
        "identity_traits": ["安静陪伴者"],
        "style": "anime_desktop_pet",
        "persona": "银白中长发、紫色眼睛的安静少女，穿浅色连衣裙，表达克制但温柔，适合桌面陪伴。",
    },
    {
        "name": "桃花",
        "appearance_traits": ["粉发", "棕瞳", "双马尾", "针织衫", "可爱"],
        "personality_traits": ["呆萌系", "害羞内向系"],
        "identity_traits": ["学习提醒伙伴"],
        "style": "anime_desktop_pet",
        "persona": "粉色双马尾、棕色眼睛的害羞少女，穿柔软针织衫，反应可爱，常轻声提醒用户休息和学习。",
    },
    {
        "name": "凛香",
        "appearance_traits": ["黑发", "黑瞳", "单马尾", "衬衫短裙", "冷淡"],
        "personality_traits": ["三无冷淡系", "毒舌系"],
        "identity_traits": ["桌面助手"],
        "style": "anime_desktop_pet",
        "persona": "黑色单马尾、黑色眼睛的冷静少女，穿衬衫短裙，吐槽简短但不过分，行动利落。",
    },
    {
        "name": "铃",
        "appearance_traits": ["金发", "蓝瞳", "波浪卷", "校服", "可爱"],
        "personality_traits": ["傲娇系", "认真优等生系"],
        "identity_traits": ["校园伙伴"],
        "style": "anime_desktop_pet",
        "persona": "金色波浪卷、蓝色眼睛的傲娇少女，穿整洁校服，嘴上强硬但实际很关心用户。",
    },
    {
        "name": "七海",
        "appearance_traits": ["棕发", "棕瞳", "侧马尾", "运动服", "活泼"],
        "personality_traits": ["元气少女系", "认真优等生系"],
        "identity_traits": ["运动提醒伙伴"],
        "style": "anime_desktop_pet",
        "persona": "棕色侧马尾、棕色眼睛的元气少女，穿运动服，鼓励用户活动身体并保持节奏。",
    },
    {
        "name": "澪",
        "appearance_traits": ["银白发", "蓝瞳", "长直发", "衬衫短裙", "清纯"],
        "personality_traits": ["害羞内向系", "温柔治愈系"],
        "identity_traits": ["安静同伴"],
        "style": "anime_desktop_pet",
        "persona": "银白长直发、蓝色眼睛的内向少女，穿简洁衬衫短裙，表达细腻，给人安静可靠的感觉。",
    },
    {
        "name": "小葵",
        "appearance_traits": ["黑发", "绿瞳", "短发", "运动服", "清纯"],
        "personality_traits": ["天然系", "元气少女系"],
        "identity_traits": ["桌面陪跑者"],
        "style": "anime_desktop_pet",
        "persona": "黑色短发、绿色眼睛的自然系少女，穿清爽运动服，反应直接，擅长把气氛变轻松。",
    },
    {
        "name": "璃月",
        "appearance_traits": ["金发", "紫瞳", "中长发", "连衣裙", "优雅"],
        "personality_traits": ["温柔治愈系", "天然系"],
        "identity_traits": ["生活陪伴者"],
        "style": "anime_desktop_pet",
        "persona": "金色中长发、紫色眼睛的优雅少女，穿柔和连衣裙，说话慢而温和，关注用户日常状态。",
    },
    {
        "name": "千夏",
        "appearance_traits": ["粉发", "蓝瞳", "短发", "休闲私服", "活泼"],
        "personality_traits": ["元气少女系", "呆萌系"],
        "identity_traits": ["日程提醒伙伴"],
        "style": "anime_desktop_pet",
        "persona": "粉色短发、蓝色眼睛的开朗少女，穿休闲私服，表情丰富，适合做轻快的桌面提醒。",
    },
    {
        "name": "真白",
        "appearance_traits": ["银白发", "绿瞳", "双马尾", "校服", "可爱"],
        "personality_traits": ["害羞内向系", "呆萌系"],
        "identity_traits": ["小声陪伴者"],
        "style": "anime_desktop_pet",
        "persona": "银白双马尾、绿色眼睛的害羞少女，穿校服，动作拘谨但表情真诚，陪伴感柔软。",
    },
    {
        "name": "雫",
        "appearance_traits": ["黑发", "紫瞳", "中长发", "针织衫", "冷淡"],
        "personality_traits": ["三无冷淡系", "认真优等生系"],
        "identity_traits": ["专注助手"],
        "style": "anime_desktop_pet",
        "persona": "黑色中长发、紫色眼睛的冷静少女，穿深色针织衫，少言但观察细致，适合专注场景。",
    },
    {
        "name": "美羽",
        "appearance_traits": ["棕发", "蓝瞳", "波浪卷", "连衣裙", "优雅"],
        "personality_traits": ["温柔治愈系", "天然系"],
        "identity_traits": ["温柔桌宠"],
        "style": "anime_desktop_pet",
        "persona": "棕色波浪卷、蓝色眼睛的温柔少女，穿浅色连衣裙，语气舒缓，适合长时间陪伴。",
    },
    {
        "name": "遥",
        "appearance_traits": ["金发", "黑瞳", "单马尾", "运动服", "活泼"],
        "personality_traits": ["元气少女系", "毒舌系"],
        "identity_traits": ["行动派伙伴"],
        "style": "anime_desktop_pet",
        "persona": "金色单马尾、黑色眼睛的行动派少女，穿运动服，说话直接，常推动用户开始任务。",
    },
    {
        "name": "花梨",
        "appearance_traits": ["粉发", "绿瞳", "长直发", "衬衫短裙", "清纯"],
        "personality_traits": ["害羞内向系", "认真优等生系"],
        "identity_traits": ["学习同伴"],
        "style": "anime_desktop_pet",
        "persona": "粉色长直发、绿色眼睛的认真少女，穿衬衫短裙，害羞但可靠，重视约定和学习计划。",
    },
    {
        "name": "若叶",
        "appearance_traits": ["棕发", "紫瞳", "双马尾", "休闲私服", "可爱"],
        "personality_traits": ["傲娇系", "呆萌系"],
        "identity_traits": ["桌面玩伴"],
        "style": "anime_desktop_pet",
        "persona": "棕色双马尾、紫色眼睛的可爱少女，穿休闲私服，反应有点嘴硬，但很容易露出真实情绪。",
    },
    {
        "name": "沙耶",
        "appearance_traits": ["黑发", "棕瞳", "侧马尾", "针织衫", "优雅"],
        "personality_traits": ["温柔治愈系", "认真优等生系"],
        "identity_traits": ["整理助手"],
        "style": "anime_desktop_pet",
        "persona": "黑色侧马尾、棕色眼睛的优雅少女，穿针织衫，做事有条理，擅长提醒用户整理桌面。",
    },
    {
        "name": "蓝",
        "appearance_traits": ["银白发", "黑瞳", "短发", "校服", "冷淡"],
        "personality_traits": ["三无冷淡系", "天然系"],
        "identity_traits": ["低调陪伴者"],
        "style": "anime_desktop_pet",
        "persona": "银白短发、黑色眼睛的低调少女，穿校服，表情变化细微，但偶尔会说出天然的话。",
    },
    {
        "name": "莉央",
        "appearance_traits": ["金发", "绿瞳", "长直发", "休闲私服", "清纯"],
        "personality_traits": ["傲娇系", "温柔治愈系"],
        "identity_traits": ["日常桌宠"],
        "style": "anime_desktop_pet",
        "persona": "金色长直发、绿色眼睛的清纯少女，穿明亮私服，外表自信，实际很会照顾用户情绪。",
    },
]


def call_with_retries(label: str, fn: Callable[[], T], attempts: int = 3, delay_seconds: int = 10) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[retry] {label} failed on attempt {attempt}/{attempts}: {type(exc).__name__}: {exc}", flush=True)
            if attempt < attempts:
                time.sleep(delay_seconds * attempt)
    assert last_error is not None
    raise last_error


def save_base64_image(value: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    decode_base64_image(value).save(path)


def complete_manifest(path: Path, expected_emotions: list[str]) -> bool:
    if not path.exists():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    expressions = manifest.get("expressions")
    if not isinstance(expressions, dict):
        return False
    for emotion in expected_emotions:
        payload = expressions.get(emotion)
        if not isinstance(payload, dict):
            return False
        source_path = payload.get("source_path")
        sprite_path = payload.get("sprite_path")
        if not source_path or not sprite_path:
            return False
        if not (Path(source_path).is_absolute() or (Path.cwd() / source_path).exists()):
            return False
        if not (Path(sprite_path).is_absolute() or (Path.cwd() / sprite_path).exists()):
            return False
    return True


def generate_set(
    generator: LocalCharacterGenerator,
    set_index: int,
    spec: dict,
    emotions: list[str],
    max_reference_workers: int,
    force: bool,
) -> dict:
    set_id = f"set_{set_index:03d}"
    set_dir = GENERATED_IMAGE_SETS_DIR / set_id
    manifest_path = set_dir / "manifest.json"
    if not force and complete_manifest(manifest_path, emotions):
        print(f"[skip] {set_id} already complete", flush=True)
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    source_dir = set_dir / "sources"
    sprite_dir = set_dir / "sprites"
    source_dir.mkdir(parents=True, exist_ok=True)
    sprite_dir.mkdir(parents=True, exist_ok=True)

    profile_json = {
        "name": spec["name"],
        "persona": spec["persona"],
        "greeting": f"你好，我是{spec['name']}。今天也一起努力吧。",
    }
    print(f"[start] {set_id} {profile_json['name']}", flush=True)

    happy_prompt = generator._build_image_prompt(
        profile_json,
        spec["appearance_traits"],
        spec["personality_traits"],
        spec["identity_traits"],
        spec["style"],
        "happy",
        EMOTION_SPECS["happy"],
        None,
        None,
        None,
        None,
    )
    happy_source_base64 = call_with_retries(
        f"{set_id}/happy source",
        lambda: generator._generate_source_image(happy_prompt),
    )

    expressions: dict[str, dict[str, str]] = {}

    def save_expression(emotion: str, source_base64: str, prompt: str) -> None:
        source_path = source_dir / f"{emotion}.png"
        sprite_path = sprite_dir / f"{emotion}.png"
        save_base64_image(source_base64, source_path)
        sprite_base64 = make_desktop_pet_standee(source_base64)
        save_base64_image(sprite_base64, sprite_path)
        expressions[emotion] = {
            "source_path": relative_path(source_path),
            "sprite_path": relative_path(sprite_path),
            "prompt": prompt,
        }

    save_expression("happy", happy_source_base64, happy_prompt)

    def generate_reference_emotion(emotion: str) -> tuple[str, str, str]:
        prompt = generator._build_reference_emotion_prompt(emotion, EMOTION_SPECS[emotion])
        source_base64 = call_with_retries(
            f"{set_id}/{emotion} source",
            lambda: generator._generate_source_image(prompt, happy_source_base64),
        )
        return emotion, source_base64, prompt

    reference_emotions = [emotion for emotion in emotions if emotion in REFERENCE_EMOTIONS and emotion != "happy"]
    if reference_emotions:
        with ThreadPoolExecutor(max_workers=max(1, min(max_reference_workers, len(reference_emotions)))) as executor:
            futures = [executor.submit(generate_reference_emotion, emotion) for emotion in reference_emotions]
            for future in as_completed(futures):
                emotion, source_base64, prompt = future.result()
                save_expression(emotion, source_base64, prompt)

    manifest = {
        "set_id": set_id,
        "character_id": f"experiment-{set_id}",
        "character_name": profile_json["name"],
        "profile": profile_json,
        "spec": spec,
        "expressions": {emotion: expressions[emotion] for emotion in emotions if emotion in expressions},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    error_path = set_dir / "error.json"
    if error_path.exists():
        error_path.unlink()
    print(f"[done] {set_id} {profile_json['name']} expressions={','.join(manifest['expressions'])}", flush=True)
    return manifest


def write_dataset_summary(manifests: list[dict]) -> None:
    csv_path = RESULTS_DIR / "generated_image_sets_summary.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["set_id", "character_id", "character_name", "expression", "source_path", "sprite_path"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for manifest in manifests:
            for expression, payload in manifest.get("expressions", {}).items():
                writer.writerow(
                    {
                        "set_id": manifest.get("set_id", ""),
                        "character_id": manifest.get("character_id", ""),
                        "character_name": manifest.get("character_name", ""),
                        "expression": expression,
                        "source_path": payload.get("source_path", ""),
                        "sprite_path": payload.get("sprite_path", ""),
                    }
                )
    print(f"[summary] wrote {relative_path(csv_path)}", flush=True)


def parse_args() -> argparse.Namespace:
    config = load_experiment_config().get("generation", {})
    parser = argparse.ArgumentParser(description="Generate experiment-only desktop pet image sets.")
    parser.add_argument("--count", type=int, default=int(config.get("count", 20)))
    parser.add_argument("--force", action="store_true", help="Regenerate sets even if complete manifests already exist.")
    parser.add_argument("--timeout", type=int, default=int(config.get("timeout_seconds", 180)))
    parser.add_argument(
        "--max-reference-workers",
        type=int,
        default=int(config.get("max_reference_workers", 3)),
        help="Concurrent reference emotion image requests per set.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_output_dirs()
    count = max(1, min(args.count, len(CHARACTER_SPECS)))
    emotions = ["happy", "sad", "angry", "shy"]
    generator = LocalCharacterGenerator(timeout=args.timeout)
    manifests: list[dict] = []
    failures: list[dict[str, str]] = []

    for index, spec in enumerate(CHARACTER_SPECS[:count], start=1):
        try:
            manifests.append(
                generate_set(
                    generator=generator,
                    set_index=index,
                    spec=spec,
                    emotions=emotions,
                    max_reference_workers=args.max_reference_workers,
                    force=args.force,
                )
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            failures.append(
                {
                    "set_id": f"set_{index:03d}",
                    "character_name": str(spec.get("name", "")),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            error_path = GENERATED_IMAGE_SETS_DIR / f"set_{index:03d}" / "error.json"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(json.dumps(failures[-1], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_dataset_summary(manifests)
    summary_path = RESULTS_DIR / "generated_image_sets_generation_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "requested_count": count,
                "completed_count": len(manifests),
                "failed_count": len(failures),
                "emotions": emotions,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[summary] wrote {relative_path(summary_path)}", flush=True)
    if failures:
        print(f"[error] completed {len(manifests)}/{count}; see {relative_path(summary_path)}", flush=True)
        return 1
    print(f"[ok] completed {len(manifests)}/{count} image sets", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
