#!/usr/bin/env python3
"""
mcd Skills 跨平台安装脚本：将仓库 skills/ 安装到 Claude Code / Codex / Kiro 本地目录。

用法:
    python scripts/install.py --target claude            # 安装全部到 Claude Code
    python scripts/install.py --target codex             # 安装全部到 Codex
    python scripts/install.py --target kiro              # 安装全部到 Kiro
    python scripts/install.py --target claude --list     # 列出可用技能
    python scripts/install.py --target kiro --skill <n>  # 安装单个到 Kiro
    python scripts/install.py --target codex --category tools
    python scripts/install.py --target claude --dry-run

环境变量:
    SKILLS_SRC         覆盖技能源目录（默认: 仓库根/skills）
    CLAUDE_SKILLS_DIR  覆盖 Claude Code 安装目录（默认: ~/.claude）
    CODEX_SKILLS_DIR   覆盖 Codex 安装目录（默认: ~/.codex/skills）
    KIRO_SKILLS_DIR    覆盖 Kiro 安装目录（默认: ~/.kiro/skills）
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_SRC = Path(os.environ.get("SKILLS_SRC", REPO_ROOT / "skills"))
COMMANDS_SRC = REPO_ROOT / "commands"

TARGET_DIRS = {
    "claude": Path(os.environ.get("CLAUDE_SKILLS_DIR", Path.home() / ".claude")),
    "codex": Path(os.environ.get("CODEX_SKILLS_DIR", Path.home() / ".codex" / "skills")),
    "kiro": Path(os.environ.get("KIRO_SKILLS_DIR", Path.home() / ".kiro" / "skills")),
}

TARGET_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "kiro": "Kiro",
}


# ── skill discovery ──────────────────────────────────────────────


def is_public(rel_parts: tuple) -> bool:
    return not any(part.startswith("_") for part in rel_parts)


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


def discover_skills() -> list:
    entries = []
    for skill_md in sorted(SKILLS_SRC.rglob("SKILL.md")):
        rel = skill_md.parent.relative_to(SKILLS_SRC)
        parts = rel.parts
        if not is_public(parts):
            continue
        category = parts[0] if len(parts) > 1 else "uncategorized"
        name, desc = parse_frontmatter(skill_md)
        entries.append({
            "name": name,
            "category": category,
            "description": desc,
            "source": skill_md.parent,
        })
    return entries


# ── list / install ───────────────────────────────────────────────

def list_skills(entries: list, dest_dir: Path, target: str) -> None:
    categories = {}
    for e in entries:
        categories.setdefault(e["category"], []).append(e)

    skill_dir = dest_dir / "skills" if target == "claude" else dest_dir
    print(f"来源: {SKILLS_SRC}")
    print(f"目标: {skill_dir}")
    if target == "claude":
        print(f"命令: {dest_dir / 'commands'}")
    print()
    print("分类：")
    print("-" * 50)
    for cat in sorted(categories):
        print(f"  {cat}: {len(categories[cat])} skills")
    print()
    print("技能列表：")
    print("-" * 50)
    for cat in sorted(categories):
        print(f"\n  [{cat}]")
        for e in sorted(categories[cat], key=lambda x: x["name"]):
            short = (e["description"][:60] + "...") if len(e["description"]) > 60 else e["description"]
            print(f"    - {e['name']}: {short}")


def install_skill(entry: dict, dest_dir: Path, target: str, dry_run: bool = False) -> bool:
    name = entry["name"]
    src = entry["source"]

    if target == "claude":
        skill_dest = dest_dir / "skills" / name
        cmd_src = COMMANDS_SRC / f"{name}.md"
        cmd_dest = dest_dir / "commands" / f"{name}.md"
    else:
        skill_dest = dest_dir / name
        cmd_src = None
        cmd_dest = None

    if dry_run:
        print(f"  [DRY RUN] {name}: {src} -> {skill_dest}")
        if cmd_src and cmd_src.exists():
            print(f"  [DRY RUN] {name}: {cmd_src} -> {cmd_dest}")
        return True

    skill_dest.parent.mkdir(parents=True, exist_ok=True)
    if skill_dest.exists():
        print(f"  更新: {name}")
        shutil.rmtree(skill_dest)
    else:
        print(f"  安装: {name}")

    shutil.copytree(src, skill_dest)

    # Claude Code: also install the command file
    if cmd_src and cmd_dest:
        cmd_dest.parent.mkdir(parents=True, exist_ok=True)
        if cmd_src.exists():
            shutil.copy2(cmd_src, cmd_dest)
            print(f"    + command: {name}.md")
        else:
            print(f"    ⚠ command 文件不存在: {cmd_src}")

    return True


# ── main ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="安装 skills 到 Claude Code / Codex / Kiro 本地目录",
    )
    parser.add_argument(
        "--target", choices=["claude", "codex", "kiro"], required=True,
        help="安装目标: claude (~/.claude) / codex (~/.codex/skills) / kiro (~/.kiro/skills)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", default=True, help="安装全部技能（默认）")
    group.add_argument("--list", action="store_true", help="列出可用技能")
    group.add_argument("--skill", type=str, help="安装单个技能")
    group.add_argument("--category", type=str, help="安装某个分类")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际安装")
    args = parser.parse_args()

    label = TARGET_LABELS[args.target]
    dest_dir = TARGET_DIRS[args.target]

    print()
    print("========================================")
    print(f"  mcd Skills - {label} 安装脚本")
    print("========================================")
    print()

    if not SKILLS_SRC.exists():
        print(f"[ERROR] 未找到 skills 目录: {SKILLS_SRC}")
        sys.exit(1)

    entries = discover_skills()
    if not entries:
        print("[WARNING] 未发现任何技能")
        sys.exit(0)

    if args.list:
        list_skills(entries, dest_dir, target=args.target)
        return

    targets = entries
    if args.skill:
        targets = [e for e in entries if e["name"] == args.skill]
        if not targets:
            print(f"[ERROR] 未找到技能: {args.skill}")
            sys.exit(1)
    elif args.category:
        targets = [e for e in entries if e["category"] == args.category]
        if not targets:
            print(f"[ERROR] 分类不存在或无技能: {args.category}")
            sys.exit(1)

    ok, fail = 0, 0
    for e in targets:
        if install_skill(e, dest_dir, target=args.target, dry_run=args.dry_run):
            ok += 1
        else:
            fail += 1

    print()
    print(f"完成: {ok} 成功, {fail} 失败")
    if not args.dry_run:
        print(f"已安装到: {dest_dir}")
    print()
    print(f"请重启 {label} 以加载新技能。")


if __name__ == "__main__":
    main()
