"""Restore command implementation.

Reads a manifest and reconstructs the original directory tree by
fetching chunks from the content-addressed store and concatenating
them in order.

Each file is verified against its stored SHA-256 digest after
reconstruction. Any missing chunk or hash mismatch causes an
immediate error exit — no corrupt data is ever silently written.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from .abc import FileEntry
from .store import FileContentStore
from .manifest import FileManifest
from .sha256 import sha256


class RestoreError(Exception):
    """Raised when restore fails due to missing chunks or hash mismatch."""


def _from_posix_path(path: str) -> str:
    """Convert a POSIX-style path to the native OS path format."""
    return path.replace("/", os.sep)


def _verify_file_data(data: bytes, expected_hash: str, rel_path: str) -> None:
    """Verify file data against expected SHA-256 hash.

    Raises RestoreError if the hash doesn't match.
    """
    actual_hash = sha256(data).hexdigest()
    if actual_hash != expected_hash:
        raise RestoreError(
            f"hash mismatch for {rel_path}: "
            f"expected {expected_hash}, got {actual_hash}"
        )


def _reconstruct_file(
    store: FileContentStore,
    entry: FileEntry,
) -> bytes:
    """Reconstruct a file's data from its chunks.

    Fetches all chunks from the store and concatenates them in order.

    Raises RestoreError if any chunk is missing from the store.
    """
    missing: List[str] = []
    for digest in entry.chunks:
        if not store.has(digest):
            missing.append(digest)

    if missing:
        raise RestoreError(
            f"missing chunks for {entry.path}: {', '.join(missing[:5])}"
            + ("..." if len(missing) > 5 else "")
        )

    parts: List[bytes] = []
    for digest in entry.chunks:
        chunk_data = store.get(digest)
        if chunk_data is None:
            raise RestoreError(f"chunk {digest} disappeared during restore")
        parts.append(chunk_data)

    return b"".join(parts)


def restore_manifest(
    manifest_path: str,
    store_path: str,
    out_dir: str,
) -> None:
    """Restore files from a manifest into the output directory.

    Args:
        manifest_path: Path to the manifest file.
        store_path: Path to the content-addressed store.
        out_dir: Path to the output directory (created if needed).

    Raises:
        RestoreError: If any chunk is missing or any file hash mismatch
                      is detected.
        FileNotFoundError: If the manifest file doesn't exist.
    """
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = FileManifest()
    manifest.load(manifest_path)

    store = FileContentStore(store_path)

    os.makedirs(out_dir, exist_ok=True)

    entries = manifest.get_files()

    for entry in entries:
        rel_path = entry.path
        native_rel_path = _from_posix_path(rel_path)
        out_path = os.path.join(out_dir, native_rel_path)

        out_dir_path = os.path.dirname(out_path)
        if out_dir_path:
            os.makedirs(out_dir_path, exist_ok=True)

        file_data = _reconstruct_file(store, entry)

        if len(file_data) != entry.size:
            raise RestoreError(
                f"size mismatch for {rel_path}: "
                f"expected {entry.size}, got {len(file_data)}"
            )

        _verify_file_data(file_data, entry.file_hash, rel_path)

        with open(out_path, "wb") as f:
            f.write(file_data)

        try:
            os.chmod(out_path, entry.mode & 0o7777)
        except OSError:
            pass
