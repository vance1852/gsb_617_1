"""Test edge cases: symlinks, determinism, error handling."""

import sys
sys.path.insert(0, r"E:\gsb\617\gsb_1\Earth")

import os
import shutil
import tempfile

from cas.pack import pack_directory, _collect_files
from cas.manifest import FileManifest
from cas.sha256 import sha256
from cas.store import FileContentStore


def test_symlink_skip():
    """Test that symlinks are skipped."""
    print("=== Symlink Skip Test ===")

    tmpdir = tempfile.mkdtemp(prefix="cas_symlink_test_")
    try:
        source = os.path.join(tmpdir, "source")
        os.makedirs(source)

        with open(os.path.join(source, "real.txt"), "w") as f:
            f.write("real file content")

        real_file = os.path.join(source, "target.txt")
        with open(real_file, "w") as f:
            f.write("target content")

        try:
            os.symlink(real_file, os.path.join(source, "link.txt"))
        except OSError as e:
            print(f"  Skipping symlink test (cannot create symlinks): {e}")
            print("  Symlink skip: SKIPPED")
            return True

        files = _collect_files(source)
        file_names = sorted(rel for _, rel in files)
        print(f"  Collected files: {file_names}")

        assert "link.txt" not in file_names, "Symlink should be skipped!"
        assert "real.txt" in file_names
        assert "target.txt" in file_names
        print("  Symlink skip: PASS")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_determinism():
    """Test that packing the same directory twice produces identical results."""
    print("\n=== Determinism Test ===")

    tmpdir = tempfile.mkdtemp(prefix="cas_determ_test_")
    try:
        source = os.path.join(tmpdir, "source")
        os.makedirs(os.path.join(source, "a"))
        os.makedirs(os.path.join(source, "b"))

        with open(os.path.join(source, "z.txt"), "w") as f:
            f.write("z file\n" * 100)
        with open(os.path.join(source, "a", "a.txt"), "w") as f:
            f.write("a file\n" * 100)
        with open(os.path.join(source, "b", "b.txt"), "w") as f:
            f.write("b file\n" * 100)

        store1 = os.path.join(tmpdir, "store1")
        manifest1 = os.path.join(tmpdir, "m1.manifest")
        pack_directory(source, store1, manifest1, avg_size=512, min_size=128, max_size=2048, num_workers=1)

        store2 = os.path.join(tmpdir, "store2")
        manifest2 = os.path.join(tmpdir, "m2.manifest")
        pack_directory(source, store2, manifest2, avg_size=512, min_size=128, max_size=2048, num_workers=2)

        with open(manifest1, "r") as f:
            content1 = f.read()
        with open(manifest2, "r") as f:
            content2 = f.read()

        assert content1 == content2, "Manifests should be identical!"
        print("  Manifest determinism: PASS")

        store1_chunks = sorted(FileContentStore(store1).list_all())
        store2_chunks = sorted(FileContentStore(store2).list_all())
        assert store1_chunks == store2_chunks, "Store chunk sets should be identical!"
        print("  Store chunk set determinism: PASS")

        manifest_hash1 = sha256(content1.encode()).hexdigest()
        manifest_hash2 = sha256(content2.encode()).hexdigest()
        print(f"  Manifest hash 1: {manifest_hash1}")
        print(f"  Manifest hash 2: {manifest_hash2}")
        print("  Full determinism: PASS")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restore_missing_chunk():
    """Test that restore properly fails on missing chunks."""
    print("\n=== Missing Chunk Test ===")

    tmpdir = tempfile.mkdtemp(prefix="cas_missing_test_")
    try:
        source = os.path.join(tmpdir, "source")
        os.makedirs(source)
        with open(os.path.join(source, "test.txt"), "w") as f:
            f.write("test content " * 100)

        store = os.path.join(tmpdir, "store")
        manifest_path = os.path.join(tmpdir, "test.manifest")
        pack_directory(source, store, manifest_path, avg_size=256, min_size=64, max_size=1024)

        store_obj = FileContentStore(store)
        all_chunks = store_obj.list_all()
        assert all_chunks, "Should have chunks"

        first_chunk = all_chunks[0]
        chunk_path = store_obj._digest_to_path(first_chunk)
        os.remove(chunk_path)
        print(f"  Removed chunk: {first_chunk[:16]}...")

        from cas.restore import restore_manifest, RestoreError
        out_dir = os.path.join(tmpdir, "restored")

        try:
            restore_manifest(manifest_path, store, out_dir)
            assert False, "Should have raised RestoreError"
        except RestoreError as e:
            print(f"  Restore correctly failed: {e}")
            print("  Missing chunk detection: PASS")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_verify_corrupted_chunk():
    """Test that verify detects corrupted chunks."""
    print("\n=== Corrupted Chunk Test ===")

    tmpdir = tempfile.mkdtemp(prefix="cas_corrupt_test_")
    try:
        source = os.path.join(tmpdir, "source")
        os.makedirs(source)
        with open(os.path.join(source, "test.bin"), "wb") as f:
            f.write(b"\xAA" * 2000)

        store = os.path.join(tmpdir, "store")
        manifest_path = os.path.join(tmpdir, "test.manifest")
        pack_directory(source, store, manifest_path)

        store_obj = FileContentStore(store)
        all_chunks = store_obj.list_all()
        first_chunk = all_chunks[0]
        chunk_path = store_obj._digest_to_path(first_chunk)

        with open(chunk_path, "r+b") as f:
            f.write(b"CORRUPTED!")

        print(f"  Corrupted chunk: {first_chunk[:16]}...")

        from cas.verify import verify_store
        result = verify_store(store)

        print(f"  Total chunks: {result.total_chunks}")
        print(f"  Corrupted: {len(result.corrupted_chunks)}")
        assert len(result.corrupted_chunks) >= 1, "Should detect corrupted chunk!"
        assert first_chunk in result.corrupted_chunks
        print("  Corrupted chunk detection: PASS")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_symlink_skip()
    test_determinism()
    test_restore_missing_chunk()
    test_verify_corrupted_chunk()
    print("\n=== All edge case tests complete ===")
