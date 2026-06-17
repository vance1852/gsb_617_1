"""Abstract base class for content-addressable storage backends.

Defines the minimal interface that any store implementation must provide:
- put_chunk: store a chunk by its content address (idempotent)
- get_chunk: retrieve a chunk by its content address
- has_chunk: check if a chunk exists
- iter_chunks: iterate over all stored chunk addresses
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class ContentStore(ABC):
    """Abstract interface for a content-addressable store.

    Chunks are addressed by their SHA-256 hex digest. Storing the same
    content twice is a no-op (deduplication).
    """

    @abstractmethod
    def put_chunk(self, digest: str, data: bytes) -> bool:
        """Store a chunk. Returns True if it was newly added, False if already present."""
        ...

    @abstractmethod
    def get_chunk(self, digest: str) -> bytes:
        """Retrieve a chunk by its digest. Raises KeyError if not found."""
        ...

    @abstractmethod
    def has_chunk(self, digest: str) -> bool:
        """Check if a chunk with the given digest exists in the store."""
        ...

    @abstractmethod
    def iter_chunks(self) -> Iterator[str]:
        """Iterate over all chunk digests stored."""
        ...

    @abstractmethod
    def chunk_size(self, digest: str) -> int:
        """Return the size in bytes of a stored chunk. Raises KeyError if not found."""
        ...
