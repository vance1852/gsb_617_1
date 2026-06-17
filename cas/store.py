"""Content-addressable storage backend with sharded directory layout.

Store layout (under store_path):
    store_path/
        chunks/
            <2-hex>/           # First 2 hex chars of digest (256 dirs)
                <2-hex>/       # Next 2 hex chars (256 dirs = 65536 total)
                    <rest>    # Remaining 60 hex chars as filename

This 2-level sharding ensures no single directory has too many files,
even for millions of chunks.
"""

from __future__ import annotations

import os
import tempfile
from typing import List, Optional

from .abc import ContentStore
from .sha256 import sha256


CHUNKS_DIR = "chunks"
SHARD_LEVELS = 2
SHARD_CHARS = 2


class FileContentStore(ContentStore):
    """Content-addressable store backed by the filesystem.

    Chunks are stored as files named by their SHA-256 hex digest,
    arranged in a 2-level sharded directory structure to prevent any
    single directory from accumulating too many entries.
    """

    def __init__(self, store_path: str) -> None:
        self.store_path = store_path
        self._chunks_dir = os.path.join(store_path, CHUNKS_DIR)
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Create the store directory structure if it doesn't exist."""
        if self._initialized:
            return
        os.makedirs(self._chunks_dir, exist_ok=True)
        self._initialized = True

    def _digest_to_path(self, digest: str) -> str:
        """Convert a hex digest to a filesystem path.

        Uses 2 levels of sharding with 2 hex chars each:
          digest = "abcdef1234567890..."
          path   = chunks/ab/cd/ef1234567890...
        """
        if len(digest) < SHARD_LEVELS * SHARD_CHARS:
            raise ValueError(f"Digest too short: {digest}")

        parts = [self._chunks_dir]
        offset = 0
        for _ in range(SHARD_LEVELS):
            parts.append(digest[offset:offset + SHARD_CHARS])
            offset += SHARD_CHARS
        parts.append(digest[offset:])
        return os.path.join(*parts)

    def put(self, data: bytes) -> str:
        """Store data and return its content address (hex digest).

        If the data already exists in the store, just return the digest
        without rewriting the file. Writes are atomic: data is first
        written to a temp file and then renamed.
        """
        self._ensure_initialized()

        digest = sha256(data).hexdigest()
        path = self._digest_to_path(digest)

        if os.path.exists(path):
            return digest

        os.makedirs(os.path.dirname(path), exist_ok=True)

        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

        return digest

    def get(self, digest: str) -> Optional[bytes]:
        """Retrieve data by its content address.

        Returns None if the chunk doesn't exist.
        """
        self._ensure_initialized()

        path = self._digest_to_path(digest)
        if not os.path.exists(path):
            return None

        with open(path, "rb") as f:
            return f.read()

    def has(self, digest: str) -> bool:
        """Check if a chunk with the given digest exists in the store."""
        self._ensure_initialized()
        path = self._digest_to_path(digest)
        return os.path.exists(path)

    def size(self, digest: str) -> int:
        """Return the size (in bytes) of the chunk with the given digest."""
        self._ensure_initialized()
        path = self._digest_to_path(digest)
        return os.path.getsize(path)

    def list_all(self) -> List[str]:
        """List all chunk digests in the store.

        Walks the sharded directory structure and reconstructs the
        full hex digest from the directory and file names.
        """
        self._ensure_initialized()

        digests: List[str] = []

        if not os.path.isdir(self._chunks_dir):
            return digests

        for level1 in os.listdir(self._chunks_dir):
            level1_path = os.path.join(self._chunks_dir, level1)
            if not os.path.isdir(level1_path):
                continue
            if len(level1) != SHARD_CHARS:
                continue

            for level2 in os.listdir(level1_path):
                level2_path = os.path.join(level1_path, level2)
                if not os.path.isdir(level2_path):
                    continue
                if len(level2) != SHARD_CHARS:
                    continue

                for filename in os.listdir(level2_path):
                    file_path = os.path.join(level2_path, filename)
                    if not os.path.isfile(file_path):
                        continue
                    if filename.startswith(".tmp_"):
                        continue
                    digest = level1 + level2 + filename
                    if len(digest) == 64:
                        digests.append(digest)

        digests.sort()
        return digests
