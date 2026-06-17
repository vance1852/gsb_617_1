"""Command-line interface for the cas tool.

Subcommands:
    pack     Pack a directory into a content-addressed store
    restore  Restore files from a store using a manifest
    verify   Verify store integrity and manifest references
    stats    Show deduplication statistics from a manifest
"""

import argparse
import os
import sys

from .store import FileContentStore
from .manifest import FileManifest
from .packer import pack_directory
from .restorer import restore_manifest, RestoreError
from .verifier import verify_store, verify_manifest
from .stats import compute_stats


def _add_chunk_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--avg-size",
        type=int,
        default=8192,
        help="Target average chunk size in bytes (default: 8192)",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=2048,
        help="Minimum chunk size in bytes (default: 2048)",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=65536,
        help="Maximum chunk size in bytes (default: 65536)",
    )


def cmd_pack(args: argparse.Namespace) -> int:
    source_dir = os.path.abspath(args.dir)
    store_path = os.path.abspath(args.store)

    if not os.path.isdir(source_dir):
        print(f"error: source directory not found: {source_dir}",
              file=sys.stderr)
        return 1

    store = FileContentStore(store_path)

    num_workers = args.workers if hasattr(args, 'workers') else None

    manifest = pack_directory(
        source_dir=source_dir,
        store=store,
        avg_size=args.avg_size,
        min_size=args.min_size,
        max_size=args.max_size,
        num_workers=num_workers,
    )

    manifest_path = args.manifest if hasattr(args, 'manifest') and args.manifest \
        else os.path.join(store_path, "manifest")
    manifest.save(manifest_path)

    print(f"Packed {manifest.num_files} files into {store_path}")
    print(f"  Total bytes: {manifest.total_bytes}")
    print(f"  Total chunks (refs): {manifest.total_chunk_refs}")
    print(f"  Unique chunks: {len(manifest.all_chunk_digests())}")
    print(f"  Manifest: {manifest_path}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    manifest_path = os.path.abspath(args.manifest)
    store_path = os.path.abspath(args.store)
    out_dir = os.path.abspath(args.out)

    if not os.path.isfile(manifest_path):
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    store = FileContentStore(store_path)

    try:
        manifest = FileManifest.load(manifest_path)
    except (ValueError, OSError) as e:
        print(f"error: failed to load manifest: {e}", file=sys.stderr)
        return 1

    try:
        restore_manifest(manifest, store, out_dir)
    except RestoreError as e:
        print(f"error: restore failed: {e}", file=sys.stderr)
        return 1

    print(f"Restored {manifest.num_files} files to {out_dir}")
    print(f"  Total bytes: {manifest.total_bytes}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    store_path = os.path.abspath(args.store)
    store = FileContentStore(store_path)

    manifest_path = None
    if hasattr(args, 'manifest') and args.manifest:
        manifest_path = os.path.abspath(args.manifest)

    if manifest_path:
        try:
            manifest = FileManifest.load(manifest_path)
        except (ValueError, OSError) as e:
            print(f"error: failed to load manifest: {e}", file=sys.stderr)
            return 1
        result = verify_manifest(store, manifest)
    else:
        result = verify_store(store)

    print(result.report())
    return 0 if result.ok else 1


def cmd_stats(args: argparse.Namespace) -> int:
    manifest_path = os.path.abspath(args.manifest)
    store_path = os.path.abspath(args.store)

    if not os.path.isfile(manifest_path):
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = FileManifest.load(manifest_path)
    except (ValueError, OSError) as e:
        print(f"error: failed to load manifest: {e}", file=sys.stderr)
        return 1

    store = FileContentStore(store_path)
    result = compute_stats(manifest, store, top_n=args.top)

    print(result.report())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cas",
        description="Content-Addressed Storage engine with CDC chunking",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pack
    pack_p = subparsers.add_parser("pack", help="Pack a directory into the store")
    pack_p.add_argument("dir", help="Source directory to pack")
    pack_p.add_argument("--store", required=True, help="Path to the store directory")
    pack_p.add_argument("--manifest", help="Path to write manifest (default: <store>/manifest)")
    pack_p.add_argument("--workers", type=int, default=None,
                        help="Number of worker processes (default: CPU count)")
    _add_chunk_args(pack_p)
    pack_p.set_defaults(func=cmd_pack)

    # restore
    restore_p = subparsers.add_parser("restore", help="Restore from a manifest")
    restore_p.add_argument("manifest", help="Path to the manifest file")
    restore_p.add_argument("--store", required=True, help="Path to the store directory")
    restore_p.add_argument("--out", required=True, help="Output directory")
    restore_p.set_defaults(func=cmd_restore)

    # verify
    verify_p = subparsers.add_parser("verify", help="Verify store integrity")
    verify_p.add_argument("--store", required=True, help="Path to the store directory")
    verify_p.add_argument("--manifest", help="Also verify manifest references")
    verify_p.set_defaults(func=cmd_verify)

    # stats
    stats_p = subparsers.add_parser("stats", help="Show deduplication statistics")
    stats_p.add_argument("manifest", help="Path to the manifest file")
    stats_p.add_argument("--store", required=True, help="Path to the store directory")
    stats_p.add_argument("--top", type=int, default=10,
                         help="Number of top-referenced chunks to show (default: 10)")
    stats_p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
