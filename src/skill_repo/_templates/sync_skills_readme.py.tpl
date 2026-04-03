#!/usr/bin/env python3
"""Sync skills catalog in skills/README.md."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
README = SKILLS_DIR / "README.md"
START = "<!-- BEGIN AUTO SKILLS -->"
END = "<!-- END AUTO SKILLS -->"

def parse_fm(p):
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return p.parent.name, ""
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return p.parent.name, ""
    meta = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta.get("name", p.parent.name), meta.get("description", "")

def main():
    entries = []
    for sm in sorted(SKILLS_DIR.rglob("SKILL.md")):
        rel = sm.parent.relative_to(SKILLS_DIR).parts
        if any(p.startswith("_") for p in rel):
            continue
        name, desc = parse_fm(sm)
        rp = sm.parent.relative_to(ROOT).as_posix()
        entries.append((name, desc, rp))
    lines = [START, "| Skill | Description | Path |", "| --- | --- | --- |"]
    for n, d, p in entries:
        lines.append(f"| `{n}` | {d} | [`{p}`](../{p}/SKILL.md) |")
    lines.append(END)
    gen = "\n".join(lines)
    if not README.exists():
        README.write_text(gen + "\n", encoding="utf-8")
        return
    content = README.read_text(encoding="utf-8")
    if START in content and END in content:
        s, e = content.index(START), content.index(END) + len(END)
        updated = content[:s] + gen + content[e:]
    else:
        updated = content.rstrip() + "\n\n" + gen + "\n"
    if updated != content:
        README.write_text(updated, encoding="utf-8")
        print("updated skills README")
    else:
        print("skills README up to date")

if __name__ == "__main__":
    raise SystemExit(main() or 0)
