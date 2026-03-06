"""
Confidence Scorer Module

This module provides functionality to calculate confidence scores for retrieval results.
It determines whether a query has HIGH, MEDIUM, or LOW confidence based on the top score
and the spread between the top and second scores.

Confidence Levels:
- HIGH: top_score > 0.7 AND score_spread > 0.2
- MEDIUM: top_score > 0.4
- LOW: top_score <= 0.4
"""

from enum import Enum
from typing import List, Tuple, Optional


class ConfidenceLevel(Enum):
    """Enum representing confidence levels for retrieval results."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceScorer:
    """
    Calculates confidence scores for retrieval results.

    The confidence is determined based on:
    1. The top retrieval score (how well the best result matches)
    2. The score spread (difference between top and second scores)

    A high score spread indicates clear winner, increasing confidence.
    """

    # Confidence thresholds
    HIGH_SCORE_THRESHOLD = 0.7
    MEDIUM_SCORE_THRESHOLD = 0.4
    HIGH_SPREAD_THRESHOLD = 0.2

    @staticmethod
    def calculate_confidence(scores: List[float]) -> Tuple[ConfidenceLevel, float, float]:
        """
        Calculate confidence level based on retrieval scores.

        Args:
            scores: List of retrieval scores sorted in descending order.

        Returns:
            Tuple of (confidence_level, top_score, score_spread)

        Raises:
            ValueError: If scores list is empty.
        """
        if not scores:
            raise ValueError("Scores list cannot be empty")

        # Get top score
        top_score = scores[0]

        # Calculate score spread (difference between top and second score)
        if len(scores) >= 2:
            score_spread = top_score - scores[1]
        else:
            # If only one score, consider spread as maximum confidence
            score_spread = 1.0

        # Determine confidence level
        confidence_level = ConfidenceScorer._determine_confidence(top_score, score_spread)

        return confidence_level, top_score, score_spread

    @staticmethod
    def _determine_confidence(top_score: float, score_spread: float) -> ConfidenceLevel:
        """
        Determine confidence level based on top score and spread.

        Args:
            top_score: The highest retrieval score.
            score_spread: Difference between top and second scores.

        Returns:
            ConfidenceLevel enum value.
        """
        # HIGH confidence: top score is high AND there's a clear winner (good spread)
        if top_score > ConfidenceScorer.HIGH_SCORE_THRESHOLD and score_spread > ConfidenceScorer.HIGH_SPREAD_THRESHOLD:
            return ConfidenceLevel.HIGH

        # MEDIUM confidence: top score is decent but may not have good spread
        if top_score > ConfidenceScorer.MEDIUM_SCORE_THRESHOLD:
            return ConfidenceLevel.MEDIUM

        # LOW confidence: top score is weak
        return ConfidenceLevel.LOW

    @staticmethod
    def get_confidence_description(confidence_level: ConfidenceLevel) -> str:
        """
        Get human-readable description of confidence level.

        Args:
            confidence_level: The confidence level to describe.

        Returns:
            String description of the confidence level.
        """
        descriptions = {
            ConfidenceLevel.HIGH: "High confidence: Top result is a clear match with significant score margin.",
            ConfidenceLevel.MEDIUM: "Medium confidence: Top result is relevant but may not be the best match.",
            ConfidenceLevel.LOW: "Low confidence: No strong matches found. Consider rephrasing the query."
        }
        return descriptions.get(confidence_level, "Unknown confidence level")

    @staticmethod
    def should_use_result(confidence_level: ConfidenceLevel) -> bool:
        """
        Determine if results should be used based on confidence level.

        Args:
            confidence_level: The confidence level to evaluate.

        Returns:
            True if results should be used, False otherwise.
        """
        # Use results for HIGH and MEDIUM confidence
        return confidence_level in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]

    @staticmethod
    def suggest_action(confidence_level: ConfidenceLevel) -> str:
        """
        Suggest an action based on confidence level.

        Args:
            confidence_level: The confidence level to evaluate.

        Returns:
            String suggesting an action to take.
        """
        actions = {
            ConfidenceLevel.HIGH: "Use the top result directly.",
            ConfidenceLevel.MEDIUM: "Consider using the top result, but verify with user if possible.",
            ConfidenceLevel.LOW: "Consider query reformulation or hybrid search strategies."
        }
        return actions.get(confidence_level, "Unknown confidence level")
