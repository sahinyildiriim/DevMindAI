"""Unit tests for :mod:`devmind.core.logger`."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from devmind.core import logger as logger_module
from devmind.core.config import LoggingConfig
from devmind.core.logger import ROOT_LOGGER_NAME, configure_logging, get_logger


@pytest.fixture
def logging_config(tmp_path: Path) -> LoggingConfig:
    return LoggingConfig(directory=tmp_path / "logs", console_enabled=False)


@pytest.fixture(autouse=True)
def restore_logging_state() -> Iterator[None]:
    root = logging.getLogger()
    original_handlers = tuple(root.handlers)
    original_level = root.level
    yield
    for handler in tuple(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)
    logger_module._configured = False


def test_configure_logging_creates_log_file(logging_config: LoggingConfig) -> None:
    configure_logging(logging_config, force=True)
    get_logger(__name__).info("sprint zero")

    logging.shutdown()
    assert logging_config.file_path.is_file()
    assert "sprint zero" in logging_config.file_path.read_text(encoding="utf-8")


def test_configure_logging_is_idempotent(logging_config: LoggingConfig) -> None:
    configure_logging(logging_config, force=True)
    handler_count = len(logging.getLogger().handlers)

    configure_logging(logging_config)
    configure_logging(logging_config)

    assert len(logging.getLogger().handlers) == handler_count


def test_get_logger_namespaces_module_names() -> None:
    assert get_logger("devmind.infrastructure").name == "devmind.infrastructure"
    assert get_logger("parsers").name == "devmind.parsers"
    assert get_logger(None).name == ROOT_LOGGER_NAME
