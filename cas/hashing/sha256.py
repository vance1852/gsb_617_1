"""Self-contained SHA-256 implementation (no hashlib)."""

import struct
from typing import List

from .abc import Hasher


def _rotr(n: int, x: int) -> int:
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


def _ch(x: int, y: int, z: int) -> int:
    return (x & y) ^ (~x & z)


def _maj(x: int, y: int, z: int) -> int:
    return (x & y) ^ (x & z) ^ (y & z)


def _sigma0(x: int) -> int:
    return _rotr(2, x) ^ _rotr(13, x) ^ _rotr(22, x)


def _sigma1(x: int) -> int:
    return _rotr(6, x) ^ _rotr(11, x) ^ _rotr(25, x)


def _gamma0(x: int) -> int:
    return _rotr(7, x) ^ _rotr(18, x) ^ (x >> 3)


def _gamma1(x: int) -> int:
    return _rotr(17, x) ^ _rotr(19, x) ^ (x >> 10)


K = [
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

INITIAL_HASH = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]


class SHA256Hasher(Hasher):
    """SHA-256 hasher implemented from scratch."""

    def __init__(self) -> None:
        self._h = INITIAL_HASH[:]
        self._buffer = b""
        self._total_len = 0
        self._digest_size = 32
        self._block_size = 64

    def update(self, data: bytes) -> None:
        self._buffer += data
        self._total_len += len(data)
        while len(self._buffer) >= self._block_size:
            block = self._buffer[: self._block_size]
            self._buffer = self._buffer[self._block_size :]
            self._process_block(block)

    def _process_block(self, block: bytes) -> None:
        w = list(struct.unpack(">16I", block))
        for i in range(16, 64):
            s0 = _gamma0(w[i - 15])
            s1 = _gamma1(w[i - 2])
            w.append((w[i - 16] + s0 + w[i - 7] + s1) & 0xFFFFFFFF)

        a, b, c, d, e, f, g, h = self._h

        for i in range(64):
            S1 = _sigma1(e)
            ch = _ch(e, f, g)
            temp1 = (h + S1 + ch + K[i] + w[i]) & 0xFFFFFFFF
            S0 = _sigma0(a)
            maj = _maj(a, b, c)
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

    def _pad(self) -> bytes:
        message_len = self._total_len * 8
        padding = b"\x80"
        while (self._total_len + len(padding) + 8) % 64 != 0:
            padding += b"\x00"
        padding += struct.pack(">Q", message_len)
        return padding

    def digest(self) -> bytes:
        clone = self.copy()
        clone.update(clone._pad())
        return struct.pack(">8I", *clone._h)

    def hexdigest(self) -> str:
        return self.digest().hex()

    def copy(self) -> "SHA256Hasher":
        new = SHA256Hasher.__new__(SHA256Hasher)
        new._h = self._h[:]
        new._buffer = self._buffer[:]
        new._total_len = self._total_len
        new._digest_size = self._digest_size
        new._block_size = self._block_size
        return new

    @property
    def digest_size(self) -> int:
        return self._digest_size

    @property
    def name(self) -> str:
        return "sha256"


def sha256(data: bytes = b"") -> SHA256Hasher:
    """Convenience function to create a SHA256Hasher and optionally feed data."""
    h = SHA256Hasher()
    if data:
        h.update(data)
    return h
