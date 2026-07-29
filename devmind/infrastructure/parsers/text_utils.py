"""Text helpers shared by the parser adapters.

Keeping these routines in one place guarantees that a PDF, a DOCX and a
Markdown file all reach the index with identical whitespace and title
conventions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from devmind.domain.exceptions import DocumentParseError

__all__ = ["clean_optional", "derive_title", "normalize_text", "read_text_file"]

# Ordered by likelihood: UTF-8 covers modern sources, the BOM variant is
# common for Windows-authored files, and cp1254 keeps Turkish legacy
# documents readable before falling back to a never-failing codec.
_FALLBACK_ENCODINGS: Final[tuple[str, ...]] = ("utf-8", "utf-8-sig", "cp1254", "latin-1")

_MAX_DERIVED_TITLE_LENGTH: Final[int] = 120

_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def read_text_file(source: Path) -> str:
    """Read a text file, tolerating the encodings found in the wild.

    Args:
        source: Path of the file to read.

    Returns:
        The decoded file content.

    Raises:
        DocumentParseError: If the file cannot be read or decoded.
    """
    for encoding in _FALLBACK_ENCODINGS:
        try:
            return source.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise DocumentParseError(f"Could not read '{source.name}': {exc}") from exc
    raise DocumentParseError(
        f"Could not decode '{source.name}' with any of the supported encodings: "
        f"{', '.join(_FALLBACK_ENCODINGS)}."
    )


def normalize_text(text: str) -> str:
    """Normalise extracted text into a stable canonical form.

    Line endings are unified, trailing spaces removed and runs of blank
    lines collapsed, so that identical content always yields identical
    text regardless of the source format.

    Args:
        text: Raw text produced by a format specific extractor.

    Returns:
        The normalised text.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    without_trailing = _TRAILING_SPACES.sub("", unified)
    return _EXCESS_BLANK_LINES.sub("\n\n", without_trailing).strip()


def clean_optional(value: object) -> str | None:
    """Normalise an optional metadata value into text.

    Document metadata coming from third party libraries is loosely
    typed and frequently blank; this turns anything unusable into
    ``None``.

    Args:
        value: Raw metadata value of any type.

    Returns:
        The stripped string, or ``None`` when empty or absent.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def derive_title(text: str) -> str | None:
    """Derive a title from the first meaningful line of a document.

    Used for formats that carry no title metadata of their own.

    Args:
        text: Normalised document text.

    Returns:
        The first non-empty line when it is short enough to read as a
        heading, otherwise ``None``.
    """
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        return candidate if len(candidate) <= _MAX_DERIVED_TITLE_LENGTH else None
    return None
