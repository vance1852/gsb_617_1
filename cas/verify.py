"""Verify command - check store integrity and manifest reference completeness.

Verifies that:
1. Every chunk in the store has a valid SHA-256 matching its filename
2. Every chunk referenced by a manifest exists in the store (if manifest provided)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .hashing.sha256 import sha256
from .manifest.manifest import TextManifest
from .store.content_store import FileContentStore


@dataclass
class VerifyResult:
    """Results of a store verification."""

    total_chunks: int = 0
    corrupted_chunks: list[str] = field(default_factory=list)
    missing_chunks: list[str] = field(default_factory=list)
    referenced_chunks: int = 0

    @property
    def ok(self) -> bool:
        return len(self.corrupted_chunks) == 0 and len(self.missing_chunks) == 0


def verify_store(
    store_path: str | os.PathLike,
    manifest_path: str | os.PathLike | None = None,
) -> VerifyResult:
    """Verify the integrity of a content store.

    Args:
        store_path: Path to the content store directory.
        manifest_path: Optional manifest path. If provided, also checks that
            all chunks referenced by the manifest exist in the store.

    Returns:
        VerifyResult with statistics and lists of problems.
    """
    store = FileContentStore(store_path)
    result = VerifyResult()

    all_digests: list[str] = []
    for digest in store.iter_chunks():
        all_digests.append(digest)
        result.total_chunks += 1

        try:
            data = store.get_chunk(digest)
        except KeyError:
            result.corrupted_chunks.append(digest)
            continue

        actual = sha256(data).hexdigest()
        if actual != digest:
            result.corrupted_chunks.append(digest)
            print(
                f"corrupted: {digest} (actual: {actual})",
                file=sys.stderr,
            )

    if manifest_path is not None and Path(manifest_path).exists():
        manifest = TextManifest.load(manifest_path)
        referenced: set[str] = set()
        for entry in manifest.iter_files():
            for digest in entry.chunks:
                referenced.add(digest)

        result.referenced_chunks = len(referenced)
        store_set = set(all_digests)

        for digest in sorted(referenced):
            if digest not in store_set:
                result.missing_chunks.append(digest)
                print(
                    f"missing: {digest} (referenced by manifest)",
                    file=sys.stderr,
                )

    return result
