"""End-to-end test for the cas tool."""

import os
import sys
import shutil
import hashlib
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cas.cli import main


def _dir_hash(path: str) -> str:
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, path)
            h.update(rel.encode())
            with open(fpath, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def _create_test_files(root: str) -> None:
    os.makedirs(os.path.join(root, "subdir1"), exist_ok=True)
    os.makedirs(os.path.join(root, "subdir2", "nested"), exist_ok=True)

    with open(os.path.join(root, "hello.txt"), "w") as f:
        f.write("Hello, World!\n" * 100)

    with open(os.path.join(root, "subdir1", "data.bin"), "wb") as f:
        f.write(os.urandom(50000))

    with open(os.path.join(root, "subdir1", "dup.txt"), "w") as f:
        f.write("Hello, World!\n" * 100)

    with open(os.path.join(root, "subdir2", "nested", "deep.txt"), "w") as f:
        f.write("Nested file content\n" * 200)

    big_data = b"A" * 100000 + b"B" * 50000 + os.urandom(20000)
    with open(os.path.join(root, "subdir2", "big.bin"), "wb") as f:
        f.write(big_data)

    with open(os.path.join(root, "subdir2", "dup.txt"), "w") as f:
        f.write("Hello, World!\n" * 100)


def test_pack_restore(tmpdir: str):
    print("=== Test: pack + restore bit-for-bit ===")
    src_dir = os.path.join(tmpdir, "src")
    store_dir = os.path.join(tmpdir, "store")
    out_dir = os.path.join(tmpdir, "out")

    _create_test_files(src_dir)
    src_hash = _dir_hash(src_dir)

    rc = main([
        "pack", src_dir,
        "--store", store_dir,
        "--avg-size", "4096",
        "--min-size", "1024",
        "--max-size", "32768",
    ])
    assert rc == 0, f"pack failed with rc={rc}"
    print("  pack: OK")

    manifest_path = os.path.join(store_dir, "manifest")
    assert os.path.isfile(manifest_path), f"manifest not found at {manifest_path}"

    rc = main([
        "restore", manifest_path,
        "--store", store_dir,
        "--out", out_dir,
    ])
    assert rc == 0, f"restore failed with rc={rc}"
    print("  restore: OK")

    out_hash = _dir_hash(out_dir)
    assert src_hash == out_hash, (
        f"hash mismatch: src={src_hash}, out={out_hash}"
    )
    print("  bit-for-bit match: OK")

    return store_dir, manifest_path


def test_verify(store_dir: str, manifest_path: str):
    print("\n=== Test: verify ===")
    rc = main(["verify", "--store", store_dir])
    assert rc == 0, f"verify store failed with rc={rc}"
    print("  store verify: OK")

    rc = main(["verify", "--store", store_dir, "--manifest", manifest_path])
    assert rc == 0, f"verify manifest failed with rc={rc}"
    print("  manifest verify: OK")


def test_stats(store_dir: str, manifest_path: str):
    print("\n=== Test: stats ===")
    rc = main(["stats", manifest_path, "--store", store_dir, "--top", "5"])
    assert rc == 0, f"stats failed with rc={rc}"
    print("  stats: OK")


def test_determinism(tmpdir: str):
    print("\n=== Test: determinism ===")
    src_dir = os.path.join(tmpdir, "src")
    store1_dir = os.path.join(tmpdir, "store1")
    store2_dir = os.path.join(tmpdir, "store2")

    _create_test_files(src_dir)

    main([
        "pack", src_dir,
        "--store", store1_dir,
        "--avg-size", "4096",
        "--min-size", "1024",
        "--max-size", "32768",
    ])

    main([
        "pack", src_dir,
        "--store", store2_dir,
        "--avg-size", "4096",
        "--min-size", "1024",
        "--max-size", "32768",
    ])

    m1 = open(os.path.join(store1_dir, "manifest"), "r").read()
    m2 = open(os.path.join(store2_dir, "manifest"), "r").read()
    assert m1 == m2, "manifests differ"
    print("  manifest determinism: OK")

    chunks1 = set()
    chunks2 = set()
    for root, _, files in os.walk(os.path.join(store1_dir, "chunks")):
        for f in files:
            if not f.endswith(".tmp"):
                chunks1.add(f)
    for root, _, files in os.walk(os.path.join(store2_dir, "chunks")):
        for f in files:
            if not f.endswith(".tmp"):
                chunks2.add(f)
    assert chunks1 == chunks2, "chunk sets differ"
    print("  chunk set determinism: OK")


def main_test():
    print("Running cas end-to-end tests...\n")

    tmpdir = tempfile.mkdtemp(prefix="cas_test_")
    try:
        store_dir, manifest_path = test_pack_restore(tmpdir)
        test_verify(store_dir, manifest_path)
        test_stats(store_dir, manifest_path)
        test_determinism(tmpdir)

        print("\n=== All tests passed! ===")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main_test()
