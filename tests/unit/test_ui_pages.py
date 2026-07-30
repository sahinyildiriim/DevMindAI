"""Smoke tests for the Streamlit pages: each renders without raising.

Pages are exercised through :class:`streamlit.testing.v1.AppTest`, which
runs the real module - including its top-level imports - in a simulated
Streamlit session. ``AppTest.from_function`` was considered but rejected:
it re-executes only the function's own source with no module context,
which would demand imports live inside every ``render()`` instead of at
module level, against this project's style everywhere else.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


@pytest.fixture(autouse=True)
def isolated_knowledge_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every page at a private, temporary knowledge base.

    ``st.cache_resource`` caches the Chat/Knowledge Base services across
    reruns for the life of the process, which is exactly what production
    wants but would leak a database between tests; clearing it here
    keeps each test's knowledge base isolated from the others.
    """
    monkeypatch.setenv("DEVMIND_DB_PATH", str(tmp_path / "devmind.db"))
    monkeypatch.setenv("DEVMIND_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DEVMIND_DOCUMENTS_DIR", str(tmp_path / "documents"))
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def render_page(module_name: str) -> AppTest:
    """Run a page module's ``render()`` in a simulated Streamlit session.

    Args:
        module_name: Name of the module under
            ``devmind.presentation.ui.pages``.

    Returns:
        The app's state after running.
    """
    source = f"from devmind.presentation.ui.pages import {module_name}\n{module_name}.render()"
    return AppTest.from_string(source).run()


def test_the_navigation_entry_point_runs_without_error() -> None:
    """app.py is what 'streamlit run app.py' actually executes."""
    at = AppTest.from_file("app.py").run()

    assert not at.exception
    assert at.title[0].value == "💬 Chat"


def test_chat_page_renders_with_no_prior_conversation() -> None:
    at = render_page("chat")

    assert not at.exception
    assert at.title[0].value == "💬 Chat"
    assert at.chat_input


def test_upload_documents_page_renders_the_uploader() -> None:
    at = render_page("upload_documents")

    assert not at.exception
    assert at.title[0].value == "📤 Upload Documents"
    assert at.file_uploader


def test_knowledge_base_page_renders_an_empty_index() -> None:
    at = render_page("knowledge_base")

    assert not at.exception
    assert at.title[0].value == "📚 Knowledge Base"
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Documents"] == "0"
    assert metrics["Chunks"] == "0"
    assert any("No documents indexed yet" in caption.value for caption in at.caption)


def test_knowledge_base_page_reflects_an_indexed_document(tmp_path: Path) -> None:
    # Indexing and rendering both run inside the one simulated script: a
    # cache_resource-backed service built outside of any AppTest-run
    # script can leave its internal lock in a state that later hangs a
    # script that reads the same cache.
    source = tmp_path / "routing.md"
    source.write_text(
        "# Routing\n\nEndpoint routing matches incoming requests.\n", encoding="utf-8"
    )
    script = (
        "from pathlib import Path\n"
        "from devmind.presentation.ui.pages import knowledge_base\n"
        "from devmind.presentation.ui.services import get_knowledge_base_service\n"
        f"get_knowledge_base_service().index_document(Path(r'{source}'))\n"
        "knowledge_base.render()\n"
    )
    at = AppTest.from_string(script).run()

    assert not at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Documents"] == "1"
    assert metrics["Chunks"] == "1"
    rows = at.dataframe[0].value.to_dict("records")
    assert rows[0]["Title"] == "Routing"


def test_settings_page_shows_the_configured_models() -> None:
    at = render_page("settings")

    assert not at.exception
    assert at.title[0].value == "⚙️ Settings"
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Chat model"] == "phi-3.5-mini"
    assert metrics["Embedding model"] == "all-minilm-l6-v2"


# --------------------------------------------------------------------------- #
# Uploading a real file, against the real (unreachable) Foundry Local
# --------------------------------------------------------------------------- #
# A connection attempt against an absent Foundry Local retries with
# backoff before the openai client gives up, comfortably longer than
# AppTest's 3-second default; these two tests raise it accordingly.
_UPLOAD_TIMEOUT_SECONDS = 25


def test_uploading_a_document_indexes_it_and_reports_the_embedding_failure() -> None:
    at = AppTest.from_string(
        "from devmind.presentation.ui.pages import upload_documents\nupload_documents.render()",
        default_timeout=_UPLOAD_TIMEOUT_SECONDS,
    ).run()
    at.file_uploader[0].upload(
        "routing.md", b"# Routing\n\nEndpoint routing matches incoming requests.\n", "text/markdown"
    )
    at.run()

    at.button[0].click().run()

    assert not at.exception
    messages = [element.value for element in at.markdown]
    assert any("routing.md" in message and "1 chunk" in message for message in messages)
    # Foundry Local is not running in this environment: the failure must
    # be reported in the status container, not raised.
    assert any("Cannot reach the embedding model" in message for message in messages)


def test_an_os_rejected_file_name_is_reported_without_crashing_the_page() -> None:
    at = AppTest.from_string(
        "from devmind.presentation.ui.pages import upload_documents\nupload_documents.render()",
        default_timeout=_UPLOAD_TIMEOUT_SECONDS,
    ).run()
    # "<" and ">" are reserved characters no Windows file name may
    # contain, so writing the upload to disk raises OSError.
    at.file_uploader[0].upload("report<1>.md", b"content", "text/markdown")
    at.run()

    at.button[0].click().run()

    assert not at.exception
    messages = [element.value for element in at.markdown]
    assert any("report<1>.md" in message for message in messages)
