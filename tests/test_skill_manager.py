"""SkillManager 单元测试"""

from pathlib import Path

import pytest

from skill_repo.metadata import MetadataParser, SkillInfo, SkillMetadata
from skill_repo.platforms import PlatformConfig, PlatformRegistry
from skill_repo.skill_manager import SkillManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(base: Path, name: str, category: str | None = None, description: str = "desc") -> Path:
    """Create a minimal skill directory with SKILL.md under *base*/[category/]name."""
    if category:
        skill_dir = base / category / name
    else:
        skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: "{name}"\ndescription: "{description}"\n---\n',
        encoding="utf-8",
    )
    # Add an extra file so we can verify full copy
    (skill_dir / "prompt.txt").write_text("hello", encoding="utf-8")
    return skill_dir


def _build_manager(tmp_path: Path, commands_dir: Path | None = None) -> tuple[SkillManager, PlatformRegistry]:
    """Build a SkillManager wired to temp platform dirs."""
    platform_base = tmp_path / "platforms"
    claude_base = platform_base / "claude"
    codex_skills = platform_base / "codex" / "skills"
    kiro_skills = platform_base / "kiro" / "skills"
    hermes_skills = platform_base / "hermes" / "skills"

    registry = PlatformRegistry.__new__(PlatformRegistry)
    registry._platforms = {
        "claude": PlatformConfig(
            name="claude",
            label="Claude Code",
            skills_dir=claude_base / "skills",
            has_commands=True,
            commands_dir=claude_base / "commands",
        ),
        "codex": PlatformConfig(
            name="codex",
            label="Codex",
            skills_dir=codex_skills,
            has_commands=False,
            commands_dir=None,
        ),
        "kiro": PlatformConfig(
            name="kiro",
            label="Kiro",
            skills_dir=kiro_skills,
            has_commands=False,
            commands_dir=None,
        ),
        "hermes": PlatformConfig(
            name="hermes",
            label="Hermes Agent",
            skills_dir=hermes_skills,
            has_commands=False,
            commands_dir=None,
        ),
    }
    manager = SkillManager(MetadataParser(), registry, commands_dir=commands_dir)
    return manager, registry


# ---------------------------------------------------------------------------
# discover_skills
# ---------------------------------------------------------------------------

class TestDiscoverSkills:
    def test_empty_dir(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        manager, _ = _build_manager(tmp_path)
        assert manager.discover_skills(skills_dir) == []

    def test_nonexistent_dir(self, tmp_path: Path):
        manager, _ = _build_manager(tmp_path)
        assert manager.discover_skills(tmp_path / "nope") == []

    def test_discover_root_level_skill(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "my-skill")
        manager, _ = _build_manager(tmp_path)

        found = manager.discover_skills(skills_dir)
        assert len(found) == 1
        assert found[0].metadata.name == "my-skill"
        assert found[0].category == "uncategorized"

    def test_discover_categorized_skill(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "tool-a", category="tools")
        manager, _ = _build_manager(tmp_path)

        found = manager.discover_skills(skills_dir)
        assert len(found) == 1
        assert found[0].category == "tools"

    def test_discover_multiple_categories(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "a", category="cat1")
        _make_skill(skills_dir, "b", category="cat2")
        _make_skill(skills_dir, "c")
        manager, _ = _build_manager(tmp_path)

        found = manager.discover_skills(skills_dir)
        assert len(found) == 3
        categories = {s.category for s in found}
        assert categories == {"cat1", "cat2", "uncategorized"}

    def test_skip_private_directories(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "public-skill")
        # Private dir at category level
        private_dir = skills_dir / "_private" / "hidden"
        private_dir.mkdir(parents=True)
        (private_dir / "SKILL.md").write_text('---\nname: "hidden"\ndescription: "x"\n---\n')
        manager, _ = _build_manager(tmp_path)

        found = manager.discover_skills(skills_dir)
        assert len(found) == 1
        assert found[0].metadata.name == "public-skill"

    def test_skip_private_skill_dir(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "ok")
        private_skill = skills_dir / "_draft"
        private_skill.mkdir()
        (private_skill / "SKILL.md").write_text('---\nname: "_draft"\ndescription: "wip"\n---\n')
        manager, _ = _build_manager(tmp_path)

        found = manager.discover_skills(skills_dir)
        assert len(found) == 1

    def test_skip_hidden_directories(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "ok")
        hidden_skill = skills_dir / ".hub" / "quarantine" / "hidden"
        hidden_skill.mkdir(parents=True)
        (hidden_skill / "SKILL.md").write_text('---\nname: "hidden"\ndescription: "x"\n---\n')
        manager, _ = _build_manager(tmp_path)

        found = manager.discover_skills(skills_dir)
        assert [skill.metadata.name for skill in found] == ["ok"]


# ---------------------------------------------------------------------------
# copy_skill
# ---------------------------------------------------------------------------

class TestCopySkill:
    def test_copy_creates_dest(self, tmp_path: Path):
        src = _make_skill(tmp_path / "src", "s1")
        dest = tmp_path / "dest" / "s1"
        manager, _ = _build_manager(tmp_path)

        manager.copy_skill(src, dest)
        assert (dest / "SKILL.md").exists()
        assert (dest / "prompt.txt").read_text() == "hello"

    def test_copy_overwrites_existing(self, tmp_path: Path):
        src = _make_skill(tmp_path / "src", "s1")
        dest = tmp_path / "dest" / "s1"
        dest.mkdir(parents=True)
        (dest / "old_file.txt").write_text("old")

        manager, _ = _build_manager(tmp_path)
        manager.copy_skill(src, dest)

        assert not (dest / "old_file.txt").exists()
        assert (dest / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# install_skill
# ---------------------------------------------------------------------------

class TestInstallSkill:
    def test_install_to_codex(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "my-skill")
        manager, registry = _build_manager(tmp_path)

        skill_info = manager.discover_skills(skills_dir)[0]
        manager.install_skill(skill_info, "codex")

        dest = registry.get("codex").skills_dir / "my-skill"
        assert dest.is_dir()
        assert (dest / "SKILL.md").exists()
        assert (dest / "prompt.txt").read_text() == "hello"

    def test_install_to_claude_without_command(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "my-skill")
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        # No command file for this skill
        manager, registry = _build_manager(tmp_path, commands_dir=commands_dir)

        skill_info = manager.discover_skills(skills_dir)[0]
        manager.install_skill(skill_info, "claude")

        dest = registry.get("claude").skills_dir / "my-skill"
        assert dest.is_dir()
        # No command file should be copied
        cmd_dest = registry.get("claude").commands_dir / "my-skill.md"
        assert not cmd_dest.exists()

    def test_install_to_claude_with_command(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "my-skill")
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "my-skill.md").write_text("# Command\nDo stuff", encoding="utf-8")

        manager, registry = _build_manager(tmp_path, commands_dir=commands_dir)
        skill_info = manager.discover_skills(skills_dir)[0]
        manager.install_skill(skill_info, "claude")

        # Skill dir copied
        dest = registry.get("claude").skills_dir / "my-skill"
        assert dest.is_dir()
        # Command file synced
        cmd_dest = registry.get("claude").commands_dir / "my-skill.md"
        assert cmd_dest.exists()
        assert cmd_dest.read_text() == "# Command\nDo stuff"

    def test_install_to_hermes(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "my-skill")
        manager, registry = _build_manager(tmp_path)

        skill_info = manager.discover_skills(skills_dir)[0]
        manager.install_skill(skill_info, "hermes")

        dest = registry.get("hermes").skills_dir / "my-skill"
        assert dest.is_dir()
        assert (dest / "SKILL.md").exists()
        assert (dest / "prompt.txt").read_text() == "hello"

    def test_install_overwrites_existing_skill(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "my-skill")
        manager, registry = _build_manager(tmp_path)

        skill_info = manager.discover_skills(skills_dir)[0]
        # Install once
        manager.install_skill(skill_info, "kiro")
        dest = registry.get("kiro").skills_dir / "my-skill"
        (dest / "stale.txt").write_text("stale")

        # Install again — should overwrite
        manager.install_skill(skill_info, "kiro")
        assert not (dest / "stale.txt").exists()
        assert (dest / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# install_all
# ---------------------------------------------------------------------------

class TestInstallAll:
    def test_install_all_returns_count(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        _make_skill(skills_dir, "a", category="cat")
        _make_skill(skills_dir, "b")
        manager, registry = _build_manager(tmp_path)

        count = manager.install_all(skills_dir, "codex")
        assert count == 2
        codex_dir = registry.get("codex").skills_dir
        assert (codex_dir / "a").is_dir()
        assert (codex_dir / "b").is_dir()

    def test_install_all_empty(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        manager, _ = _build_manager(tmp_path)
        assert manager.install_all(skills_dir, "kiro") == 0


# ---------------------------------------------------------------------------
# list_installed / remove_skill
# ---------------------------------------------------------------------------

class TestInstalledSkills:
    def test_list_installed_scans_categorized_skills(self, tmp_path: Path):
        manager, registry = _build_manager(tmp_path)
        hermes_dir = registry.get("hermes").skills_dir
        _make_skill(hermes_dir, "apple-notes", category="apple")
        _make_skill(hermes_dir, "github-pr", category="github")

        installed = manager.list_installed("hermes")

        assert {skill.metadata.name for skill in installed} == {"apple-notes", "github-pr"}
        assert {skill.category for skill in installed} == {"apple", "github"}

    def test_find_installed_matches_directory_name(self, tmp_path: Path):
        manager, registry = _build_manager(tmp_path)
        hermes_dir = registry.get("hermes").skills_dir
        skill_dir = hermes_dir / "apple" / "apple-notes"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            '---\nname: "notes"\ndescription: "desc"\n---\n',
            encoding="utf-8",
        )

        found = manager.find_installed("apple-notes", "hermes")

        assert found is not None
        assert found.source_path == skill_dir

    def test_remove_skill_deletes_categorized_skill(self, tmp_path: Path):
        manager, registry = _build_manager(tmp_path)
        hermes_dir = registry.get("hermes").skills_dir
        _make_skill(hermes_dir, "apple-notes", category="apple")

        assert manager.remove_skill("apple-notes", "hermes") is True
        assert not (hermes_dir / "apple" / "apple-notes").exists()


# ---------------------------------------------------------------------------
# validate_skill
# ---------------------------------------------------------------------------

class TestValidateSkill:
    def test_valid_skill(self, tmp_path: Path):
        skill_dir = _make_skill(tmp_path, "good")
        manager, _ = _build_manager(tmp_path)
        assert manager.validate_skill(skill_dir) == []

    def test_missing_skill_md(self, tmp_path: Path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        manager, _ = _build_manager(tmp_path)
        errors = manager.validate_skill(skill_dir)
        assert len(errors) >= 1
        assert any("SKILL.md" in e for e in errors)

    def test_empty_description(self, tmp_path: Path):
        skill_dir = tmp_path / "no-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text('---\nname: "ok"\ndescription: ""\n---\n')
        manager, _ = _build_manager(tmp_path)
        errors = manager.validate_skill(skill_dir)
        assert any("description" in e for e in errors)
