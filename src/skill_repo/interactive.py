"""交互式 TUI 模式 - 使用 rich + questionary 实现美观的菜单式交互

优化点:
- 分组菜单（7 项主菜单，版本管理收为子菜单）
- 操作完成后 "按 Enter 继续" 替代强制 select
- 首次清屏，后续用分隔线
- 概览只展示摘要
- 默认平台支持
- Esc 取消用 sentinel 区分 None 值
- 搜索结果可直接安装
- 错误后提供恢复建议
"""

from __future__ import annotations

import os
from pathlib import Path

import questionary
from questionary import Style
from rich.panel import Panel

from skill_repo._console import (
    console,
    error,
    history_table,
    repos_table,
    skill_table,
    status_spinner,
    success,
    update_table,
    warning,
    info,
)
from skill_repo.config_manager import ConfigManager
from skill_repo.git_manager import GitManager
from skill_repo.metadata import MetadataParser, SkillInfo
from skill_repo.platforms import PlatformRegistry
from skill_repo.services import RepoConnection, list_repo_connections, resolve_repo, upload_skills_to_repo
from skill_repo.skill_manager import SkillManager

# ── sentinel 值：区分 Esc 取消 vs 选择了 None ────────────────────
_CANCELLED = object()

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
    repo = resolve_repo(config, require_cache=True)
    if repo is None:
        return None
    return repo.url, repo.cache_path


def _pick_repo(prompt: str = "选择仓库:") -> RepoConnection | None:
    """Pick a connected repo, prompting only when more than one is available."""
    config = _get_config()
    repos = list_repo_connections(config, require_cache=True)
    if not repos:
        _not_connected_msg()
        return None
    if len(repos) == 1:
        return repos[0]

    choices = [
        questionary.Choice(
            title=f"{repo.alias}  {repo.url}" + ("  (当前)" if repo.is_current else ""),
            value=repo,
        )
        for repo in repos
    ]
    selected = _ask(questionary.select(prompt, choices=choices, style=_QS, instruction="(Esc 返回)"))
    if selected is _CANCELLED:
        return None
    return selected


def _ask(prompt_fn):
    """Wrap a questionary prompt — return _CANCELLED on Esc/Ctrl+C."""
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
        return _CANCELLED


def _pause() -> None:
    """操作完成后暂停，按 Enter 继续。"""
    console.print()
    console.input("  [dim]按 Enter 返回主菜单...[/dim]")


def _separator() -> None:
    """主菜单前的分隔线（替代清屏）。"""
    console.print()
    console.rule(style="dim")
    console.print()


def _banner(first_time: bool = False) -> None:
    if first_time:
        os.system("cls" if os.name == "nt" else "clear")
    else:
        _separator()
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


def _default_platform() -> str | None:
    """读取默认平台配置。"""
    config = _get_config()
    return config.get("defaults.target_platform")


def _skill_choice_label(s: SkillInfo) -> str:
    """生成 questionary Choice 的纯文本标签：名称 (分类) — 描述"""
    desc = s.metadata.description or ""
    if len(desc) > 40:
        desc = desc[:38] + "…"
    if desc:
        return f"{s.metadata.name}  ({s.category}) — {desc}"
    return f"{s.metadata.name}  ({s.category})"


def _pick_platform(prompt: str = "选择平台:") -> str | None:
    """选择平台，支持默认值。返回平台 name 或 None（取消）。"""
    registry = PlatformRegistry()
    platforms = registry.all()
    default = _default_platform()

    # 如果有默认值，放在第一个并标注
    names = []
    for pc in platforms:
        label = pc.label
        if pc.name == default:
            label += " (默认)"
        names.append(label)

    # 默认选中项
    default_label = None
    for pc, label in zip(platforms, names):
        if pc.name == default:
            default_label = label
            break

    result = _ask(questionary.select(
        prompt,
        choices=names,
        default=default_label,
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if result is _CANCELLED:
        return None
    # 从 label 还原 platform name
    for pc, label in zip(platforms, names):
        if label == result:
            return pc.name
    return None


# ── actions ──────────────────────────────────────────────────────

def _action_overview() -> None:
    """概览 — 只展示摘要，不信息过载"""
    conn = _get_connected_repo()

    if conn:
        url, cache_path = conn
        sm = _get_skill_manager(cache_path)
        skills = sm.discover_skills(cache_path / "skills")

        # 分类统计
        cats: dict[str, int] = {}
        for s in skills:
            cats[s.category] = cats.get(s.category, 0) + 1
        cats_str = "  ".join(f"{c}: {n}" for c, n in sorted(cats.items())) if cats else "无"

        repo_info = (
            f"[bold]仓库:[/bold] {url}\n"
            f"[bold]Skill 总数:[/bold] {len(skills)}\n"
            f"[bold]分类:[/bold] {cats_str}"
        )
        console.print(Panel(repo_info, title="[bold]远程仓库[/bold]", border_style="cyan", padding=(0, 2)))
    else:
        _not_connected_msg()

    # 本地平台摘要
    console.print()
    registry = PlatformRegistry()
    local_sm = _get_skill_manager()
    for pc in registry.all():
        if not pc.skills_dir.is_dir():
            console.print(f"  [bold]{pc.label}[/bold]  [dim]— 未安装[/dim]")
            continue
        count = len(local_sm.list_installed(pc.name))
        console.print(f"  [bold]{pc.label}[/bold]  [success]{count}[/success] 个 skill")

    # 提供展开详情的选项
    console.print()
    action = _ask(questionary.select(
        "查看详情:",
        choices=["查看远程仓库 Skill 列表", "查看某个平台的本地 Skill", "← 返回"],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if action is _CANCELLED or action == "← 返回":
        return

    if action == "查看远程仓库 Skill 列表":
        if conn:
            _url, cache_path = conn
            sm = _get_skill_manager(cache_path)
            skills = sm.discover_skills(cache_path / "skills")
            if skills:
                console.print(skill_table(skills, title="远程仓库 Skill"))
            else:
                warning("仓库中暂无 skill")
        else:
            _not_connected_msg()
    elif action == "查看某个平台的本地 Skill":
        platform_name = _pick_platform("查看哪个平台?")
        if platform_name is None:
            return
        pc = registry.get(platform_name)
        if not pc.skills_dir.is_dir():
            warning(f"{pc.label} 目录不存在")
            return
        local_skills = local_sm.list_installed(platform_name)
        if local_skills:
            console.print(skill_table(local_skills, title=f"{pc.label} 本地 Skill"))
        else:
            warning(f"{pc.label} 暂无 skill")


def _action_install() -> None:
    """安装 skill（仓库 → 本地）"""
    repo = _pick_repo("从哪个仓库安装?")
    if repo is None:
        return

    cache_path = repo.cache_path
    sm = _get_skill_manager(cache_path)
    available = sm.discover_skills(cache_path / "skills")

    if not available:
        warning("仓库中暂无 skill")
        return

    # 选平台（支持默认值）
    platform_name = _pick_platform("安装到哪个平台?")
    if platform_name is None:
        return

    # 先展示可用 skill 列表（含描述）
    console.print(skill_table(available, title="可用 Skill"))
    console.print()

    # 选 skill — 名称 + 截短描述
    choices = [
        questionary.Choice(
            title=_skill_choice_label(s),
            value=i,
        )
        for i, s in enumerate(available)
    ]
    selected = _ask(questionary.checkbox(
        "选择要安装的 skill (Space 选择, Enter 确认):",
        choices=choices,
        style=_QS,
    ))
    if selected is _CANCELLED or not selected:
        console.print("  [dim]已取消[/dim]")
        return

    # 展示选中的 skill 详情
    console.print()
    for idx in selected:
        s = available[idx]
        console.print(f"  • {s.metadata.name} — {s.metadata.description or '无描述'}")
    console.print()

    with status_spinner(f"正在安装 {len(selected)} 个 skill ..."):
        for idx in selected:
            sm.install_skill(available[idx], platform_name)

    for idx in selected:
        success(available[idx].metadata.name)
    console.print(f"\n  [success]已安装 {len(selected)} 个 skill 到 {platform_name}[/success]")


def _action_upload() -> None:
    """上传 skill（本地 → 仓库）— 支持多选批量上传"""
    repo = _pick_repo("上传到哪个仓库?")
    if repo is None:
        return

    cache_path = repo.cache_path
    registry = PlatformRegistry()
    parser = MetadataParser()
    sm = _get_skill_manager(cache_path)

    # 选来源平台
    platform_name = _pick_platform("从哪个平台上传?")
    if platform_name is None:
        return
    source = registry.get(platform_name)

    # 扫描本地 skill
    local_skills = sm.list_installed(platform_name)

    if not local_skills:
        warning(f"{source.label} 平台暂无 skill")
        return

    # 多选 skill
    choices = [
        questionary.Choice(
            title=f"{s.metadata.name}  {s.metadata.description or ''}",
            value=i,
        )
        for i, s in enumerate(local_skills)
    ]
    selected_indices = _ask(questionary.checkbox(
        "选择要上传的 skill (Space 选择, Enter 确认):",
        choices=choices,
        style=_QS,
    ))
    if selected_indices is _CANCELLED or not selected_indices:
        console.print("  [dim]已取消[/dim]")
        return

    selected_skills = [local_skills[i] for i in selected_indices]

    # 验证所有选中的 skill
    invalid: list[tuple[str, list[str]]] = []
    valid_skills: list[SkillInfo] = []
    for skill in selected_skills:
        errors = parser.validate(skill.source_path)
        if errors:
            invalid.append((skill.metadata.name, errors))
        else:
            valid_skills.append(skill)

    if invalid:
        warning("以下 skill 元数据不完整，将跳过:")
        for name, errs in invalid:
            console.print(f"    [bold]{name}[/bold]:")
            for e in errs:
                console.print(f"      [error]•[/error] {e}")
        console.print()
        if not valid_skills:
            info("没有可上传的 skill，请补充 SKILL.md 元数据后重试。")
            return
        info(f"将上传 {len(valid_skills)} 个有效 skill。")
        console.print()

    # 选分类（统一分类）
    skills_dir = cache_path / "skills"
    cats = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))) if skills_dir.is_dir() else []
    if not cats:
        cats = ["uncategorized"]
    cat_choices = cats + ["+ 新建分类"]

    cat = _ask(questionary.select("选择分类:", choices=cat_choices, style=_QS, instruction="(Esc 返回)"))
    if cat is _CANCELLED:
        return
    if cat == "+ 新建分类":
        cat = _ask(questionary.text("输入分类名:", style=_QS))
        if cat is _CANCELLED or not cat or not cat.strip():
            return
        cat = cat.strip()

    # 展示上传计划
    console.print()
    for skill in valid_skills:
        dest = cache_path / "skills" / cat / skill.metadata.name
        tag = "[warning]更新[/warning]" if dest.exists() else "[info]新增[/info]"
        console.print(f"  {tag} {skill.metadata.name}")
    console.print()

    ok = _ask(questionary.confirm(f"确认上传 {len(valid_skills)} 个 skill 到 '{cat}' 分类?", default=True, style=_QS))
    if ok is _CANCELLED or not ok:
        return

    git = _get_git()
    config = _get_config()
    with status_spinner("正在提交、推送并同步生成文件 ..."):
        try:
            result = upload_skills_to_repo(
                git=git,
                skill_manager=sm,
                config=config,
                cache_path=cache_path,
                source=source.name,
                skills=valid_skills,
                category=cat,
            )
        except RuntimeError as exc:
            if "push" in str(exc).lower():
                warning(f"推送失败: {exc}")
                info("skill 已提交到本地仓库，请手动 git push。")
            else:
                error(f"Git 错误: {exc}")
            return

    console.print()
    for item in result.items:
        success(f"{item.action_label} {item.skill_name}")

    from skill_repo._console import upload_summary
    if len(result.items) == 1:
        item = result.items[0]
        console.print()
        console.print(upload_summary(
            item.action_label, item.skill_name,
            source=source.name, category=cat,
            version=item.version, pushed=result.pushed,
        ))
    else:
        console.print()
        status_text = "[success]已推送到远程[/success]" if result.pushed else "[warning]仅本地提交[/warning]"
        console.print(f"  批量上传 {len(result.items)} 个 skill 到 [cyan]{cat}[/cyan] 分类  {status_text}")

    if result.branch_name and result.merged:
        success("已合并到主分支。")
    elif result.branch_name:
        warning(f"分支 {result.branch_name} 已推送，无法自动合并。")
        info("请在 GitHub/GitLab 创建 Pull Request 合并到主分支。")


def _action_search() -> None:
    """搜索 skill — 支持本地和远程，搜索结果可直接操作"""
    # 选择搜索范围
    scope = _ask(questionary.select(
        "搜索范围:",
        choices=["🌐  远程仓库", "💻  本地已安装", "🔎  全部（远程 + 本地）"],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if scope is _CANCELLED:
        return

    keyword = _ask(questionary.text("搜索关键词:", style=_QS))
    if keyword is _CANCELLED or not keyword or not keyword.strip():
        return
    keyword = keyword.strip()

    repo = _pick_repo("使用哪个远程仓库搜索?") if scope in ("🌐  远程仓库", "🔎  全部（远程 + 本地）") else None
    sm_remote = _get_skill_manager(repo.cache_path) if repo else None
    registry = PlatformRegistry()
    local_sm = _get_skill_manager()

    remote_matched: list[SkillInfo] = []
    local_matched: list[tuple[str, SkillInfo]] = []  # (platform_name, skill)

    # 远程搜索
    if scope in ("🌐  远程仓库", "🔎  全部（远程 + 本地）"):
        if repo and sm_remote:
            cache_path = repo.cache_path
            available = sm_remote.discover_skills(cache_path / "skills")
            remote_matched = sm_remote.search_skills(available, keyword)
        elif scope == "🌐  远程仓库":
            return

    # 本地搜索
    if scope in ("💻  本地已安装", "🔎  全部（远程 + 本地）"):
        for pc in registry.all():
            if not pc.skills_dir.is_dir():
                continue
            for si in local_sm.list_installed(pc.name):
                kw = keyword.lower()
                if (kw in si.metadata.name.lower()
                        or kw in (si.metadata.description or "").lower()
                        or kw in si.category.lower()):
                    local_matched.append((pc.name, si))

    # 展示结果
    has_results = False

    if remote_matched:
        has_results = True
        console.print(skill_table(remote_matched, title=f"远程仓库匹配: '{keyword}' ({len(remote_matched)} 个)"))
        console.print()

    if local_matched:
        has_results = True
        # 按平台分组展示
        by_platform: dict[str, list[SkillInfo]] = {}
        for pname, si in local_matched:
            by_platform.setdefault(pname, []).append(si)
        for pname, skills in by_platform.items():
            pc = registry.get(pname)
            console.print(skill_table(skills, title=f"{pc.label} 本地匹配 ({len(skills)} 个)"))
            console.print()

    if not has_results:
        console.print(f"  [dim]未找到匹配 '{keyword}' 的 skill[/dim]")
        return

    # 后续操作
    actions = []
    if remote_matched:
        actions.append("📥  安装远程搜索结果")
    if local_matched and repo:
        actions.append("📤  上传本地搜索结果")
    actions.append("← 返回")

    action = _ask(questionary.select(
        "操作:",
        choices=actions,
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if action is _CANCELLED or action == "← 返回":
        return

    if action == "📥  安装远程搜索结果":
        platform_name = _pick_platform("安装到哪个平台?")
        if platform_name is None:
            return
        choices = [
            questionary.Choice(title=s.metadata.name, value=i)
            for i, s in enumerate(remote_matched)
        ]
        selected = _ask(questionary.checkbox(
            "选择要安装的 skill:",
            choices=choices,
            style=_QS,
        ))
        if selected is _CANCELLED or not selected:
            return
        with status_spinner(f"正在安装 {len(selected)} 个 skill ..."):
            for idx in selected:
                sm_remote.install_skill(remote_matched[idx], platform_name)
        for idx in selected:
            success(remote_matched[idx].metadata.name)

    elif action == "📤  上传本地搜索结果" and repo:
        cache_path = repo.cache_path
        # 选分类
        skills_dir = cache_path / "skills"
        cats = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))) if skills_dir.is_dir() else []
        if not cats:
            cats = ["uncategorized"]
        cat_choices = cats + ["+ 新建分类"]
        cat = _ask(questionary.select("选择分类:", choices=cat_choices, style=_QS))
        if cat is _CANCELLED:
            return
        if cat == "+ 新建分类":
            cat = _ask(questionary.text("输入分类名:", style=_QS))
            if cat is _CANCELLED or not cat or not cat.strip():
                return
            cat = cat.strip()

        all_local = local_matched
        choices = [
            questionary.Choice(title=f"{pname}: {s.metadata.name}", value=i)
            for i, (pname, s) in enumerate(all_local)
        ]
        selected = _ask(questionary.checkbox(
            "选择要上传的 skill:",
            choices=choices,
            style=_QS,
        ))
        if selected is _CANCELLED or not selected:
            return

        selected_pairs = [all_local[idx] for idx in selected]
        invalid: list[tuple[str, list[str]]] = []
        valid_pairs: list[tuple[str, SkillInfo]] = []
        parser = MetadataParser()
        for pname, skill in selected_pairs:
            errs = parser.validate(skill.source_path)
            if errs:
                invalid.append((skill.metadata.name, errs))
            else:
                valid_pairs.append((pname, skill))

        if invalid:
            warning("以下 skill 元数据不完整，将跳过:")
            for name, errs in invalid:
                console.print(f"    [bold]{name}[/bold]:")
                for e in errs:
                    console.print(f"      [error]•[/error] {e}")
            if not valid_pairs:
                return

        sm = _get_skill_manager(cache_path)
        git = _get_git()
        config = _get_config()
        source_names = {pname for pname, _skill in valid_pairs}
        source_name = next(iter(source_names)) if len(source_names) == 1 else "mixed"
        skills = [skill for _pname, skill in valid_pairs]
        with status_spinner(f"正在上传 {len(skills)} 个 skill ..."):
            try:
                result = upload_skills_to_repo(
                    git=git,
                    skill_manager=sm,
                    config=config,
                    cache_path=cache_path,
                    source=source_name,
                    skills=skills,
                    category=cat,
                )
            except RuntimeError as exc:
                warning(f"推送失败: {exc}")
                return
        for item in result.items:
            success(f"{item.action_label} {item.skill_name}")
        if result.branch_name and not result.merged:
            warning(f"分支 {result.branch_name} 已推送，无法自动合并。")


def _action_update() -> None:
    """更新已安装的 skill"""
    repo = _pick_repo("从哪个仓库更新?")
    if repo is None:
        return

    cache_path = repo.cache_path

    platform_name = _pick_platform("更新哪个平台的 skill?")
    if platform_name is None:
        return

    git = _get_git()
    with status_spinner("正在拉取远程仓库最新内容 ..."):
        try:
            git.pull(cache_path)
        except RuntimeError as exc:
            warning(f"拉取失败: {exc}")

    sm = _get_skill_manager(cache_path)
    new, updated, unchanged = sm.diff_skills(cache_path / "skills", platform_name)

    if not new and not updated:
        success("所有已安装的 skill 均为最新。")
        return

    console.print(update_table(new, updated, unchanged))
    console.print()

    if not updated:
        console.print("  [dim]无需更新的 skill[/dim]")
        if new:
            info(f"有 {len(new)} 个新 skill 可用，使用「安装 Skill」菜单安装。")
        return

    ok = _ask(questionary.confirm(f"更新 {len(updated)} 个 skill?", default=True, style=_QS))
    if ok is _CANCELLED or not ok:
        return

    with status_spinner(f"正在更新 {len(updated)} 个 skill ..."):
        for s in updated:
            sm.install_skill(s, platform_name)

    success(f"已更新 {len(updated)} 个 skill。")
    if new:
        info(f"另有 {len(new)} 个新 skill 可用。")


def _action_remove() -> None:
    """卸载 skill"""
    platform_name = _pick_platform("从哪个平台卸载?")
    if platform_name is None:
        return

    sm = _get_skill_manager()
    installed = sm.list_installed(platform_name)

    if not installed:
        registry = PlatformRegistry()
        pc = registry.get(platform_name)
        warning(f"{pc.label} 平台暂无已安装的 skill")
        return

    choices = [
        questionary.Choice(
            title=f"{s.metadata.name}  {s.metadata.description or ''}",
            value=s.metadata.name,
        )
        for s in installed
    ]
    selected = _ask(questionary.checkbox(
        "选择要卸载的 skill (Space 选择, Enter 确认):",
        choices=choices,
        style=_QS,
    ))
    if selected is _CANCELLED or not selected:
        console.print("  [dim]已取消[/dim]")
        return

    # 展示即将卸载的内容
    console.print()
    for name in selected:
        console.print(f"  [warning]•[/warning] {name}")
    console.print()

    ok = _ask(questionary.confirm(f"确认卸载 {len(selected)} 个 skill?", default=False, style=_QS))
    if ok is _CANCELLED or not ok:
        return

    for name in selected:
        sm.remove_skill(name, platform_name)
        success(f"已卸载 {name}")


def _action_version_mgmt() -> None:
    """版本管理 — 子菜单：变更历史 + 回退 + 版本锁定安装"""
    repo = _pick_repo("使用哪个仓库做版本管理?")
    if repo is None:
        return

    action = _ask(questionary.select(
        "版本管理:",
        choices=["📜  查看变更历史", "📌  安装指定版本", "← 返回"],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if action is _CANCELLED or action == "← 返回":
        return

    if action == "📜  查看变更历史":
        _sub_history(repo)
    elif action == "📌  安装指定版本":
        _sub_pin_install(repo)


def _sub_history(repo: RepoConnection) -> None:
    """变更历史 + 可选回退"""
    cache_path = repo.cache_path
    git = _get_git()
    sm = _get_skill_manager(cache_path)
    available = sm.discover_skills(cache_path / "skills")

    if not available:
        warning("仓库中暂无 skill")
        return

    skill_name = _ask(questionary.select(
        "查看哪个 skill 的历史?",
        choices=[s.metadata.name for s in available],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if skill_name is _CANCELLED:
        return

    skill_path = git.find_skill_path(cache_path, skill_name)
    if not skill_path:
        error(f"未找到 '{skill_name}' 的路径")
        return

    commits = git.skill_log(cache_path, skill_path, max_count=20)
    if not commits:
        console.print(f"  [dim]'{skill_name}' 暂无变更历史[/dim]")
        return

    console.print(history_table(commits, title=f"'{skill_name}' 变更历史"))
    console.print(f"  [dim]共 {len(commits)} 条记录[/dim]")

    # 后续操作
    action = _ask(questionary.select(
        "操作:",
        choices=["⏪  回退到某个版本", "← 返回"],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if action is _CANCELLED or action == "← 返回":
        return

    commit_choices = [
        questionary.Choice(
            title=f"{c.short_hash}  {c.date}  {c.author}  {c.message}",
            value=c,
        )
        for c in commits
    ]
    selected_commit = _ask(questionary.select(
        "回退到哪个版本?",
        choices=commit_choices,
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if selected_commit is _CANCELLED:
        return

    ok = _ask(questionary.confirm(
        f"确认回退 '{skill_name}' 到 {selected_commit.short_hash}?",
        default=False, style=_QS,
    ))
    if ok is _CANCELLED or not ok:
        return

    with status_spinner(f"正在回退 '{skill_name}' ..."):
        try:
            git.restore_skill(cache_path, skill_path, selected_commit.hash)
        except RuntimeError as exc:
            error(f"回退失败: {exc}")
            return

    success(f"已回退 '{skill_name}' 到 {selected_commit.short_hash}")

    push = _ask(questionary.confirm("推送到远程仓库?", default=True, style=_QS))
    if push is _CANCELLED:
        return
    if push:
        msg = git.build_skill_commit_message(
            "回退", skill_name,
            description=f"→ {selected_commit.short_hash} ({selected_commit.message})",
        )
        with status_spinner("正在提交并推送 ..."):
            try:
                git.add_commit_push(cache_path, msg, push=True)
            except RuntimeError as exc:
                warning(f"推送失败: {exc}")
                info("回退已在本地生效，请手动 git push。")
                return
        success("已推送到远程仓库")
    else:
        info("回退仅在本地缓存生效。")


def _sub_pin_install(repo: RepoConnection) -> None:
    """安装指定历史版本"""
    cache_path = repo.cache_path
    git = _get_git()
    sm = _get_skill_manager(cache_path)
    available = sm.discover_skills(cache_path / "skills")

    if not available:
        warning("仓库中暂无 skill")
        return

    skill_name = _ask(questionary.select(
        "选择 skill:",
        choices=[s.metadata.name for s in available],
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if skill_name is _CANCELLED:
        return

    skill_path = git.find_skill_path(cache_path, skill_name)
    if not skill_path:
        error(f"未找到 '{skill_name}' 的路径")
        return

    commits = git.skill_log(cache_path, skill_path, max_count=20)

    # 选版本
    version_choices = [questionary.Choice(title="最新版本 (HEAD)", value="HEAD")]
    if commits:
        for c in commits:
            version_choices.append(questionary.Choice(
                title=f"{c.short_hash}  {c.date}  {c.message}",
                value=c,
            ))

    selected = _ask(questionary.select(
        "安装哪个版本?",
        choices=version_choices,
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if selected is _CANCELLED:
        return

    # 选平台
    platform_name = _pick_platform("安装到哪个平台?")
    if platform_name is None:
        return

    if selected == "HEAD":
        matched_skills = [s for s in available if s.metadata.name == skill_name]
        if matched_skills:
            with status_spinner(f"正在安装 {skill_name} (最新) ..."):
                sm.install_skill(matched_skills[0], platform_name)
            success(f"已安装 '{skill_name}' (最新) 到 {platform_name}")
    else:
        import subprocess
        import tempfile
        import tarfile
        import io

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                archive_result = subprocess.run(
                    ["git", "archive", selected.hash, "--", skill_path],
                    cwd=cache_path, check=True, capture_output=True,
                )
                tar = tarfile.open(fileobj=io.BytesIO(archive_result.stdout))
                tar.extractall(path=tmpdir)
                tar.close()
            except (subprocess.CalledProcessError, Exception) as exc:
                error(f"提取历史版本失败: {exc}")
                return

            extracted = Path(tmpdir) / skill_path
            if not extracted.is_dir():
                error("提取的 skill 目录不存在")
                return

            parser = MetadataParser()
            skill_md = extracted / "SKILL.md"
            if skill_md.exists():
                metadata = parser.parse(skill_md)
            else:
                from skill_repo.metadata import SkillMetadata
                metadata = SkillMetadata(name=skill_name, description="")
            skill_info = SkillInfo(metadata=metadata, category="pinned", source_path=extracted)

            with status_spinner(f"正在安装 {skill_name}@{selected.short_hash} ..."):
                sm.install_skill(skill_info, platform_name)

        success(f"已安装 '{skill_name}' @ {selected.short_hash} 到 {platform_name}")


def _action_repo() -> None:
    """仓库管理"""
    config = _get_config()
    all_repos = config.get_repos()

    if all_repos:
        current_url = config.get("repo.url")
        current_alias = None
        for a, r in all_repos.items():
            if r.get("url") == current_url:
                current_alias = a
                break
        console.print(repos_table(all_repos, current_alias))
        console.print()

    # 动态构建菜单：有多个仓库时才显示"切换当前仓库"
    repo_choices = ["连接已有仓库", "初始化新仓库"]
    if len(all_repos) > 1:
        repo_choices.insert(0, "切换当前仓库")
    repo_choices.append("断开连接")
    repo_choices.append("← 返回")

    choice = _ask(questionary.select(
        "操作:",
        choices=repo_choices,
        style=_QS,
        instruction="(Esc 返回)",
    ))
    if choice is _CANCELLED or choice == "← 返回":
        return

    if choice == "切换当前仓库":
        current_url = config.get("repo.url")
        switch_choices = []
        for a, r in all_repos.items():
            label = f"{a}  ({r.get('url', '')})"
            if r.get("url") == current_url:
                label += "  ● 当前"
            switch_choices.append(questionary.Choice(title=label, value=a))

        selected_alias = _ask(questionary.select(
            "选择要切换到的仓库:",
            choices=switch_choices,
            style=_QS,
            instruction="(Esc 返回)",
        ))
        if selected_alias is _CANCELLED:
            return

        repo_info = all_repos[selected_alias]
        config.set("repo.url", repo_info["url"])
        config.set("repo.cache_path", repo_info.get("cache_path", ""))
        success(f"已切换到仓库 '{selected_alias}'")
        return

    if choice == "断开连接":
        if not all_repos:
            console.print("  [dim]当前未连接[/dim]")
            return
        if len(all_repos) > 1:
            alias = _ask(questionary.select(
                "选择要断开的仓库:",
                choices=list(all_repos.keys()),
                style=_QS,
                instruction="(Esc 返回)",
            ))
            if alias is _CANCELLED:
                return
        else:
            alias = next(iter(all_repos.keys()))
        ok = _ask(questionary.confirm(f"确认断开 '{alias}'?", default=False, style=_QS))
        if ok is _CANCELLED or not ok:
            return
        config.remove_repo(alias)
        success(f"已断开 '{alias}'")
        return

    # 连接或初始化
    alias = _ask(questionary.text("仓库别名 (默认 default):", default="default", style=_QS))
    if alias is _CANCELLED:
        return
    alias = alias.strip() or "default"

    url = _ask(questionary.text("Git 仓库 URL:", style=_QS))
    if url is _CANCELLED or not url or not url.strip():
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
        if not git.has_skills_dir(repo_path):
            with status_spinner("正在创建仓库结构 ..."):
                git.init_repo_structure(repo_path)
            with status_spinner("正在提交并推送 ..."):
                try:
                    git.add_commit_push(repo_path, "初始化 skill 仓库结构")
                    success("已初始化并推送")
                except RuntimeError as exc:
                    warning(f"推送失败: {exc}")
                    info("本地结构已创建，请手动推送。")
        else:
            info("该仓库已包含 skills/ 目录结构。")
    else:
        if not git.has_skills_dir(repo_path):
            warning("该仓库无 skills/ 目录，可能不是有效的 skill 仓库。")

    config.add_repo(alias, url, str(repo_path))
    success(f"已连接 (别名: {alias})")


def _action_settings() -> None:
    """设置页面 — 配置默认平台、分支模式等"""
    config = _get_config()

    while True:
        # 读取当前配置
        default_platform = config.get("defaults.target_platform") or "未设置"
        branch_mode = config.get("branch.mode") or "direct"
        auto_merge = config.get("branch.auto_merge")
        auto_merge_label = "开启" if auto_merge == "true" else "关闭"
        cleanup = config.get("branch.cleanup")
        cleanup_label = "开启" if cleanup == "true" else "关闭"

        # 展示当前配置
        from rich.table import Table
        t = Table(title="[bold]当前配置[/bold]", border_style="cyan", pad_edge=True, show_lines=True)
        t.add_column("配置项", style="bold", width=24)
        t.add_column("当前值", style="cyan", width=16)
        t.add_column("说明", style="dim", width=36)
        t.add_row("默认平台", default_platform, "安装/更新/卸载时的默认平台")
        t.add_row("分支模式", branch_mode, "direct=直推 / branch=分支协作")
        t.add_row("自动合并", auto_merge_label, "分支模式下无冲突时自动合并")
        t.add_row("自动清理分支", cleanup_label, "合并后删除远程分支")
        console.print(t)
        console.print()

        choice = _ask(questionary.select(
            "修改配置:",
            choices=[
                "修改默认平台",
                "修改分支模式",
                "修改自动合并",
                "修改自动清理分支",
                "← 返回",
            ],
            style=_QS,
            instruction="(Esc 返回)",
        ))
        if choice is _CANCELLED or choice == "← 返回":
            return

        if choice == "修改默认平台":
            registry = PlatformRegistry()
            platforms = registry.all()
            selected = _ask(questionary.select(
                "选择默认平台:",
                choices=[pc.name for pc in platforms] + ["清除默认"],
                style=_QS,
            ))
            if selected is _CANCELLED:
                continue
            if selected == "清除默认":
                config.delete("defaults.target_platform")
                success("已清除默认平台。")
            else:
                config.set("defaults.target_platform", selected)
                success(f"默认平台已设为 {selected}。")

        elif choice == "修改分支模式":
            selected = _ask(questionary.select(
                "选择分支模式:",
                choices=[
                    questionary.Choice("direct — 直接推送到主分支", value="direct"),
                    questionary.Choice("branch — 创建个人分支再合并", value="branch"),
                ],
                style=_QS,
            ))
            if selected is _CANCELLED:
                continue
            config.set("branch.mode", selected)
            label = "直推模式" if selected == "direct" else "分支协作模式"
            success(f"已切换到 {label}。")

        elif choice == "修改自动合并":
            new_val = _ask(questionary.select(
                "自动合并:",
                choices=[
                    questionary.Choice("开启 — 无冲突时自动合并到主分支", value="true"),
                    questionary.Choice("关闭 — 只推送分支，手动合并", value="false"),
                ],
                style=_QS,
            ))
            if new_val is _CANCELLED:
                continue
            config.set("branch.auto_merge", new_val)
            success(f"自动合并已{'开启' if new_val == 'true' else '关闭'}。")

        elif choice == "修改自动清理分支":
            new_val = _ask(questionary.select(
                "自动清理分支:",
                choices=[
                    questionary.Choice("开启 — 合并后自动删除远程分支", value="true"),
                    questionary.Choice("关闭 — 保留远程分支", value="false"),
                ],
                style=_QS,
            ))
            if new_val is _CANCELLED:
                continue
            config.set("branch.cleanup", new_val)
            success(f"自动清理分支已{'开启' if new_val == 'true' else '关闭'}。")

        console.print()


# ── main menu ────────────────────────────────────────────────────

_MENU = [
    ("📋  概览", _action_overview),
    ("📥  安装 Skill", _action_install),
    ("📤  上传 Skill", _action_upload),
    ("🔍  搜索 Skill", _action_search),
    ("🔄  更新 Skill", _action_update),
    ("🗑️   卸载 Skill", _action_remove),
    ("📜  版本管理", _action_version_mgmt),
    ("🔗  仓库管理", _action_repo),
    ("⚙️   设置", _action_settings),
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

    first_time = True
    try:
        while True:
            _banner(first_time=first_time)
            first_time = False

            choice = _ask(questionary.select(
                "操作:",
                choices=[label for label, _ in _MENU],
                style=_QS,
            ))

            if choice is _CANCELLED:
                break

            action = dict(_MENU).get(choice)
            if action is None:
                break

            console.print()
            action()
            _pause()

    except KeyboardInterrupt:
        pass

    console.print("\n  [dim]再见 👋[/dim]\n")
