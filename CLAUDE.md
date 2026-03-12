# Claude Telemetry Plugin

## Architecture

Claude Code plugin that logs hook events to local JSONL files and optionally sends them to MongoDB.

```
hooks/hooks.json        → defines which hooks trigger which handler scripts
hooks-handlers/         → Python scripts invoked by Claude Code hooks
utils/                  → shared utilities (config, mongodb, logging, io, time)
tests/                  → pytest test suite
```

## Key Patterns

- **Config precedence**: env vars (`CLAUDE_TELEMETRY_*`) > `config.json` > defaults
- **Bootstrap**: handlers call `ensure_deps()` at top — auto-installs pymongo if missing
- **MongoDB caching**: first connection failure caches `unavailable` for the session to avoid repeated 5s timeouts
- **Graceful degradation**: if MongoDB is unconfigured/unreachable, events still log locally

## Configuration

Copy `.env.example` → `.env` and fill in values. Or use `config.example.json` → `config.json`.

Key env vars:

- `CLAUDE_TELEMETRY_EMAIL` / `CLAUDE_TELEMETRY_USERNAME` — session metadata
- `CLAUDE_TELEMETRY_MONGODB_URL` / `CLAUDE_TELEMETRY_MONGODB_DATABASE` — MongoDB target
- `CLAUDE_TELEMETRY_MONGODB_ENABLED` — set to `false` for local-only mode

## Dev Commands

```bash
# Run tests
python3 -m pytest tests/

# Lint
ruff check .

# Import check
python3 -c "from utils import PROJECT_ROOT, get_config; print('OK')"
```

## File Layout

- `utils/config.py` — layered Config class
- `utils/bootstrap.py` — auto-dependency installer
- `utils/mongodb.py` — MongoDB send with proxy/direct routing, connection caching
- `utils/env.py` — `PLUGIN_ROOT` and `PROJECT_ROOT` path constants
- `utils/logging.py` — session log directories, hook logger setup, `log_json()` helper
- `hooks-handlers/event_logger.py` — logs each hook event
- `hooks-handlers/conversation_logger.py` — batches conversation events to MongoDB
- `hooks-handlers/session_start.py` — reads user identity from Config, sends metadata
