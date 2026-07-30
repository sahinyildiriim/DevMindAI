"""Settings page: read-only view of the active configuration."""

from __future__ import annotations

import streamlit as st

from devmind.core.config import get_settings

__all__ = ["render"]


def render() -> None:
    """Render the Settings page."""
    st.title("⚙️ Settings")
    st.caption("Read-only view of the active configuration. Edit `.env` and restart to change it.")

    settings = get_settings()

    st.subheader("Microsoft Foundry Local")
    columns = st.columns(2)
    columns[0].metric("Chat model", settings.foundry.chat_model)
    columns[1].metric("Embedding model", settings.foundry.embedding_model)
    st.caption(f"Endpoint: `{settings.foundry.endpoint}`")

    st.subheader("Retrieval")
    columns = st.columns(3)
    columns[0].metric("Top K", settings.retrieval.top_k)
    columns[1].metric("Min. confidence", f"{settings.retrieval.min_score:.0%}")
    columns[2].metric("Chunk size", settings.retrieval.chunk_size)

    st.subheader("Storage")
    st.caption(f"Knowledge base: `{settings.database.path}`")
    st.caption(f"Documents directory: `{settings.documents.source_directory}`")
