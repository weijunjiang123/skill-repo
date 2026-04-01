#!/usr/bin/env python3
"""
mcd Skills 上传脚本：从本地 Claude Code / Codex / Kiro 的 skills 目录中，
将指定技能上传（复制）到本仓库的 skills/ 目录。

用法:
    python scripts/upload.py --source claude --skill <name>                # 从 Claude Code 上传
    python scripts/upload.py --source codex  --skill <name>                # 从 Codex 上传
    python scripts/upload.py --source kiro   --skill <name>                # 从 Kiro 上传
    python scripts/upload.py --source kiro   --skill <name> --category tools  # 指定分类
    python scripts/upload.py --source claude --list                        # 列出本地可用技能
    python scripts/upload.py --source codex  --skill <name> --dry-run      # 仅预览

环境变量:
    CLAUDE_SKILLS_DIR  覆盖 Claude Code 目录（默认: ~/.claude）
    CODEX_SKILLS_DIR   覆盖 Codex 目录（默认: ~/.codex/skills）
    KIRO_SKILLS_DIR    覆盖 Kiro 目录（默认: ~/.kiro/skills）
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DEST = REPO_ROOT / "skills"

SOURCE_DIRS = {
    "claude": Path(os.environ.get("CLAUDE_SKILLS_DIR", Path.home() / ".claude" / "skills")),
    "codex": Path(os.environ.get("CODEX_SKILLS_DIR", Path.home() / ".codex" / "skills")),
    "kiro": Path(os.environ.get("KIRO_SKILLS_DIR", Path.home() / ".kiro" / "skills")),
}

SOURCE_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "kiro": "Kiro",
}


# ── skill discovery (from local platform dir) ────────────────────

def parse_frontmatter(skill_md: Path) -> tuple:
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


def discover_local_skills(source_dir: Path) -> list:
    """Scan a local platform skills directory for available skills."""
    entries = []
    if not source_dir.exists():
        return entries
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        name, desc = parse_frontmatter(skill_md)
        entries.append({
            "name": name,
            "description": desc,
            "source": child,
        })
    return entries


# ── list / upload ────────────────────────────────────────────────

def list_skills(entries: list, source_dir: Path) -> None:
    print(f"来源: {source_dir}")
    print(f"目标: {SKILLS_DEST}")
    print()
    print("可用技能：")
    print("-" * 50)
    if not entries:
        print("  （无）")
        return
    for e in entries:
        short = (e["description"][:60] + "...") if len(e["description"]) > 60 else e["description"]
        print(f"  - {e['name']}: {short or '(no description)'}")


def upload_skill(entry: dict, category: str, dry_run: bool = False) -> bool:
    name = entry["name"]
    src = entry["source"]
    dest = SKILLS_DEST / category / name

    if dry_run:
        print(f"  [DRY RUN] {name}: {src} -> {dest}")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  更新: {name} -> {dest}")
        shutil.rmtree(dest)
    else:
        print(f"  上传: {name} -> {dest}")

    shutil.copytree(src, dest)
    return True


# ── main ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="从本地 Claude Code / Codex / Kiro 上传技能到仓库",
    )
    parser.add_argument(
        "--source", choices=["claude", "codex", "kiro"], required=True,
        help="来源平台: claude / codex / kiro",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出本地可用技能")
    group.add_argument("--skill", type=str, help="要上传的技能名称")
    parser.add_argument(
        "--category", type=str, default="tools",
        help="目标分类目录（默认: tools）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际上传")
    args = parser.parse_args()

    label = SOURCE_LABELS[args.source]
    source_dir = SOURCE_DIRS[args.source]

    print()
    print("========================================")
    print(f"  mcd Skills - 从 {label} 上传")
    print("========================================")
    print()

    if not source_dir.exists():
        print(f"[ERROR] 未找到本地 skills 目录: {source_dir}")
        sys.exit(1)

    entries = discover_local_skills(source_dir)

    if args.list:
        list_skills(entries, source_dir)
        return

    # find the target skill
    matches = [e for e in entries if e["name"] == args.skill]
    if not matches:
        # also try matching by directory name
        for child in source_dir.iterdir():
            if child.is_dir() and child.name == args.skill and (child / "SKILL.md").exists():
                name, desc = parse_frontmatter(child / "SKILL.md")
                matches = [{"name": name, "description": desc, "source": child}]
                break

    if not matches:
        print(f"[ERROR] 未找到技能: {args.skill}")
        print(f"  在 {source_dir} 中查找包含 SKILL.md 的目录")
        print()
        print("可用技能：")
        for e in entries:
            print(f"  - {e['name']}")
        sys.exit(1)

    entry = matches[0]
    if upload_skill(entry, category=args.category, dry_run=args.dry_run):
        print()
        if not args.dry_run:
            print(f"已上传到: {SKILLS_DEST / args.category / entry['name']}")
            print()
            print("后续步骤：")
            print("  1. 检查 SKILL.md 内容是否符合仓库规范")
            print("  2. git add & git commit（prek 会自动同步 manifest 和 README）")
            print("  3. git push")
    else:
        print("[ERROR] 上传失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
