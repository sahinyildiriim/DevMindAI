"""Assembles the Streamlit navigation for DevMind AI."""

from __future__ import annotations

import streamlit as st

from devmind.core import configure_logging
from devmind.presentation.ui.pages import chat, knowledge_base, settings, upload_documents

__all__ = ["run"]


def run() -> None:
    """Configure the page and dispatch to the selected page."""
    configure_logging()
    st.set_page_config(
        page_title="DevMind AI - Ask your documentation", page_icon="📚", layout="wide"
    )

    # Every page module exposes a same-named render() function, so the
    # URL path - otherwise inferred from that name - is set explicitly
    # here to keep the four pages distinct.
    pages = [
        st.Page(chat.render, title="Chat", icon="💬", url_path="chat", default=True),
        st.Page(upload_documents.render, title="Upload Documents", icon="📤", url_path="upload"),
        st.Page(
            knowledge_base.render, title="Knowledge Base", icon="📚", url_path="knowledge-base"
        ),
        st.Page(settings.render, title="Settings", icon="⚙️", url_path="settings"),
    ]
    st.navigation(pages).run()
