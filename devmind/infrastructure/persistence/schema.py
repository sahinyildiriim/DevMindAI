"""Schema of the local SQLite knowledge base.

The schema is intentionally small and fully normalised: a document is
stored once, its chunks reference it, and an embedding references the
chunk it describes. Deleting a document therefore removes everything
derived from it through cascades rather than through application code.

Derived values (file name, character counts) are never stored, so a
fact can never disagree with itself.
"""

from __future__ import annotations

from typing import Final

__all__ = ["SCHEMA_STATEMENTS", "SCHEMA_VERSION", "SCHEMA_VERSION_KEY"]

SCHEMA_VERSION: Final[str] = "1"
SCHEMA_VERSION_KEY: Final[str] = "schema_version"

SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    # Knowledge base level key/value state, including the schema version.
    """
    CREATE TABLE IF NOT EXISTS metadata (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    # One row per indexed file. The source path is the natural key: the
    # surrogate id exists only to keep foreign keys compact and never
    # leaves the persistence layer.
    """
    CREATE TABLE IF NOT EXISTS documents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        source_path     TEXT    NOT NULL UNIQUE,
        document_format TEXT    NOT NULL,
        size_bytes      INTEGER NOT NULL,
        checksum        TEXT    NOT NULL,
        modified_at     TEXT    NOT NULL,
        title           TEXT,
        author          TEXT,
        page_count      INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documents_checksum ON documents (checksum)",
    # One row per chunk. chunk_index keeps reading order explicit rather
    # than relying on insertion order.
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id     TEXT    PRIMARY KEY,
        document_id  INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
        chunk_index  INTEGER NOT NULL,
        content      TEXT    NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset   INTEGER NOT NULL,
        UNIQUE (document_id, chunk_index)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id)",
    # At most one vector per chunk. The model is stored alongside it
    # because vectors are only comparable within the same model.
    """
    CREATE TABLE IF NOT EXISTS embeddings (
        chunk_id   TEXT    PRIMARY KEY REFERENCES chunks (chunk_id) ON DELETE CASCADE,
        model      TEXT    NOT NULL,
        dimensions INTEGER NOT NULL,
        vector     BLOB    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings (model)",
)
