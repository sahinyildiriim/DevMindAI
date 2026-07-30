"""Upload Documents page: add files to the knowledge base."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from devmind.core.config import get_settings
from devmind.core.exceptions import DevMindError
from devmind.domain.value_objects import DocumentFormat
from devmind.presentation.ui.services import get_knowledge_base_service

__all__ = ["render"]


def render() -> None:
    """Render the Upload Documents page."""
    st.title("📤 Upload Documents")
    st.caption(
        "Add PDF, DOCX, Markdown or plain-text files to the knowledge base. "
        "Re-uploading an unchanged file is skipped automatically."
    )

    extensions = [extension.lstrip(".") for extension in DocumentFormat.supported_extensions()]
    uploaded_files = st.file_uploader(
        "Choose one or more documents", type=extensions, accept_multiple_files=True
    )

    if uploaded_files and st.button("Index documents", type="primary"):
        _index_uploaded_files(uploaded_files)


def _index_uploaded_files(uploaded_files: list[UploadedFile]) -> None:
    """Save each uploaded file, index it, then embed whatever is pending.

    Kept as a single function, rather than split around the status
    container, because Streamlit does not publish a stable type for
    what ``st.status`` returns - only the context manager producing it.

    Args:
        uploaded_files: Files selected in the uploader widget.
    """
    service = get_knowledge_base_service()
    destination = get_settings().documents.source_directory
    destination.mkdir(parents=True, exist_ok=True)

    any_new_chunks = False
    with st.status("Indexing documents...", expanded=True) as status:
        for uploaded_file in uploaded_files:
            # Only the file name is trusted, never any path the browser
            # might send, so an upload can never write outside the
            # documents directory.
            target = destination / Path(uploaded_file.name).name
            try:
                target.write_bytes(uploaded_file.getvalue())
                result = service.index_document(target)
            except DevMindError as exc:
                status.write(f":x: **{uploaded_file.name}**: {exc}")
                continue

            if result.was_skipped:
                status.write(
                    f":arrows_counterclockwise: **{uploaded_file.name}**: unchanged, skipped"
                )
            else:
                status.write(
                    f":white_check_mark: **{uploaded_file.name}**: {result.chunks_indexed} chunk(s)"
                )
                any_new_chunks = True

        if any_new_chunks:
            status.write("Embedding new chunks...")
            try:
                run = service.embed_pending()
            except DevMindError as exc:
                status.write(f":x: Embedding failed: {exc}")
            else:
                status.write(f"Embedded {run.embedded} chunk(s) in {run.batches} batch(es).")

        status.update(label="Indexing complete", state="complete")
