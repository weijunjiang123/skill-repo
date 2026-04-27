#!/usr/bin/env python3
"""Build a standalone skill-repo executable with Nuitka."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
NUITKA_BUILD_DIR = DIST_DIR / "nuitka"
ENTRYPOINT = REPO_ROOT / "scripts" / "nuitka_entry.py"
TEMPLATE_DIR = REPO_ROOT / "src" / "skill_repo" / "_templates"


def _platform_slug() -> tuple[str, str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()

    os_map = {
        "darwin": "macos",
        "linux": "linux",
        "windows": "windows",
    }
    arch_map = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }

    if system not in os_map:
        raise SystemExit(f"Unsupported OS for release build: {platform.system()}")
    if machine not in arch_map:
        raise SystemExit(f"Unsupported CPU architecture for release build: {platform.machine()}")

    os_name = os_map[system]
    arch_name = arch_map[machine]
    extension = ".exe" if os_name == "windows" else ""
    return os_name, arch_name, extension


def _default_asset_name() -> str:
    os_name, arch_name, extension = _platform_slug()
    return f"skill-repo-{os_name}-{arch_name}{extension}"


def build(asset_name: str, clean: bool) -> Path:
    if clean and NUITKA_BUILD_DIR.exists():
        shutil.rmtree(NUITKA_BUILD_DIR)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    NUITKA_BUILD_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--assume-yes-for-downloads",
        "--include-package=skill_repo",
        f"--include-data-dir={TEMPLATE_DIR}=skill_repo/_templates",
        f"--output-dir={NUITKA_BUILD_DIR}",
        f"--output-filename={asset_name}",
        str(ENTRYPOINT),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)

    built_asset = NUITKA_BUILD_DIR / asset_name
    if not built_asset.exists():
        matches = sorted(NUITKA_BUILD_DIR.glob(f"{asset_name}*"))
        if not matches:
            raise SystemExit(f"Nuitka finished, but no asset was found for {asset_name}")
        built_asset = matches[0]

    final_asset = DIST_DIR / asset_name
    if final_asset.exists():
        final_asset.unlink()
    shutil.copy2(built_asset, final_asset)
    final_asset.chmod(final_asset.stat().st_mode | 0o755)
    return final_asset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a standalone skill-repo executable with Nuitka.")
    parser.add_argument("--asset-name", default=_default_asset_name(), help="Output binary name.")
    parser.add_argument("--no-clean", action="store_true", help="Reuse the existing Nuitka build directory.")
    args = parser.parse_args()

    asset = build(asset_name=args.asset_name, clean=not args.no_clean)
    print(f"Built {asset}")


if __name__ == "__main__":
    main()
