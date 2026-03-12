"""Install claude-telemetry plugin into Claude Code and configure .env."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

PLUGIN_NAME = "claude-telemetry"
MARKETPLACE_NAME = "local-plugins"
PLUGIN_SRC = Path(__file__).parent.resolve()
CLAUDE_DIR = Path.home() / ".claude"
MARKETPLACE_DIR = CLAUDE_DIR / "plugins" / "marketplaces" / MARKETPLACE_NAME
PLUGIN_INSTALL_DIR = MARKETPLACE_DIR / "plugins" / PLUGIN_NAME
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
KNOWN_MARKETPLACES_PATH = CLAUDE_DIR / "plugins" / "known_marketplaces.json"

EXCLUDE_PATTERNS = {
    ".env",
    "config.json",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    "logs",
    "tests",
    "install.py",
}

CONFIG_FIELDS = [
    ("CLAUDE_TELEMETRY_USERNAME", "Username", ""),
    ("CLAUDE_TELEMETRY_EMAIL", "Email", ""),
    ("CLAUDE_TELEMETRY_MONGODB_PROXY_URL", "MongoDB proxy URL", "http://149.28.225.133:5100/"),
    ("CLAUDE_TELEMETRY_MONGODB_DATABASE", "MongoDB database", "baseline"),
]


# ─── File copy ───────────────────────────────────────────────────────────────
def _should_exclude(path: Path) -> bool:
    """Check whether a path matches any exclusion pattern.

    Args:
        path: Path relative to the plugin source root.

    Returns:
        True if the path should be skipped during copy.
    """
    return any(part in EXCLUDE_PATTERNS for part in path.parts)


def _copy_plugin(src: Path, dst: Path) -> None:
    """Copy plugin files to the install directory, skipping excluded paths.

    Args:
        src: Source plugin directory.
        dst: Destination install directory.
    """
    if dst.exists():
        print(f"Removing previous installation at {dst}")
        shutil.rmtree(dst)

    dst.mkdir(parents=True, exist_ok=True)

    for item in src.rglob("*"):
        relative = item.relative_to(src)
        if _should_exclude(relative):
            continue
        target = dst / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _install_dependencies(install_dir: Path) -> None:
    """Install Python dependencies from requirements.txt.

    Args:
        install_dir: Plugin install directory containing requirements.txt.
    """
    requirements = install_dir / "requirements.txt"
    if not requirements.is_file():
        return
    print("Installing Python dependencies...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements), "--quiet"]
    )


# ─── Plugin registration ────────────────────────────────────────────────────
def _read_json(path: Path) -> dict:
    """Read a JSON file, returning empty dict if missing or corrupt.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict, or empty dict on failure.
    """
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    """Write a dict to a JSON file with consistent formatting.

    Args:
        path: Destination file path.
        data: Dict to serialize.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_marketplace_manifest() -> None:
    """Create .claude-plugin/marketplace.json listing this plugin."""
    manifest_path = MARKETPLACE_DIR / ".claude-plugin" / "marketplace.json"
    manifest = _read_json(manifest_path)

    manifest.setdefault("name", MARKETPLACE_NAME)
    manifest.setdefault("description", "Locally installed plugins")
    manifest.setdefault("owner", {"name": "local"})

    plugin_entry = {
        "name": PLUGIN_NAME,
        "description": "Claude Code plugin for logging telemetry events to local files and MongoDB",
        "source": f"./plugins/{PLUGIN_NAME}",
    }

    existing_plugins = manifest.setdefault("plugins", [])
    if not any(p.get("name") == PLUGIN_NAME for p in existing_plugins):
        existing_plugins.append(plugin_entry)

    _write_json(manifest_path, manifest)


def _register_marketplace() -> None:
    """Write marketplace manifest and register in known_marketplaces.json."""
    _write_marketplace_manifest()

    marketplaces = _read_json(KNOWN_MARKETPLACES_PATH)
    if MARKETPLACE_NAME not in marketplaces:
        marketplaces[MARKETPLACE_NAME] = {
            "source": {"source": "directory", "path": str(MARKETPLACE_DIR)},
            "installLocation": str(MARKETPLACE_DIR),
            "lastUpdated": "2026-03-11T00:00:00.000Z",
        }
        _write_json(KNOWN_MARKETPLACES_PATH, marketplaces)
    print(f"Registered marketplace: {MARKETPLACE_NAME}")


def _enable_plugin() -> None:
    """Enable the plugin in ~/.claude/settings.json."""
    settings = _read_json(SETTINGS_PATH)
    enabled = settings.setdefault("enabledPlugins", {})
    plugin_key = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"
    if enabled.get(plugin_key) is True:
        return
    enabled[plugin_key] = True
    _write_json(SETTINGS_PATH, settings)
    print(f"Enabled plugin: {plugin_key}")


def _read_existing_env(path: Path) -> dict[str, str]:
    """Parse an existing .env file into a dict.

    Args:
        path: Path to the .env file.

    Returns:
        Dict mapping variable names to their values.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _resolve_current_value(key: str, existing: dict[str, str]) -> str:
    """Return the current value from env vars or existing .env file.

    Args:
        key: Environment variable name.
        existing: Values parsed from existing .env file.

    Returns:
        Current value, or empty string if unset.
    """
    return os.environ.get(key, existing.get(key, ""))


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    """Write config values to a .env file.

    Args:
        path: Destination .env file path.
        values: Dict mapping variable names to their values.
    """
    lines: list[str] = [
        "# Claude Telemetry — Configuration",
        "",
        f"CLAUDE_TELEMETRY_USERNAME={values.get('CLAUDE_TELEMETRY_USERNAME', '')}",
        f"CLAUDE_TELEMETRY_EMAIL={values.get('CLAUDE_TELEMETRY_EMAIL', '')}",
        "",
        "CLAUDE_TELEMETRY_MONGODB_ENABLE_PROXY=true",
        f"CLAUDE_TELEMETRY_MONGODB_PROXY_URL={values.get('CLAUDE_TELEMETRY_MONGODB_PROXY_URL', '')}",
        f"CLAUDE_TELEMETRY_MONGODB_DATABASE={values.get('CLAUDE_TELEMETRY_MONGODB_DATABASE', '')}",
        "CLAUDE_TELEMETRY_MONGODB_ENABLED=true",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _prompt_value(label: str, current: str) -> str:
    """Prompt user for a single config value, showing the current/default.

    Args:
        label: Human-readable field label.
        current: Current or default value to display.

    Returns:
        User input, or current value if user pressed Enter.
    """
    if current:
        user_input = input(f"  {label} ({current}): ").strip()
        return user_input if user_input else current
    return input(f"  {label}: ").strip()


def _run_setup(env_path: Path) -> None:
    """Prompt user for each config value and write to .env.

    Args:
        env_path: Path to the .env file to create/update.
    """
    print(f"\nConfiguration  [{env_path}]\n")
    print("Press Enter to keep the current value.\n")

    existing = _read_existing_env(env_path)
    result: dict[str, str] = {}

    for key, label, default in CONFIG_FIELDS:
        current = _resolve_current_value(key, existing) or default
        result[key] = _prompt_value(label, current)

    print()
    _write_env_file(env_path, result)
    print(f"Saved to {env_path}")


def _test_proxy(proxy_url: str) -> bool:
    """Test proxy server connectivity via its health endpoint.

    Args:
        proxy_url: Base URL of the MongoDB proxy server.

    Returns:
        True if the proxy is healthy, False otherwise.
    """
    if not proxy_url:
        print("  Proxy URL not set, skipping test.")
        return False

    health_url = f"{proxy_url.rstrip('/')}/health"
    print(f"  Testing proxy: {health_url} ...", end=" ")
    try:
        req = Request(health_url, method="GET")
        with urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "ok":
                print("OK")
                return True
            print(f"unexpected response: {body}")
            return False
    except URLError as err:
        print(f"FAILED ({err.reason})")
        return False
    except Exception as err:
        print(f"FAILED ({err})")
        return False


def main() -> None:
    """Copy plugin, register in Claude Code, and configure .env."""
    print("Claude Telemetry — Installer")
    print(f"Source:  {PLUGIN_SRC}")
    print(f"Target:  {PLUGIN_INSTALL_DIR}\n")

    _copy_plugin(PLUGIN_SRC, PLUGIN_INSTALL_DIR)
    _install_dependencies(PLUGIN_INSTALL_DIR)
    _register_marketplace()
    _enable_plugin()

    print(f"\nInstalled {PLUGIN_NAME} to {PLUGIN_INSTALL_DIR}")
    env_path = PLUGIN_INSTALL_DIR / ".env"
    _run_setup(env_path)

    print("\nConnection test:")
    existing = _read_existing_env(env_path)
    proxy_url = existing.get("CLAUDE_TELEMETRY_MONGODB_PROXY_URL", "")
    _test_proxy(proxy_url)

    print("\nRestart Claude Code to load the plugin.")


if __name__ == "__main__":
    main()
