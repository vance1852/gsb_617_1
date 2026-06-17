"""Rabin fingerprint rolling hash chunker with O(1) incremental updates.

Implements Content-Defined Chunking (CDC) using Rabin fingerprints.
The rolling hash is updated in O(1) time when sliding the window:
- Remove the contribution of the byte sliding out
- Add the contribution of the byte sliding in
"""

from __future__ import annotations

import math
from typing import List, Iterator

from .abc import Chunker


DEFAULT_WINDOW_SIZE = 48
DEFAULT_BASE = 257
DEFAULT_MODULUS = (1 << 41) - 1  # Large prime-like modulus


class RabinChunker(Chunker):
    """Content-defined chunker using Rabin fingerprint rolling hash.

    The rolling hash is updated in truly O(1) fashion: when the window
    slides forward by one byte, we:
    1. Subtract the contribution of the byte that slides out (the old
       leftmost byte, weighted by base^(window_size-1))
    2. Multiply the hash by base to shift all bytes up in significance
    3. Add the new byte that slides in on the right

    Chunk boundary condition:
    - The chunk is at least min_size bytes long
    - The rolling hash at some position & chunk_mask == 0
    - The chunk is forced at max_size bytes if no natural cut is found
    """

    def __init__(
        self,
        avg_size: int = 8192,
        min_size: int = 2048,
        max_size: int = 65536,
        window_size: int = DEFAULT_WINDOW_SIZE,
    ) -> None:
        self.avg_size = avg_size
        self.min_size = min_size
        self.max_size = max_size
        self.window_size = window_size

        self._base = DEFAULT_BASE
        self._modulus = DEFAULT_MODULUS
        self._mask = self._derive_mask(avg_size)
        self._base_power = self._precompute_base_power()

    def _derive_mask(self, avg_size: int) -> int:
        """Derive the chunking mask from the target average chunk size.

        The number of bits in the mask determines the probability that
        a random window position is a cut point. We use mask bits =
        floor(log2(avg_size)), so the probability of a cut at any
        position is roughly 1/avg_size.
        """
        bits = max(1, int(math.log2(avg_size)))
        return (1 << bits) - 1

    def _precompute_base_power(self) -> int:
        """Precompute base^(window_size-1) mod modulus.

        This is the weight of the leftmost (oldest) byte in the window.
        We need this to subtract the outgoing byte's contribution in
        O(1) time when the window slides.
        """
        return pow(self._base, self.window_size - 1, self._modulus)

    def _initial_hash(self, window: bytes) -> int:
        """Compute the Rabin hash of the initial window.

        The hash is computed as:
            h = b_0 * base^(w-1) + b_1 * base^(w-2) + ... + b_(w-1)
        where w is window_size.
        This is equivalent to Horner's method:
            h = 0
            for each byte b in window:
                h = (h * base + b) % modulus
        """
        h = 0
        for b in window:
            h = ((h * self._base) + b) % self._modulus
        return h

    def _roll_hash(self, h: int, out_byte: int, in_byte: int) -> int:
        """Roll the hash forward by one position — O(1) update.

        Given the hash of window [b_i, b_{i+1}, ..., b_{i+w-1}],
        compute the hash of window [b_{i+1}, b_{i+2}, ..., b_{i+w}].

        Steps (all modulo modulus):
        1. Subtract out_byte * base^(w-1)  — remove the leftmost byte's contribution
        2. Multiply by base                — shift all bytes left (increase significance)
        3. Add in_byte                     — add the new rightmost byte

        This is truly O(1): constant time regardless of window size.
        """
        h = (h - (out_byte * self._base_power) % self._modulus) % self._modulus
        h = (h + self._modulus) % self._modulus  # Ensure non-negative
        h = (h * self._base) % self._modulus
        h = (h + in_byte) % self._modulus
        return h

    def chunk(self, data: bytes) -> List[bytes]:
        """Split data into chunks using Rabin fingerprint CDC.

        The algorithm:
        1. Start at position start
        2. Compute initial window hash at start
        3. Slide the window forward, one byte at a time, updating
           the rolling hash in O(1)
        4. After sliding past min_size, check if the hash satisfies
           the cut condition (hash & mask == 0)
        5. If a cut point is found, or we reach max_size, emit the
           chunk and continue from the new start position

        Args:
            data: The input byte stream to chunk.

        Returns:
            List of bytes, each being a chunk.
        """
        chunks: List[bytes] = []
        n = len(data)
        start = 0

        while start < n:
            remaining = n - start

            if remaining <= self.min_size:
                chunks.append(data[start:])
                break

            if remaining <= self.window_size:
                chunks.append(data[start:])
                break

            initial_window = data[start:start + self.window_size]
            current_hash = self._initial_hash(initial_window)

            cut_pos = -1
            search_start = start + self.min_size
            search_end = min(start + self.max_size, n)

            w_start = start
            while w_start + self.window_size <= search_end:
                if w_start + self.window_size >= search_start:
                    if (current_hash & self._mask) == 0:
                        cut_pos = w_start + self.window_size
                        break

                if w_start + self.window_size < n:
                    out_byte = data[w_start]
                    in_byte = data[w_start + self.window_size]
                    current_hash = self._roll_hash(current_hash, out_byte, in_byte)

                w_start += 1

            if cut_pos == -1:
                cut_pos = search_end

            chunks.append(data[start:cut_pos])
            start = cut_pos

        return chunks

    def chunk_stream(self, stream: Iterator[bytes]) -> Iterator[bytes]:
        """Chunk a stream of data.

        This is a streaming version that processes data incrementally.

        Args:
            stream: Iterator yielding bytes objects.

        Yields:
            Chunks of bytes.
        """
        buffer = bytearray()

        for data in stream:
            buffer.extend(data)

            while len(buffer) >= self.max_size:
                chunks = self.chunk(bytes(buffer))
                if len(chunks) >= 2:
                    for c in chunks[:-1]:
                        yield c
                    buffer = bytearray(chunks[-1])
                else:
                    break

        if buffer:
            for c in self.chunk(bytes(buffer)):
                yield c
