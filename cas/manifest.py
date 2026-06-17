"""Manifest management with line-oriented plain-text format.

Manifest file format:
    # Lines starting with # are comments
    # Format version
    version 1
    # Hash algorithm used for chunk addressing and file verification
    hash_algo sha256
    # Chunking algorithm and parameters (for reference)
    chunk_algo rabin
    chunk_avg_size 8192
    chunk_min_size 2048
    chunk_max_size 65536
    # File entries, one per file, sorted by path
    # Format: file <path> <size> <mode> <file_hash> <chunk1>,<chunk2>,...
    file path/to/file.txt 12345 33188 abcdef1234... digest1,digest2,...

All file paths use forward slashes and are sorted lexicographically to
ensure deterministic manifests regardless of filesystem traversal order.
"""

from __future__ import annotations

import os
import stat
from typing import List, Set

from .abc import Manifest, FileEntry


MANIFEST_VERSION = "1"


class FileManifest(Manifest):
    """Manifest backed by a line-oriented plain text file.

    The manifest records all files in a backup, along with their
    metadata and ordered list of chunk digests. File entries are
    always sorted by path to ensure determinism.
    """

    def __init__(self) -> None:
        self._files: List[FileEntry] = []
        self.hash_algo: str = "sha256"
        self.chunk_algo: str = "rabin"
        self.chunk_avg_size: int = 8192
        self.chunk_min_size: int = 2048
        self.chunk_max_size: int = 65536

    def add_file(self, entry: FileEntry) -> None:
        """Add a file entry to the manifest.

        Note: Files are not sorted until save/load time. Call sort()
        or rely on save() which sorts automatically.
        """
        self._files.append(entry)

    def _sort(self) -> None:
        """Sort file entries deterministically by path."""
        self._files.sort(key=lambda e: e.path)

    def get_files(self) -> List[FileEntry]:
        """Get all file entries, sorted by path."""
        self._sort()
        return list(self._files)

    def all_chunk_digests(self) -> List[str]:
        """Get all unique chunk digests referenced by this manifest, sorted."""
        digests: Set[str] = set()
        for entry in self._files:
            digests.update(entry.chunks)
        return sorted(digests)

    def save(self, path: str) -> None:
        """Save the manifest to a file.

        File entries are sorted before writing to ensure determinism.
        """
        self._sort()

        lines: List[str] = []
        lines.append(f"version {MANIFEST_VERSION}")
        lines.append(f"hash_algo {self.hash_algo}")
        lines.append(f"chunk_algo {self.chunk_algo}")
        lines.append(f"chunk_avg_size {self.chunk_avg_size}")
        lines.append(f"chunk_min_size {self.chunk_min_size}")
        lines.append(f"chunk_max_size {self.chunk_max_size}")

        for entry in self._files:
            chunks_str = ",".join(entry.chunks)
            lines.append(
                f"file {entry.path} {entry.size} {entry.mode} "
                f"{entry.file_hash} {chunks_str}"
            )

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def load(self, path: str) -> None:
        """Load the manifest from a file."""
        self._files = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split(None, 1)
                if not parts:
                    continue

                keyword = parts[0]

                if keyword == "version":
                    continue
                elif keyword == "hash_algo":
                    self.hash_algo = parts[1] if len(parts) > 1 else "sha256"
                elif keyword == "chunk_algo":
                    self.chunk_algo = parts[1] if len(parts) > 1 else "rabin"
                elif keyword == "chunk_avg_size":
                    if len(parts) > 1:
                        self.chunk_avg_size = int(parts[1])
                elif keyword == "chunk_min_size":
                    if len(parts) > 1:
                        self.chunk_min_size = int(parts[1])
                elif keyword == "chunk_max_size":
                    if len(parts) > 1:
                        self.chunk_max_size = int(parts[1])
                elif keyword == "file":
                    if len(parts) < 2:
                        continue
                    self._parse_file_line(parts[1])

        self._sort()

    def _parse_file_line(self, rest: str) -> None:
        """Parse a 'file' line from the manifest.

        Format: <path> <size> <mode> <file_hash> <chunk1>,<chunk2>,...

        For empty files (zero chunks), the chunks field may be omitted
        or empty. We split from the right to handle paths that may
        contain spaces.
        """
        parts = rest.rsplit(None, 4)
        if len(parts) == 5:
            path, size_str, mode_str, file_hash, chunks_str = parts
        elif len(parts) == 4:
            path, size_str, mode_str, file_hash = parts
            chunks_str = ""
        else:
            raise ValueError(f"Invalid file entry: {rest}")

        size = int(size_str)
        mode = int(mode_str)
        chunks = [c for c in chunks_str.split(",") if c]

        entry = FileEntry(
            path=path,
            size=size,
            mode=mode,
            chunks=chunks,
            file_hash=file_hash,
        )
        self._files.append(entry)
