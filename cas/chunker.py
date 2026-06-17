from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Iterator


class Chunker(ABC):
    @abstractmethod
    def chunk(self, data: bytes) -> Iterator[bytes]:
        ...


_RABIN_PRIME = (1 << 31) - 1
_RABIN_BASE = 0x101
_RABIN_WINDOW = 48


class RabinChunker(Chunker):
    def __init__(
        self,
        avg_size: int = 8192,
        min_size: int = 2048,
        max_size: int = 65536,
    ) -> None:
        self.avg_size = avg_size
        self.min_size = min_size
        self.max_size = max_size
        self._mask_bits = int(math.log2(avg_size))
        self._mask = (1 << self._mask_bits) - 1
        self._pow_base = pow(_RABIN_BASE, _RABIN_WINDOW - 1, _RABIN_PRIME)

    def chunk(self, data: bytes) -> Iterator[bytes]:
        if not data:
            return

        fp = 0
        window = bytearray(_RABIN_WINDOW)
        wpos = 0
        mask = self._mask
        min_sz = self.min_size
        max_sz = self.max_size
        prime = _RABIN_PRIME
        base = _RABIN_BASE
        pow_base = self._pow_base
        win_sz = _RABIN_WINDOW

        start = 0
        n = len(data)

        for i in range(n):
            byte_in = data[i]
            byte_out = window[wpos]
            fp = ((fp - byte_out * pow_base) * base + byte_in) % prime
            window[wpos] = byte_in
            wpos = (wpos + 1) % win_sz

            pos = i - start + 1
            if pos >= min_sz:
                if pos >= max_sz or (fp & mask == 0):
                    yield data[start : i + 1]
                    start = i + 1
                    fp = 0
                    window = bytearray(win_sz)
                    wpos = 0

        if start < n:
            yield data[start:n]


__all__ = ["Chunker", "RabinChunker"]
