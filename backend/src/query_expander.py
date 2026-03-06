"""Query expansion and rewriting for improved retrieval.

Improves retrieval for ambiguous or complex queries by:
1. Rewriting queries for better clarity
2. Generating multiple query variations
3. Adding relevant context terms
4. Expanding abbreviations and acronyms
"""

import logging
from typing import List, Dict, Any, Optional

from .zhipuai_llm import ZhipuAIClient

# Configure logging
logger = logging.getLogger(__name__)


class QueryExpander:
    """
    Expands and rewrites queries for better retrieval.

    Uses LLM to generate query variations and improvements.
    """

    def __init__(
        self,
        llm_client: Optional[ZhipuAIClient] = None,
        max_variations: int = 3,
        enable_acronym_expansion: bool = True,
    ):
        """
        Initialize query expander.

        Args:
            llm_client: LLM client for query rewriting
            max_variations: Maximum number of query variations to generate
            enable_acronym_expansion: Whether to expand acronyms
        """
        self.llm_client = llm_client
        self.max_variations = max_variations
        self.enable_acronym_expansion = enable_acronym_expansion

        # Common acronyms in educational context
        self.acronym_map = {
            'CS': 'Computer Science',
            'AI': 'Artificial Intelligence',
            'ML': 'Machine Learning',
            'NLP': 'Natural Language Processing',
            'DL': 'Deep Learning',
            'GPU': 'Graphics Processing Unit',
            'CPU': 'Central Processing Unit',
            'API': 'Application Programming Interface',
            'DB': 'Database',
            'RAG': 'Retrieval Augmented Generation',
            'LLM': 'Large Language Model',
            'STEM': 'Science Technology Engineering Mathematics',
        }

    def expand_query(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> List[str]:
        """
        Generate expanded query variations.

        Args:
            query: Original query
            context: Optional context to guide expansion

        Returns:
            List of query variations (including original)
        """
        variations = [query]

        # Add acronym expansion
        if self.enable_acronym_expansion:
            expanded = self._expand_acronyms(query)
            if expanded != query:
                variations.append(expanded)

        # Add LLM-generated variations
        if self.llm_client:
            llm_variations = self._generate_llm_variations(query, context)
            variations.extend(llm_variations)

        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for v in variations:
            if v.lower() not in seen:
                seen.add(v.lower())
                unique_variations.append(v)

        return unique_variations[:self.max_variations]

    def rewrite_query(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Rewrite a query for better clarity and retrieval.

        Args:
            query: Original query
            context: Optional context

        Returns:
            Rewritten query
        """
        if not self.llm_client:
            return query

        prompt = self._get_rewrite_prompt(query, context)

        try:
            response = self.llm_client.generate(
                prompt,
                temperature=0.3,  # Low temperature for consistent rewriting
                max_tokens=100,
            )

            # Extract the rewritten query
            rewritten = response.strip()
            if rewritten and rewritten.lower() != query.lower():
                logger.info(f"Query rewritten: '{query}' -> '{rewritten}'")
                return rewritten

            return query
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}")
            return query

    def _expand_acronyms(self, query: str) -> str:
        """Expand acronyms in the query."""
        expanded = query
        for acronym, full_form in self.acronym_map.items():
            # Match word boundaries
            import re
            pattern = r'\b' + acronym + r'\b'
            expanded = re.sub(pattern, full_form, expanded, flags=re.IGNORECASE)
        return expanded

    def _generate_llm_variations(
        self,
        query: str,
        context: Optional[str],
    ) -> List[str]:
        """Generate query variations using LLM."""
        prompt = self._get_variation_prompt(query, context)

        try:
            response = self.llm_client.generate(
                prompt,
                temperature=0.5,
                max_tokens=150,
            )

            # Parse variations from response
            variations = self._parse_variation_response(response)
            return variations[:self.max_variations - 1]  # -1 for original
        except Exception as e:
            logger.warning(f"LLM variation generation failed: {e}")
            return []

    def _get_rewrite_prompt(self, query: str, context: Optional[str]) -> str:
        """Generate prompt for query rewriting."""
        if context:
            return f"""Rewrite the following question to make it more clear and specific for document search.

Context: {context}

Original question: {query}

Rewritten question (just the question, no explanation):"""
        else:
            return f"""Rewrite the following question to make it more clear and specific for document search.

Original question: {query}

Rewritten question (just the question, no explanation):"""

    def _get_variation_prompt(self, query: str, context: Optional[str]) -> str:
        """Generate prompt for query variations."""
        if context:
            return f"""Generate {self.max_variations - 1} alternative ways to search for information about this question.

Context: {context}
Question: {query}

Provide {self.max_variations - 1} different search queries, one per line:
1."""
        else:
            return f"""Generate {self.max_variations - 1} alternative ways to search for information about this question.

Question: {query}

Provide {self.max_variations - 1} different search queries, one per line:
1."""

    def _parse_variation_response(self, response: str) -> List[str]:
        """Parse variations from LLM response."""
        variations = []

        # Try numbered list format
        lines = response.strip().split('\n')
        for line in lines:
            line = line.strip()
            # Remove numbering
            line = line.lstrip('0123456789.-* ')
            if line and len(line) > 3:  # Minimum meaningful length
                variations.append(line)

        return variations


class HyDEQueryExpander:
    """
    Hypothetical Document Embeddings (HyDE) query expansion.

    Generates a hypothetical answer to the query, then uses
    that for retrieval. This can improve semantic search.
    """

    def __init__(
        self,
        llm_client: ZhipuAIClient,
        max_hypothetical_length: int = 200,
    ):
        """
        Initialize HyDE expander.

        Args:
            llm_client: LLM client for generating hypothetical documents
            max_hypothetical_length: Max length of hypothetical answer
        """
        self.llm_client = llm_client
        self.max_length = max_hypothetical_length

    def generate_hypothetical(
        self,
        query: str,
        domain_hint: Optional[str] = None,
    ) -> str:
        """
        Generate a hypothetical answer to use for retrieval.

        Args:
            query: User's query
            domain_hint: Optional hint about the domain

        Returns:
            Hypothetical answer text
        """
        prompt = self._get_hyde_prompt(query, domain_hint)

        try:
            response = self.llm_client.generate(
                prompt,
                temperature=0.7,  # Higher for more diverse hypotheticals
                max_tokens=self.max_length,
            )

            return response.strip()
        except Exception as e:
            logger.warning(f"HyDE generation failed: {e}")
            return query  # Fallback to original query

    def _get_hyde_prompt(self, query: str, domain_hint: Optional[str]) -> str:
        """Generate prompt for hypothetical document."""
        if domain_hint:
            return f"""Given this question about {domain_hint}, write a brief hypothetical answer that would contain the relevant information:

Question: {query}

Hypothetical answer:"""
        else:
            return f"""Given this question, write a brief hypothetical answer that would contain the relevant information:

Question: {query}

Hypothetical answer:"""


class QueryExpansionPipeline:
    """
    Complete query expansion pipeline.

    Combines multiple expansion strategies for optimal retrieval.
    """

    def __init__(
        self,
        llm_client: Optional[ZhipuAIClient] = None,
        enable_rewriting: bool = True,
        enable_variations: bool = True,
        enable_hyde: bool = False,
        enable_acronym_expansion: bool = True,
    ):
        """
        Initialize expansion pipeline.

        Args:
            llm_client: LLM client for advanced expansion
            enable_rewriting: Enable query rewriting
            enable_variations: Enable query variations
            enable_hyde: Enable HyDE expansion
            enable_acronym_expansion: Enable acronym expansion
        """
        self.enable_rewriting = enable_rewriting
        self.enable_variations = enable_variations
        self.enable_hyde = enable_hyde

        if enable_rewriting or enable_variations or enable_hyde:
            self.expander = QueryExpander(
                llm_client=llm_client,
                enable_acronym_expansion=enable_acronym_expansion,
            )

        if enable_hyde and llm_client:
            self.hyde = HyDEQueryExpander(llm_client)

    def process_query(
        self,
        query: str,
        context: Optional[str] = None,
        domain_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process query through the expansion pipeline.

        Args:
            query: Original query
            context: Optional context
            domain_hint: Optional domain hint for HyDE

        Returns:
            Dictionary with original_query, rewritten_query, variations,
            and hypothetical_answer (if enabled)
        """
        result = {
            'original_query': query,
            'rewritten_query': query,
            'variations': [query],
            'hypothetical_answer': None,
        }

        # Rewrite query
        if self.enable_rewriting and hasattr(self, 'expander'):
            result['rewritten_query'] = self.expander.rewrite_query(
                query, context
            )

        # Generate variations
        if self.enable_variations and hasattr(self, 'expander'):
            result['variations'] = self.expander.expand_query(
                result['rewritten_query'], context
            )

        # Generate HyDE
        if self.enable_hyde and hasattr(self, 'hyde'):
            result['hypothetical_answer'] = self.hyde.generate_hypothetical(
                query, domain_hint
            )

        return result

    def get_search_queries(self, query: str) -> List[str]:
        """
        Get list of queries to use for search.

        Args:
            query: Original query

        Returns:
            List of queries to use for retrieval
        """
        result = self.process_query(query)

        queries = [result['rewritten_query']]
        queries.extend(result['variations'][1:])  # Skip first (is rewritten)

        if result['hypothetical_answer']:
            queries.append(result['hypothetical_answer'])

        # Remove duplicates
        seen = set()
        unique = []
        for q in queries:
            if q.lower() not in seen:
                seen.add(q.lower())
                unique.append(q)

        return unique
