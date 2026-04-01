"""交互式 TUI 模式 - 使用 rich + questionary 实现美观的菜单式交互"""

from __future__ import annotations

import os
from pathlib import Path

import questionary
from questionary import Style
from rich.panel import Panel

from skill_repo._console import (
    console,
    error,
    skill_table,
    status_spinner,
    success,
    warning,
)
from skill_repo.config_manager import ConfigManager
from skill_repo.git_manager import GitManager
from skill_repo.metadata import MetadataParser, SkillInfo
from skill_repo.platforms import PlatformRegistry
from skill_repo.skill_manager import SkillManager

# questionary 自定义样式
_QS = Style([
    ("qmark", "fg:cyan bold"),
    ("question", "bold"),
    ("answer", "fg:cyan"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan bold"),
    ("selected", "fg:green"),
    ("separator", "fg:#808080"),
    ("instruction", "fg:#808080"),
])


# ── helpers ──────────────────────────────────────────────────────

def _get_config() -> ConfigManager:
    return ConfigManager()

def _get_git() -> GitManager:
    config = _get_config()
    cache_base = Path(config.config_path).parent / "cache"
    return GitManager(cache_dir=cache_base)

def _get_skill_manager(repo_path: Path | None = None) -> SkillManager:
    commands_dir = repo_path / "commands" if repo_path else None
    return SkillManager(MetadataParser(), PlatformRegistry(), commands_dir=commands_dir)


def _get_connected_repo() -> tuple[str, Path] | None:
    config = _get_config()
    url = config.get("repo.url")
    cache = config.get("repo.cache_path")
    if not url or not cache:
        return None
    p = Path(cache)
    return (url, p) if p.is_dir() else None


def _ask(prompt_fn):
    """Wrap a questionary prompt — return None on Esc/Ctrl+C."""
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    from prompt_toolkit.keys import Keys

    app = prompt_fn.application
    app.timeoutlen = 0.05

    esc_kb = KeyBindings()

    @esc_kb.add(Keys.Escape)
    def _esc_handler(event):
        event.app.exit(exception=KeyboardInterrupt)

    app.key_bindings = merge_key_bindings([app.key_bindings, esc_kb])

    try:
        return app.run()
    except KeyboardInterrupt:
        return None


def _banner() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    console.print(
        Panel(
            "[bold cyan]Skill Repo[/bold cyan]  [dim]— 团队 Skill 共享管理工具[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()


def _not_connected_msg() -> None:
    console.print(
        Panel(
            "[warning]未连接到远程仓库[/warning]\n"
            "使用主菜单「仓库管理」连接或初始化仓库",
            border_style="yellow",
            title="提示",
        )
    )


# ── actions ──────────────────────────────────────────────────────

def _action_overview() -> None:
    """查看 skill 概览 - 远程仓库 + 本地平台详细列表"""
    conn = _get_connected_repo()
    parser = MetadataParser()

    # ── 远程仓库 ──
    if conn:
        url, cache_path = conn
        sm = _get_skill_manager(cache_path)
        skills = sm.discover_skills(cache_path / "skills")

        console.print(f"  [dim]仓库:[/dim] {url}\n")

        if skills:
            console.print(skill_table(skills, title="远程仓库 Skill"))
        else:
            warning("仓库中暂无 skill")
    else:
        _not_connected_msg()

    # ── 本地平台 ──
    console.print()
    registry = PlatformRegistry()
    for pc in registry.all():
        if not pc.skills_dir.is_dir():
            console.print(f"  [bold]{pc.label}[/bold]  [dim]— 目录不存在[/dim]")
            continue

        local_skills: list[SkillInfo] = []
        for child in sorted(pc.skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                meta = parser.parse(child / "SKILL.md")
                local_skills.append(SkillInfo(metadata=meta, category="local", source_path=child))

        if not local_skills:
            console.print(f"  [bold]{pc.label}[/bold]  [dim]— 无 skill[/dim]")
            continue

        console.print(skill_table(local_skills, title=f"{pc.label} ({len(local_skills)} skills)"))
        console.print()

    _ask(questionary.select(
        "",
        choices=["← 返回主菜单"],
        style=_QS,
        instruction="(Esc 返回)",
    ))


def _action_install() -> None:
    """安装 skill（仓库 → 本地）"""
    conn = _get_connected_repo()
    if not conn:
        _not_connected_msg()
        return

    _url, cache_path = conn
    sm = _get_skill_manager(cache_path)
    available = sm.discover_skills(cache_path / "skills")

    if not available:
        warning("仓库中暂无 skill")
        return

    # 选平台
    registry = PlatformRegistry()
    platforms = registry.all()
    target_name = _ask(questionary.select(
        "安装到哪个平台?",
        choices=[pc.label for pc in platforms],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if target_name is None:
        return
    target = next(pc for pc in platforms if pc.label == target_name)

    # 选 skill
    choices = [
        questionary.Choice(
            title=f"{s.metadata.name}  {s.category}  {s.metadata.description or ''}",
            value=i,
        )
        for i, s in enumerate(available)
    ]
    selected = _ask(questionary.checkbox(
        "选择 skill (Space 选择, Enter 确认, Esc 返回):",
        choices=choices,
        style=_QS,
    ))
    if not selected:
        console.print("  [dim]已取消[/dim]")
        return

    with status_spinner(f"正在安装 {len(selected)} 个 skill ..."):
        for idx in selected:
            skill = available[idx]
            sm.install_skill(skill, target.name)

    for idx in selected:
        skill = available[idx]
        success(skill.metadata.name)

    console.print(f"\n  [success]已安装 {len(selected)} 个 skill 到 {target.label}[/success]")


def _action_upload() -> None:
    """上传 skill（本地 → 仓库）"""
    conn = _get_connected_repo()
    if not conn:
        _not_connected_msg()
        return

    _url, cache_path = conn
    registry = PlatformRegistry()
    platforms = registry.all()
    parser = MetadataParser()

    # 选来源平台
    source_name = _ask(questionary.select(
        "从哪个平台上传?",
        choices=[pc.label for pc in platforms],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if source_name is None:
        return
    source = next(pc for pc in platforms if pc.label == source_name)

    # 扫描本地 skill
    local_skills: list[SkillInfo] = []
    if source.skills_dir.is_dir():
        for child in sorted(source.skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                meta = parser.parse(child / "SKILL.md")
                local_skills.append(SkillInfo(metadata=meta, category="local", source_path=child))

    if not local_skills:
        warning(f"{source.label} 平台暂无 skill")
        return

    # 选 skill
    skill_choice = _ask(questionary.select(
        "选择要上传的 skill:",
        choices=[s.metadata.name for s in local_skills],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if skill_choice is None:
        return
    skill = next(s for s in local_skills if s.metadata.name == skill_choice)

    # 验证
    errors = parser.validate(skill.source_path)
    if errors:
        error("元数据不完整:")
        for e in errors:
            console.print(f"    [error]•[/error] {e}")
        return

    # 选分类
    skills_dir = cache_path / "skills"
    cats = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith("_")) if skills_dir.is_dir() else []
    if not cats:
        cats = ["uncategorized"]
    cat_choices = cats + ["+ 新建分类"]

    cat = _ask(questionary.select("选择分类:", choices=cat_choices, style=_QS, instruction="(Esc 返回)"))
    if cat is None:
        return
    if cat == "+ 新建分类":
        cat = _ask(questionary.text("输入分类名:", style=_QS))
        if not cat or not cat.strip():
            return
        cat = cat.strip()

    # 复制 + git
    dest = cache_path / "skills" / cat / skill.metadata.name
    is_update = dest.exists()
    sm = _get_skill_manager(cache_path)

    with status_spinner("正在复制到仓库缓存 ..."):
        sm.copy_skill(skill.source_path, dest)
    success("已复制到仓库缓存")

    label = "更新" if is_update else "添加"
    git = _get_git()
    msg = f"{label} skill: {skill.metadata.name} ({source.name}/{cat})"

    with status_spinner("正在推送到远程仓库 ..."):
        try:
            git.add_commit_push(cache_path, msg, push=True)
        except RuntimeError as exc:
            if "push" in str(exc).lower():
                warning("推送失败，请手动 git push")
            else:
                error(f"Git 错误: {exc}")
            return

    success("已推送到远程仓库")


def _action_repo() -> None:
    """仓库管理"""
    conn = _get_connected_repo()
    if conn:
        url, _ = conn
        console.print(f"  [dim]当前仓库:[/dim] {url}\n")

    choice = _ask(questionary.select(
        "操作:",
        choices=["连接已有仓库", "初始化新仓库", "断开连接"],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if choice is None:
        return

    if choice == "断开连接":
        if not conn:
            console.print("  [dim]当前未连接[/dim]")
            return
        ok = _ask(questionary.confirm("确认断开?", default=False, style=_QS))
        if ok:
            config = _get_config()
            config.set("repo.url", "")
            config.set("repo.cache_path", "")
            success("已断开")
        return

    url = _ask(questionary.text("Git 仓库 URL:", style=_QS))
    if not url or not url.strip():
        return
    url = url.strip()

    git = _get_git()
    if not git.validate_url(url):
        error("无效 URL", hint="支持 https://... 或 git@...:...")
        return

    with status_spinner(f"正在克隆 {url} ..."):
        try:
            repo_path = git.clone(url)
        except RuntimeError as exc:
            error(str(exc))
            return

    if choice == "初始化新仓库":
        has_commits = git._has_commits(repo_path)
        if has_commits and git.has_skills_dir(repo_path):
            with status_spinner("正在检查远程仓库状态 ..."):
                try:
                    git._run_git(["push"], cwd=repo_path)
                    success("已推送到远程仓库")
                except RuntimeError:
                    try:
                        branch = git._get_current_branch(repo_path)
                        git._run_git(["push", "-u", "origin", branch], cwd=repo_path)
                        success("已推送到远程仓库")
                    except RuntimeError as exc:
                        if "up to date" in str(exc).lower() or "everything" in str(exc).lower():
                            success("远程仓库已是最新")
                        else:
                            warning(f"推送失败: {exc}")
                            console.print(f"    cd {repo_path}")
                            console.print("    git push -u origin main")
        else:
            with status_spinner("正在创建仓库结构 ..."):
                git.init_repo_structure(repo_path)
            with status_spinner("正在提交并推送 ..."):
                try:
                    git.add_commit_push(repo_path, "初始化 skill 仓库结构")
                    success("已初始化并推送")
                except RuntimeError as exc:
                    warning(f"推送失败: {exc}")
                    console.print("  本地结构已创建，请手动推送:")
                    console.print(f"    cd {repo_path}")
                    console.print("    git push -u origin main")
    else:
        if not git.has_skills_dir(repo_path):
            warning("该仓库无 skills/ 目录")

    config = _get_config()
    config.set("repo.url", url)
    config.set("repo.cache_path", str(repo_path))
    success("已连接")


# ── main menu ────────────────────────────────────────────────────

_MENU = [
    ("📋  概览", _action_overview),
    ("📥  安装 Skill", _action_install),
    ("📤  上传 Skill", _action_upload),
    ("🔗  仓库管理", _action_repo),
    ("🚪  退出", None),
]


def run_interactive() -> None:
    """交互式 TUI 入口"""
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h = k.GetStdHandle(-11)
            m = ctypes.c_ulong()
            k.GetConsoleMode(h, ctypes.byref(m))
            k.SetConsoleMode(h, m.value | 0x0004)
        except Exception:
            pass

    try:
        while True:
            _banner()
            choice = _ask(questionary.select(
                "操作:",
                choices=[label for label, _ in _MENU],
                style=_QS,
            ))

            if choice is None:
                break

            action = dict(_MENU).get(choice)
            if action is None:
                break

            console.print()
            action()

            if action is not _action_overview:
                console.print()
                _ask(questionary.select(
                    "",
                    choices=["← 返回主菜单"],
                    style=_QS,
                    instruction="(Esc 返回)",
                ))

    except KeyboardInterrupt:
        pass

    console.print("\n  [dim]再见 👋[/dim]\n")
