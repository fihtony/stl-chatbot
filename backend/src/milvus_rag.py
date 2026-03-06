"""基于 Milvus 的 RAG 流程。

本模块提供:
- 使用 Milvus 向量数据库进行文档检索
- 多语言查询处理（英/法/中）
- 学校术语匹配和重排序
- BGE-M3 嵌入模型支持
- 时间感知的文档检索
"""

import time
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

from .milvus_store import MilvusStore
from .embedding import EmbeddingClient
from .zhipuai_llm import ZhipuAIClient
from .translation_service import FreeTranslationService
from .school_terms import expand_query_with_school_terms
from .hybrid_retriever import HybridRetriever


# 语言检测模式
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
FRENCH_PATTERN = re.compile(r"[éèêëàâäùûüôöîïç]")


def detect_language(text: str) -> str:
    """检测文本语言。

    Args:
        text: 要检测的文本

    Returns:
        语言代码: 'zh' (中文), 'fr' (法语), 'en' (英语)
    """
    # 检查中文字符
    if CHINESE_PATTERN.search(text):
        return "zh"

    # 检查法文字符
    if FRENCH_PATTERN.search(text):
        return "fr"

    # 检查常见的法语单词（即使没有重音符号）
    text_lower = text.lower()
    french_keywords = [
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "pour",
        "que",
        "qui",
        "quoi",
        "où",
        "quand",
        "comment",
        "pourquoi",
        "et",
        "ou",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "ce",
        "cet",
        "cette",
        "ces",
        "mon",
        "ton",
        "son",
        "ma",
        "ta",
        "sa",
        "mes",
        "tes",
        "ses",
        "nos",
        "vos",
        "être",
        "avoir",
        "faire",
        "aller",
        "dire",
        "voir",
        "pouvoir",
        "vouloir",
        "quels",
        "quelles",
        "quel",
        "quelle",
        "sont",
        "est",
        "suis",
        "es",
        "derniers",
        "dernières",
        "dernier",
        "dernière",
        "info-parents",
        "info parents",
        "récent",
        "récente",
        "récents",
        "récentes",
        "plus",
        "très",
        "bien",
    ]
    # 如果查询中包含多个法语关键词，判定为法语
    french_word_count = sum(1 for word in french_keywords if word in text_lower.split())
    if french_word_count >= 2:  # 至少2个法语单词
        return "fr"

    # 默认为英语
    return "en"


# 语言名称映射
LANGUAGE_NAMES = {
    "zh": "中文",
    "fr": "法语",
    "en": "英语",
}


# 语言特定的提示词
LANGUAGE_PROMPTS = {
    "zh": """请用中文回答。**关键指示**：即使文档内容需要解释或重新组织，如果文档中包含相关信息，请基于该信息进行回答。只有在完全没有相关信息时，才说明「根据提供的文档，我无法回答这个问题」。

**重要提示**：本文档库是关于 Collège Saint-Louis（圣路易中学）的，这是一所中学（中学1-5年级，约12-17岁）。

**年级映射规则**：
- 1-2年级 = 1er cycle（中学第一阶段）
- 3-4-5年级 = 2e cycle（中学第二阶段）

**課程和活動查詢處理**：
- 当文档提到相关的课程或年级信息时，请立即提供答案，即使需要解释其含义
- 当文档明确标注某个活动属于特定 cycle（如「Jazz 2e cycle」、「Jazz 1er cycle」）时，请直接列出这些活动
- 不要因为「信息格式不完全匹配问题措辞」就拒绝回答
- 如果文档中既有 cycle 明确的活动，又有一般活动，请先列出明确的 cycle 活动，然后说明还有其他活动

例如：用户问「3年级的课程」应该查找「2e cycle」的课程或学习计划信息。

请基于以下文档内容回答问题：
""",
    "fr": """Veuillez répondre en français. **Instruction clé** : Même si le contenu du document nécessite une interprétation ou une réorganisation, si le document contient des informations pertinentes, veuillez répondre en vous basant sur cette information. Ne refusez de répondre que si aucune information pertinente n'est trouvée.

**Note importante** : Cette base de documents concerne le Collège Saint-Louis, une école secondaire (secondaire 1 à 5, environ 12-17 ans).

**Règles de correspondance des niveaux** :
- Secondaire 1-2 = 1er cycle
- Secondaire 3-4-5 = 2e cycle

**Traitement des requêtes sur les programmes d'études et activités** :
- Lorsque le document mentionne des informations pertinentes sur le curriculum ou le programme d'un niveau, veuillez immédiatement fournir une réponse
- Lorsqu'un document mentionne explicitement qu'une activité appartient à un cycle spécifique (ex: « Jazz 2e cycle », « Jazz 1er cycle »), veuillez lister ces activités
- Ne refusez pas de répondre sous prétexte que « le format de l'information ne correspond pas exactement au libellé de la question »
- Si les documents contiennent à la fois des activités avec un cycle explicite et des activités générales, listez d'abord les activités explicites, puis mentionnez les autres

Par exemple : si l'utilisateur demande « le curriculum pour la 3e secondaire », vous devriez chercher les informations du « 2e cycle » relate aux programmes d'études.

Veuillez répondre à la question suivante en vous basant sur les documents ci-dessous :
""",
    "en": """Please answer in English. **Key Instruction**: Even if document content requires interpretation or reorganization, if the documents contain relevant information, provide an answer based on that information. Only refuse to answer if absolutely no relevant information is found in the documents.

**Important Note**: This document database is about Collège Saint-Louis, a secondary school (grades 7-11, approximately 12-17 years old).

**Grade Mapping Rules**:
- Secondary 1-2 = 1er cycle (first cycle)
- Secondary 3-4-5 = 2e cycle (second cycle)

**Curriculum & Program Query Processing** (IMPORTANT):
- For ANY questions about curriculum, programs, course offerings, or study plans: If documents contain information about that grade level's programs, ALWAYS synthesize and provide a complete answer
- Do NOT say "I cannot answer" if documents are provided - instead, answer based on what's in the documents
- When a document mentions a "program" or "curriculum" or "study" information, treat it as relevant to curriculum questions regardless of exact wording
- When a document explicitly labels an activity as belonging to a specific cycle (e.g., "Jazz 2e cycle", "Jazz 1er cycle"), list these activities
- Do NOT refuse to answer simply because "the information format does not exactly match the question wording"
- If documents contain both cycle-specific content and general information, provide both

For example: if the user asks "What is the curriculum for grade 9?", and you find "2e cycle - Programme d'études" in the documents, provide that information as the answer.

Please answer the following question based on the documents below. Remember: Always answer if relevant documents are provided:
""",
}


class MilvusRAGPipeline:
    """基于 Milvus 的 RAG 流程。

    特性:
    - 使用 Milvus 向量数据库进行高效检索
    - BGE-M3 多语言嵌入支持
    - 英语查询自动翻译到法语
    - 学校术语匹配和重排序
    - 时间感知的文档新鲜度评分
    """

    # 默认配置
    DEFAULT_TOP_K = 10
    DEFAULT_RERANK_COUNT = 10  # Increased to include more relevant chunks

    # 重排序权重
    VECTOR_WEIGHT = 1.0
    TERM_BONUS_WEIGHT = 0.15
    RECENCY_BONUS_WEIGHT = 0.10

    def __init__(
        self,
        milvus_store: MilvusStore,
        embedding_client: Optional[EmbeddingClient] = None,
        llm_client: Optional[ZhipuAIClient] = None,
        translation_service: Optional[FreeTranslationService] = None,
        top_k: int = DEFAULT_TOP_K,
        rerank_count: int = DEFAULT_RERANK_COUNT,
        use_hybrid_search: bool = True,
    ):
        """初始化 Milvus RAG 流程。

        Args:
            milvus_store: Milvus 向量存储实例
            embedding_client: 嵌入模型客户端（默认使用 BGE-M3）
            llm_client: LLM 客户端
            translation_service: 翻译服务
            top_k: 检索的文档块数量
            rerank_count: 重排序后保留的文档块数量
            use_hybrid_search: 是否使用混合检索（BM25+语义）
        """
        self.milvus_store = milvus_store
        self.top_k = top_k
        self.rerank_count = rerank_count
        self.use_hybrid_search = use_hybrid_search

        # 初始化嵌入客户端（默认使用 BGE-M3）
        if embedding_client is None:
            embedding_client = EmbeddingClient(model_name="BAAI/bge-m3", device="cpu")
        self.embedding_client = embedding_client

        # 初始化 LLM 客户端
        if llm_client is None:
            llm_client = ZhipuAIClient()
        self.llm_client = llm_client

        # 初始化翻译服务
        if translation_service is None:
            translation_service = FreeTranslationService(llm_client=llm_client)
        self.translation_service = translation_service

        # 初始化混合检索器
        if use_hybrid_search:
            self.hybrid_retriever = HybridRetriever(
                milvus_store=milvus_store,
                embedding_client=embedding_client,
                bm25_weight=0.3,
                milvus_weight=0.7,
            )
        else:
            self.hybrid_retriever = None

        # 性能统计
        self._stats = {
            "queries": 0,
            "translated_queries": 0,
            "with_context": 0,
            "without_context": 0,
            "avg_search_time_ms": 0,
            "avg_generation_time_ms": 0,
        }

    def query(
        self,
        question: str,
        language: Optional[str] = None,
        top_k: Optional[int] = None,
        use_reranking: bool = True,
        use_date_sorting: bool = True,
    ) -> Dict[str, Any]:
        """处理用户查询。

        Args:
            question: 用户问题
            language: 回答语言（自动检测）
            top_k: 检索的文档块数量（默认使用初始化时的值）
            use_reranking: 是否使用重排序
            use_date_sorting: 是否对"最新"查询使用日期排序

        Returns:
            包含 answer, sources, metadata 的字典
        """
        start_time = time.time()

        # 检测语言
        if language is None:
            language = detect_language(question)

        # 检测是否为"最新"查询
        is_latest_query = self._is_latest_query(question, language)

        # 对于特定文档查询（包含月份名称），使用更高的 top_k 以获取更多内容
        # 这允许对整个文档进行更好的总结
        query_lower = question.lower()
        has_document_reference = any(
            month in query_lower
            for month in [
                "janvier",
                "fevrier",
                "mars",
                "avril",
                "mai",
                "juin",
                "juillet",
                "aout",
                "septembre",
                "octobre",
                "novembre",
                "decembre",
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ]
        )

        if is_latest_query:
            if has_document_reference:
                # 对于特定文档查询，使用 4x top_k 以获取更多文档内容
                search_top_k = (top_k or self.top_k) * 4
            else:
                # 对于一般 "latest" 查询，使用 2x top_k
                search_top_k = (top_k or self.top_k) * 2
        else:
            search_top_k = top_k or self.top_k

        # 处理英语查询（翻译到法语）
        original_question = question
        if language == "en":
            question_translated, _ = self.translation_service.translate(
                question, "fr", source_lang="en"
            )
            if question_translated != question:
                question = question_translated
                self._stats["translated_queries"] += 1
                # 翻译后的查询是法语，使用法语进行术语扩展
                expanded_queries = expand_query_with_school_terms(question, lang="fr")
            else:
                # 翻译失败或不需要翻译，使用原始语言
                expanded_queries = expand_query_with_school_terms(
                    question, lang=language
                )
        else:
            # 非英语查询，使用原始语言
            expanded_queries = expand_query_with_school_terms(question, lang=language)

        # 选择搜索方法
        print(
            f"🔍 Debug: is_latest_query={is_latest_query}, hybrid_retriever={self.hybrid_retriever is not None}"
        )
        if is_latest_query and self.hybrid_retriever:
            # 使用混合检索 + 日期排序
            search_results = self.hybrid_retriever.hybrid_search(
                query=question, top_k=search_top_k, use_date_sorting=True
            )
            search_time = (
                search_results[0].get("search_time_ms", 0) if search_results else 0
            )
        else:
            # 标准Milvus 搜索
            query_embedding = self.embedding_client.embed_query(question)

            # 搜索相似文档
            search_results, search_time = self.milvus_store.search_timed(
                query_embedding, top_k=search_top_k
            )

            # 如果使用学校术语扩展，也搜索扩展的查询
            if len(expanded_queries) > 1:
                for expanded_query in expanded_queries[1:]:
                    expanded_embedding = self.embedding_client.embed_query(
                        expanded_query
                    )
                    expanded_results, _ = self.milvus_store.search_timed(
                        expanded_embedding, top_k=search_top_k
                    )
                    # 合并结果（去重）
                    existing_ids = {r["id"] for r in search_results}
                    for result in expanded_results:
                        if result["id"] not in existing_ids:
                            search_results.append(result)
                            existing_ids.add(result["id"])

        # 重排序结果（但对于"最新"查询，跳过重排序以保留日期排序）
        # 混合搜索已经按日期排序，重排序可能会破坏这个顺序
        if use_reranking and search_results and not is_latest_query:
            search_results = self._rerank(
                search_results,
                original_question,
                language=language,
            )

        # 限制结果数量
        search_results = search_results[: self.rerank_count]

        # Debug: 打印前5个结果的来源
        if is_latest_query:
            print(f"📋 Debug: Top 5 sources for latest query:")
            for i, r in enumerate(search_results[:5]):
                source = r["metadata"].get("source", "")
                score = r.get("hybrid_score", r.get("score", 0))
                date_str = r.get("doc_date_str", "N/A")
                print(f"  {i + 1}. {source} (score: {score:.3f}, date: {date_str})")

        # 构建上下文（对于最新查询，只使用排序后的前几个结果）
        context = self._build_context(
            search_results, language=language, is_latest_query=is_latest_query
        )

        # 生成答案
        has_context = len(context) > 0
        answer, generation_time = self._generate_answer(
            original_question,
            context,
            language=language,
            is_latest_query=is_latest_query,
        )

        # 计算总时间
        total_time = (time.time() - start_time) * 1000

        # 更新统计信息
        self._stats["queries"] += 1
        if has_context:
            self._stats["with_context"] += 1
        else:
            self._stats["without_context"] += 1

        # 更新平均时间
        self._stats["avg_search_time_ms"] = (
            self._stats["avg_search_time_ms"] * (self._stats["queries"] - 1)
            + search_time
        ) / self._stats["queries"]
        self._stats["avg_generation_time_ms"] = (
            self._stats["avg_generation_time_ms"] * (self._stats["queries"] - 1)
            + generation_time
        ) / self._stats["queries"]

        # 提取来源
        sources = []
        seen_sources = set()
        for result in search_results:
            source = result["metadata"]["source"]
            if source not in seen_sources:
                sources.append(
                    {
                        "source": source,
                        "page": result["metadata"]["page"],
                        "score": result["score"],
                    }
                )
                seen_sources.add(source)

        return {
            "answer": answer,
            "sources": sources,
            "metadata": {
                "language": language,
                "translated": language == "en" and question != original_question,
                "original_question": original_question,
                "searched_question": question,
                "search_results_count": len(search_results),
                "has_context": has_context,
                "search_time_ms": round(search_time, 2),
                "generation_time_ms": round(generation_time, 2),
                "total_time_ms": round(total_time, 2),
            },
        }

    def _is_latest_query(self, question: str, language: str) -> bool:
        """检测查询是否询问"最新"内容。

        Args:
            question: 查询文本
            language: 语言代码

        Returns:
            True 如果是"最新"查询
        """
        question_lower = question.lower()

        # 多语言的"最新"关键词
        latest_keywords = {
            "fr": [
                "latest",
                "plus récent",
                "récent",
                "plus récents",
                "récents",
                "dernier",
                "derniers",
                "dernière",
                "dernières",
                "nouveau",
                "nouveaux",
                "nouvelle",
                "nouvelles",
                "finale",
                "finales",
                "actuel",
                "actuelle",
            ],
            "en": ["latest", "most recent", "newest", "current", "last", "up to date"],
            "zh": ["最新", "最近", "当前", "最新期", "最后一个"],
        }

        keywords = latest_keywords.get(language, [])

        # 检查是否包含任何"最新"关键词
        for keyword in keywords:
            if keyword in question_lower:
                return True

        # 检测带月份的查询（如 "march 2026", "février 2026"）
        # 这类查询应该使用日期排序
        import re
        from .date_utils import ALL_MONTHS

        # 匹配 "month year" 或 "monthannée" 模式
        for month_name in ALL_MONTHS.keys():
            # 匹配 "march 2026" 或 "mars 2026"
            if month_name in question_lower:
                # 检查附近是否有4位数字年份
                pattern = rf"{month_name}[^\d]*?(\d{{4}})"
                if re.search(pattern, question_lower):
                    return True

        return False

    def _rerank(
        self,
        results: List[Dict[str, Any]],
        query: str,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """对搜索结果进行重排序。

        结合向量相似度、术语匹配和时间新鲜度进行重新排序。

        Args:
            results: 搜索结果列表
            query: 原始查询
            language: 查询语言

        Returns:
            重排序后的结果列表
        """
        if not results:
            return results

        # 计算每个结果的综合得分
        for result in results:
            base_score = result["score"]

            # 计算术语匹配奖励
            term_bonus = self._calculate_term_bonus(result["content"], query, language)

            # 计算时间新鲜度奖励
            recency_bonus = self._calculate_recency_bonus(result["metadata"])

            # 综合得分
            combined_score = (
                base_score * self.VECTOR_WEIGHT
                + term_bonus * self.TERM_BONUS_WEIGHT
                + recency_bonus * self.RECENCY_BONUS_WEIGHT
            )

            result["rerank_score"] = combined_score

        # 按综合得分排序
        return sorted(results, key=lambda x: x["rerank_score"], reverse=True)

    def _calculate_term_bonus(
        self,
        content: str,
        query: str,
        language: str = "en",
    ) -> float:
        """计算术语匹配奖励。

        如果文档内容包含查询中的学校术语，给予额外奖励。

        Args:
            content: 文档内容
            query: 查询文本
            language: 查询语言

        Returns:
            术语匹配奖励分数 [0, 1]
        """
        content_lower = content.lower()
        query_lower = query.lower()

        # 对于英语查询，检查法语翻译的术语
        if language == "en":
            # 从查询中提取可能的学校术语
            from .school_terms import ENGLISH_TO_FRENCH_TERMS

            bonus = 0.0
            matched_terms = 0

            for en_term, fr_terms in ENGLISH_TO_FRENCH_TERMS.items():
                # 检查查询中是否包含英语术语
                if en_term in query_lower:
                    # 检查文档中是否包含对应的法语术语
                    for fr_term in fr_terms:
                        if fr_term in content_lower:
                            bonus += 0.1
                            matched_terms += 1
                            break

            # 限制最大奖励
            return min(bonus, 1.0)

        # 对于非英语查询，简单检查查询词是否出现在内容中
        query_words = set(query_lower.split())
        content_words = set(content_lower.split())

        if not query_words:
            return 0.0

        overlap = len(query_words & content_words) / len(query_words)
        return overlap

    def _calculate_recency_bonus(self, metadata: Dict[str, Any]) -> float:
        """计算时间新鲜度奖励。

        较新的文档获得额外奖励。

        Args:
            metadata: 文档元数据

        Returns:
            时间新鲜度奖励分数 [0, 1]
        """
        date_str = metadata.get("date", "")
        if not date_str:
            return 0.0

        try:
            # 尝试解析日期
            # 支持多种日期格式: 2024-01-15, 15/01/2024, Jan 15, 2024
            date_formats = [
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%b %d, %Y",
                "%B %d, %Y",
            ]

            doc_date = None
            for fmt in date_formats:
                try:
                    doc_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

            if doc_date is None:
                return 0.0

            # 计算文档年龄（天数）
            age_days = (datetime.now() - doc_date).days

            # 较新的文档（< 1 年）获得奖励
            if age_days < 365:
                # 使用指数衰减
                bonus = np.exp(-age_days / 365)
                return float(bonus)

            return 0.0

        except Exception:
            return 0.0

    def _build_context(
        self,
        results: List[Dict[str, Any]],
        language: str = "en",
        is_latest_query: bool = False,
    ) -> str:
        """构建上下文文本。

        Args:
            results: 搜索结果列表
            language: 语言
            is_latest_query: 是否为"最新"查询

        Returns:
            格式化的上下文文本
        """
        if not results:
            return ""

        # 对于最新查询，只使用前2个结果（排序后最新的）
        if is_latest_query:
            results = results[:2]

        context_parts = []

        for i, result in enumerate(results, 1):
            content = result["content"]
            source = result["metadata"]["source"]
            page = result["metadata"]["page"]

            # 提取文件名
            source_name = source.split("/")[-1] if "/" in source else source

            # 格式化每个文档块
            context_part = f"[Document {i}] {source_name} (page {page})\n{content}\n"
            context_parts.append(context_part)

        return "\n".join(context_parts)

    def _generate_answer(
        self,
        question: str,
        context: str,
        language: str = "en",
        is_latest_query: bool = False,
    ) -> Tuple[str, float]:
        """生成答案。

        Args:
            question: 用户问题
            context: 检索到的上下文
            language: 回答语言
            is_latest_query: 是否为"最新"查询

        Returns:
            元组 (答案, 生成时间毫秒)
        """
        # 获取语言特定的提示词
        system_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["en"])

        # 如果是"最新"查询，添加日期优先级提示
        if is_latest_query:
            date_priority_hints = {
                "fr": "\n\n**IMPORTANT** : Pour la question sur les dernieres informations, utilisez UNIQUEMENT le document le plus recent (celui avec la date la plus recente). Ignorez les documents plus anciens.",
                "en": "\n\n**IMPORTANT**: For questions about the latest information, use ONLY the most recent document (the one with the most recent date). Ignore older documents.",
                "zh": "\n\n**重要提示**：对于最新信息的问题，请仅使用最新日期的文档。忽略较旧的文档。",
            }
            system_prompt += date_priority_hints.get(
                language, date_priority_hints["en"]
            )

        # 如果没有上下文，调整提示词
        if not context:
            context = "没有找到相关文档内容。"

        # 调用 LLM - 正确传递 context 和 system_prompt
        result, generation_time = self.llm_client.chat_timed(
            prompt=question,
            context=context,
            system_prompt=system_prompt,
            temperature=0.7,
        )

        if result["success"]:
            answer = result["response"].strip()
            # 移除可能的引号
            answer = answer.strip("\"'")
        else:
            # 记录错误信息以便调试
            error_msg = result.get("error", "Unknown error")
            print(f"⚠️ LLM 生成失败: {error_msg}")
            print(f"   问题: {question[:100]}...")
            print(f"   语言: {language}")
            answer = "抱歉，生成答案时出现问题。请稍后重试。"

        return answer, generation_time

    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计信息。

        Returns:
            包含统计信息的字典
        """
        return {
            **self._stats,
            "milvus_healthy": self.milvus_store.is_healthy(),
            "embedding_model": self.embedding_client.model_name,
            "embedding_dim": self.embedding_client.embedding_dim,
            "top_k": self.top_k,
            "rerank_count": self.rerank_count,
        }

    def health_check(self) -> Dict[str, Any]:
        """执行健康检查。

        Returns:
            包含健康状态的字典
        """
        milvus_health = self.milvus_store.health_check()
        llm_healthy = self.llm_client.health_check()

        return {
            "healthy": milvus_health.get("healthy", False) and llm_healthy,
            "milvus": milvus_health,
            "llm": llm_healthy,
            "embedding": {
                "model": self.embedding_client.model_name,
                "dim": self.embedding_client.embedding_dim,
                "neural": self.embedding_client.is_neural,
            },
        }


# 便捷函数
def create_milvus_rag(
    milvus_host: str = "localhost",
    milvus_port: int = 19530,
    collection_name: str = "documents",
    embedding_model: str = "BAAI/bge-m3",
    top_k: int = 10,
) -> MilvusRAGPipeline:
    """创建 Milvus RAG 流程实例的便捷函数。

    Args:
        milvus_host: Milvus 服务器地址
        milvus_port: Milvus 服务器端口
        collection_name: 集合名称
        embedding_model: 嵌入模型名称
        top_k: 检索的文档块数量

    Returns:
        MilvusRAGPipeline 实例
    """
    # 创建 Milvus 存储
    milvus_store = MilvusStore(
        host=milvus_host,
        port=milvus_port,
        collection_name=collection_name,
    )

    # 创建嵌入客户端
    embedding_client = EmbeddingClient(model_name=embedding_model, device="cpu")

    # 创建 LLM 客户端
    llm_client = ZhipuAIClient()

    # 创建翻译服务
    translation_service = FreeTranslationService(llm_client=llm_client)

    # 创建 RAG 流程
    return MilvusRAGPipeline(
        milvus_store=milvus_store,
        embedding_client=embedding_client,
        llm_client=llm_client,
        translation_service=translation_service,
        top_k=top_k,
    )
