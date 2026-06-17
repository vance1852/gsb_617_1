from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


_MAGIC = "CAS_MANIFEST_1"


@dataclass
class ManifestEntry:
    path: str
    size: int
    mode: int
    file_hash: str
    chunks: List[Tuple[int, str]]


@dataclass
class Manifest:
    entries: List[ManifestEntry] = field(default_factory=list)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(_MAGIC + "\n")
            for entry in self.entries:
                chunk_strs = [f"{sz}:{d}" for sz, d in entry.chunks]
                f.write(
                    f"{entry.path}\t{entry.size}\t{entry.mode}\t{entry.file_hash}\t{','.join(chunk_strs)}\n"
                )

    @staticmethod
    def load(path: str | Path) -> Manifest:
        p = Path(path)
        entries: List[ManifestEntry] = []
        with open(p, "r", encoding="utf-8") as f:
            header = f.readline().rstrip("\n")
            if header != _MAGIC:
                raise ValueError(f"Invalid manifest header: {header!r}")
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) != 5:
                    raise ValueError(f"Invalid manifest line: {line!r}")
                rel_path, size_str, mode_str, file_hash, chunk_str = parts
                size = int(size_str)
                mode = int(mode_str)
                chunks: List[Tuple[int, str]] = []
                if chunk_str:
                    for c in chunk_str.split(","):
                        sz_s, digest = c.split(":", 1)
                        chunks.append((int(sz_s), digest))
                entries.append(
                    ManifestEntry(
                        path=rel_path,
                        size=size,
                        mode=mode,
                        file_hash=file_hash,
                        chunks=chunks,
                    )
                )
        return Manifest(entries)


__all__ = ["Manifest", "ManifestEntry"]
