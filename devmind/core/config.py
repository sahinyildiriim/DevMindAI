"""Typed, immutable application configuration.

Configuration is read once from the process environment (optionally
seeded by a ``.env`` file) and exposed as frozen dataclasses. Every
section owns its parsing and validation logic, which keeps the module
open for extension but closed for modification when a new setting group
is introduced.

No other module is allowed to call :func:`os.getenv` directly; this is
the single source of truth for runtime settings.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

from devmind import __version__
from devmind.core.exceptions import ConfigurationError

__all__ = [
    "PROJECT_ROOT",
    "AppConfig",
    "DatabaseConfig",
    "DocumentConfig",
    "FoundryConfig",
    "LoggingConfig",
    "RetrievalConfig",
    "Settings",
    "get_settings",
]

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
"""Absolute path of the repository root, used to resolve relative paths."""

_ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"
_VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)
_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})


# --------------------------------------------------------------------------- #
# Environment helpers
# --------------------------------------------------------------------------- #
def _read_env[T](key: str, default: T, converter: Callable[[str], T]) -> T:
    """Read ``key`` from the environment and convert it.

    Args:
        key: Environment variable name.
        default: Value returned when the variable is unset or blank.
        converter: Callable turning the raw string into the target type.

    Returns:
        The converted value, or ``default`` when the variable is absent.

    Raises:
        ConfigurationError: If the raw value cannot be converted.
    """
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return converter(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Environment variable '{key}' has an invalid value: {raw!r}"
        ) from exc


def _to_bool(value: str) -> bool:
    """Convert a textual flag into a boolean.

    Args:
        value: Raw string such as ``"true"`` or ``"0"``.

    Returns:
        The parsed boolean.

    Raises:
        ValueError: If the string is not a recognised boolean literal.
    """
    normalized = value.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"not a boolean flag: {value!r}")


def _to_path(value: str) -> Path:
    """Convert a raw path string into an absolute :class:`Path`.

    Relative paths are anchored to :data:`PROJECT_ROOT` so that the
    application behaves identically regardless of the working directory.

    Args:
        value: Raw path, absolute or relative, possibly using ``~``.

    Returns:
        An absolute, normalised path.
    """
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return Path(os.path.normpath(path))


def _require(condition: bool, message: str) -> None:
    """Assert a configuration invariant.

    Args:
        condition: Invariant that must hold.
        message: Human readable description used in the raised error.

    Raises:
        ConfigurationError: If ``condition`` is falsy.
    """
    if not condition:
        raise ConfigurationError(message)


# --------------------------------------------------------------------------- #
# Configuration sections
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AppConfig:
    """General application metadata and runtime mode."""

    name: str = "DevMind AI"
    version: str = __version__
    environment: str = "development"
    debug: bool = False

    def __post_init__(self) -> None:
        """Validate the runtime mode."""
        _require(bool(self.environment), "Application environment must not be empty.")

    @classmethod
    def from_env(cls) -> AppConfig:
        """Build the section from environment variables."""
        return cls(
            environment=_read_env("DEVMIND_ENV", "development", str),
            debug=_read_env("DEVMIND_DEBUG", False, _to_bool),
        )


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Logging destinations, verbosity and rotation policy."""

    level: str = "INFO"
    directory: Path = PROJECT_ROOT / "logs"
    file_name: str = "devmind.log"
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 5
    console_enabled: bool = True

    def __post_init__(self) -> None:
        """Validate verbosity and rotation limits."""
        _require(
            self.level in _VALID_LOG_LEVELS,
            f"Log level must be one of {sorted(_VALID_LOG_LEVELS)}, got {self.level!r}.",
        )
        _require(bool(self.file_name), "Log file name must not be empty.")
        _require(self.max_bytes > 0, "Log rotation size must be greater than zero.")
        _require(self.backup_count >= 0, "Log backup count must not be negative.")

    @property
    def file_path(self) -> Path:
        """Absolute path of the active log file."""
        return self.directory / self.file_name

    @classmethod
    def from_env(cls) -> LoggingConfig:
        """Build the section from environment variables."""
        return cls(
            level=_read_env("DEVMIND_LOG_LEVEL", "INFO", str).upper(),
            directory=_read_env("DEVMIND_LOG_DIR", PROJECT_ROOT / "logs", _to_path),
            file_name=_read_env("DEVMIND_LOG_FILE", "devmind.log", str),
            max_bytes=_read_env("DEVMIND_LOG_MAX_BYTES", 5 * 1024 * 1024, int),
            backup_count=_read_env("DEVMIND_LOG_BACKUP_COUNT", 5, int),
            console_enabled=_read_env("DEVMIND_LOG_CONSOLE", True, _to_bool),
        )


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Location of the local SQLite knowledge base."""

    path: Path = PROJECT_ROOT / "data" / "db" / "devmind.db"

    def __post_init__(self) -> None:
        """Validate that a database file name is present."""
        _require(bool(self.path.name), "Database path must point to a file.")

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        """Build the section from environment variables."""
        return cls(
            path=_read_env("DEVMIND_DB_PATH", PROJECT_ROOT / "data" / "db" / "devmind.db", _to_path)
        )


@dataclass(frozen=True, slots=True)
class FoundryConfig:
    """Connection and generation settings for Microsoft Foundry Local."""

    endpoint: str = "http://localhost:5273/v1"
    api_key: str = field(default="foundry-local", repr=False)
    chat_model: str = "phi-3.5-mini"
    embedding_model: str = "all-minilm-l6-v2"
    timeout_seconds: float = 120.0
    max_tokens: int = 1024
    temperature: float = 0.1
    embedding_batch_size: int = 16
    max_retries: int = 2

    def __post_init__(self) -> None:
        """Validate the endpoint URL and generation parameters."""
        _require(
            self.endpoint.startswith(("http://", "https://")),
            f"Foundry endpoint must be an HTTP(S) URL, got {self.endpoint!r}.",
        )
        _require(bool(self.chat_model), "Foundry chat model must not be empty.")
        _require(bool(self.embedding_model), "Foundry embedding model must not be empty.")
        _require(self.timeout_seconds > 0, "Foundry timeout must be greater than zero.")
        _require(self.max_tokens > 0, "Foundry max tokens must be greater than zero.")
        _require(
            0.0 <= self.temperature <= 2.0,
            "Foundry temperature must be between 0.0 and 2.0.",
        )
        _require(
            self.embedding_batch_size > 0,
            "Foundry embedding batch size must be greater than zero.",
        )
        _require(self.max_retries >= 0, "Foundry max retries must not be negative.")

    @classmethod
    def from_env(cls) -> FoundryConfig:
        """Build the section from environment variables."""
        return cls(
            endpoint=_read_env("DEVMIND_FOUNDRY_ENDPOINT", "http://localhost:5273/v1", str),
            api_key=_read_env("DEVMIND_FOUNDRY_API_KEY", "foundry-local", str),
            chat_model=_read_env("DEVMIND_FOUNDRY_CHAT_MODEL", "phi-3.5-mini", str),
            embedding_model=_read_env("DEVMIND_FOUNDRY_EMBEDDING_MODEL", "all-minilm-l6-v2", str),
            timeout_seconds=_read_env("DEVMIND_FOUNDRY_TIMEOUT_SECONDS", 120.0, float),
            max_tokens=_read_env("DEVMIND_FOUNDRY_MAX_TOKENS", 1024, int),
            temperature=_read_env("DEVMIND_FOUNDRY_TEMPERATURE", 0.1, float),
            embedding_batch_size=_read_env("DEVMIND_FOUNDRY_EMBEDDING_BATCH_SIZE", 16, int),
            max_retries=_read_env("DEVMIND_FOUNDRY_MAX_RETRIES", 2, int),
        )


@dataclass(frozen=True, slots=True)
class DocumentConfig:
    """Ingestion boundaries for the local documentation corpus."""

    source_directory: Path = PROJECT_ROOT / "data" / "documents"
    max_file_size_mb: int = 25

    def __post_init__(self) -> None:
        """Validate the ingestion size limit."""
        _require(self.max_file_size_mb > 0, "Max file size must be greater than zero.")

    @property
    def max_file_size_bytes(self) -> int:
        """Maximum accepted file size expressed in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> DocumentConfig:
        """Build the section from environment variables."""
        return cls(
            source_directory=_read_env(
                "DEVMIND_DOCUMENTS_DIR", PROJECT_ROOT / "data" / "documents", _to_path
            ),
            max_file_size_mb=_read_env("DEVMIND_MAX_FILE_SIZE_MB", 25, int),
        )


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    """Chunking and retrieval parameters of the RAG pipeline."""

    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 5
    min_score: float = 0.25

    def __post_init__(self) -> None:
        """Validate chunking and ranking parameters."""
        _require(self.chunk_size > 0, "Chunk size must be greater than zero.")
        _require(
            0 <= self.chunk_overlap < self.chunk_size,
            "Chunk overlap must be non-negative and smaller than the chunk size.",
        )
        _require(self.top_k > 0, "Top-K must be greater than zero.")
        _require(0.0 <= self.min_score <= 1.0, "Minimum score must be between 0.0 and 1.0.")

    @classmethod
    def from_env(cls) -> RetrievalConfig:
        """Build the section from environment variables."""
        return cls(
            chunk_size=_read_env("DEVMIND_CHUNK_SIZE", 1000, int),
            chunk_overlap=_read_env("DEVMIND_CHUNK_OVERLAP", 150, int),
            top_k=_read_env("DEVMIND_TOP_K", 5, int),
            min_score=_read_env("DEVMIND_MIN_SCORE", 0.25, float),
        )


# --------------------------------------------------------------------------- #
# Aggregate root
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Settings:
    """Aggregate of every configuration section."""

    app: AppConfig
    logging: LoggingConfig
    database: DatabaseConfig
    foundry: FoundryConfig
    documents: DocumentConfig
    retrieval: RetrievalConfig

    @classmethod
    def load(cls, env_file: Path | None = _ENV_FILE) -> Settings:
        """Load settings from an optional ``.env`` file and the environment.

        Real environment variables always win over ``.env`` entries, which
        keeps container and CI overrides predictable.

        Args:
            env_file: Optional ``.env`` file to seed the environment with.
                Pass ``None`` to read the process environment only.

        Returns:
            A fully validated :class:`Settings` instance.

        Raises:
            ConfigurationError: If any value is malformed or out of range.
        """
        if env_file is not None and env_file.is_file():
            load_dotenv(env_file, override=False, encoding="utf-8")
        return cls(
            app=AppConfig.from_env(),
            logging=LoggingConfig.from_env(),
            database=DatabaseConfig.from_env(),
            foundry=FoundryConfig.from_env(),
            documents=DocumentConfig.from_env(),
            retrieval=RetrievalConfig.from_env(),
        )

    def ensure_directories(self) -> None:
        """Create the writable directories the application depends on.

        Directory creation is an explicit side effect kept out of
        :meth:`load` so that configuration stays pure and testable.
        """
        for directory in (
            self.logging.directory,
            self.database.path.parent,
            self.documents.source_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    The result is cached, so configuration is parsed and validated exactly
    once per process.

    Returns:
        The shared :class:`Settings` instance.
    """
    return Settings.load()
