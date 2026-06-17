"""Verify logic - check chunk integrity and manifest reference
completeness.

Two verification modes:
1. Store-only: Recompute SHA-256 of every chunk in the store and
   compare with its filename (address).  Report any corrupted chunks.
2. Store + manifest: Also check that all chunks referenced by the
   manifest exist in the store, and report any missing referenced
   chunks.
"""

import sys
from typing import List, Optional, Tuple

from .store import ContentStore
from .manifest import FileManifest
from .hashing import SHA256Hasher


class VerifyResult:
    """Results of a verification run."""

    def __init__(self) -> None:
        self.total_chunks: int = 0
        self.corrupted_chunks: List[str] = []
        self.missing_chunks: List[str] = []
        self.referenced_chunks: int = 0

    @property
    def ok(self) -> bool:
        return not self.corrupted_chunks and not self.missing_chunks

    def report(self) -> str:
        lines = []
        lines.append(f"Total chunks in store: {self.total_chunks}")
        if self.referenced_chunks:
            lines.append(f"Chunks referenced by manifest: {self.referenced_chunks}")
        if self.corrupted_chunks:
            lines.append(f"Corrupted chunks: {len(self.corrupted_chunks)}")
            for d in self.corrupted_chunks:
                lines.append(f"  CORRUPTED: {d}")
        else:
            lines.append("Corrupted chunks: 0")
        if self.missing_chunks:
            lines.append(f"Missing referenced chunks: {len(self.missing_chunks)}")
            for d in self.missing_chunks:
                lines.append(f"  MISSING: {d}")
        elif self.referenced_chunks:
            lines.append("Missing referenced chunks: 0")
        return "\n".join(lines)


def verify_store(store: ContentStore) -> VerifyResult:
    """Verify all chunks in the store for integrity.

    Recomputes SHA-256 of each chunk's data and compares with the
    chunk's filename (its address).
    """
    result = VerifyResult()

    for digest in store.iter_chunks():
        result.total_chunks += 1
        data = store.get(digest)
        if data is None:
            result.corrupted_chunks.append(digest)
            continue

        hasher = SHA256Hasher()
        hasher.update(data)
        computed = hasher.hexdigest()
        if computed != digest:
            result.corrupted_chunks.append(digest)

    return result


def verify_manifest(
    store: ContentStore,
    manifest: FileManifest,
) -> VerifyResult:
    """Verify store integrity plus manifest reference completeness.

    1. Check all store chunks for integrity.
    2. Check that all chunks referenced by the manifest exist in
       the store and are not corrupted.
    """
    result = verify_store(store)

    referenced = set(manifest.all_chunk_digests())
    result.referenced_chunks = len(referenced)

    corrupted_set = set(result.corrupted_chunks)
    for digest in referenced:
        if not store.has(digest):
            result.missing_chunks.append(digest)
        elif digest in corrupted_set:
            if digest not in result.missing_chunks:
                result.missing_chunks.append(digest)

    result.missing_chunks.sort()
    return result
