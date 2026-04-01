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

    @staticmethod
    def _default_path() -> Path:
        """根据操作系统返回默认配置路径。"""
        if platform.system() == "Windows":
            base = Path.home() / "AppData" / "Roaming"
        else:
            base = Path.home() / ".config"
        return base / "skill-repo" / "config.toml"
