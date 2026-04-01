#!/usr/bin/env python3
"""Sync `commands/*.md` from public `skills/**/SKILL.md`."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
COMMANDS_DIR = ROOT / "commands"

COMMAND_TEMPLATE = """\
---
description: {description}
location: plugin
---

Use the `{name}` skill to help with this task.
"""


def is_public_skill(skill_file: Path) -> bool:
    rel_parts = skill_file.parent.relative_to(SKILLS_DIR).parts
    return not any(part.startswith("_") for part in rel_parts)


def parse_frontmatter(skill_md: Path) -> tuple[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return skill_md.parent.name, ""
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return skill_md.parent.name, ""
    name = skill_md.parent.name
    desc = ""
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "name":
            name = value or name
        elif key == "description":
            desc = value
    return name, desc


def main() -> int:
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    updated = 0

    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        if not is_public_skill(skill_md):
            continue
        name, description = parse_frontmatter(skill_md)
        if not description:
            print(f"  skip {name}: no description in frontmatter", file=sys.stderr)
            continue

        cmd_file = COMMANDS_DIR / f"{name}.md"
        desired = COMMAND_TEMPLATE.format(name=name, description=description)

        if cmd_file.exists() and cmd_file.read_text(encoding="utf-8") == desired:
            continue

        cmd_file.write_text(desired, encoding="utf-8")
        updated += 1

    if updated:
        print(f"updated commands: {updated} files")
    else:
        print("commands are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
