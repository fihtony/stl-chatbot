"""Performance monitoring for RAG pipeline operations.

This module provides tools to track and analyze performance metrics
across different stages of the retrieval and generation pipeline.
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QueryRecord:
    """Represents a single query performance record.

    Attributes:
        query_id: Unique identifier for the query
        timestamp: When the query was executed
        query: The query text
        stages: Dictionary mapping stage names to their duration in seconds
        total_time: Total time for the entire query
        metadata: Additional metadata about the query
    """
    query_id: str
    timestamp: datetime
    query: str
    stages: Dict[str, float] = field(default_factory=dict)
    total_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "query_id": self.query_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "query": self.query,
            "stages": self.stages,
            "total_time": self.total_time,
            "metadata": self.metadata
        }


@dataclass
class StageStats:
    """Statistics for a specific pipeline stage.

    Attributes:
        stage_name: Name of the stage
        count: Number of recorded executions
        mean: Mean execution time
        median: Median execution time
        min: Minimum execution time
        max: Maximum execution time
        p50: 50th percentile (median)
        p75: 75th percentile
        p90: 90th percentile
        p95: 95th percentile
        p99: 99th percentile
        std: Standard deviation
    """
    stage_name: str
    count: int
    mean: float
    median: float
    min: float
    max: float
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    std: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "stage_name": self.stage_name,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "min": self.min,
            "max": self.max,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
            "p95": self.p95,
            "p99": self.p99,
            "std": self.std
        }


class StageTimer:
    """Context manager for timing a specific stage of the pipeline.

    Example:
        monitor = PerformanceMonitor()
        with monitor.stage_timer("retrieval", query_id="123"):
            # Perform retrieval
            results = retriever.retrieve(query)
    """

    def __init__(self, monitor: 'PerformanceMonitor', stage_name: str,
                 query_id: Optional[str] = None):
        """Initialize the stage timer.

        Args:
            monitor: The PerformanceMonitor instance
            stage_name: Name of the stage being timed
            query_id: Optional query ID for tracking
        """
        self.monitor = monitor
        self.stage_name = stage_name
        self.query_id = query_id
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self) -> 'StageTimer':
        """Start the timer."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the timer and record the stage duration."""
        if self.start_time is not None:
            self.end_time = time.perf_counter()
            duration = self.end_time - self.start_time
            self.monitor.record_stage(self.stage_name, duration, self.query_id)
        return False


class PerformanceMonitor:
    """Monitor and track performance metrics for RAG pipeline operations.

    This class provides functionality to:
    - Time individual stages of the pipeline using StageTimer context manager
    - Record query execution times
    - Calculate statistics (mean, median, percentiles) for each stage
    - Track query history for analysis

    Example:
        monitor = PerformanceMonitor()

        # Time a specific stage
        with monitor.stage_timer("embedding", query_id="query_1"):
            embedding = embedder.embed(query)

        # Record a complete query
        monitor.record_query("query_1", "What is RAG?",
                            {"embedding": 0.1, "retrieval": 0.5})

        # Get statistics
        stats = monitor.get_stage_stats("embedding")
        print(f"Mean embedding time: {stats.mean:.3f}s")
    """

    def __init__(self, max_history: int = 10000):
        """Initialize the performance monitor.

        Args:
            max_history: Maximum number of query records to keep in memory
        """
        self.max_history = max_history
        self._stage_times: Dict[str, List[float]] = defaultdict(list)
        self._query_records: Dict[str, QueryRecord] = {}
        self._query_counter = 0

        # Additional tracking structures for API compatibility
        self._by_language: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_ms": 0.0}
        )
        self._by_path: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_ms": 0.0}
        )
        self._query_times: List[float] = []

    def stage_timer(self, stage_name: str,
                   query_id: Optional[str] = None) -> StageTimer:
        """Create a context manager for timing a stage.

        Args:
            stage_name: Name of the stage to time
            query_id: Optional query ID to associate with this timing

        Returns:
            StageTimer context manager
        """
        return StageTimer(self, stage_name, query_id)

    def record_stage(self, stage_name: str, duration: float,
                    query_id: Optional[str] = None) -> None:
        """Record the duration of a stage execution.

        Args:
            stage_name: Name of the stage
            duration: Duration in seconds
            query_id: Optional query ID to associate with this timing
        """
        self._stage_times[stage_name].append(duration)

        # Also record to query if provided
        if query_id:
            # Auto-create query record if it doesn't exist
            if query_id not in self._query_records:
                self._query_records[query_id] = QueryRecord(
                    query_id=query_id,
                    timestamp=datetime.now(),
                    query="",  # Will be filled in by record_query if needed
                    stages={},
                    total_time=0.0
                )
            # Add stage and update total time
            self._query_records[query_id].stages[stage_name] = duration
            self._query_records[query_id].total_time += duration

        logger.debug(f"Recorded stage {stage_name}: {duration:.4f}s")

    def record_query(self, query_id: str, query: str,
                    stages: Dict[str, float],
                    total_time: Optional[float] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a complete query with its stage timings.

        Args:
            query_id: Unique identifier for the query
            query: The query text
            stages: Dictionary mapping stage names to durations
            total_time: Optional total time (calculated from stages if not provided)
            metadata: Optional additional metadata
        """
        # Calculate total time if not provided
        if total_time is None:
            total_time = sum(stages.values())

        # Create query record
        record = QueryRecord(
            query_id=query_id,
            timestamp=datetime.now(),
            query=query,
            stages=stages.copy(),
            total_time=total_time,
            metadata=metadata or {}
        )

        # Store record
        self._query_records[query_id] = record

        # Update stage times
        for stage_name, duration in stages.items():
            self._stage_times[stage_name].append(duration)

        # Manage history size
        if len(self._query_records) > self.max_history:
            # Remove oldest query (FIFO)
            oldest_id = min(self._query_records.keys(),
                           key=lambda k: self._query_records[k].timestamp)
            del self._query_records[oldest_id]

        logger.info(f"Recorded query {query_id}: {total_time:.4f}s total")

    def get_stage_stats(self, stage_name: str) -> Optional[StageStats]:
        """Calculate statistics for a specific stage.

        Args:
            stage_name: Name of the stage

        Returns:
            StageStats object or None if stage has no recorded times
        """
        if stage_name not in self._stage_times or not self._stage_times[stage_name]:
            return None

        times = np.array(self._stage_times[stage_name])

        return StageStats(
            stage_name=stage_name,
            count=len(times),
            mean=float(np.mean(times)),
            median=float(np.median(times)),
            min=float(np.min(times)),
            max=float(np.max(times)),
            p50=float(np.percentile(times, 50)),
            p75=float(np.percentile(times, 75)),
            p90=float(np.percentile(times, 90)),
            p95=float(np.percentile(times, 95)),
            p99=float(np.percentile(times, 99)),
            std=float(np.std(times))
        )

    def get_all_stage_stats(self) -> Dict[str, StageStats]:
        """Get statistics for all stages.

        Returns:
            Dictionary mapping stage names to StageStats objects
        """
        stats = {}
        for stage_name in self._stage_times:
            stage_stats = self.get_stage_stats(stage_name)
            if stage_stats:
                stats[stage_name] = stage_stats
        return stats

    def get_query_record(self, query_id: str) -> Optional[QueryRecord]:
        """Get a specific query record.

        Args:
            query_id: Query identifier

        Returns:
            QueryRecord or None if not found
        """
        return self._query_records.get(query_id)

    def get_recent_queries(self, n: int = 10) -> List[QueryRecord]:
        """Get the most recent query records.

        Args:
            n: Number of recent queries to return

        Returns:
            List of QueryRecord objects, sorted by timestamp (newest first)
        """
        records = list(self._query_records.values())
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records[:n]

    def get_stage_times(self, stage_name: str) -> List[float]:
        """Get all recorded times for a specific stage.

        Args:
            stage_name: Name of the stage

        Returns:
            List of duration values in seconds
        """
        return self._stage_times.get(stage_name, []).copy()

    def get_stage_count(self, stage_name: str) -> int:
        """Get the number of recorded executions for a stage.

        Args:
            stage_name: Name of the stage

        Returns:
            Number of recorded executions
        """
        return len(self._stage_times.get(stage_name, []))

    def clear(self) -> None:
        """Clear all recorded data."""
        self._stage_times.clear()
        self._query_records.clear()
        self._query_counter = 0
        self._by_language.clear()
        self._by_path.clear()
        self._query_times.clear()
        logger.info("Performance monitor cleared")

    def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive performance report.

        Returns:
            Dictionary containing performance metrics and statistics
        """
        stats = self.get_all_stage_stats()

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(self._query_records),
            "stages": {}
        }

        for stage_name, stage_stats in stats.items():
            report["stages"][stage_name] = stage_stats.to_dict()

        return report

    def get_slow_queries(self, threshold: float,
                        n: int = 10) -> List[QueryRecord]:
        """Get queries that exceeded a time threshold.

        Args:
            threshold: Time threshold in seconds
            n: Maximum number of queries to return

        Returns:
            List of slow QueryRecord objects, sorted by total time (slowest first)
        """
        slow_queries = [
            r for r in self._query_records.values()
            if r.total_time > threshold
        ]
        slow_queries.sort(key=lambda r: r.total_time, reverse=True)
        return slow_queries[:n]

    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics in the format expected by the API.

        Returns:
            Dict with stages, by_language, by_path, and query_times
        """
        # Calculate stage averages from _stage_times
        stages = {}
        for stage_name, times in self._stage_times.items():
            if times:
                total_ms = sum(t * 1000 for t in times)  # Convert seconds to ms
                stages[stage_name] = {
                    "count": len(times),
                    "total_ms": round(total_ms, 2),
                    "avg_ms": round(total_ms / len(times), 2) if times else 0
                }

        # Convert defaultdicts to regular dicts for JSON serialization
        by_language = {k: {"count": v["count"], "total_ms": round(v["total_ms"], 2)}
                       for k, v in self._by_language.items()}
        by_path = {k: {"count": v["count"], "total_ms": round(v["total_ms"], 2)}
                   for k, v in self._by_path.items()}

        return {
            "stages": stages,
            "by_language": by_language,
            "by_path": by_path,
            "query_times": sorted(self._query_times)
        }

    def get_average_time(self) -> float:
        """Get average query response time in milliseconds."""
        if not self._query_times:
            return 0
        return round(sum(self._query_times) / len(self._query_times), 2)

    def get_percentile(self, percentile: int) -> float:
        """Get percentile of query response times.

        Args:
            percentile: Percentile to calculate (0-100)

        Returns:
            Response time in milliseconds at given percentile
        """
        if not self._query_times:
            return 0

        sorted_times = sorted(self._query_times)
        idx = int(len(sorted_times) * percentile / 100)
        idx = min(idx, len(sorted_times) - 1)
        return sorted_times[idx]

    # Wrapper methods for backward compatibility with the planned API
    def record_query_simple(self, language: str, path_type: str, elapsed_ms: float) -> None:
        """Record a query in the simple format expected by the plan.

        Args:
            language: Query language (fr, en, zh)
            path_type: Path taken (fast_path, standard_path)
            elapsed_ms: Total query time in milliseconds
        """
        # Track by language
        self._by_language[language]["count"] += 1
        self._by_language[language]["total_ms"] += elapsed_ms

        # Track by path
        self._by_path[path_type]["count"] += 1
        self._by_path[path_type]["total_ms"] += elapsed_ms

        # Track all times
        self._query_times.append(elapsed_ms)

        # Also record in the detailed format
        query_id = f"{language}_{path_type}_{len(self._query_times)}"
        self.record_query(
            query_id=query_id,
            query=f"{language} query",
            stages={},
            total_time=elapsed_ms / 1000,
            metadata={"language": language, "path": path_type}
        )
