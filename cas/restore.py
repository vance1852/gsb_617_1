"""Restore command - rebuild files from a manifest and content store.

Performs per-file content hash verification to ensure bit-for-bit accuracy.
Any missing chunk or hash mismatch causes an immediate error exit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .hashing.sha256 import sha256
from .manifest.base import Manifest
from .manifest.manifest import TextManifest
from .store.base import ContentStore
from .store.content_store import FileContentStore


class RestoreError(Exception):
    """Raised when restore fails due to missing chunks or hash mismatch."""


def restore_manifest(
    manifest_path: str | os.PathLike,
    store_path: str | os.PathLike,
    out_dir: str | os.PathLike,
) -> None:
    """Restore files from a manifest and content store.

    Args:
        manifest_path: Path to the manifest file.
        store_path: Path to the content store directory.
        out_dir: Directory to restore files into.

    Raises:
        RestoreError: If any chunk is missing or any file's content hash
            doesn't match the manifest.
    """
    manifest = TextManifest.load(manifest_path)
    store = FileContentStore(store_path)
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    for entry in manifest.iter_files():
        file_path = out / entry.path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = bytearray()
        for digest in entry.chunks:
            if not store.has_chunk(digest):
                raise RestoreError(
                    f"Missing chunk {digest} referenced by {entry.path}"
                )
            chunk_data = store.get_chunk(digest)
            content.extend(chunk_data)

        content_bytes = bytes(content)

        if len(content_bytes) != entry.size:
            raise RestoreError(
                f"Size mismatch for {entry.path}: "
                f"expected {entry.size}, got {len(content_bytes)}"
            )

        actual_hash = sha256(content_bytes).hexdigest()
        if actual_hash != entry.content_hash:
            raise RestoreError(
                f"Content hash mismatch for {entry.path}: "
                f"expected {entry.content_hash}, got {actual_hash}"
            )

        file_path.write_bytes(content_bytes)

        try:
            os.chmod(file_path, entry.mode)
        except OSError:
            pass

        print(f"restored: {entry.path} ({entry.size} bytes)", file=sys.stderr)
