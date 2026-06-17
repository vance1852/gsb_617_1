from __future__ import annotations

import sys
from pathlib import Path
from typing import Union

from .manifest import Manifest, ManifestEntry
from .sha256 import SHA256
from .store import ContentStore, FileSystemStore


def restore(
    manifest_path: Union[str, Path],
    store_path: Union[str, Path],
    out_dir: Union[str, Path],
) -> None:
    mf = Manifest.load(manifest_path)
    store: ContentStore = FileSystemStore(store_path)
    out = Path(out_dir).resolve()

    for entry in mf.entries:
        target = out / entry.path
        target.parent.mkdir(parents=True, exist_ok=True)

        parts: list[bytes] = []
        for chunk_size, chunk_digest in entry.chunks:
            data = store.get(chunk_digest)
            if data is None:
                print(
                    f"Error: missing chunk {chunk_digest} for file {entry.path}",
                    file=sys.stderr,
                )
                sys.exit(1)
            if len(data) != chunk_size:
                print(
                    f"Error: chunk {chunk_digest} size mismatch "
                    f"(expected {chunk_size}, got {len(data)}) for file {entry.path}",
                    file=sys.stderr,
                )
                sys.exit(1)
            chunk_hasher = SHA256()
            chunk_hasher.update(data)
            if chunk_hasher.hexdigest() != chunk_digest:
                print(
                    f"Error: chunk {chunk_digest} hash mismatch for file {entry.path}",
                    file=sys.stderr,
                )
                sys.exit(1)
            parts.append(data)

        content = b"".join(parts)

        if len(content) != entry.size:
            print(
                f"Error: file {entry.path} size mismatch "
                f"(expected {entry.size}, got {len(content)})",
                file=sys.stderr,
            )
            sys.exit(1)

        file_hasher = SHA256()
        file_hasher.update(content)
        if file_hasher.hexdigest() != entry.file_hash:
            print(
                f"Error: file {entry.path} hash mismatch",
                file=sys.stderr,
            )
            sys.exit(1)

        with open(target, "wb") as f:
            f.write(content)

        try:
            target.chmod(entry.mode)
        except OSError:
            pass


__all__ = ["restore"]
