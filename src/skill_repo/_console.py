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
    """构建通用 skill 表格。"""
    t = Table(title=f"[bold]{title}[/bold]", border_style="cyan", show_lines=False, pad_edge=True)
    t.add_column("#", style="dim", width=4, justify="right")
    t.add_column("名称", style="bold")
    t.add_column("分类", style="cyan")
    t.add_column("描述", style="dim", max_width=44)
    for i, s in enumerate(skills, 1):
        desc = s.metadata.description or "—"
        if len(desc) > 42:
            desc = desc[:40] + "…"
        t.add_row(str(i), s.metadata.name, s.category, desc)
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
