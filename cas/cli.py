"""Command-line interface for the cas tool.

Subcommands:
  pack     Pack a directory into the content-addressed store
  restore  Restore files from a manifest
  verify   Verify store integrity and optionally check manifest references
  stats    Show deduplication statistics from a manifest
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="cas",
        description="Content-Addressable Storage engine with CDC (Rabin fingerprint)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cas {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_pack_parser(subparsers)
    _add_restore_parser(subparsers)
    _add_verify_parser(subparsers)
    _add_stats_parser(subparsers)

    return parser


def _add_pack_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'pack' subcommand parser."""
    p = subparsers.add_parser(
        "pack",
        help="Pack a directory into the content-addressed store",
        description="Recursively scan a directory, chunk all files using "
                    "Rabin CDC, store unique chunks, and write a manifest.",
    )
    p.add_argument(
        "dir",
        help="Source directory to pack",
    )
    p.add_argument(
        "--store",
        required=True,
        dest="store_path",
        help="Path to the content-addressed store directory",
    )
    p.add_argument(
        "--manifest",
        dest="manifest_path",
        help="Path for the output manifest file (default: <dir>.manifest)",
    )
    p.add_argument(
        "--avg-size",
        type=int,
        default=8192,
        help="Target average chunk size in bytes (default: 8192)",
    )
    p.add_argument(
        "--min-size",
        type=int,
        default=2048,
        help="Minimum chunk size in bytes (default: 2048)",
    )
    p.add_argument(
        "--max-size",
        type=int,
        default=65536,
        help="Maximum chunk size in bytes (default: 65536)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes (default: CPU count)",
    )
    p.set_defaults(func=_cmd_pack)


def _add_restore_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'restore' subcommand parser."""
    p = subparsers.add_parser(
        "restore",
        help="Restore files from a manifest",
        description="Read a manifest and reconstruct the original directory "
                    "tree by fetching chunks from the store. Each file is "
                    "verified by SHA-256 after reconstruction.",
    )
    p.add_argument(
        "manifest",
        help="Path to the manifest file",
    )
    p.add_argument(
        "--store",
        required=True,
        dest="store_path",
        help="Path to the content-addressed store directory",
    )
    p.add_argument(
        "--out",
        required=True,
        dest="out_dir",
        help="Output directory for restored files",
    )
    p.set_defaults(func=_cmd_restore)


def _add_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'verify' subcommand parser."""
    p = subparsers.add_parser(
        "verify",
        help="Verify store integrity",
        description="Verify all chunks in the store by recomputing their "
                    "SHA-256 hash. With --manifest, also checks that all "
                    "referenced chunks exist and are intact.",
    )
    p.add_argument(
        "--store",
        required=True,
        dest="store_path",
        help="Path to the content-addressed store directory",
    )
    p.add_argument(
        "--manifest",
        dest="manifest_path",
        help="Optional manifest to check for missing referenced chunks",
    )
    p.set_defaults(func=_cmd_verify)


def _add_stats_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'stats' subcommand parser."""
    p = subparsers.add_parser(
        "stats",
        help="Show deduplication statistics",
        description="Analyze a manifest and report deduplication statistics "
                    "including space savings and most-referenced chunks.",
    )
    p.add_argument(
        "manifest",
        help="Path to the manifest file",
    )
    p.add_argument(
        "--store",
        required=True,
        dest="store_path",
        help="Path to the content-addressed store directory",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top referenced chunks to show (default: 10)",
    )
    p.set_defaults(func=_cmd_stats)


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute the 'pack' command."""
    from .pack import pack_directory

    source_dir = os.path.abspath(args.dir)
    store_path = os.path.abspath(args.store_path)

    if args.manifest_path:
        manifest_path = os.path.abspath(args.manifest_path)
    else:
        base = os.path.basename(os.path.normpath(source_dir))
        manifest_path = os.path.join(os.getcwd(), f"{base}.manifest")

    if args.min_size >= args.max_size:
        print("error: --min-size must be less than --max-size", file=sys.stderr)
        return 1
    if args.avg_size < args.min_size or args.avg_size > args.max_size:
        print("error: --avg-size must be between --min-size and --max-size",
              file=sys.stderr)
        return 1

    manifest = pack_directory(
        source_dir=source_dir,
        store_path=store_path,
        manifest_path=manifest_path,
        avg_size=args.avg_size,
        min_size=args.min_size,
        max_size=args.max_size,
        num_workers=args.workers,
    )

    num_files = len(manifest.get_files())
    print(f"Packed {num_files} files")
    print(f"Manifest written to: {manifest_path}")
    print(f"Store: {store_path}")

    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    """Execute the 'restore' command."""
    from .restore import restore_manifest, RestoreError

    manifest_path = os.path.abspath(args.manifest)
    store_path = os.path.abspath(args.store_path)
    out_dir = os.path.abspath(args.out_dir)

    try:
        restore_manifest(
            manifest_path=manifest_path,
            store_path=store_path,
            out_dir=out_dir,
        )
    except RestoreError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Restored to: {out_dir}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Execute the 'verify' command."""
    from .verify import verify_store, print_verify_result

    store_path = os.path.abspath(args.store_path)
    manifest_path = os.path.abspath(args.manifest_path) if args.manifest_path else None

    result = verify_store(
        store_path=store_path,
        manifest_path=manifest_path,
    )

    print_verify_result(result)
    return 0 if result.ok else 1


def _cmd_stats(args: argparse.Namespace) -> int:
    """Execute the 'stats' command."""
    from .stats_ import compute_stats, print_stats

    manifest_path = os.path.abspath(args.manifest)
    store_path = os.path.abspath(args.store_path)

    result = compute_stats(
        manifest_path=manifest_path,
        store_path=store_path,
        top_n=args.top,
    )

    print_stats(result, top_n=args.top)
    return 0


def main(argv: list = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: List of command-line arguments (excluding program name).
              If None, uses sys.argv[1:].

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
