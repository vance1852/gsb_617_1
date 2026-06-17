"""Self-contained SHA-256 implementation (no hashlib usage).

Implements the SHA-256 cryptographic hash function as defined in FIPS 180-4.
"""

from __future__ import annotations

from typing import Final

K: Final[tuple[int, ...]] = (
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
)

_INITIAL_HASH: Final[tuple[int, ...]] = (
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
)

_MASK32: Final[int] = 0xFFFFFFFF


def _rotr(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & _MASK32


def _ch(x: int, y: int, z: int) -> int:
    return (x & y) ^ (~x & z)


def _maj(x: int, y: int, z: int) -> int:
    return (x & y) ^ (x & z) ^ (y & z)


def _sigma0(x: int) -> int:
    return _rotr(x, 2) ^ _rotr(x, 13) ^ _rotr(x, 22)


def _sigma1(x: int) -> int:
    return _rotr(x, 6) ^ _rotr(x, 11) ^ _rotr(x, 25)


def _gamma0(x: int) -> int:
    return _rotr(x, 7) ^ _rotr(x, 18) ^ (x >> 3)


def _gamma1(x: int) -> int:
    return _rotr(x, 17) ^ _rotr(x, 19) ^ (x >> 10)


def _pad_message(message: bytes, total_len: int) -> bytes:
    original_bits = total_len * 8

    padded = bytearray(message)
    padded.append(0x80)

    while (len(padded) * 8) % 512 != 448:
        padded.append(0x00)

    padded.extend(original_bits.to_bytes(8, byteorder="big"))
    return bytes(padded)


def _process_block(block: bytes, state: list[int]) -> None:
    w = [0] * 64
    for i in range(16):
        w[i] = int.from_bytes(block[i * 4:(i + 1) * 4], byteorder="big")

    for i in range(16, 64):
        w[i] = (_gamma1(w[i - 2]) + w[i - 7] + _gamma0(w[i - 15]) + w[i - 16]) & _MASK32

    a, b, c, d, e, f, g, h = state

    for i in range(64):
        t1 = (h + _sigma1(e) + _ch(e, f, g) + K[i] + w[i]) & _MASK32
        t2 = (_sigma0(a) + _maj(a, b, c)) & _MASK32
        h = g
        g = f
        f = e
        e = (d + t1) & _MASK32
        d = c
        c = b
        b = a
        a = (t1 + t2) & _MASK32

    state[0] = (state[0] + a) & _MASK32
    state[1] = (state[1] + b) & _MASK32
    state[2] = (state[2] + c) & _MASK32
    state[3] = (state[3] + d) & _MASK32
    state[4] = (state[4] + e) & _MASK32
    state[5] = (state[5] + f) & _MASK32
    state[6] = (state[6] + g) & _MASK32
    state[7] = (state[7] + h) & _MASK32


class SHA256:
    """Self-contained SHA-256 hash implementation.

    Mirrors the hashlib.sha256 interface: update(), digest(), hexdigest().
    """

    def __init__(self, data: bytes | None = None) -> None:
        self._state: list[int] = list(_INITIAL_HASH)
        self._buffer = bytearray()
        self._total_len = 0

        if data is not None:
            self.update(data)

    def update(self, data: bytes) -> None:
        self._buffer.extend(data)
        self._total_len += len(data)

        while len(self._buffer) >= 64:
            block = bytes(self._buffer[:64])
            del self._buffer[:64]
            _process_block(block, self._state)

    def digest(self) -> bytes:
        state = list(self._state)
        buffer = bytes(self._buffer)
        padded = _pad_message(buffer, self._total_len)
        offset = 0

        while offset < len(padded):
            block = padded[offset:offset + 64]
            _process_block(block, state)
            offset += 64

        return b"".join(s.to_bytes(4, byteorder="big") for s in state)

    def hexdigest(self) -> str:
        return self.digest().hex()

    def copy(self) -> "SHA256":
        new = SHA256()
        new._state = list(self._state)
        new._buffer = bytearray(self._buffer)
        new._total_len = self._total_len
        return new


def sha256(data: bytes | None = None) -> SHA256:
    """Convenience function matching hashlib.sha256 signature."""
    return SHA256(data)
