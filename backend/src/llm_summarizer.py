"""LLM-based chunk summarizer for generating summaries and tags."""

import asyncio
import re
import logging
from typing import List, Tuple, Optional, Dict, Any
from collections import Counter

from .zhipuai_llm import ZhipuAIClient

logger = logging.getLogger(__name__)


class LLMChunkSummarizer:
    """
    Generate summaries and tags for document chunks using LLM.

    Features:
    - Generate 100-200 character summaries
    - Extract 5-10 relevant tags
    - Batch processing for efficiency
    - Fallback strategy when LLM fails
    - Retry mechanism with exponential backoff
    """

    SUMMARY_MIN_LENGTH = 50
    SUMMARY_MAX_LENGTH = 200
    TAGS_MIN_COUNT = 3
    TAGS_MAX_COUNT = 10
    DEFAULT_BATCH_SIZE = 5
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        llm_client: Optional[ZhipuAIClient] = None,
        model: str = "GLM-4.7",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        """
        Initialize the summarizer.

        Args:
            llm_client: ZhipuAI client instance (creates new one if None)
            model: Model name to use for generation
            batch_size: Number of chunks to process in each batch
        """
        self.llm_client = llm_client or ZhipuAIClient(model=model)
        self.model = model
        self.batch_size = batch_size

    async def generate_summary_and_tags(
        self,
        chunk: str,
        context: Optional[str] = None
    ) -> Tuple[str, List[str]]:
        """
        Generate summary and tags for a single chunk.

        Args:
            chunk: The chunk text content
            context: Optional context from previous chunk (last 200 chars)

        Returns:
            Tuple of (summary, tags)

        Raises:
            RuntimeError: If all retries fail
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                prompt = self._build_prompt(chunk, context)
                result = self.llm_client.chat(
                    prompt=prompt,
                    temperature=0.3,  # Lower temperature for more consistent output
                )

                if result["success"]:
                    summary, tags = self._parse_response(result["response"])
                    return summary, tags
                else:
                    logger.warning(f"LLM call failed: {result['error']}")

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

            # Exponential backoff before retry
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(self.RETRY_DELAY * (2 ** attempt))

        # All retries failed, use fallback strategy
        logger.warning("LLM generation failed, using fallback strategy")
        return self._fallback_summary(chunk)

    async def process_batch(
        self,
        chunks: List[str],
        contexts: Optional[List[Optional[str]]] = None
    ) -> List[Tuple[str, List[str]]]:
        """
        Process multiple chunks in batches for efficiency.

        Args:
            chunks: List of chunk texts
            contexts: Optional list of contexts for each chunk

        Returns:
            List of (summary, tags) tuples for each chunk
        """
        if contexts is None:
            contexts = [None] * len(chunks)

        results = []

        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch_chunks = chunks[i:i + self.batch_size]
            batch_contexts = contexts[i:i + self.batch_size]

            # Process batch concurrently
            batch_tasks = [
                self.generate_summary_and_tags(chunk, ctx)
                for chunk, ctx in zip(batch_chunks, batch_contexts)
            ]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Handle any exceptions in batch results
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.warning(f"Chunk {i + j} failed: {result}")
                    results.append(self._fallback_summary(batch_chunks[j]))
                else:
                    results.append(result)

        return results

    def _build_prompt(self, chunk: str, context: Optional[str]) -> str:
        """Build the prompt for LLM."""
        context_section = f"上下文：{context}\n\n" if context else ""

        # Truncate chunk if too long (keep within reasonable limits)
        max_chunk_length = 2000
        truncated_chunk = chunk[:max_chunk_length]
        if len(chunk) > max_chunk_length:
            truncated_chunk += "..."

        return f"""请为以下文本片段生成摘要和关键词标签。

{context_section}文本片段：
{truncated_chunk}

请按以下格式输出：
摘要：[50-200字的简洁摘要，概括核心内容]
标签：[3-10个关键词标签，用逗号分隔]

要求：
- 摘要要精炼，保留关键信息
- 标签要能用于检索和过滤
- 如果是技术文档，包含技术术语
- 如果是叙述性文本，包含主题和类别
- 标签包括：核心概念、实体名称、分类标签

示例：
摘要：机器学习是人工智能的一个分支，它通过算法让计算机从数据中学习规律。
标签：机器学习, 人工智能, 算法, 数据挖掘, 计算机科学

现在请输出："""

    def _parse_response(self, response: str) -> Tuple[str, List[str]]:
        """
        Parse LLM response to extract summary and tags.

        Args:
            response: Raw LLM response text

        Returns:
            Tuple of (summary, tags)
        """
        # Initialize with default values
        summary = ""
        tags = []

        # Try to extract summary
        summary_match = re.search(
            r'摘要[：:]\s*(.+?)(?:\n|$)',
            response,
            re.IGNORECASE | re.DOTALL
        )
        if summary_match:
            summary = summary_match.group(1).strip()
        else:
            # Fallback: take first sentence
            first_sentence = response.split('。')[0].split('\n')[0].strip()
            summary = first_sentence if first_sentence else response[:100]

        # Ensure summary length constraints
        if len(summary) < self.SUMMARY_MIN_LENGTH:
            summary = summary + "..." if len(summary) < len(response) else summary
        if len(summary) > self.SUMMARY_MAX_LENGTH:
            summary = summary[:self.SUMMARY_MAX_LENGTH - 3] + "..."

        # Try to extract tags
        tags_match = re.search(
            r'标签[：:]\s*(.+?)(?:\n|$)',
            response,
            re.IGNORECASE
        )
        if tags_match:
            tags_str = tags_match.group(1).strip()
            # Split by comma and clean up
            tags = [
                tag.strip()
                for tag in re.split(r'[,，、\n]+', tags_str)
                if tag.strip()
            ]

        # Ensure tag count constraints
        if len(tags) < self.TAGS_MIN_COUNT:
            # Try to extract more tags from summary if needed
            extra_tags = self._extract_keywords_from_text(summary)
            tags.extend(extra_tags[:self.TAGS_MIN_COUNT - len(tags)])
        elif len(tags) > self.TAGS_MAX_COUNT:
            tags = tags[:self.TAGS_MAX_COUNT]

        return summary, tags

    def _fallback_summary(self, chunk: str) -> Tuple[str, List[str]]:
        """
        Generate fallback summary when LLM fails.

        Uses simple extraction-based approach:
        - Summary: First 200 characters
        - Tags: Most frequent meaningful words

        Args:
            chunk: The chunk text

        Returns:
            Tuple of (summary, tags)
        """
        # Summary: take first meaningful part
        summary = chunk[:self.SUMMARY_MAX_LENGTH]
        if len(chunk) > self.SUMMARY_MAX_LENGTH:
            summary = summary.rstrip() + "..."

        # Tags: extract keywords
        tags = self._extract_keywords_from_text(chunk)

        # Ensure we have at least some tags
        if len(tags) < self.TAGS_MIN_COUNT:
            tags = tags[:self.TAGS_MIN_COUNT] or ["通用", "文本"]

        # Limit max tags
        tags = tags[:self.TAGS_MAX_COUNT]

        return summary, tags

    def _extract_keywords_from_text(self, text: str) -> List[str]:
        """
        Extract keywords from text using simple frequency analysis.

        Args:
            text: The text to analyze

        Returns:
            List of keywords sorted by frequency
        """
        # Common stopwords to filter out (Chinese and English)
        stopwords = {
            # Chinese stopwords
            '的', '了', '是', '在', '和', '有', '我', '他', '她', '它',
            '这', '那', '就', '都', '也', '而', '及', '与', '或', '但',
            '可以', '能够', '需要', '应该', '如果', '因为', '所以', '但是',
            # English stopwords
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
            'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was',
            # Common symbols
            '，', '。', '、', '；', '：', '？', '！', '「', '」', '『', '』'
        }

        # Extract words (Chinese characters and English words)
        # For Chinese, we'll use bigrams; for English, use individual words
        words = []

        # Extract Chinese bigrams (2-character sequences)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for chars in chinese_chars:
            if len(chars) >= 2:
                # Add 2-character words
                for i in range(len(chars) - 1):
                    words.append(chars[i:i + 2])

        # Extract English words
        english_words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
        words.extend([w.lower() for w in english_words])

        # Filter out stopwords and count frequency
        filtered_words = [w for w in words if w not in stopwords and len(w) > 1]
        word_counts = Counter(filtered_words)

        # Get top keywords
        top_keywords = [w for w, _ in word_counts.most_common(20)]

        return top_keywords

    async def health_check(self) -> bool:
        """
        Check if the LLM service is available.

        Returns:
            True if LLM is accessible
        """
        return self.llm_client.health_check()


class MockSummarizer(LLMChunkSummarizer):
    """
    Mock summarizer for testing purposes.

    Generates deterministic summaries and tags without calling LLM.
    """

    async def generate_summary_and_tags(
        self,
        chunk: str,
        context: Optional[str] = None
    ) -> Tuple[str, List[str]]:
        """Generate mock summary and tags for testing."""
        # Create a simple summary based on chunk content
        summary = chunk[:min(150, len(chunk))]
        if len(chunk) > 150:
            summary = summary.rstrip() + "..."

        # Extract some keywords
        tags = self._extract_keywords_from_text(chunk)[:8]

        # Ensure we have at least 3 tags
        if len(tags) < 3:
            tags = tags + ["测试", "示例"]

        return summary, tags[:8]
