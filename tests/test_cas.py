"""Tests for the cas content-addressable storage engine.

Tests:
- SHA-256 correctness (compared to hashlib)
- Rabin rolling hash O(1) incremental correctness
- Chunker boundary constraints (min/avg/max size)
- Store put/get/has/deduplication
- Manifest save/load round-trip
- pack -> restore bit-for-bit identity
- Deterministic output across multiple pack runs
- Deduplication statistics
- Verify command integrity checking
"""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cas.hashing.sha256 import sha256 as cas_sha256
from cas.hashing.rolling import RabinRollingHash, ChunkBoundaryDetector
from cas.chunker.rabin_chunker import RabinChunker
from cas.store.content_store import FileContentStore
from cas.manifest.manifest import TextManifest
from cas.manifest.base import FileEntry
from cas.packer import pack_directory
from cas.restore import restore_manifest, RestoreError
from cas.verify import verify_store
from cas.stats import compute_stats


class TestSHA256(unittest.TestCase):
    """Test self-implemented SHA-256 against stdlib hashlib."""

    def test_empty(self):
        self.assertEqual(cas_sha256(b"").hexdigest(), hashlib.sha256(b"").hexdigest())

    def test_abc(self):
        data = b"abc"
        self.assertEqual(cas_sha256(data).hexdigest(), hashlib.sha256(data).hexdigest())

    def test_short_string(self):
        data = b"The quick brown fox jumps over the lazy dog"
        self.assertEqual(cas_sha256(data).hexdigest(), hashlib.sha256(data).hexdigest())

    def test_exactly_one_block(self):
        data = b"a" * 64
        self.assertEqual(cas_sha256(data).hexdigest(), hashlib.sha256(data).hexdigest())

    def test_two_blocks(self):
        data = b"b" * 128
        self.assertEqual(cas_sha256(data).hexdigest(), hashlib.sha256(data).hexdigest())

    def test_random_bytes(self):
        rng = random.Random(42)
        for _ in range(50):
            length = rng.randint(0, 10_000)
            data = rng.randbytes(length)
            self.assertEqual(
                cas_sha256(data).hexdigest(),
                hashlib.sha256(data).hexdigest(),
                f"Mismatch for length {length}",
            )

    def test_incremental_update(self):
        data = b"Hello, World! This is a test of incremental SHA-256 updates."
        h1 = cas_sha256()
        for i in range(0, len(data), 7):
            h1.update(data[i:i+7])
        h2 = cas_sha256(data)
        self.assertEqual(h1.hexdigest(), h2.hexdigest())
        self.assertEqual(h1.hexdigest(), hashlib.sha256(data).hexdigest())

    def test_copy(self):
        data = b"test copy functionality"
        h1 = cas_sha256(data[:10])
        h2 = h1.copy()
        h1.update(data[10:])
        h2.update(data[10:])
        self.assertEqual(h1.hexdigest(), h2.hexdigest())
        self.assertEqual(h1.hexdigest(), hashlib.sha256(data).hexdigest())


class TestRabinRollingHash(unittest.TestCase):
    """Test Rabin rolling hash O(1) incremental update correctness."""

    def _naive_fingerprint(self, data: bytes, base: int, mod: int) -> int:
        fp = 0
        for b in data:
            fp = ((fp * base) + b) % mod
        return fp

    def test_initialization(self):
        data = b"abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        rh = RabinRollingHash(window_size=48)
        rh.init(data)
        expected = self._naive_fingerprint(data[:48], rh._base, rh._mod)
        self.assertEqual(rh.fingerprint, expected)

    def test_rolling_matches_naive(self):
        rng = random.Random(123)
        data = rng.randbytes(500)
        window = 32
        rh = RabinRollingHash(window_size=window)
        rh.init(data[:window])

        for i in range(len(data) - window):
            expected = self._naive_fingerprint(data[i:i+window], rh._base, rh._mod)
            self.assertEqual(
                rh.fingerprint, expected,
                f"Mismatch at position {i}",
            )
            rh.roll(data[i], data[i + window])

        expected = self._naive_fingerprint(data[-window:], rh._base, rh._mod)
        self.assertEqual(rh.fingerprint, expected)

    def test_reset(self):
        data = b"hello world test data"
        rh = RabinRollingHash(window_size=8)
        rh.init(data[:8])
        fp1 = rh.fingerprint
        rh.reset()
        self.assertEqual(rh.fingerprint, 0)
        rh.init(data[:8])
        self.assertEqual(rh.fingerprint, fp1)


class TestChunkBoundaryDetector(unittest.TestCase):
    """Test chunk boundary detection with min/max constraints."""

    def test_max_size_enforced(self):
        data = b"\x00" * 100_000
        detector = ChunkBoundaryDetector(min_size=100, avg_size=1000, max_size=5000)
        chunk_sizes = []
        current = 0
        for b in data:
            current += 1
            if detector.feed_byte(b):
                chunk_sizes.append(current)
                current = 0
                detector.reset()
        if current > 0:
            chunk_sizes.append(current)
        for s in chunk_sizes[:-1]:
            self.assertLessEqual(s, 5000, f"Chunk size {s} exceeds max")

    def test_min_size_enforced(self):
        rng = random.Random(42)
        data = rng.randbytes(200_000)
        min_size = 512
        detector = ChunkBoundaryDetector(min_size=min_size, avg_size=4096, max_size=65536)
        chunk_sizes = []
        current = 0
        for b in data:
            current += 1
            if detector.feed_byte(b):
                chunk_sizes.append(current)
                current = 0
                detector.reset()
        if current > 0:
            chunk_sizes.append(current)
        for s in chunk_sizes[:-1]:
            self.assertGreaterEqual(s, min_size, f"Chunk size {s} below min")

    def test_mask_derivation(self):
        d = ChunkBoundaryDetector(min_size=64, avg_size=8192, max_size=65536)
        self.assertEqual(d.mask, 0x1FFF)
        d2 = ChunkBoundaryDetector(min_size=64, avg_size=4096, max_size=65536)
        self.assertEqual(d2.mask, 0xFFF)


class TestRabinChunker(unittest.TestCase):
    """Test the Rabin CDC chunker."""

    def test_chunk_data_assembly(self):
        rng = random.Random(99)
        data = rng.randbytes(50_000)
        chunker = RabinChunker(min_size=256, avg_size=1024, max_size=8192)
        chunks = chunker.chunk_data(data)
        assembled = b"".join(c.data for c in chunks)
        self.assertEqual(assembled, data)

    def test_chunk_digest_correctness(self):
        rng = random.Random(77)
        data = rng.randbytes(20_000)
        chunker = RabinChunker(min_size=128, avg_size=512, max_size=4096)
        chunks = chunker.chunk_data(data)
        for c in chunks:
            self.assertEqual(c.digest, hashlib.sha256(c.data).hexdigest())
            self.assertEqual(c.size, len(c.data))

    def test_deterministic(self):
        rng = random.Random(55)
        data = rng.randbytes(100_000)
        chunker = RabinChunker(min_size=512, avg_size=2048, max_size=16384)
        c1 = chunker.chunk_data(data)
        c2 = chunker.chunk_data(data)
        self.assertEqual([c.digest for c in c1], [c.digest for c in c2])
        self.assertEqual([c.size for c in c1], [c.size for c in c2])


class TestFileContentStore(unittest.TestCase):
    """Test the file-based content store."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = FileContentStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_put_and_get(self):
        data = b"hello world chunk data"
        digest = hashlib.sha256(data).hexdigest()
        self.assertTrue(self.store.put_chunk(digest, data))
        self.assertTrue(self.store.has_chunk(digest))
        self.assertEqual(self.store.get_chunk(digest), data)

    def test_put_deduplicates(self):
        data = b"duplicate data"
        digest = hashlib.sha256(data).hexdigest()
        self.assertTrue(self.store.put_chunk(digest, data))
        self.assertFalse(self.store.put_chunk(digest, data))

    def test_get_missing_raises(self):
        with self.assertRaises(KeyError):
            self.store.get_chunk("a" * 64)

    def test_iter_chunks(self):
        digests = set()
        for i in range(20):
            data = f"chunk-{i}".encode()
            d = hashlib.sha256(data).hexdigest()
            self.store.put_chunk(d, data)
            digests.add(d)
        stored = set(self.store.iter_chunks())
        self.assertEqual(stored, digests)

    def test_chunk_size(self):
        data = b"size test data"
        digest = hashlib.sha256(data).hexdigest()
        self.store.put_chunk(digest, data)
        self.assertEqual(self.store.chunk_size(digest), len(data))

    def test_sharded_layout(self):
        data = b"sharded layout test"
        digest = hashlib.sha256(data).hexdigest()
        self.store.put_chunk(digest, data)
        path = self.store._digest_to_path(digest)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.parent.parent, self.store.chunks_dir)


class TestManifest(unittest.TestCase):
    """Test manifest save/load round-trip."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_load_roundtrip(self):
        manifest = TextManifest()
        manifest.set_chunker_config({
            "algorithm": "rabin",
            "min_size": 2048,
            "avg_size": 8192,
            "max_size": 65536,
        })
        manifest.add_file(FileEntry(
            path="dir/file1.txt",
            size=12345,
            mode=0o644,
            chunks=["a" * 64, "b" * 64],
            content_hash="c" * 64,
        ))
        manifest.add_file(FileEntry(
            path="file2.bin",
            size=999,
            mode=0o755,
            chunks=["d" * 64],
            content_hash="e" * 64,
        ))

        path = self.tmpdir / "manifest.txt"
        manifest.save(path)

        loaded = TextManifest.load(path)

        cfg = loaded.get_chunker_config()
        self.assertEqual(cfg["algorithm"], "rabin")
        self.assertEqual(cfg["min_size"], 2048)

        files = list(loaded.iter_files())
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0].path, "dir/file1.txt")
        self.assertEqual(files[1].path, "file2.bin")
        self.assertEqual(files[0].size, 12345)
        self.assertEqual(files[0].mode, 0o644)
        self.assertEqual(files[0].chunks, ["a" * 64, "b" * 64])
        self.assertEqual(files[0].content_hash, "c" * 64)

    def test_sorted_order(self):
        manifest = TextManifest()
        manifest.add_file(FileEntry(path="z.txt", size=1, mode=0o644, chunks=[], content_hash="a" * 64))
        manifest.add_file(FileEntry(path="a.txt", size=2, mode=0o644, chunks=[], content_hash="b" * 64))
        manifest.add_file(FileEntry(path="m.bin", size=3, mode=0o644, chunks=[], content_hash="c" * 64))

        files = list(manifest.iter_files())
        self.assertEqual([f.path for f in files], ["a.txt", "m.bin", "z.txt"])


class TestPackRestore(unittest.TestCase):
    """Integration tests for pack + restore pipeline."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.src_dir = self.tmpdir / "source"
        self.store_dir = self.tmpdir / "store"
        self.restore_dir = self.tmpdir / "restored"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_test_data(self):
        rng = random.Random(12345)
        self.src_dir.mkdir()

        (self.src_dir / "subdir").mkdir()
        (self.src_dir / "subdir" / "nested").mkdir()

        (self.src_dir / "small.txt").write_bytes(b"Hello, World!\n")
        (self.src_dir / "medium.bin").write_bytes(rng.randbytes(50_000))
        (self.src_dir / "large.bin").write_bytes(rng.randbytes(200_000))
        (self.src_dir / "subdir" / "file1.txt").write_bytes(b"file one content")
        (self.src_dir / "subdir" / "nested" / "deep.log").write_bytes(
            rng.randbytes(10_000)
        )

        dup_data = rng.randbytes(30_000)
        (self.src_dir / "dup_a.bin").write_bytes(dup_data)
        (self.src_dir / "subdir" / "dup_b.bin").write_bytes(dup_data)

    def _compare_dirs(self, a: Path, b: Path):
        a_files = {}
        for f in a.rglob("*"):
            if f.is_file():
                rel = f.relative_to(a)
                a_files[str(rel).replace("\\", "/")] = f.read_bytes()

        b_files = {}
        for f in b.rglob("*"):
            if f.is_file():
                rel = f.relative_to(b)
                b_files[str(rel).replace("\\", "/")] = f.read_bytes()

        self.assertEqual(set(a_files.keys()), set(b_files.keys()))
        for path in a_files:
            self.assertEqual(a_files[path], b_files[path], f"Mismatch in {path}")

    def test_pack_restore_bit_for_bit(self):
        self._create_test_data()

        manifest = pack_directory(
            source_dir=self.src_dir,
            store_path=self.store_dir,
            min_size=512,
            avg_size=2048,
            max_size=16384,
            num_workers=1,
        )

        file_count = sum(1 for _ in manifest.iter_files())
        self.assertGreater(file_count, 0)

        manifest_path = self.store_dir / "manifest.txt"
        self.assertTrue(manifest_path.exists())

        restore_manifest(
            manifest_path=manifest_path,
            store_path=self.store_dir,
            out_dir=self.restore_dir,
        )

        self._compare_dirs(self.src_dir, self.restore_dir)

    def test_deterministic_pack(self):
        self._create_test_data()

        store1 = self.tmpdir / "store1"
        store2 = self.tmpdir / "store2"

        m1 = pack_directory(
            source_dir=self.src_dir,
            store_path=store1,
            min_size=512,
            avg_size=2048,
            max_size=16384,
            num_workers=1,
        )
        m2 = pack_directory(
            source_dir=self.src_dir,
            store_path=store2,
            min_size=512,
            avg_size=2048,
            max_size=16384,
            num_workers=1,
        )

        f1 = list(m1.iter_files())
        f2 = list(m2.iter_files())
        self.assertEqual([e.path for e in f1], [e.path for e in f2])
        for a, b in zip(f1, f2):
            self.assertEqual(a.chunks, b.chunks)
            self.assertEqual(a.content_hash, b.content_hash)
            self.assertEqual(a.size, b.size)

        chunks1 = set(FileContentStore(store1).iter_chunks())
        chunks2 = set(FileContentStore(store2).iter_chunks())
        self.assertEqual(chunks1, chunks2)

    def test_deduplication_works(self):
        self._create_test_data()

        pack_directory(
            source_dir=self.src_dir,
            store_path=self.store_dir,
            min_size=512,
            avg_size=2048,
            max_size=16384,
            num_workers=1,
        )

        report = compute_stats(
            manifest_path=self.store_dir / "manifest.txt",
            store_path=self.store_dir,
            top_n=5,
        )

        self.assertGreater(report.total_files, 0)
        self.assertGreater(report.raw_total_bytes, 0)
        self.assertGreater(report.unique_chunks, 0)
        self.assertGreater(report.total_chunk_refs, report.unique_chunks)
        self.assertGreater(report.saving_percent, 0)

    def test_restore_missing_chunk_raises(self):
        self._create_test_data()

        pack_directory(
            source_dir=self.src_dir,
            store_path=self.store_dir,
            min_size=512,
            avg_size=2048,
            max_size=16384,
            num_workers=1,
        )

        store = FileContentStore(self.store_dir)
        chunks = list(store.iter_chunks())
        if chunks:
            chunk_path = store._digest_to_path(chunks[0])
            os.unlink(chunk_path)

        with self.assertRaises(RestoreError):
            restore_manifest(
                manifest_path=self.store_dir / "manifest.txt",
                store_path=self.store_dir,
                out_dir=self.restore_dir,
            )


class TestVerify(unittest.TestCase):
    """Test verify command."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.src_dir = self.tmpdir / "source"
        self.store_dir = self.tmpdir / "store"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_verify_clean_store(self):
        rng = random.Random(42)
        self.src_dir.mkdir()
        self.src_dir.joinpath("f1.bin").write_bytes(rng.randbytes(10_000))
        self.src_dir.joinpath("f2.bin").write_bytes(rng.randbytes(5_000))

        pack_directory(
            source_dir=self.src_dir,
            store_path=self.store_dir,
            min_size=256,
            avg_size=1024,
            max_size=8192,
            num_workers=1,
        )

        result = verify_store(
            store_path=self.store_dir,
            manifest_path=self.store_dir / "manifest.txt",
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(result.corrupted_chunks), 0)
        self.assertEqual(len(result.missing_chunks), 0)

    def test_verify_corrupted_chunk(self):
        rng = random.Random(42)
        self.src_dir.mkdir()
        self.src_dir.joinpath("data.bin").write_bytes(rng.randbytes(20_000))

        pack_directory(
            source_dir=self.src_dir,
            store_path=self.store_dir,
            min_size=256,
            avg_size=1024,
            max_size=8192,
            num_workers=1,
        )

        store = FileContentStore(self.store_dir)
        chunks = list(store.iter_chunks())
        if chunks:
            chunk_path = store._digest_to_path(chunks[0])
            with open(chunk_path, "r+b") as f:
                f.seek(0)
                f.write(b"CORRUPTED")

        result = verify_store(store_path=self.store_dir)
        self.assertFalse(result.ok)
        self.assertGreaterEqual(len(result.corrupted_chunks), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
