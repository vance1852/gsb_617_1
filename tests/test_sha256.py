"""Quick test to verify SHA-256 implementation against hashlib."""

import sys
sys.path.insert(0, r"E:\gsb\617\gsb_1\Earth")

import hashlib
from cas.sha256 import sha256


def test_sha256():
    test_cases = [
        b"",
        b"abc",
        b"hello world",
        b"The quick brown fox jumps over the lazy dog",
        b"a" * 1000,
        b"\x00" * 64,
        b"\x00" * 65,
    ]

    all_passed = True
    for test in test_cases:
        expected = hashlib.sha256(test).hexdigest()
        actual = sha256(test).hexdigest()
        status = "PASS" if expected == actual else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"{status}: {repr(test[:50])}... ({len(test)} bytes)")
        if status == "FAIL":
            print(f"  Expected: {expected}")
            print(f"  Actual:   {actual}")

    # Test incremental hashing
    h = sha256()
    h.update(b"hello ")
    h.update(b"world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    actual = h.hexdigest()
    status = "PASS" if expected == actual else "FAIL"
    if status == "FAIL":
        all_passed = False
    print(f"{status}: incremental hashing")

    # Test copy
    h1 = sha256(b"hello")
    h2 = h1.copy()
    h1.update(b" world")
    h2.update(b" there")
    expected1 = hashlib.sha256(b"hello world").hexdigest()
    expected2 = hashlib.sha256(b"hello there").hexdigest()
    status1 = "PASS" if h1.hexdigest() == expected1 else "FAIL"
    status2 = "PASS" if h2.hexdigest() == expected2 else "FAIL"
    print(f"{status1}: copy + update (world)")
    print(f"{status2}: copy + update (there)")
    if status1 == "FAIL" or status2 == "FAIL":
        all_passed = False

    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return all_passed


if __name__ == "__main__":
    success = test_sha256()
    sys.exit(0 if success else 1)
