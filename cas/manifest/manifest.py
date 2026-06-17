"""Line-based text manifest format.

Format specification (deterministic, sort-order independent):

    VERSION 1
    CHUNKER rabin 2048 8192 65536
    FILE <path> <size> <mode> <content_hash>
    CHUNK <digest_1>
    CHUNK <digest_2>
    ...
    FILE <next_path> <size> <mode> <content_hash>
    CHUNK <digest_1>
    ...

Files are emitted in sorted (lexicographic) path order for determinism.
All fields are whitespace-separated; paths are URL-encoded if they contain
spaces or special characters.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Iterator

from .base import FileEntry, Manifest


class TextManifest(Manifest):
    """Text-based manifest implementation with deterministic output."""

    _VERSION = "1"

    def __init__(self) -> None:
        self._files: dict[str, FileEntry] = {}
        self._chunker_config: dict[str, int | str] = {}

    def add_file(self, entry: FileEntry) -> None:
        self._files[entry.path] = entry

    def iter_files(self) -> Iterator[FileEntry]:
        for path in sorted(self._files.keys()):
            yield self._files[path]

    def get_file(self, path: str) -> FileEntry | None:
        return self._files.get(path)

    def set_chunker_config(self, config: dict[str, int | str]) -> None:
        self._chunker_config = dict(config)

    def get_chunker_config(self) -> dict[str, int | str]:
        return dict(self._chunker_config)

    def save(self, path: str | os.PathLike) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append(f"VERSION {self._VERSION}")

        cfg = self._chunker_config
        if cfg:
            algo = cfg.get("algorithm", "rabin")
            min_s = cfg.get("min_size", 0)
            avg_s = cfg.get("avg_size", 0)
            max_s = cfg.get("max_size", 0)
            lines.append(f"CHUNKER {algo} {min_s} {avg_s} {max_s}")

        for entry in self.iter_files():
            encoded_path = urllib.parse.quote(entry.path)
            lines.append(
                f"FILE {encoded_path} {entry.size} {entry.mode} {entry.content_hash}"
            )
            for digest in entry.chunks:
                lines.append(f"CHUNK {digest}")

        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | os.PathLike) -> "TextManifest":
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()

        manifest = cls()
        current_file: FileEntry | None = None

        for line in lines:
            if not line:
                continue

            parts = line.split(" ", 1)
            tag = parts[0]

            if tag == "VERSION":
                continue

            elif tag == "CHUNKER":
                rest = parts[1] if len(parts) > 1 else ""
                fields = rest.split()
                if len(fields) >= 4:
                    manifest._chunker_config = {
                        "algorithm": fields[0],
                        "min_size": int(fields[1]),
                        "avg_size": int(fields[2]),
                        "max_size": int(fields[3]),
                    }

            elif tag == "FILE":
                rest = parts[1] if len(parts) > 1 else ""
                fields = rest.split()
                if len(fields) >= 4:
                    file_path = urllib.parse.unquote(fields[0])
                    size = int(fields[1])
                    mode = int(fields[2])
                    content_hash = fields[3]
                    current_file = FileEntry(
                        path=file_path,
                        size=size,
                        mode=mode,
                        content_hash=content_hash,
                    )
                    manifest.add_file(current_file)

            elif tag == "CHUNK":
                if current_file is not None:
                    digest = parts[1].strip() if len(parts) > 1 else ""
                    if digest:
                        current_file.chunks.append(digest)

        return manifest
