"""Abstract base classes for manifest representations.

A manifest records the mapping from files (relative paths) to their
constituent chunk digests (in order), along with necessary file metadata.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class FileEntry:
    """Metadata and chunk list for a single file in the manifest.

    Attributes:
        path: Relative path of the file.
        size: Total size of the file in bytes.
        mode: File mode/permissions (st_mode & 0o7777).
        chunks: Ordered list of SHA-256 hex digests of the file's chunks.
        content_hash: SHA-256 hex digest of the full file content (for verification).
    """

    path: str
    size: int
    mode: int
    chunks: list[str] = field(default_factory=list)
    content_hash: str = ""


class Manifest(ABC):
    """Abstract interface for manifest storage and retrieval."""

    @abstractmethod
    def add_file(self, entry: FileEntry) -> None:
        """Add a file entry to the manifest."""
        ...

    @abstractmethod
    def iter_files(self) -> Iterator[FileEntry]:
        """Iterate over all file entries in deterministic (sorted path) order."""
        ...

    @abstractmethod
    def get_file(self, path: str) -> FileEntry | None:
        """Get a file entry by path, or None if not found."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """Save the manifest to a file."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> "Manifest":
        """Load a manifest from a file."""
        ...

    @abstractmethod
    def set_chunker_config(self, config: dict[str, int | str]) -> None:
        """Store chunker configuration for reproducibility."""
        ...

    @abstractmethod
    def get_chunker_config(self) -> dict[str, int | str]:
        """Retrieve chunker configuration."""
        ...
