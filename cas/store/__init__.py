"""Content-addressable storage abstractions."""

from .abc import ContentStore
from .content_store import FileContentStore

__all__ = ["ContentStore", "FileContentStore"]
