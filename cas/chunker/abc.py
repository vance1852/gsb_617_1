"""Abstract base classes for rolling hash and chunker."""

from abc import ABC, abstractmethod
from typing import Iterator, Tuple


class RollingHash(ABC):
    """Abstract rolling hash interface."""

    @abstractmethod
    def reset(self) -> None:
        """Reset the rolling hash state."""

    @abstractmethod
    def update(self, data: bytes) -> None:
        """Feed initial bytes to build up the window."""

    @abstractmethod
    def roll(self, out_byte: int, in_byte: int) -> None:
        """Slide the window by one byte: remove out_byte, add in_byte.
        This must be O(1) incremental update.
        """

    @abstractmethod
    def digest(self) -> int:
        """Return the current hash value as an integer."""

    @property
    @abstractmethod
    def window_size(self) -> int:
        """Size of the rolling hash window in bytes."""


class Chunker(ABC):
    """Abstract chunker interface."""

    @abstractmethod
    def chunk(self, data: bytes) -> Iterator[Tuple[bytes, int]]:
        """Yield (chunk_data, chunk_offset) tuples from input data."""
