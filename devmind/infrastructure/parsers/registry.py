"""Resolution of the parser responsible for a given file."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from devmind.application.interfaces.document_parser import DocumentParser, DocumentParserRegistry
from devmind.core.config import DocumentConfig, get_settings
from devmind.core.exceptions import ConfigurationError
from devmind.core.logger import get_logger
from devmind.domain.exceptions import UnsupportedFormatError
from devmind.infrastructure.parsers.docx_parser import DocxParser
from devmind.infrastructure.parsers.markdown_parser import MarkdownParser
from devmind.infrastructure.parsers.pdf_parser import PdfParser
from devmind.infrastructure.parsers.text_parser import TextParser

__all__ = ["ParserRegistry", "build_parser_registry"]

_logger = get_logger(__name__)


class ParserRegistry(DocumentParserRegistry):
    """Maps file extensions to parsers through a precomputed index."""

    def __init__(self, parsers: Iterable[DocumentParser]) -> None:
        """Index the given parsers by the extensions they support.

        Args:
            parsers: Parsers to register.

        Raises:
            ConfigurationError: If no parser is supplied, or if two
                parsers claim the same extension.
        """
        index: dict[str, DocumentParser] = {}
        for parser in parsers:
            for extension in parser.document_format.extensions:
                registered = index.get(extension)
                if registered is not None:
                    raise ConfigurationError(
                        f"Extension '{extension}' is claimed by both "
                        f"{type(registered).__name__} and {type(parser).__name__}."
                    )
                index[extension] = parser
        if not index:
            raise ConfigurationError("At least one parser must be registered.")
        self._index = index

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        """Every extension the registered parsers can handle."""
        return tuple(sorted(self._index))

    def get_parser(self, source: Path) -> DocumentParser:
        """Return the parser registered for a file.

        Args:
            source: Path of the file to be parsed.

        Returns:
            The parser bound to the file extension.

        Raises:
            UnsupportedFormatError: If no parser claims the extension.
        """
        parser = self._index.get(source.suffix.lower())
        if parser is None:
            raise UnsupportedFormatError(
                f"No parser is registered for '{source.name}'. "
                f"Supported extensions: {', '.join(self.supported_extensions)}."
            )
        return parser


def build_parser_registry(config: DocumentConfig | None = None) -> ParserRegistry:
    """Create a registry holding every parser DevMind AI ships with.

    Args:
        config: Ingestion settings to apply. Defaults to the active
            application settings.

    Returns:
        A registry covering PDF, DOCX, Markdown and plain text.
    """
    documents = config if config is not None else get_settings().documents
    size_limit = documents.max_file_size_bytes
    registry = ParserRegistry(
        (
            PdfParser(size_limit),
            DocxParser(size_limit),
            MarkdownParser(size_limit),
            TextParser(size_limit),
        )
    )
    _logger.debug(
        "Parser registry ready for extensions: %s", ", ".join(registry.supported_extensions)
    )
    return registry
