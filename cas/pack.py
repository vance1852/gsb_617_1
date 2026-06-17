from __future__ import annotations

import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import List, Optional, Tuple

from .chunker import Chunker, RabinChunker
from .manifest import Manifest, ManifestEntry
from .sha256 import Hasher, SHA256
from .store import ContentStore, FileSystemStore


def _walk_directory(directory: str | Path) -> List[Tuple[str, str]]:
    base = Path(directory).resolve()
    files: List[Tuple[str, str]] = []
    for root, dirs, filenames in os.walk(base, followlinks=False):
        dirs.sort()
        root_path = Path(root)
        for name in sorted(filenames):
            abs_path = root_path / name
            if abs_path.is_symlink():
                continue
            rel = abs_path.relative_to(base).as_posix()
            files.append((rel, str(abs_path)))
    return files


def _pack_file(
    rel_path: str,
    abs_path: str,
    store_path: str,
    chunker_cls: type,
    chunker_kwargs: dict,
    hasher_cls: type,
) -> Optional[ManifestEntry]:
    try:
        data = Path(abs_path).read_bytes()
    except OSError as e:
        print(f"Warning: cannot read {rel_path}: {e}", file=sys.stderr)
        return None

    mode = 0
    try:
        mode = Path(abs_path).stat().st_mode
    except OSError:
        pass

    store = FileSystemStore(store_path)
    chunker: Chunker = chunker_cls(**chunker_kwargs)

    file_hasher: Hasher = hasher_cls()
    file_hasher.update(data)
    file_hash = file_hasher.hexdigest()

    chunks: List[Tuple[int, str]] = []
    for chunk_data in chunker.chunk(data):
        chunk_hasher: Hasher = hasher_cls()
        chunk_hasher.update(chunk_data)
        chunk_digest = chunk_hasher.hexdigest()
        store.put(chunk_digest, chunk_data)
        chunks.append((len(chunk_data), chunk_digest))

    return ManifestEntry(
        path=rel_path,
        size=len(data),
        mode=mode,
        file_hash=file_hash,
        chunks=chunks,
    )


def _pack_file_wrapper(args: tuple) -> Optional[ManifestEntry]:
    return _pack_file(*args)


def pack(
    directory: str | Path,
    store_path: str | Path,
    chunker_cls: type = RabinChunker,
    chunker_kwargs: Optional[dict] = None,
    hasher_cls: type = SHA256,
    workers: Optional[int] = None,
) -> Manifest:
    directory = Path(directory).resolve()
    store_path = str(Path(store_path).resolve())

    if chunker_kwargs is None:
        chunker_kwargs = {}

    files = _walk_directory(directory)

    if not files:
        return Manifest(entries=[])

    args = [
        (rel, absp, store_path, chunker_cls, chunker_kwargs, hasher_cls)
        for rel, absp in files
    ]

    if workers != 1 and len(files) > 1:
        with Pool(processes=workers) as pool:
            results = pool.map(_pack_file_wrapper, args)
    else:
        results = [_pack_file_wrapper(a) for a in args]

    entries: List[ManifestEntry] = []
    for r in results:
        if r is not None:
            entries.append(r)

    entries.sort(key=lambda e: e.path)
    return Manifest(entries=entries)


__all__ = ["pack"]
