"""Semantic document chunking that respects content boundaries."""

import re
from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SemanticChunk:
    """A semantic chunk of text with metadata."""
    text: str
    metadata: Dict[str, Any]
    chunk_id: str


class SemanticChunker:
    """
    Chunk documents based on semantic boundaries rather than fixed sizes.

    This chunker respects:
    - Paragraph boundaries
    - Sentence boundaries within paragraphs
    - Section headers
    - Natural topic transitions
    """

    def __init__(
        self,
        min_chunk_size: int = 200,
        max_chunk_size: int = 1500,
        target_chunk_size: int = 800,
    ):
        """
        Initialize semantic chunker.

        Args:
            min_chunk_size: Minimum characters per chunk
            max_chunk_size: Maximum characters per chunk
            target_chunk_size: Target characters per chunk (soft limit)
        """
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.target_chunk_size = target_chunk_size

        # Pattern for detecting headers (various styles)
        self.header_pattern = re.compile(
            r'^(#{1,6}\s+|Chapter|Section|Part|I+\.|\d+\.|\d+\.\d+)\s+.*$',
            re.MULTILINE | re.IGNORECASE
        )

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs while preserving structure."""
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Split by double newlines (paragraph breaks)
        paragraphs = text.split('\n\n+')

        result = []
        for para in paragraphs:
            para = para.strip()
            if para:
                result.append(para)

        return result

    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """
        Split a long paragraph into smaller chunks at sentence boundaries.

        Args:
            paragraph: A paragraph that exceeds max_chunk_size

        Returns:
            List of chunks
        """
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-öø-ÿ])', paragraph)

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If sentence itself is too long, force split
            if len(sentence) > self.max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                # Split long sentence by phrases
                phrases = re.split(r'[,;:]\s+', sentence)
                temp_chunk = ""
                for phrase in phrases:
                    if len(temp_chunk) + len(phrase) + 2 > self.target_chunk_size and temp_chunk:
                        chunks.append(temp_chunk.strip())
                        temp_chunk = phrase
                    else:
                        temp_chunk += (", " if temp_chunk else "") + phrase
                if temp_chunk:
                    current_chunk = temp_chunk
            elif len(current_chunk) + len(sentence) + 1 > self.max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """Merge small chunks with neighbors to reach target size."""
        if not chunks:
            return []

        merged = []
        i = 0

        while i < len(chunks):
            current = chunks[i]

            # If current chunk is too small, try to merge with next
            while (len(current) < self.min_chunk_size and
                   i + 1 < len(chunks) and
                   len(current) + len(chunks[i + 1]) + 2 <= self.max_chunk_size):
                current += "\n\n" + chunks[i + 1]
                i += 1

            # If still too small, try merging with previous
            if len(current) < self.min_chunk_size and merged:
                merged[-1] += "\n\n" + current
            else:
                merged.append(current)

            i += 1

        return merged

    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None
    ) -> List[SemanticChunk]:
        """
        Chunk text into semantic units.

        Args:
            text: The text to chunk
            metadata: Optional metadata to attach to all chunks

        Returns:
            List of SemanticChunk objects
        """
        if metadata is None:
            metadata = {}

        # Clean text
        text = self._clean_text(text)

        # Split into paragraphs
        paragraphs = self._split_into_paragraphs(text)

        chunks = []
        for para in paragraphs:
            if len(para) <= self.max_chunk_size:
                chunks.append(para)
            else:
                # Split long paragraph
                chunks.extend(self._split_long_paragraph(para))

        # Merge small chunks
        merged_chunks = self._merge_small_chunks(chunks)

        # Create SemanticChunk objects
        result = []
        for i, chunk_text in enumerate(merged_chunks):
            chunk_id = metadata.get('chunk_id', f'chunk_{i}')
            chunk_metadata = metadata.copy()
            chunk_metadata['chunk_index'] = i
            chunk_metadata['chunk_total'] = len(merged_chunks)
            chunk_metadata['char_count'] = len(chunk_text)

            result.append(SemanticChunk(
                text=chunk_text,
                metadata=chunk_metadata,
                chunk_id=f"{chunk_id}_{i}"
            ))

        return result

    def _clean_text(self, text: str) -> str:
        """Clean text while preserving structure."""
        # Remove control characters but keep formatting
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

        # Normalize whitespace
        text = re.sub(r' +', ' ', text)  # Multiple spaces to single
        text = re.sub(r'\n{3,}', '\n\n', text)  # Multiple newlines to double

        return text.strip()

    def process_document(
        self,
        file_path: Path,
        text: str,
        page: int = None
    ) -> List[SemanticChunk]:
        """
        Process a document (or page) into semantic chunks.

        Args:
            file_path: Path to the source file
            text: Text content
            page: Page number (if applicable)

        Returns:
            List of SemanticChunk objects
        """
        metadata = {
            'source': file_path.name if isinstance(file_path, Path) else str(file_path),
            'page': page if page is not None else 1,
        }

        return self.chunk_text(text, metadata)


def create_semantic_chunker(
    min_size: int = 200,
    max_size: int = 1500,
    target_size: int = 800,
) -> SemanticChunker:
    """Factory function to create a semantic chunker."""
    return SemanticChunker(
        min_chunk_size=min_size,
        max_chunk_size=max_size,
        target_chunk_size=target_size,
    )
