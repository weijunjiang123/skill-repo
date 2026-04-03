"""共享终端输出工具 — 统一 cli.py 和 interactive.py 的输出风格。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Generator

    from skill_repo.metadata import SkillInfo

_THEME = Theme({
    "success": "green",
    "error": "red bold",
    "warning": "yellow",
    "info": "cyan",
    "hint": "dim",
    "key": "bold cyan",
})

console = Console(theme=_THEME)


# ── 语义化输出 ────────────────────────────────────────────────────

def success(msg: str) -> None:
    """输出成功信息：绿色 ✓ 前缀。"""
    console.print(f"  [success]✓[/success] {msg}")


def error(msg: str, *, hint: str | None = None) -> None:
    """输出错误信息：红色前缀 + 可选提示。"""
    console.print(f"  [error]✗ 错误:[/error] {msg}")
    if hint:
        console.print(f"  [hint]💡 {hint}[/hint]")


def warning(msg: str) -> None:
    """输出警告信息。"""
    console.print(f"  [warning]⚠ {msg}[/warning]")


def info(msg: str) -> None:
    """输出普通信息。"""
    console.print(f"  [info]ℹ[/info] {msg}")


# ── Spinner ───────────────────────────────────────────────────────

@contextmanager
def status_spinner(msg: str) -> Generator[None, None, None]:
    """耗时操作的 spinner 上下文管理器。"""
    with console.status(f"  {msg}", spinner="dots"):
        yield


# ── 表格组件 ──────────────────────────────────────────────────────

def skill_table(skills: list[SkillInfo], *, title: str = "Skills") -> Table:
    """构建通用 skill 表格，包含版本和作者信息（如有）。"""
    # 检测是否有扩展字段
    has_version = any(s.metadata.version for s in skills)
    has_author = any(s.metadata.author for s in skills)
    has_updated = any(s.metadata.updated for s in skills)

    t = Table(title=f"[bold]{title}[/bold]", border_style="cyan", show_lines=False, pad_edge=True)
    t.add_column("#", style="dim", width=4, justify="right")
    t.add_column("名称", style="bold")
    t.add_column("分类", style="cyan")
    t.add_column("描述", style="dim", max_width=36)
    if has_version:
        t.add_column("版本", style="green", width=8)
    if has_author:
        t.add_column("作者", style="dim", width=12)
    if has_updated:
        t.add_column("更新", style="dim", width=12)

    for i, s in enumerate(skills, 1):
        desc = s.metadata.description or "—"
        if len(desc) > 34:
            desc = desc[:32] + "…"
        row: list[str] = [str(i), s.metadata.name, s.category, desc]
        if has_version:
            row.append(s.metadata.version or "—")
        if has_author:
            row.append(s.metadata.author or "—")
        if has_updated:
            row.append(s.metadata.updated or "—")
        t.add_row(*row)
    return t


def status_panel(title: str, content: str, *, border: str = "cyan") -> Panel:
    """构建状态面板。"""
    return Panel(content, title=f"[bold]{title}[/bold]", border_style=border, padding=(0, 2))


def config_table(items: list[tuple[str, str]]) -> Table:
    """构建配置项表格。"""
    t = Table(border_style="dim", show_header=True, pad_edge=True)
    t.add_column("配置项", style="key")
    t.add_column("值", style="dim")
    for key, value in items:
        t.add_row(key, value)
    return t


def platform_table(platforms: list[tuple[str, bool, int]]) -> Table:
    """构建平台状态表格。platforms: [(label, exists, skill_count)]"""
    t = Table(title="[bold]本地平台[/bold]", border_style="green", pad_edge=True)
    t.add_column("平台", style="bold")
    t.add_column("状态")
    t.add_column("Skills", justify="right")
    for label, exists, count in platforms:
        status_text = "[success]已安装[/success]" if exists else "[error]未安装[/error]"
        t.add_row(label, status_text, str(count))
    return t


def update_table(
    new: list[SkillInfo],
    updated: list[SkillInfo],
    unchanged: list[SkillInfo],
) -> Table:
    """构建 update 对比结果表格。"""
    t = Table(title="[bold]更新检查[/bold]", border_style="cyan", pad_edge=True)
    t.add_column("名称", style="bold")
    t.add_column("状态")
    t.add_column("分类", style="cyan")
    for s in new:
        t.add_row(s.metadata.name, "[info]🆕 新增[/info]", s.category)
    for s in updated:
        t.add_row(s.metadata.name, "[warning]📦 有更新[/warning]", s.category)
    for s in unchanged:
        t.add_row(s.metadata.name, "[success]✓ 最新[/success]", s.category)
    return t


def repos_table(repos: dict[str, dict[str, str]], current_alias: str | None = None) -> Table:
    """构建多仓库列表表格。"""
    t = Table(title="[bold]已连接仓库[/bold]", border_style="cyan", pad_edge=True)
    t.add_column("别名", style="bold")
    t.add_column("URL")
    t.add_column("状态")
    for alias, info_dict in repos.items():
        marker = "[success]● 当前[/success]" if alias == current_alias else "[dim]○[/dim]"
        t.add_row(alias, info_dict.get("url", ""), marker)
    return t


def history_table(commits: list, *, title: str = "变更历史") -> Table:
    """构建 git commit 历史表格。commits: list[CommitInfo]"""
    t = Table(title=f"[bold]{title}[/bold]", border_style="cyan", pad_edge=True)
    t.add_column("#", style="dim", width=4, justify="right")
    t.add_column("提交", style="yellow", width=8)
    t.add_column("日期", style="dim", width=12)
    t.add_column("作者", style="cyan", width=14)
    t.add_column("说明", max_width=44)
    for i, c in enumerate(commits, 1):
        msg = c.message
        if len(msg) > 42:
            msg = msg[:40] + "…"
        t.add_row(str(i), c.short_hash, c.date, c.author, msg)
    return t


def upload_summary(
    action: str,
    skill_name: str,
    *,
    source: str = "",
    category: str = "",
    version: str = "",
    pushed: bool = True,
) -> Panel:
    """构建上传操作摘要面板。"""
    emoji = {"新增": "✨", "更新": "📦"}.get(action, "📝")
    lines = [f"{emoji} [bold]{action}[/bold] skill: [cyan]{skill_name}[/cyan]"]
    if source:
        lines.append(f"  来源: {source}")
    if category:
        lines.append(f"  分类: {category}")
    if version:
        lines.append(f"  版本: {version}")
    status_text = "[success]已推送到远程[/success]" if pushed else "[warning]仅本地提交[/warning]"
    lines.append(f"  状态: {status_text}")
    return Panel("\n".join(lines), title="[bold]操作摘要[/bold]", border_style="green", padding=(0, 2))
