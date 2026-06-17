"""Pack command - recursively chunk a directory and store deduplicated chunks.

Uses multiprocessing for parallel chunking while ensuring deterministic
output by sorting file paths and producing a sorted manifest.
"""

from __future__ import annotations

import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import NamedTuple

from .chunker.rabin_chunker import RabinChunker
from .hashing.sha256 import sha256
from .manifest.base import FileEntry, Manifest
from .manifest.manifest import TextManifest
from .store.content_store import FileContentStore


class _FileChunkResult(NamedTuple):
    path: str
    size: int
    mode: int
    chunk_digests: list[str]
    chunk_sizes: list[int]
    chunk_data: list[bytes]
    content_hash: str
    error: str | None = None


def _walk_files(root: Path) -> list[Path]:
    """Recursively collect all regular file paths, skipping symlinks.

    Returns paths sorted lexicographically for determinism.
    """
    files: list[Path] = []
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for filename in sorted(filenames):
            fpath = Path(dirpath) / filename
            try:
                if fpath.is_symlink():
                    continue
                if not fpath.is_file():
                    continue
            except OSError:
                print(f"warning: cannot stat {fpath}", file=sys.stderr)
                continue
            files.append(fpath)

    return files


def _chunk_file_worker(args: tuple[str, str, int, int, int]) -> _FileChunkResult:
    """Worker function for multiprocessing pool.

    Args:
        args: Tuple of (abs_path_str, rel_path_str, min_size, avg_size, max_size)

    Returns:
        _FileChunkResult with chunk info and data, or error info.
    """
    abs_path_str, rel_path, min_size, avg_size, max_size = args

    try:
        abs_path = Path(abs_path_str)
        data = abs_path.read_bytes()
        stat = abs_path.stat()
    except (OSError, PermissionError) as e:
        print(f"warning: cannot read {abs_path_str}: {e}", file=sys.stderr)
        return _FileChunkResult(
            path=rel_path,
            size=0,
            mode=0,
            chunk_digests=[],
            chunk_sizes=[],
            chunk_data=[],
            content_hash="",
            error=str(e),
        )

    chunker = RabinChunker(
        min_size=min_size,
        avg_size=avg_size,
        max_size=max_size,
    )

    chunk_results = chunker.chunk_data(data)
    digests = [c.digest for c in chunk_results]
    sizes = [c.size for c in chunk_results]
    datas = [c.data for c in chunk_results]

    content_hash = sha256(data).hexdigest()

    return _FileChunkResult(
        path=rel_path,
        size=len(data),
        mode=stat.st_mode & 0o7777,
        chunk_digests=digests,
        chunk_sizes=sizes,
        chunk_data=datas,
        content_hash=content_hash,
    )


def pack_directory(
    source_dir: str | os.PathLike,
    store_path: str | os.PathLike,
    manifest_path: str | os.PathLike | None = None,
    min_size: int = 2 * 1024,
    avg_size: int = 8 * 1024,
    max_size: int = 64 * 1024,
    num_workers: int | None = None,
) -> Manifest:
    """Pack a directory into a content-addressable store.

    Args:
        source_dir: Directory to pack recursively.
        store_path: Path to the content store directory.
        manifest_path: Path to write the manifest file. If None, writes to
                       <store_path>/manifest.txt.
        min_size: Minimum chunk size in bytes.
        avg_size: Target average chunk size in bytes.
        max_size: Maximum chunk size in bytes.
        num_workers: Number of worker processes. Defaults to os.cpu_count().

    Returns:
        The generated Manifest object.
    """
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise ValueError(f"Source is not a directory: {source_dir}")

    store = FileContentStore(store_path)

    files = _walk_files(source)

    manifest = TextManifest()
    manifest.set_chunker_config({
        "algorithm": "rabin",
        "min_size": min_size,
        "avg_size": avg_size,
        "max_size": max_size,
    })

    if not files:
        if manifest_path is None:
            manifest_path = Path(store_path) / "manifest.txt"
        manifest.save(manifest_path)
        return manifest

    worker_args: list[tuple[str, str, int, int, int]] = []
    for fpath in files:
        try:
            rel = fpath.relative_to(source)
        except ValueError:
            rel = fpath
        rel_str = str(rel).replace("\\", "/")
        worker_args.append((str(fpath), rel_str, min_size, avg_size, max_size))

    if num_workers is None:
        num_workers = max(1, os.cpu_count() or 1)

    results: list[_FileChunkResult] = []
    if num_workers <= 1:
        for args in worker_args:
            results.append(_chunk_file_worker(args))
    else:
        with Pool(processes=num_workers) as pool:
            results = pool.map(_chunk_file_worker, worker_args)

    results.sort(key=lambda r: r.path)

    seen_digests: set[str] = set()
    chunks_to_store: list[tuple[str, bytes]] = []

    for result in results:
        if result.error is not None:
            continue

        entry = FileEntry(
            path=result.path,
            size=result.size,
            mode=result.mode,
            chunks=list(result.chunk_digests),
            content_hash=result.content_hash,
        )
        manifest.add_file(entry)

        for digest, data in zip(result.chunk_digests, result.chunk_data):
            if digest not in seen_digests:
                seen_digests.add(digest)
                chunks_to_store.append((digest, data))

    chunks_to_store.sort(key=lambda x: x[0])
    for digest, data in chunks_to_store:
        store.put_chunk(digest, data)

    if manifest_path is None:
        manifest_path = Path(store_path) / "manifest.txt"

    manifest.save(manifest_path)
    return manifest
