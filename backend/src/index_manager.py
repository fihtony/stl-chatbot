#!/usr/bin/env python3
"""Unified Index Manager for RAG system.

This module provides a consistent interface for all index operations:
- Full rebuild from all source documents
- Incremental updates for new documents
- Index verification and statistics

All operations follow the same process and produce consistent output format.
"""

import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class IndexResult:
    """Consistent output format for all index operations."""
    success: bool
    operation: str  # "rebuild", "add", "verify"
    message: str
    files_processed: int
    chunks_indexed: int
    chunks_total: int
    processing_time_seconds: float
    sources: List[str]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IndexManager:
    """Unified index manager with consistent operations."""

    def __init__(self, cache_dir: str = "./data", db_path: str = "./data/chroma_db"):
        """
        Initialize index manager.

        Args:
            cache_dir: Directory for index cache files
            db_path: Path to ChromaDB vector store
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path

        # Import here to avoid circular imports
        from .document import DocumentProcessor
        from .embedding import EmbeddingClient
        from .vectorstore import VectorStore
        from .hybrid_retriever import HybridRetriever

        self.document_processor = DocumentProcessor()
        self.embedding_client = EmbeddingClient()
        self.vector_store = VectorStore(db_path=db_path)
        self.hybrid_retriever = HybridRetriever(cache_dir=cache_dir)

    def _get_source_files(self, input_dir: Path) -> Tuple[List[Path], List[Path]]:
        """
        Get all source files to be indexed.

        Args:
            input_dir: Input directory path

        Returns:
            Tuple of (pdf_files, text_files)
        """
        pdf_files = []
        text_files = []

        # PDFs in scraped/pdfs
        pdfs_dir = input_dir / "scraped" / "pdfs"
        if pdfs_dir.exists():
            pdf_files.extend(sorted(pdfs_dir.glob("*.pdf")))

        # Text files in scraped/pages
        pages_dir = input_dir / "scraped" / "pages"
        if pages_dir.exists():
            text_files.extend(sorted(pages_dir.glob("*.txt")))

        # PDFs in input root
        if input_dir.exists():
            pdf_files.extend(sorted(input_dir.glob("*.pdf")))

        # Remove duplicates (files that appear in multiple locations)
        seen = set()
        unique_pdfs = []
        for f in pdf_files:
            key = (f.name, f.stat().st_size)
            if key not in seen:
                seen.add(key)
                unique_pdfs.append(f)

        return unique_pdfs, text_files

    def _get_existing_chunk_ids(self) -> set:
        """Get set of existing chunk_ids to detect duplicates."""
        existing_ids = set()
        for doc in self.hybrid_retriever.documents:
            chunk_id = doc.get("metadata", {}).get("chunk_id", "")
            if chunk_id:
                existing_ids.add(chunk_id)
        return existing_ids

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute hash of file for identification."""
        return hashlib.md5(str(file_path.resolve()).encode('utf-8')).hexdigest()[:12]

    def _is_file_indexed(self, file_path: Path, existing_ids: set) -> bool:
        """Check if file is already indexed."""
        file_hash = self._compute_file_hash(file_path)

        if file_path.suffix == ".pdf":
            # Check for any chunk from this PDF (assuming max 100 pages)
            expected_chunk_ids = {f"{file_hash}_{i}" for i in range(100)}
            return any(cid in existing_ids for cid in expected_chunk_ids)
        else:
            # Text file has single chunk
            expected_chunk_id = f"{file_hash}_0"
            return expected_chunk_id in existing_ids

    def _process_files(
        self,
        pdf_files: List[Path],
        text_files: List[Path],
        skip_indexed: bool = False
    ) -> Tuple[List[Any], List[str], List[str], int]:
        """
        Process files into chunks.

        Args:
            pdf_files: List of PDF files
            text_files: List of text files
            skip_indexed: Skip files that are already indexed

        Returns:
            Tuple of (chunks, sources, errors, total_files)
        """
        chunks = []
        sources = []
        errors = []
        total_files = 0

        existing_ids = self._get_existing_chunk_ids() if skip_indexed else set()

        # Process PDFs
        for pdf_file in pdf_files:
            total_files += 1
            if skip_indexed and self._is_file_indexed(pdf_file, existing_ids):
                continue

            try:
                file_chunks = self.document_processor.process_pdf_semantic(
                    pdf_file, generate_summary=False
                )
                chunks.extend(file_chunks)
                sources.append(str(pdf_file.relative_to(self.cache_dir.parent)))
            except Exception as e:
                errors.append(f"PDF {pdf_file.name}: {e}")

        # Process text files
        for txt_file in text_files:
            total_files += 1
            if skip_indexed and self._is_file_indexed(txt_file, existing_ids):
                continue

            try:
                file_chunks = self.document_processor.process_text_file_semantic(txt_file)
                chunks.extend(file_chunks)
                sources.append(str(txt_file.relative_to(self.cache_dir.parent)))
            except Exception as e:
                errors.append(f"TXT {txt_file.name}: {e}")

        return chunks, sources, errors, total_files

    def _index_chunks(self, chunks: List[Any], embeddings, operation: str) -> int:
        """
        Index chunks using hybrid retriever and vector store.

        Args:
            chunks: List of document chunks
            embeddings: Embeddings for chunks
            operation: "rebuild" or "add"

        Returns:
            Number of chunks indexed
        """
        # Prepare documents
        documents = [
            {"content": chunk.text, "metadata": chunk.metadata}
            for chunk in chunks
        ]

        if operation == "rebuild":
            # Clear and recreate index
            self.hybrid_retriever.clear()
            self.hybrid_retriever.index_documents(documents, embeddings)

            # Clear and recreate vector store with reset
            from src.vectorstore import VectorStore
            self.vector_store = VectorStore(db_path=self.db_path, reset=True)
        else:
            # Add to existing index
            self.hybrid_retriever.add_documents(documents, embeddings)

            # Save the updated hybrid index to disk
            self.hybrid_retriever.save()

        # Add to vector store (handles errors gracefully)
        added = self.vector_store.add_chunks(chunks, embeddings)

        return added

    def rebuild_index(self, input_dir: str = "./data/input") -> IndexResult:
        """
        Rebuild the entire index from all source documents.

        This is a complete rebuild - all previous index data is cleared
        and recreated from source files.

        Args:
            input_dir: Input directory containing source documents

        Returns:
            IndexResult with operation details
        """
        start_time = time.time()
        operation = "rebuild"

        print("=" * 80)
        print("REBUILDING INDEX (Full Rebuild)")
        print("=" * 80)

        input_path = Path(input_dir)
        if not input_path.exists():
            return IndexResult(
                success=False,
                operation=operation,
                message=f"Input directory not found: {input_dir}",
                files_processed=0,
                chunks_indexed=0,
                chunks_total=0,
                processing_time_seconds=time.time() - start_time,
                sources=[],
                errors=[f"Input directory not found: {input_dir}"]
            )

        # Get all source files
        print(f"\nScanning {input_dir} for documents...")
        pdf_files, text_files = self._get_source_files(input_path)
        print(f"Found {len(pdf_files)} PDF files and {len(text_files)} text files")

        # Process files
        print(f"\nProcessing documents...")
        chunks, sources, errors, total_files = self._process_files(
            pdf_files, text_files, skip_indexed=False
        )

        if not chunks:
            return IndexResult(
                success=False,
                operation=operation,
                message="No chunks created from documents",
                files_processed=total_files,
                chunks_indexed=0,
                chunks_total=0,
                processing_time_seconds=time.time() - start_time,
                sources=[],
                errors=errors
            )

        print(f"Created {len(chunks)} chunks from {len(sources)} files")

        # Generate embeddings
        print(f"\nGenerating embeddings...")
        embeddings = self.embedding_client.embed_texts([chunk.text for chunk in chunks])
        print(f"Embeddings shape: {embeddings.shape}")

        # Index chunks
        print(f"\nIndexing chunks...")
        chunks_indexed = self._index_chunks(chunks, embeddings, operation)

        elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("REBUILD COMPLETE")
        print(f"Files processed: {len(sources)}")
        print(f"Chunks indexed: {chunks_indexed}")
        print(f"Processing time: {elapsed:.2f} seconds")
        print("=" * 80)

        return IndexResult(
            success=True,
            operation=operation,
            message=f"Rebuild complete: {chunks_indexed} chunks from {len(sources)} files",
            files_processed=len(sources),
            chunks_indexed=chunks_indexed,
            chunks_total=chunks_indexed,
            processing_time_seconds=elapsed,
            sources=sources,
            errors=errors
        )

    def add_documents(
        self,
        file_paths: List[str],
        input_dir: str = "./data/input"
    ) -> IndexResult:
        """
        Add specific documents to the index.

        Only processes files that are not already indexed.

        Args:
            file_paths: List of file paths to add
            input_dir: Base input directory

        Returns:
            IndexResult with operation details
        """
        start_time = time.time()
        operation = "add"

        print("=" * 80)
        print(f"ADDING DOCUMENTS ({len(file_paths)} files)")
        print("=" * 80)

        # Filter files by type
        pdf_files = []
        text_files = []
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                continue
            if path.suffix == ".pdf":
                pdf_files.append(path)
            elif path.suffix == ".txt":
                text_files.append(path)

        print(f"Found {len(pdf_files)} PDFs and {len(text_files)} text files")

        # Process only new files (skip already indexed)
        chunks, sources, errors, total_files = self._process_files(
            pdf_files, text_files, skip_indexed=True
        )

        if not chunks:
            return IndexResult(
                success=True,
                operation=operation,
                message="No new documents to add (all already indexed)",
                files_processed=0,
                chunks_indexed=0,
                chunks_total=self.hybrid_retriever.count(),
                processing_time_seconds=time.time() - start_time,
                sources=[],
                errors=errors
            )

        print(f"Processing {len(chunks)} chunks from {len(sources)} new files")

        # Generate embeddings
        print("Generating embeddings...")
        embeddings = self.embedding_client.embed_texts([chunk.text for chunk in chunks])

        # Add to index
        print("Adding to index...")
        chunks_indexed = self._index_chunks(chunks, embeddings, operation)

        elapsed = time.time() - start_time
        total_chunks = self.hybrid_retriever.count()

        print("\n" + "=" * 80)
        print("ADD COMPLETE")
        print(f"New files: {len(sources)}")
        print(f"New chunks: {chunks_indexed}")
        print(f"Total chunks: {total_chunks}")
        print("=" * 80)

        return IndexResult(
            success=True,
            operation=operation,
            message=f"Added {chunks_indexed} chunks from {len(sources)} files",
            files_processed=len(sources),
            chunks_indexed=chunks_indexed,
            chunks_total=total_chunks,
            processing_time_seconds=elapsed,
            sources=sources,
            errors=errors
        )

    def add_new_documents(self, input_dir: str = "./data/input") -> IndexResult:
        """
        Automatically find and add only new (unindexed) documents.

        Args:
            input_dir: Input directory containing source documents

        Returns:
            IndexResult with operation details
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            return IndexResult(
                success=False,
                operation="add",
                message=f"Input directory not found: {input_dir}",
                files_processed=0,
                chunks_indexed=0,
                chunks_total=self.hybrid_retriever.count(),
                processing_time_seconds=0,
                sources=[],
                errors=[f"Input directory not found: {input_dir}"]
            )

        # Get all source files
        pdf_files, text_files = self._get_source_files(input_path)

        # Filter to only new files
        existing_ids = self._get_existing_chunk_ids()
        new_pdfs = [f for f in pdf_files if not self._is_file_indexed(f, existing_ids)]
        new_txts = [f for f in text_files if not self._is_file_indexed(f, existing_ids)]

        new_files = [str(f) for f in new_pdfs + new_txts]

        if not new_files:
            return IndexResult(
                success=True,
                operation="add",
                message="No new documents to add",
                files_processed=0,
                chunks_indexed=0,
                chunks_total=self.hybrid_retriever.count(),
                processing_time_seconds=0,
                sources=[],
                errors=[]
            )

        return self.add_documents(new_files, input_dir)

    def verify_index(self) -> IndexResult:
        """
        Verify index integrity and return statistics.

        Returns:
            IndexResult with verification details
        """
        start_time = time.time()
        operation = "verify"

        print("=" * 80)
        print("VERIFYING INDEX")
        print("=" * 80)

        # Get counts
        hybrid_count = self.hybrid_retriever.count()
        vector_count = self.vector_store.count()

        # Get unique sources
        sources = set()
        for doc in self.hybrid_retriever.documents:
            source = doc.get("metadata", {}).get("source", "")
            if source:
                sources.add(source)

        # Check for issues
        errors = []
        if hybrid_count != vector_count:
            errors.append(f"Count mismatch: Hybrid={hybrid_count}, Vector={vector_count}")

        elapsed = time.time() - start_time

        print(f"\nHybrid retriever documents: {hybrid_count}")
        print(f"Vector store documents: {vector_count}")
        print(f"Unique sources: {len(sources)}")

        if errors:
            print(f"\nErrors found: {len(errors)}")
            for error in errors:
                print(f"  - {error}")
        else:
            print("\n✅ Index verification PASSED")

        print("=" * 80)

        return IndexResult(
            success=len(errors) == 0,
            operation=operation,
            message=f"Verification complete: {hybrid_count} chunks, {len(sources)} sources",
            files_processed=len(sources),
            chunks_indexed=hybrid_count,
            chunks_total=hybrid_count,
            processing_time_seconds=elapsed,
            sources=sorted(list(sources)),
            errors=errors
        )


# Convenience functions for external use
def rebuild_index(input_dir: str = "./data/input") -> IndexResult:
    """Convenience function to rebuild the entire index."""
    manager = IndexManager()
    return manager.rebuild_index(input_dir)


def add_documents(file_paths: List[str]) -> IndexResult:
    """Convenience function to add specific documents."""
    manager = IndexManager()
    return manager.add_documents(file_paths)


def add_new_documents(input_dir: str = "./data/input") -> IndexResult:
    """Convenience function to add new documents automatically."""
    manager = IndexManager()
    return manager.add_new_documents(input_dir)


def verify_index() -> IndexResult:
    """Convenience function to verify the index."""
    manager = IndexManager()
    return manager.verify_index()
