"""Git 管理器 - 封装 git 命令行操作"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

# HTTPS: https://github.com/user/repo.git or https://github.com/user/repo
_HTTPS_RE = re.compile(r"^https://[^/]+/[^/]+/[^/]+(\.git)?$")
# SSH: git@github.com:user/repo.git or git@github.com:user/repo
_SSH_RE = re.compile(r"^git@[^:]+:[^/]+/[^/]+(\.git)?$")


class GitManager:
    """封装 git 命令行操作，管理仓库克隆、更新和推送。"""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def validate_url(self, git_url: str) -> bool:
        """验证 Git URL 格式（HTTPS 或 SSH）。"""
        return bool(_HTTPS_RE.match(git_url) or _SSH_RE.match(git_url))

    def get_cache_path(self, git_url: str) -> Path:
        """根据 URL 的 SHA256 哈希前 8 位生成确定性缓存目录路径。"""
        url_hash = hashlib.sha256(git_url.encode()).hexdigest()[:8]
        return self.cache_dir / url_hash

    def clone(self, git_url: str) -> Path:
        """克隆远程仓库到本地缓存，返回本地路径。"""
        dest = self.get_cache_path(git_url)
        if dest.exists():
            if self._has_commits(dest):
                self.pull(dest)
            return dest
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._run_git(["clone", git_url, str(dest)])
        return dest

    def pull(self, repo_path: Path) -> None:
        """更新已缓存的仓库。跳过无提交的空仓库或远程无分支的情况。"""
        if not self._has_commits(repo_path):
            return
        try:
            self._run_git(["pull"], cwd=repo_path)
        except RuntimeError as exc:
            # Remote has no branch yet (local-only commits, push never succeeded)
            if "no such ref" in str(exc).lower() or "couldn't find remote ref" in str(exc).lower():
                return
            raise

    @staticmethod
    def _has_commits(repo_path: Path) -> bool:
        """检查仓库是否有至少一个提交。"""
        try:
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path, check=True, capture_output=True,
                encoding="utf-8", errors="replace",
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _get_current_branch(self, repo_path: Path) -> str:
        """获取当前分支名，默认返回 'main'。"""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path, check=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            branch = result.stdout.strip()
            return branch if branch else "main"
        except subprocess.CalledProcessError:
            return "main"

    def add_commit_push(
        self, repo_path: Path, message: str, push: bool = True
    ) -> None:
        """git add all → commit → optional push。

        如果没有变更则跳过 commit 和 push。
        """
        self._run_git(["add", "."], cwd=repo_path)

        # Check if there's anything to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_path, capture_output=True,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            # Nothing staged — check if working tree is also clean
            result2 = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            if not result2.stdout.strip():
                return  # Nothing to commit, skip silently

        self._run_git(["commit", "-m", message], cwd=repo_path)
        if push:
            branch = self._get_current_branch(repo_path)
            try:
                subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref",
                     f"{branch}@{{upstream}}"],
                    cwd=repo_path, check=True, capture_output=True,
                    encoding="utf-8", errors="replace",
                )
                self._run_git(["push"], cwd=repo_path)
            except subprocess.CalledProcessError:
                self._run_git(["push", "-u", "origin", branch], cwd=repo_path)

    def has_skills_dir(self, repo_path: Path) -> bool:
        """检查仓库是否包含 skills/ 目录。"""
        return (repo_path / "skills").is_dir()

    def init_repo_structure(self, repo_path: Path) -> None:
        """在仓库中创建完整的 skill 仓库目录结构。"""
        from skill_repo._templates import (
            GITIGNORE, MANIFEST_JSON, PREK_TOML, PYPROJECT_TOML,
            ROOT_README, SKILLS_README,
            POST_COMMIT_SYNC_PY, SYNC_COMMANDS_PY,
            SYNC_SKILLS_README_PY, SYNC_CLAUDE_MARKETPLACE_PY,
        )

        def _w(path: Path, content: str) -> None:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

        _w(repo_path / "README.md", ROOT_README)
        _w(repo_path / ".gitignore", GITIGNORE)
        _w(repo_path / "pyproject.toml", PYPROJECT_TOML)
        _w(repo_path / "prek.toml", PREK_TOML)
        (repo_path / "skills").mkdir(parents=True, exist_ok=True)
        _w(repo_path / "skills" / "README.md", SKILLS_README)
        (repo_path / "commands").mkdir(parents=True, exist_ok=True)
        _w(repo_path / ".claude-plugin" / "manifest.json", MANIFEST_JSON)
        sd = repo_path / "scripts"
        sd.mkdir(parents=True, exist_ok=True)
        _w(sd / "post_commit_sync.py", POST_COMMIT_SYNC_PY)
        _w(sd / "sync_commands.py", SYNC_COMMANDS_PY)
        _w(sd / "sync_skills_readme.py", SYNC_SKILLS_README_PY)
        _w(sd / "sync_claude_marketplace.py", SYNC_CLAUDE_MARKETPLACE_PY)

    @staticmethod
    def _run_git(
        args: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """执行 git 命令，失败时抛出描述性错误。"""
        cmd = ["git", *args]
        try:
            return subprocess.run(
                cmd, cwd=cwd, check=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            raise RuntimeError(
                f"git 命令失败: {' '.join(cmd)}\n{stderr}"
            ) from exc
