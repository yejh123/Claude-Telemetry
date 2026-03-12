"""File I/O helpers for JSONL transcripts and JSON extraction."""

import json
from pathlib import Path
from typing import Optional, Union


def read_jsonl(file_path: Union[str, Path], limit: Optional[int] = None) -> list[dict]:
    """Read records from a JSONL file.

    Args:
        file_path: Path to the JSONL file
        limit: Maximum number of records to return (from the end)

    Returns:
        List of parsed dictionaries
    """
    if not file_path or not Path(file_path).exists():
        return []

    records: list[dict] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise json.JSONDecodeError(
                        f"Invalid JSON on line {line_num}: {exc.msg}", exc.doc, exc.pos
                    ) from exc

    if limit:
        return records[-limit:]
    return records


def read_transcript(
    transcript_path: Union[str, Path], limit: Optional[int] = None
) -> list[dict]:
    """Read events from a transcript file.

    Supports two formats:
    - JSONL (one JSON object per line, e.g. ``session.jsonl``)
    - MongoDB-style JSON (single object with ``events`` dict keyed by id,
      e.g. ``conversations.json``)

    Args:
        transcript_path: Path to the transcript file
        limit: Maximum number of events to read (from the end)

    Returns:
        List of event dictionaries sorted by id
    """
    if not transcript_path or not Path(transcript_path).exists():
        return []

    path = Path(transcript_path)

    if path.suffix == ".json":
        return _read_conversation_json(path=path, limit=limit)
    return read_jsonl(file_path=path, limit=limit)


def _read_conversation_json(path: Path, limit: Optional[int] = None) -> list[dict]:
    """Read events from a MongoDB-style conversations.json file.

    Expected structure: ``{"events": {"0": {...}, "1": {...}, ...}}``.

    Args:
        path: Path to the JSON file
        limit: Maximum number of events to return (from the end)

    Returns:
        List of event dicts sorted by numeric id
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events_dict: dict = data.get("events", {})
    events = sorted(events_dict.values(), key=lambda e: int(e.get("id", 0)))

    if limit:
        return events[-limit:]
    return events


def save_jsonl(file_path: Union[str, Path], records: list[dict]) -> None:
    """Write records to a JSONL file (overwrite).

    Args:
        file_path: Path to the output file
        records: List of dictionaries to write
    """
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, default=str) + "\n")
