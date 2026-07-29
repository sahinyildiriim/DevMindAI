"""SQLite-backed persistence adapters."""

from devmind.infrastructure.persistence.chunk_repository import SqliteChunkRepository
from devmind.infrastructure.persistence.database import SqliteDatabase, build_database
from devmind.infrastructure.persistence.document_repository import SqliteDocumentRepository
from devmind.infrastructure.persistence.embedding_repository import SqliteEmbeddingRepository
from devmind.infrastructure.persistence.metadata_repository import SqliteMetadataRepository
from devmind.infrastructure.persistence.schema import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "SqliteChunkRepository",
    "SqliteDatabase",
    "SqliteDocumentRepository",
    "SqliteEmbeddingRepository",
    "SqliteMetadataRepository",
    "build_database",
]
