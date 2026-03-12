"""Centralized configuration (dataclass singleton).

Precedence (highest wins):
  1. Environment variables  (CLAUDE_TELEMETRY_<FIELD_NAME>)
  2. config.json            (at plugin root)
  3. Built-in defaults

Each field is declared once — type, default, env var, and description together.

Usage::

    from utils.config import get_config
    cfg = get_config()          # cached singleton
    print(cfg.mongodb_url)

Tests::

    cfg = Config(config_path=tmp / "c.json", load_dotenv=False)
"""

import json
import os
from dataclasses import InitVar, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv as _load_dotenv

from utils.env import PLUGIN_ROOT, PROJECT_ROOT

_BOOLEAN_TRUTHY = frozenset({"true", "1", "yes", "on"})


def _coerce_bool(value: Any) -> bool:
    """Coerce a value to bool, treating common truthy strings as True."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower().strip() in _BOOLEAN_TRUTHY
    return bool(value)


def _cfg(default: Any, env: str, description: str) -> Any:
    """Shorthand for creating a config field with env var and description metadata."""
    return field(default=default, metadata={"env": env, "description": description})


def _load_dotenv_files() -> None:
    """Load .env into os.environ.

    Searches the project root (parent of plugin dir) and the plugin root
    itself.  The first matching file wins.
    """
    plugin_root = (
        Path(os.environ["CLAUDE_PLUGIN_ROOT"])
        if "CLAUDE_PLUGIN_ROOT" in os.environ
        else PLUGIN_ROOT
    )
    project_root = plugin_root.parent

    for candidate in (project_root / ".env", PLUGIN_ROOT / ".env"):
        if candidate.exists():
            _load_dotenv(dotenv_path=candidate, override=True)
            break


def _read_json(path: Path) -> dict:
    """Read a JSON file and return its contents as a dict.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict, or empty dict on missing/corrupt file.
    """
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, IOError):
        return {}


@dataclass
class Config:
    """Read-only configuration bag.

    Every field carries metadata:
      - ``env``  — environment variable name (``CLAUDE_TELEMETRY_<FIELD>``)
      - ``description`` — human-readable purpose
    """

    config_path: InitVar[Optional[Path]] = None
    load_dotenv: InitVar[bool] = True

    email: str = _cfg(
        "",
        "CLAUDE_TELEMETRY_EMAIL",
        "User email address for session metadata",
    )
    username: str = _cfg(
        "",
        "CLAUDE_TELEMETRY_USERNAME",
        "Username for session metadata",
    )
    mongodb_url: str = _cfg(
        "",
        "CLAUDE_TELEMETRY_MONGODB_URL",
        "MongoDB connection string (e.g. mongodb+srv://user:pass@host/db)",
    )
    mongodb_database: str = _cfg(
        "",
        "CLAUDE_TELEMETRY_MONGODB_DATABASE",
        "Target MongoDB database name",
    )
    mongodb_enabled: bool = _cfg(
        True,
        "CLAUDE_TELEMETRY_MONGODB_ENABLED",
        "Enable MongoDB data transmission; set false for local-only mode",
    )
    mongodb_enable_proxy: bool = _cfg(
        True,
        "CLAUDE_TELEMETRY_MONGODB_ENABLE_PROXY",
        "Route MongoDB writes through a proxy server instead of direct pymongo",
    )
    mongodb_proxy_url: str = _cfg(
        "",
        "CLAUDE_TELEMETRY_MONGODB_PROXY_URL",
        "Base URL of the MongoDB proxy server (e.g. http://localhost:3000)",
    )
    plugin_root: Path = field(default=PLUGIN_ROOT, init=False, repr=False)
    project_root: Path = field(default=PROJECT_ROOT, init=False, repr=False)

    def __post_init__(self, config_path: Optional[Path], load_dotenv: bool) -> None:
        if load_dotenv:
            _load_dotenv_files()

        file_values = _read_json(
            config_path if config_path is not None else PLUGIN_ROOT / "config.json"
        )

        for f in fields(self):
            env_name = f.metadata.get("env")
            if not env_name:
                continue

            is_bool = isinstance(f.default, bool)
            if env_name in os.environ:
                raw = os.environ[env_name]
                setattr(self, f.name, _coerce_bool(raw) if is_bool else raw)
            elif f.name in file_values:
                raw = file_values[f.name]
                setattr(self, f.name, _coerce_bool(raw) if is_bool else raw)

    @property
    def is_mongodb_configured(self) -> bool:
        """Return True when both mongodb_url and mongodb_database are set."""
        return bool(self.mongodb_url and self.mongodb_database)


_config: Optional[Config] = None


def get_config() -> Config:
    """Return the process-wide Config singleton (created on first call)."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Discard the cached singleton (for tests)."""
    global _config
    _config = None
