#!/usr/bin/env python3
"""Sync commands/*.md from public skills/**/SKILL.md."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
COMMANDS_DIR = ROOT / "commands"
TEMPLATE = """---
description: {description}
location: plugin
---

Use the `{name}` skill to help with this task.
"""

def parse_frontmatter(p):
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return p.parent.name, ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return p.parent.name, ""
    name, desc = p.parent.name, ""
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k == "name":
            name = v or name
        elif k == "description":
            desc = v
    return name, desc

def main():
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    updated = 0
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = skill_md.parent.relative_to(SKILLS_DIR).parts
        if any(p.startswith("_") for p in rel):
            continue
        name, desc = parse_frontmatter(skill_md)
        if not desc:
            continue
        desired = TEMPLATE.format(name=name, description=desc)
        cmd_file = COMMANDS_DIR / f"{name}.md"
        if cmd_file.exists() and cmd_file.read_text(encoding="utf-8") == desired:
            continue
        cmd_file.write_text(desired, encoding="utf-8")
        updated += 1
    print(f"updated commands: {updated} files" if updated else "commands up to date")

if __name__ == "__main__":
    raise SystemExit(main() or 0)
