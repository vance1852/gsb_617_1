"""Abstract base class for content-addressable storage."""

from abc import ABC, abstractmethod
from typing import Iterator, Optional


class ContentStore(ABC):
    """Abstract content-addressable store interface.

    Chunks are addressed by their content digest (hex string).
    The store is responsible for de-duplication: putting the same
    content twice is a no-op.
    """

    @abstractmethod
    def has(self, digest: str) -> bool:
        """Return True if a chunk with this digest exists."""

    @abstractmethod
    def get(self, digest: str) -> Optional[bytes]:
        """Retrieve chunk data by digest, or None if not found."""

    @abstractmethod
    def put(self, digest: str, data: bytes) -> bool:
        """Store a chunk.  Returns True if it was newly added,
        False if it already existed.
        """

    @abstractmethod
    def iter_chunks(self) -> Iterator[str]:
        """Iterate over all chunk digests in the store."""

    @abstractmethod
    def size(self, digest: str) -> Optional[int]:
        """Return the size in bytes of a chunk, or None if not found."""
