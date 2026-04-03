"""Git 管理器 - 封装 git 命令行操作"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# HTTPS: https://github.com/user/repo.git or https://github.com/user/repo
_HTTPS_RE = re.compile(r"^https://[^/]+/[^/]+/[^/]+(\.git)?$")
# SSH: git@github.com:user/repo.git or git@github.com:user/repo
_SSH_RE = re.compile(r"^git@[^:]+:[^/]+/[^/]+(\.git)?$")


@dataclass
class CommitInfo:
    """Git commit 信息"""

    hash: str
    short_hash: str
    author: str
    date: str
    message: str


@dataclass
class BranchInfo:
    """分支信息"""

    name: str
    is_remote: bool
    last_commit: str = ""
    last_date: str = ""


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
            DEFAULT_SKILL_REPO_CLI_MD,
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

        # 默认内置 skill: skill-repo-cli 操作指南
        _w(repo_path / "skills" / "tools" / "skill-repo-cli" / "SKILL.md",
           DEFAULT_SKILL_REPO_CLI_MD)

    def build_skill_commit_message(
        self,
        action: str,
        skill_name: str,
        *,
        source: str = "",
        category: str = "",
        description: str = "",
        version: str = "",
    ) -> str:
        """构建规范化的 skill commit message。

        格式: [action] skill-name — 简短描述
              来源: platform | 分类: category | 版本: version

        action: 新增/更新/回退/删除
        """
        # 第一行：主题行
        emoji = {"新增": "✨", "更新": "📦", "回退": "⏪", "删除": "🗑️"}.get(action, "📝")
        subject = f"{emoji} [{action}] {skill_name}"
        if description:
            short_desc = description[:50] + "…" if len(description) > 50 else description
            subject += f" — {short_desc}"

        # 第二行：元信息
        meta_parts: list[str] = []
        if source:
            meta_parts.append(f"来源: {source}")
        if category:
            meta_parts.append(f"分类: {category}")
        if version:
            meta_parts.append(f"版本: {version}")

        if meta_parts:
            return f"{subject}\n\n{' | '.join(meta_parts)}"
        return subject

    def run_sync_scripts(self, repo_path: Path) -> int:
        """运行仓库中的同步脚本，返回成功运行的数量。

        直接执行 scripts/ 下的同步脚本，不依赖 prek。
        """
        import sys as _sys

        scripts = [
            "sync_skills_readme.py",
            "sync_commands.py",
            "sync_claude_marketplace.py",
        ]
        scripts_dir = repo_path / "scripts"
        ran = 0
        for script_name in scripts:
            script_path = scripts_dir / script_name
            if not script_path.is_file():
                continue
            try:
                subprocess.run(
                    [_sys.executable, str(script_path)],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                ran += 1
            except subprocess.CalledProcessError:
                pass  # 静默失败，不阻塞主流程
        return ran

    def find_skill_path(self, repo_path: Path, skill_name: str) -> str | None:
        """在仓库 skills/ 目录下查找 skill 的相对路径（相对于 repo root）。

        返回如 'skills/tools/my-skill' 的路径字符串，未找到返回 None。
        """
        skills_dir = repo_path / "skills"
        if not skills_dir.is_dir():
            return None
        for skill_md in skills_dir.rglob("SKILL.md"):
            if skill_md.parent.name == skill_name:
                return str(skill_md.parent.relative_to(repo_path))
        # 也尝试匹配 frontmatter 中的 name
        from skill_repo.metadata import MetadataParser
        parser = MetadataParser()
        for skill_md in skills_dir.rglob("SKILL.md"):
            meta = parser.parse(skill_md)
            if meta.name == skill_name:
                return str(skill_md.parent.relative_to(repo_path))
        return None

    def skill_log(
        self, repo_path: Path, skill_rel_path: str, max_count: int = 20,
    ) -> list[CommitInfo]:
        """获取某个 skill 目录的 git log 历史。

        使用 git log -- <path> 过滤只涉及该 skill 的提交。
        """
        fmt = "%H%n%h%n%an%n%ai%n%s"  # hash, short_hash, author, date, subject
        try:
            result = self._run_git(
                ["log", f"--max-count={max_count}", f"--format={fmt}", "--", skill_rel_path],
                cwd=repo_path,
            )
        except RuntimeError:
            return []

        lines = result.stdout.strip().split("\n")
        commits: list[CommitInfo] = []
        # 每 5 行一组
        i = 0
        while i + 4 < len(lines):
            commits.append(CommitInfo(
                hash=lines[i],
                short_hash=lines[i + 1],
                author=lines[i + 2],
                date=lines[i + 3][:10],  # 只取日期部分
                message=lines[i + 4],
            ))
            i += 5
        return commits

    def restore_skill(
        self, repo_path: Path, skill_rel_path: str, commit_hash: str,
    ) -> None:
        """将 skill 目录恢复到指定 commit 的状态。

        使用 git checkout <commit> -- <path> 实现。
        """
        self._run_git(
            ["checkout", commit_hash, "--", skill_rel_path],
            cwd=repo_path,
        )

    def show_file_at_commit(
        self, repo_path: Path, file_rel_path: str, commit_hash: str,
    ) -> str | None:
        """获取指定 commit 时某个文件的内容。"""
        try:
            result = self._run_git(
                ["show", f"{commit_hash}:{file_rel_path}"],
                cwd=repo_path,
            )
            return result.stdout
        except RuntimeError:
            return None

    # ── 分支协作 ────────────────────────────────────────────────────

    def get_username(self, repo_path: Path) -> str:
        """获取当前 git 用户名，转为 kebab-case。"""
        import getpass
        import re as _re

        try:
            result = self._run_git(["config", "user.name"], cwd=repo_path)
            name = result.stdout.strip()
        except RuntimeError:
            name = ""

        if not name:
            name = getpass.getuser()
        if not name:
            name = "anonymous"

        # kebab-case: 小写，空格/下划线转连字符，去掉特殊字符
        name = name.lower().strip()
        name = _re.sub(r"[\s_]+", "-", name)
        name = _re.sub(r"[^a-z0-9\-]", "", name)
        return name or "anonymous"

    def create_skill_branch(
        self, repo_path: Path, username: str, action: str, skill_name: str,
    ) -> str:
        """基于最新 main 创建 skill 分支，返回分支名。"""
        main_branch = self._get_main_branch(repo_path)

        # 确保 main 是最新的
        self._run_git(["checkout", main_branch], cwd=repo_path)
        try:
            self.pull(repo_path)
        except RuntimeError:
            pass

        branch_name = f"skill/{username}/{action}-{skill_name}"
        # 如果分支已存在，先删除
        try:
            self._run_git(["branch", "-D", branch_name], cwd=repo_path)
        except RuntimeError:
            pass

        self._run_git(["checkout", "-b", branch_name], cwd=repo_path)
        return branch_name

    def push_branch(self, repo_path: Path, branch_name: str) -> None:
        """推送分支到远程。"""
        self._run_git(["push", "-u", "origin", branch_name], cwd=repo_path)

    def try_merge_to_main(self, repo_path: Path, branch_name: str) -> bool:
        """尝试 fast-forward merge 分支到 main。

        成功返回 True，有冲突返回 False。
        """
        main_branch = self._get_main_branch(repo_path)

        self._run_git(["checkout", main_branch], cwd=repo_path)
        try:
            self.pull(repo_path)
        except RuntimeError:
            pass

        try:
            self._run_git(["merge", "--ff-only", branch_name], cwd=repo_path)
            return True
        except RuntimeError:
            # ff-only 失败，尝试普通 merge（无冲突时自动合并）
            try:
                self._run_git(
                    ["merge", branch_name, "-m", f"合并分支: {branch_name}"],
                    cwd=repo_path,
                )
                return True
            except RuntimeError:
                # 真的有冲突，回退
                try:
                    self._run_git(["merge", "--abort"], cwd=repo_path)
                except RuntimeError:
                    pass
                return False

    def push_main(self, repo_path: Path) -> None:
        """推送 main 分支到远程。"""
        main_branch = self._get_main_branch(repo_path)
        self._run_git(["push", "origin", main_branch], cwd=repo_path)

    def delete_remote_branch(self, repo_path: Path, branch_name: str) -> None:
        """删除远程分支（清理）。"""
        try:
            self._run_git(["push", "origin", "--delete", branch_name], cwd=repo_path)
        except RuntimeError:
            pass  # 静默失败
        # 也删除本地分支
        try:
            self._run_git(["branch", "-d", branch_name], cwd=repo_path)
        except RuntimeError:
            pass

    def list_skill_branches(self, repo_path: Path) -> list[BranchInfo]:
        """列出所有 skill/ 开头的远程分支。"""
        try:
            self._run_git(["fetch", "--prune"], cwd=repo_path)
        except RuntimeError:
            pass

        try:
            result = self._run_git(
                ["branch", "-r", "--format=%(refname:short) %(committerdate:short) %(subject)"],
                cwd=repo_path,
            )
        except RuntimeError:
            return []

        branches: list[BranchInfo] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split(" ", 2)
            ref = parts[0]
            # 只要 origin/skill/ 开头的
            if not ref.startswith("origin/skill/"):
                continue
            name = ref.replace("origin/", "", 1)
            date = parts[1] if len(parts) > 1 else ""
            msg = parts[2] if len(parts) > 2 else ""
            branches.append(BranchInfo(name=name, is_remote=True, last_commit=msg, last_date=date))
        return branches

    def checkout_branch(self, repo_path: Path, branch_name: str) -> None:
        """切换到指定分支。"""
        self._run_git(["checkout", branch_name], cwd=repo_path)

    def _get_main_branch(self, repo_path: Path) -> str:
        """获取主分支名（main 或 master）。"""
        for name in ("main", "master"):
            try:
                self._run_git(["rev-parse", "--verify", name], cwd=repo_path)
                return name
            except RuntimeError:
                continue
        return "main"

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
