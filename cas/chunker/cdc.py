"""Content-Defined Chunker using Rabin fingerprint rolling hash.

Chunks are cut when the rolling hash & mask == 0, subject to min/max
size constraints.  The mask is derived from the target average chunk
size so that the expected chunk size is approximately avg_size.
"""

import math
from typing import Iterator, Tuple, Optional

from .abc import Chunker, RollingHash
from .rabin import RabinFingerprint


class CDCChunker(Chunker):
    """Content-Defined Chunker with min/max/avg size constraints."""

    def __init__(
        self,
        avg_size: int = 8192,
        min_size: int = 2048,
        max_size: int = 65536,
        rolling_hash: Optional[RollingHash] = None,
    ) -> None:
        if min_size <= 0:
            raise ValueError("min_size must be positive")
        if max_size <= min_size:
            raise ValueError("max_size must be > min_size")
        if avg_size <= min_size or avg_size >= max_size:
            raise ValueError("avg_size must be between min_size and max_size")

        self._avg_size = avg_size
        self._min_size = min_size
        self._max_size = max_size
        self._mask = self._derive_mask(avg_size)
        self._rolling_hash = rolling_hash or RabinFingerprint()

    @staticmethod
    def _derive_mask(avg_size: int) -> int:
        """Derive a bitmask such that probability of (hash & mask) == 0
        yields approximately the target average chunk size.
        """
        bits = max(1, int(math.log2(avg_size)))
        return (1 << bits) - 1

    @property
    def avg_size(self) -> int:
        return self._avg_size

    @property
    def min_size(self) -> int:
        return self._min_size

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def mask(self) -> int:
        return self._mask

    def chunk(self, data: bytes) -> Iterator[Tuple[bytes, int]]:
        """Yield (chunk_bytes, offset) tuples by content-defined chunking.

        The chunking algorithm:
        1. Slide the window until at least min_size bytes have been seen.
        2. Once past min_size, cut whenever (rolling_hash & mask) == 0.
        3. Always cut at max_size if no cut point was found.
        4. The final chunk is emitted even if smaller than min_size.
        """
        if not data:
            return

        data_len = len(data)
        offset = 0
        rh = self._rolling_hash
        ws = rh.window_size

        while offset < data_len:
            remaining = data_len - offset
            if remaining <= self._min_size:
                yield data[offset:], offset
                return

            rh.reset()
            chunk_start = offset
            window_end = min(chunk_start + ws, data_len)
            rh.update(data[chunk_start:window_end])

            pos = chunk_start + ws

            cut_at = -1
            max_cut = min(chunk_start + self._max_size, data_len)

            while pos < max_cut:
                if pos - chunk_start >= self._min_size:
                    if (rh.digest() & self._mask) == 0:
                        cut_at = pos
                        break

                if pos < data_len:
                    out_byte = data[pos - ws]
                    in_byte = data[pos]
                    rh.roll(out_byte, in_byte)
                pos += 1

            if cut_at == -1:
                cut_at = max_cut

            yield data[chunk_start:cut_at], chunk_start
            offset = cut_at
