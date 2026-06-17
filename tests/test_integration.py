"""End-to-end integration test for the cas tool.

Creates a test directory with various files, packs it, verifies the
store, restores to a new directory, and compares the restored files
bit-for-bit against the originals.
"""

import sys
sys.path.insert(0, r"E:\gsb\617\gsb_1\Earth")

import os
import shutil
import tempfile
import filecmp

from cas.pack import pack_directory
from cas.restore import restore_manifest, RestoreError
from cas.verify import verify_store
from cas.stats_ import compute_stats, print_stats
from cas.sha256 import sha256


def create_test_files(root_dir: str) -> None:
    """Create a test directory tree with various files."""
    os.makedirs(os.path.join(root_dir, "subdir1"), exist_ok=True)
    os.makedirs(os.path.join(root_dir, "subdir2", "nested"), exist_ok=True)

    with open(os.path.join(root_dir, "hello.txt"), "w") as f:
        f.write("Hello, world!\n")

    with open(os.path.join(root_dir, "empty.txt"), "w") as f:
        pass

    with open(os.path.join(root_dir, "subdir1", "data.bin"), "wb") as f:
        f.write(b"\x00" * 1000 + b"\xff" * 1000 + b"\x00" * 1000)

    with open(os.path.join(root_dir, "subdir1", "repeated.txt"), "w") as f:
        f.write("repeated content " * 100)

    with open(os.path.join(root_dir, "subdir2", "nested", "deep.txt"), "w") as f:
        f.write("Deep file content\n" * 50)

    with open(os.path.join(root_dir, "subdir2", "big.bin"), "wb") as f:
        import os as _os
        f.write(_os.urandom(20000))

    with open(os.path.join(root_dir, "dedup_a.txt"), "w") as f:
        f.write("common prefix " + "A" * 1000 + " common suffix")

    with open(os.path.join(root_dir, "dedup_b.txt"), "w") as f:
        f.write("common prefix " + "B" * 1000 + " common suffix")


def dir_compare(dir1: str, dir2: str) -> bool:
    """Recursively compare two directories, returning True if identical."""
    def file_sha(path: str) -> str:
        with open(path, "rb") as f:
            return sha256(f.read()).hexdigest()

    files1 = {}
    for dirpath, _, filenames in os.walk(dir1):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, dir1)
            rel = rel.replace("\\", "/")
            files1[rel] = file_sha(full)

    files2 = {}
    for dirpath, _, filenames in os.walk(dir2):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, dir2)
            rel = rel.replace("\\", "/")
            files2[rel] = file_sha(full)

    if set(files1.keys()) != set(files2.keys()):
        print("File list mismatch!")
        print("Only in original:", set(files1.keys()) - set(files2.keys()))
        print("Only in restored:", set(files2.keys()) - set(files1.keys()))
        return False

    all_ok = True
    for path in sorted(files1.keys()):
        if files1[path] != files2[path]:
            print(f"Hash mismatch: {path}")
            print(f"  Original: {files1[path]}")
            print(f"  Restored: {files2[path]}")
            all_ok = False

    return all_ok


def main():
    tmpdir = tempfile.mkdtemp(prefix="cas_test_")
    print(f"Test directory: {tmpdir}")

    try:
        source_dir = os.path.join(tmpdir, "source")
        store_dir = os.path.join(tmpdir, "store")
        manifest_path = os.path.join(tmpdir, "test.manifest")
        restore_dir = os.path.join(tmpdir, "restored")

        os.makedirs(source_dir)
        create_test_files(source_dir)
        print("Test files created.")

        print("\n=== Pack ===")
        pack_directory(
            source_dir=source_dir,
            store_path=store_dir,
            manifest_path=manifest_path,
            avg_size=1024,
            min_size=256,
            max_size=4096,
            num_workers=2,
        )
        print("Pack complete.")

        print("\n=== Verify (store only) ===")
        result = verify_store(store_dir)
        print(f"Total chunks: {result.total_chunks}")
        print(f"Corrupted:    {len(result.corrupted_chunks)}")
        assert result.ok, "Store verification failed!"
        print("Store verification: PASS")

        print("\n=== Verify (with manifest) ===")
        result2 = verify_store(store_dir, manifest_path)
        print(f"Missing: {len(result2.missing_chunks)}")
        assert result2.ok, "Manifest reference check failed!"
        print("Manifest reference check: PASS")

        print("\n=== Stats ===")
        stats = compute_stats(manifest_path, store_dir)
        print_stats(stats)

        print("\n=== Restore ===")
        restore_manifest(
            manifest_path=manifest_path,
            store_path=store_dir,
            out_dir=restore_dir,
        )
        print("Restore complete.")

        print("\n=== Bit-for-bit comparison ===")
        if dir_compare(source_dir, restore_dir):
            print("All files match: PASS")
        else:
            print("File mismatch: FAIL")
            return 1

        print("\n=== All tests passed! ===")
        return 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
