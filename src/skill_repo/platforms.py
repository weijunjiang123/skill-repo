"""平台路径注册表 - 管理各 code agent 平台的路径配置"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlatformConfig:
    """平台配置数据类"""

    name: str  # "claude", "codex", "kiro", "hermes"
    label: str  # "Claude Code", "Codex", "Kiro", "Hermes Agent"
    skills_dir: Path  # 本地 skill 存储路径
    has_commands: bool  # 是否需要同步 command 文件
    commands_dir: Path | None  # command 文件目录


def _build_default_platforms() -> dict[str, PlatformConfig]:
    """构建默认平台配置，支持环境变量覆盖路径。

    环境变量覆盖基础路径：
    - CLAUDE_SKILLS_DIR: 覆盖 ~/.claude，skills/commands 为其子目录
    - CODEX_SKILLS_DIR: 覆盖 ~/.codex/skills
    - KIRO_SKILLS_DIR: 覆盖 ~/.kiro/skills
    - HERMES_SKILLS_DIR: 覆盖 ~/.hermes/skills
    """
    home = Path.home()

    # Claude: env var overrides the base ~/.claude path
    claude_base = Path(os.environ["CLAUDE_SKILLS_DIR"]) if "CLAUDE_SKILLS_DIR" in os.environ else home / ".claude"
    claude = PlatformConfig(
        name="claude",
        label="Claude Code",
        skills_dir=claude_base / "skills",
        has_commands=True,
        commands_dir=claude_base / "commands",
    )

    # Codex: env var directly overrides the skills dir
    codex_skills = Path(os.environ["CODEX_SKILLS_DIR"]) if "CODEX_SKILLS_DIR" in os.environ else home / ".codex" / "skills"
    codex = PlatformConfig(
        name="codex",
        label="Codex",
        skills_dir=codex_skills,
        has_commands=False,
        commands_dir=None,
    )

    # Kiro: env var directly overrides the skills dir
    kiro_skills = Path(os.environ["KIRO_SKILLS_DIR"]) if "KIRO_SKILLS_DIR" in os.environ else home / ".kiro" / "skills"
    kiro = PlatformConfig(
        name="kiro",
        label="Kiro",
        skills_dir=kiro_skills,
        has_commands=False,
        commands_dir=None,
    )

    # Hermes: env var directly overrides the skills dir
    hermes_skills = (
        Path(os.environ["HERMES_SKILLS_DIR"])
        if "HERMES_SKILLS_DIR" in os.environ
        else home / ".hermes" / "skills"
    )
    hermes = PlatformConfig(
        name="hermes",
        label="Hermes Agent",
        skills_dir=hermes_skills,
        has_commands=False,
        commands_dir=None,
    )

    return {p.name: p for p in (claude, codex, kiro, hermes)}


class PlatformRegistry:
    """平台注册表 - 管理所有支持的 code agent 平台配置"""

    def __init__(self) -> None:
        self._platforms = _build_default_platforms()

    def get(self, name: str) -> PlatformConfig:
        """获取平台配置，名称无效时抛出 ValueError"""
        if name not in self._platforms:
            valid = ", ".join(sorted(self._platforms))
            raise ValueError(f"未知平台 '{name}'，支持的平台: {valid}")
        return self._platforms[name]

    def all(self) -> list[PlatformConfig]:
        """返回所有支持的平台配置列表"""
        return list(self._platforms.values())

    def skills_path(self, name: str) -> Path:
        """返回平台的 skill 存储路径"""
        return self.get(name).skills_dir
