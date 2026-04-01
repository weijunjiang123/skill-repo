"""CLI 入口与子命令定义 — 使用 rich-click 实现现代化终端体验"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import rich_click as click

import skill_repo
from skill_repo._console import (
    config_table,
    console,
    error,
    info,
    platform_table,
    skill_table,
    status_panel,
    status_spinner,
    success,
    warning,
)
from skill_repo.config_manager import ConfigManager
from skill_repo.git_manager import GitManager
from skill_repo.metadata import MetadataParser, SkillInfo
from skill_repo.platforms import PlatformRegistry
from skill_repo.skill_manager import SkillManager

# ── rich-click 配置 ──────────────────────────────────────────────

click.rich_click.USE_RICH_MARKUP = True
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
click.rich_click.STYLE_COMMANDS_TABLE_COLUMN_WIDTH_RATIO = (1, 2)
click.rich_click.COMMAND_GROUPS = {
    "skill-repo": [
        {"name": "仓库管理", "commands": ["connect", "init", "status"]},
        {"name": "Skill 操作", "commands": ["install", "upload"]},
        {"name": "工具", "commands": ["config", "prek", "interactive"]},
    ]
}


# ── helpers ──────────────────────────────────────────────────────


def _get_config() -> ConfigManager:
    return ConfigManager()


def _get_git() -> GitManager:
    config = _get_config()
    cache_base = Path(config.config_path).parent / "cache"
    return GitManager(cache_dir=cache_base)


def _get_skill_manager(repo_path: Path | None = None) -> SkillManager:
    commands_dir = repo_path / "commands" if repo_path else None
    return SkillManager(
        metadata_parser=MetadataParser(),
        platform_registry=PlatformRegistry(),
        commands_dir=commands_dir,
    )


def _require_connected() -> tuple[ConfigManager, str, Path]:
    """检查仓库是否已连接，未连接时输出错误并退出。"""
    config = _get_config()
    repo_url = config.get("repo.url")
    cache_path_str = config.get("repo.cache_path")

    if not repo_url or not cache_path_str:
        error(
            "未连接到任何远程仓库。",
            hint="使用 [bold]skill-repo connect <git-url>[/bold] 或 [bold]skill-repo init <git-url>[/bold]",
        )
        sys.exit(1)

    cache_path = Path(cache_path_str)
    return config, repo_url, cache_path


# ── CLI 入口 ─────────────────────────────────────────────────────


@click.group()
@click.version_option(version=skill_repo.__version__)
def cli():
    """[bold cyan]Skill 仓库 CLI 工具[/bold cyan] — 管理和共享 code agent 技能"""


# ── connect ──────────────────────────────────────────────────────


@cli.command()
@click.argument("git_url")
def connect(git_url: str):
    """连接到远程 skill 仓库"""
    git = _get_git()

    if not git.validate_url(git_url):
        error(
            f"无效的 Git URL: {git_url}",
            hint="支持格式: https://github.com/user/repo.git 或 git@github.com:user/repo.git",
        )
        sys.exit(1)

    with status_spinner(f"正在连接 {git_url} ..."):
        try:
            repo_path = git.clone(git_url)
        except RuntimeError as exc:
            error(str(exc))
            sys.exit(1)

    if not git.has_skills_dir(repo_path):
        warning("该仓库不包含 skills/ 目录，可能不是有效的 skill 仓库。")
        info("使用 [bold]skill-repo init <git-url>[/bold] 初始化仓库结构。")

    config = _get_config()
    config.set("repo.url", git_url)
    config.set("repo.cache_path", str(repo_path))

    success("已成功连接到远程仓库。")


# ── init ─────────────────────────────────────────────────────────


@cli.command()
@click.argument("git_url")
def init(git_url: str):
    """初始化远程仓库为 skill 仓库"""
    git = _get_git()

    if not git.validate_url(git_url):
        error(
            f"无效的 Git URL: {git_url}",
            hint="支持格式: https://github.com/user/repo.git 或 git@github.com:user/repo.git",
        )
        sys.exit(1)

    with status_spinner(f"正在克隆 {git_url} ..."):
        try:
            repo_path = git.clone(git_url)
        except RuntimeError as exc:
            error(str(exc))
            sys.exit(1)

    if git.has_skills_dir(repo_path):
        warning("该仓库已包含 skills/ 目录结构。")
        info("建议使用 [bold]skill-repo connect <git-url>[/bold] 直接连接。")
        sys.exit(0)

    with status_spinner("正在创建标准 skill 仓库结构 ..."):
        git.init_repo_structure(repo_path)

    with status_spinner("正在提交并推送初始结构 ..."):
        try:
            git.add_commit_push(repo_path, "初始化 skill 仓库结构")
        except RuntimeError as exc:
            warning(f"推送失败: {exc}")
            info(f"本地结构已创建，请手动推送:\n    cd {repo_path}\n    git push")

    config = _get_config()
    config.set("repo.url", git_url)
    config.set("repo.cache_path", str(repo_path))

    success("skill 仓库初始化完成。")


# ── status ───────────────────────────────────────────────────────


@cli.command()
def status():
    """查看仓库连接状态和 skill 概览"""
    config = _get_config()
    repo_url = config.get("repo.url")

    if not repo_url:
        console.print(
            status_panel(
                "未连接",
                "[warning]未连接到任何远程仓库[/warning]\n\n"
                "  [bold]skill-repo connect <git-url>[/bold]   连接已有仓库\n"
                "  [bold]skill-repo init <git-url>[/bold]      初始化新仓库",
                border="yellow",
            )
        )
        return

    cache_path_str = config.get("repo.cache_path")
    cache_path = Path(cache_path_str) if cache_path_str else None

    # 仓库信息面板
    repo_info = f"[bold]URL:[/bold] {repo_url}"

    if cache_path and cache_path.is_dir():
        skills_dir = cache_path / "skills"
        sm = _get_skill_manager(cache_path)
        skills = sm.discover_skills(skills_dir)

        repo_info += f"\n[bold]Skill 总数:[/bold] {len(skills)}"

        if skills:
            categories: dict[str, int] = {}
            for s in skills:
                categories[s.category] = categories.get(s.category, 0) + 1
            cats_str = "  ".join(f"{cat}: {count}" for cat, count in sorted(categories.items()))
            repo_info += f"\n[bold]分类:[/bold] {cats_str}"
    else:
        repo_info += "\n[dim]Skill 总数: (缓存不可用)[/dim]"

    console.print(status_panel("仓库状态", repo_info))
    console.print()

    # 本地平台表格
    registry = PlatformRegistry()
    platform_data: list[tuple[str, bool, int]] = []
    for pc in registry.all():
        exists = pc.skills_dir.is_dir()
        installed = sum(1 for d in pc.skills_dir.iterdir() if d.is_dir()) if exists else 0
        platform_data.append((pc.label, exists, installed))

    console.print(platform_table(platform_data))


# ── install ──────────────────────────────────────────────────────


@cli.command()
@click.option("--target", type=click.Choice(["claude", "codex", "kiro"]), required=True,
              help="目标平台")
@click.option("--skill", default=None, help="要安装的 skill 名称")
@click.option("--all", "install_all", is_flag=True, help="安装所有 skill")
@click.option("--list", "list_skills", is_flag=True, help="列出可用 skill")
def install(target: str, skill: str | None, install_all: bool, list_skills: bool):
    """从远程仓库安装 skill 到本地平台"""
    _config, _repo_url, cache_path = _require_connected()
    skills_dir = cache_path / "skills"
    sm = _get_skill_manager(cache_path)

    available = sm.discover_skills(skills_dir)

    if list_skills or (not skill and not install_all):
        if not available:
            warning("仓库中暂无 skill")
            return
        console.print(skill_table(available, title="可用 Skill"))
        return

    if install_all:
        with status_spinner(f"正在安装 {len(available)} 个 skill 到 {target} ..."):
            count = sm.install_all(skills_dir, target)
        success(f"已安装 {count} 个 skill 到 {target} 平台。")
        return

    if skill:
        matched = [s for s in available if s.metadata.name == skill]
        if not matched:
            error(
                f"未找到名为 '{skill}' 的 skill。",
                hint="使用 [bold]--list[/bold] 查看可用 skill。",
            )
            sys.exit(1)

        target_skill = matched[0]
        with status_spinner(f"正在安装 {skill} 到 {target} ..."):
            sm.install_skill(target_skill, target)
        success(f"已安装 skill '{skill}' 到 {target} 平台。")


# ── upload ───────────────────────────────────────────────────────


@cli.command()
@click.option("--source", type=click.Choice(["claude", "codex", "kiro"]), required=True,
              help="来源平台")
@click.option("--skill", default=None, help="要上传的 skill 名称")
@click.option("--no-push", is_flag=True, help="仅本地 commit，不推送到远程")
@click.option("--category", default=None, help="skill 分类目录")
@click.option("--list", "list_skills", is_flag=True, help="列出本地可用 skill")
def upload(source: str, skill: str | None, no_push: bool, category: str | None, list_skills: bool):
    """上传本地 skill 到远程仓库"""
    _config, _repo_url, cache_path = _require_connected()

    registry = PlatformRegistry()
    platform_config = registry.get(source)
    local_skills_dir = platform_config.skills_dir

    parser = MetadataParser()
    local_skills: list[SkillInfo] = []
    if local_skills_dir.is_dir():
        for child in sorted(local_skills_dir.iterdir()):
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.exists():
                    metadata = parser.parse(skill_md)
                    local_skills.append(SkillInfo(metadata=metadata, category="local", source_path=child))

    if list_skills:
        if not local_skills:
            warning(f"{platform_config.label} 平台暂无 skill")
            return
        console.print(skill_table(local_skills, title=f"{platform_config.label} 本地 Skill"))
        return

    if not skill:
        error(
            "请通过 --skill 指定要上传的 skill 名称。",
            hint="使用 [bold]--list[/bold] 查看本地可用 skill。",
        )
        sys.exit(1)

    matched = [s for s in local_skills if s.metadata.name == skill]
    if not matched and local_skills_dir.is_dir():
        direct = local_skills_dir / skill
        if direct.is_dir() and (direct / "SKILL.md").exists():
            metadata = parser.parse(direct / "SKILL.md")
            matched = [SkillInfo(metadata=metadata, category="local", source_path=direct)]

    if not matched:
        error(
            f"在 {platform_config.label} 平台未找到名为 '{skill}' 的 skill。",
            hint="使用 [bold]--list[/bold] 查看本地可用 skill。",
        )
        sys.exit(1)

    source_skill = matched[0]

    errors = parser.validate(source_skill.source_path)
    if errors:
        error(f"skill '{skill}' 元数据不完整，无法上传:")
        for e in errors:
            console.print(f"    [error]•[/error] {e}")
        sys.exit(1)

    cat = category or "uncategorized"
    skill_name = source_skill.metadata.name
    dest = cache_path / "skills" / cat / skill_name

    is_update = dest.exists()
    with status_spinner("正在复制 skill 到仓库缓存 ..."):
        sm = _get_skill_manager(cache_path)
        sm.copy_skill(source_skill.source_path, dest)

    action_label = "更新" if is_update else "添加"
    success(f"已将 skill '{skill_name}' 复制到仓库缓存。")

    git = _get_git()
    commit_msg = f"{action_label} skill: {skill_name} (来源: {source}, 分类: {cat})"
    with status_spinner("正在提交到 Git ..."):
        try:
            git.add_commit_push(cache_path, commit_msg, push=not no_push)
        except RuntimeError as exc:
            err_msg = str(exc)
            if "push" in err_msg.lower():
                warning(f"推送失败: {exc}")
                info(f"skill 已提交到本地仓库，请手动推送:\n    cd {cache_path}\n    git push")
                return
            else:
                error(f"Git 操作失败: {exc}")
                sys.exit(1)

    if no_push:
        success("已提交到本地仓库（未推送）。")
    else:
        success("已提交并推送到远程仓库。")


# ── config 子命令组 ──────────────────────────────────────────────


@cli.group()
def config():
    """配置管理"""


@config.command("show")
def config_show():
    """显示所有配置项"""
    cm = _get_config()
    data = cm.load()

    if not data:
        info("暂无配置项")
        return

    def _flatten(d: dict, prefix: str = "") -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for k, v in d.items():
            full_key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict):
                items.extend(_flatten(v, full_key))
            else:
                items.append((full_key, str(v)))
        return items

    console.print(config_table(_flatten(data)))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """更新配置项"""
    cm = _get_config()
    cm.set(key, value)
    success(f"已设置 {key} = {value}")


# ── prek 子命令组 ────────────────────────────────────────────────


def _check_prek_installed() -> bool:
    if shutil.which("prek") is None:
        warning("prek 未安装。")
        info("请先安装: [bold]pip install prek[/bold]")
        return False
    return True


@cli.group()
def prek():
    """prek 集成管理"""


@prek.command("setup")
def prek_setup():
    """生成/更新 prek.toml 配置"""
    _check_prek_installed()

    _config, _repo_url, cache_path = _require_connected()

    prek_toml_path = cache_path / "prek.toml"
    action = "更新" if prek_toml_path.exists() else "生成"

    content = (
        'default_install_hook_types = ["post-commit"]\n'
        'default_stages = ["post-commit"]\n'
        "\n"
        "[[repos]]\n"
        'repo = "local"\n'
        "hooks = [\n"
        '  { id = "sync-skills-artifacts", name = "Sync marketplace and skills README", '
        'entry = "python scripts/post_commit_sync.py", language = "system", '
        'pass_filenames = false, always_run = true, stages = ["post-commit"] },\n'
        "]\n"
    )
    prek_toml_path.write_text(content, encoding="utf-8")

    success(f"已{action} {prek_toml_path}")


@prek.command("run")
def prek_run():
    """手动触发同步脚本"""
    _check_prek_installed()

    _config, _repo_url, cache_path = _require_connected()

    scripts = [
        "sync_claude_marketplace.py",
        "sync_skills_readme.py",
        "sync_commands.py",
    ]
    scripts_dir = cache_path / "scripts"

    ran = 0
    for script_name in scripts:
        script_path = scripts_dir / script_name
        if not script_path.is_file():
            info(f"跳过 {script_name} (文件不存在)")
            continue
        with status_spinner(f"运行 {script_name} ..."):
            try:
                subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=str(cache_path),
                    check=True,
                    capture_output=True,
                    text=True,
                )
                ran += 1
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.strip() if exc.stderr else ""
                error(f"{script_name} 执行失败: {stderr}")

    success(f"已运行 {ran}/{len(scripts)} 个同步脚本。")


@prek.command("scan")
def prek_scan():
    """扫描 skill 并输出摘要"""
    _config, _repo_url, cache_path = _require_connected()

    skills_dir = cache_path / "skills"
    parser = MetadataParser()
    sm = _get_skill_manager(cache_path)

    with status_spinner("正在扫描 skill ..."):
        skills = sm.discover_skills(skills_dir)

    if not skills:
        info("未发现任何 skill")
        return

    console.print(skill_table(skills, title=f"Skill 扫描结果 ({len(skills)} 个)"))

    # 检查元数据不完整的 skill
    incomplete: list[tuple[str, list[str]]] = []
    for s in skills:
        errs = parser.validate(s.source_path)
        if errs:
            incomplete.append((s.metadata.name, errs))

    if incomplete:
        console.print()
        warning("元数据不完整的 skill:")
        for name, errs in incomplete:
            console.print(f"    [bold]{name}[/bold]:")
            for e in errs:
                console.print(f"      [error]•[/error] {e}")
    else:
        console.print()
        success("所有 skill 元数据完整")


# ── interactive 子命令 ───────────────────────────────────────────


@cli.command()
def interactive():
    """进入交互式 TUI 模式"""
    from skill_repo.interactive import run_interactive

    run_interactive()
