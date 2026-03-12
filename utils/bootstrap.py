"""Auto-dependency installer for hook handlers.

Each handler calls ``ensure_deps()`` at the top. On first invocation it checks
whether ``pymongo`` is importable; if not, it tries ``uv pip install`` then
``pip install``.  A ``.deps_installed`` marker file prevents repeated checks.
Failures are silent — MongoDB features degrade gracefully.
"""

import subprocess
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
_MARKER = _PLUGIN_ROOT / ".deps_installed"
_REQUIREMENTS = _PLUGIN_ROOT / "requirements.txt"


def _try_install() -> bool:
    """Attempt to install dependencies via uv or pip. Returns True on success."""
    for cmd in (
        [sys.executable, "-m", "uv", "pip", "install", "-r", str(_REQUIREMENTS)],
        [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(_REQUIREMENTS)],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return False


def ensure_deps() -> None:
    """Ensure core dependencies are installed. Safe to call on every invocation."""
    if _MARKER.exists():
        return

    try:
        import pymongo  # noqa: F401

        # Already available — write marker and return
        _MARKER.write_text("ok\n")
        return
    except ImportError:
        pass

    if not _REQUIREMENTS.is_file():
        return

    if _try_install():
        _MARKER.write_text("ok\n")
