"""Core abstract interfaces and type definitions for the cas package.

All modules depend on these abstractions rather than concrete implementations,
enabling loose coupling and easy replacement of components.
"""

from __future__ import annotations

from typing import Protocol, Iterator, List, Tuple, Optional, Dict, Any
from abc import abstractmethod


class Hasher(Protocol):
    """Protocol for hash algorithms.

    Provides a hashlib-like interface for incremental hashing.
    """

    @abstractmethod
    def update(self, data: bytes) -> None:
        """Update the hash with new data."""
        ...

    @abstractmethod
    def digest(self) -> bytes:
        """Return the final hash digest as bytes."""
        ...

    @abstractmethod
    def hexdigest(self) -> str:
        """Return the final hash digest as a hex string."""
        ...

    @abstractmethod
    def copy(self) -> "Hasher":
        """Return a copy of the hasher in its current state."""
        ...


class Chunk(Protocol):
    """Protocol for a chunk of data with its content address."""

    data: bytes
    digest: str
    size: int


class Chunker(Protocol):
    """Protocol for content-defined chunking algorithms."""

    @abstractmethod
    def chunk(self, data: bytes) -> List[bytes]:
        """Split data into chunks and return list of chunk data.

        Args:
            data: The input byte stream to chunk.

        Returns:
            List of bytes, each being a chunk.
        """
        ...

    @abstractmethod
    def chunk_stream(self, stream: Iterator[bytes]) -> Iterator[bytes]:
        """Chunk a stream of data.

        Args:
            stream: Iterator yielding bytes objects.

        Yields:
            Chunks of bytes.
        """
        ...


class ContentStore(Protocol):
    """Protocol for content-addressable storage backends."""

    @abstractmethod
    def put(self, data: bytes) -> str:
        """Store data and return its content address (hex digest).

        If the data already exists, just return the address.
        """
        ...

    @abstractmethod
    def get(self, digest: str) -> Optional[bytes]:
        """Retrieve data by its content address.

        Returns None if not found.
        """
        ...

    @abstractmethod
    def has(self, digest: str) -> bool:
        """Check if data with the given digest exists in the store."""
        ...

    @abstractmethod
    def list_all(self) -> List[str]:
        """List all content addresses in the store."""
        ...

    @abstractmethod
    def size(self, digest: str) -> int:
        """Return the size of the data with the given digest."""
        ...


class FileEntry:
    """Metadata for a single file in the manifest."""

    def __init__(
        self,
        path: str,
        size: int,
        mode: int,
        chunks: List[str],
        file_hash: str,
    ) -> None:
        self.path = path
        self.size = size
        self.mode = mode
        self.chunks = chunks
        self.file_hash = file_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "mode": self.mode,
            "chunks": list(self.chunks),
            "file_hash": self.file_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileEntry":
        return cls(
            path=data["path"],
            size=data["size"],
            mode=data["mode"],
            chunks=list(data["chunks"]),
            file_hash=data["file_hash"],
        )


class Manifest(Protocol):
    """Protocol for manifest file management."""

    @abstractmethod
    def add_file(self, entry: FileEntry) -> None:
        """Add a file entry to the manifest."""
        ...

    @abstractmethod
    def get_files(self) -> List[FileEntry]:
        """Get all file entries, sorted deterministically by path."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """Save the manifest to a file."""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """Load the manifest from a file."""
        ...

    @abstractmethod
    def all_chunk_digests(self) -> List[str]:
        """Get all unique chunk digests referenced by this manifest."""
        ...
