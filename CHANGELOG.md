# Changelog

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
