"""End-to-end test for the cas CLI tool."""

import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cas.cli import main


def test_e2e():
    tmpdir = Path(tempfile.mkdtemp(prefix="cas_e2e_"))
    try:
        src = tmpdir / "src"
        src.mkdir()
        rng = random.Random(42)

        (src / "subdir" / "deep").mkdir(parents=True)
        (src / "hello.txt").write_text("Hello, World!\n")
        (src / "subdir" / "binary.bin").write_bytes(rng.randbytes(50_000))
        (src / "subdir" / "deep" / "log.txt").write_bytes(rng.randbytes(15_000))

        dup_data = rng.randbytes(20_000)
        (src / "dup1.bin").write_bytes(dup_data)
        (src / "subdir" / "dup2.bin").write_bytes(dup_data)

        store = tmpdir / "store"
        manifest = store / "manifest.txt"

        print("=" * 60)
        print("1. Testing PACK")
        print("=" * 60)
        rc = main(["pack", str(src), "--store", str(store)])
        assert rc == 0, f"pack failed with rc={rc}"
        print(f"Pack OK - manifest at {manifest}")
        assert manifest.exists(), "manifest not created"

        print()
        print("=" * 60)
        print("2. Testing VERIFY")
        print("=" * 60)
        rc = main(["verify", "--store", str(store), "--manifest", str(manifest)])
        assert rc == 0, f"verify failed with rc={rc}"
        print("Verify OK")

        print()
        print("=" * 60)
        print("3. Testing STATS")
        print("=" * 60)
        rc = main(["stats", str(manifest), "--store", str(store), "--top", "5"])
        assert rc == 0, f"stats failed with rc={rc}"
        print("Stats OK")

        print()
        print("=" * 60)
        print("4. Testing RESTORE")
        print("=" * 60)
        out = tmpdir / "restored"
        rc = main(["restore", str(manifest), "--store", str(store), "--out", str(out)])
        assert rc == 0, f"restore failed with rc={rc}"
        print("Restore OK")

        print()
        print("=" * 60)
        print("5. Verifying bit-for-bit equality")
        print("=" * 60)

        src_files = {}
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                src_files[str(rel).replace("\\", "/")] = f.read_bytes()

        out_files = {}
        for f in out.rglob("*"):
            if f.is_file():
                rel = f.relative_to(out)
                out_files[str(rel).replace("\\", "/")] = f.read_bytes()

        assert set(src_files.keys()) == set(out_files.keys()), \
            f"File list mismatch: {set(src_files.keys()) ^ set(out_files.keys())}"

        for path in src_files:
            assert src_files[path] == out_files[path], f"Content mismatch: {path}"

        print(f"All {len(src_files)} files match bit-for-bit!")
        print()
        print("=" * 60)
        print("ALL END-TO-END TESTS PASSED!")
        print("=" * 60)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_e2e()
