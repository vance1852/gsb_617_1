"""File-based content-addressable store with sharded directory layout.

Storage layout (to avoid huge flat directories):
    <store_root>/
        chunks/
            <hex[0:2]>/
                <hex[2:4]>/
                    <full_hex_digest>

Each chunk file contains only the raw chunk bytes.
"""

import os
from typing import Iterator, Optional

from .abc import ContentStore

_CHUNKS_DIR = "chunks"
_SHARD_LEVELS = 2
_SHARD_CHARS = 2


class FileContentStore(ContentStore):
    """Content-addressed store backed by the filesystem."""

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)
        self._chunks_dir = os.path.join(self._root, _CHUNKS_DIR)
        os.makedirs(self._chunks_dir, exist_ok=True)

    @property
    def root(self) -> str:
        return self._root

    def _shard_path(self, digest: str) -> str:
        if len(digest) < _SHARD_LEVELS * _SHARD_CHARS:
            raise ValueError(f"Digest too short for sharding: {digest}")
        parts = [self._chunks_dir]
        for i in range(_SHARD_LEVELS):
            start = i * _SHARD_CHARS
            end = start + _SHARD_CHARS
            parts.append(digest[start:end])
        parts.append(digest)
        return os.path.join(*parts)

    def has(self, digest: str) -> bool:
        return os.path.isfile(self._shard_path(digest))

    def get(self, digest: str) -> Optional[bytes]:
        path = self._shard_path(digest)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def put(self, digest: str, data: bytes) -> bool:
        path = self._shard_path(digest)
        if os.path.isfile(path):
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
        return True

    def iter_chunks(self) -> Iterator[str]:
        chunks_dir = self._chunks_dir
        if not os.path.isdir(chunks_dir):
            return
        for level1 in sorted(os.listdir(chunks_dir)):
            path1 = os.path.join(chunks_dir, level1)
            if not os.path.isdir(path1):
                continue
            for level2 in sorted(os.listdir(path1)):
                path2 = os.path.join(path1, level2)
                if not os.path.isdir(path2):
                    continue
                for fname in sorted(os.listdir(path2)):
                    fpath = os.path.join(path2, fname)
                    if os.path.isfile(fpath) and not fname.endswith(".tmp"):
                        yield fname

    def size(self, digest: str) -> Optional[int]:
        path = self._shard_path(digest)
        if not os.path.isfile(path):
            return None
        return os.path.getsize(path)
