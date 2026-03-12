"""Unit tests for the Config system."""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from utils.config import Config  # noqa: E402


class TestDefaults:
    """Config returns sensible defaults when no file or env vars exist."""

    def test_mongodb_url_default(self, clean_env, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexistent.json", load_dotenv=False)
        assert cfg.mongodb_url == ""

    def test_mongodb_enabled_default(self, clean_env, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexistent.json", load_dotenv=False)
        assert cfg.mongodb_enabled is True

    def test_is_mongodb_configured_false_by_default(self, clean_env, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexistent.json", load_dotenv=False)
        assert cfg.is_mongodb_configured is False


class TestFileLoading:
    """Config reads values from config.json."""

    def test_reads_mongodb_url(self, clean_env, tmp_config):
        path = tmp_config({"mongodb_url": "mongodb://localhost:27017"})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.mongodb_url == "mongodb://localhost:27017"

    def test_reads_mongodb_database(self, clean_env, tmp_config):
        path = tmp_config({"mongodb_database": "test_db"})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.mongodb_database == "test_db"

    def test_is_mongodb_configured_true(self, clean_env, tmp_config):
        path = tmp_config({"mongodb_url": "mongodb://x", "mongodb_database": "db"})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.is_mongodb_configured is True

    def test_ignores_corrupt_file(self, clean_env, tmp_path):
        bad_file = tmp_path / "config.json"
        bad_file.write_text("not json!!!", encoding="utf-8")
        cfg = Config(config_path=bad_file, load_dotenv=False)
        assert cfg.mongodb_url == ""


class TestEnvOverride:
    """Environment variables override config.json values."""

    def test_prefixed_env_overrides_file(self, clean_env, tmp_config, monkeypatch):
        path = tmp_config({"mongodb_url": "from_file"})
        monkeypatch.setenv("CLAUDE_TELEMETRY_MONGODB_URL", "from_env")
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.mongodb_url == "from_env"

    def test_env_overrides_default(self, clean_env, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELEMETRY_MONGODB_DATABASE", "from_env")
        cfg = Config(config_path=tmp_path / "nope.json", load_dotenv=False)
        assert cfg.mongodb_database == "from_env"


class TestBooleanCoercion:
    """Boolean values are properly coerced from strings."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("", False),
        ],
    )
    def test_boolean_string_coercion(self, clean_env, tmp_config, value, expected):
        path = tmp_config({"mongodb_enabled": value})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.mongodb_enabled is expected

    def test_boolean_from_env(self, clean_env, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELEMETRY_MONGODB_ENABLED", "false")
        cfg = Config(config_path=tmp_path / "nope.json", load_dotenv=False)
        assert cfg.mongodb_enabled is False

    def test_native_bool_in_json(self, clean_env, tmp_config):
        path = tmp_config({"mongodb_enabled": False})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.mongodb_enabled is False


class TestUser:
    """User identity fields are read from file and env vars."""

    def test_email_default(self, clean_env, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexistent.json", load_dotenv=False)
        assert cfg.email == ""

    def test_username_default(self, clean_env, tmp_path):
        cfg = Config(config_path=tmp_path / "nonexistent.json", load_dotenv=False)
        assert cfg.username == ""

    def test_email_from_env(self, clean_env, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELEMETRY_EMAIL", "alice@example.com")
        cfg = Config(config_path=tmp_path / "nope.json", load_dotenv=False)
        assert cfg.email == "alice@example.com"

    def test_username_from_env(self, clean_env, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELEMETRY_USERNAME", "user-42")
        cfg = Config(config_path=tmp_path / "nope.json", load_dotenv=False)
        assert cfg.username == "user-42"

    def test_email_from_file(self, clean_env, tmp_config):
        path = tmp_config({"email": "bob@example.com"})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.email == "bob@example.com"

    def test_username_from_file(self, clean_env, tmp_config):
        path = tmp_config({"username": "user-99"})
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.username == "user-99"

    def test_env_overrides_file_for_email(self, clean_env, tmp_config, monkeypatch):
        path = tmp_config({"email": "from_file@example.com"})
        monkeypatch.setenv("CLAUDE_TELEMETRY_EMAIL", "from_env@example.com")
        cfg = Config(config_path=path, load_dotenv=False)
        assert cfg.email == "from_env@example.com"


class TestPrecedence:
    """Full precedence chain: env > file > default."""

    def test_env_beats_file_beats_default(self, clean_env, tmp_config, monkeypatch):
        # Default is True for mongodb_enabled
        path = tmp_config({"mongodb_enabled": False})
        cfg_file = Config(config_path=path, load_dotenv=False)
        assert cfg_file.mongodb_enabled is False  # file beats default

        monkeypatch.setenv("CLAUDE_TELEMETRY_MONGODB_ENABLED", "true")
        cfg_env = Config(config_path=path, load_dotenv=False)
        assert cfg_env.mongodb_enabled is True  # env beats file
