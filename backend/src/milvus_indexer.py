"""Milvus 索引构建器 - 从源文档构建 Milvus 向量索引。

本模块提供:
- MilvusIndexer: 重建 Milvus 索引的主类
- DocumentProcessor: PDF 和文本文件处理
- 使用 BGE-M3 嵌入模型
"""

import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import pdfplumber
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .document_registry import DocumentRegistry
from .date_utils import extract_date_from_filename


@dataclass
class DocumentChunk:
    """文档块数据结构。"""

    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""

    def __post_init__(self):
        if not self.chunk_id:
            # 使用文件路径、页码和文本内容生成唯一 ID
            source = self.metadata.get("source", "")
            page = self.metadata.get("page", 0)
            content = self.text[:50]
            self.chunk_id = hashlib.md5(
                f"{source}-{page}-{content}".encode('utf-8')
            ).hexdigest()[:12]


class DocumentProcessor:
    """文档处理器 - 解析 PDF 和文本文件并进行分块。"""

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
    ):
        """初始化文档处理器。

        Args:
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # 使用递归字符分割器
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "。", " ", ""],
            length_function=len,
        )

    def _clean_text(self, text: str) -> str:
        """清理文本，移除特殊字符和多余空白。"""
        import re

        # 移除项目符号字符并替换为短横线
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

        # 移除多余空格和换行
        text = re.sub(r"\n\s*\n", "\n", text)
        text = re.sub(r" +", " ", text)

        # 移除控制字符（除了 tab 和换行）
        text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\n")

        return text

    def _is_text_quality_acceptable(self, text: str) -> bool:
        """检查文本质量是否可接受。

        过滤掉:
        - 大部分乱码/二进制数据
        - 清理后太短的文本
        - 主要包含图像头的文档
        """
        import re

        if not text or len(text.strip()) < 50:
            return False

        # 检查图像文件签名
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

        # 检查乱码字符比例
        garbled_pattern = re.compile(r'[^\x20-\x7E\u00A0-\u00FF\u4e00-\u9FFF\s]')
        garbled_count = len(garbled_pattern.findall(text))

        if len(text) > 0:
            garbled_ratio = garbled_count / len(text)
            if garbled_ratio > 0.3:  # 超过 30% 乱码
                return False

        # 检查有意义的内容
        meaningful_chars = re.findall(r'[A-Za-z\u4e00-\u9fff]', text)
        if len(meaningful_chars) < 20:
            return False

        return True

    def parse_pdf(self, file_path: Path) -> List[Dict[str, Any]]:
        """解析 PDF 文件并提取带页码的文本。

        Returns:
            包含 'text' 和 'page' 键的字典列表
        """
        pages = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text and text.strip():
                        text = self._clean_text(text)
                        if self._is_text_quality_acceptable(text):
                            pages.append({
                                "text": text.strip(),
                                "page": i,
                                "source": file_path.name
                            })
        except Exception as e:
            raise RuntimeError(f"解析 PDF 失败 {file_path}: {e}")

        return pages

    def parse_text_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """解析文本文件并提取内容。

        Returns:
            包含 'text' 和 'page' 键的字典列表
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()

            if text and text.strip():
                text = self._clean_text(text)
                if self._is_text_quality_acceptable(text):
                    return [{"text": text.strip(), "page": 1, "source": file_path.name}]
                else:
                    return []
            return []
        except UnicodeDecodeError:
            # 尝试使用 latin-1 编码
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    text = f.read()

                if text and text.strip():
                    text = self._clean_text(text)
                    if self._is_text_quality_acceptable(text):
                        return [{"text": text.strip(), "page": 1, "source": file_path.name}]
                return []
            except Exception as e:
                raise RuntimeError(f"解析文本文件失败 {file_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"解析文本文件失败 {file_path}: {e}")

    def _chunk_document_pages(
        self,
        pages: List[Dict[str, Any]],
        file_path: Path,
    ) -> List[DocumentChunk]:
        """对文档页面进行分块。

        Args:
            pages: 页面列表
            file_path: 文件路径

        Returns:
            DocumentChunk 对象列表
        """
        chunks = []

        # 提取文档日期
        date_str = ""
        date_info = extract_date_from_filename(file_path.name)
        if date_info:
            date_obj, date_desc = date_info
            # 格式化为 YYYY-MM
            date_str = date_obj.strftime("%Y-%m")

        for page_data in pages:
            page_chunks = self.splitter.split_text(page_data["text"])

            for idx, chunk_text in enumerate(page_chunks):
                chunk = DocumentChunk(
                    text=chunk_text,
                    metadata={
                        "source": page_data["source"],
                        "page": page_data["page"],
                        "chunk_index": idx,
                        "file_path": str(file_path),
                        "date": date_str,
                    },
                )
                chunks.append(chunk)

        return chunks


class MilvusIndexer:
    """Milvus 索引构建器 - 重建 Milvus 向量索引。"""

    def __init__(
        self,
        milvus_store,
        embedding_model: str = "BAAI/bge-m3",
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
    ):
        """初始化 Milvus 索引构建器。

        Args:
            milvus_store: MilvusStore 实例
            embedding_model: 嵌入模型名称
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
        """
        self.milvus_store = milvus_store
        self.embedding_model_name = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # 初始化文档处理器
        self.document_processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # 延迟加载嵌入模型
        self._embedding_model = None

    @property
    def embedding_model(self):
        """延迟加载嵌入模型。"""
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            print(f"正在加载嵌入模型: {self.embedding_model_name}")
            self._embedding_model = SentenceTransformer(self.embedding_model_name)
            print(f"✅ 已加载嵌入模型: {self.embedding_model_name}")
            print(f"   嵌入维度: {self._embedding_model.get_sentence_embedding_dimension()}")

        return self._embedding_model

    def _load_documents(self, input_dir: Path) -> Tuple[List[Path], List[Path]]:
        """Load document files from input directory.

        Supports multiple layouts:
        - Crawler output: input_dir/pages/*.txt, input_dir/documents/*.pdf
        - Legacy: input_dir/scraped/pages/*.txt, input_dir/scraped/pdfs/*.pdf
        - Flat: input_dir/*.pdf, input_dir/*.txt

        Args:
            input_dir: Root input directory path

        Returns:
            Tuple of (list of PDF paths, list of text file paths)
        """
        pdf_files = []
        text_files = []

        # Crawler layout: pages/ (txt) and documents/ (pdf) under output_dir
        crawler_pages = input_dir / "pages"
        crawler_docs = input_dir / "documents"
        if crawler_pages.exists():
            text_files.extend(sorted(crawler_pages.glob("*.txt")))
        if crawler_docs.exists():
            pdf_files.extend(sorted(crawler_docs.glob("*.pdf")))

        # Legacy: scraped/pdfs and scraped/pages
        pdfs_dir = input_dir / "scraped" / "pdfs"
        if pdfs_dir.exists():
            pdf_files.extend(sorted(pdfs_dir.glob("*.pdf")))
        pages_dir = input_dir / "scraped" / "pages"
        if pages_dir.exists():
            text_files.extend(sorted(pages_dir.glob("*.txt")))

        # Flat: root-level PDFs and txt
        if input_dir.exists():
            pdf_files.extend(sorted(input_dir.glob("*.pdf")))
            text_files.extend(sorted(input_dir.glob("*.txt")))

        # 去重
        seen = set()
        unique_pdfs = []
        for f in pdf_files:
            key = (f.name, f.stat().st_size)
            if key not in seen:
                seen.add(key)
                unique_pdfs.append(f)

        # 文本文件去重
        seen_txt = set()
        unique_txts = []
        for f in text_files:
            key = (f.name, f.stat().st_size)
            if key not in seen_txt:
                seen_txt.add(key)
                unique_txts.append(f)

        return unique_pdfs, unique_txts

    def _chunk_document(
        self,
        file_path: Path,
        file_type: str,
    ) -> List[DocumentChunk]:
        """对单个文档进行分块。

        Args:
            file_path: 文件路径
            file_type: 文件类型 ('pdf' 或 'text')

        Returns:
            DocumentChunk 对象列表
        """
        if file_type == "pdf":
            pages = self.document_processor.parse_pdf(file_path)
        else:
            pages = self.document_processor.parse_text_file(file_path)

        return self.document_processor._chunk_document_pages(pages, file_path)

    def _insert_chunks(
        self,
        chunks: List[DocumentChunk],
        embeddings: np.ndarray,
    ) -> int:
        """将文档块插入 Milvus。

        Args:
            chunks: DocumentChunk 对象列表
            embeddings: 嵌入向量数组

        Returns:
            插入的文档块数量
        """
        if not chunks:
            return 0

        # 准备数据
        ids = [chunk.chunk_id for chunk in chunks]
        contents = [chunk.text for chunk in chunks]
        sources = [chunk.metadata.get("source", "") for chunk in chunks]
        pages = [chunk.metadata.get("page", 0) for chunk in chunks]
        chunk_indices = [chunk.metadata.get("chunk_index", 0) for chunk in chunks]
        dates = [chunk.metadata.get("date", "") for chunk in chunks]

        # 插入到 Milvus
        inserted = self.milvus_store.insert(
            ids=ids,
            embeddings=embeddings,
            contents=contents,
            sources=sources,
            pages=pages,
            chunk_indices=chunk_indices,
            dates=dates,
        )

        return inserted

    def rebuild(
        self,
        input_dir: str = "./data/input",
    ) -> int:
        """从源文档重建 Milvus 索引。

        Args:
            input_dir: 输入目录路径

        Returns:
            构建的文档块数量
        """
        start_time = time.time()

        print("=" * 80)
        print("重建 Milvus 索引")
        print("=" * 80)

        input_path = Path(input_dir)
        if not input_path.exists():
            print(f"错误: 输入目录不存在: {input_dir}")
            return 0

        # 加载文档
        print(f"\n扫描 {input_dir} 中的文档...")
        pdf_files, text_files = self._load_documents(input_path)
        print(f"找到 {len(pdf_files)} 个 PDF 文件和 {len(text_files)} 个文本文件")

        if not pdf_files and not text_files:
            print("警告: 没有找到任何文档")
            return 0

        # 处理所有文档
        all_chunks = []
        all_sources = []

        # 处理 PDF 文件
        for pdf_file in pdf_files:
            print(f"处理 PDF: {pdf_file.name}")
            try:
                chunks = self._chunk_document(pdf_file, "pdf")
                all_chunks.extend(chunks)
                all_sources.append(str(pdf_file))
                print(f"  生成 {len(chunks)} 个块")
            except Exception as e:
                print(f"  错误: {e}")

        # 处理文本文件
        for txt_file in text_files:
            print(f"处理文本: {txt_file.name}")
            try:
                chunks = self._chunk_document(txt_file, "text")
                all_chunks.extend(chunks)
                all_sources.append(str(txt_file))
                print(f"  生成 {len(chunks)} 个块")
            except Exception as e:
                print(f"  错误: {e}")

        if not all_chunks:
            print("警告: 没有生成任何文档块")
            return 0

        print(f"\n总共生成 {len(all_chunks)} 个文档块")

        # 生成嵌入
        print(f"\n生成嵌入向量...")
        texts = [chunk.text for chunk in all_chunks]
        embeddings = self.embedding_model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        print(f"嵌入形状: {embeddings.shape}")

        # 插入到 Milvus
        print(f"\n插入文档块到 Milvus...")
        inserted = self._insert_chunks(all_chunks, embeddings)

        elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("重建完成")
        print(f"处理的文件: {len(all_sources)}")
        print(f"索引的块: {inserted}")
        print(f"处理时间: {elapsed:.2f} 秒")
        print("=" * 80)

        return inserted

    def add_new_documents(
        self,
        input_dir: str = "./data/input",
    ) -> Dict[str, int]:
        """增量添加新文档到 Milvus 索引。

        使用 DocumentRegistry 检查哪些文档需要索引，
        只添加新的或已修改的文档。

        Args:
            input_dir: 输入目录路径

        Returns:
            包含统计信息的字典:
            - added: 添加的文档数
            - chunks_added: 添加的文档块数
            - skipped: 跳过的已索引文档数
        """
        start_time = time.time()

        print("=" * 80)
        print("增量添加文档到 Milvus")
        print("=" * 80)

        input_path = Path(input_dir)
        if not input_path.exists():
            print(f"错误: 输入目录不存在: {input_dir}")
            return {"added": 0, "chunks_added": 0, "skipped": 0}

        # 初始化文档注册表
        registry = DocumentRegistry()

        # 加载所有文档
        print(f"\n扫描 {input_dir} 中的文档...")
        pdf_files, text_files = self._load_documents(input_path)
        print(f"找到 {len(pdf_files)} 个 PDF 文件和 {len(text_files)} 个文本文件")

        all_files = [(f, "pdf") for f in pdf_files] + [(f, "text") for f in text_files]

        if not all_files:
            print("警告: 没有找到任何文档")
            return {"added": 0, "chunks_added": 0, "skipped": 0}

        # 筛选出需要索引的文档（新文档或已修改的文档）
        files_to_index = []
        skipped = 0

        for file_path, file_type in all_files:
            file_str = str(file_path.resolve())
            if not registry.is_indexed(file_str):
                files_to_index.append((file_path, file_type))
            else:
                skipped += 1

        print(f"需要索引: {len(files_to_index)} 个文档")
        print(f"已跳过: {skipped} 个已索引文档")

        if not files_to_index:
            print("没有新文档需要索引")
            return {"added": 0, "chunks_added": 0, "skipped": skipped}

        # 处理需要索引的文档
        all_chunks = []
        processed_files = []

        for file_path, file_type in files_to_index:
            print(f"处理 {'PDF' if file_type == 'pdf' else '文本'}: {file_path.name}")
            try:
                chunks = self._chunk_document(file_path, file_type)
                all_chunks.extend(chunks)
                processed_files.append(str(file_path))
                print(f"  生成 {len(chunks)} 个块")
            except Exception as e:
                print(f"  错误: {e}")

        if not all_chunks:
            print("警告: 没有生成任何文档块")
            return {"added": 0, "chunks_added": 0, "skipped": skipped}

        print(f"\n总共生成 {len(all_chunks)} 个文档块")

        # 生成嵌入
        print(f"\n生成嵌入向量...")
        texts = [chunk.text for chunk in all_chunks]
        embeddings = self.embedding_model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        print(f"嵌入形状: {embeddings.shape}")

        # 插入到 Milvus
        print(f"\n插入文档块到 Milvus...")
        inserted = self._insert_chunks(all_chunks, embeddings)

        # 标记文档为已索引
        print(f"\n更新文档注册表...")
        for file_path in processed_files:
            file_str = str(Path(file_path).resolve())
            registry.mark_indexed(
                file_str,
                metadata={
                    "file_name": Path(file_path).name,
                },
            )

        elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("增量索引完成")
        print(f"处理的文件: {len(processed_files)}")
        print(f"索引的块: {inserted}")
        print(f"跳过的文件: {skipped}")
        print(f"处理时间: {elapsed:.2f} 秒")
        print("=" * 80)

        return {
            "added": len(processed_files),
            "chunks_added": inserted,
            "skipped": skipped,
        }
