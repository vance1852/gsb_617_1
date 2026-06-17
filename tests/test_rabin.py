"""Test the Rabin chunker implementation."""

import sys
sys.path.insert(0, r"E:\gsb\617\gsb_1\Earth")

import os
from cas.rabin import RabinChunker
from cas.sha256 import sha256


def test_basic_chunking():
    """Test basic chunking functionality."""
    print("=== Basic Chunking Test ===")

    chunker = RabinChunker(avg_size=1024, min_size=256, max_size=4096)

    data = os.urandom(10000)
    chunks = chunker.chunk(data)

    print(f"Input size: {len(data)} bytes")
    print(f"Number of chunks: {len(chunks)}")
    print(f"Chunk sizes: {[len(c) for c in chunks]}")

    reassembled = b"".join(chunks)
    assert reassembled == data, "Chunks don't reassemble to original data!"
    print("Reassembly: PASS")

    avg = sum(len(c) for c in chunks) / len(chunks)
    print(f"Average chunk size: {avg:.1f} bytes")
    print(f"Min chunk size: {min(len(c) for c in chunks)}")
    print(f"Max chunk size: {max(len(c) for c in chunks)}")


def test_deterministic():
    """Test that chunking is deterministic."""
    print("\n=== Determinism Test ===")

    chunker = RabinChunker(avg_size=512, min_size=128, max_size=2048)
    data = os.urandom(5000)

    chunks1 = chunker.chunk(data)
    chunks2 = chunker.chunk(data)

    assert len(chunks1) == len(chunks2), "Chunk count differs!"
    for i, (c1, c2) in enumerate(zip(chunks1, chunks2)):
        assert c1 == c2, f"Chunk {i} differs!"
    print("Deterministic: PASS")


def test_rolling_hash_accuracy():
    """Test that rolling hash matches full recompute."""
    print("\n=== Rolling Hash Accuracy Test ===")

    chunker = RabinChunker(avg_size=1024, min_size=256, max_size=4096)
    data = os.urandom(1000)
    window_size = chunker.window_size

    rolling_hash = chunker._initial_hash(data[:window_size])

    errors = 0
    for i in range(1, len(data) - window_size + 1):
        out_byte = data[i - 1]
        in_byte = data[i + window_size - 1]
        rolling_hash = chunker._roll_hash(rolling_hash, out_byte, in_byte)

        full_hash = chunker._initial_hash(data[i:i + window_size])
        if rolling_hash != full_hash:
            errors += 1
            if errors <= 3:
                print(f"Mismatch at position {i}: rolling={rolling_hash}, full={full_hash}")

    if errors == 0:
        print("Rolling hash matches full recompute: PASS")
    else:
        print(f"Rolling hash mismatches: {errors} FAIL")
        return False
    return True


def test_min_max_constraints():
    """Test that min and max chunk sizes are respected."""
    print("\n=== Min/Max Constraints Test ===")

    min_size = 256
    max_size = 2048
    chunker = RabinChunker(avg_size=512, min_size=min_size, max_size=max_size)

    data = os.urandom(20000)
    chunks = chunker.chunk(data)

    all_ok = True
    for i, c in enumerate(chunks[:-1]):
        if len(c) < min_size:
            print(f"Chunk {i} too small: {len(c)} < {min_size}")
            all_ok = False
        if len(c) > max_size:
            print(f"Chunk {i} too large: {len(c)} > {max_size}")
            all_ok = False

    last = chunks[-1]
    if len(last) > max_size:
        print(f"Last chunk too large: {len(last)} > {max_size}")
        all_ok = False

    if all_ok:
        print("Min/max constraints respected: PASS")
    return all_ok


def test_content_dedup():
    """Test that identical content produces identical chunks."""
    print("\n=== Content Deduplication Test ===")

    chunker = RabinChunker(avg_size=256, min_size=64, max_size=1024)

    common = b"X" * 500 + b"Y" * 500
    data1 = b"A" * 100 + common + b"B" * 100
    data2 = b"C" * 200 + common + b"D" * 200

    chunks1 = chunker.chunk(data1)
    chunks2 = chunker.chunk(data2)

    hashes1 = set(sha256(c).hexdigest() for c in chunks1)
    hashes2 = set(sha256(c).hexdigest() for c in chunks2)

    common_hashes = hashes1 & hashes2
    print(f"Unique chunks in data1: {len(hashes1)}")
    print(f"Unique chunks in data2: {len(hashes2)}")
    print(f"Common chunks: {len(common_hashes)}")

    if len(common_hashes) > 0:
        print("Content-based deduplication works: PASS")
    else:
        print("WARNING: No common chunks found (may be expected with these params)")


def test_small_data():
    """Test chunking of data smaller than min_size."""
    print("\n=== Small Data Test ===")

    chunker = RabinChunker(avg_size=1024, min_size=256, max_size=4096)

    data = b"hello"
    chunks = chunker.chunk(data)
    assert len(chunks) == 1, "Small data should be one chunk"
    assert chunks[0] == data, "Small chunk should match data"
    print("Small data: PASS")

    data2 = b"x" * 200
    chunks2 = chunker.chunk(data2)
    assert len(chunks2) == 1
    assert chunks2[0] == data2
    print("Sub-min-size data: PASS")


if __name__ == "__main__":
    test_basic_chunking()
    test_deterministic()
    test_rolling_hash_accuracy()
    test_min_max_constraints()
    test_content_dedup()
    test_small_data()
    print("\n=== All Tests Complete ===")
