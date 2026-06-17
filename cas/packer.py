"""Pack logic - directory traversal, parallel chunking, store writing,
manifest generation.

Uses multiprocessing for parallel file processing.  Each worker chunks
a file, hashes the chunks, and writes them directly to the store
(atomic rename ensures safety under concurrent writes).
"""

import os
import sys
import stat
from multiprocessing import Pool
from typing import List, Tuple, Optional

from .chunker import CDCChunker
from .hashing import SHA256Hasher
from .store import ContentStore
from .manifest import FileManifest, FileEntry


def _hash_data(data: bytes) -> str:
    h = SHA256Hasher()
    h.update(data)
    return h.hexdigest()


def _process_file(args: Tuple[str, str, int, int, int]) -> Optional[dict]:
    """Worker function: chunk a single file, write chunks to store,
    return file entry info.

    Args:
        args: (file_path, relpath, avg_size, min_size, max_size)

    Returns:
        dict with file entry info, or None if the file should be skipped.
    """
    file_path, relpath, avg_size, min_size, max_size = args

    try:
        file_stat = os.stat(file_path)
        if not stat.S_ISREG(file_stat.st_mode):
            return None
    except OSError as e:
        print(f"warning: cannot stat {file_path}: {e}", file=sys.stderr)
        return None

    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"warning: cannot read {file_path}: {e}", file=sys.stderr)
        return None

    file_hash = _hash_data(data)

    chunker = CDCChunker(avg_size=avg_size, min_size=min_size, max_size=max_size)
    chunk_digests: List[str] = []

    for chunk_data, _ in chunker.chunk(data):
        chunk_digest = _hash_data(chunk_data)
        chunk_digests.append(chunk_digest)
        yield_chunk = (chunk_digest, chunk_data)

    return {
        "relpath": relpath,
        "size": file_stat.st_size,
        "mode": file_stat.st_mode & 0o7777,
        "file_hash": file_hash,
        "chunks": chunk_digests,
        "chunk_data": list(chunker.chunk(data)),
    }


def _worker_process(args: Tuple[str, str, int, int, int, str]) -> Optional[dict]:
    """Worker function that also writes chunks to the store."""
    file_path, relpath, avg_size, min_size, max_size, store_root = args

    from .store import FileContentStore
    from .chunker import CDCChunker
    from .hashing import SHA256Hasher
    import os
    import stat
    import sys

    try:
        file_stat = os.stat(file_path)
        if not stat.S_ISREG(file_stat.st_mode):
            return None
    except OSError as e:
        print(f"warning: cannot stat {file_path}: {e}", file=sys.stderr)
        return None

    try:
        with open(file_path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"warning: cannot read {file_path}: {e}", file=sys.stderr)
        return None

    hasher = SHA256Hasher()
    hasher.update(data)
    file_hash = hasher.hexdigest()

    chunker = CDCChunker(avg_size=avg_size, min_size=min_size, max_size=max_size)
    store = FileContentStore(store_root)

    chunk_digests: List[str] = []
    for chunk_data, _ in chunker.chunk(data):
        chunk_hasher = SHA256Hasher()
        chunk_hasher.update(chunk_data)
        chunk_digest = chunk_hasher.hexdigest()
        chunk_digests.append(chunk_digest)
        store.put(chunk_digest, chunk_data)

    return {
        "relpath": relpath,
        "size": file_stat.st_size,
        "mode": file_stat.st_mode & 0o7777,
        "file_hash": file_hash,
        "chunks": chunk_digests,
    }


def _collect_files(root_dir: str) -> List[Tuple[str, str]]:
    """Collect all regular files under root_dir, skipping symlinks.

    Returns a list of (abs_path, rel_path) tuples sorted by rel_path
    for deterministic processing order.
    """
    files: List[Tuple[str, str]] = []
    root_dir = os.path.abspath(root_dir)

    for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
        dirnames.sort()
        for filename in sorted(filenames):
            full_path = os.path.join(dirpath, filename)
            if os.path.islink(full_path):
                continue
            if not os.path.isfile(full_path):
                continue
            rel_path = os.path.relpath(full_path, root_dir)
            files.append((full_path, rel_path))

    files.sort(key=lambda x: x[1])
    return files


def pack_directory(
    source_dir: str,
    store: ContentStore,
    avg_size: int = 8192,
    min_size: int = 2048,
    max_size: int = 65536,
    num_workers: Optional[int] = None,
) -> FileManifest:
    """Pack a directory into the content store.

    Args:
        source_dir: Path to the source directory.
        store: Content store to write chunks into.
        avg_size: Target average chunk size.
        min_size: Minimum chunk size.
        max_size: Maximum chunk size.
        num_workers: Number of worker processes (None = default).

    Returns:
        A FileManifest describing all files and their chunks.
    """
    if not os.path.isdir(source_dir):
        raise ValueError(f"Source directory does not exist: {source_dir}")

    files = _collect_files(source_dir)

    manifest = FileManifest(
        hash_algo="sha256",
        chunk_avg=avg_size,
        chunk_min=min_size,
        chunk_max=max_size,
    )

    if not files:
        return manifest

    store_root = store.root if hasattr(store, 'root') else ""

    if num_workers is None or num_workers <= 1:
        for abs_path, rel_path in files:
            result = _worker_process(
                (abs_path, rel_path, avg_size, min_size, max_size, store_root)
            )
            if result is not None:
                entry = FileEntry(
                    relpath=result["relpath"],
                    size=result["size"],
                    mode=result["mode"],
                    file_hash=result["file_hash"],
                    chunks=result["chunks"],
                )
                manifest.add_file(entry)
    else:
        tasks = [
            (abs_path, rel_path, avg_size, min_size, max_size, store_root)
            for abs_path, rel_path in files
        ]
        with Pool(processes=num_workers) as pool:
            results = pool.map(_worker_process, tasks)

        for result in sorted(results, key=lambda r: r["relpath"] if r else ""):
            if result is not None:
                entry = FileEntry(
                    relpath=result["relpath"],
                    size=result["size"],
                    mode=result["mode"],
                    file_hash=result["file_hash"],
                    chunks=result["chunks"],
                )
                manifest.add_file(entry)

    return manifest
