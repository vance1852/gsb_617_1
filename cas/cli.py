"""Command-line interface for the cas tool.

Provides four subcommands:
    pack     - Recursively chunk a directory into the content store
    restore  - Rebuild files from a manifest and store
    verify   - Check store integrity and manifest reference completeness
    stats    - Produce deduplication statistics report
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .packer import pack_directory
from .restore import restore_manifest, RestoreError
from .stats import compute_stats, format_report
from .verify import verify_store


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cas",
        description="Content-Addressable Storage engine with CDC deduplication",
    )
    parser.add_argument("--version", action="version", version=f"cas {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_pack_parser(subparsers)
    _add_restore_parser(subparsers)
    _add_verify_parser(subparsers)
    _add_stats_parser(subparsers)

    return parser


def _add_pack_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "pack",
        help="Recursively chunk a directory into the content store",
    )
    p.add_argument("dir", help="Source directory to pack")
    p.add_argument("--store", required=True, help="Path to content store directory")
    p.add_argument(
        "--manifest",
        default=None,
        help="Path to write manifest (default: <store>/manifest.txt)",
    )
    p.add_argument(
        "--min-size",
        type=int,
        default=2 * 1024,
        help="Minimum chunk size in bytes (default: 2KB)",
    )
    p.add_argument(
        "--avg-size",
        type=int,
        default=8 * 1024,
        help="Target average chunk size in bytes (default: 8KB)",
    )
    p.add_argument(
        "--max-size",
        type=int,
        default=64 * 1024,
        help="Maximum chunk size in bytes (default: 64KB)",
    )
    p.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        help="Number of worker processes (default: CPU count)",
    )


def _add_restore_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "restore",
        help="Rebuild files from a manifest and content store",
    )
    p.add_argument("manifest", help="Path to manifest file")
    p.add_argument("--store", required=True, help="Path to content store directory")
    p.add_argument("--out", required=True, help="Output directory for restored files")


def _add_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "verify",
        help="Verify store integrity and manifest references",
    )
    p.add_argument("--store", required=True, help="Path to content store directory")
    p.add_argument(
        "--manifest",
        default=None,
        help="Optional manifest to check for missing referenced chunks",
    )


def _add_stats_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "stats",
        help="Show deduplication statistics from a manifest",
    )
    p.add_argument("manifest", help="Path to manifest file")
    p.add_argument(
        "--store",
        default=None,
        help="Optional store path for accurate stored byte count",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top referenced chunks to show (default: 10)",
    )


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the cas CLI.

    Args:
        argv: Command-line arguments (excluding program name).
              If None, uses sys.argv[1:].

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "pack":
            return _cmd_pack(args)
        elif args.command == "restore":
            return _cmd_restore(args)
        elif args.command == "verify":
            return _cmd_verify(args)
        elif args.command == "stats":
            return _cmd_stats(args)
        else:
            parser.print_help()
            return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


def _cmd_pack(args: argparse.Namespace) -> int:
    manifest = pack_directory(
        source_dir=args.dir,
        store_path=args.store,
        manifest_path=args.manifest,
        min_size=args.min_size,
        avg_size=args.avg_size,
        max_size=args.max_size,
        num_workers=args.jobs,
    )
    file_count = sum(1 for _ in manifest.iter_files())
    print(f"Packed {file_count} files into {args.store}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        restore_manifest(
            manifest_path=args.manifest,
            store_path=args.store,
            out_dir=args.out,
        )
    except RestoreError as e:
        print(f"restore error: {e}", file=sys.stderr)
        return 1
    print(f"Restored to {args.out}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_store(
        store_path=args.store,
        manifest_path=args.manifest,
    )

    print(f"Total chunks in store:  {result.total_chunks}")
    print(f"Corrupted chunks:       {len(result.corrupted_chunks)}")
    print(f"Missing referenced:     {len(result.missing_chunks)}")

    if result.corrupted_chunks:
        print("\nCorrupted:")
        for d in result.corrupted_chunks:
            print(f"  {d}")

    if result.missing_chunks:
        print("\nMissing (referenced by manifest):")
        for d in result.missing_chunks:
            print(f"  {d}")

    if result.ok:
        print("\nAll checks passed.")
        return 0
    else:
        print("\nVerification FAILED.", file=sys.stderr)
        return 1


def _cmd_stats(args: argparse.Namespace) -> int:
    report = compute_stats(
        manifest_path=args.manifest,
        store_path=args.store,
        top_n=args.top,
    )
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
