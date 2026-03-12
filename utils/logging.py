"""Hook logger setup and session log directory management."""

import json
import logging
from datetime import datetime
from pathlib import Path

from utils.env import PLUGIN_ROOT

SEPARATOR_WIDTH = 70
SEPARATOR = "=" * SEPARATOR_WIDTH
LOG_TRUNCATION_LIMIT = 5000


def get_session_log_dir(conversation_id: str) -> Path:
    """Get the log directory for a session using cached mapping.

    Uses claude-analytics/logs/.session_cache.json to ensure all events
    for the same session go to the same directory.

    Args:
        conversation_id: Conversation ID

    Returns:
        Log directory path (claude-analytics/logs/{timestamp}_{conversation_id_short})
    """
    logs_dir = PLUGIN_ROOT / "logs"
    cache_file = logs_dir / ".session_cache.json"

    logs_dir.mkdir(parents=True, exist_ok=True)

    cache: dict[str, str] = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    if conversation_id in cache:
        dir_name = cache[conversation_id]
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        id_short = conversation_id[:8] if len(conversation_id) >= 8 else conversation_id
        dir_name = f"{timestamp}_{id_short}"

        cache[conversation_id] = dir_name
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

    log_dir = logs_dir / dir_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_hook_logger(
    log_name: str, conversation_id: str, level: int = logging.INFO
) -> logging.Logger:
    """Setup a logger for a hook script.

    Args:
        log_name: Name of the log file (e.g., "gitlab", "mongodb", "monitor")
        conversation_id: Conversation ID
        level: Logging level (default: logging.INFO)

    Returns:
        Configured logger instance
    """
    log_dir = get_session_log_dir(conversation_id=conversation_id)
    log_file = log_dir / f"{log_name}.log"

    logger_name = f"{log_name}_{conversation_id[:8]}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    logger.handlers.clear()
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def log_json(data: dict, logger: logging.Logger) -> None:
    """Log a dict as pretty-printed JSON, truncating if too large.

    Args:
        data: Dictionary to log.
        logger: Logger instance.
    """
    text = json.dumps(data, indent=2, default=str)
    if len(text) > LOG_TRUNCATION_LIMIT:
        logger.info("%s\n... [truncated, %d chars]", text[:LOG_TRUNCATION_LIMIT], len(text))
    else:
        logger.info(text)


def log_separator(logger: logging.Logger, char: str = "=", length: int = SEPARATOR_WIDTH) -> None:
    """Log a separator line.

    Args:
        logger: Logger instance
        char: Character to use for the separator
        length: Length of the separator line
    """
    logger.info(char * length)
