"""Skill 元数据解析器 - 解析和验证 SKILL.md frontmatter"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class SkillMetadata:
    """Skill 元数据"""

    name: str
    description: str


@dataclass
class SkillInfo:
    """Skill 完整信息（元数据 + 分类 + 路径）"""

    metadata: SkillMetadata
    category: str
    source_path: Path


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


class MetadataParser:
    """解析、验证和格式化 SKILL.md 的 YAML frontmatter"""

    def parse(self, skill_md_path: Path) -> SkillMetadata:
        """解析 SKILL.md 的 YAML frontmatter。

        缺失 frontmatter 时回退到目录名作为 name，description 为空字符串。
        """
        content = skill_md_path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.search(content)
        if not match:
            # 回退：用父目录名作为 name
            dir_name = skill_md_path.parent.name
            return SkillMetadata(name=dir_name, description="")

        raw = yaml.safe_load(match.group(1))
        if not isinstance(raw, dict):
            dir_name = skill_md_path.parent.name
            return SkillMetadata(name=dir_name, description="")

        return SkillMetadata(
            name=str(raw.get("name", "")),
            description=str(raw.get("description", "")),
        )

    def validate(self, skill_dir: Path) -> list[str]:
        """验证 skill 元数据完整性，返回错误列表。"""
        errors: list[str] = []
        skill_md = skill_dir / "SKILL.md"

        if not skill_md.exists():
            errors.append("缺少 SKILL.md 文件")
            return errors

        metadata = self.parse(skill_md)
        if not metadata.name:
            errors.append("name 字段为空")
        if not metadata.description:
            errors.append("description 字段为空")

        return errors

    def format_frontmatter(self, metadata: SkillMetadata) -> str:
        """将元数据格式化为 YAML frontmatter 字符串。"""
        data = {"name": metadata.name, "description": metadata.description}
        body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip("\n")
        return f"---\n{body}\n---\n"
