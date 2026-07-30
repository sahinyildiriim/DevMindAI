"""Knowledge Base page: what has been indexed, and its embedding status."""

from __future__ import annotations

import streamlit as st

from devmind.application.dto import KnowledgeBaseStats
from devmind.core.exceptions import DevMindError
from devmind.domain.value_objects import DocumentMetadata
from devmind.presentation.ui.services import get_knowledge_base_service

__all__ = ["render"]


def render() -> None:
    """Render the Knowledge Base page."""
    st.title("📚 Knowledge Base")

    service = get_knowledge_base_service()
    try:
        stats = service.get_stats()
        documents = service.list_documents()
    except DevMindError as exc:
        st.error(f"Could not read the knowledge base: {exc}")
        return

    _render_stats(stats)
    st.divider()
    _render_documents(documents)


def _render_stats(stats: KnowledgeBaseStats) -> None:
    """Show document/chunk counts and the embedding model's status.

    Args:
        stats: Snapshot of the knowledge base to display.
    """
    columns = st.columns(3)
    columns[0].metric("Documents", stats.document_count)
    columns[1].metric("Chunks", stats.chunk_count)
    columns[2].metric(
        "Embedded",
        f"{stats.embedded_count} / {stats.chunk_count}",
        help="Chunks with an embedding from the currently configured model.",
    )

    if stats.indexed_embedding_model is None:
        st.info(f"Model configured: **{stats.configured_embedding_model}**. Nothing embedded yet.")
    elif stats.is_embedding_model_current:
        st.success(f"Embeddings are up to date with **{stats.configured_embedding_model}**.")
    else:
        st.warning(
            f"Stored embeddings were produced with **{stats.indexed_embedding_model}**, but "
            f"**{stats.configured_embedding_model}** is now configured. "
            "Re-run indexing to bring the knowledge base up to date."
        )

    if stats.pending_embedding_count:
        st.caption(f"{stats.pending_embedding_count} chunk(s) awaiting embedding.")


def _render_documents(documents: tuple[DocumentMetadata, ...]) -> None:
    """List the indexed documents in a table.

    Args:
        documents: Documents to display, in the order they were read.
    """
    st.subheader("Indexed documents")
    if not documents:
        st.caption("No documents indexed yet. Use the Upload Documents page to add some.")
        return

    st.dataframe(
        [
            {
                "Title": metadata.display_title,
                "Format": metadata.document_format.value,
                "Size (KB)": round(metadata.size_bytes / 1024, 1),
                "Modified": metadata.modified_at.strftime("%Y-%m-%d %H:%M"),
            }
            for metadata in documents
        ],
        width="stretch",
        hide_index=True,
    )
