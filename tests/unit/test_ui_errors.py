"""Unit tests for the shared UI error logging helper."""

from __future__ import annotations

import logging

import pytest

from devmind.domain.exceptions import StorageError
from devmind.presentation.ui.errors import log_and_format


def test_the_exception_message_is_returned_unchanged() -> None:
    assert log_and_format("Reading the knowledge base", StorageError("disk is full")) == (
        "disk is full"
    )


def test_the_failure_is_logged_with_its_context(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="devmind"):
        log_and_format("Reading the knowledge base", StorageError("disk is full"))

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "WARNING"
    assert "Reading the knowledge base" in record.getMessage()
    assert "disk is full" in record.getMessage()
