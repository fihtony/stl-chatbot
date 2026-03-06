#!/usr/bin/env python3
"""
Incremental document indexing script using Milvus.

This script adds only new (unindexed) documents to the Milvus RAG system.
It does NOT rebuild the entire index - it only processes new files.

Usage:
    python scripts/add_new_documents.py                    # Add all new files
    python scripts/add_new_documents.py --file path.pdf     # Add specific file
    python scripts/add_new_documents.py --verify           # Verify and add new files
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.milvus_store import MilvusStore
from src.milvus_indexer import MilvusIndexer
from src.embedding import EmbeddingClient
from src.config import config


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def get_indexer():
    """Get or create Milvus indexer."""
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
    return MilvusIndexer(milvus_store, embedding_client)


def verify_and_add(input_dir: str = "./data/input") -> bool:
    """Verify index and add new documents."""
    print_section("Step 1: Verify Current Index")

    try:
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )
        health = milvus_store.health_check()

        print(f"  Current chunks: {health.get('count', 0)}")
        print(f"  Collection: {config.milvus_collection}")

    except Exception as e:
        print(f"  ❌ Error verifying index: {e}")
        return False

    print_section("Step 2: Add New Documents")

    try:
        indexer = get_indexer()
        result = indexer.add_new_documents(input_dir=input_dir)

        print(f"  Files added: {result.get('added', 0)}")
        print(f"  Chunks indexed: {result.get('chunks_added', 0)}")
        print(f"  Files skipped: {result.get('skipped', 0)}")

        return result.get('chunks_added', 0) > 0

    except Exception as e:
        print(f"  ❌ Error adding documents: {e}")
        import traceback
        traceback.print_exc()
        return False


def add_specific_files(file_paths: list) -> bool:
    """Add specific files to the index."""
    print_section(f"Adding {len(file_paths)} File(s)")

    print("  Files to add:")
    for path in file_paths:
        exists = "✓" if Path(path).exists() else "✗"
        print(f"    {exists} {path}")

    try:
        indexer = get_indexer()

        # For specific files, we need to process them
        # MilvusIndexer.add_new_documents processes directories
        # So we'll need to ensure files are in the data/input directory

        added = 0
        for file_path in file_paths:
            path = Path(file_path)
            if path.exists():
                # Copy to input directory if not already there
                import shutil
                input_dir = Path("./data/input")
                target_dir = input_dir / "uploaded"
                target_dir.mkdir(parents=True, exist_ok=True)

                target = target_dir / path.name
                shutil.copy2(path, target)
                added += 1

        # Now index all new files
        result = indexer.add_new_documents()

        print(f"\n  Files processed: {result.get('added', 0)}")
        print(f"  Chunks indexed: {result.get('chunks_added', 0)}")

        return result.get('chunks_added', 0) > 0

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Incremental document indexing for Milvus RAG system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add all new documents automatically
  python scripts/add_new_documents.py

  # Add a specific file
  python scripts/add_new_documents.py --file data/input/new.pdf

  # Add multiple files
  python scripts/add_new_documents.py --file file1.pdf --file file2.pdf

  # Verify index first, then add new files
  python scripts/add_new_documents.py --verify

  # Check index status only (no changes)
  python scripts/add_new_documents.py --status
        """
    )

    parser.add_argument(
        "--file", "-f",
        action="append",
        dest="files",
        help="Add specific file(s) to index. Can be used multiple times."
    )

    parser.add_argument(
        "--input-dir", "-i",
        default="./data/input",
        help="Input directory containing documents (default: ./data/input)"
    )

    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify index before adding new documents"
    )

    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show index status only (no changes)"
    )

    args = parser.parse_args()

    # Show status and exit
    if args.status:
        print_section("Index Status (Milvus)")
        try:
            milvus_store = MilvusStore(
                host=config.milvus_host,
                port=config.milvus_port,
                collection_name=config.milvus_collection,
                reset=False,
            )
            health = milvus_store.health_check()
            print(f"  Chunks indexed: {health.get('count', 0)}")
            print(f"  Unique sources: {health.get('unique_sources', 0)}")
            print(f"  Collection: {config.milvus_collection}")
            print(f"  Healthy: {health.get('healthy', False)}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        return 0

    # Add specific files
    if args.files:
        success = add_specific_files(args.files)
    else:
        # Auto-add new files
        if args.verify:
            success = verify_and_add(args.input_dir)
        else:
            print_section("Adding New Documents")
            try:
                indexer = get_indexer()
                result = indexer.add_new_documents(input_dir=args.input_dir)

                print(f"  Files added: {result.get('added', 0)}")
                print(f"  Chunks indexed: {result.get('chunks_added', 0)}")
                print(f"  Files skipped: {result.get('skipped', 0)}")

                success = result.get('chunks_added', 0) > 0

            except Exception as e:
                print(f"  ❌ Error: {e}")
                import traceback
                traceback.print_exc()
                success = False

    print_section("Complete")
    print("  ✅ Done!" if success else "  ⚠️ Finished with warnings")
    print()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
