"""平台注册表单元测试"""

from pathlib import Path
from unittest.mock import patch

import pytest

from skill_repo.platforms import PlatformConfig, PlatformRegistry


class TestPlatformRegistry:
    """PlatformRegistry 基本功能测试"""

    def test_get_claude(self):
        registry = PlatformRegistry()
        config = registry.get("claude")
        assert config.name == "claude"
        assert config.label == "Claude Code"
        assert config.has_commands is True
        assert config.commands_dir is not None
        assert config.skills_dir == Path.home() / ".claude" / "skills"
        assert config.commands_dir == Path.home() / ".claude" / "commands"

    def test_get_codex(self):
        registry = PlatformRegistry()
        config = registry.get("codex")
        assert config.name == "codex"
        assert config.label == "Codex"
        assert config.has_commands is False
        assert config.commands_dir is None
        assert config.skills_dir == Path.home() / ".codex" / "skills"

    def test_get_kiro(self):
        registry = PlatformRegistry()
        config = registry.get("kiro")
        assert config.name == "kiro"
        assert config.label == "Kiro"
        assert config.has_commands is False
        assert config.commands_dir is None
        assert config.skills_dir == Path.home() / ".kiro" / "skills"

    def test_get_hermes(self):
        registry = PlatformRegistry()
        config = registry.get("hermes")
        assert config.name == "hermes"
        assert config.label == "Hermes Agent"
        assert config.has_commands is False
        assert config.commands_dir is None
        assert config.skills_dir == Path.home() / ".hermes" / "skills"

    def test_get_invalid_platform_raises(self):
        registry = PlatformRegistry()
        with pytest.raises(ValueError, match="未知平台"):
            registry.get("vscode")

    def test_all_returns_four_platforms(self):
        registry = PlatformRegistry()
        platforms = registry.all()
        assert len(platforms) == 4
        names = {p.name for p in platforms}
        assert names == {"claude", "codex", "kiro", "hermes"}

    def test_skills_path_returns_correct_path(self):
        registry = PlatformRegistry()
        for name in ("claude", "codex", "kiro", "hermes"):
            path = registry.skills_path(name)
            assert path == registry.get(name).skills_dir

    def test_skills_path_invalid_platform_raises(self):
        registry = PlatformRegistry()
        with pytest.raises(ValueError):
            registry.skills_path("unknown")


class TestPlatformRegistryEnvOverride:
    """环境变量覆盖路径测试"""

    def test_claude_env_override(self, tmp_path):
        with patch.dict("os.environ", {"CLAUDE_SKILLS_DIR": str(tmp_path)}):
            registry = PlatformRegistry()
            config = registry.get("claude")
            assert config.skills_dir == tmp_path / "skills"
            assert config.commands_dir == tmp_path / "commands"

    def test_codex_env_override(self, tmp_path):
        with patch.dict("os.environ", {"CODEX_SKILLS_DIR": str(tmp_path / "custom")}):
            registry = PlatformRegistry()
            config = registry.get("codex")
            assert config.skills_dir == tmp_path / "custom"

    def test_kiro_env_override(self, tmp_path):
        with patch.dict("os.environ", {"KIRO_SKILLS_DIR": str(tmp_path / "my-skills")}):
            registry = PlatformRegistry()
            config = registry.get("kiro")
            assert config.skills_dir == tmp_path / "my-skills"

    def test_hermes_env_override(self, tmp_path):
        with patch.dict("os.environ", {"HERMES_SKILLS_DIR": str(tmp_path / "hermes-skills")}):
            registry = PlatformRegistry()
            config = registry.get("hermes")
            assert config.skills_dir == tmp_path / "hermes-skills"

    def test_env_override_does_not_affect_other_platforms(self, tmp_path):
        with patch.dict("os.environ", {"CLAUDE_SKILLS_DIR": str(tmp_path)}):
            registry = PlatformRegistry()
            # codex, kiro and hermes should still use defaults
            assert registry.get("codex").skills_dir == Path.home() / ".codex" / "skills"
            assert registry.get("kiro").skills_dir == Path.home() / ".kiro" / "skills"
            assert registry.get("hermes").skills_dir == Path.home() / ".hermes" / "skills"


class TestPlatformConfig:
    """PlatformConfig 数据类测试"""

    def test_dataclass_fields(self):
        config = PlatformConfig(
            name="test",
            label="Test Platform",
            skills_dir=Path("/tmp/skills"),
            has_commands=True,
            commands_dir=Path("/tmp/commands"),
        )
        assert config.name == "test"
        assert config.label == "Test Platform"
        assert config.skills_dir == Path("/tmp/skills")
        assert config.has_commands is True
        assert config.commands_dir == Path("/tmp/commands")

    def test_dataclass_equality(self):
        a = PlatformConfig("x", "X", Path("/a"), False, None)
        b = PlatformConfig("x", "X", Path("/a"), False, None)
        assert a == b
