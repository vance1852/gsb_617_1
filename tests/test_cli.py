"""Full CLI end-to-end test."""

import sys
import os
import shutil
import tempfile
import filecmp

sys.path.insert(0, r"E:\gsb\617\gsb_1\Earth")

from cas.sha256 import sha256


def create_test_files(root_dir: str) -> None:
    os.makedirs(os.path.join(root_dir, "subdir1"), exist_ok=True)
    os.makedirs(os.path.join(root_dir, "subdir2"), exist_ok=True)

    with open(os.path.join(root_dir, "hello.txt"), "w") as f:
        f.write("Hello, world!\n" * 100)

    with open(os.path.join(root_dir, "subdir1", "data.bin"), "wb") as f:
        f.write(b"\xAA" * 5000 + b"\xBB" * 5000)

    with open(os.path.join(root_dir, "subdir2", "log.txt"), "w") as f:
        f.write("Log line\n" * 200)


def dir_sha(root_dir: str) -> dict:
    result = {}
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root_dir).replace("\\", "/")
            with open(full, "rb") as f:
                result[rel] = sha256(f.read()).hexdigest()
    return result


def main():
    tmpdir = tempfile.mkdtemp(prefix="cas_cli_test_")
    print(f"Test dir: {tmpdir}")

    try:
        source = os.path.join(tmpdir, "source")
        store = os.path.join(tmpdir, "store")
        manifest = os.path.join(tmpdir, "test.manifest")
        restored = os.path.join(tmpdir, "restored")

        os.makedirs(source)
        create_test_files(source)

        print("\n--- pack ---")
        from cas.cli import main as cli_main
        rc = cli_main([
            "pack", source,
            "--store", store,
            "--manifest", manifest,
            "--avg-size", "2048",
            "--min-size", "512",
            "--max-size", "16384",
        ])
        assert rc == 0, f"pack failed with rc={rc}"
        print("pack: OK")

        print("\n--- stats ---")
        rc = cli_main(["stats", manifest, "--store", store, "--top", "5"])
        assert rc == 0, f"stats failed with rc={rc}"
        print("stats: OK")

        print("\n--- verify ---")
        rc = cli_main(["verify", "--store", store, "--manifest", manifest])
        assert rc == 0, f"verify failed with rc={rc}"
        print("verify: OK")

        print("\n--- restore ---")
        rc = cli_main(["restore", manifest, "--store", store, "--out", restored])
        assert rc == 0, f"restore failed with rc={rc}"
        print("restore: OK")

        print("\n--- compare ---")
        src_hashes = dir_sha(source)
        dst_hashes = dir_sha(restored)
        assert src_hashes == dst_hashes, "File hashes don't match!"
        print("All files match bit-for-bit: OK")

        print("\n=== ALL CLI TESTS PASSED ===")
        return 0

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
