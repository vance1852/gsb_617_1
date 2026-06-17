"""Rabin fingerprint rolling hash with O(1) incremental updates.

Implements a sliding-window Rabin fingerprint that can be updated
in constant time by removing the byte that slides out and adding
the byte that slides in, without recomputing the entire window.
"""

from __future__ import annotations

from typing import Final

_DEFAULT_BASE: Final[int] = 110351524523
_DEFAULT_MOD: Final[int] = 0xFFFFFFFFFFFFFFFF
_DEFAULT_WINDOW_SIZE: Final[int] = 48


class RabinRollingHash:
    """Rabin fingerprint rolling hash with O(1) window slide.

    The fingerprint of a window [b0, b1, ..., b(n-1)] is computed as:
        fp = b0 * base^(n-1) + b1 * base^(n-2) + ... + b(n-1) * base^0
    all modulo mod_value.

    Sliding the window by one byte (removing b0, appending bn):
        fp = ((fp - b0 * base^(n-1)) * base + bn) % mod_value
    This is O(1) per slide.
    """

    def __init__(
        self,
        window_size: int = _DEFAULT_WINDOW_SIZE,
        base: int = _DEFAULT_BASE,
        mod_value: int = _DEFAULT_MOD,
    ) -> None:
        self._window_size = window_size
        self._base = base
        self._mod = mod_value
        self._fp = 0
        self._window: list[int] = []
        self._base_power = pow(base, window_size - 1, mod_value)

    def reset(self) -> None:
        self._fp = 0
        self._window = []

    def init(self, data: bytes) -> None:
        """Initialize the rolling hash with the first window of data."""
        self.reset()
        n = min(len(data), self._window_size)
        for i in range(n):
            b = data[i]
            self._fp = ((self._fp * self._base) + b) % self._mod
            self._window.append(b)

    def roll(self, out_byte: int, in_byte: int) -> int:
        """Slide the window: remove out_byte, append in_byte.

        Returns the new fingerprint value.
        """
        self._fp = (
            ((self._fp - (out_byte * self._base_power) % self._mod) * self._base + in_byte)
            % self._mod
        )
        self._window.pop(0)
        self._window.append(in_byte)
        return self._fp

    @property
    def fingerprint(self) -> int:
        return self._fp

    @property
    def window_size(self) -> int:
        return self._window_size

    def __len__(self) -> int:
        return len(self._window)


class ChunkBoundaryDetector:
    """Wraps RabinRollingHash to detect chunk boundaries using a bitmask.

    A boundary is found when (fingerprint & mask) == 0, with min/max size
    constraints to prevent degenerate chunks.
    """

    def __init__(
        self,
        min_size: int,
        avg_size: int,
        max_size: int,
        window_size: int = _DEFAULT_WINDOW_SIZE,
    ) -> None:
        if min_size < window_size:
            min_size = window_size
        if min_size >= max_size:
            raise ValueError("min_size must be less than max_size")
        if avg_size <= 0:
            raise ValueError("avg_size must be positive")

        self._min_size = min_size
        self._avg_size = avg_size
        self._max_size = max_size
        self._mask = self._derive_mask(avg_size)
        self._rh = RabinRollingHash(window_size=window_size)
        self._window_size = window_size
        self.reset()

    @staticmethod
    def _derive_mask(avg_size: int) -> int:
        """Derive a bitmask such that boundary probability ~ 1/avg_size.

        The mask has floor(log2(avg_size)) lower bits set to 1.
        For example, avg_size=8192 (2^13) → mask = 0x1FFF (13 bits set).
        """
        bits = max(1, avg_size.bit_length() - 1)
        return (1 << bits) - 1

    @property
    def mask(self) -> int:
        return self._mask

    @property
    def min_size(self) -> int:
        return self._min_size

    @property
    def max_size(self) -> int:
        return self._max_size

    def reset(self) -> None:
        self._rh.reset()
        self._bytes_seen = 0
        self._buffer: list[int] = []

    def feed_byte(self, b: int) -> bool:
        """Feed one byte. Returns True if this byte ends a chunk boundary."""
        self._bytes_seen += 1
        self._buffer.append(b)

        if self._bytes_seen <= self._window_size:
            if self._bytes_seen == self._window_size:
                self._rh.init(bytes(self._buffer))
            return False

        if self._bytes_seen < self._min_size:
            self._rh.roll(self._buffer[self._bytes_seen - self._window_size - 1], b)
            return False

        self._rh.roll(self._buffer[self._bytes_seen - self._window_size - 1], b)

        if self._bytes_seen >= self._max_size:
            return True

        return (self._rh.fingerprint & self._mask) == 0
