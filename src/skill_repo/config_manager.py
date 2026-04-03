"""配置管理器 - 读写 TOML 格式的配置文件"""

from __future__ import annotations

import platform
from pathlib import Path

import tomli
import tomli_w


class ConfigManager:
    """管理 skill-repo 的 TOML 配置文件。

    遵循 XDG 规范：
    - Linux/macOS: ~/.config/skill-repo/config.toml
    - Windows: %APPDATA%/skill-repo/config.toml
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or self._default_path()

    def load(self) -> dict:
        """加载配置文件，不存在则返回空字典。"""
        if not self.config_path.exists():
            return {}
        data = self.config_path.read_bytes()
        return tomli.loads(data.decode("utf-8"))

    def save(self, config: dict) -> None:
        """保存配置到文件，自动创建父目录。"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes(tomli_w.dumps(config).encode("utf-8"))

    def get(self, key: str) -> str | None:
        """获取配置项，支持点号分隔的嵌套键（如 'repo.url'）。"""
        config = self.load()
        parts = key.split(".")
        current: dict | str | None = config
        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if current is None:
            return None
        return str(current) if not isinstance(current, str) else current

    def set(self, key: str, value: str) -> None:
        """设置配置项，支持点号分隔的嵌套键，自动创建中间字典。"""
        config = self.load()
        parts = key.split(".")
        current = config
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        self.save(config)

    def delete(self, key: str) -> bool:
        """删除配置项，返回是否成功删除。"""
        config = self.load()
        parts = key.split(".")
        current = config
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        if not isinstance(current, dict) or parts[-1] not in current:
            return False
        del current[parts[-1]]
        self.save(config)
        return True

    # ── 多仓库管理 ──────────────────────────────────────────────

    def get_repos(self) -> dict[str, dict[str, str]]:
        """获取所有已连接的仓库。返回 {alias: {url, cache_path}}。

        向后兼容：如果只有旧的 repo.url 配置，自动映射为 alias='default'。
        """
        config = self.load()
        repos = config.get("repos", {})
        if isinstance(repos, dict) and repos:
            return repos

        # 向后兼容旧配置
        repo = config.get("repo", {})
        if isinstance(repo, dict) and repo.get("url"):
            return {"default": {"url": repo["url"], "cache_path": repo.get("cache_path", "")}}
        return {}

    def add_repo(self, alias: str, url: str, cache_path: str) -> None:
        """添加或更新一个仓库连接。同时维护旧的 repo.url 兼容字段。"""
        config = self.load()
        if "repos" not in config or not isinstance(config["repos"], dict):
            config["repos"] = {}
        config["repos"][alias] = {"url": url, "cache_path": cache_path}
        # 保持 repo.url 指向最新操作的仓库（向后兼容）
        if "repo" not in config:
            config["repo"] = {}
        config["repo"]["url"] = url
        config["repo"]["cache_path"] = cache_path
        self.save(config)

    def remove_repo(self, alias: str) -> bool:
        """移除一个仓库连接。"""
        config = self.load()
        repos = config.get("repos", {})
        if not isinstance(repos, dict) or alias not in repos:
            return False
        del repos[alias]
        config["repos"] = repos
        # 如果删除的是当前 repo.url 指向的仓库，清空
        repo = config.get("repo", {})
        if isinstance(repo, dict) and repo.get("url") == "":
            pass  # already empty
        elif isinstance(repo, dict):
            # 如果还有其他仓库，切换到第一个
            if repos:
                first = next(iter(repos.values()))
                repo["url"] = first["url"]
                repo["cache_path"] = first["cache_path"]
            else:
                repo["url"] = ""
                repo["cache_path"] = ""
        self.save(config)
        return True

    def get_repo(self, alias: str) -> dict[str, str] | None:
        """获取指定 alias 的仓库信息。"""
        repos = self.get_repos()
        return repos.get(alias)

    @staticmethod
    def _default_path() -> Path:
        """根据操作系统返回默认配置路径。"""
        if platform.system() == "Windows":
            base = Path.home() / "AppData" / "Roaming"
        else:
            base = Path.home() / ".config"
        return base / "skill-repo" / "config.toml"
