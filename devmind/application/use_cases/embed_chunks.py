"""Give every stored chunk an embedding."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Final

from devmind.application.dto.embedding_run import EmbeddingRun
from devmind.application.interfaces.embedding_provider import EmbeddingProvider
from devmind.core.logger import get_logger
from devmind.domain.exceptions import EmbeddingError
from devmind.domain.repositories.chunk_repository import ChunkRepository
from devmind.domain.repositories.embedding_repository import EmbeddingRepository
from devmind.domain.repositories.metadata_repository import MetadataRepository
from devmind.domain.value_objects.embedding import Embedding

__all__ = ["EMBEDDING_MODEL_KEY", "EmbedChunksUseCase", "ProgressCallback"]

_logger = get_logger(__name__)

EMBEDDING_MODEL_KEY: Final[str] = "embedding_model"
"""Metadata entry recording which model the stored vectors come from."""

ProgressCallback = Callable[[int, int, str], None]
"""Called after each batch with (embedded, pending, current document title)."""


class EmbedChunksUseCase:
    """Embeds the chunks that do not have a vector yet.

    The run is resumable by construction: pending work is derived from
    the knowledge base rather than tracked in memory, so a batch that
    fails leaves everything already written in place and a later run
    simply continues. Switching to another model makes every chunk
    pending again, so no index ever mixes vectors from two models.
    """

    def __init__(
        self,
        chunks: ChunkRepository,
        embeddings: EmbeddingRepository,
        metadata: MetadataRepository,
        provider: EmbeddingProvider,
        batch_size: int,
    ) -> None:
        """Initialise the use case.

        Args:
            chunks: Source of the chunks to embed.
            embeddings: Destination of the produced vectors.
            metadata: Store recording the model in use.
            provider: Service turning text into vectors.
            batch_size: Number of chunks embedded and written per step.

        Raises:
            ValueError: If the batch size is not positive.
        """
        if batch_size <= 0:
            raise ValueError("Batch size must be greater than zero.")
        self._chunks = chunks
        self._embeddings = embeddings
        self._metadata = metadata
        self._provider = provider
        self._batch_size = batch_size

    def execute(self, on_progress: ProgressCallback | None = None) -> EmbeddingRun:
        """Embed every pending chunk and store the vectors.

        Args:
            on_progress: Called after each batch is written, with the
                number of chunks embedded so far, the total pending at
                the start of the run, and the title of the document the
                batch's last chunk belongs to.

        Returns:
            What the run accomplished.

        Raises:
            EmbeddingError: If the model service fails. Batches written
                before the failure stay in the knowledge base.
            StorageError: If the knowledge base cannot be read or
                written.
        """
        model = self._provider.model
        started_at = perf_counter()
        pending = self._chunks.count_pending_embedding(model)

        if not pending:
            _logger.info("Every chunk already has an embedding from '%s'", model)
            return EmbeddingRun(model=model, embedded=0, batches=0, duration_seconds=0.0)

        _logger.info("Embedding %d chunks with '%s'", pending, model)
        embedded = 0
        batches = 0

        while batch := self._chunks.list_pending_embedding(model, self._batch_size):
            vectors = self._provider.embed([chunk.content for chunk in batch])
            self._assert_stamped_with(vectors, model)
            self._embeddings.save_many(
                dict(zip((chunk.chunk_id for chunk in batch), vectors, strict=True))
            )
            embedded += len(batch)
            batches += 1
            _logger.info(
                "Embedded %d/%d chunks (%d%%)", embedded, pending, embedded * 100 // pending
            )
            if on_progress is not None:
                on_progress(embedded, pending, batch[-1].metadata.display_title)

        self._metadata.put(EMBEDDING_MODEL_KEY, model)
        duration = perf_counter() - started_at
        _logger.info(
            "Embedded %d chunks in %d batches in %.1fs with '%s'",
            embedded,
            batches,
            duration,
            model,
        )
        return EmbeddingRun(
            model=model, embedded=embedded, batches=batches, duration_seconds=duration
        )

    @staticmethod
    def _assert_stamped_with(vectors: Sequence[Embedding], model: str) -> None:
        """Verify that the provider honoured its own model identifier.

        Chunks stay pending until an embedding from ``model`` exists for
        them, so a provider returning some other name would loop
        forever. Failing loudly here turns that into a clear error.

        Args:
            vectors: Embeddings just produced.
            model: Identifier the provider announced.

        Raises:
            EmbeddingError: If an embedding carries a different model.
        """
        for vector in vectors:
            if vector.model != model:
                raise EmbeddingError(
                    f"Provider announced model '{model}' but returned a vector "
                    f"from '{vector.model}'."
                )
