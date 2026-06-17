"""File manifest - maps files to their chunk digests and metadata.

Manifest format (plain text, line-oriented, deterministic):

    CAS_MANIFEST_V1
    hash_algo=sha256
    chunk_avg=<int>
    chunk_min=<int>
    chunk_max=<int>
    num_files=<int>
    num_chunks=<int>
    total_bytes=<int>
    --
    FILE <relpath> <size> <mode> <file_sha256>
    CHUNK <digest>
    CHUNK <digest>
    ...
    FILE <relpath> <size> <mode> <file_sha256>
    CHUNK <digest>
    ...

Files are listed in sorted order by relative path to ensure
deterministic output regardless of traversal order.
"""

import os
import stat
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class FileEntry:
    """Metadata and chunk list for a single file."""
    relpath: str
    size: int
    mode: int
    file_hash: str
    chunks: List[str] = field(default_factory=list)


class FileManifest:
    """Manifest recording all files and their chunk composition."""

    _MAGIC = "CAS_MANIFEST_V1"

    def __init__(
        self,
        hash_algo: str = "sha256",
        chunk_avg: int = 8192,
        chunk_min: int = 2048,
        chunk_max: int = 65536,
    ) -> None:
        self.hash_algo = hash_algo
        self.chunk_avg = chunk_avg
        self.chunk_min = chunk_min
        self.chunk_max = chunk_max
        self._files: Dict[str, FileEntry] = {}

    def add_file(self, entry: FileEntry) -> None:
        self._files[entry.relpath] = entry

    def get_file(self, relpath: str) -> FileEntry:
        return self._files[relpath]

    def has_file(self, relpath: str) -> bool:
        return relpath in self._files

    @property
    def files(self) -> List[FileEntry]:
        return [self._files[p] for p in sorted(self._files.keys())]

    @property
    def num_files(self) -> int:
        return len(self._files)

    @property
    def total_bytes(self) -> int:
        return sum(e.size for e in self._files.values())

    @property
    def total_chunk_refs(self) -> int:
        return sum(len(e.chunks) for e in self._files.values())

    def all_chunk_digests(self) -> List[str]:
        """Return all unique chunk digests referenced by the manifest."""
        digests = set()
        for entry in self._files.values():
            digests.update(entry.chunks)
        return sorted(digests)

    def chunk_reference_counts(self) -> Dict[str, int]:
        """Return a dict mapping chunk digest to reference count."""
        counts: Dict[str, int] = {}
        for entry in self._files.values():
            for d in entry.chunks:
                counts[d] = counts.get(d, 0) + 1
        return counts

    def serialize(self) -> str:
        """Serialize to the canonical text format."""
        lines = [
            self._MAGIC,
            f"hash_algo={self.hash_algo}",
            f"chunk_avg={self.chunk_avg}",
            f"chunk_min={self.chunk_min}",
            f"chunk_max={self.chunk_max}",
            f"num_files={self.num_files}",
            f"num_chunks={len(self.all_chunk_digests())}",
            f"total_bytes={self.total_bytes}",
            "--",
        ]
        for entry in self.files:
            lines.append(
                f"FILE {entry.relpath} {entry.size} {entry.mode} {entry.file_hash}"
            )
            for chunk_digest in entry.chunks:
                lines.append(f"CHUNK {chunk_digest}")
        return "\n".join(lines) + "\n"

    @classmethod
    def parse(cls, text: str) -> "FileManifest":
        """Parse a manifest from its text representation."""
        lines = text.strip().split("\n")
        if not lines or lines[0] != cls._MAGIC:
            raise ValueError("Invalid manifest: bad magic")

        manifest = cls()
        i = 1
        while i < len(lines) and lines[i] != "--":
            line = lines[i]
            if "=" in line:
                key, val = line.split("=", 1)
                if key == "hash_algo":
                    manifest.hash_algo = val
                elif key == "chunk_avg":
                    manifest.chunk_avg = int(val)
                elif key == "chunk_min":
                    manifest.chunk_min = int(val)
                elif key == "chunk_max":
                    manifest.chunk_max = int(val)
            i += 1

        if i >= len(lines) or lines[i] != "--":
            raise ValueError("Invalid manifest: missing separator")
        i += 1

        current_entry: FileEntry | None = None
        while i < len(lines):
            line = lines[i]
            if line.startswith("FILE "):
                parts = line[5:].split(" ")
                if len(parts) < 4:
                    raise ValueError(f"Invalid FILE entry: {line}")
                relpath = parts[0]
                size = int(parts[1])
                mode = int(parts[2])
                file_hash = parts[3]
                current_entry = FileEntry(
                    relpath=relpath,
                    size=size,
                    mode=mode,
                    file_hash=file_hash,
                )
                manifest.add_file(current_entry)
            elif line.startswith("CHUNK "):
                if current_entry is None:
                    raise ValueError("CHUNK without preceding FILE")
                current_entry.chunks.append(line[6:])
            i += 1

        return manifest

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.serialize())

    @classmethod
    def load(cls, path: str) -> "FileManifest":
        with open(path, "r", encoding="utf-8") as f:
            return cls.parse(f.read())
