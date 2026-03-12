"""Plugin path constants.

These are resolved at import time and used by other modules that need
the plugin root before Config is initialized (e.g. logging.py).
"""

from pathlib import Path

PLUGIN_ROOT: Path = Path(__file__).parent.parent.resolve()
PROJECT_ROOT: Path = PLUGIN_ROOT.parent
