#!/usr/bin/env python3
"""Conversation Logger Hook

Sends session events from the conversation file to MongoDB and stores local copies.
"""

import json
import logging
import shutil
import sys
import traceback
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

COLLECTION_CONVERSATIONS = "conversations"
COLLECTION_METADATA = "metadata"


def _should_skip_event(hook_name: str) -> bool:
    """Check if this hook event should be skipped to avoid recursive logging.

    Args:
        hook_name: The hookName field from the hook progress event.

    Returns:
        True if this event should be skipped, False otherwise.
    """
    return "event_logger" in hook_name or "conversation_logger" in hook_name


def _send_metadata(conversation_id: str, username: str, email: str, logger: logging.Logger) -> None:
    """Send user metadata to MongoDB on first conversation transmission.

    Args:
        conversation_id: Conversation ID.
        username: Username from config.
        email: Email from config.
        logger: Logger instance.
    """
    metadata = {
        "conversation_id": conversation_id,
        "username": username,
        "email": email,
        "status": "active",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    success, resp = send_to_mongodb_server(
        collection=COLLECTION_METADATA,
        data={"conversation_id": conversation_id, "document": metadata},
        logger=logger,
    )
    if success:
        logger.info("Metadata sent to MongoDB: %s", resp.get("status", "ok"))
    else:
        logger.warning("Failed to send metadata to MongoDB")


def _state_file_path(conversation_id: str) -> Path:
    return get_session_log_dir(conversation_id=conversation_id) / ".conversation_logger_state.json"


def _read_last_indices(conversation_id: str) -> tuple[int, int]:
    """Read last line index and last processed event ID from state file.

    Returns:
        (line_index, last_processed_event_id) tuple. Defaults to (-1, -1) on error.
    """
    path = _state_file_path(conversation_id=conversation_id)
    if not path.exists():
        return -1, -1
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
            entry = state.get(conversation_id, {})
            # Support both old and new formats for backwards compatibility
            if isinstance(entry, dict):
                return entry.get("line_index", -1), entry.get("last_processed_event_id", -1)
            return -1, -1
    except (json.JSONDecodeError, IOError):
        return -1, -1


def _write_last_indices(
    conversation_id: str, line_index: int, last_processed_event_id: int
) -> None:
    """Write last line index and last processed event ID to state file.

    Args:
        conversation_id: Conversation ID.
        line_index: Line number in the raw conversation.jsonl file.
        last_processed_event_id: Last event ID processed/assigned.
    """
    path = _state_file_path(conversation_id=conversation_id)
    state: dict = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    state[conversation_id] = {
        "line_index": line_index,
        "last_processed_event_id": last_processed_event_id,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _reorder_fields(event: dict) -> dict:
    ordered: dict = {}
    for field in ("id", "timestamp", "type", "uuid", "parentUuid"):
        if field in event:
            ordered[field] = event[field]
    for key, value in event.items():
        if key not in ordered and key != "message":
            ordered[key] = value
    if "message" in event:
        ordered["message"] = event["message"]
    return ordered


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


def _build_events_dict(events: list[dict], start_event_id: int = 0) -> dict:
    """Build MongoDB events dict with proper IDs starting from start_event_id.

    Args:
        events: List of events to process.
        start_event_id: Starting ID for MongoDB events (default 0 for full rebuild).

    Returns:
        Dict with string IDs as keys and reordered events as values.
    """
    result: dict = {}
    for i, event in enumerate(events):
        mongodb_id = start_event_id + i
        copy = event.copy()
        copy["id"] = mongodb_id
        result[str(mongodb_id)] = _reorder_fields(event=copy)
    return result


def _is_logger_hook_event(event: dict) -> bool:
    """Check if event is a logger infrastructure hook_progress that should be skipped.

    Args:
        event: The event dict to check.

    Returns:
        True if event should be skipped, False otherwise.
    """
    if event.get("type") != "progress":
        return False
    data = event.get("data", {})
    if data.get("type") != "hook_progress":
        return False
    hook_name = data.get("hookName", "")
    return _should_skip_event(hook_name)


def _read_conversation_events(
    conversation_path: str, start_line_index: int, logger: logging.Logger
) -> tuple[list[dict], int]:
    """Read new conversation events from JSONL file, filtering out logger infrastructure hooks.

    Only reads lines after start_line_index, optimizing for incremental updates.

    Args:
        conversation_path: Path to the conversation.jsonl file.
        start_line_index: Skip lines up to and including this index. -1 means read all.
        logger: Logger instance.

    Returns:
        (events_list, last_line_index) tuple. events_list is filtered events read.
        last_line_index is the line number of the last line read.
        Returns ([], -1) on error.
    """
    events: list[dict] = []
    last_line_index = -1
    try:
        with open(conversation_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f):
                # Skip lines up to start_line_index
                if line_num <= start_line_index:
                    continue
                last_line_index = line_num

                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if _is_logger_hook_event(event):
                        logger.debug("Skipping logger hook event at line %d", line_num)
                        continue
                    events.append(event)
                except json.JSONDecodeError as e:
                    logger.warning("Parse error at line %d: %s", line_num, e)
    except Exception as e:
        logger.error("Error reading conversation: %s", e)
        return [], -1
    return events, last_line_index


def _update_metadata_on_session_end(
    conversation_id: str, hook_event_name: str, logger: logging.Logger
) -> None:
    """Update metadata status to "completed" if this is a SessionEnd hook.

    Args:
        conversation_id: Conversation ID.
        hook_event_name: The hook_event_name from the event.
        logger: Logger instance.
    """
    if "SessionEnd" not in hook_event_name:
        return

    config = get_config()
    metadata_update = {
        "conversation_id": conversation_id,
        "username": config.username,
        "email": config.email,
        "status": "completed",
        "updated_at": utc_now_iso(),
    }
    success, resp = send_to_mongodb_server(
        collection=COLLECTION_METADATA,
        data={"conversation_id": conversation_id, "document": metadata_update},
        logger=logger,
    )
    if success:
        logger.info("Metadata status updated to completed: %s", resp.get("status", "ok"))
    else:
        logger.warning("Failed to update metadata status to completed")


def process_conversation(
    conversation_path: str, conversation_id: str, logger: logging.Logger, hook_event_name: str = ""
) -> None:
    if not conversation_path or not Path(conversation_path).exists():
        logger.error("Conversation file not found: %s", conversation_path)
        return

    _save_local_conversation(
        conversation_path=conversation_path, conversation_id=conversation_id, logger=logger
    )

    # Read last tracked indices
    line_index, last_processed_event_id = _read_last_indices(conversation_id=conversation_id)
    logger.info(
        "Last state: line_index=%d, last_processed_event_id=%d", line_index, last_processed_event_id
    )

    # Read only new events (lines after line_index)
    new_events, last_line_index = _read_conversation_events(
        conversation_path=conversation_path, start_line_index=line_index, logger=logger
    )

    if not new_events:
        logger.info("No new events to send")
        return

    config = get_config()

    # On first transmission, send metadata
    if last_processed_event_id == -1:
        _send_metadata(
            conversation_id=conversation_id,
            username=config.username,
            email=config.email,
            logger=logger,
        )

    logger.info("Sending %d new events to MongoDB", len(new_events))

    # Assign MongoDB event IDs starting from last_processed_event_id + 1
    next_event_id = last_processed_event_id + 1
    for i, event in enumerate(new_events):
        event["id"] = next_event_id + i

    success, resp = send_to_mongodb_server(
        collection=COLLECTION_CONVERSATIONS,
        data={
            "conversation_id": conversation_id,
            "username": config.username,
            "email": config.email,
            "new_events": new_events,
        },
        logger=logger,
    )

    # Build events dict for local storage
    events_dict = _build_events_dict(events=new_events, start_event_id=next_event_id)
    if not success:
        logger.warning("Failed to send conversation to MongoDB")
    else:
        logger.info("Sent conversation to MongoDB: %s", resp.get("status", "ok"))

    _save_local_mongodb_format(
        conversation_id=conversation_id, new_events=events_dict, logger=logger
    )

    # Update state with both line_index and last_processed_event_id
    final_last_processed_event_id = next_event_id + len(new_events) - 1
    _write_last_indices(
        conversation_id=conversation_id,
        line_index=last_line_index,
        last_processed_event_id=final_last_processed_event_id,
    )

    _update_metadata_on_session_end(
        conversation_id=conversation_id, hook_event_name=hook_event_name, logger=logger
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

        hook_event_name: str = event_data.get("hook_event_name", "")
        process_conversation(
            conversation_path=conversation_path,
            conversation_id=conversation_id,
            logger=logger,
            hook_event_name=hook_event_name,
        )

        logger.info("Conversation Logger Hook Completed")
        log_separator(logger=logger)

    except Exception as e:
        print(f"Conversation logger error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
