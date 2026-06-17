"""Restore logic - reconstruct files from store chunks based on manifest.

Each file is verified against its stored SHA-256 hash after assembly.
Any missing chunk or hash mismatch causes an immediate error exit.
"""

import os
import sys
from typing import Optional

from .store import ContentStore
from .manifest import FileManifest, FileEntry
from .hashing import SHA256Hasher


class RestoreError(Exception):
    """Raised when restore fails due to missing chunks or hash mismatch."""


def _verify_file_data(data: bytes, expected_hash: str) -> None:
    hasher = SHA256Hasher()
    hasher.update(data)
    actual = hasher.hexdigest()
    if actual != expected_hash:
        raise RestoreError(
            f"File hash mismatch: expected {expected_hash}, got {actual}"
        )


def restore_file(
    entry: FileEntry,
    store: ContentStore,
    out_path: str,
) -> None:
    """Restore a single file from store chunks.

    Args:
        entry: File manifest entry.
        store: Content store to read chunks from.
        out_path: Output file path.

    Raises:
        RestoreError: If any chunk is missing or the final hash mismatches.
    """
    chunks_data = []
    for chunk_digest in entry.chunks:
        chunk_data = store.get(chunk_digest)
        if chunk_data is None:
            raise RestoreError(f"Missing chunk: {chunk_digest}")
        chunk_hasher = SHA256Hasher()
        chunk_hasher.update(chunk_data)
        if chunk_hasher.hexdigest() != chunk_digest:
            raise RestoreError(
                f"Chunk hash mismatch: {chunk_digest} "
                f"(chunk data corrupted?)"
            )
        chunks_data.append(chunk_data)

    file_data = b"".join(chunks_data)

    if len(file_data) != entry.size:
        raise RestoreError(
            f"File size mismatch for {entry.relpath}: "
            f"expected {entry.size}, got {len(file_data)}"
        )

    _verify_file_data(file_data, entry.file_hash)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(file_data)

    try:
        os.chmod(out_path, entry.mode)
    except OSError:
        pass


def restore_manifest(
    manifest: FileManifest,
    store: ContentStore,
    out_dir: str,
) -> None:
    """Restore all files from a manifest.

    Args:
        manifest: The manifest to restore from.
        store: Content store containing the chunks.
        out_dir: Output directory.

    Raises:
        RestoreError: If any file fails to restore.
    """
    out_dir = os.path.abspath(out_dir)

    for entry in manifest.files:
        out_path = os.path.join(out_dir, entry.relpath)
        try:
            restore_file(entry, store, out_path)
        except RestoreError as e:
            print(f"error: failed to restore {entry.relpath}: {e}",
                  file=sys.stderr)
            raise
