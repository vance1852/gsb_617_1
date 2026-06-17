"""File-based content-addressable store with sharded directory layout.

Store layout:
    <storePath>/
        chunks/
            <aa>/          # first 2 hex chars of digest
                <bb>/      # next 2 hex chars of digest
                    <aabb...>  # full 64-char hex digest as filename
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterator

from .base import ContentStore

_CHUNKS_SUBDIR = "chunks"
_SHARD_LEVELS = 2
_SHARD_CHARS = 2


class FileContentStore(ContentStore):
    """Content-addressable store backed by the filesystem.

    Chunks are stored in a 2-level sharded directory structure to avoid
    having too many files in a single directory (which degrades performance
    on many filesystems).
    """

    def __init__(self, store_path: str | os.PathLike) -> None:
        self._root = Path(store_path).resolve()
        self._chunks_dir = self._root / _CHUNKS_SUBDIR
        self._chunks_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def chunks_dir(self) -> Path:
        return self._chunks_dir

    def _digest_to_path(self, digest: str) -> Path:
        if len(digest) != 64:
            raise ValueError(f"Invalid SHA-256 digest length: {len(digest)}")
        parts = [digest[i * _SHARD_CHARS:(i + 1) * _SHARD_CHARS] for i in range(_SHARD_LEVELS)]
        return self._chunks_dir.joinpath(*parts, digest)

    def put_chunk(self, digest: str, data: bytes) -> bool:
        path = self._digest_to_path(digest)
        if path.exists():
            return False

        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".tmp_",
            suffix=f"_{digest}",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return True

    def get_chunk(self, digest: str) -> bytes:
        path = self._digest_to_path(digest)
        if not path.exists():
            raise KeyError(f"Chunk not found: {digest}")
        return path.read_bytes()

    def has_chunk(self, digest: str) -> bool:
        path = self._digest_to_path(digest)
        return path.exists()

    def iter_chunks(self) -> Iterator[str]:
        for level1 in sorted(self._chunks_dir.iterdir()):
            if not level1.is_dir():
                continue
            for level2 in sorted(level1.iterdir()):
                if not level2.is_dir():
                    continue
                for entry in sorted(level2.iterdir()):
                    if entry.is_file() and len(entry.name) == 64:
                        yield entry.name

    def chunk_size(self, digest: str) -> int:
        path = self._digest_to_path(digest)
        if not path.exists():
            raise KeyError(f"Chunk not found: {digest}")
        return path.stat().st_size
