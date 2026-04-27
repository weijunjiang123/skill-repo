"""Skill 管理器 - 发现、安装、验证、搜索和复制 skill"""

from __future__ import annotations

import filecmp
import json
import shutil
from pathlib import Path

from skill_repo.metadata import MetadataParser, SkillInfo
from skill_repo.platforms import PlatformRegistry

# ── 同步相关常量 ─────────────────────────────────────────────────

_SKILLS_README_START = "<!-- BEGIN AUTO SKILLS -->"
_SKILLS_README_END = "<!-- END AUTO SKILLS -->"

_COMMAND_TEMPLATE = """\
---
description: {description}
location: plugin
---

Use the `{name}` skill to help with this task.
"""


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
            # Skip private/hidden directories (any ancestor starting with _ or .)
            rel = skill_md.relative_to(skills_dir)
            if any(part.startswith("_") or part.startswith(".") for part in rel.parts):
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

    def search_skills(self, skills: list[SkillInfo], keyword: str) -> list[SkillInfo]:
        """按关键词模糊匹配 skill 的 name、description、category。"""
        kw = keyword.lower()
        return [
            s for s in skills
            if kw in s.metadata.name.lower()
            or kw in (s.metadata.description or "").lower()
            or kw in s.category.lower()
        ]

    def remove_skill(self, skill_name: str, target_platform: str) -> bool:
        """从目标平台删除 skill，返回是否成功删除。

        安全处理符号链接和普通目录两种情况。
        """
        platform_config = self.platforms.get(target_platform)
        installed = self.find_installed(skill_name, target_platform)
        dest = installed.source_path if installed is not None else platform_config.skills_dir / skill_name
        if not dest.exists() and not dest.is_symlink():
            return False
        if dest.is_symlink():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        elif dest.is_file():
            dest.unlink()
        # Claude platform: also remove command file
        if platform_config.has_commands and platform_config.commands_dir is not None:
            cmd_file = platform_config.commands_dir / f"{skill_name}.md"
            if cmd_file.is_file():
                cmd_file.unlink()
            elif cmd_file.is_symlink():
                cmd_file.unlink()
        return True

    def list_installed(self, target_platform: str) -> list[SkillInfo]:
        """列出目标平台已安装的 skill。"""
        platform_config = self.platforms.get(target_platform)
        return self.discover_skills(platform_config.skills_dir)

    def find_installed(self, skill_name: str, target_platform: str) -> SkillInfo | None:
        """按 metadata.name 或目录名查找目标平台已安装的 skill。"""
        for skill in self.list_installed(target_platform):
            if skill.metadata.name == skill_name or skill.source_path.name == skill_name:
                return skill
        return None

    def diff_skills(
        self, skills_dir: Path, target_platform: str,
    ) -> tuple[list[SkillInfo], list[SkillInfo], list[SkillInfo]]:
        """对比远程仓库 vs 本地已安装，返回 (new, updated, unchanged)。

        - new: 远程有但本地没有
        - updated: 两边都有但内容不同
        - unchanged: 两边都有且内容一致
        """
        remote_skills = self.discover_skills(skills_dir)
        installed = self.list_installed(target_platform)
        installed_map = {s.metadata.name: s for s in installed}

        new: list[SkillInfo] = []
        updated: list[SkillInfo] = []
        unchanged: list[SkillInfo] = []

        for rs in remote_skills:
            local = installed_map.get(rs.metadata.name)
            if local is None:
                new.append(rs)
            elif not self._dirs_equal(rs.source_path, local.source_path):
                updated.append(rs)
            else:
                unchanged.append(rs)

        return new, updated, unchanged

    @staticmethod
    def _dirs_equal(dir_a: Path, dir_b: Path) -> bool:
        """递归比较两个目录内容是否一致。"""
        cmp = filecmp.dircmp(dir_a, dir_b)
        if cmp.left_only or cmp.right_only or cmp.diff_files:
            return False
        for sub in cmp.common_dirs:
            if not SkillManager._dirs_equal(dir_a / sub, dir_b / sub):
                return False
        return True

    @staticmethod
    def diff_skill_content(dir_a: Path, dir_b: Path) -> list[str]:
        """生成两个 skill 目录的人类可读差异摘要。

        dir_a 视为「本地」，dir_b 视为「远程」。
        返回差异描述行列表，无差异时返回空列表。
        """
        import difflib

        lines: list[str] = []
        if not dir_a.exists() and not dir_b.exists():
            return lines
        if not dir_a.exists():
            lines.append("本地不存在，远程有此 skill")
            return lines
        if not dir_b.exists():
            lines.append("远程不存在，仅本地有此 skill")
            return lines

        cmp = filecmp.dircmp(dir_a, dir_b)

        for f in sorted(cmp.left_only):
            lines.append(f"  仅本地: {f}")
        for f in sorted(cmp.right_only):
            lines.append(f"  仅远程: {f}")

        for f in sorted(cmp.diff_files):
            lines.append(f"  文件差异: {f}")
            fa = dir_a / f
            fb = dir_b / f
            try:
                a_lines = fa.read_text(encoding="utf-8").splitlines(keepends=True)
                b_lines = fb.read_text(encoding="utf-8").splitlines(keepends=True)
                diff = difflib.unified_diff(a_lines, b_lines, fromfile=f"本地/{f}", tofile=f"远程/{f}", n=3)
                for d in diff:
                    lines.append(f"    {d.rstrip()}")
            except (UnicodeDecodeError, OSError):
                lines.append("    (二进制文件，无法显示差异)")

        for sub in sorted(cmp.common_dirs):
            sub_diff = SkillManager.diff_skill_content(dir_a / sub, dir_b / sub)
            if sub_diff:
                lines.append(f"  子目录 {sub}/:")
                lines.extend(f"  {item}" for item in sub_diff)

        return lines

    def create_skill(
        self,
        target_dir: Path,
        name: str,
        description: str = "",
        author: str = "",
        version: str = "0.1.0",
    ) -> Path:
        """脚手架创建新 skill 目录，返回创建的目录路径。"""
        from datetime import date

        skill_dir = target_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # 构建 frontmatter
        fm_lines = [
            "---",
            f'name: "{name}"',
            f'description: "{description}"',
            f'version: "{version}"',
        ]
        if author:
            fm_lines.append(f'author: "{author}"')
        fm_lines.append(f'updated: "{date.today().isoformat()}"')
        fm_lines.append("---")
        fm_lines.append("")
        fm_lines.append(f"# {name}")
        fm_lines.append("")
        fm_lines.append("在此编写 skill 的详细说明和 prompt 内容...")
        fm_lines.append("")

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("\n".join(fm_lines), encoding="utf-8")

        return skill_dir

    # ── 内置同步方法（不依赖外部脚本）─────────────────────────────

    def sync_all(self, repo_path: Path) -> dict[str, bool]:
        """运行所有同步任务，返回 {任务名: 是否有变更}。"""
        return {
            "skills_readme": self.sync_skills_readme(repo_path),
            "commands": self.sync_commands(repo_path),
            "manifest": self.sync_manifest(repo_path),
        }

    def sync_skills_readme(self, repo_path: Path) -> bool:
        """同步 skills/README.md 中的 skill 目录表格。返回是否有变更。"""
        skills_dir = repo_path / "skills"
        readme = skills_dir / "README.md"

        skills = self.discover_skills(skills_dir)
        lines = [
            _SKILLS_README_START,
            "| Skill | Description | Path |",
            "| --- | --- | --- |",
        ]
        for s in skills:
            rel_path = s.source_path.relative_to(repo_path).as_posix()
            lines.append(
                f"| `{s.metadata.name}` | {s.metadata.description} "
                f"| [`{rel_path}`](../{rel_path}/SKILL.md) |"
            )
        lines.append(_SKILLS_README_END)
        generated = "\n".join(lines)

        if not readme.exists():
            readme.write_text(generated + "\n", encoding="utf-8")
            return True

        content = readme.read_text(encoding="utf-8")
        if _SKILLS_README_START in content and _SKILLS_README_END in content:
            start = content.index(_SKILLS_README_START)
            end = content.index(_SKILLS_README_END) + len(_SKILLS_README_END)
            updated = content[:start] + generated + content[end:]
        else:
            updated = content.rstrip() + "\n\n" + generated + "\n"

        if updated != content:
            readme.write_text(updated, encoding="utf-8")
            return True
        return False

    def sync_commands(self, repo_path: Path) -> bool:
        """同步 commands/*.md 文件。返回是否有变更。"""
        skills_dir = repo_path / "skills"
        commands_dir = repo_path / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        skills = self.discover_skills(skills_dir)
        changed = False
        for s in skills:
            if not s.metadata.description:
                continue
            desired = _COMMAND_TEMPLATE.format(
                name=s.metadata.name,
                description=s.metadata.description,
            )
            cmd_file = commands_dir / f"{s.metadata.name}.md"
            if cmd_file.exists() and cmd_file.read_text(encoding="utf-8") == desired:
                continue
            cmd_file.write_text(desired, encoding="utf-8")
            changed = True
        return changed

    def sync_manifest(self, repo_path: Path) -> bool:
        """同步 .claude-plugin/manifest.json。返回是否有变更。"""
        skills_dir = repo_path / "skills"
        manifest_path = repo_path / ".claude-plugin" / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        skills = self.discover_skills(skills_dir)
        entries = []
        for s in skills:
            rel_path = s.source_path.relative_to(repo_path).as_posix()
            entry: dict[str, object] = {
                "name": s.metadata.name,
                "path": rel_path,
                "command": f"commands/{s.metadata.name}.md",
                "tested": False,
            }
            if s.category and s.category != "uncategorized":
                entry["category"] = s.category
            entries.append(entry)

        data: dict[str, object] = {}
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}

        if data.get("skills") == entries:
            return False

        data["skills"] = entries
        if "name" not in data:
            data["name"] = "skill-repo"
        if "version" not in data:
            data["version"] = "1.0.0"
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
