"""GitManager 单元测试"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from skill_repo.git_manager import GitManager


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------
class TestValidateUrl:
    def setup_method(self):
        self.gm = GitManager(cache_dir=Path("/tmp/cache"))

    # --- valid HTTPS ---
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/user/repo.git",
            "https://github.com/user/repo",
            "https://gitlab.com/org/project.git",
            "https://gitlab.com/org/project",
        ],
    )
    def test_valid_https(self, url):
        assert self.gm.validate_url(url) is True

    # --- valid SSH ---
    @pytest.mark.parametrize(
        "url",
        [
            "git@github.com:user/repo.git",
            "git@github.com:user/repo",
            "git@gitlab.com:org/project.git",
            "git@gitlab.com:org/project",
        ],
    )
    def test_valid_ssh(self, url):
        assert self.gm.validate_url(url) is True

    # --- invalid ---
    @pytest.mark.parametrize(
        "url",
        [
            "",
            "not-a-url",
            "http://github.com/user/repo.git",  # http, not https
            "ftp://github.com/user/repo.git",
            "https://github.com/repo",  # missing user segment
            "git@github.com/user/repo.git",  # slash instead of colon
            "git@github.com:repo",  # missing user segment
            "github.com:user/repo.git",  # missing git@ prefix
        ],
    )
    def test_invalid_urls(self, url):
        assert self.gm.validate_url(url) is False


# ---------------------------------------------------------------------------
# get_cache_path
# ---------------------------------------------------------------------------
class TestGetCachePath:
    def test_deterministic(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path)
        url = "https://github.com/user/repo.git"
        assert gm.get_cache_path(url) == gm.get_cache_path(url)

    def test_different_urls_different_paths(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path)
        p1 = gm.get_cache_path("https://github.com/a/b.git")
        p2 = gm.get_cache_path("https://github.com/c/d.git")
        assert p1 != p2

    def test_path_under_cache_dir(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path)
        path = gm.get_cache_path("https://github.com/user/repo.git")
        assert path.parent == tmp_path

    def test_hash_length_is_8(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path)
        path = gm.get_cache_path("https://github.com/user/repo.git")
        assert len(path.name) == 8


# ---------------------------------------------------------------------------
# has_skills_dir
# ---------------------------------------------------------------------------
class TestHasSkillsDir:
    def test_true_when_exists(self, tmp_path):
        (tmp_path / "skills").mkdir()
        gm = GitManager(cache_dir=tmp_path)
        assert gm.has_skills_dir(tmp_path) is True

    def test_false_when_missing(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path)
        assert gm.has_skills_dir(tmp_path) is False

    def test_false_when_file_not_dir(self, tmp_path):
        (tmp_path / "skills").write_text("not a dir")
        gm = GitManager(cache_dir=tmp_path)
        assert gm.has_skills_dir(tmp_path) is False


# ---------------------------------------------------------------------------
# init_repo_structure
# ---------------------------------------------------------------------------
class TestInitRepoStructure:
    def test_creates_expected_files(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path)
        gm.init_repo_structure(tmp_path)

        assert (tmp_path / "skills").is_dir()
        assert (tmp_path / "skills" / "README.md").is_file()
        assert (tmp_path / "commands").is_dir()
        assert (tmp_path / ".claude-plugin" / "manifest.json").is_file()
        assert (tmp_path / "scripts" / "post_commit_sync.py").is_file()
        assert (tmp_path / "scripts" / "sync_commands.py").is_file()
        assert (tmp_path / "scripts" / "sync_skills_readme.py").is_file()
        assert (tmp_path / "scripts" / "sync_claude_marketplace.py").is_file()
        assert (tmp_path / "prek.toml").is_file()
        assert (tmp_path / "pyproject.toml").is_file()
        assert (tmp_path / "README.md").is_file()
        assert (tmp_path / ".gitignore").is_file()

        # prek.toml should have proper hook config
        prek_content = (tmp_path / "prek.toml").read_text(encoding="utf-8")
        assert "post-commit" in prek_content
        assert "post_commit_sync.py" in prek_content

        # README should have usage instructions
        readme_content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "skill-repo" in readme_content
        assert "install" in readme_content

    def test_does_not_overwrite_existing(self, tmp_path):
        (tmp_path / "skills").mkdir()
        readme = tmp_path / "skills" / "README.md"
        readme.write_text("custom content")

        gm = GitManager(cache_dir=tmp_path)
        gm.init_repo_structure(tmp_path)

        assert readme.read_text() == "custom content"


# ---------------------------------------------------------------------------
# clone / pull / add_commit_push — use real git repos via tmp_path
# ---------------------------------------------------------------------------
def _init_bare_repo(path: Path) -> Path:
    """Create a bare git repo to act as a 'remote'."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-b", "master", str(path)], check=True, capture_output=True)
    return path


def _init_working_repo(path: Path) -> Path:
    """Create a working git repo with an initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "master", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    # initial commit
    (path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


class TestClone:
    def test_clone_from_local_bare(self, tmp_path):
        bare = _init_bare_repo(tmp_path / "remote.git")
        # push an initial commit to bare
        work = _init_working_repo(tmp_path / "work")
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=work, check=True, capture_output=True)

        cache = tmp_path / "cache"
        gm = GitManager(cache_dir=cache)
        result = gm.clone(str(bare))

        assert result.exists()
        assert (result / "README.md").is_file()

    def test_clone_existing_does_pull(self, tmp_path):
        """If cache already exists, clone should pull instead."""
        bare = _init_bare_repo(tmp_path / "remote.git")
        work = _init_working_repo(tmp_path / "work")
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=work, check=True, capture_output=True)

        cache = tmp_path / "cache"
        gm = GitManager(cache_dir=cache)
        first = gm.clone(str(bare))

        # add a new file to remote
        (work / "new.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add new"], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=work, check=True, capture_output=True)

        second = gm.clone(str(bare))
        assert first == second
        assert (second / "new.txt").is_file()


class TestPull:
    def test_pull_updates_repo(self, tmp_path):
        bare = _init_bare_repo(tmp_path / "remote.git")
        work = _init_working_repo(tmp_path / "work")
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=work, check=True, capture_output=True)

        cache = tmp_path / "cache"
        gm = GitManager(cache_dir=cache)
        cloned = gm.clone(str(bare))

        # push new content
        (work / "update.txt").write_text("updated")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "update"], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=work, check=True, capture_output=True)

        gm.pull(cloned)
        assert (cloned / "update.txt").read_text() == "updated"


class TestAddCommitPush:
    def test_commit_without_push(self, tmp_path):
        repo = _init_working_repo(tmp_path / "repo")
        gm = GitManager(cache_dir=tmp_path)

        (repo / "new.txt").write_text("content")
        gm.add_commit_push(repo, "add file", push=False)

        # verify commit happened
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=repo, capture_output=True, text=True, check=True,
        )
        assert "add file" in result.stdout

    def test_commit_and_push(self, tmp_path):
        bare = _init_bare_repo(tmp_path / "remote.git")
        work = _init_working_repo(tmp_path / "work")
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "master"], cwd=work, check=True, capture_output=True)

        gm = GitManager(cache_dir=tmp_path)
        (work / "pushed.txt").write_text("pushed")
        gm.add_commit_push(work, "push test", push=True)

        # verify by cloning fresh
        fresh = tmp_path / "fresh"
        subprocess.run(["git", "clone", str(bare), str(fresh)], check=True, capture_output=True)
        assert (fresh / "pushed.txt").read_text() == "pushed"

    def test_commit_only_selected_paths(self, tmp_path):
        repo = _init_working_repo(tmp_path / "repo")
        gm = GitManager(cache_dir=tmp_path)

        (repo / "selected.txt").write_text("selected")
        (repo / "unrelated.txt").write_text("unrelated")
        committed = gm.add_commit_push(repo, "selected only", push=False, paths=[repo / "selected.txt"])

        assert committed is True
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "?? unrelated.txt" in status
        assert "selected.txt" not in status

    def test_commit_selected_paths_leaves_pre_staged_unrelated_change(self, tmp_path):
        repo = _init_working_repo(tmp_path / "repo")
        gm = GitManager(cache_dir=tmp_path)

        (repo / "selected.txt").write_text("selected")
        (repo / "staged.txt").write_text("staged")
        subprocess.run(["git", "add", "staged.txt"], cwd=repo, check=True, capture_output=True)

        gm.add_commit_push(repo, "selected only", push=False, paths=["selected.txt"])

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "A  staged.txt" in status
        assert "selected.txt" not in status

    def test_returns_false_when_no_changes(self, tmp_path):
        repo = _init_working_repo(tmp_path / "repo")
        gm = GitManager(cache_dir=tmp_path)

        committed = gm.add_commit_push(repo, "nothing", push=False, paths=["README.md"])

        assert committed is False


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    def test_clone_invalid_url_raises(self, tmp_path):
        gm = GitManager(cache_dir=tmp_path / "cache")
        with pytest.raises(RuntimeError, match="git 命令失败"):
            gm.clone("https://invalid.example.com/no/repo.git")

    def test_pull_non_repo_skips_silently(self, tmp_path):
        """pull on a non-repo (no commits) should skip without error."""
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()
        gm = GitManager(cache_dir=tmp_path)
        # Should not raise — empty/non-repo is handled gracefully
        gm.pull(not_a_repo)
