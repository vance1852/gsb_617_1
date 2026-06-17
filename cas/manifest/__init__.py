"""Manifest module - records file-to-chunk mappings and metadata."""

from .base import FileEntry, Manifest
from .manifest import TextManifest

__all__ = ["FileEntry", "Manifest", "TextManifest"]
