"""Skill 管理器 - 发现、安装、验证和复制 skill"""

from __future__ import annotations

import shutil
from pathlib import Path

from skill_repo.metadata import MetadataParser, SkillInfo
from skill_repo.platforms import PlatformRegistry


class SkillManager:
    """管理 skill 的发现、安装、验证和复制操作。"""

    def __init__(
        self,
        metadata_parser: MetadataParser,
        platform_registry: PlatformRegistry,
        commands_dir: Path | None = None,
    ) -> None:
        self.parser = metadata_parser
        self.platforms = platform_registry
        self.commands_dir = commands_dir  # repo's commands/ directory

    def discover_skills(self, skills_dir: Path) -> list[SkillInfo]:
        """递归扫描目录发现所有 skill。

        跳过以 ``_`` 开头的私有目录。分类取自 skill 相对于
        *skills_dir* 的父目录名；若 skill 直接位于 *skills_dir* 下则
        分类为 ``"uncategorized"``。
        """
        skills: list[SkillInfo] = []
        if not skills_dir.is_dir():
            return skills

        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            # Skip private directories (any ancestor starting with _)
            rel = skill_md.relative_to(skills_dir)
            if any(part.startswith("_") for part in rel.parts):
                continue

            skill_dir = skill_md.parent
            metadata = self.parser.parse(skill_md)

            # Determine category from parent directory
            rel_skill = skill_dir.relative_to(skills_dir)
            if len(rel_skill.parts) <= 1:
                category = "uncategorized"
            else:
                category = rel_skill.parts[0]

            skills.append(
                SkillInfo(
                    metadata=metadata,
                    category=category,
                    source_path=skill_dir,
                )
            )
        return skills

    def install_skill(self, skill: SkillInfo, target_platform: str) -> None:
        """将 skill 复制到目标平台目录。

        对于 Claude 平台，还会同步 command 文件（如果存在）。
        """
        platform_config = self.platforms.get(target_platform)
        skill_name = skill.metadata.name
        dest = platform_config.skills_dir / skill_name

        self.copy_skill(skill.source_path, dest)

        # Claude platform: sync command file if it exists
        if platform_config.has_commands and self.commands_dir is not None:
            cmd_src = self.commands_dir / f"{skill_name}.md"
            if cmd_src.is_file() and platform_config.commands_dir is not None:
                platform_config.commands_dir.mkdir(parents=True, exist_ok=True)
                cmd_dest = platform_config.commands_dir / f"{skill_name}.md"
                shutil.copy2(cmd_src, cmd_dest)

    def install_all(self, skills_dir: Path, target_platform: str) -> int:
        """发现并安装所有 skill 到目标平台，返回安装数量。"""
        skills = self.discover_skills(skills_dir)
        for skill in skills:
            self.install_skill(skill, target_platform)
        return len(skills)

    def validate_skill(self, skill_dir: Path) -> list[str]:
        """验证 skill 目录结构和元数据，返回错误列表。"""
        return self.parser.validate(skill_dir)

    def copy_skill(self, src: Path, dest: Path) -> None:
        """复制 skill 目录，目标已存在时先删除再复制。"""
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
