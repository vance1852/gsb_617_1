"""Pure Python implementation of SHA-256 hash algorithm.

This module provides a hashlib-compatible SHA-256 implementation
without relying on the standard library hashlib module.
"""

from __future__ import annotations

from typing import List

from .abc import Hasher


def _right_rotate(n: int, bits: int) -> int:
    """Right rotate a 32-bit integer by the specified number of bits."""
    return ((n >> bits) | (n << (32 - bits))) & 0xFFFFFFFF


class SHA256(Hasher):
    """SHA-256 hash implementation.

    Follows the FIPS 180-4 specification for SHA-256.
    """

    _K: List[int] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
        0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
        0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
        0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
        0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
        0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
        0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ]

    def __init__(self, data: bytes = b"") -> None:
        self._h: List[int] = [
            0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
            0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
        ]
        self._buffer = bytearray()
        self._bit_length = 0

        if data:
            self.update(data)

    def update(self, data: bytes) -> None:
        """Update the hash with new data."""
        self._buffer.extend(data)
        self._bit_length += len(data) * 8

        while len(self._buffer) >= 64:
            block = bytes(self._buffer[:64])
            self._buffer = self._buffer[64:]
            self._process_block(block)

    def _process_block(self, block: bytes) -> None:
        """Process a single 512-bit (64-byte) block."""
        w = [0] * 64
        for i in range(16):
            w[i] = int.from_bytes(block[i * 4:(i + 1) * 4], "big")

        for i in range(16, 64):
            s0 = _right_rotate(w[i - 15], 7) ^ _right_rotate(w[i - 15], 18) ^ (w[i - 15] >> 3)
            s1 = _right_rotate(w[i - 2], 17) ^ _right_rotate(w[i - 2], 19) ^ (w[i - 2] >> 10)
            w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & 0xFFFFFFFF

        a, b, c, d, e, f, g, h = self._h

        for i in range(64):
            S1 = _right_rotate(e, 6) ^ _right_rotate(e, 11) ^ _right_rotate(e, 25)
            ch = (e & f) ^ ((~e) & g) & 0xFFFFFFFF
            temp1 = (h + S1 + ch + self._K[i] + w[i]) & 0xFFFFFFFF
            S0 = _right_rotate(a, 2) ^ _right_rotate(a, 13) ^ _right_rotate(a, 22)
            maj = (a & b) ^ (a & c) ^ (b & c)
            temp2 = (S0 + maj) & 0xFFFFFFFF

            h = g
            g = f
            f = e
            e = (d + temp1) & 0xFFFFFFFF
            d = c
            c = b
            b = a
            a = (temp1 + temp2) & 0xFFFFFFFF

        self._h[0] = (self._h[0] + a) & 0xFFFFFFFF
        self._h[1] = (self._h[1] + b) & 0xFFFFFFFF
        self._h[2] = (self._h[2] + c) & 0xFFFFFFFF
        self._h[3] = (self._h[3] + d) & 0xFFFFFFFF
        self._h[4] = (self._h[4] + e) & 0xFFFFFFFF
        self._h[5] = (self._h[5] + f) & 0xFFFFFFFF
        self._h[6] = (self._h[6] + g) & 0xFFFFFFFF
        self._h[7] = (self._h[7] + h) & 0xFFFFFFFF

    def _finalize(self) -> bytes:
        """Pad the message and process the final blocks."""
        padded = bytearray(self._buffer)
        padded.append(0x80)

        while (len(padded) % 64) != 56:
            padded.append(0x00)

        padded.extend(self._bit_length.to_bytes(8, "big"))

        temp_hasher = self.copy()
        for i in range(0, len(padded), 64):
            block = bytes(padded[i:i + 64])
            temp_hasher._process_block(block)

        return b"".join(h.to_bytes(4, "big") for h in temp_hasher._h)

    def digest(self) -> bytes:
        """Return the final hash digest as bytes."""
        return self._finalize()

    def hexdigest(self) -> str:
        """Return the final hash digest as a hex string."""
        return self._finalize().hex()

    def copy(self) -> "SHA256":
        """Return a copy of the hasher in its current state."""
        new_hasher = SHA256()
        new_hasher._h = list(self._h)
        new_hasher._buffer = bytearray(self._buffer)
        new_hasher._bit_length = self._bit_length
        return new_hasher


def sha256(data: bytes = b"") -> SHA256:
    """Create a new SHA-256 hash object.

    Args:
        data: Optional initial data to hash.

    Returns:
        A SHA256 hasher object.
    """
    return SHA256(data)
