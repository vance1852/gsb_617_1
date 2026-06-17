from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Set

from .manifest import Manifest
from .sha256 import SHA256
from .store import ContentStore, FileSystemStore


def verify(
    store_path: str | Path,
    manifest_path: Optional[str | Path] = None,
) -> int:
    store: ContentStore = FileSystemStore(store_path)
    corrupt = 0
    total = 0

    for digest in store.list_digests():
        total += 1
        data = store.get(digest)
        if data is None:
            print(f"Corrupt: {digest} (cannot read)", file=sys.stderr)
            corrupt += 1
            continue
        h = SHA256()
        h.update(data)
        actual = h.hexdigest()
        if actual != digest:
            print(
                f"Corrupt: {digest} (actual hash {actual})",
                file=sys.stderr,
            )
            corrupt += 1

    print(f"Verified {total} chunks, {corrupt} corrupt")

    missing = 0
    if manifest_path is not None:
        mf = Manifest.load(manifest_path)
        referenced: Set[str] = set()
        for entry in mf.entries:
            for _, chunk_digest in entry.chunks:
                referenced.add(chunk_digest)

        for d in sorted(referenced):
            if not store.contains(d):
                print(f"Missing: {d}", file=sys.stderr)
                missing += 1

        print(f"Referenced {len(referenced)} unique chunks, {missing} missing")

    return corrupt + missing


__all__ = ["verify"]
