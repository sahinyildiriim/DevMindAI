"""Process-wide Streamlit resources.

Streamlit reruns the page script on every interaction, so anything that
opens a connection or a client must be built once and reused, not
reconstructed on every keystroke. :func:`st.cache_resource` is
Streamlit's mechanism for exactly that: the decorated function runs
once per server process and every rerun receives the same instance.
"""

from __future__ import annotations

import streamlit as st

from devmind.infrastructure.chat_service import ChatService, build_chat_service
from devmind.infrastructure.knowledge_base_service import (
    KnowledgeBaseService,
    build_knowledge_base_service,
)

__all__ = ["get_chat_service", "get_knowledge_base_service"]


@st.cache_resource(show_spinner=False)
def get_chat_service() -> ChatService:
    """Return the process-wide Chat Service, built on first use."""
    return build_chat_service()


@st.cache_resource(show_spinner=False)
def get_knowledge_base_service() -> KnowledgeBaseService:
    """Return the process-wide Knowledge Base Service, built on first use.

    A separate connection from :func:`get_chat_service`'s: SQLite's
    write-ahead log lets both coexist safely, which is simpler than
    sharing one connection and its lifecycle between two independent
    services.
    """
    return build_knowledge_base_service()
