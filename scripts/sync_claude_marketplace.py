#!/usr/bin/env python3
"""Sync `.claude-plugin/manifest.json` from public `skills/**/SKILL.md`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_FILE = ROOT / ".claude-plugin" / "manifest.json"
SKILLS_DIR = ROOT / "skills"


def is_public_skill(skill_file: Path) -> bool:
    rel_parts = skill_file.parent.relative_to(SKILLS_DIR).parts
    return not any(part.startswith("_") for part in rel_parts)


def discover_skills() -> list[dict[str, str | bool]]:
    skill_entries: list[dict[str, str | bool]] = []
    if not SKILLS_DIR.exists():
        return skill_entries

    # Support both:
    # - skills/<skill-name>/SKILL.md
    # - skills/<category>/<skill-name>/SKILL.md
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        if not is_public_skill(skill_file):
            continue
        skill_dir = skill_file.parent
        relative_dir = skill_dir.relative_to(ROOT).as_posix()
        rel_parts = skill_dir.relative_to(SKILLS_DIR).parts
        category = rel_parts[0] if len(rel_parts) > 1 else ""
        skill_name = parse_frontmatter_name(skill_file) or skill_dir.name
        entry: dict[str, str | bool] = {
            "name": skill_name,
            "path": relative_dir,
            "command": f"commands/{skill_name}.md",
            "tested": False,
        }
        if category:
            entry["category"] = category
        skill_entries.append(entry)
    return skill_entries


def parse_frontmatter_name(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""

    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return ""

    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "name":
            return value.strip().strip('"').strip("'")
    return ""


def load_manifest() -> dict:
    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(f"Missing file: {MANIFEST_FILE}")
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def write_manifest(data: dict) -> None:
    MANIFEST_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync marketplace skills list.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check drift; do not write file.",
    )
    args = parser.parse_args()

    data = load_manifest()
    desired = discover_skills()
    current = data.get("skills") or []

    if current == desired:
        print("manifest skills are up to date")
        return 0

    if args.check:
        print("marketplace skills out of date", file=sys.stderr)
        print(f"current: {current}", file=sys.stderr)
        print(f"desired: {desired}", file=sys.stderr)
        return 1

    data["skills"] = desired
    write_manifest(data)
    print(f"updated manifest skills: {len(desired)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
