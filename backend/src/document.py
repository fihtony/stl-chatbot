"""Document processing: parsing, chunking, and metadata extraction."""

import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Import semantic chunker
from .semantic_chunker import SemanticChunker

# Import summarizer (optional, only used when generate_summary=True)
try:
    from .llm_summarizer import LLMChunkSummarizer
    SUMMARIZER_AVAILABLE = True
except ImportError:
    SUMMARIZER_AVAILABLE = False


@dataclass
class DocumentChunk:
    """A chunk of document text with metadata."""

    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = hashlib.md5(
                f"{self.metadata.get('source', '')}-{self.metadata.get('page', 0)}-{self.text[:50]}".encode()
            ).hexdigest()[:12]


class DocumentProcessor:
    """Process documents: parse, chunk, and extract metadata."""

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
        use_semantic_chunking: bool = True,
        summarizer: Optional["LLMChunkSummarizer"] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_semantic_chunking = use_semantic_chunking
        self.summarizer = summarizer

        # Traditional splitter (fallback)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "。", " ", ""],
            length_function=len,
        )

        # Semantic chunker
        self.semantic_chunker = SemanticChunker(
            min_chunk_size=200,
            max_chunk_size=1500,
            target_chunk_size=800,
        )

    def parse_pdf(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Parse a PDF file and extract text with page numbers.

        Returns list of dicts with 'text' and 'page' keys.
        """
        pages = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text and text.strip():
                        # Clean up special characters and bullets
                        text = self._clean_text(text)
                        # Check text quality before adding
                        if self._is_text_quality_acceptable(text):
                            pages.append(
                                {"text": text.strip(), "page": i, "source": file_path.name}
                            )
        except Exception as e:
            raise RuntimeError(f"Failed to parse PDF {file_path}: {e}")

        return pages

    def _is_text_quality_acceptable(self, text: str) -> bool:
        """
        Check if text quality is acceptable for indexing.

        Filters out documents that are:
        - Mostly garbled/binary data
        - Too short after cleaning
        - Contain mostly image headers
        """
        import re

        if not text or len(text.strip()) < 50:
            return False

        # Check for image file headers (JFIF, PNG, etc.)
        image_signatures = [
            b'\xff\xd8\xff',  # JPEG
            b'\x89PNG',      # PNG
            b'GIF87a',      # GIF
            b'BM',          # BMP
        ]

        text_bytes = text[:100].encode('utf-8', errors='ignore')
        for sig in image_signatures:
            if sig in text_bytes:
                return False

        # Check for garbled character ratio
        # Count non-ASCII, non-punctuation characters
        garbled_pattern = re.compile(r'[^\x20-\x7E\u00A0-\u00FF\u4e00-\u9FFF\s]')
        garbled_count = len(garbled_pattern.findall(text))

        if len(text) > 0:
            garbled_ratio = garbled_count / len(text)
            if garbled_ratio > 0.3:  # More than 30% garbled
                return False

        # Check for meaningful content (at least some letters)
        meaningful_chars = re.findall(r'[A-Za-z\u4e00-\u9fff]', text)
        if len(meaningful_chars) < 20:
            return False

        return True

    def _clean_text(self, text: str) -> str:
        """Clean up text by removing/replacing problematic characters."""
        import re

        # Remove various bullet point characters and replace with dash
        bullet_chars = [
            "\u25a0",  # ◼ (filled square)
            "\u25a1",  # □ (empty square)
            "\u2022",  # • (bullet)
            "\u2023",  # ‣ (triangular bullet)
            "\u2043",  # ⁃ (hyphen bullet)
            "\u3000",  # ideographic space
        ]

        for bullet in bullet_chars:
            text = text.replace(bullet, "-")

        # Remove multiple spaces and newlines
        text = re.sub(r"\n\s*\n", "\n", text)  # Remove blank lines
        text = re.sub(r" +", " ", text)  # Remove multiple spaces

        # Remove control characters except tab and newline
        text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\n")

        return text

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks."""
        return self.splitter.split_text(text)

    def process_pdf(self, file_path: Path) -> List[DocumentChunk]:
        """
        Process a PDF file: parse and chunk.

        Returns list of DocumentChunk objects.
        """
        pages = self.parse_pdf(file_path)
        chunks = []

        for page_data in pages:
            page_chunks = self.chunk_text(page_data["text"])

            for idx, chunk_text in enumerate(page_chunks):
                chunk = DocumentChunk(
                    text=chunk_text,
                    metadata={
                        "source": page_data["source"],
                        "page": page_data["page"],
                        "chunk_index": idx,
                        "file_path": str(file_path),
                    },
                )
                chunks.append(chunk)

        return chunks

    def process_pdf_semantic(
        self,
        file_path: Path,
        generate_summary: bool = False
    ) -> List[DocumentChunk]:
        """
        Process a PDF file using semantic chunking.

        Args:
            file_path: Path to PDF file
            generate_summary: Whether to generate summaries and tags for chunks

        Returns list of DocumentChunk objects.
        """
        pages = self.parse_pdf(file_path)
        chunks = []

        for page_data in pages:
            # Use semantic chunker for this page
            semantic_chunks = self.semantic_chunker.process_document(
                file_path=file_path,
                text=page_data["text"],
                page=page_data["page"],
            )

            for sem_chunk in semantic_chunks:
                chunk = DocumentChunk(
                    text=sem_chunk.text,
                    metadata={
                        **sem_chunk.metadata,
                        "file_path": str(file_path),
                        "chunking_method": "semantic",
                    },
                )
                chunks.append(chunk)

        # Generate summaries if requested
        if generate_summary:
            chunks = asyncio.run(self._enrich_with_summary(chunks))

        return chunks

    def process_directory(self, dir_path: Path) -> List[DocumentChunk]:
        """
        Process all PDF files in a directory.

        Returns list of all DocumentChunk objects.
        """
        all_chunks = []
        pdf_files = list(dir_path.glob("*.pdf")) + list(dir_path.glob("*.PDF"))

        for pdf_file in pdf_files:
            chunks = self.process_pdf(pdf_file)
            all_chunks.extend(chunks)

        return all_chunks

    def parse_text_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Parse a text file and extract content.

        Returns list of dicts with 'text' and 'page' keys.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()

            if text and text.strip():
                text = self._clean_text(text)
                # Check text quality before accepting
                if self._is_text_quality_acceptable(text):
                    # For text files, treat entire content as page 1
                    return [{"text": text.strip(), "page": 1, "source": file_path.name}]
                else:
                    # Skip low-quality text files
                    return []
            return []
        except UnicodeDecodeError:
            # Try with latin-1 encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    text = f.read()

                if text and text.strip():
                    text = self._clean_text(text)
                    if self._is_text_quality_acceptable(text):
                        return [{"text": text.strip(), "page": 1, "source": file_path.name}]
                return []
            except Exception as e:
                raise RuntimeError(f"Failed to parse text file {file_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to parse text file {file_path}: {e}")

    def process_text_file(self, file_path: Path) -> List[DocumentChunk]:
        """
        Process a text file: parse and chunk.

        Returns list of DocumentChunk objects.
        """
        pages = self.parse_text_file(file_path)
        chunks = []

        for page_data in pages:
            page_chunks = self.chunk_text(page_data["text"])

            for idx, chunk_text in enumerate(page_chunks):
                chunk = DocumentChunk(
                    text=chunk_text,
                    metadata={
                        "source": page_data["source"],
                        "page": page_data["page"],
                        "chunk_index": idx,
                        "file_path": str(file_path),
                        "file_type": "text",
                    },
                )
                chunks.append(chunk)

        return chunks

    def process_text_file_semantic(self, file_path: Path) -> List[DocumentChunk]:
        """
        Process a text file using semantic chunking.

        Returns list of DocumentChunk objects.
        """
        pages = self.parse_text_file(file_path)
        chunks = []

        for page_data in pages:
            semantic_chunks = self.semantic_chunker.process_document(
                file_path=file_path,
                text=page_data["text"],
                page=page_data["page"],
            )

            for sem_chunk in semantic_chunks:
                chunk = DocumentChunk(
                    text=sem_chunk.text,
                    metadata={
                        **sem_chunk.metadata,
                        "file_path": str(file_path),
                        "file_type": "text",
                        "chunking_method": "semantic",
                    },
                )
                chunks.append(chunk)

        return chunks

    async def _enrich_with_summary(
        self,
        chunks: List[DocumentChunk]
    ) -> List[DocumentChunk]:
        """
        Enrich chunks with summaries and tags using LLM.

        Args:
            chunks: List of DocumentChunk objects to enrich

        Returns:
            List of DocumentChunk objects with summary and tags in metadata
        """
        if not SUMMARIZER_AVAILABLE:
            print("Warning: LLMChunkSummarizer not available, skipping summary generation")
            return chunks

        if self.summarizer is None:
            self.summarizer = LLMChunkSummarizer()

        enriched_chunks = []

        # Process chunks in batches
        batch_size = self.summarizer.batch_size
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            # Prepare contexts (previous chunk's tail for continuity)
            contexts = []
            for j in range(len(batch)):
                if i + j > 0:
                    prev_chunk = chunks[i + j - 1]
                    # Use last 200 characters of previous chunk as context
                    context = prev_chunk.text[-200:] if len(prev_chunk.text) > 200 else prev_chunk.text
                    contexts.append(context)
                else:
                    contexts.append(None)

            # Generate summaries and tags for the batch
            chunk_texts = [c.text for c in batch]
            summaries_and_tags = await self.summarizer.process_batch(chunk_texts, contexts)

            # Update chunks with summaries and tags
            for chunk, (summary, tags) in zip(batch, summaries_and_tags):
                chunk.metadata["summary"] = summary
                chunk.metadata["tags"] = str(tags)  # Store as string for ChromaDB compatibility
                enriched_chunks.append(chunk)

        return enriched_chunks

    def get_pdf_info(self, file_path: Path) -> Dict[str, Any]:
        """Get basic info about a PDF file."""
        try:
            with pdfplumber.open(file_path) as pdf:
                return {
                    "file": file_path.name,
                    "pages": len(pdf.pages),
                    "path": str(file_path),
                }
        except Exception as e:
            return {
                "file": file_path.name,
                "error": str(e),
                "path": str(file_path),
            }

    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get basic info about any supported file."""
        suffix = file_path.suffix.lower()
        if suffix in ['.pdf', '.PDF']:
            return self.get_pdf_info(file_path)
        elif suffix in ['.txt', '.text']:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                return {
                    "file": file_path.name,
                    "pages": 1,
                    "path": str(file_path),
                    "size": len(text),
                }
            except Exception as e:
                return {
                    "file": file_path.name,
                    "error": str(e),
                    "path": str(file_path),
                }
        else:
            return {
                "file": file_path.name,
                "error": f"Unsupported file type: {suffix}",
                "path": str(file_path),
            }

    def process_directory_with_text(self, dir_path: Path, recursive: bool = False) -> List[DocumentChunk]:
        """
        Process all PDF and text files in a directory.

        Args:
            dir_path: Path to directory
            recursive: Whether to process subdirectories recursively

        Returns list of all DocumentChunk objects.
        """
        all_chunks = []

        # Get all files based on recursive flag
        if recursive:
            pdf_files = list(dir_path.rglob("*.pdf")) + list(dir_path.rglob("*.PDF"))
            txt_files = list(dir_path.rglob("*.txt")) + list(dir_path.rglob("*.text"))
        else:
            pdf_files = list(dir_path.glob("*.pdf")) + list(dir_path.glob("*.PDF"))
            txt_files = list(dir_path.glob("*.txt")) + list(dir_path.glob("*.text"))

        # Process PDF files
        for pdf_file in pdf_files:
            try:
                chunks = self.process_pdf(pdf_file)
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"  Warning: Failed to process {pdf_file.name}: {e}")

        # Process text files
        for txt_file in txt_files:
            try:
                chunks = self.process_text_file(txt_file)
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"  Warning: Failed to process {txt_file.name}: {e}")

        return all_chunks
