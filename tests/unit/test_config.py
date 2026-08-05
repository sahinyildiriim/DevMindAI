"""Unit tests for :mod:`devmind.core.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmind.core.config import (
    PROJECT_ROOT,
    FoundryConfig,
    LoggingConfig,
    RetrievalConfig,
    Settings,
)
from devmind.core.exceptions import ConfigurationError


def test_load_uses_defaults_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DEVMIND_ENV", "DEVMIND_DEBUG", "DEVMIND_LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.load(env_file=None)

    assert settings.app.environment == "development"
    assert settings.app.debug is False
    assert settings.logging.level == "INFO"


def test_load_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVMIND_ENV", "production")
    monkeypatch.setenv("DEVMIND_DEBUG", "yes")
    monkeypatch.setenv("DEVMIND_LOG_LEVEL", "debug")
    monkeypatch.setenv("DEVMIND_TOP_K", "8")

    settings = Settings.load(env_file=None)

    assert settings.app.environment == "production"
    assert settings.app.debug is True
    assert settings.logging.level == "DEBUG"
    assert settings.retrieval.top_k == 8


def test_disable_thinking_defaults_to_false() -> None:
    assert FoundryConfig().disable_thinking is False


def test_disable_thinking_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVMIND_FOUNDRY_DISABLE_THINKING", "true")

    settings = Settings.load(env_file=None)

    assert settings.foundry.disable_thinking is True


def test_relative_paths_resolve_against_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVMIND_DB_PATH", "data/db/custom.db")

    settings = Settings.load(env_file=None)

    assert settings.database.path == PROJECT_ROOT / "data" / "db" / "custom.db"


def test_invalid_integer_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVMIND_TOP_K", "many")

    with pytest.raises(ConfigurationError, match="DEVMIND_TOP_K"):
        Settings.load(env_file=None)


def test_invalid_boolean_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVMIND_DEBUG", "maybe")

    with pytest.raises(ConfigurationError, match="DEVMIND_DEBUG"):
        Settings.load(env_file=None)


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Log level"):
        LoggingConfig(level="VERBOSE")


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ConfigurationError, match="Chunk overlap"):
        RetrievalConfig(chunk_size=500, chunk_overlap=500)


def test_endpoint_must_be_http_url() -> None:
    with pytest.raises(ConfigurationError, match="HTTP"):
        FoundryConfig(endpoint="localhost:5273")


def test_api_key_is_hidden_from_repr() -> None:
    config = FoundryConfig(api_key="super-secret")

    assert "super-secret" not in repr(config)


def test_configuration_sections_are_immutable() -> None:
    settings = Settings.load(env_file=None)

    with pytest.raises(AttributeError):
        settings.retrieval.top_k = 99  # type: ignore[misc]


def test_ensure_directories_creates_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEVMIND_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DEVMIND_DB_PATH", str(tmp_path / "db" / "devmind.db"))
    monkeypatch.setenv("DEVMIND_DOCUMENTS_DIR", str(tmp_path / "documents"))

    settings = Settings.load(env_file=None)
    settings.ensure_directories()

    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "db").is_dir()
    assert (tmp_path / "documents").is_dir()
