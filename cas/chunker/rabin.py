"""Rabin fingerprint rolling hash - true O(1) incremental update.

Implementation based on polynomial hashing over GF(2) with a 64-bit
irreducible polynomial.  Sliding the window one byte at a time is O(1):
we remove the contribution of the byte sliding out, shift, and add the
byte sliding in - all using polynomial arithmetic modulo an irreducible
polynomial of degree 64.
"""

from typing import List

from .abc import RollingHash

DEFAULT_WINDOW_SIZE = 48

_IRREDUCIBLE_POLY_64 = 0x000000000000001B  # x^64 + x^4 + x^3 + x + 1
_MASK64 = 0xFFFFFFFFFFFFFFFF


def _poly_mod_mult(a: int, b: int, mod: int) -> int:
    """Multiply two polynomials modulo 'mod', all over GF(2).

    Both a and b represent polynomials of degree < 64 (bits 0..63).
    mod represents the lower 64 bits of a degree-64 irreducible
    polynomial (the x^64 coefficient is implicitly 1).
    """
    result = 0
    for _ in range(64):
        if b & 1:
            result ^= a
        carry = a & (1 << 63)
        a = (a << 1) & _MASK64
        if carry:
            a ^= mod
        b >>= 1
    return result


def _poly_mod_pow(base: int, exp: int, mod: int) -> int:
    """Compute base^exp mod p (polynomial exponentiation over GF(2))."""
    result = 1
    current = base
    while exp > 0:
        if exp & 1:
            result = _poly_mod_mult(result, current, mod)
        current = _poly_mod_mult(current, current, mod)
        exp >>= 1
    return result


def _precompute_out_table(window_size: int, mod: int) -> List[int]:
    """Precompute out_table[byte] = byte * x^(8*(window_size-1)) mod p.

    The oldest byte in the window sits at position x^(8*(window_size-1))
    (the highest-order position).  When it slides out, we XOR its
    contribution away before shifting the window left by one byte.
    """
    x_pow = _poly_mod_pow(2, (window_size - 1) * 8, mod)
    table = [0] * 256
    for byte_val in range(256):
        table[byte_val] = _poly_mod_mult(byte_val, x_pow, mod)
    return table


def _shift_left_byte(fp: int, mod: int) -> int:
    """Shift fingerprint left by 8 bits (one byte) modulo mod."""
    for _ in range(8):
        carry = fp & (1 << 63)
        fp = (fp << 1) & _MASK64
        if carry:
            fp ^= mod
    return fp


class RabinFingerprint(RollingHash):
    """64-bit Rabin fingerprint with true O(1) incremental sliding.

    The fingerprint of a byte window [b_0, b_1, ..., b_{w-1}] is:
        fingerprint = b_0 * x^{8(w-1)} + b_1 * x^{8(w-2)} + ... + b_{w-1}
    where arithmetic is over GF(2)[x] modulo an irreducible polynomial.

    Sliding one byte (removing b_0, adding b_w) can be done in O(1):
        new_fp = ((fp XOR out_table[b_0]) << 8) XOR b_w    (mod p)
    """

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE,
                 mod: int = _IRREDUCIBLE_POLY_64) -> None:
        self._window_size = window_size
        self._mod = mod & _MASK64
        self._out_table = _precompute_out_table(window_size, mod)
        self._fingerprint = 0
        self._buffer: List[int] = []
        self._buffer_pos = 0

    def reset(self) -> None:
        self._fingerprint = 0
        self._buffer = []
        self._buffer_pos = 0

    def update(self, data: bytes) -> None:
        """Feed bytes into the rolling hash.

        If the window is not yet full, build it up.  Once full, each
        additional byte slides the window by one position.
        """
        for b in data:
            if len(self._buffer) < self._window_size:
                self._buffer.append(b)
                self._fingerprint = _shift_left_byte(self._fingerprint, self._mod) ^ b
            else:
                out_byte = self._buffer[self._buffer_pos]
                self.roll(out_byte, b)
                self._buffer[self._buffer_pos] = b
                self._buffer_pos = (self._buffer_pos + 1) % self._window_size

    def roll(self, out_byte: int, in_byte: int) -> None:
        """Slide the window by one byte in O(1).

        Args:
            out_byte: the byte leaving the window (oldest byte)
            in_byte: the byte entering the window (newest byte)
        """
        fp = self._fingerprint ^ self._out_table[out_byte]
        fp = _shift_left_byte(fp, self._mod)
        fp ^= in_byte
        self._fingerprint = fp

    def digest(self) -> int:
        return self._fingerprint

    @property
    def window_size(self) -> int:
        return self._window_size
