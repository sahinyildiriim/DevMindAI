"""Binary representation of embedding vectors.

Vectors are stored as little-endian 32-bit floats. Single precision is
what embedding models emit anyway, and it halves the size of the index
compared to Python's native doubles.
"""

from __future__ import annotations

import math
import sys
from array import array
from typing import Final

from devmind.domain.exceptions import StorageError

__all__ = ["decode_vector", "encode_vector"]

_TYPE_CODE: Final[str] = "f"
_BYTES_PER_COMPONENT: Final[int] = 4
_IS_BIG_ENDIAN: Final[bool] = sys.byteorder == "big"


def encode_vector(vector: tuple[float, ...]) -> bytes:
    """Pack a vector into its stored representation.

    Args:
        vector: The vector components.

    Returns:
        The little-endian byte representation.

    Raises:
        StorageError: If a component is too large for single precision.
            Narrowing turns such a value into infinity instead of
            failing, so the result is checked rather than trusted.
    """
    values = array(_TYPE_CODE, vector)
    if any(math.isinf(value) for value in values):
        raise StorageError("Embedding component is out of range for single precision storage.")
    if _IS_BIG_ENDIAN:
        values.byteswap()
    return values.tobytes()


def decode_vector(blob: bytes) -> tuple[float, ...]:
    """Unpack a stored vector.

    Args:
        blob: The stored byte representation.

    Returns:
        The vector components.

    Raises:
        StorageError: If the blob is empty or truncated.
    """
    if not blob or len(blob) % _BYTES_PER_COMPONENT:
        raise StorageError(
            f"Stored embedding is corrupt: {len(blob)} bytes is not a whole "
            f"number of {_BYTES_PER_COMPONENT} byte components."
        )
    values = array(_TYPE_CODE)
    values.frombytes(blob)
    if _IS_BIG_ENDIAN:
        values.byteswap()
    return tuple(values)
