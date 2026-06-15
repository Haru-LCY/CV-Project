from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path


APP_NAME = "MurasamePet"
ENTRYPOINT = Path("scripts") / "pet_app.py"
DATA_PATHS = (
    (Path("config.json"), "."),
    (Path("icon.png"), "."),
    (Path("思源黑体Bold.otf"), "."),
    (Path("fgimages"), "fgimages"),
    (Path("ui"), "ui"),
    (Path("character_cards"), "character_cards"),
)
HIDDEN_IMPORTS = (
    "cv2",
    "PIL.ImageGrab",
    "PyQt5.QtWebChannel",
    "PyQt5.QtWebEngineWidgets",
)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent.parent
    pyinstaller_args = build_pyinstaller_args(project_root, args)

    print("PyInstaller command:")
    print(format_command([sys.executable, "-m", "PyInstaller", *pyinstaller_args]))

    if args.dry_run:
        return 0

    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PyInstaller is not installed in this environment.\n"
            "Install the project build extra first:\n"
            "  uv sync --extra build\n"
            "Then run:\n"
            "  python -m scripts.build_executable"
        ) from exc

    pyinstaller_run(pyinstaller_args)
    print_build_result(project_root, args.name, args.dist_dir, args.onefile)
    return 0


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the MurasamePet desktop executable with PyInstaller.")
    parser.add_argument("--name", default=APP_NAME, help=f"Application/executable name. Default: {APP_NAME}")
    parser.add_argument("--onefile", action="store_true", help="Build a single-file executable when supported.")
    parser.add_argument("--console", action="store_true", help="Keep a console window for debug logs.")
    parser.add_argument("--dry-run", action="store_true", help="Print the PyInstaller command without running it.")
    parser.add_argument("--dist-dir", default="dist", help="Output directory. Default: dist")
    parser.add_argument("--work-dir", default="build/pyinstaller", help="PyInstaller work directory.")
    parser.add_argument("--spec-dir", default="build/pyinstaller-spec", help="Directory for the generated spec file.")
    return parser.parse_args(argv)


def build_pyinstaller_args(project_root: Path, args: argparse.Namespace) -> list[str]:
    if not (project_root / ENTRYPOINT).exists():
        raise SystemExit(f"Missing entrypoint: {project_root / ENTRYPOINT}")

    command = [
        str(project_root / ENTRYPOINT),
        "--name",
        args.name,
        "--noconfirm",
        "--clean",
        "--distpath",
        str(project_root / args.dist_dir),
        "--workpath",
        str(project_root / args.work_dir),
        "--specpath",
        str(project_root / args.spec_dir),
    ]

    command.append("--console" if args.console else "--windowed")
    if args.onefile:
        command.append("--onefile")
    else:
        command.append("--onedir")

    for source, destination in DATA_PATHS:
        path = project_root / source
        if path.exists():
            command.extend(["--add-data", add_data_arg(path, destination)])

    for hidden_import in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", hidden_import])

    if platform.system() == "Darwin":
        command.extend(["--hidden-import", "AppKit", "--hidden-import", "objc"])
        command.extend(["--osx-bundle-identifier", "com.murasame.pet"])

    return command


def add_data_arg(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def format_command(parts: list[str]) -> str:
    return " ".join(shlex_quote(part) for part in parts)


def shlex_quote(value: str) -> str:
    if not value:
        return '""'
    if all(char not in value for char in ' \t\n"\';&|()<>'):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def print_build_result(project_root: Path, name: str, dist_dir_name: str, onefile: bool) -> None:
    dist_dir = project_root / dist_dir_name
    system = platform.system()
    if system == "Darwin":
        candidate = dist_dir / f"{name}.app"
    elif system == "Windows" and onefile:
        candidate = dist_dir / f"{name}.exe"
    elif system == "Windows":
        candidate = dist_dir / name / f"{name}.exe"
    else:
        candidate = dist_dir / name / name

    if candidate.exists():
        print(f"Build output: {candidate}")
        return

    resolved = shutil.which(name)
    if resolved:
        print(f"Build output found on PATH: {resolved}")
    else:
        print(f"Build finished. Check output directory: {dist_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
