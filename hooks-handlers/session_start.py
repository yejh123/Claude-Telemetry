#!/usr/bin/env python3
"""Session Start Hook

On SessionStart, reads user identity from Config (.env / env vars)
and sends user metadata to MongoDB.
"""

import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from utils.bootstrap import ensure_deps  # noqa: E402

ensure_deps()

from utils import (  # noqa: E402
    get_config,
    log_separator,
    send_to_mongodb_server,
    setup_hook_logger,
)

COLLECTION_METADATA = "metadata"


def _read_event_from_stdin() -> Optional[dict]:
    """Read a JSON hook event from stdin.

    Returns:
        Parsed event dict, or None if stdin is empty or unparseable.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None


def _send_metadata(conversation_id: str, username: str, email: str, logger: logging.Logger) -> None:
    """Send user metadata to MongoDB.

    Args:
        conversation_id: Session conversation ID.
        username: Username.
        email: User email address.
        logger: Logger instance.
    """
    metadata = {"conversation_id": conversation_id, "username": username, "email": email}

    success, resp = send_to_mongodb_server(
        collection=COLLECTION_METADATA,
        data={"conversation_id": conversation_id, "document": metadata},
        logger=logger,
    )
    if success:
        logger.info("Metadata sent to MongoDB: %s", resp.get("status", "ok"))
    else:
        logger.warning("Failed to send metadata to MongoDB")


def main() -> None:
    """Entry point for the session start hook."""
    event_data = _read_event_from_stdin()
    conversation_id = event_data.get("session_id", "unknown") if event_data else "unknown"
    logger = setup_hook_logger(log_name="session_start", conversation_id=conversation_id)

    try:
        log_separator(logger=logger)
        logger.info("Session Start Hook Started")
        logger.info("Conversation ID: %s", conversation_id)

        if event_data is None:
            logger.error("No event data received on stdin")
            sys.exit(1)

        os.environ["CONVERSATION_ID"] = conversation_id

        cfg = get_config()
        _send_metadata(
            conversation_id=conversation_id, username=cfg.username, email=cfg.email, logger=logger
        )

        logger.info("Session Start Hook Completed")
        log_separator(logger=logger)

    except Exception as exc:
        logger.error("Error: %s", exc)
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
