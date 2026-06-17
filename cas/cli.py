from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chunker import RabinChunker
from .pack import pack
from .restore import restore
from .sha256 import SHA256
from .stats import stats
from .verify import verify


def cmd_pack(args: argparse.Namespace) -> None:
    directory = args.directory
    store_path = args.store
    manifest_path = getattr(args, "manifest", None)
    avg_size = args.avg_size
    min_size = args.min_size
    max_size = args.max_size
    workers = getattr(args, "workers", None)

    chunker_kwargs = {
        "avg_size": avg_size,
        "min_size": min_size,
        "max_size": max_size,
    }

    mf = pack(
        directory=directory,
        store_path=store_path,
        chunker_cls=RabinChunker,
        chunker_kwargs=chunker_kwargs,
        hasher_cls=SHA256,
        workers=workers,
    )

    if manifest_path is None:
        manifest_path = str(Path(store_path) / "manifest.cas")

    mf.save(manifest_path)
    print(f"Packed {len(mf.entries)} files -> {manifest_path}")


def cmd_restore(args: argparse.Namespace) -> None:
    restore(
        manifest_path=args.manifest,
        store_path=args.store,
        out_dir=args.out,
    )
    print(f"Restored to {args.out}")


def cmd_verify(args: argparse.Namespace) -> None:
    result = verify(
        store_path=args.store,
        manifest_path=getattr(args, "manifest", None),
    )
    if result > 0:
        sys.exit(1)


def cmd_stats(args: argparse.Namespace) -> None:
    stats(
        manifest_path=args.manifest,
        top=args.top,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cas",
        description="Content-addressed storage engine based on CDC",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pack = sub.add_parser("pack", help="Pack a directory into a content store")
    p_pack.add_argument("directory", help="Directory to pack")
    p_pack.add_argument("--store", required=True, help="Store path")
    p_pack.add_argument("--manifest", default=None, help="Manifest output path")
    p_pack.add_argument("--avg-size", type=int, default=8192, help="Average chunk size (default 8KB)")
    p_pack.add_argument("--min-size", type=int, default=2048, help="Minimum chunk size (default 2KB)")
    p_pack.add_argument("--max-size", type=int, default=65536, help="Maximum chunk size (default 64KB)")
    p_pack.add_argument("--workers", type=int, default=None, help="Number of worker processes")
    p_pack.set_defaults(func=cmd_pack)

    p_restore = sub.add_parser("restore", help="Restore files from a manifest and store")
    p_restore.add_argument("manifest", help="Manifest file path")
    p_restore.add_argument("--store", required=True, help="Store path")
    p_restore.add_argument("--out", required=True, help="Output directory")
    p_restore.set_defaults(func=cmd_restore)

    p_verify = sub.add_parser("verify", help="Verify store integrity")
    p_verify.add_argument("--store", required=True, help="Store path")
    p_verify.add_argument("--manifest", default=None, help="Manifest file to check referenced chunks")
    p_verify.set_defaults(func=cmd_verify)

    p_stats = sub.add_parser("stats", help="Show dedup statistics")
    p_stats.add_argument("manifest", help="Manifest file path")
    p_stats.add_argument("--top", type=int, default=10, help="Top N most referenced chunks (default 10)")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


__all__ = ["main"]
