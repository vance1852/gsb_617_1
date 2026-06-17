"""Abstract base class for hash algorithms."""

from abc import ABC, abstractmethod
from typing import Protocol


class Hasher(ABC):
    """Abstract hasher interface."""

    @abstractmethod
    def update(self, data: bytes) -> None:
        """Feed more bytes into the hash."""

    @abstractmethod
    def digest(self) -> bytes:
        """Return the final hash digest as bytes."""

    @abstractmethod
    def hexdigest(self) -> str:
        """Return the final hash digest as a hex string."""

    @abstractmethod
    def copy(self) -> "Hasher":
        """Return a copy of the hasher state."""

    @property
    @abstractmethod
    def digest_size(self) -> int:
        """Size of the digest in bytes."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the hash algorithm."""
