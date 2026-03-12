# Claude Telemetry Plugin

A Claude Code plugin that automatically captures every hook event, conversation transcript, and session metadata during your coding sessions. Data is logged locally to JSONL files and sent to MongoDB via a proxy server for centralized analysis.

## What It Captures

| Handler | Trigger | Data |
|---|---|---|
| **event_logger** | All hook events | Tool calls, permissions, notifications, subagent activity |
| **conversation_logger** | UserPromptSubmit, Stop, Notification, SessionEnd | Full conversation transcript (user + assistant messages) |
| **session_start** | SessionStart | User identity (username, email) and session metadata |

## Quick Start

### 1. Clone the repository

```bash
git clone <repo-url>
cd claude-telemetry
```

### 2. Run the installer

```bash
python install.py
```

The installer will:
- Copy the plugin into `~/.claude/plugins/`
- Register it as a local marketplace plugin
- Install Python dependencies
- Prompt you for username and email
- Test the proxy server connection

### 3. Restart Claude Code

The plugin loads automatically on the next session start.

## Installation by Interface

### Claude Code CLI

```bash
# Install from local directory
python install.py

# Or load temporarily for development
claude --plugin-dir ./claude-telemetry
```

### Claude Desktop

1. Run `python install.py` in your terminal.
2. Restart Claude Desktop.
3. The plugin appears under **Code** tab > **+** > **Plugins**.

### VS Code (Claude Code Extension)

1. Run `python install.py` in the VS Code integrated terminal.
2. Reload the window (`Cmd+Shift+P` > "Developer: Reload Window").
3. The plugin appears when you type `/plugins` in the Claude Code prompt.

## Configuration

The installer writes a `.env` file with your settings. To reconfigure later, edit the `.env` file at the installed plugin location or re-run `python install.py`.

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_TELEMETRY_USERNAME` | `""` | Your username for session metadata |
| `CLAUDE_TELEMETRY_EMAIL` | `""` | Your email for session metadata |
| `CLAUDE_TELEMETRY_MONGODB_PROXY_URL` | `""` | MongoDB proxy server URL |
| `CLAUDE_TELEMETRY_MONGODB_DATABASE` | `""` | Target MongoDB database name |
| `CLAUDE_TELEMETRY_MONGODB_ENABLED` | `true` | Set `false` for local-only mode |

## Local-Only Mode

Set `CLAUDE_TELEMETRY_MONGODB_ENABLED=false` in your `.env`. Events still log to `logs/` as JSONL files.

## Development

```bash
# Install dev dependencies
pip install ".[dev]"

# Run tests
python -m pytest tests/

# Lint
ruff check .

# Load plugin without installing
claude --plugin-dir ./claude-telemetry
```

## Troubleshooting

| Issue | Solution |
|---|---|
| Plugin not visible after install | Restart Claude Code; check `~/.claude/settings.json` has `enabledPlugins` entry |
| Proxy connection failed | Verify `CLAUDE_TELEMETRY_MONGODB_PROXY_URL` is reachable |
| Events not appearing in MongoDB | Check `CLAUDE_TELEMETRY_MONGODB_ENABLED` is `true` and database is set |
| Hook not triggering | Verify plugin is enabled via `/plugins` |

## License

MIT — see [LICENSE](LICENSE).
