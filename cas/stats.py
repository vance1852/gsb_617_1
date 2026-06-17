from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from .manifest import Manifest, ManifestEntry


def stats(manifest_path: str | Path, top: int = 10) -> None:
    mf = Manifest.load(manifest_path)

    total_files = len(mf.entries)
    total_bytes = sum(e.size for e in mf.entries)

    ref_count: Counter[str] = Counter()
    unique_sizes: Dict[str, int] = {}

    for entry in mf.entries:
        for chunk_size, chunk_digest in entry.chunks:
            ref_count[chunk_digest] += 1
            if chunk_digest not in unique_sizes:
                unique_sizes[chunk_digest] = chunk_size

    unique_chunks = len(ref_count)
    total_refs = sum(ref_count.values())
    stored_bytes = sum(unique_sizes[d] for d in ref_count)

    if total_bytes > 0:
        saving = (1 - stored_bytes / total_bytes) * 100
    else:
        saving = 0.0

    print(f"Files:          {total_files}")
    print(f"Original bytes: {total_bytes}")
    print(f"Stored bytes:   {stored_bytes}")
    print(f"Saving:         {saving:.2f}%")
    print(f"Unique chunks:  {unique_chunks}")
    print(f"Total refs:     {total_refs}")

    top_items: List[Tuple[str, int]] = ref_count.most_common(top)
    if top_items:
        print(f"\nTop {top} most referenced chunks:")
        for digest, count in top_items:
            sz = unique_sizes.get(digest, 0)
            print(f"  {digest}  refs={count}  size={sz}")


__all__ = ["stats"]
