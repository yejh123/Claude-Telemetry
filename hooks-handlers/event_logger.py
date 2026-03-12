#!/usr/bin/env python3
"""Event Logger Hook

Logs individual hook events to local files and sends them to MongoDB.
"""

import json
import logging
import sys
import traceback
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from utils.bootstrap import ensure_deps  # noqa: E402

ensure_deps()

from utils import (  # noqa: E402
    SEPARATOR,
    get_config,
    get_session_log_dir,
    log_json,
    log_separator,
    send_to_mongodb_server,
    setup_hook_logger,
    utc_now_iso,
)

COLLECTION_EVENTS = "events"


def generate_event_id() -> str:
    """Generate a unique, sortable event ID (timestamp + short UUID)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{ts}_{uuid.uuid4().hex[:8]}"


def order_event_data(event_data: dict) -> OrderedDict:
    """Reorder event data with session_id and hook_event_name first."""
    ordered: OrderedDict = OrderedDict()
    for key in ("session_id", "hook_event_name"):
        if key in event_data:
            ordered[key] = event_data[key]
    for key, value in event_data.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def format_event(event_data: dict) -> str:
    """Format event data as JSON with separator for JSONL files."""
    formatted_json = json.dumps(event_data, ensure_ascii=False, indent=2)
    return f"\n{SEPARATOR}\n{formatted_json}\n"


def send_event_to_mongodb(conversation_id: str, event_data: dict, logger: logging.Logger) -> None:
    """Send a single event to MongoDB."""
    event_with_id = dict(event_data)
    event_with_id["id"] = generate_event_id()

    config = get_config()
    event_with_id["username"] = config.username
    event_with_id["email"] = config.email

    success, resp = send_to_mongodb_server(
        collection=COLLECTION_EVENTS,
        data={"conversation_id": conversation_id, "event_data": event_with_id},
        logger=logger,
    )
    if success:
        logger.info("Sent event to MongoDB: %s", resp.get("status", "ok"))
    else:
        logger.warning("Failed to send event to MongoDB")


def main() -> None:
    try:
        event_data = json.load(sys.stdin)
        conversation_id: str = event_data.get("session_id", "unknown")
        logger = setup_hook_logger(log_name="event_logger", conversation_id=conversation_id)

        log_separator(logger=logger)
        logger.info("Event Logger Hook Started")
        logger.info("Conversation ID: %s", conversation_id)

        log_json(data=event_data, logger=logger)
        log_separator(logger=logger, char="-")

        event_type: str = event_data.get("hook_event_name", "unknown")
        event_data["timestamp"] = utc_now_iso()

        ordered_data = order_event_data(event_data=event_data)
        formatted_output = format_event(event_data=ordered_data)

        session_dir: Path = get_session_log_dir(conversation_id=conversation_id)

        all_events_file = session_dir / "all_events.jsonl"
        with open(all_events_file, "a", encoding="utf-8") as f:
            f.write(formatted_output)

        logger.info("Logged event type: %s", event_type)

        send_event_to_mongodb(
            conversation_id=conversation_id, event_data=ordered_data, logger=logger
        )

        logger.info("Event Logger Hook Completed")
        log_separator(logger=logger)

    except Exception as e:
        print(f"Event logger error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
