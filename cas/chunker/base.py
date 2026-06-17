"""Abstract base classes for chunker implementations.

Defines the Chunker Protocol and ChunkResult dataclass that all
chunking algorithms must adhere to, enabling independent replacement
of the chunking strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass(frozen=True)
class ChunkResult:
    """Result of chunking a single piece of data.

    Attributes:
        data: The raw bytes of the chunk.
        digest: SHA-256 hex digest of the chunk data (content address).
        size: Size of the chunk in bytes.
    """

    data: bytes
    digest: str
    size: int


class Chunker(ABC):
    """Abstract base class for content-defined chunking algorithms.

    Implementations must be able to chunk a byte stream into variable-sized
    chunks based on content boundaries, and compute each chunk's SHA-256
    content address.
    """

    @abstractmethod
    def chunk_data(self, data: bytes) -> list[ChunkResult]:
        """Chunk a complete byte string into a list of chunks.

        Args:
            data: The complete byte string to chunk.

        Returns:
            An ordered list of ChunkResult objects covering all input data.
        """
        ...

    @abstractmethod
    def chunk_stream(self, stream: Iterator[bytes]) -> Iterator[ChunkResult]:
        """Chunk a streaming byte source into chunks.

        Args:
            stream: An iterator yielding byte chunks of arbitrary size.

        Yields:
            ChunkResult objects as boundaries are found.
        """
        ...
