# Changelog

## 2.1.0 — 2026-03-12

### Added
- Dual-index state tracking for conversation processing:
  - `line_index`: Position in raw conversation.jsonl file (native Claude format)
  - `last_processed_event_id`: Last event ID assigned during processing
- Username/email enrichment in events collection
- Username/email enrichment in conversations collection
- Metadata document with `created_at`, `status` ("active"/"completed"), and `updated_at` fields

### Changed
- **Metadata transmission moved from SessionStart to first conversation transmission** — ensures metadata always exists even if plugin activates after SessionStart
- SessionEnd hook now updates metadata status to "completed"
- Renamed `mongodb_event_id` to `last_processed_event_id` for clarity (variable may not be sent to MongoDB)
- Event IDs now increment consecutively across sessions (not reset on logger hook filtering)
- Conversation logger now only reads new lines (after `line_index`) instead of entire file each time
- Optimized `_read_conversation_events()` to accept `start_line_index` parameter for incremental reading
- Logger infrastructure hook_progress events (event_logger, conversation_logger) now filtered at conversation DAG level, not individual event level

### Removed
- `session_start.py` hook handler — metadata now sent on first conversation transmission
- SessionStart hook no longer triggers session_start.py

### Technical Details
- State file now stores: `{ "line_index": N, "last_processed_event_id": M }`
- Backwards compatible: old single-index format auto-migrates
- `_build_events_dict()` accepts `start_event_id` parameter for flexible ID assignment
- First transmission detection: `last_processed_event_id == -1` instead of checking last_index

## 2.0.0 — 2026-03-11

### Changed
- Renamed `CLAUDE_TELEMETRY_PARTICIPANT_ID` to `CLAUDE_TELEMETRY_USERNAME`
- Renamed `CLAUDE_TELEMETRY_PARTICIPANT_EMAIL` to `CLAUDE_TELEMETRY_EMAIL`
- Renamed config field `participant_id` to `username`
- Renamed config field `participant_email` to `email`
- Removed `workspace` config field (unused)
- Removed `participant.env` file loading (`.env` is the canonical config file)

### Added
- Interactive setup script (`python3 setup.py` or `claude-telemetry-setup`)
- `.gitignore` for public distribution
- `LICENSE` (MIT)
- `CHANGELOG.md`

## 1.0.0

### Added
- Initial release with hook event logging, conversation batching, and session metadata
- MongoDB and local-only mode support
- MongoDB proxy routing option
- Layered config system (env vars > config.json > defaults)
- Auto-dependency installation via `ensure_deps()`
