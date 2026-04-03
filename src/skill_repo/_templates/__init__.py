"""初始化仓库时使用的文件模板。

模板内容从同目录下的独立文件中读取，方便直接编辑和查看。
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent


def _read(filename: str) -> str:
    return (_DIR / filename).read_text(encoding="utf-8")


# ── 仓库结构模板 ─────────────────────────────────────────────────

ROOT_README = _read("root_readme.md")
SKILLS_README = _read("skills_readme.md")
PREK_TOML = _read("prek.toml")
MANIFEST_JSON = _read("manifest.json")
PYPROJECT_TOML = _read("pyproject.toml")
GITIGNORE = _read("gitignore.txt")

# ── 同步脚本模板 ─────────────────────────────────────────────────

POST_COMMIT_SYNC_PY = _read("post_commit_sync.py.tpl")
SYNC_COMMANDS_PY = _read("sync_commands.py.tpl")
SYNC_SKILLS_README_PY = _read("sync_skills_readme.py.tpl")
SYNC_CLAUDE_MARKETPLACE_PY = _read("sync_claude_marketplace.py.tpl")

# ── 默认内置 Skill ───────────────────────────────────────────────

DEFAULT_SKILL_REPO_CLI_MD = _read("default_skill_repo_cli.md")
