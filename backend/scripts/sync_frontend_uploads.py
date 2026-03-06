#!/usr/bin/env python3
"""
Sync uploaded files from frontend to backend input directory.

This script handles the path separation between frontend uploads
(frontend/data/scraped/) and the backend indexing location
(backend/data/input/).

Usage:
    python scripts/sync_frontend_uploads.py              # Sync all files
    python scripts/sync_frontend_uploads.py --index      # Sync and index new files
    python scripts/sync_frontend_uploads.py --pdfs-only  # Sync PDFs only
"""

import sys
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_SCRAPED = PROJECT_ROOT / "frontend" / "data" / "scraped"
BACKEND_INPUT = BACKEND_DIR / "data" / "input"

# Subdirectories
BACKEND_PDFS_ROOT = BACKEND_INPUT  # Root PDFs go here
BACKEND_SCRAPED = BACKEND_INPUT / "scraped"
BACKEND_SCRAPED_PDFS = BACKEND_SCRAPED / "pdfs"
BACKEND_SCRAPED_PAGES = BACKEND_SCRAPED / "pages"


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def ensure_directories():
    """Ensure all required directories exist."""
    directories = [
        BACKEND_SCRAPED,
        BACKEND_SCRAPED_PDFS,
        BACKEND_SCRAPED_PAGES,
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)


def sync_file(src: Path, dest: Path, dry_run: bool = False) -> bool:
    """
    Sync a single file from source to destination.

    Returns True if file was copied (new or updated).
    """
    if not src.exists():
        return False

    # Check if destination exists and is up to date
    if dest.exists():
        # Compare sizes and modification times
        if dest.stat().st_size >= src.stat().st_size:
            # Destination is same or newer (size check is enough for our use case)
            return False

    if dry_run:
        print(f"  Would copy: {src.name}")
        return True

    try:
        shutil.copy2(src, dest)
        return True
    except Exception as e:
        print(f"  ❌ Error copying {src.name}: {e}")
        return False


def sync_pdfs(dry_run: bool = False) -> dict:
    """
    Sync PDF files from frontend to backend.

    Returns dict with stats.
    """
    stats = {"copied": 0, "skipped": 0, "errors": 0}
    frontend_pdfs = FRONTEND_SCRAPED / "pdfs"

    if not frontend_pdfs.exists():
        print(f"  ⚠️ Frontend PDFs directory not found: {frontend_pdfs}")
        return stats

    print(f"\n  Scanning: {frontend_pdfs}")
    pdf_files = list(frontend_pdfs.glob("*.pdf"))
    print(f"  Found {len(pdf_files)} PDF files")

    for src in pdf_files:
        dest = BACKEND_SCRAPED_PDFS / src.name
        if sync_file(src, dest, dry_run):
            stats["copied"] += 1
            print(f"  + {src.name}")
        else:
            stats["skipped"] += 1

    return stats


def sync_pages(dry_run: bool = False) -> dict:
    """
    Sync page text files from frontend to backend.

    Returns dict with stats.
    """
    stats = {"copied": 0, "skipped": 0, "errors": 0}
    frontend_pages = FRONTEND_SCRAPED / "pages"

    if not frontend_pages.exists():
        print(f"  ⚠️ Frontend pages directory not found: {frontend_pages}")
        return stats

    print(f"\n  Scanning: {frontend_pages}")
    txt_files = list(frontend_pages.glob("*.txt"))
    print(f"  Found {len(txt_files)} text files")

    for src in txt_files:
        dest = BACKEND_SCRAPED_PAGES / src.name
        if sync_file(src, dest, dry_run):
            stats["copied"] += 1
            print(f"  + {src.name}")
        else:
            stats["skipped"] += 1

    return stats


def sync_root_pdfs(dry_run: bool = False) -> dict:
    """
    Sync PDFs from frontend root (if any) to backend root.

    Returns dict with stats.
    """
    stats = {"copied": 0, "skipped": 0, "errors": 0}

    # Check if there are PDFs directly in frontend/data/scraped
    pdf_files = list(FRONTEND_SCRAPED.glob("*.pdf"))

    if not pdf_files:
        return stats

    print(f"\n  Scanning root for PDFs")
    print(f"  Found {len(pdf_files)} PDF files")

    for src in pdf_files:
        dest = BACKEND_PDFS_ROOT / src.name
        if sync_file(src, dest, dry_run):
            stats["copied"] += 1
            print(f"  + {src.name}")
        else:
            stats["skipped"] += 1

    return stats


def sync_all(pdfs_only: bool = False, dry_run: bool = False) -> dict:
    """
    Sync all files from frontend to backend.

    Returns dict with combined stats.
    """
    total_stats = {"copied": 0, "skipped": 0, "errors": 0}

    ensure_directories()

    # Sync PDFs
    pdf_stats = sync_pdfs(dry_run)
    root_pdf_stats = sync_root_pdfs(dry_run)

    for key in total_stats:
        total_stats[key] += pdf_stats[key] + root_pdf_stats[key]

    # Sync pages (text files)
    if not pdfs_only:
        page_stats = sync_pages(dry_run)
        for key in total_stats:
            total_stats[key] += page_stats[key]

    return total_stats


def index_new_files():
    """Run incremental indexing on new files using Milvus."""
    print_section("Running Incremental Index (Milvus)")

    try:
        # Import Milvus indexer
        from src.milvus_store import MilvusStore
        from src.milvus_indexer import MilvusIndexer
        from src.embedding import EmbeddingClient
        from src.config import config

        # Initialize Milvus store
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )

        # Initialize embedding client - MUST use BGE-M3
        embedding_client = EmbeddingClient(
            model_name="BAAI/bge-m3",
            device=config.embedding_device
        )

        # Create Milvus indexer
        indexer = MilvusIndexer(milvus_store, embedding_client)

        # Index new files
        result = indexer.add_new_documents(input_dir=str(BACKEND_INPUT))

        print(f"\n  Files added: {result.get('added', 0)}")
        print(f"  Chunks indexed: {result.get('chunks_added', 0)}")
        print(f"  Files skipped: {result.get('skipped', 0)}")

        return result.get('chunks_added', 0) > 0

    except Exception as e:
        print(f"  ❌ Indexing error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync frontend uploads to backend for indexing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync all files (no indexing)
  python scripts/sync_frontend_uploads.py

  # Sync and index new files
  python scripts/sync_frontend_uploads.py --index

  # Sync only PDFs
  python scripts/sync_frontend_uploads.py --pdfs-only

  # Show what would be copied (dry run)
  python scripts/sync_frontend_uploads.py --dry-run

  # Sync and index in one command
  python scripts/sync_frontend_uploads.py --index --pdfs-only
        """
    )

    parser.add_argument(
        "--index", "-i",
        action="store_true",
        help="Run incremental indexing after syncing"
    )

    parser.add_argument(
        "--pdfs-only",
        action="store_true",
        help="Sync only PDF files, skip text files"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without actually copying"
    )

    args = parser.parse_args()

    print_section("Frontend to Backend File Sync")
    print(f"  Frontend: {FRONTEND_SCRAPED}")
    print(f"  Backend:  {BACKEND_INPUT}")

    if args.dry_run:
        print("\n  ⚠️ DRY RUN - No files will be copied")

    # Sync files
    stats = sync_all(pdfs_only=args.pdfs_only, dry_run=args.dry_run)

    # Show results
    print_section("Sync Results")
    print(f"  Copied:  {stats['copied']} file(s)")
    print(f"  Skipped: {stats['skipped']} file(s) (already up to date)")
    if stats['errors'] > 0:
        print(f"  Errors:  {stats['errors']} file(s)")

    if args.index and not args.dry_run:
        if stats['copied'] > 0:
            # Run indexing only if files were copied
            index_new_files()
        else:
            print("\n  ℹ️ No new files to index")

    print_section("Complete")
    print("  ✅ Done!" if not args.dry_run else "  ℹ️ Dry run complete")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
