"""Service workflow tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from skill_repo.config_manager import ConfigManager
from skill_repo.git_manager import GitManager
from skill_repo.metadata import MetadataParser
from skill_repo.platforms import PlatformConfig, PlatformRegistry
from skill_repo.services import list_repo_connections, resolve_repo, upload_skills_to_repo
from skill_repo.skill_manager import SkillManager


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "skills").mkdir()
    (path / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


def _make_skill(base: Path, name: str, description: str = "desc", prompt: str = "hello") -> Path:
    skill_dir = base / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: "{name}"\ndescription: "{description}"\nversion: "0.1.0"\n---\n',
        encoding="utf-8",
    )
    (skill_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    return skill_dir


def _manager(tmp_path: Path, repo_path: Path) -> SkillManager:
    registry = PlatformRegistry.__new__(PlatformRegistry)
    registry._platforms = {
        "codex": PlatformConfig("codex", "Codex", tmp_path / "codex-skills", False, None),
    }
    return SkillManager(MetadataParser(), registry, commands_dir=repo_path / "commands")


class TestRepoResolution:
    def test_resolve_current_repo(self, tmp_path: Path):
        cfg = ConfigManager(tmp_path / "config.toml")
        cfg.add_repo("one", "https://example.com/one.git", str(tmp_path / "one"))
        cfg.add_repo("two", "https://example.com/two.git", str(tmp_path / "two"))

        repo = resolve_repo(cfg)

        assert repo is not None
        assert repo.alias == "two"
        assert repo.is_current is True

    def test_list_repo_connections_can_require_cache(self, tmp_path: Path):
        cached = tmp_path / "cached"
        cached.mkdir()
        cfg = ConfigManager(tmp_path / "config.toml")
        cfg.add_repo("cached", "https://example.com/cached.git", str(cached))
        cfg.add_repo("missing", "https://example.com/missing.git", str(tmp_path / "missing"))

        repos = list_repo_connections(cfg, require_cache=True)

        assert [repo.alias for repo in repos] == ["cached"]

    def test_require_cache_rejects_empty_cache_path(self, tmp_path: Path):
        cfg = ConfigManager(tmp_path / "config.toml")
        cfg.set("repo.url", "https://example.com/legacy.git")
        cfg.set("repo.cache_path", "")

        repos = list_repo_connections(cfg, require_cache=True)
        repo = resolve_repo(cfg, require_cache=True)

        assert repos == []
        assert repo is None


class TestUploadWorkflow:
    def test_upload_reports_add_then_update(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        src = _make_skill(tmp_path / "src", "demo")
        sm = _manager(tmp_path, repo)
        skill = sm.parser.parse(src / "SKILL.md")
        skill_info = sm.discover_skills(tmp_path / "src")[0]
        assert skill.name == "demo"

        cfg = ConfigManager(tmp_path / "config.toml")
        cfg.set("branch.mode", "direct")
        git = GitManager(tmp_path / "cache")

        added = upload_skills_to_repo(
            git=git,
            skill_manager=sm,
            config=cfg,
            cache_path=repo,
            source="codex",
            skills=[skill_info],
            category="tools",
            no_push=True,
        )
        assert added.items[0].action_label == "新增"
        assert (repo / "skills" / "tools" / "demo" / "prompt.txt").read_text(encoding="utf-8") == "hello"

        (src / "prompt.txt").write_text("changed", encoding="utf-8")
        updated = upload_skills_to_repo(
            git=git,
            skill_manager=sm,
            config=cfg,
            cache_path=repo,
            source="codex",
            skills=[skill_info],
            category="tools",
            no_push=True,
        )
        assert updated.items[0].action_label == "更新"
        assert (repo / "skills" / "tools" / "demo" / "prompt.txt").read_text(encoding="utf-8") == "changed"

    def test_upload_does_not_stage_unrelated_files(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        src = _make_skill(tmp_path / "src", "demo")
        sm = _manager(tmp_path, repo)
        skill_info = sm.discover_skills(tmp_path / "src")[0]
        cfg = ConfigManager(tmp_path / "config.toml")
        git = GitManager(tmp_path / "cache")
        (repo / "unrelated.txt").write_text("leave me alone", encoding="utf-8")

        upload_skills_to_repo(
            git=git,
            skill_manager=sm,
            config=cfg,
            cache_path=repo,
            source="codex",
            skills=[skill_info],
            category="tools",
            no_push=True,
        )

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "?? unrelated.txt" in status
