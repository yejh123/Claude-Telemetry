"""Shared pytest fixtures for claude-telemetry tests."""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on the path
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary config.json and return its path."""
    config_file = tmp_path / "config.json"

    def _write(data: dict):
        config_file.write_text(json.dumps(data), encoding="utf-8")
        return config_file

    return _write


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all CLAUDE_TELEMETRY_ env vars."""
    prefixes = ("CLAUDE_TELEMETRY_",)
    for key in list(os.environ):
        if any(key.startswith(p) for p in prefixes):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def sample_event_data():
    """Return a sample hook event payload."""
    return {
        "session_id": "abc12345-6789-def0-1234-567890abcdef",
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "/tmp/test.py"},
        "timestamp": "2026-03-11T12:00:00+00:00",
    }


@pytest.fixture
def sample_conversation_events():
    """Return a list of sample conversation events."""
    return [
        {"type": "human", "message": {"role": "user", "content": "Hello"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "Hi there!"}},
        {"type": "human", "message": {"role": "user", "content": "Write a test"}},
    ]
