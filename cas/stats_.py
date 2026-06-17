"""Stats command implementation.

Generates deduplication reports from a manifest, including:
- Total number of files
- Total raw bytes (before dedup)
- Total stored bytes (after dedup)
- Space savings percentage
- Unique chunk count vs total chunk references
- Top N most-referenced chunks
"""

from __future__ import annotations

import os
from collections import Counter
from typing import List, Tuple

from .store import FileContentStore
from .manifest import FileManifest


class StatsResult:
    """Result of a stats analysis."""

    def __init__(self) -> None:
        self.total_files: int = 0
        self.total_raw_bytes: int = 0
        self.total_stored_bytes: int = 0
        self.unique_chunks: int = 0
        self.total_chunk_refs: int = 0
        self.savings_pct: float = 0.0
        self.top_chunks: List[Tuple[str, int, int]] = []  # (digest, ref_count, size)


def compute_stats(
    manifest_path: str,
    store_path: str,
    top_n: int = 10,
) -> StatsResult:
    """Compute deduplication statistics from a manifest.

    Args:
        manifest_path: Path to the manifest file.
        store_path: Path to the content-addressed store.
        top_n: Number of top referenced chunks to report.

    Returns:
        A StatsResult with all computed statistics.
    """
    result = StatsResult()

    manifest = FileManifest()
    manifest.load(manifest_path)

    store = FileContentStore(store_path)

    entries = manifest.get_files()
    result.total_files = len(entries)

    for entry in entries:
        result.total_raw_bytes += entry.size
        result.total_chunk_refs += len(entry.chunks)

    ref_counter: Counter = Counter()
    for entry in entries:
        ref_counter.update(entry.chunks)

    result.unique_chunks = len(ref_counter)

    total_stored = 0
    for digest in ref_counter:
        if store.has(digest):
            total_stored += store.size(digest)
        else:
            pass
    result.total_stored_bytes = total_stored

    if result.total_raw_bytes > 0:
        saved = result.total_raw_bytes - result.total_stored_bytes
        result.savings_pct = (saved / result.total_raw_bytes) * 100.0
    else:
        result.savings_pct = 0.0

    top_n = max(1, top_n)
    top_items = ref_counter.most_common(top_n)
    top_list: List[Tuple[str, int, int]] = []
    for digest, count in top_items:
        size = 0
        if store.has(digest):
            size = store.size(digest)
        top_list.append((digest, count, size))
    result.top_chunks = top_list

    return result


def print_stats(result: StatsResult, top_n: int = 10) -> None:
    """Print a human-readable statistics report."""
    print(f"Total files:            {result.total_files}")
    print(f"Raw (pre-dedup) bytes:  {result.total_raw_bytes:,}")
    print(f"Stored (post-dedup):    {result.total_stored_bytes:,}")
    print(f"Space savings:          {result.savings_pct:.2f}%")
    print(f"Unique chunks:          {result.unique_chunks}")
    print(f"Total chunk references: {result.total_chunk_refs}")

    if result.top_chunks:
        print(f"\nTop {len(result.top_chunks)} most-referenced chunks:")
        print(f"  {'Rank':<5} {'Digest':<66} {'Refs':>6} {'Size':>10}")
        print(f"  {'-'*5} {'-'*66} {'-'*6} {'-'*10}")
        for i, (digest, refs, size) in enumerate(result.top_chunks, 1):
            print(f"  {i:<5} {digest:<66} {refs:>6} {size:>10,}")
