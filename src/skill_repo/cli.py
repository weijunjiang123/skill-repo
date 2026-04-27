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
    history_table,
    info,
    platform_table,
    repos_table,
    skill_table,
    status_panel,
    status_spinner,
    success,
    update_table,
    warning,
)
from skill_repo.config_manager import ConfigManager
from skill_repo.git_manager import GitManager
from skill_repo.metadata import MetadataParser
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
        {"name": "Skill 操作", "commands": ["install", "upload", "search", "update", "remove", "diff", "create"]},
        {"name": "版本管理", "commands": ["history", "rollback", "pin"]},
        {"name": "协作", "commands": ["branch"]},
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


def _require_connected(from_alias: str | None = None) -> tuple[ConfigManager, str, Path]:
    """检查仓库是否已连接，未连接时输出错误并退出。

    支持 --from alias 指定仓库，默认使用 repo.url（向后兼容）。
    """
    config = _get_config()

    if from_alias:
        repo_info = config.get_repo(from_alias)
        if not repo_info:
            available = config.get_repos()
            if available:
                aliases = ", ".join(available.keys())
                error(
                    f"未找到别名为 '{from_alias}' 的仓库。",
                    hint=f"可用仓库: {aliases}",
                )
            else:
                error(
                    f"未找到别名为 '{from_alias}' 的仓库。",
                    hint="使用 [bold]skill-repo connect <git-url> --alias <name>[/bold] 连接仓库",
                )
            sys.exit(1)
        return config, repo_info["url"], Path(repo_info["cache_path"])

    # 默认：使用旧的 repo.url
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


def _get_branch_mode() -> str:
    """获取分支模式：'direct' 或 'branch'。"""
    config = _get_config()
    mode = config.get("branch.mode")
    return mode if mode in ("direct", "branch") else "direct"


def _upload_with_branch(
    git: GitManager,
    sm: SkillManager,
    cache_path: Path,
    skill_name: str,
    commit_msg: str,
    action: str,
) -> tuple[bool, str]:
    """分支模式上传：创建分支 → commit → push → 尝试 merge。

    返回 (merged, branch_name)。
    """
    username = git.get_username(cache_path)
    branch_name = git.create_skill_branch(cache_path, username, action, skill_name)

    # 在分支上 commit
    git.add_commit_push(cache_path, commit_msg, push=False)

    # push 分支
    git.push_branch(cache_path, branch_name)

    # 读取配置
    config = _get_config()
    auto_merge = config.get("branch.auto_merge") != "false"
    cleanup = config.get("branch.cleanup") != "false"

    if not auto_merge:
        return False, branch_name

    # 尝试 merge 到 main
    merged = git.try_merge_to_main(cache_path, branch_name)
    if merged:
        # 在 main 上运行同步 + 追加提交
        sync_result = sm.sync_all(cache_path)
        if any(sync_result.values()):
            try:
                git.add_commit_push(cache_path, "同步生成文件", push=False)
            except RuntimeError:
                pass
        git.push_main(cache_path)
        if cleanup:
            git.delete_remote_branch(cache_path, branch_name)

    return merged, branch_name


# ── CLI 入口 ─────────────────────────────────────────────────────


@click.group()
@click.version_option(version=skill_repo.__version__)
def cli():
    """[bold cyan]Skill 仓库 CLI 工具[/bold cyan] — 管理和共享 code agent 技能"""


# ── connect ──────────────────────────────────────────────────────


@cli.command()
@click.argument("git_url")
@click.option("--alias", default=None, help="仓库别名（多仓库场景使用）")
def connect(git_url: str, alias: str | None):
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
    repo_alias = alias or "default"
    config.add_repo(repo_alias, git_url, str(repo_path))

    success(f"已成功连接到远程仓库 (别名: {repo_alias})。")


# ── init ─────────────────────────────────────────────────────────


@cli.command()
@click.argument("git_url")
@click.option("--alias", default=None, help="仓库别名")
def init(git_url: str, alias: str | None):
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
    repo_alias = alias or "default"
    config.add_repo(repo_alias, git_url, str(repo_path))

    success("skill 仓库初始化完成。")


# ── status ───────────────────────────────────────────────────────


@cli.command()
def status():
    """查看仓库连接状态和 skill 概览"""
    config = _get_config()
    all_repos = config.get_repos()

    if not all_repos:
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

    # 当前默认仓库
    current_url = config.get("repo.url")
    current_alias = None
    for a, r in all_repos.items():
        if r.get("url") == current_url:
            current_alias = a
            break

    # 多仓库列表
    if len(all_repos) > 1:
        console.print(repos_table(all_repos, current_alias))
        console.print()

    # 每个仓库的 skill 统计
    for repo_alias, repo_info in all_repos.items():
        cache_path = Path(repo_info.get("cache_path", ""))
        repo_url = repo_info.get("url", "")

        repo_label = f"[bold]URL:[/bold] {repo_url}"
        if len(all_repos) > 1:
            repo_label = f"[bold]别名:[/bold] {repo_alias}\n" + repo_label

        if cache_path.is_dir():
            skills_dir = cache_path / "skills"
            sm = _get_skill_manager(cache_path)
            skills = sm.discover_skills(skills_dir)

            repo_label += f"\n[bold]Skill 总数:[/bold] {len(skills)}"

            if skills:
                categories: dict[str, int] = {}
                for s in skills:
                    categories[s.category] = categories.get(s.category, 0) + 1
                cats_str = "  ".join(f"{cat}: {count}" for cat, count in sorted(categories.items()))
                repo_label += f"\n[bold]分类:[/bold] {cats_str}"
        else:
            repo_label += "\n[dim]Skill 总数: (缓存不可用)[/dim]"

        console.print(status_panel("仓库状态", repo_label))
        console.print()

    # 本地平台表格
    registry = PlatformRegistry()
    platform_data: list[tuple[str, bool, int]] = []
    for pc in registry.all():
        exists = pc.skills_dir.is_dir()
        installed = sum(1 for d in pc.skills_dir.iterdir() if d.is_dir()) if exists else 0
        platform_data.append((pc.label, exists, installed))

    console.print(platform_table(platform_data))


# ── search ───────────────────────────────────────────────────────


@cli.command()
@click.argument("keyword")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def search(keyword: str, from_alias: str | None):
    """搜索仓库中的 skill（按名称、描述、分类模糊匹配）"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
    skills_dir = cache_path / "skills"
    sm = _get_skill_manager(cache_path)

    available = sm.discover_skills(skills_dir)
    matched = sm.search_skills(available, keyword)

    if not matched:
        info(f"未找到匹配 '{keyword}' 的 skill。")
        return

    console.print(skill_table(matched, title=f"搜索结果: '{keyword}' ({len(matched)} 个)"))


# ── install ──────────────────────────────────────────────────────


@cli.command()
@click.option("--target", type=click.Choice(["claude", "codex", "kiro", "hermes"]), required=True,
              help="目标平台")
@click.option("--skill", default=None, help="要安装的 skill 名称")
@click.option("--all", "install_all", is_flag=True, help="安装所有 skill")
@click.option("--list", "list_skills", is_flag=True, help="列出可用 skill")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def install(target: str, skill: str | None, install_all: bool, list_skills: bool, from_alias: str | None):
    """从远程仓库安装 skill 到本地平台"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
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
@click.option("--source", type=click.Choice(["claude", "codex", "kiro", "hermes"]), required=True,
              help="来源平台")
@click.option("--skill", default=None, help="要上传的 skill 名称")
@click.option("--no-push", is_flag=True, help="仅本地 commit，不推送到远程")
@click.option("--category", default=None, help="skill 分类目录")
@click.option("--list", "list_skills", is_flag=True, help="列出本地可用 skill")
@click.option("--from", "from_alias", default=None, help="指定目标仓库别名")
def upload(source: str, skill: str | None, no_push: bool, category: str | None, list_skills: bool, from_alias: str | None):
    """上传本地 skill 到远程仓库"""
    _config, _repo_url, cache_path = _require_connected(from_alias)

    registry = PlatformRegistry()
    platform_config = registry.get(source)

    parser = MetadataParser()
    sm = _get_skill_manager(cache_path)
    local_skills = sm.list_installed(source)

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

    matched = [s for s in local_skills if s.metadata.name == skill or s.source_path.name == skill]

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

    cat = category or source_skill.category or "uncategorized"
    skill_name = source_skill.metadata.name
    dest = cache_path / "skills" / cat / skill_name

    is_update = dest.exists()
    with status_spinner("正在复制 skill 到仓库缓存 ..."):
        sm.copy_skill(source_skill.source_path, dest)

    action_label = "更新" if is_update else "新增"
    skill_version = source_skill.metadata.version or ""

    git = _get_git()
    commit_msg = git.build_skill_commit_message(
        action_label, skill_name,
        source=source, category=cat,
        description=source_skill.metadata.description,
        version=skill_version,
    )

    branch_mode = _get_branch_mode()
    git = _get_git()
    sm = _get_skill_manager(cache_path)

    if branch_mode == "branch" and not no_push:
        # 分支模式
        action_short = "update" if is_update else "add"
        with status_spinner("正在创建分支并提交 ..."):
            try:
                merged, branch_name = _upload_with_branch(
                    git, sm, cache_path, skill_name, commit_msg, action_short,
                )
            except RuntimeError as exc:
                error(f"Git 操作失败: {exc}")
                sys.exit(1)

        from skill_repo._console import upload_summary
        console.print()
        if merged:
            console.print(upload_summary(
                action_label, skill_name,
                source=source, category=cat,
                version=skill_version, pushed=True,
            ))
            success("已合并到主分支。")
        else:
            console.print(upload_summary(
                action_label, skill_name,
                source=source, category=cat,
                version=skill_version, pushed=True,
            ))
            warning(f"分支 {branch_name} 已推送，但无法自动合并。")
            info("请在 GitHub/GitLab 创建 Pull Request 合并到主分支。")
    else:
        # 直推模式
        pushed = False
        with status_spinner("正在提交到 Git ..."):
            try:
                git.add_commit_push(cache_path, commit_msg, push=not no_push)
                pushed = not no_push
            except RuntimeError as exc:
                err_msg = str(exc)
                if "push" in err_msg.lower():
                    warning(f"推送失败: {exc}")
                    info(f"skill 已提交到本地仓库，请手动推送:\n    cd {cache_path}\n    git push")
                else:
                    error(f"Git 操作失败: {exc}")
                    sys.exit(1)

        # 内置同步
        with status_spinner("正在同步生成文件 ..."):
            sync_result = sm.sync_all(cache_path)
        if any(sync_result.values()):
            try:
                git.add_commit_push(cache_path, "同步生成文件", push=pushed)
            except RuntimeError:
                pass

        from skill_repo._console import upload_summary
        console.print()
        console.print(upload_summary(
            action_label, skill_name,
            source=source, category=cat,
            version=skill_version, pushed=pushed,
        ))


# ── update ───────────────────────────────────────────────────────


@cli.command()
@click.option("--target", type=click.Choice(["claude", "codex", "kiro", "hermes"]), required=True,
              help="目标平台")
@click.option("--dry-run", is_flag=True, help="仅检查，不实际更新")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def update(target: str, dry_run: bool, from_alias: str | None):
    """更新本地已安装的 skill（从远程仓库拉取最新版本）"""
    _config, _repo_url, cache_path = _require_connected(from_alias)

    # 先 pull 最新
    git = _get_git()
    with status_spinner("正在拉取远程仓库最新内容 ..."):
        try:
            git.pull(cache_path)
        except RuntimeError as exc:
            warning(f"拉取失败: {exc}")

    skills_dir = cache_path / "skills"
    sm = _get_skill_manager(cache_path)

    new, updated, unchanged = sm.diff_skills(skills_dir, target)

    if not new and not updated:
        success("所有已安装的 skill 均为最新。")
        if unchanged:
            info(f"{len(unchanged)} 个 skill 无需更新。")
        return

    console.print(update_table(new, updated, unchanged))
    console.print()

    if dry_run:
        info(f"新增: {len(new)}  有更新: {len(updated)}  最新: {len(unchanged)}")
        info("使用不带 --dry-run 执行实际更新。")
        return

    to_install = updated  # 只更新有变化的，不自动安装新的
    if not to_install:
        success("无需更新。")
        return

    with status_spinner(f"正在更新 {len(to_install)} 个 skill ..."):
        for s in to_install:
            sm.install_skill(s, target)

    success(f"已更新 {len(to_install)} 个 skill 到 {target} 平台。")
    if new:
        info(f"另有 {len(new)} 个新 skill 可用，使用 [bold]skill-repo install[/bold] 安装。")


# ── remove ───────────────────────────────────────────────────────


@cli.command()
@click.option("--target", type=click.Choice(["claude", "codex", "kiro", "hermes"]), required=True,
              help="目标平台")
@click.option("--skill", required=True, help="要卸载的 skill 名称")
@click.option("--yes", "-y", is_flag=True, help="跳过确认提示")
def remove(target: str, skill: str, yes: bool):
    """从本地平台卸载 skill"""
    sm = _get_skill_manager()
    registry = PlatformRegistry()
    platform_config = registry.get(target)
    installed = sm.find_installed(skill, target)
    dest = installed.source_path if installed is not None else platform_config.skills_dir / skill

    if not dest.exists() and not dest.is_symlink():
        error(
            f"在 {target} 平台未找到名为 '{skill}' 的 skill。",
            hint=f"使用 [bold]skill-repo install --target {target} --list[/bold] 查看已安装 skill。",
        )
        sys.exit(1)

    # 展示即将删除的内容
    if dest.is_symlink():
        info(f"'{skill}' 是符号链接 → {dest.resolve()}")
    else:
        file_count = sum(1 for _ in dest.rglob("*") if _.is_file())
        info(f"将从 {platform_config.label} 卸载 '{skill}' ({file_count} 个文件)")
    info(f"路径: {dest}")

    if not yes:
        click.confirm("  确认卸载?", abort=True)

    removed = sm.remove_skill(skill, target)
    if removed:
        success(f"已从 {target} 平台卸载 skill '{skill}'。")
    else:
        error("卸载失败。")
        sys.exit(1)


# ── diff ─────────────────────────────────────────────────────────


@cli.command()
@click.option("--skill", required=True, help="要对比的 skill 名称")
@click.option("--target", type=click.Choice(["claude", "codex", "kiro", "hermes"]), required=True,
              help="本地平台")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def diff(skill: str, target: str, from_alias: str | None):
    """对比本地已安装 vs 远程仓库的 skill 差异"""
    _config, _repo_url, cache_path = _require_connected(from_alias)

    sm = _get_skill_manager(cache_path)
    registry = PlatformRegistry()
    platform_config = registry.get(target)

    installed = sm.find_installed(skill, target)
    local_dir = installed.source_path if installed is not None else platform_config.skills_dir / skill
    # 在远程仓库中查找 skill
    skills_dir = cache_path / "skills"
    available = sm.discover_skills(skills_dir)
    matched = [s for s in available if s.metadata.name == skill]

    remote_dir = matched[0].source_path if matched else None

    if not local_dir.exists() and not remote_dir:
        error(f"skill '{skill}' 在本地和远程仓库中均不存在。")
        sys.exit(1)

    if not local_dir.exists():
        info(f"skill '{skill}' 本地未安装，远程仓库中存在。")
        info("使用 [bold]skill-repo install[/bold] 安装。")
        return

    if not remote_dir:
        info(f"skill '{skill}' 仅存在于本地 {target} 平台，远程仓库中不存在。")
        info("使用 [bold]skill-repo upload[/bold] 上传到仓库。")
        return

    diff_lines = sm.diff_skill_content(local_dir, remote_dir)
    if not diff_lines:
        success(f"skill '{skill}' 本地与远程内容一致。")
        return

    console.print(f"\n  [bold]skill '{skill}' 差异:[/bold]  (本地 {target} vs 远程仓库)\n")
    for line in diff_lines:
        # 着色 diff 输出
        if line.lstrip().startswith("+") and not line.lstrip().startswith("+++"):
            console.print(f"  [green]{line}[/green]")
        elif line.lstrip().startswith("-") and not line.lstrip().startswith("---"):
            console.print(f"  [red]{line}[/red]")
        elif line.lstrip().startswith("@@"):
            console.print(f"  [cyan]{line}[/cyan]")
        else:
            console.print(f"  {line}")


# ── create ───────────────────────────────────────────────────────


@cli.command()
@click.option("--name", required=True, help="Skill 名称")
@click.option("--description", default="", help="Skill 描述")
@click.option("--author", default="", help="作者")
@click.option("--version", default="0.1.0", help="初始版本号")
@click.option("--target", type=click.Choice(["claude", "codex", "kiro", "hermes"]), default=None,
              help="直接创建到本地平台目录")
def create(name: str, description: str, author: str, version: str, target: str | None):
    """脚手架创建新 skill（自动生成 SKILL.md 模板）"""
    sm = _get_skill_manager()

    if target:
        registry = PlatformRegistry()
        platform_config = registry.get(target)
        target_dir = platform_config.skills_dir
    else:
        target_dir = Path.cwd()

    # 检查是否已存在
    if (target_dir / name).exists():
        error(f"目录 '{target_dir / name}' 已存在。")
        sys.exit(1)

    skill_dir = sm.create_skill(
        target_dir=target_dir,
        name=name,
        description=description,
        author=author,
        version=version,
    )

    success(f"已创建 skill '{name}' → {skill_dir}")
    info("编辑 SKILL.md 添加 prompt 内容，然后使用 [bold]skill-repo upload[/bold] 上传到仓库。")


# ── history ──────────────────────────────────────────────────────


@cli.command()
@click.option("--skill", required=True, help="Skill 名称")
@click.option("--limit", default=20, help="显示条数")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def history(skill: str, limit: int, from_alias: str | None):
    """查看 skill 的 Git 变更历史"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
    git = _get_git()

    skill_path = git.find_skill_path(cache_path, skill)
    if not skill_path:
        error(
            f"在仓库中未找到名为 '{skill}' 的 skill。",
            hint="使用 [bold]skill-repo install --list[/bold] 查看可用 skill。",
        )
        sys.exit(1)

    commits = git.skill_log(cache_path, skill_path, max_count=limit)
    if not commits:
        info(f"skill '{skill}' 暂无变更历史。")
        return

    console.print(history_table(commits, title=f"'{skill}' 变更历史"))
    console.print()
    info(f"共 {len(commits)} 条记录 (路径: {skill_path})")
    info("使用 [bold]skill-repo rollback --skill <name> --to <commit>[/bold] 回退到指定版本。")


# ── rollback ─────────────────────────────────────────────────────


@cli.command()
@click.option("--skill", required=True, help="Skill 名称")
@click.option("--to", "commit_hash", required=True, help="目标 commit hash（完整或短 hash）")
@click.option("--push", is_flag=True, help="回退后自动提交并推送")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def rollback(skill: str, commit_hash: str, push: bool, from_alias: str | None):
    """将仓库中的 skill 回退到指定 Git 版本"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
    git = _get_git()

    skill_path = git.find_skill_path(cache_path, skill)
    if not skill_path:
        error(f"在仓库中未找到名为 '{skill}' 的 skill。")
        sys.exit(1)

    # 验证 commit 存在
    commits = git.skill_log(cache_path, skill_path, max_count=100)
    matched_commit = None
    for c in commits:
        if c.hash.startswith(commit_hash) or c.short_hash == commit_hash:
            matched_commit = c
            break

    if not matched_commit:
        error(
            f"未找到 commit '{commit_hash}'。",
            hint=f"使用 [bold]skill-repo history --skill {skill}[/bold] 查看可用版本。",
        )
        sys.exit(1)

    info(f"将回退 '{skill}' 到: {matched_commit.short_hash} ({matched_commit.date}) {matched_commit.message}")
    click.confirm("  确认回退?", abort=True)

    with status_spinner(f"正在回退 '{skill}' 到 {matched_commit.short_hash} ..."):
        try:
            git.restore_skill(cache_path, skill_path, matched_commit.hash)
        except RuntimeError as exc:
            error(f"回退失败: {exc}")
            sys.exit(1)

    success(f"已将 '{skill}' 回退到 {matched_commit.short_hash}。")

    if push:
        commit_msg = git.build_skill_commit_message(
            "回退", skill,
            description=f"→ {matched_commit.short_hash} ({matched_commit.message})",
        )
        with status_spinner("正在提交并推送 ..."):
            try:
                git.add_commit_push(cache_path, commit_msg, push=True)
            except RuntimeError as exc:
                warning(f"推送失败: {exc}")
                info("回退已在本地生效，请手动 git push。")
                return
        success("已提交并推送到远程仓库。")
    else:
        info("回退仅在本地缓存生效。使用 --push 提交到远程，或手动 git add/commit/push。")


# ── pin ──────────────────────────────────────────────────────────


@cli.command()
@click.option("--skill", required=True, help="Skill 名称")
@click.option("--commit", "commit_hash", default=None, help="锁定到指定 commit（默认当前 HEAD）")
@click.option("--target", type=click.Choice(["claude", "codex", "kiro", "hermes"]), required=True,
              help="目标平台")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def pin(skill: str, commit_hash: str | None, target: str, from_alias: str | None):
    """安装指定 Git 版本的 skill 到本地平台（版本锁定）"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
    git = _get_git()

    skill_path = git.find_skill_path(cache_path, skill)
    if not skill_path:
        error(f"在仓库中未找到名为 '{skill}' 的 skill。")
        sys.exit(1)

    if commit_hash:
        # 验证 commit 存在
        commits = git.skill_log(cache_path, skill_path, max_count=100)
        matched = None
        for c in commits:
            if c.hash.startswith(commit_hash) or c.short_hash == commit_hash:
                matched = c
                break
        if not matched:
            error(
                f"未找到 commit '{commit_hash}'。",
                hint=f"使用 [bold]skill-repo history --skill {skill}[/bold] 查看可用版本。",
            )
            sys.exit(1)
        info(f"锁定版本: {matched.short_hash} ({matched.date}) {matched.message}")

        # 获取该 commit 时的 skill 内容到临时目录
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / skill
            tmp_path.mkdir(parents=True)
            # 用 git archive 提取指定 commit 的 skill 目录
            try:
                import tarfile
                import io
                archive_result = subprocess.run(
                    ["git", "archive", matched.hash, "--", skill_path],
                    cwd=cache_path, check=True, capture_output=True,
                )
                tar = tarfile.open(fileobj=io.BytesIO(archive_result.stdout))
                tar.extractall(path=tmpdir)
                tar.close()
            except (RuntimeError, subprocess.CalledProcessError) as exc:
                error(f"提取历史版本失败: {exc}")
                sys.exit(1)

            # 从提取的目录安装
            extracted = Path(tmpdir) / skill_path
            if not extracted.is_dir():
                error("提取的 skill 目录不存在。")
                sys.exit(1)

            sm = _get_skill_manager(cache_path)
            from skill_repo.metadata import SkillInfo
            parser = MetadataParser()
            skill_md = extracted / "SKILL.md"
            if skill_md.exists():
                metadata = parser.parse(skill_md)
            else:
                from skill_repo.metadata import SkillMetadata
                metadata = SkillMetadata(name=skill, description="")
            skill_info = SkillInfo(metadata=metadata, category="pinned", source_path=extracted)

            with status_spinner(f"正在安装 {skill}@{matched.short_hash} 到 {target} ..."):
                sm.install_skill(skill_info, target)

        success(f"已安装 '{skill}' @ {matched.short_hash} 到 {target} 平台。")
    else:
        # 无 commit 指定，安装当前 HEAD 版本
        sm = _get_skill_manager(cache_path)
        skills_dir = cache_path / "skills"
        available = sm.discover_skills(skills_dir)
        matched_skills = [s for s in available if s.metadata.name == skill]
        if not matched_skills:
            error(f"未找到名为 '{skill}' 的 skill。")
            sys.exit(1)

        with status_spinner(f"正在安装 {skill} (HEAD) 到 {target} ..."):
            sm.install_skill(matched_skills[0], target)

        # 获取当前 HEAD hash
        try:
            head_result = GitManager._run_git(["rev-parse", "--short", "HEAD"], cwd=cache_path)
            head_hash = head_result.stdout.strip()
        except RuntimeError:
            head_hash = "HEAD"

        success(f"已安装 '{skill}' @ {head_hash} 到 {target} 平台。")


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


# ── branch 子命令组 ──────────────────────────────────────────────


@cli.group()
def branch():
    """分支协作管理"""


@branch.command("list")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def branch_list(from_alias: str | None):
    """查看待合并的 skill 分支"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
    git = _get_git()

    branches = git.list_skill_branches(cache_path)
    if not branches:
        info("没有待合并的 skill 分支。")
        return

    from rich.table import Table
    t = Table(title="[bold]Skill 分支[/bold]", border_style="cyan", pad_edge=True)
    t.add_column("分支", style="bold")
    t.add_column("日期", style="dim", width=12)
    t.add_column("说明", max_width=44)
    for b in branches:
        t.add_row(b.name, b.last_date, b.last_commit)
    console.print(t)
    console.print()
    info(f"共 {len(branches)} 个待合并分支。")
    info("使用 [bold]skill-repo branch merge <branch-name>[/bold] 合并到主分支。")


@branch.command("merge")
@click.argument("branch_name")
@click.option("--from", "from_alias", default=None, help="指定仓库别名")
def branch_merge(branch_name: str, from_alias: str | None):
    """合并指定分支到主分支"""
    _config, _repo_url, cache_path = _require_connected(from_alias)
    git = _get_git()
    sm = _get_skill_manager(cache_path)

    # 先 checkout 到 main
    with status_spinner(f"正在合并 {branch_name} ..."):
        merged = git.try_merge_to_main(cache_path, branch_name)

    if not merged:
        error(f"分支 {branch_name} 无法自动合并（存在冲突）。")
        info("请手动解决冲突后合并，或在 GitHub/GitLab 创建 PR。")
        sys.exit(1)

    # 同步生成文件
    with status_spinner("正在同步生成文件 ..."):
        sync_result = sm.sync_all(cache_path)
    if any(sync_result.values()):
        try:
            git.add_commit_push(cache_path, "同步生成文件", push=False)
        except RuntimeError:
            pass

    with status_spinner("正在推送 ..."):
        try:
            git.push_main(cache_path)
        except RuntimeError as exc:
            warning(f"推送失败: {exc}")
            info("合并已在本地完成，请手动 git push。")
            return

    # 清理远程分支
    config = _get_config()
    if config.get("branch.cleanup") != "false":
        git.delete_remote_branch(cache_path, branch_name)

    success(f"已合并 {branch_name} 到主分支并推送。")


@branch.command("mode")
@click.argument("mode", type=click.Choice(["direct", "branch"]))
def branch_mode(mode: str):
    """切换分支模式（direct=直推 / branch=分支协作）"""
    config = _get_config()
    config.set("branch.mode", mode)
    label = "直推模式" if mode == "direct" else "分支协作模式"
    success(f"已切换到 {label}。")
    if mode == "branch":
        info("上传 skill 时将自动创建个人分支，无冲突时自动合并到主分支。")


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
    """生成/更新 prek.toml 并安装 Git Hook"""
    if not _check_prek_installed():
        return

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

    # 实际安装 git hook
    with status_spinner("正在安装 Git Hook ..."):
        try:
            subprocess.run(
                ["prek", "install"],
                cwd=str(cache_path),
                check=True,
                capture_output=True,
                text=True,
            )
            success("Git Hook 已安装。每次 commit 后会自动同步生成文件。")
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            warning(f"Hook 安装失败: {stderr}")
            info("请手动在仓库目录运行: prek install")


@prek.command("run")
def prek_run():
    """手动触发同步（生成 README、commands、manifest）"""
    _config, _repo_url, cache_path = _require_connected()

    sm = _get_skill_manager(cache_path)
    with status_spinner("正在同步生成文件 ..."):
        result = sm.sync_all(cache_path)

    changed = [k for k, v in result.items() if v]
    if not changed:
        success("所有生成文件均为最新。")
    else:
        for name in changed:
            label = {"skills_readme": "skills/README.md", "commands": "commands/*.md", "manifest": "manifest.json"}.get(name, name)
            success(f"已更新 {label}")
        info("使用 git commit/push 提交变更，或重新运行 upload 自动提交。")


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
