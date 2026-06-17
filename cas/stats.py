"""Stats command - produce deduplication reports from a manifest.

Reports:
- Total files and raw total bytes
- Deduplicated stored bytes (unique chunks)
- Space saving percentage
- Unique chunk count vs total chunk references
- Top N most-referenced chunks
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .manifest.base import Manifest
from .manifest.manifest import TextManifest
from .store.content_store import FileContentStore


@dataclass
class StatsReport:
    """Deduplication statistics report."""

    total_files: int = 0
    raw_total_bytes: int = 0
    stored_bytes: int = 0
    unique_chunks: int = 0
    total_chunk_refs: int = 0
    top_chunks: list[tuple[str, int]] = field(default_factory=list)

    @property
    def saving_ratio(self) -> float:
        if self.raw_total_bytes == 0:
            return 0.0
        return 1.0 - (self.stored_bytes / self.raw_total_bytes)

    @property
    def saving_percent(self) -> float:
        return round(self.saving_ratio * 100, 2)


def compute_stats(
    manifest_path: str | os.PathLike,
    store_path: str | os.PathLike | None = None,
    top_n: int = 10,
) -> StatsReport:
    """Compute deduplication statistics from a manifest.

    Args:
        manifest_path: Path to the manifest file.
        store_path: Optional path to the content store. If provided, chunk
            sizes are read from the store for accuracy. If not provided,
            sizes are estimated from file sizes / chunk counts (less accurate).
        top_n: Number of top referenced chunks to report.

    Returns:
        StatsReport with all computed statistics.
    """
    manifest = TextManifest.load(manifest_path)
    report = StatsReport()

    ref_counter: Counter[str] = Counter()
    all_digests: set[str] = set()

    for entry in manifest.iter_files():
        report.total_files += 1
        report.raw_total_bytes += entry.size
        report.total_chunk_refs += len(entry.chunks)
        for digest in entry.chunks:
            ref_counter[digest] += 1
            all_digests.add(digest)

    report.unique_chunks = len(all_digests)

    if store_path is not None and Path(store_path).exists():
        store = FileContentStore(store_path)
        for digest in all_digests:
            try:
                report.stored_bytes += store.chunk_size(digest)
            except KeyError:
                pass
    else:
        if report.total_chunk_refs > 0 and report.raw_total_bytes > 0:
            avg_chunk_size = report.raw_total_bytes / report.total_chunk_refs
            report.stored_bytes = int(avg_chunk_size * report.unique_chunks)

    top = ref_counter.most_common(top_n)
    report.top_chunks = top

    return report


def format_report(report: StatsReport) -> str:
    """Format a StatsReport as a human-readable string."""
    lines = [
        f"Total files:        {report.total_files}",
        f"Raw total bytes:    {report.raw_total_bytes}",
        f"Stored bytes:       {report.stored_bytes}",
        f"Space saved:        {report.saving_percent}%",
        f"Unique chunks:      {report.unique_chunks}",
        f"Total chunk refs:   {report.total_chunk_refs}",
        "",
        f"Top {len(report.top_chunks)} most-referenced chunks:",
    ]
    for i, (digest, count) in enumerate(report.top_chunks, 1):
        lines.append(f"  {i:2d}. {digest}  x{count}")
    return "\n".join(lines)
