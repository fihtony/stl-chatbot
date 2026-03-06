"""Document reranker for improved retrieval accuracy.

Uses free, open-source cross-encoder models to rerank retrieved documents
by their relevance to the query. Can improve retrieval accuracy by 15-25%.

Models supported:
- ms-marco-MiniLM-L-6-v2: Fast, good quality (~80MB)
- ms-marco-MiniLM-L-12-v2: Better quality, slower (~350MB)
- bge-reranker-base: Multilingual support
"""

import logging
from typing import List, Dict, Any, Optional

from sentence_transformers import CrossEncoder

# Configure logging
logger = logging.getLogger(__name__)


class DocumentReranker:
    """
    Reranks documents using a cross-encoder model.

    The cross-encoder scores query-document pairs for relevance,
    allowing more accurate ranking than vector similarity alone.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        max_length: int = 512,
        batch_size: int = 32,
        device: Optional[str] = None,
    ):
        """
        Initialize reranker.

        Args:
            model_name: Cross-encoder model to use
            max_length: Max sequence length for the model
            batch_size: Batch size for inference
            device: Device to run on (cpu/cuda, auto-detect if None)
        """
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size

        logger.info(f"Loading reranker model: {model_name}")
        self.model = CrossEncoder(
            model_name,
            max_length=max_length,
            device=device,
        )
        logger.info(f"Reranker loaded: {model_name}")

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents by relevance to query.

        Args:
            query: User query
            documents: List of document dicts with 'content' or 'text' field
            top_k: Number of top documents to return (None = all)
            score_threshold: Minimum score threshold (None = no threshold)

        Returns:
            Reranked list of documents, with added 'rerank_score' field
        """
        if not documents:
            return []

        # Extract text content from documents
        doc_texts = []
        for doc in documents:
            text = doc.get('content') or doc.get('text') or ''
            # Truncate if too long
            if len(text) > self.max_length * 3:  # Rough char estimate
                text = text[:self.max_length * 3]
            doc_texts.append(text)

        # Create query-document pairs
        pairs = [[query, text] for text in doc_texts]

        # Score pairs
        try:
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Return original documents on error
            return documents

        # Add scores to documents and sort
        scored_docs = []
        for doc, score in zip(documents, scores):
            doc_copy = doc.copy()
            doc_copy['rerank_score'] = float(score)
            scored_docs.append(doc_copy)

        # Sort by score (descending)
        scored_docs.sort(key=lambda d: d['rerank_score'], reverse=True)

        # Apply threshold if specified
        if score_threshold is not None:
            scored_docs = [
                d for d in scored_docs
                if d['rerank_score'] >= score_threshold
            ]

        # Apply top_k if specified
        if top_k is not None:
            scored_docs = scored_docs[:top_k]

        return scored_docs

    def rerank_with_fallback(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        original_scores: Optional[str] = 'score',
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents with fallback to original scores.

        If reranking fails, preserves original order and scores.

        Args:
            query: User query
            documents: List of document dicts
            top_k: Number of top documents to return
            original_scores: Field name for original relevance scores

        Returns:
            Reranked list of documents
        """
        try:
            reranked = self.rerank(query, documents, top_k)
            return reranked
        except Exception as e:
            logger.warning(f"Reranking failed, using original order: {e}")
            # Sort by original scores if available
            if original_scores and documents:
                scored = [
                    d for d in documents
                    if original_scores in d
                ]
                scored.sort(
                    key=lambda d: d[original_scores],
                    reverse=True
                )
                if top_k:
                    scored = scored[:top_k]
                return scored
            return documents[:top_k] if top_k else documents

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        return {
            "model_name": self.model_name,
            "max_length": self.max_length,
            "parameters": sum(p.numel() for p in self.model.model.parameters()),
        }


class HybridReranker:
    """
    Combines vector similarity with cross-encoder scores.

    This approach can be more robust than using either method alone.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        vector_weight: float = 0.3,
        rerank_weight: float = 0.7,
    ):
        """
        Initialize hybrid reranker.

        Args:
            model_name: Cross-encoder model name
            vector_weight: Weight for vector similarity scores
            rerank_weight: Weight for reranker scores
        """
        self.reranker = DocumentReranker(model_name)
        self.vector_weight = vector_weight
        self.rerank_weight = rerank_weight

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank using combined vector and cross-encoder scores.

        Args:
            query: User query
            documents: List of documents with 'score' (vector similarity)
            top_k: Number of top documents to return

        Returns:
            Reranked documents with 'combined_score' field
        """
        if not documents:
            return []

        # First get reranker scores
        reranked = self.reranker.rerank(query, documents)

        # Normalize and combine scores
        max_vector = max((d.get('score', 0) for d in documents), default=1.0)
        max_rerank = max((d.get('rerank_score', 0) for d in reranked), default=1.0)

        for doc in reranked:
            vector_score = doc.get('score', 0) / max_vector if max_vector > 0 else 0
            rerank_score = doc.get('rerank_score', 0) / max_rerank if max_rerank > 0 else 0

            doc['combined_score'] = (
                self.vector_weight * vector_score +
                self.rerank_weight * rerank_score
            )

        # Sort by combined score
        reranked.sort(key=lambda d: d['combined_score'], reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked


# Pre-configured rerankers for common use cases
RERANKER_FAST = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_QUALITY = "cross-encoder/ms-marco-MiniLM-L-12-v2"
RERANKER_MULTILINGUAL = "BAAI/bge-reranker-base"


def create_reranker(
    quality: str = "fast",
    multilingual: bool = False,
) -> DocumentReranker:
    """
    Factory function to create a pre-configured reranker.

    Args:
        quality: "fast" or "quality" - speed vs accuracy tradeoff
        multilingual: Whether to use a multilingual model

    Returns:
        Configured DocumentReranker instance
    """
    if multilingual:
        model_name = RERANKER_MULTILINGUAL
    elif quality == "quality":
        model_name = RERANKER_QUALITY
    else:
        model_name = RERANKER_FAST

    return DocumentReranker(model_name=model_name)
