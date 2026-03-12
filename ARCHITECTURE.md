# Claude Telemetry Plugin — Architecture

## Overview

The plugin captures Claude Code hook events and conversation transcripts, logs them locally, and sends them to MongoDB for analysis. It consists of two main handlers working in tandem:

1. **event_logger** — Captures individual hook events in real-time
2. **conversation_logger** — Batches conversation transcripts on demand

## Data Collection Flow

```
Claude Code Hook Event
    ↓
[Hook] (SessionStart, UserPromptSubmit, Stop, etc.)
    ↓
┌─────────────────────────────────────┐
│ event_logger.py                     │
├─────────────────────────────────────┤
│ • Parse hook event from stdin       │
│ • Add username/email from config    │
│ • Assign unique event ID            │
│ • Write to all_events.jsonl         │
│ • Send to MongoDB events collection │
└─────────────────────────────────────┘
    ↓
│ (For conversation hooks:
│  UserPromptSubmit, Stop, Notification, SessionEnd)
    ↓
┌─────────────────────────────────────┐
│ conversation_logger.py              │
├─────────────────────────────────────┤
│ • Read conversation.jsonl (incremental)
│ • Filter logger infrastructure hooks
│ • Assign event IDs (consecutive)    │
│ • Send metadata (first transmission)│
│ • Send conversation to MongoDB      │
│ • Save local MongoDB format         │
│ • Update state file indices         │
└─────────────────────────────────────┘
```

## State Management

### State File Structure

Location: `~/.claude/logs/{conversation_id}/.conversation_logger_state.json`

```json
{
  "conversation_id": {
    "line_index": 156,
    "last_processed_event_id": 92
  }
}
```

### Index Definitions

- **`line_index`** — Line number in the raw `conversation.jsonl` file (0-indexed)
  - Tracks position in native Claude conversation format
  - Used to only read new lines on next transmission
  - Increments even if lines are filtered out (logger hooks)

- **`last_processed_event_id`** — Last event ID assigned during processing (-1 = never processed)
  - Used to generate consecutive event IDs in MongoDB
  - Independent of raw file position
  - Increments by 1 for each new event sent
  - Determines if first transmission: `last_processed_event_id == -1`

### Why Separate Indices?

| Scenario | Impact |
|----------|--------|
| Logger hook appears in middle of events | `line_index` still advances; `last_processed_event_id` unaffected |
| Transmission fails | State not updated; retry uses same indices |
| New conversation started | Both indices reset to -1 |

## Metadata Collection

### Metadata Document Structure

```json
{
  "conversation_id": "uuid",
  "username": "from config",
  "email": "from config",
  "created_at": "2026-03-12T12:34:56.789123",
  "status": "active|completed",
  "updated_at": "2026-03-12T12:34:56.789123"
}
```

### Status Transitions

- **`active`** — Set on first conversation transmission
  - Indicates logging has begun for this session
  - Persists even if plugin disables/re-enables

- **`completed`** — Set when SessionEnd hook fires
  - Indicates session ended gracefully
  - Only updates existing metadata documents

### Timing

**Old (v2.0.0):** Metadata sent on SessionStart hook
- Problem: If plugin activates after SessionStart, metadata never sent
- Problem: Separate hook invocation creates overhead

**New (v2.1.0+):** Metadata sent on first conversation transmission
- Guaranteed: Metadata always exists once we have conversation context
- Efficient: Combines with existing batching in conversation_logger
- Resilient: Works even if plugin enables after SessionStart

## Event ID Assignment

### Algorithm

```python
# Read last state
line_index, last_processed_event_id = _read_last_indices()

# Read new events from line_index+1 onwards
new_events, last_line_index = _read_conversation_events(
    start_line_index=line_index
)

# Assign IDs consecutively
next_event_id = last_processed_event_id + 1
for i, event in enumerate(new_events):
    event["id"] = next_event_id + i

# Save state
final_event_id = next_event_id + len(new_events) - 1
_write_last_indices(
    line_index=last_line_index,
    last_processed_event_id=final_event_id
)
```

### Example Timeline

**Transmission 1** (5 events)
- `line_index`: -1 → 4
- `last_processed_event_id`: -1 → 4
- Event IDs assigned: 0, 1, 2, 3, 4

**Transmission 2** (3 events)
- `line_index`: 4 → 8
- `last_processed_event_id`: 4 → 7
- Event IDs assigned: 5, 6, 7

**Transmission 3** (1 logger hook + 2 events)
- Raw lines 9-11: 1 logger hook (filtered), 2 events
- `line_index`: 8 → 11
- `last_processed_event_id`: 7 → 9
- Event IDs assigned: 8, 9 (logger hook not counted)

## Logger Hook Filtering

### What Gets Filtered

Events with:
- `type == "progress"`
- `data.type == "hook_progress"`
- `hookName` contains "event_logger" or "conversation_logger"

### Where Filtering Happens

**event_logger.py:** No filtering (captures all events)
- `all_events.jsonl` contains complete event history including logger hooks

**conversation_logger.py:** Filters logger hooks
- Prevents infrastructure events from cluttering conversation DAG
- Keeps event IDs clean (no gaps from filtered hooks)
- Local `conversation.jsonl` still contains all events (no filtering there)

## Collections

### MongoDB Collections

#### `events`
Individual hook events, indexed by conversation_id + event_id.

```json
{
  "conversation_id": "uuid",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601",
  "username": "from config",
  "email": "from config",
  "events": {
    "0": { "id": 0, "type": "tool_use", "timestamp": "...", ... },
    "1": { "id": 1, "type": "permission_request", ... }
  }
}
```

#### `conversations`
Conversation transcripts (filtered), indexed by conversation_id.

```json
{
  "conversation_id": "uuid",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601",
  "username": "from config",
  "email": "from config",
  "events": {
    "0": { "id": 0, "type": "message", ... },
    "1": { "id": 1, "type": "message", ... }
  }
}
```

#### `metadata`
Session metadata, indexed by conversation_id.

```json
{
  "conversation_id": "uuid",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601",
  "username": "from config",
  "email": "from config",
  "status": "active|completed"
}
```

## Local Storage

### Directory Structure

```
~/.claude/logs/{conversation_id}/
├── .conversation_logger_state.json  # State: line_index, last_processed_event_id
├── all_events.jsonl                 # All hook events (no filtering)
├── conversation.jsonl               # Copy of Claude's conversation file
└── conversation_mongodb.json        # Local copy of MongoDB format
```

### File Formats

- **`all_events.jsonl`** — JSONL with separator-delimited events (no ID assignment)
- **`conversation.jsonl`** — Copy of Claude's native format (for backup)
- **`conversation_mongodb.json`** — JSON dict with "events" key containing processed events with IDs

## Error Handling

### Graceful Degradation

- **MongoDB unavailable:** Events still log locally; sent when connection restored
- **Config incomplete:** Events still logged; skips MongoDB transmission
- **File I/O error:** Logs error; continues with next event
- **JSON parse error:** Logs warning with line number; continues parsing

### Caching

MongoDB availability is cached locally (`.mongodb_status`) for 60 seconds to avoid repeated timeouts.

## Performance Considerations

### Efficiency Gains (v2.1.0+)

1. **Incremental Reading**
   - Only reads new lines after `line_index`
   - Saves I/O on large conversation files

2. **Separated Index Tracking**
   - Avoids recalculating filtered event positions
   - Logger hook filtering no longer affects event ID assignments

3. **Metadata Batching**
   - Metadata sent with first conversation, not separate hook
   - Reduces overhead by ~1 hook invocation per session

### Scalability

- Event processing: O(N) where N = new events since last transmission
- File reading: O(M) where M = new lines since last transmission (M ≥ N due to filtering)
- State tracking: Constant space (two integers per conversation)

## Configuration

All config via environment variables (precedence: env > config.json > defaults):

- `CLAUDE_TELEMETRY_USERNAME` — User identity
- `CLAUDE_TELEMETRY_EMAIL` — User identity
- `CLAUDE_TELEMETRY_MONGODB_ENABLED` — Enable/disable MongoDB (default: true)
- `CLAUDE_TELEMETRY_MONGODB_DATABASE` — Target database name
- `CLAUDE_TELEMETRY_MONGODB_PROXY_URL` — Proxy server URL
- `CLAUDE_TELEMETRY_MONGODB_ENABLE_PROXY` — Use proxy or direct pymongo (default: true)

## Testing

All changes covered by 36 tests:
- Config loading and precedence
- MongoDB integration (when available)

Run tests: `python3 -m pytest tests/ -v`
