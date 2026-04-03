#!/usr/bin/env python3
"""Sync .claude-plugin/manifest.json from skills."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "manifest.json"
SKILLS_DIR = ROOT / "skills"

def parse_name(p):
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return ""
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip() == "name":
            return v.strip().strip('"').strip("'")
    return ""

def main():
    entries = []
    for sf in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = sf.parent.relative_to(SKILLS_DIR).parts
        if any(p.startswith("_") for p in rel):
            continue
        name = parse_name(sf) or sf.parent.name
        rp = sf.parent.relative_to(ROOT).as_posix()
        cat = rel[0] if len(rel) > 1 else ""
        e = {"name": name, "path": rp, "command": f"commands/{name}.md", "tested": False}
        if cat:
            e["category"] = cat
        entries.append(e)
    data = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    if data.get("skills") == entries:
        print("manifest up to date")
        return
    data["skills"] = entries
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated manifest: {len(entries)} entries")

if __name__ == "__main__":
    raise SystemExit(main() or 0)
