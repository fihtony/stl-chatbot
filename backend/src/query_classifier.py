"""Query complexity classifier for adaptive RAG.

This module analyzes query complexity to determine the optimal retrieval strategy:
- Simple: Direct LLM response (no retrieval needed)
- Medium: Single-step retrieval
- Complex: Multi-step retrieval with query expansion
"""

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from sentence_transformers import CrossEncoder

# Configure logging
logger = logging.getLogger(__name__)


class QueryComplexity(Enum):
    """Query complexity levels."""
    SIMPLE = "simple"      # Direct LLM response
    MEDIUM = "medium"      # Single-step retrieval
    COMPLEX = "complex"    # Multi-step retrieval


class RetrievalStrategy(Enum):
    """Retrieval strategies based on complexity."""
    NO_RETRIEVAL = "none"          # Use LLM knowledge only
    SINGLE_STEP = "single"         # One retrieval pass
    MULTI_STEP = "multi"           # Multiple retrieval passes


@dataclass
class QueryAnalysis:
    """Result of query analysis."""
    complexity: QueryComplexity
    strategy: RetrievalStrategy
    reasoning: str
    top_k: int
    use_variations: bool


class QueryComplexityClassifier:
    """
    Classifies query complexity using heuristic rules.

    Features analyzed:
    - Token count
    - Number of entities (capitalized words)
    - Question words
    - Logical connectors (and, or, but, etc.)
    - Nested questions
    """

    # Simple question patterns
    SIMPLE_PATTERNS = [
        r'^what is [a-z\s]+$',
        r'^who is [a-z\s]+$',
        r'^where is [a-z\s]+$',
        r'^define \w+$',
        r'^explain \w+$',
    ]

    # Logical connectors indicating complexity
    LOGICAL_CONNECTORS = [
        'and', 'or', 'but', 'however', 'therefore',
        'because', 'although', 'while', 'whereas',
        'versus', 'compared to', 'difference between'
    ]

    # Words indicating multi-hop reasoning
    MULTI_HOP_INDICATORS = [
        'relationship between', 'how does', 'affect',
        'impact', 'influence', 'cause', 'lead to',
        'result in', 'connection', 'compare'
    ]

    def __init__(
        self,
        simple_threshold: int = 6,
        complex_threshold: int = 15,
        medium_top_k: int = 5,
        complex_top_k: int = 10,
    ):
        """
        Initialize classifier.

        Args:
            simple_threshold: Max tokens for simple classification
            complex_threshold: Min tokens for complex classification
            medium_top_k: Default top_k for medium queries
            complex_top_k: Default top_k for complex queries
        """
        self.simple_threshold = simple_threshold
        self.complex_threshold = complex_threshold
        self.medium_top_k = medium_top_k
        self.complex_top_k = complex_top_k

    def classify(self, query: str) -> QueryAnalysis:
        """
        Classify query complexity and determine retrieval strategy.

        Args:
            query: User query string

        Returns:
            QueryAnalysis with complexity, strategy, and recommendations
        """
        query = query.strip()
        tokens = query.split()
        token_count = len(tokens)

        # Extract features
        entities = self._extract_entities(query)
        entity_count = len(entities)
        has_logical = self._has_logical_connectors(query)
        has_multi_hop = self._has_multi_hop_indicators(query)
        has_nested = self._has_nested_questions(query)

        # Determine complexity
        complexity = self._determine_complexity(
            token_count, entity_count, has_logical,
            has_multi_hop, has_nested
        )

        # Determine strategy based on complexity
        strategy, top_k, use_variations = self._get_strategy(complexity)

        # Generate reasoning
        reasoning = self._generate_reasoning(
            complexity, token_count, entity_count,
            has_logical, has_multi_hop, has_nested
        )

        return QueryAnalysis(
            complexity=complexity,
            strategy=strategy,
            reasoning=reasoning,
            top_k=top_k,
            use_variations=use_variations,
        )

    def _extract_entities(self, query: str) -> List[str]:
        """Extract capitalized words as potential entities."""
        # Match words starting with capital letter (not at start)
        entities = re.findall(r'\b[A-Z][a-z]+\b', query)
        return list(set(entities))

    def _has_logical_connectors(self, query: str) -> bool:
        """Check if query has logical connectors."""
        query_lower = query.lower()
        return any(connector in query_lower for connector in self.LOGICAL_CONNECTORS)

    def _has_multi_hop_indicators(self, query: str) -> bool:
        """Check if query requires multi-hop reasoning."""
        query_lower = query.lower()
        return any(indicator in query_lower for indicator in self.MULTI_HOP_INDICATORS)

    def _has_nested_questions(self, query: str) -> bool:
        """Check if query has nested questions."""
        # Count question marks
        qmark_count = query.count('?')
        return qmark_count > 1

    def _determine_complexity(
        self,
        token_count: int,
        entity_count: int,
        has_logical: bool,
        has_multi_hop: bool,
        has_nested: bool,
    ) -> QueryComplexity:
        """Determine complexity based on features."""
        # Check for simple patterns first
        if token_count <= self.simple_threshold and entity_count <= 1:
            if not (has_logical or has_multi_hop or has_nested):
                return QueryComplexity.SIMPLE

        # Check for complex patterns
        if (
            token_count >= self.complex_threshold or
            has_multi_hop or
            has_nested or
            (has_logical and entity_count >= 2)
        ):
            return QueryComplexity.COMPLEX

        # Default to medium
        return QueryComplexity.MEDIUM

    def _get_strategy(
        self,
        complexity: QueryComplexity,
    ) -> Tuple[RetrievalStrategy, int, bool]:
        """Get retrieval strategy based on complexity."""
        if complexity == QueryComplexity.SIMPLE:
            # Simple queries might not need retrieval
            return (
                RetrievalStrategy.SINGLE_STEP,
                3,  # Smaller top_k for simple queries
                False  # No variations needed
            )
        elif complexity == QueryComplexity.MEDIUM:
            return (
                RetrievalStrategy.SINGLE_STEP,
                self.medium_top_k,
                False
            )
        else:  # COMPLEX
            return (
                RetrievalStrategy.MULTI_STEP,
                self.complex_top_k,
                True  # Use query variations
            )

    def _generate_reasoning(
        self,
        complexity: QueryComplexity,
        token_count: int,
        entity_count: int,
        has_logical: bool,
        has_multi_hop: bool,
        has_nested: bool,
    ) -> str:
        """Generate human-readable reasoning for classification."""
        parts = [f"Token count: {token_count}, Entities: {entity_count}"]

        if has_logical:
            parts.append("has logical connectors")
        if has_multi_hop:
            parts.append("requires multi-hop reasoning")
        if has_nested:
            parts.append("has nested questions")

        reason = ", ".join(parts)
        return f"Classified as {complexity.value}: {reason}"


class SemanticQueryClassifier:
    """
    Uses a cross-encoder model to classify query complexity.

    This is more accurate but slower than the heuristic classifier.
    Uses the same model as the reranker for efficiency.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        simple_threshold: float = 0.3,
        complex_threshold: float = 0.7,
    ):
        """
        Initialize semantic classifier.

        Args:
            model_name: Cross-encoder model name
            simple_threshold: Score below which query is simple
            complex_threshold: Score above which query is complex
        """
        self.model = CrossEncoder(model_name)
        self.simple_threshold = simple_threshold
        self.complex_threshold = complex_threshold

    def classify_by_retrieval_need(
        self,
        query: str,
        sample_documents: List[str],
    ) -> QueryAnalysis:
        """
        Classify query by analyzing retrieval need.

        Scores the query against sample documents to determine
        how much retrieval is needed.

        Args:
            query: User query
            sample_documents: Sample documents to score against

        Returns:
            QueryAnalysis with complexity assessment
        """
        if not sample_documents:
            # No documents available, treat as medium complexity
            return QueryAnalysis(
                complexity=QueryComplexity.MEDIUM,
                strategy=RetrievalStrategy.SINGLE_STEP,
                reasoning="No sample documents available for classification",
                top_k=5,
                use_variations=False,
            )

        # Score query against documents
        pairs = [[query, doc] for doc in sample_documents[:5]]
        scores = self.model.predict(pairs)
        max_score = float(max(scores)) if len(scores) > 0 else 0.0

        # Classify based on max score
        if max_score < self.simple_threshold:
            complexity = QueryComplexity.SIMPLE
            strategy = RetrievalStrategy.SINGLE_STEP
            top_k = 3
            use_variations = False
        elif max_score > self.complex_threshold:
            complexity = QueryComplexity.COMPLEX
            strategy = RetrievalStrategy.MULTI_STEP
            top_k = 10
            use_variations = True
        else:
            complexity = QueryComplexity.MEDIUM
            strategy = RetrievalStrategy.SINGLE_STEP
            top_k = 5
            use_variations = False

        return QueryAnalysis(
            complexity=complexity,
            strategy=strategy,
            reasoning=f"Max retrieval score: {max_score:.3f}",
            top_k=top_k,
            use_variations=use_variations,
        )
