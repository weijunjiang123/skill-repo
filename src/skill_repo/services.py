"""Shared application workflows for CLI and interactive frontends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from skill_repo.config_manager import ConfigManager
from skill_repo.git_manager import GitManager
from skill_repo.metadata import SkillInfo
from skill_repo.skill_manager import SkillManager

SYNC_ARTIFACT_PATHS = (
    Path("skills") / "README.md",
    Path("commands"),
    Path(".claude-plugin") / "manifest.json",
)


@dataclass(frozen=True)
class RepoConnection:
    """A configured repository connection."""

    alias: str
    url: str
    cache_path: Path
    is_current: bool = False
    cache_exists: bool = False


@dataclass(frozen=True)
class UploadItemResult:
    """Result for one uploaded skill."""

    skill_name: str
    action_label: str
    category: str
    version: str = ""


@dataclass(frozen=True)
class UploadBatchResult:
    """Result for an upload workflow."""

    items: list[UploadItemResult]
    source: str
    category: str
    pushed: bool
    committed: bool
    branch_name: str | None = None
    merged: bool = False
    sync_result: dict[str, bool] = field(default_factory=dict)


def list_repo_connections(config: ConfigManager, *, require_cache: bool = False) -> list[RepoConnection]:
    """Return configured repositories with current/cache status attached."""
    repos = config.get_repos()
    current_url = config.get("repo.url")
    connections: list[RepoConnection] = []
    for alias, info in repos.items():
        raw_cache_path = str(info.get("cache_path") or "").strip()
        if not raw_cache_path:
            if require_cache:
                continue
            cache_path = Path("")
            cache_exists = False
        else:
            cache_path = Path(raw_cache_path)
            cache_exists = cache_path.is_dir()
            if require_cache and not cache_exists:
                continue
        connections.append(
            RepoConnection(
                alias=alias,
                url=info.get("url", ""),
                cache_path=cache_path,
                is_current=info.get("url") == current_url,
                cache_exists=cache_exists,
            )
        )
    return connections


def resolve_repo(
    config: ConfigManager,
    alias: str | None = None,
    *,
    require_cache: bool = False,
) -> RepoConnection | None:
    """Resolve an alias or the current/default repository."""
    connections = list_repo_connections(config, require_cache=require_cache)
    if alias:
        return next((repo for repo in connections if repo.alias == alias), None)
    current = next((repo for repo in connections if repo.is_current), None)
    if current is not None:
        return current
    return connections[0] if connections else None


def upload_skills_to_repo(
    *,
    git: GitManager,
    skill_manager: SkillManager,
    config: ConfigManager,
    cache_path: Path,
    source: str,
    skills: list[SkillInfo],
    category: str,
    no_push: bool = False,
) -> UploadBatchResult:
    """Copy skills into a repo and commit/push them consistently.

    This is intentionally UI-free so the CLI and TUI can share the exact same
    behavior while presenting prompts and summaries differently.
    """
    if not skills:
        raise ValueError("no skills to upload")

    branch_mode = config.get("branch.mode") or "direct"
    use_branch = branch_mode == "branch" and not no_push

    if use_branch:
        git.checkout_main_and_pull(cache_path)

    plans: list[tuple[SkillInfo, Path, str]] = []
    for skill in skills:
        dest = cache_path / "skills" / category / skill.metadata.name
        action_label = "更新" if dest.exists() else "新增"
        plans.append((skill, dest, action_label))

    git_branch_name: str | None = None
    if use_branch:
        username = git.get_username(cache_path)
        if len(plans) == 1:
            skill, _dest, action_label = plans[0]
            action_short = "update" if action_label == "更新" else "add"
            git_branch_name = git.create_skill_branch(cache_path, username, action_short, skill.metadata.name)
        else:
            git_branch_name = git.create_skill_branch(cache_path, username, "batch-upload", str(len(plans)))

    for skill, dest, _action_label in plans:
        skill_manager.copy_skill(skill.source_path, dest)

    commit_msg = _build_upload_message(git, source, category, plans)
    committed = git.add_commit_push(
        cache_path,
        commit_msg,
        push=False if use_branch else not no_push,
        paths=[dest for _skill, dest, _action_label in plans],
    )
    pushed = committed and not no_push
    merged = False
    sync_result: dict[str, bool] = {}

    if use_branch and git_branch_name is not None:
        git.push_branch(cache_path, git_branch_name)
        pushed = True

        auto_merge = config.get("branch.auto_merge") == "true"
        cleanup = config.get("branch.cleanup") == "true"
        if auto_merge:
            merged = git.try_merge_to_main(cache_path, git_branch_name)
            if merged:
                sync_result = skill_manager.sync_all(cache_path)
                if any(sync_result.values()):
                    git.add_commit_push(cache_path, "同步生成文件", push=False, paths=SYNC_ARTIFACT_PATHS)
                git.push_main(cache_path)
                if cleanup:
                    git.delete_remote_branch(cache_path, git_branch_name)
    else:
        sync_result = skill_manager.sync_all(cache_path)
        if any(sync_result.values()):
            sync_committed = git.add_commit_push(
                cache_path,
                "同步生成文件",
                push=not no_push,
                paths=SYNC_ARTIFACT_PATHS,
            )
            pushed = pushed or (sync_committed and not no_push)

    return UploadBatchResult(
        items=[
            UploadItemResult(
                skill_name=skill.metadata.name,
                action_label=action_label,
                category=category,
                version=skill.metadata.version or "",
            )
            for skill, _dest, action_label in plans
        ],
        source=source,
        category=category,
        pushed=pushed,
        committed=committed,
        branch_name=git_branch_name,
        merged=merged,
        sync_result=sync_result,
    )


def _build_upload_message(
    git: GitManager,
    source: str,
    category: str,
    plans: list[tuple[SkillInfo, Path, str]],
) -> str:
    if len(plans) == 1:
        skill, _dest, action_label = plans[0]
        return git.build_skill_commit_message(
            action_label,
            skill.metadata.name,
            source=source,
            category=category,
            description=skill.metadata.description,
            version=skill.metadata.version or "",
        )

    names = ", ".join(skill.metadata.name for skill, _dest, _action_label in plans)
    return f"批量上传 {len(plans)} 个 skill: {names}\n\n来源: {source} | 分类: {category}"
