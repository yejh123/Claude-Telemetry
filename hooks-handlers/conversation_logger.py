#!/usr/bin/env python3
"""Conversation Logger Hook

Sends session events from the conversation file to MongoDB and stores local copies.
"""

import json
import logging
import shutil
import sys
import traceback
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from utils.bootstrap import ensure_deps  # noqa: E402

ensure_deps()

from utils import (  # noqa: E402
    get_config,
    get_session_log_dir,
    log_json,
    log_separator,
    send_to_mongodb_server,
    setup_hook_logger,
    utc_now_iso,
)

get_config()

COLLECTION_CONVERSATIONS = "conversations"


def _state_file_path(conversation_id: str) -> Path:
    return get_session_log_dir(conversation_id=conversation_id) / ".conversation_logger_state.json"


def _read_last_sent_index(conversation_id: str) -> int:
    path = _state_file_path(conversation_id=conversation_id)
    if not path.exists():
        return -1
    try:
        with open(path, "r") as f:
            return json.load(f).get(conversation_id, -1)
    except (json.JSONDecodeError, IOError):
        return -1


def _write_last_sent_index(conversation_id: str, index: int) -> None:
    path = _state_file_path(conversation_id=conversation_id)
    state: dict = {}
    if path.exists():
        try:
            with open(path, "r") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    state[conversation_id] = index
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _reorder_fields(event: dict) -> dict:
    ordered: OrderedDict = OrderedDict()
    for field in ("id", "timestamp", "type", "uuid", "parentUuid"):
        if field in event:
            ordered[field] = event[field]
    for key, value in event.items():
        if key not in ordered and key != "message":
            ordered[key] = value
    if "message" in event:
        ordered["message"] = event["message"]
    return dict(ordered)


def _save_local_conversation(
    conversation_path: str, conversation_id: str, logger: logging.Logger
) -> None:
    if not conversation_path or not Path(conversation_path).exists():
        return
    dest = get_session_log_dir(conversation_id=conversation_id) / "conversation.jsonl"
    try:
        shutil.copy2(conversation_path, dest)
        logger.info("Saved local conversation: %s", dest)
    except Exception as e:
        logger.error("Error saving local conversation: %s", e)


def _save_local_mongodb_format(
    conversation_id: str, new_events: dict, logger: logging.Logger
) -> None:
    local_path = get_session_log_dir(conversation_id=conversation_id) / "conversation_mongodb.json"
    current_time = utc_now_iso()

    existing_doc: dict = {}
    if local_path.exists():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                existing_doc = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    existing_events: dict = existing_doc.get("events", {})
    existing_events.update(new_events)

    doc = {
        "conversation_id": conversation_id,
        "created_at": existing_doc.get("created_at", current_time),
        "events": existing_events,
        "updated_at": current_time,
    }
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, default=str)
        logger.info("Saved local MongoDB format: %s", local_path)
    except Exception as e:
        logger.error("Error saving local MongoDB format: %s", e)


def _build_events_dict(events: list[dict]) -> dict:
    result: dict = {}
    for i, event in enumerate(events):
        copy = event.copy()
        copy["id"] = i
        result[str(i)] = _reorder_fields(event=copy)
    return result


def process_conversation(
    conversation_path: str, conversation_id: str, logger: logging.Logger
) -> None:
    if not conversation_path or not Path(conversation_path).exists():
        logger.error("Conversation file not found: %s", conversation_path)
        return

    _save_local_conversation(
        conversation_path=conversation_path, conversation_id=conversation_id, logger=logger
    )

    events: list[dict] = []
    try:
        with open(conversation_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning("Parse error: %s", e)
    except Exception as e:
        logger.error("Error reading conversation: %s", e)
        return

    last_index = _read_last_sent_index(conversation_id=conversation_id)
    logger.info("Conversation events: %d, last sent index: %d", len(events), last_index)

    new_events: list[dict] = []
    for i in range(last_index + 1, len(events)):
        event = events[i]
        event["id"] = i
        new_events.append(_reorder_fields(event=event))

    if new_events:
        logger.info("Sending %d new events to MongoDB", len(new_events))

        success, resp = send_to_mongodb_server(
            collection=COLLECTION_CONVERSATIONS,
            data={
                "conversation_id": conversation_id,
                "new_events": new_events,
                "total_event_count": len(events),
            },
            logger=logger,
        )

        if success:
            logger.info("Sent conversation to MongoDB: %s", resp.get("status", "ok"))
            events_dict = {str(e["id"]): e for e in new_events}
        else:
            logger.warning("Failed to send conversation to MongoDB")
            events_dict = _build_events_dict(events=events)

        _save_local_mongodb_format(
            conversation_id=conversation_id, new_events=events_dict, logger=logger
        )
        _write_last_sent_index(conversation_id=conversation_id, index=len(events) - 1)
    else:
        logger.info("No new events to send")
        _save_local_mongodb_format(
            conversation_id=conversation_id,
            new_events=_build_events_dict(events=events),
            logger=logger,
        )


def main() -> None:
    try:
        event_data = json.load(sys.stdin)
        conversation_id: str = event_data.get("session_id", "unknown")
        logger = setup_hook_logger(log_name="conversation_logger", conversation_id=conversation_id)

        log_separator(logger=logger)
        logger.info("Conversation Logger Hook Started")
        logger.info("Conversation ID: %s", conversation_id)

        log_json(data=event_data, logger=logger)
        log_separator(logger=logger, char="-")

        conversation_path: str = event_data.get("transcript_path")
        logger.info("Conversation path: %s", conversation_path)

        process_conversation(
            conversation_path=conversation_path, conversation_id=conversation_id, logger=logger
        )

        logger.info("Conversation Logger Hook Completed")
        log_separator(logger=logger)

    except Exception as e:
        print(f"Conversation logger error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
