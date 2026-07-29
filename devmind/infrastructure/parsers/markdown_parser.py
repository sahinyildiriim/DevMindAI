"""Markdown parser adapter built on the ``markdown`` library."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Final

import markdown

from devmind.domain.value_objects.document_format import DocumentFormat
from devmind.infrastructure.parsers.base import ExtractedContent, FileDocumentParser
from devmind.infrastructure.parsers.text_utils import clean_optional, derive_title, read_text_file

__all__ = ["MarkdownParser"]

# Tags whose content is markup, not prose, and must never be indexed.
_SKIPPED_TAGS: Final[frozenset[str]] = frozenset({"script", "style"})

# Tags that introduce a line break in the plain text rendering.
_BLOCK_TAGS: Final[frozenset[str]] = frozenset(
    {
        "blockquote",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "table",
        "tr",
        "ul",
    }
)
_CELL_TAGS: Final[frozenset[str]] = frozenset({"td", "th"})

_ATX_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*\s*$", re.MULTILINE)

# Front matter is only read when the document opens with a YAML fence.
# Without this guard the "meta" extension would treat an ordinary first
# line such as "Note: read this first" as metadata and drop it from the
# indexed text.
_FRONT_MATTER_FENCE = re.compile(r"^---[ \t]*\r?\n")

_BASE_EXTENSIONS: Final[tuple[str, ...]] = ("tables", "fenced_code")


class MarkdownParser(FileDocumentParser):
    """Renders Markdown to plain text and reads its front matter."""

    @property
    def document_format(self) -> DocumentFormat:
        """Format handled by this parser."""
        return DocumentFormat.MARKDOWN

    def extract(self, source: Path) -> ExtractedContent:
        """Extract prose and front matter from a Markdown file.

        The document is rendered to HTML and then flattened, so that
        syntax markers never reach the index while the reading order of
        lists, tables and code blocks is preserved.

        Args:
            source: Absolute path of the validated Markdown file.

        Returns:
            The plain text and the metadata declared in the front
            matter, falling back to the first heading for the title.
        """
        raw = read_text_file(source)
        has_front_matter = _FRONT_MATTER_FENCE.match(raw) is not None
        extensions = ("meta", *_BASE_EXTENSIONS) if has_front_matter else _BASE_EXTENSIONS
        renderer = markdown.Markdown(extensions=list(extensions))
        html = renderer.convert(raw)
        front_matter: dict[str, list[str]] = getattr(renderer, "Meta", {})

        text = _html_to_text(html)
        return ExtractedContent(
            text=text,
            title=_first_value(front_matter, "title") or _heading_title(raw) or derive_title(text),
            author=_first_value(front_matter, "author"),
        )


def _first_value(front_matter: dict[str, list[str]], key: str) -> str | None:
    """Read a single front matter entry.

    Args:
        front_matter: Metadata collected by the ``meta`` extension.
        key: Entry name, matched case-insensitively.

    Returns:
        The first value of the entry, or ``None`` when absent or blank.
    """
    values = front_matter.get(key) or front_matter.get(key.capitalize())
    return clean_optional(values[0]) if values else None


def _heading_title(raw: str) -> str | None:
    """Read the title from the first Markdown heading.

    Args:
        raw: Raw Markdown source.

    Returns:
        The heading text, or ``None`` when the document has no heading.
    """
    match = _ATX_HEADING.search(raw)
    return clean_optional(match.group("title")) if match else None


def _html_to_text(html: str) -> str:
    """Flatten rendered HTML into readable plain text.

    Args:
        html: HTML produced by the Markdown renderer.

    Returns:
        The text content. Whitespace is left to the shared
        normalisation step applied by the parser template.
    """
    extractor = _HtmlTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text


class _HtmlTextExtractor(HTMLParser):
    """Collects the text nodes of an HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skipped_depth = 0

    @property
    def text(self) -> str:
        """The collected text."""
        return "".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Open a tag, tracking layout breaks and skipped sections."""
        if tag in _SKIPPED_TAGS:
            self._skipped_depth += 1
        elif tag in _BLOCK_TAGS or tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Close a tag, restoring the skip state and layout breaks."""
        if tag in _SKIPPED_TAGS:
            self._skipped_depth = max(0, self._skipped_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")
        elif tag in _CELL_TAGS:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        """Collect a text node unless it belongs to a skipped section."""
        if not self._skipped_depth:
            self._parts.append(data)
