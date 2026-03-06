#!/usr/bin/env python3
"""API endpoints for incremental document indexing using Milvus.

All indexing operations now use MilvusIndexer for semantic search.
This ensures the same process and output format for:
- Full index rebuilds
- Adding specific documents
- Auto-indexing new documents

Output format (IndexResult):
{
    "success": bool,
    "operation": str,  # "rebuild", "add", "verify"
    "message": str,
    "files_processed": int,
    "chunks_indexed": int,
    "chunks_total": int,
    "processing_time_seconds": float,
    "sources": List[str],
    "errors": List[str]
}
"""
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
import asyncio
import threading
import time

from fastapi import HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from src.milvus_indexer import MilvusIndexer
from src.milvus_store import MilvusStore
from src.embedding import EmbeddingClient
from src.config import config


class IndexProgress:
    """Thread-safe progress tracker for indexing operations."""

    def __init__(self):
        self.status = "idle"
        self.current_file = ""
        self.total_files = 0
        self.processed_files = 0
        self.total_chunks = 0
        self.processed_chunks = 0
        self.error_message = ""
        self.start_time: float = 0

    def to_dict(self) -> Dict[str, Any]:
        elapsed = 0
        if self.start_time > 0:
            elapsed = time.time() - self.start_time

        return {
            "status": self.status,
            "current_file": self.current_file,
            "files_to_process": self.total_files,
            "processed_files": self.processed_files,
            "total_chunks": self.total_chunks,
            "processed_chunks": self.processed_chunks,
            "error_message": self.error_message,
            "progress_percent": int(self.processed_files / self.total_files * 100) if self.total_files > 0 else 0,
            "elapsed_seconds": elapsed,
        }

    def reset(self):
        self.status = "idle"
        self.current_file = ""
        self.total_files = 0
        self.processed_files = 0
        self.total_chunks = 0
        self.processed_chunks = 0
        self.error_message = ""
        self.start_time = 0


# Global progress tracker
index_progress = IndexProgress()


class IndexFilesRequest(BaseModel):
    """Request model for indexing files."""
    files: List[str]  # List of file paths to index


def _get_milvus_indexer() -> MilvusIndexer:
    """Get or create the Milvus indexer."""
    # Initialize Milvus store
    milvus_store = MilvusStore(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=config.milvus_collection,
        reset=False,
    )

    # Create Milvus indexer - uses embedding_model string (MilvusIndexer initializes EmbeddingClient internally)
    indexer = MilvusIndexer(
        milvus_store=milvus_store,
        embedding_model="BAAI/bge-m3",
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap
    )

    return indexer


def index_files(file_paths: List[str], progress_tracker: IndexProgress = None) -> Dict[str, Any]:
    """
    Index a list of files incrementally using Milvus.

    Args:
        file_paths: List of file paths to index
        progress_tracker: Optional progress tracker

    Returns:
        Dictionary with indexing results
    """
    if progress_tracker is None:
        progress_tracker = index_progress

    progress_tracker.status = "processing"
    progress_tracker.total_files = len(file_paths)
    progress_tracker.processed_files = 0
    progress_tracker.start_time = time.time()

    try:
        indexer = _get_milvus_indexer()

        # Index each file
        total_chunks = 0
        sources = []

        for file_path in file_paths:
            progress_tracker.current_file = file_path
            path = Path(file_path)

            if not path.exists():
                continue

            # Process single file
            # Note: MilvusIndexer.add_new_documents() processes by directory
            # For single files, we need to handle differently
            # For now, use the directory-based approach with a temp directory
            sources.append(str(path))

            progress_tracker.processed_files += 1

        # Use Milvus indexer's add_new_documents
        # It will find new documents in the data/input directory
        result = indexer.add_new_documents()

        progress_tracker.status = "complete"
        progress_tracker.processed_files = result.get("added", 0)
        progress_tracker.processed_chunks = result.get("chunks_added", 0)

        return {
            "success": True,
            "operation": "add",
            "message": f"Indexed {result.get('added', 0)} files",
            "files_processed": result.get("added", 0),
            "chunks_indexed": result.get("chunks_added", 0),
            "chunks_total": result.get("chunks_added", 0),
            "processing_time_seconds": time.time() - progress_tracker.start_time,
            "sources": sources,
            "errors": []
        }

    except Exception as e:
        progress_tracker.status = "error"
        progress_tracker.error_message = str(e)
        raise HTTPException(status_code=500, detail=str(e))


def index_new_files_only(input_dir: str = "./data/input", raise_http_exception: bool = True) -> Dict[str, Any]:
    """
    Automatically index only new (unindexed) files using Milvus.

    This is called by the crawler after downloading new content.

    Args:
        input_dir: Input directory containing source documents
        raise_http_exception: If False, return result dict instead of raising HTTPException

    Returns:
        Dictionary with consistent IndexResult format
    """
    index_progress.start_time = time.time()
    index_progress.status = "processing"

    try:
        indexer = _get_milvus_indexer()
        result = indexer.add_new_documents(input_dir=input_dir)

        index_progress.status = "complete"
        index_progress.processed_files = result.get("added", 0)
        index_progress.processed_chunks = result.get("chunks_added", 0)

        return {
            "success": True,
            "operation": "add",
            "message": f"Indexed {result.get('added', 0)} new files",
            "files_processed": result.get("added", 0),
            "chunks_indexed": result.get("chunks_added", 0),
            "chunks_total": result.get("chunks_added", 0),
            "processing_time_seconds": 0,
            "sources": result.get("sources", []),
            "errors": []
        }

    except Exception as e:
        index_progress.status = "error"
        index_progress.error_message = str(e)
        if raise_http_exception:
            raise HTTPException(status_code=500, detail=str(e))
        # For internal use, return error as dict instead of raising
        return {
            "success": False,
            "operation": "add",
            "message": str(e),
            "files_processed": 0,
            "chunks_indexed": 0,
            "chunks_total": 0,
            "processing_time_seconds": 0,
            "sources": [],
            "errors": [str(e)]
        }


def rebuild_index_full(input_dir: str = "./data/input") -> Dict[str, Any]:
    """
    Rebuild the entire Milvus index from all source documents.

    This is a FULL REBUILD - all previous index data is cleared
    and recreated from source files.

    Args:
        input_dir: Input directory containing source documents

    Returns:
        IndexResult with operation details
    """
    start_time = time.time()
    operation = "rebuild"

    print("=" * 80)
    print("REBUILDING MILVUS INDEX (Full Rebuild)")
    print("=" * 80)

    input_path = Path(input_dir)
    if not input_path.exists():
        return {
            "success": False,
            "operation": operation,
            "message": f"Input directory not found: {input_dir}",
            "files_processed": 0,
            "chunks_indexed": 0,
            "chunks_total": 0,
            "processing_time_seconds": time.time() - start_time,
            "sources": [],
            "errors": [f"Input directory not found: {input_dir}"]
        }

    try:
        # Initialize Milvus store with reset=True to clear existing data
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=True,  # Clear and recreate
        )

        # Create Milvus indexer - uses embedding_model string (MilvusIndexer initializes EmbeddingClient internally)
        indexer = MilvusIndexer(
            milvus_store=milvus_store,
            embedding_model="BAAI/bge-m3",
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )

        # Rebuild index from source directory
        chunk_count = indexer.rebuild(str(input_path))

        elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("MILVUS INDEX REBUILD COMPLETE")
        print("=" * 80)
        print(f"Chunks indexed: {chunk_count}")
        print(f"Processing time: {elapsed:.2f} seconds")
        print("=" * 80)

        return {
            "success": True,
            "operation": operation,
            "message": f"Milvus index rebuilt successfully with {chunk_count} chunks",
            "files_processed": 0,  # MilvusIndexer.rebuild doesn't return file count
            "chunks_indexed": chunk_count,
            "chunks_total": chunk_count,
            "processing_time_seconds": elapsed,
            "sources": [],
            "errors": []
        }

    except Exception as e:
        return {
            "success": False,
            "operation": operation,
            "message": f"Rebuild failed: {str(e)}",
            "files_processed": 0,
            "chunks_indexed": 0,
            "chunks_total": 0,
            "processing_time_seconds": time.time() - start_time,
            "sources": [],
            "errors": [str(e)]
        }


def verify_index() -> Dict[str, Any]:
    """
    Verify Milvus index integrity and return detailed statistics.

    Returns:
        Index verification results including counts and sources
    """
    try:
        milvus_store = MilvusStore(
            host=config.milvus_host,
            port=config.milvus_port,
            collection_name=config.milvus_collection,
            reset=False,
        )

        health = milvus_store.health_check()

        return {
            "success": health.get("healthy", False),
            "count": health.get("count", 0),
            "unique_sources": health.get("unique_sources", 0),
            "collection": config.milvus_collection,
            "message": "Milvus index verified" if health.get("healthy") else "Milvus index verification failed"
        }

    except Exception as e:
        return {
            "success": False,
            "count": 0,
            "unique_sources": 0,
            "collection": config.milvus_collection,
            "message": f"Verification failed: {str(e)}"
        }
