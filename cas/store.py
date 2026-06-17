from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Optional


class ContentStore(ABC):
    @abstractmethod
    def put(self, digest: str, data: bytes) -> None:
        ...

    @abstractmethod
    def get(self, digest: str) -> Optional[bytes]:
        ...

    @abstractmethod
    def contains(self, digest: str) -> bool:
        ...

    @abstractmethod
    def list_digests(self) -> Iterator[str]:
        ...


class FileSystemStore(ContentStore):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def put(self, digest: str, data: bytes) -> None:
        p = self._path(digest)
        if p.exists():
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        try:
            with open(tmp, "xb") as f:
                f.write(data)
            os.replace(tmp, p)
        except FileExistsError:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if not p.exists():
                with open(p, "xb") as f:
                    f.write(data)

    def get(self, digest: str) -> Optional[bytes]:
        p = self._path(digest)
        if p.exists():
            return p.read_bytes()
        return None

    def contains(self, digest: str) -> bool:
        return self._path(digest).exists()

    def list_digests(self) -> Iterator[str]:
        if not self.root.exists():
            return
        for shard in sorted(self.root.iterdir()):
            if not shard.is_dir():
                continue
            if len(shard.name) != 2:
                continue
            for f in sorted(shard.iterdir()):
                if f.is_file() and not f.suffix:
                    yield f.name


__all__ = ["ContentStore", "FileSystemStore"]
