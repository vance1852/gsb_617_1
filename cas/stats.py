"""Stats logic - deduplication report from a manifest.

Reports:
- Total files
- Original total bytes
- Actual stored bytes (unique chunks only)
- Deduplication ratio (percentage saved)
- Unique chunk count vs total chunk references
- Top N most-referenced chunks
"""

from typing import List, Tuple

from .manifest import FileManifest
from .store import ContentStore


class StatsResult:
    """Container for deduplication statistics."""

    def __init__(self) -> None:
        self.num_files: int = 0
        self.total_bytes: int = 0
        self.unique_chunks: int = 0
        self.total_chunk_refs: int = 0
        self.stored_bytes: int = 0
        self.saved_percent: float = 0.0
        self.top_chunks: List[Tuple[str, int]] = []

    def report(self) -> str:
        lines = []
        lines.append(f"Total files: {self.num_files}")
        lines.append(f"Original total bytes: {self.total_bytes}")
        lines.append(f"Stored bytes (after dedup): {self.stored_bytes}")
        lines.append(f"Space saved: {self.saved_percent:.2f}%")
        lines.append(f"Unique chunks: {self.unique_chunks}")
        lines.append(f"Total chunk references: {self.total_chunk_refs}")
        if self.top_chunks:
            lines.append("")
            lines.append("Top most-referenced chunks:")
            for i, (digest, count) in enumerate(self.top_chunks, 1):
                lines.append(f"  {i}. {digest} ({count} references)")
        return "\n".join(lines)


def compute_stats(
    manifest: FileManifest,
    store: ContentStore,
    top_n: int = 10,
) -> StatsResult:
    """Compute deduplication statistics from a manifest and store.

    Args:
        manifest: The manifest to analyze.
        store: The content store (for chunk sizes).
        top_n: Number of top-referenced chunks to report.

    Returns:
        A StatsResult with all computed statistics.
    """
    result = StatsResult()

    result.num_files = manifest.num_files
    result.total_bytes = manifest.total_bytes
    result.total_chunk_refs = manifest.total_chunk_refs

    ref_counts = manifest.chunk_reference_counts()
    result.unique_chunks = len(ref_counts)

    stored_bytes = 0
    for digest in ref_counts:
        size = store.size(digest)
        if size is not None:
            stored_bytes += size
        else:
            pass
    result.stored_bytes = stored_bytes

    if result.total_bytes > 0:
        result.saved_percent = (
            (result.total_bytes - result.stored_bytes) / result.total_bytes * 100
        )
    else:
        result.saved_percent = 0.0

    sorted_chunks = sorted(
        ref_counts.items(), key=lambda x: (-x[1], x[0])
    )
    result.top_chunks = sorted_chunks[:top_n]

    return result
