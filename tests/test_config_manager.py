"""ConfigManager 单元测试"""

from __future__ import annotations

import platform
from pathlib import Path

from skill_repo.config_manager import ConfigManager


class TestDefaultPath:
    def test_linux_macos_path(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        path = ConfigManager._default_path()
        assert path == Path.home() / ".config" / "skill-repo" / "config.toml"

    def test_windows_path(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        path = ConfigManager._default_path()
        assert path == Path.home() / "AppData" / "Roaming" / "skill-repo" / "config.toml"


class TestLoad:
    def test_load_missing_file_returns_empty_dict(self, tmp_path):
        cm = ConfigManager(config_path=tmp_path / "nonexistent.toml")
        assert cm.load() == {}

    def test_load_existing_file(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[repo]\nurl = "git@github.com:team/skills.git"\n')
        cm = ConfigManager(config_path=cfg_file)
        result = cm.load()
        assert result == {"repo": {"url": "git@github.com:team/skills.git"}}


class TestSave:
    def test_save_creates_parent_dirs(self, tmp_path):
        cfg_file = tmp_path / "a" / "b" / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.save({"repo": {"url": "https://example.com/repo.git"}})
        assert cfg_file.exists()
        loaded = cm.load()
        assert loaded["repo"]["url"] == "https://example.com/repo.git"

    def test_save_overwrites_existing(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.save({"key": "old"})
        cm.save({"key": "new"})
        assert cm.load() == {"key": "new"}


class TestGet:
    def test_get_top_level_key(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('name = "test"\n')
        cm = ConfigManager(config_path=cfg_file)
        assert cm.get("name") == "test"

    def test_get_nested_key(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[repo]\nurl = "git@host:repo.git"\n')
        cm = ConfigManager(config_path=cfg_file)
        assert cm.get("repo.url") == "git@host:repo.git"

    def test_get_missing_key_returns_none(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[repo]\nurl = "x"\n')
        cm = ConfigManager(config_path=cfg_file)
        assert cm.get("repo.missing") is None
        assert cm.get("nonexistent") is None
        assert cm.get("a.b.c") is None

    def test_get_from_empty_config(self, tmp_path):
        cm = ConfigManager(config_path=tmp_path / "nope.toml")
        assert cm.get("anything") is None


class TestSet:
    def test_set_top_level_key(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.set("name", "hello")
        assert cm.get("name") == "hello"

    def test_set_nested_key_creates_intermediate_dicts(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.set("repo.url", "https://example.com/repo.git")
        assert cm.get("repo.url") == "https://example.com/repo.git"

    def test_set_deeply_nested_key(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.set("a.b.c", "deep")
        assert cm.get("a.b.c") == "deep"

    def test_set_preserves_existing_keys(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.set("repo.url", "url1")
        cm.set("repo.cache_path", "path1")
        assert cm.get("repo.url") == "url1"
        assert cm.get("repo.cache_path") == "path1"

    def test_set_overwrites_existing_value(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cm = ConfigManager(config_path=cfg_file)
        cm.set("key", "old")
        cm.set("key", "new")
        assert cm.get("key") == "new"
