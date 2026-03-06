#!/usr/bin/env python3
"""Rebuild the Milvus RAG index.

This script rebuilds the Milvus vector index from source documents.

Usage:
    python scripts/rebuild_index.py          # Full rebuild
    python scripts/rebuild_index.py --verify # Verify only
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.milvus_store import MilvusStore
from src.milvus_indexer import MilvusIndexer
from src.config import config


def main():
    """Main entry point for index rebuild."""
    parser = argparse.ArgumentParser(description="Rebuild or verify Milvus RAG index")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify index integrity instead of rebuilding"
    )
    parser.add_argument(
        "--input-dir",
        default="data/input",
        help="Input directory containing source documents (default: data/input)"
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Don't reset (clear) the collection before rebuilding (adds only new documents)"
    )

    args = parser.parse_args()

    if args.verify:
        # Verify index
        print("=" * 80)
        print("VERIFYING MILVUS INDEX")
        print("=" * 80)

        try:
            milvus_store = MilvusStore(
                host=config.milvus_host,
                port=config.milvus_port,
                collection_name=config.milvus_collection,
                reset=False,
            )
            health = milvus_store.health_check()

            print(f"Collection: {config.milvus_collection}")
            print(f"Healthy: {health.get('healthy', False)}")
            print(f"Chunks: {health.get('count', 0)}")
            print(f"Unique sources: {health.get('unique_sources', 0)}")

            if not health.get('healthy', False):
                sys.exit(1)

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Full rebuild
        print("=" * 80)
        print("REBUILDING MILVUS INDEX")
        print("=" * 80)
        print(f"Input directory: {args.input_dir}")
        print(f"Milvus: {config.milvus_host}:{config.milvus_port}")
        print(f"Collection: {config.milvus_collection}")
        print(f"Reset before rebuild: {not args.no_reset}")
        print()

        try:
            # Initialize Milvus store with reset option
            milvus_store = MilvusStore(
                host=config.milvus_host,
                port=config.milvus_port,
                collection_name=config.milvus_collection,
                reset=not args.no_reset,  # Reset unless --no-reset is specified
            )

            # Create Milvus indexer with BGE-M3 model
            indexer = MilvusIndexer(
                milvus_store,
                embedding_model="BAAI/bge-m3"
            )

            # Rebuild index
            if args.no_reset:
                # Add new documents only
                print("Adding new documents only (--no-reset specified)...")
                result = indexer.add_new_documents(input_dir=args.input_dir)
                chunks_indexed = result.get('chunks_added', 0)
                files_processed = result.get('added', 0)
            else:
                # Full rebuild
                print("Running full rebuild...")
                chunks_indexed = indexer.rebuild(str(args.input_dir))
                files_processed = 0  # rebuild() doesn't return file count

            # Print result summary
            print("\n" + "=" * 80)
            print("REBUILD COMPLETE")
            print("=" * 80)
            print(f"Chunks indexed: {chunks_indexed}")
            print(f"Collection: {config.milvus_collection}")
            print(f"Embedding model: BAAI/bge-m3 (1024 dim)")

        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
