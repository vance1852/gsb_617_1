"""Verify command implementation.

Verifies the integrity of a content-addressed store and optionally
cross-references with a manifest to detect missing referenced chunks.

Two verification modes:
1. Store integrity: Recompute SHA-256 of every chunk in the store
   and compare against its filename (content address). Reports any
   corrupted chunks.
2. Manifest reference check (optional): Given a manifest, verify
   that all chunks referenced by the manifest exist in the store
   and are intact.
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple, Optional, Set

from .store import FileContentStore
from .manifest import FileManifest
from .sha256 import sha256


class VerifyResult:
    """Result of a verification run."""

    def __init__(self) -> None:
        self.total_chunks: int = 0
        self.corrupted_chunks: List[str] = []
        self.missing_chunks: List[str] = []
        self.verified_chunks: int = 0

    @property
    def ok(self) -> bool:
        return len(self.corrupted_chunks) == 0 and len(self.missing_chunks) == 0


def verify_store(
    store_path: str,
    manifest_path: Optional[str] = None,
) -> VerifyResult:
    """Verify the integrity of a content-addressed store.

    Args:
        store_path: Path to the content-addressed store.
        manifest_path: Optional path to a manifest. If provided, also
                       verify that all chunks referenced by the manifest
                       exist and are intact.

    Returns:
        A VerifyResult with details of what was found.
    """
    result = VerifyResult()

    store = FileContentStore(store_path)

    all_digests = store.list_all()
    result.total_chunks = len(all_digests)

    for digest in all_digests:
        try:
            data = store.get(digest)
            if data is None:
                result.corrupted_chunks.append(digest)
                continue

            actual = sha256(data).hexdigest()
            if actual != digest:
                result.corrupted_chunks.append(digest)
            else:
                result.verified_chunks += 1
        except Exception as e:
            print(f"warning: error reading chunk {digest}: {e}", file=sys.stderr)
            result.corrupted_chunks.append(digest)

    if manifest_path and os.path.isfile(manifest_path):
        manifest = FileManifest()
        manifest.load(manifest_path)
        referenced = set(manifest.all_chunk_digests())

        store_set = set(all_digests)
        missing = referenced - store_set
        result.missing_chunks = sorted(missing)

        for digest in list(missing):
            if digest in result.corrupted_chunks:
                pass

    return result


def print_verify_result(result: VerifyResult) -> None:
    """Print a human-readable verification report."""
    print(f"Total chunks in store: {result.total_chunks}")
    print(f"Verified (intact):     {result.verified_chunks}")
    print(f"Corrupted:             {len(result.corrupted_chunks)}")

    if result.corrupted_chunks:
        print("\nCorrupted chunks:")
        for d in result.corrupted_chunks[:10]:
            print(f"  {d}")
        if len(result.corrupted_chunks) > 10:
            print(f"  ... and {len(result.corrupted_chunks) - 10} more")

    if result.missing_chunks:
        print(f"\nMissing referenced chunks: {len(result.missing_chunks)}")
        for d in result.missing_chunks[:10]:
            print(f"  {d}")
        if len(result.missing_chunks) > 10:
            print(f"  ... and {len(result.missing_chunks) - 10} more")

    if result.ok:
        print("\nAll checks passed.")
    else:
        print("\nVERIFICATION FAILED")
