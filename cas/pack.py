"""Pack command implementation.

Recursively scans a directory, chunks all files in parallel using a
multiprocessing pool, stores unique chunks in the content-addressed
store, and produces a manifest file describing all files and their
chunk composition.

Determinism guarantees:
- Files are sorted by relative path before processing
- Chunk boundaries are deterministic (Rabin CDC)
- Manifest is written with files in sorted order
- The store is content-addressed, so identical content always maps
  to the same address regardless of write order
"""

from __future__ import annotations

import os
import stat
import sys
import multiprocessing
from typing import List, Tuple, Optional

from .abc import FileEntry
from .store import FileContentStore
from .manifest import FileManifest
from .rabin import RabinChunker
from .sha256 import sha256


def _to_posix_path(path: str) -> str:
    """Convert a filesystem path to POSIX style with forward slashes."""
    return path.replace(os.sep, "/")


def _collect_files(root_dir: str) -> List[Tuple[str, str]]:
    """Collect all regular files under root_dir, skipping symlinks.

    Returns a sorted list of (absolute_path, relative_path) tuples,
    sorted by relative path for determinism.

    Files that cannot be stat'd are skipped with a warning to stderr.
    """
    root_dir = os.path.abspath(root_dir)
    files: List[Tuple[str, str]] = []

    for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
        dirnames.sort()
        filenames.sort()

        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)

            try:
                st = os.lstat(abs_path)
            except OSError as e:
                print(f"warning: cannot stat {abs_path}: {e}", file=sys.stderr)
                continue

            if stat.S_ISLNK(st.st_mode):
                continue

            if not stat.S_ISREG(st.st_mode):
                continue

            rel_path = os.path.relpath(abs_path, root_dir)
            rel_path = _to_posix_path(rel_path)
            files.append((abs_path, rel_path))

    files.sort(key=lambda x: x[1])
    return files


def _process_file(args: Tuple[str, str, str, int, int, int]) -> Optional[FileEntry]:
    """Process a single file: read, chunk, hash, and store chunks.

    This function is designed to run in a worker process. It reads the
    file, splits it into chunks using Rabin CDC, hashes each chunk
    with SHA-256, and stores all chunks in the content store.

    Args:
        args: Tuple of (abs_path, rel_path, store_path, avg_size,
              min_size, max_size)

    Returns:
        A FileEntry describing the file and its chunks, or None if
        the file could not be processed.
    """
    abs_path, rel_path, store_path, avg_size, min_size, max_size = args

    try:
        st = os.stat(abs_path)
    except OSError as e:
        print(f"warning: cannot stat {abs_path}: {e}", file=sys.stderr)
        return None

    try:
        with open(abs_path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"warning: cannot read {abs_path}: {e}", file=sys.stderr)
        return None

    chunker = RabinChunker(
        avg_size=avg_size,
        min_size=min_size,
        max_size=max_size,
    )
    chunks = chunker.chunk(data)

    store = FileContentStore(store_path)

    chunk_digests: List[str] = []
    for chunk_data in chunks:
        digest = store.put(chunk_data)
        chunk_digests.append(digest)

    file_hash = sha256(data).hexdigest()

    return FileEntry(
        path=rel_path,
        size=st.st_size,
        mode=st.st_mode,
        chunks=chunk_digests,
        file_hash=file_hash,
    )


def pack_directory(
    source_dir: str,
    store_path: str,
    manifest_path: str,
    avg_size: int = 8192,
    min_size: int = 2048,
    max_size: int = 65536,
    num_workers: Optional[int] = None,
) -> FileManifest:
    """Pack a directory into the content-addressed store.

    Args:
        source_dir: Path to the directory to pack.
        store_path: Path to the content-addressed store directory.
        manifest_path: Path where the manifest file will be written.
        avg_size: Target average chunk size in bytes.
        min_size: Minimum chunk size in bytes.
        max_size: Maximum chunk size in bytes.
        num_workers: Number of worker processes. None means use
                     os.cpu_count().

    Returns:
        The FileManifest that was written.
    """
    if not os.path.isdir(source_dir):
        raise NotADirectoryError(f"Source directory not found: {source_dir}")

    files = _collect_files(source_dir)

    if not files:
        print(f"warning: no files found in {source_dir}", file=sys.stderr)

    work_items = [
        (abs_path, rel_path, store_path, avg_size, min_size, max_size)
        for abs_path, rel_path in files
    ]

    manifest = FileManifest()
    manifest.hash_algo = "sha256"
    manifest.chunk_algo = "rabin"
    manifest.chunk_avg_size = avg_size
    manifest.chunk_min_size = min_size
    manifest.chunk_max_size = max_size

    if num_workers is None:
        num_workers = os.cpu_count() or 1

    if num_workers <= 1 or len(work_items) <= 1:
        for item in work_items:
            entry = _process_file(item)
            if entry is not None:
                manifest.add_file(entry)
    else:
        with multiprocessing.Pool(processes=num_workers) as pool:
            results = pool.map(_process_file, work_items)

        for entry in results:
            if entry is not None:
                manifest.add_file(entry)

    manifest.save(manifest_path)
    return manifest
