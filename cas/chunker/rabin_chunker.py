"""Rabin-based Content-Defined Chunking implementation.

Uses a rolling Rabin fingerprint to find content-dependent chunk
boundaries, with min/avg/max size constraints.
"""

from __future__ import annotations

import io
from typing import Iterator

from ..hashing.rolling import ChunkBoundaryDetector
from ..hashing.sha256 import sha256
from .base import ChunkResult, Chunker


class RabinChunker(Chunker):
    """Content-defined chunker using Rabin fingerprint rolling hash.

    Chunk boundaries are determined by the rolling hash of a sliding window
    matching a bitmask pattern, subject to minimum and maximum size limits.
    """

    def __init__(
        self,
        min_size: int = 2 * 1024,
        avg_size: int = 8 * 1024,
        max_size: int = 64 * 1024,
        window_size: int = 48,
    ) -> None:
        self._min_size = min_size
        self._avg_size = avg_size
        self._max_size = max_size
        self._window_size = window_size

    @property
    def min_size(self) -> int:
        return self._min_size

    @property
    def avg_size(self) -> int:
        return self._avg_size

    @property
    def max_size(self) -> int:
        return self._max_size

    def chunk_data(self, data: bytes) -> list[ChunkResult]:
        results: list[ChunkResult] = []
        for chunk in self.chunk_stream(iter([data])):
            results.append(chunk)
        return results

    def chunk_stream(self, stream: Iterator[bytes]) -> Iterator[ChunkResult]:
        detector = ChunkBoundaryDetector(
            min_size=self._min_size,
            avg_size=self._avg_size,
            max_size=self._max_size,
            window_size=self._window_size,
        )

        chunk_buf = bytearray()
        hasher = sha256()
        current_size = 0

        for block in stream:
            if not block:
                continue
            for byte in block:
                chunk_buf.append(byte)
                hasher.update(bytes([byte]))
                current_size += 1

                if detector.feed_byte(byte):
                    data = bytes(chunk_buf)
                    digest = hasher.hexdigest()
                    yield ChunkResult(data=data, digest=digest, size=current_size)
                    chunk_buf = bytearray()
                    hasher = sha256()
                    current_size = 0
                    detector.reset()

        if current_size > 0:
            data = bytes(chunk_buf)
            digest = hasher.hexdigest()
            yield ChunkResult(data=data, digest=digest, size=current_size)
