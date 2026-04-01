#!/usr/bin/env python3
"""
mcd Skills 交互式管理工具。

用法:
    python scripts/cli.py

提供菜单式交互，支持上下键选择，无需记忆命令参数。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_SRC = REPO_ROOT / "skills"
COMMANDS_SRC = REPO_ROOT / "commands"

PLATFORMS = {
    "claude": {
        "label": "Claude Code",
        "skills_dir": Path(os.environ.get(
            "CLAUDE_SKILLS_DIR", Path.home() / ".claude")),
        "is_claude": True,
    },
    "codex": {
        "label": "Codex",
        "skills_dir": Path(os.environ.get(
            "CODEX_SKILLS_DIR", Path.home() / ".codex" / "skills")),
        "is_claude": False,
    },
    "kiro": {
        "label": "Kiro",
        "skills_dir": Path(os.environ.get(
            "KIRO_SKILLS_DIR", Path.home() / ".kiro" / "skills")),
        "is_claude": False,
    },
}

# ── colors ───────────────────────────────────────────────────────

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
REVERSE = "\033[7m"
RESET = "\033[0m"


# ── terminal input ───────────────────────────────────────────────

def _enable_ansi_windows():
    """Enable ANSI escape codes on Windows 10+."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def read_key():
    """Read a single keypress. Returns 'up', 'down', 'enter', 'space', 'q', or char."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            return "enter"
        if ch == " ":
            return "space"
        if ch == "q":
            return "q"
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            if ch2 == "H":
                return "up"
            if ch2 == "P":
                return "down"
            return ""
        return ch
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                return "enter"
            if ch == " ":
                return "space"
            if ch == "q":
                return "q"
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    if ch3 == "B":
                        return "down"
                return ""
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── UI components ────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def move_up(n):
    if n > 0:
        sys.stdout.write(f"\033[{n}A")


def clear_lines(n):
    for _ in range(n):
        sys.stdout.write("\033[2K\033[1B")
    move_up(n)


def banner():
    print()
    print(f"  {CYAN}{BOLD}╔══════════════════════════════════════╗{RESET}")
    print(f"  {CYAN}{BOLD}║     mcd Skills 管理工具              ║{RESET}")
    print(f"  {CYAN}{BOLD}╚══════════════════════════════════════╝{RESET}")
    print()


def pause():
    print(f"\n  {DIM}按任意键继续...{RESET}")
    read_key()


def select_one(title: str, options: list, fmt=None) -> int:
    """Arrow-key single select. Returns index or -1."""
    if not options:
        print(f"  {DIM}（无可用选项）{RESET}")
        return -1

    cur = 0
    total = len(options) + 1  # options + back

    def render():
        print(f"  {BOLD}{title}{RESET}  {DIM}↑↓ 移动  Enter 确认{RESET}\n")
        for i, opt in enumerate(options):
            label = fmt(opt) if fmt else str(opt)
            if i == cur:
                print(f"  {CYAN}{BOLD}❯ {label}{RESET}")
            else:
                print(f"    {label}")
        # back option
        if cur == len(options):
            print(f"\n  {CYAN}{BOLD}❯ ← 返回{RESET}")
        else:
            print(f"\n    {DIM}← 返回{RESET}")

    hide_cursor()
    try:
        render()
        while True:
            key = read_key()
            if key == "up":
                cur = (cur - 1) % total
            elif key == "down":
                cur = (cur + 1) % total
            elif key == "enter":
                show_cursor()
                print()
                if cur == len(options):
                    return -1
                return cur
            elif key == "q":
                show_cursor()
                print()
                return -1

            # redraw
            lines_to_clear = len(options) + 4  # title + options + blank + back
            move_up(lines_to_clear)
            clear_lines(lines_to_clear)
            render()
    except (KeyboardInterrupt, EOFError):
        show_cursor()
        print()
        return -1


def select_multi(title: str, options: list, fmt=None) -> list:
    """Arrow-key multi select with space to toggle. Returns list of indices."""
    if not options:
        print(f"  {DIM}（无可用选项）{RESET}")
        return []

    cur = 0
    selected = set()
    total = len(options) + 2  # options + select all + confirm

    def render():
        print(f"  {BOLD}{title}{RESET}  {DIM}↑↓ 移动  Space 选择  Enter 确认{RESET}\n")
        for i, opt in enumerate(options):
            label = fmt(opt) if fmt else str(opt)
            check = f"{GREEN}✔{RESET}" if i in selected else " "
            if i == cur:
                print(f"  {CYAN}{BOLD}❯{RESET} [{check}] {CYAN}{label}{RESET}")
            else:
                print(f"    [{check}] {label}")
        # select all
        all_selected = len(selected) == len(options)
        all_check = f"{GREEN}✔{RESET}" if all_selected else " "
        idx_all = len(options)
        if cur == idx_all:
            print(f"\n  {CYAN}{BOLD}❯{RESET} [{all_check}] {CYAN}全选{RESET}")
        else:
            print(f"\n    [{all_check}] {DIM}全选{RESET}")
        # confirm
        idx_confirm = len(options) + 1
        count = len(selected)
        confirm_label = f"确认（已选 {count} 项）" if count else "返回"
        if cur == idx_confirm:
            print(f"  {CYAN}{BOLD}❯ {confirm_label}{RESET}")
        else:
            print(f"    {DIM}{confirm_label}{RESET}")

    hide_cursor()
    try:
        render()
        while True:
            key = read_key()
            if key == "up":
                cur = (cur - 1) % total
            elif key == "down":
                cur = (cur + 1) % total
            elif key == "space":
                if cur < len(options):
                    if cur in selected:
                        selected.discard(cur)
                    else:
                        selected.add(cur)
                elif cur == len(options):
                    # toggle all
                    if len(selected) == len(options):
                        selected.clear()
                    else:
                        selected = set(range(len(options)))
            elif key == "enter":
                show_cursor()
                print()
                if cur == len(options) + 1:
                    return sorted(selected)
                # if on an item, toggle it
                if cur < len(options):
                    if cur in selected:
                        selected.discard(cur)
                    else:
                        selected.add(cur)
                elif cur == len(options):
                    if len(selected) == len(options):
                        selected.clear()
                    else:
                        selected = set(range(len(options)))
            elif key == "q":
                show_cursor()
                print()
                return []

            # redraw
            lines_to_clear = len(options) + 5
            move_up(lines_to_clear)
            clear_lines(lines_to_clear)
            render()
    except (KeyboardInterrupt, EOFError):
        show_cursor()
        print()
        return []


# ── skill helpers ────────────────────────────────────────────────

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
    name, desc = "", ""
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key == "name":
            name = value
        elif key == "description":
            desc = value
    return name or skill_md.parent.name, desc


def is_public(rel_parts: tuple) -> bool:
    return not any(part.startswith("_") for part in rel_parts)


def discover_repo_skills() -> list:
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


def discover_local_skills(skills_dir: Path) -> list:
    entries = []
    if not skills_dir.exists():
        return entries
    for child in sorted(skills_dir.iterdir()):
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


def fmt_skill(e: dict) -> str:
    desc = e.get("description", "")
    short = (desc[:45] + "...") if len(desc) > 45 else desc
    cat = e.get("category", "")
    prefix = f"{DIM}[{cat}]{RESET} " if cat else ""
    return f"{prefix}{e['name']:28s} {DIM}{short}{RESET}"


# ── actions ──────────────────────────────────────────────────────

def action_list():
    """List all skills in repo and local platforms."""
    print(f"  {BOLD}── 技能概览 ──{RESET}\n")

    repo_entries = discover_repo_skills()
    print(f"  {CYAN}仓库技能{RESET}（{len(repo_entries)} 个）")
    print(f"  {'─' * 55}")
    if repo_entries:
        for e in repo_entries:
            print(f"    {fmt_skill(e)}")
    else:
        print(f"    {DIM}（无）{RESET}")

    for key, pinfo in PLATFORMS.items():
        local_dir = (pinfo["skills_dir"] / "skills") if pinfo["is_claude"] else pinfo["skills_dir"]
        entries = discover_local_skills(local_dir)
        print(f"\n  {CYAN}{pinfo['label']} 本地{RESET}（{len(entries)} 个）  {DIM}{local_dir}{RESET}")
        print(f"  {'─' * 55}")
        if entries:
            for e in entries:
                print(f"    {fmt_skill(e)}")
        else:
            status = "目录不存在" if not local_dir.exists() else "无技能"
            print(f"    {DIM}（{status}）{RESET}")


def action_install():
    """Install skills from repo to a local platform."""
    print(f"  {BOLD}── 安装技能（仓库 → 本地）──{RESET}\n")

    platforms = list(PLATFORMS.keys())
    idx = select_one("选择目标平台", platforms,
                     fmt=lambda k: f"{PLATFORMS[k]['label']:15s} {DIM}{PLATFORMS[k]['skills_dir']}{RESET}")
    if idx < 0:
        return
    target = platforms[idx]
    pinfo = PLATFORMS[target]

    entries = discover_repo_skills()
    if not entries:
        print(f"\n  {YELLOW}仓库中未发现任何技能{RESET}")
        return

    selected = select_multi(f"选择要安装到 {pinfo['label']} 的技能", entries, fmt=fmt_skill)
    if not selected:
        return

    dest_dir = pinfo["skills_dir"]
    is_claude = pinfo["is_claude"]
    print()
    for i in selected:
        e = entries[i]
        name = e["name"]
        src = e["source"]
        skill_dest = (dest_dir / "skills" / name) if is_claude else (dest_dir / name)

        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        if skill_dest.exists():
            shutil.rmtree(skill_dest)
            print(f"  {YELLOW}更新{RESET}: {name}")
        else:
            print(f"  {GREEN}安装{RESET}: {name}")
        shutil.copytree(src, skill_dest)

        if is_claude:
            cmd_src = COMMANDS_SRC / f"{name}.md"
            cmd_dest = dest_dir / "commands" / f"{name}.md"
            cmd_dest.parent.mkdir(parents=True, exist_ok=True)
            if cmd_src.exists():
                shutil.copy2(cmd_src, cmd_dest)
                print(f"       {DIM}+ command: {name}.md{RESET}")

    print(f"\n  {GREEN}完成{RESET}，已安装 {len(selected)} 个技能")
    print(f"  请重启 {pinfo['label']} 以加载新技能。")


def action_upload():
    """Upload a skill from local platform to repo."""
    print(f"  {BOLD}── 上传技能（本地 → 仓库）──{RESET}\n")

    platforms = list(PLATFORMS.keys())
    idx = select_one("选择来源平台", platforms,
                     fmt=lambda k: f"{PLATFORMS[k]['label']:15s} {DIM}{PLATFORMS[k]['skills_dir']}{RESET}")
    if idx < 0:
        return
    source = platforms[idx]
    pinfo = PLATFORMS[source]

    local_dir = (pinfo["skills_dir"] / "skills") if pinfo["is_claude"] else pinfo["skills_dir"]
    if not local_dir.exists():
        print(f"\n  {YELLOW}未找到本地 skills 目录: {local_dir}{RESET}")
        return

    entries = discover_local_skills(local_dir)
    if not entries:
        print(f"\n  {YELLOW}{local_dir} 中未发现任何技能{RESET}")
        return

    idx = select_one(f"选择要上传的技能（来自 {pinfo['label']}）", entries, fmt=fmt_skill)
    if idx < 0:
        return
    entry = entries[idx]

    # pick category
    existing_cats = sorted(set(
        d.name for d in SKILLS_SRC.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )) or ["tools"]

    cat_options = existing_cats + ["+ 新建分类"]
    cat_idx = select_one("选择目标分类", cat_options,
                         fmt=lambda c: c)
    if cat_idx < 0:
        return
    if cat_idx == len(existing_cats):
        show_cursor()
        category = input("\n  输入新分类名称: ").strip()
        if not category:
            return
    else:
        category = existing_cats[cat_idx]

    name = entry["name"]
    src = entry["source"]
    dest = SKILLS_SRC / category / name

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
        print(f"\n  {YELLOW}更新{RESET}: {name} → {dest}")
    else:
        print(f"\n  {GREEN}上传{RESET}: {name} → {dest}")
    shutil.copytree(src, dest)

    print(f"\n  {GREEN}已上传到{RESET}: {dest}")
    print(f"\n  {DIM}后续步骤：{RESET}")
    print(f"  {DIM}  1. 检查 SKILL.md 是否符合仓库规范{RESET}")
    print(f"  {DIM}  2. git add & git commit（prek 自动同步）{RESET}")
    print(f"  {DIM}  3. git push{RESET}")


def action_sync():
    """Run sync scripts manually."""
    print(f"  {BOLD}── 手动同步生成文件 ──{RESET}\n")
    scripts = [
        ("sync_claude_marketplace.py", "同步 manifest.json"),
        ("sync_skills_readme.py", "同步 skills/README.md"),
        ("sync_commands.py", "同步 commands/*.md"),
    ]
    for script, desc in scripts:
        path = REPO_ROOT / "scripts" / script
        if not path.exists():
            print(f"  {DIM}跳过: {script}（不存在）{RESET}")
            continue
        print(f"  {CYAN}▸{RESET} {desc}")
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"    {DIM}{line}{RESET}")
        if result.returncode != 0 and result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                print(f"    {YELLOW}{line}{RESET}")
    print(f"\n  {GREEN}同步完成。{RESET}")


# ── main menu ────────────────────────────────────────────────────

ACTIONS = [
    ("📋  查看技能概览", action_list),
    ("📥  安装技能（仓库 → 本地）", action_install),
    ("📤  上传技能（本地 → 仓库）", action_upload),
    ("🔄  手动同步生成文件", action_sync),
]


def main():
    _enable_ansi_windows()

    while True:
        clear()
        banner()
        idx = select_one("请选择操作", [label for label, _ in ACTIONS],
                         fmt=lambda x: x)
        if idx < 0:
            break

        clear()
        banner()
        try:
            ACTIONS[idx][1]()
        except KeyboardInterrupt:
            print(f"\n\n  {YELLOW}已取消。{RESET}")
        pause()

    print(f"\n  {DIM}再见 👋{RESET}\n")
    show_cursor()


if __name__ == "__main__":
    main()
