"""混合检索器 - 结合 BM25 关键词搜索和 Milvus 语义搜索。

特性:
1. BM25 关键词搜索 - 精确匹配文档中的词汇
2. Milvus 语义搜索 - 向量相似度匹配
3. 结果融合 - 结合两种搜索结果
4. 日期感知 - 按文档日期排序结果
"""

import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import numpy as np

from .milvus_store import MilvusStore
from .embedding import EmbeddingClient
from .date_utils import extract_date_from_content, compare_dates, is_later_date


class BM25Searcher:
    """BM25 关键词搜索器。

    使用简化的 BM25 算法进行关键词搜索。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """初始化 BM25 搜索器。

        Args:
            k1: 词频饱和参数
            b: 长度归一化参数
        """
        self.k1 = k1
        self.b = b
        self.avg_doc_length = 0

    def tokenize(self, text: str) -> List[str]:
        """将文本分词。

        支持英语、法语和中文的基本分词。

        Args:
            text: 输入文本

        Returns:
            词汇列表
        """
        # 转小写
        text = text.lower()

        # 移除特殊字符但保留多语言字符
        import re
        words = re.findall(r'\w+', text)

        return words

    def build_index(self, documents: List[str]) -> Dict[str, Any]:
        """构建 BM25 索引。

        Args:
            documents: 文档列表

        Returns:
            包含 IDF、文档长度等的索引字典
        """
        # 分词
        tokenized_docs = [self.tokenize(doc) for doc in documents]

        # 计算文档长度
        doc_lengths = [len(tokens) for tokens in tokenized_docs]
        self.avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 0

        # 计算 IDF
        from collections import defaultdict

        df = defaultdict(int)  # 文档频率
        for tokens in tokenized_docs:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                df[token] += 1

        N = len(documents)
        idf = {}
        for token, freq in df.items():
            idf[token] = np.log((N - freq + 0.5) / (freq + 0.5) + 1)

        return {
            'tokenized_docs': tokenized_docs,
            'doc_lengths': doc_lengths,
            'idf': idf,
            'N': N
        }

    def search(
        self,
        query: str,
        index: Dict[str, Any],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """使用 BM25 算法搜索文档。

        Args:
            query: 查询文本
            index: BM25 索引
            top_k: 返回的结果数量

        Returns:
            搜索结果列表，按 BM25 分数降序排列
        """
        query_tokens = self.tokenize(query)
        tokenized_docs = index['tokenized_docs']
        doc_lengths = index['doc_lengths']
        idf = index['idf']
        N = index['N']

        scores = []

        for doc_idx, doc_tokens in enumerate(tokenized_docs):
            score = 0
            doc_len = doc_lengths[doc_idx]

            for token in query_tokens:
                if token not in doc_tokens:
                    continue

                # 词频
                tf = doc_tokens.count(token)

                # BM25 分数
                idf_score = idf.get(token, 0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
                score += idf_score * (numerator / denominator)

            if score > 0:
                scores.append({
                    'doc_idx': doc_idx,
                    'score': score
                })

        # 按分数排序
        scores.sort(key=lambda x: x['score'], reverse=True)

        return scores[:top_k]


class HybridRetriever:
    """混合检索器 - 结合 BM25 和 Milvus 搜索。

    特性:
    1. BM25 关键词搜索 - 精确匹配
    2. Milvus 语义搜索 - 向量相似度
    3. 结果融合 - RRF (Reciprocal Rank Fusion)
    4. 日期感知排序 - 最新文档优先
    """

    def __init__(
        self,
        milvus_store: MilvusStore,
        embedding_client: EmbeddingClient,
        bm25_weight: float = 0.3,
        milvus_weight: float = 0.7,
        rrf_k: int = 60
    ):
        """初始化混合检索器。

        Args:
            milvus_store: Milvus 存储实例
            embedding_client: 嵌入客户端
            bm25_weight: BM25 权重 (默认 0.3)
            milvus_weight: Milvus 权重 (默认 0.7)
            rrf_k: RRF 融合参数 (默认 60)
        """
        self.milvus_store = milvus_store
        self.embedding_client = embedding_client
        self.bm25_weight = bm25_weight
        self.milvus_weight = milvus_weight
        self.rrf_k = rrf_k

        # 确保 bm25_weight + milvus_weight = 1
        total = bm25_weight + milvus_weight
        if total != 1:
            self.bm25_weight = bm25_weight / total
            self.milvus_weight = milvus_weight / total

        self.bm25_searcher = BM25Searcher()

        # 缓存 BM25 索引
        self._bm25_index = None
        self._documents_cache = []

    def _build_bm25_index(self, documents: List[str]) -> None:
        """构建 BM25 索引。

        Args:
            documents: 文档列表
        """
        self._documents_cache = documents
        self._bm25_index = self.bm25_searcher.build_index(documents)

    def _get_all_documents(self) -> List[str]:
        """获取所有文档内容。

        Returns:
            文档内容列表
        """
        # 从 Milvus 获取所有文档
        try:
            # 使用一个通用查询来获取所有文档
            all_results = []
            for start in range(0, 10000, 100):
                # 这里需要 Milvus 支持分页或直接查询
                # 暂时返回空列表，后续需要实现
                pass
        except Exception:
            pass

        return []

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        use_date_sorting: bool = False
    ) -> List[Dict[str, Any]]:
        """执行混合检索。

        结合 BM25 关键词搜索和 Milvus 语义搜索的结果。

        Args:
            query: 查询文本
            top_k: 返回的结果数量
            use_date_sorting: 是否使用日期排序

        Returns:
            融合后的搜索结果列表
        """
        start_time = time.time()

        # 1. Milvus 语义搜索
        # 如果是日期排序查询（"latest" 等），添加当前年份和月份以改善检索
        search_query = query
        if use_date_sorting:
            current_year = datetime.now().year
            current_month = datetime.now().month
            # 获取当前月份的法语名称
            from .date_utils import MONTH_NUM_TO_FRENCH
            month_fr = MONTH_NUM_TO_FRENCH.get(current_month, '')
            # 添加当前年份到查询中，帮助检索到最新文档
            search_query = f"{query} {current_year}"

        query_embedding = self.embedding_client.embed_query(search_query)
        milvus_results = self.milvus_store.search(query_embedding, top_k=top_k * 2)

        # 如果是日期排序查询，额外搜索当前月份的文档
        if use_date_sorting and month_fr:
            month_query = f"info-parents {month_fr} {current_year}"
            month_embedding = self.embedding_client.embed_query(month_query)
            month_results = self.milvus_store.search(month_embedding, top_k=top_k)

            # 合并结果，去重
            seen_ids = {r.get('id') for r in milvus_results}
            for result in month_results:
                if result.get('id') not in seen_ids:
                    milvus_results.append(result)
                    seen_ids.add(result.get('id'))

        # 2. BM25 关键词搜索（如果需要）
        # 注意：完整的 BM25 需要所有文档，这在 Milvus 中不实用
        # 我们使用简化的方法：基于术语匹配的重新排序

        # 3. RRF (Reciprocal Rank Fusion) 融合
        # 实际上，我们主要使用 Milvus 结果，但用术语匹配增强

        # 提取查询中的日期相关词汇
        date_boosts = self._extract_date_terms(query)

        # 为每个结果计算融合分数
        for result in milvus_results:
            base_score = result['score']

            # 术语匹配奖励
            term_bonus = self._calculate_term_match_bonus(
                result['content'],
                query
            )

            # 日期奖励
            date_bonus = self._calculate_date_bonus(
                result['metadata'],
                date_boosts
            )

            # 综合分数
            result['hybrid_score'] = (
                base_score * 0.85 +
                term_bonus * 0.10 +
                date_bonus * 0.05
            )

        # 4. 按综合分数排序
        results = sorted(milvus_results, key=lambda x: x.get('hybrid_score', x['score']), reverse=True)

        # 5. 如果需要日期排序，进一步调整顺序
        if use_date_sorting:
            results = self._sort_by_date(results, query)

        # 限制结果数量
        results = results[:top_k]

        # 记录搜索时间
        search_time = (time.time() - start_time) * 1000

        # 添加搜索时间到元数据
        for result in results:
            result['search_time_ms'] = search_time

        return results

    def _extract_date_terms(self, query: str) -> List[str]:
        """从查询中提取日期相关词汇。

        Args:
            query: 查询文本

        Returns:
            日期词汇列表
        """
        from .date_utils import ALL_MONTHS

        date_terms = []
        query_lower = query.lower()

        # 检查月份名称
        for month_name in ALL_MONTHS.keys():
            if month_name in query_lower:
                date_terms.append(month_name)

        # 检查 "latest", "recent", "plus récent", "dernier" 等词汇
        latest_keywords = [
            'latest', 'recent', 'most recent', 'newest',
            'plus récent', 'plus récents', 'récent', 'récents',
            'dernier', 'derniers', 'dernière', 'dernières',
            'nouveau', 'nouveaux', 'nouvelle', 'nouvelles'
        ]
        for keyword in latest_keywords:
            if keyword in query_lower:
                date_terms.append('LATEST')
                break

        return date_terms

    def _calculate_term_match_bonus(
        self,
        content: str,
        query: str
    ) -> float:
        """计算术语匹配奖励分数。

        Args:
            content: 文档内容
            query: 查询文本

        Returns:
            奖励分数 [0, 1]
        """
        content_lower = content.lower()
        query_lower = query.lower()
        query_words = set(self.bm25_searcher.tokenize(query_lower))

        if not query_words:
            return 0.0

        # 计算查询词在内容中的覆盖率
        matched_words = 0
        for word in query_words:
            if word in content_lower:
                matched_words += 1

        coverage = matched_words / len(query_words)

        # 对于完全匹配给予额外奖励
        if coverage >= 0.8:
            return min(coverage * 1.2, 1.0)

        return coverage

    def _calculate_date_bonus(
        self,
        metadata: Dict[str, Any],
        date_terms: List[str]
    ) -> float:
        """计算日期相关奖励分数。

        如果文档包含更新的日期，给予奖励。

        Args:
            metadata: 文档元数据
            date_terms: 查询中的日期词汇

        Returns:
            奖励分数 [0, 1]
        """
        if 'LATEST' not in date_terms:
            return 0.0

        source = metadata.get('source', '')

        # 从源文件名提取日期
        from .date_utils import extract_date_from_filename

        doc_date = extract_date_from_filename(source)
        if doc_date:
            date_obj, date_str = doc_date

            # 当前年份的文档获得奖励
            current_year = datetime.now().year
            if date_obj.year >= current_year:
                # 2026 年的文档
                return 0.5

            # 2025 年的文档获得较少奖励
            if date_obj.year == current_year - 1:
                return 0.2

        return 0.0

    def _sort_by_date(
        self,
        results: List[Dict[str, Any]],
        query: str
    ) -> List[Dict[str, Any]]:
        """按文档日期排序结果。

        如果查询包含 "latest" 或类似词汇，将更新的文档排在前面。

        Args:
            results: 搜索结果列表
            query: 查询文本

        Returns:
            排序后的结果列表
        """
        # 检查是否需要日期排序
        query_lower = query.lower()
        need_date_sort = any(
            keyword in query_lower
            for keyword in ['latest', 'recent', 'most recent', 'newest',
                          'plus récent', 'récent', 'plus récents', 'récents',
                          'dernier', 'derniers', 'dernière', 'dernières',
                          'nouveau', 'nouveaux', 'nouvelle', 'nouvelles']
        )

        if not need_date_sort:
            return results

        # 为每个结果提取日期
        dated_results = []
        for result in results:
            source = result['metadata'].get('source', '')
            content = result['content']

            date_info = extract_date_from_content(content, source)

            result_copy = result.copy()
            if date_info:
                date_obj, date_str = date_info
                result_copy['doc_date'] = date_obj
                result_copy['doc_date_str'] = date_str

                # 当前年份的文档获得提升
                current_year = datetime.now().year
                if date_obj.year >= current_year:
                    result_copy['date_boost'] = 1.0
                elif date_obj.year == current_year - 1:
                    result_copy['date_boost'] = 0.5
                else:
                    result_copy['date_boost'] = 0.0
            else:
                result_copy['doc_date'] = None
                result_copy['doc_date_str'] = ''
                result_copy['date_boost'] = 0.0

            dated_results.append(result_copy)

        # 排序：优先级
        # 1. 有日期的文档按日期降序（最新的在前）
        # 2. 同日期的文档按 hybrid_score 降序
        # 3. 没有日期的文档按 hybrid_score 降序

        def sort_key(item):
            date_boost = item.get('date_boost', 0)
            doc_date = item.get('doc_date')
            score = item.get('hybrid_score', item.get('score', 0))

            if date_boost > 0 and doc_date:
                # 有日期：按日期降序（用负数），然后按分数降序
                # 使用 (year, month) 作为日期键
                date_key = -(doc_date.year * 100 + doc_date.month)
                return (0, date_key, -score)  # 0 表示有日期
            else:
                # 没有日期：按分数降序
                return (1, -score, 0)  # 1 表示没有日期

        dated_results.sort(key=sort_key)

        return dated_results


def create_hybrid_retriever(
    milvus_store: MilvusStore,
    embedding_client: EmbeddingClient,
    bm25_weight: float = 0.3,
    milvus_weight: float = 0.7
) -> HybridRetriever:
    """创建混合检索器实例。

    Args:
        milvus_store: Milvus 存储实例
        embedding_client: 嵌入客户端
        bm25_weight: BM25 权重
        milvus_weight: Milvus 权重

    Returns:
        HybridRetriever 实例
    """
    return HybridRetriever(
        milvus_store=milvus_store,
        embedding_client=embedding_client,
        bm25_weight=bm25_weight,
        milvus_weight=milvus_weight
    )
