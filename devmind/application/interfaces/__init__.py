"""Ports: abstractions the application depends on, owned by this layer."""

from devmind.application.interfaces.document_parser import DocumentParser, DocumentParserRegistry

__all__ = ["DocumentParser", "DocumentParserRegistry"]
