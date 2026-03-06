"""
Temporal-aware search for date/time-based queries.

This module provides:
1. Temporal indexing of documents by date
2. Relative date interpretation ("latest", "last month", etc.)
3. Year inference from month when not specified
4. Alternative suggestions when exact match not found
"""
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import calendar

# French month names
FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    # Without accents
    "fevrier": 2, "decembre": 12,
    # Abbreviations
    "janv": 1, "fév": 2, "mars": 3, "avr": 4,
    "mai": 5, "juin": 6, "juil": 7, "août": 8,
    "sept": 9, "oct": 10, "nov": 11, "déc": 12,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # Special case for "mi-septembre"
    "mi-septembre": 9, "mi-sept": 9,
}

# English month names
ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Chinese month patterns (月份)
CHINESE_MONTHS = {
    "一月": 1, "二月": 2, "三月": 3, "四月": 4,
    "五月": 5, "六月": 6, "七月": 7, "八月": 8,
    "九月": 9, "十月": 10, "十一月": 11, "十二月": 12,
    "1月": 1, "2月": 2, "3月": 3, "4月": 4,
    "5月": 5, "6月": 6, "7月": 7, "8月": 8,
    "9月": 9, "10月": 10, "11月": 11, "12月": 12,
}

ALL_MONTHS = {**FRENCH_MONTHS, **ENGLISH_MONTHS, **CHINESE_MONTHS}


@dataclass
class TemporalRange:
    """Represents a time range for filtering documents."""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    year: Optional[int] = None
    month: Optional[int] = None

    def __str__(self):
        if self.year and self.month:
            return f"{self.year}-{self.month:02d}"
        elif self.year:
            return str(self.year)
        elif self.start_date and self.end_date:
            return f"{self.start_date.date()} to {self.end_date.date()}"
        return "unknown"


@dataclass
class TemporalQuery:
    """Represents a temporal query with interpreted dates."""
    original_query: str
    temporal_range: TemporalRange
    query_type: str  # "latest", "specific_month", "relative", "none"
    inferred_year: Optional[int] = None
    confidence: float = 1.0  # 0-1, how confident we are in the interpretation


class TemporalIndex:
    """
    Index for temporal search - maps dates to document chunks.
    """

    def __init__(self):
        # Maps (year, month) -> list of chunk_ids
        self.monthly_index: Dict[Tuple[int, int], List[str]] = {}

        # Maps chunk_id -> (year, month, date_str)
        self.chunk_dates: Dict[str, Tuple[int, int, str]] = {}

        # All available dates in the index
        self.available_dates: List[Tuple[int, int]] = []

    def add_chunk(self, chunk_id: str, metadata: Dict[str, Any]):
        """Add a chunk to the temporal index."""
        # Extract date from metadata
        date_info = self._extract_date_from_metadata(metadata)
        if date_info:
            year, month, date_str = date_info
            self.chunk_dates[chunk_id] = (year, month, date_str)

            # Only index if we have both year and month
            if month:
                key = (year, month)
                if key not in self.monthly_index:
                    self.monthly_index[key] = []
                    self.available_dates.append(key)
                if chunk_id not in self.monthly_index[key]:
                    self.monthly_index[key].append(chunk_id)

                # Keep sorted by date (newest first) - only sort entries with both year and month
                self.available_dates = sorted(
                    [d for d in self.available_dates if d[1] is not None],
                    key=lambda x: (x[0], x[1]),
                    reverse=True
                )

    def _extract_date_from_metadata(self, metadata: Dict[str, Any]) -> Optional[Tuple[int, int, str]]:
        """Extract date from metadata."""
        source = metadata.get("source", "")

        # Try various date patterns
        # Info-parents patterns - handle "Info-parents-de-fevrier-2026.pdf" format
        patterns = [
            # Info-parents with hyphens: Info-parents-de-fevrier-2026
            r"info-parents[^a-z0-9]*de[^a-z0-9]*([a-zA-ZÀ-ÿ]+)[^a-z0-9]*(\d{4})",
            # YYYY-MM format
            r"(\d{4})-(\d{2})",
            # YYYY MonthName or MonthName YYYY
            r"(\d{4})\s*(?:de)?\s*([a-zA-ZÀ-ÿ\u4e00-\u9fff]+)",
            r"(?:de\s*)?([a-zA-ZÀ-ÿ\u4e00-\u9fff]+)\s*(?:de)?\s*(\d{4})",
            # MonthName YYYY in various formats
            r"([a-zA-ZÀ-ÿ\u4e00-\u9fff]+)[^a-z0-9]*(\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, source, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    # Determine which group is year and which is month
                    group0, group1 = groups

                    # Check if first group is a 4-digit year
                    if group0.isdigit() and len(group0) == 4:
                        year = int(group0)
                        month_str = group1.lower()
                    # Check if second group is a 4-digit year
                    elif group1.isdigit() and len(group1) == 4:
                        year = int(group1)
                        month_str = group0.lower()
                    else:
                        continue

                    # Convert month name to number
                    month = ALL_MONTHS.get(month_str)
                    if month:
                        return year, month, f"{year}-{month:02d}"

        # Try to find just a year
        year_match = re.search(r"\b(20\d{2})\b", source)
        if year_match:
            year = int(year_match.group(1))
            return year, None, str(year)

        return None

    def get_chunks_for_date(self, year: int, month: Optional[int] = None) -> List[str]:
        """Get chunk IDs for a specific year/month."""
        if month:
            return self.monthly_index.get((year, month), [])
        else:
            # Get all chunks for the year
            chunks = []
            for (y, m), chunk_list in self.monthly_index.items():
                if y == year:
                    chunks.extend(chunk_list)
            return chunks

    def get_latest_date(self) -> Optional[Tuple[int, int]]:
        """Get the most recent date in the index."""
        if self.available_dates:
            return self.available_dates[0]
        return None

    def get_dates_around(self, year: int, month: int, radius: int = 1) -> List[Tuple[int, int]]:
        """Get dates within `radius` months of the given date."""
        result = []
        target_date = year * 100 + month

        for (y, m) in self.available_dates:
            date_val = y * 100 + m
            diff = abs(target_date - date_val)
            # Within radius months
            if diff <= radius * 100 + 12:  # Allow year transition
                result.append((y, m))

        return sorted(result, key=lambda x: (x[0], x[1]), reverse=True)

    def find_closest_date(self, year: int, month: Optional[int] = None) -> Optional[Tuple[int, int]]:
        """Find the closest available date to the given year/month."""
        if month:
            target = year * 100 + month
            closest = None
            min_diff = float('inf')

            for (y, m) in self.available_dates:
                date_val = y * 100 + m
                diff = abs(target - date_val)
                if diff < min_diff:
                    min_diff = diff
                    closest = (y, m)

            return closest
        else:
            # Find closest year
            years = set(y for y, m in self.available_dates)
            closest_year = min(years, key=lambda y: abs(y - year))
            return (closest_year, None)

    def date_exists(self, year: int, month: Optional[int] = None) -> bool:
        """Check if a date exists in the index."""
        if month:
            return (year, month) in self.monthly_index
        else:
            return any(y == year for y, m in self.available_dates)


class TemporalQueryProcessor:
    """
    Processes temporal queries and interprets relative dates.
    """

    def __init__(self, current_date: Optional[datetime] = None):
        # Default to March 2026 (most recent info-parents)
        # Or use actual current date if not specified
        if current_date is None:
            # Try to get the latest date from the temporal index if available
            self.current_date = datetime(2026, 3, 1)  # March 2026
        else:
            self.current_date = current_date

    def parse_query(self, query: str) -> TemporalQuery:
        """
        Parse a query and extract temporal information.

        Returns a TemporalQuery with interpreted dates.
        """
        query_lower = query.lower()

        # Check for "latest" queries
        if self._is_latest_query(query_lower):
            return self._parse_latest_query(query)

        # Check for relative time queries ("last month", "last year")
        relative_info = self._parse_relative_query(query_lower)
        if relative_info:
            return self._build_relative_temporal_query(query, relative_info)

        # Check for specific month/year queries
        specific_info = self._parse_specific_date_query(query_lower)
        if specific_info:
            return self._build_specific_temporal_query(query, specific_info)

        # No temporal information found
        return TemporalQuery(
            original_query=query,
            temporal_range=TemporalRange(),
            query_type="none",
            confidence=0.0
        )

    def _is_latest_query(self, query: str) -> bool:
        """Check if query is asking for latest information."""
        latest_patterns = [
            r"\blatest\b",
            r"\bnewest\b",
            r"\bmost recent\b",
            r"\bdernier\b",
            r"\bdernière\b",
            r"\brécents?\b",
            r"\brécent\b",
            r"\b最新的?\b",
            r"\b最近\b",
        ]
        return any(re.search(pattern, query) for pattern in latest_patterns)

    def _parse_latest_query(self, query: str) -> TemporalQuery:
        """Parse a 'latest' query."""
        return TemporalQuery(
            original_query=query,
            temporal_range=TemporalRange(
                start_date=self.current_date,
                end_date=self.current_date,
                year=self.current_date.year,
                month=self.current_date.month
            ),
            query_type="latest",
            inferred_year=self.current_date.year,
            confidence=0.9
        )

    def _parse_relative_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Parse relative time queries like 'last month', 'last year'."""
        # Last month patterns
        last_month_patterns = [
            r"\blast month\b",
            r"\bprevious month\b",
            r"\bmois dernier\b",
            r"\bmois précédent\b",
            r"\b上个月\b",
        ]

        # This month patterns
        this_month_patterns = [
            r"\bthis month\b",
            r"\bce mois\b",
            r"\b本月\b",
        ]

        # Last year patterns
        last_year_patterns = [
            r"\blast year\b",
            r"\bprevious year\b",
            r"\bl'année dernière\b",
            r"\blannée précédente\b",
            r"\b去年\b",
        ]

        # This year patterns
        this_year_patterns = [
            r"\bthis year\b",
            r"\bcette année\b",
            r"\b今年\b",
        ]

        for pattern in last_month_patterns:
            if re.search(pattern, query):
                # Calculate last month
                if self.current_date.month == 1:
                    target_date = self.current_date.replace(year=self.current_date.year - 1, month=12)
                else:
                    target_date = self.current_date.replace(month=self.current_date.month - 1)
                return {"type": "month", "date": target_date, "offset": -1}

        for pattern in this_month_patterns:
            if re.search(pattern, query):
                return {"type": "month", "date": self.current_date, "offset": 0}

        for pattern in last_year_patterns:
            if re.search(pattern, query):
                target_date = self.current_date.replace(year=self.current_date.year - 1)
                return {"type": "year", "date": target_date, "offset": -1}

        for pattern in this_year_patterns:
            if re.search(pattern, query):
                return {"type": "year", "date": self.current_date, "offset": 0}

        return None

    def _parse_specific_date_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Parse specific date queries like 'February 2026', 'fevrier', '2月'.
        """
        # Pattern: Month name (with or without year)
        # Matches: "february 2026", "fevrier", "二月", "feb 2026", etc.

        # Try to find month name
        for month_name, month_num in ALL_MONTHS.items():
            if month_name.lower() in query:
                # Check if year is specified
                year_match = re.search(r"\b(20\d{2})\b", query)

                if year_match:
                    year = int(year_match.group(1))
                    return {"type": "specific", "year": year, "month": month_num, "month_name": month_name}
                else:
                    # No year specified - will be inferred
                    return {"type": "specific_no_year", "month": month_num, "month_name": month_name}

        # Pattern: Just a year
        year_match = re.search(r"\b(20\d{2})\b", query)
        if year_match:
            return {"type": "year_only", "year": int(year_match.group(1))}

        return None

    def _build_relative_temporal_query(self, query: str, info: Dict[str, Any]) -> TemporalQuery:
        """Build TemporalQuery from relative time info."""
        date = info["date"]

        if info["type"] == "month":
            return TemporalQuery(
                original_query=query,
                temporal_range=TemporalRange(
                    year=date.year,
                    month=date.month,
                    start_date=date.replace(day=1),
                    end_date=self._end_of_month(date)
                ),
                query_type="relative",
                inferred_year=date.year,
                confidence=0.95
            )
        else:  # year
            return TemporalQuery(
                original_query=query,
                temporal_range=TemporalRange(
                    year=date.year,
                    start_date=date.replace(month=1, day=1),
                    end_date=date.replace(month=12, day=31)
                ),
                query_type="relative",
                inferred_year=date.year,
                confidence=0.95
            )

    def _build_specific_temporal_query(self, query: str, info: Dict[str, Any]) -> TemporalQuery:
        """Build TemporalQuery from specific date info."""
        if info["type"] == "specific":
            year = info["year"]
            month = info["month"]
            date = datetime(year, month, 1)

            return TemporalQuery(
                original_query=query,
                temporal_range=TemporalRange(
                    year=year,
                    month=month,
                    start_date=date,
                    end_date=self._end_of_month(date)
                ),
                query_type="specific_month",
                inferred_year=year,
                confidence=0.95
            )

        elif info["type"] == "specific_no_year":
            month = info["month"]

            # Infer year from current date
            current_year = self.current_date.year
            current_month = self.current_date.month

            # If the requested month is in the future relative to current month,
            # assume previous year
            if month > current_month:
                inferred_year = current_year - 1
            else:
                inferred_year = current_year

            date = datetime(inferred_year, month, 1)

            return TemporalQuery(
                original_query=query,
                temporal_range=TemporalRange(
                    year=inferred_year,
                    month=month,
                    start_date=date,
                    end_date=self._end_of_month(date)
                ),
                query_type="specific_month",
                inferred_year=inferred_year,
                confidence=0.8  # Lower confidence since year was inferred
            )

        elif info["type"] == "year_only":
            year = info["year"]
            return TemporalQuery(
                original_query=query,
                temporal_range=TemporalRange(
                    year=year,
                    start_date=datetime(year, 1, 1),
                    end_date=datetime(year, 12, 31)
                ),
                query_type="specific_year",
                inferred_year=year,
                confidence=0.95
            )

        # Fallback
        return TemporalQuery(
            original_query=query,
            temporal_range=TemporalRange(),
            query_type="none",
            confidence=0.0
        )

    def _end_of_month(self, date: datetime) -> datetime:
        """Get the last day of the month for a given date."""
        _, last_day = calendar.monthrange(date.year, date.month)
        return date.replace(day=last_day)


class TemporalSearchEnhancer:
    """
    Enhances search with temporal awareness and provides helpful suggestions.
    """

    def __init__(self, temporal_index: TemporalIndex, current_date: Optional[datetime] = None):
        self.temporal_index = temporal_index
        self.processor = TemporalQueryProcessor(current_date)

    def enhance_query(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        language: str = "en"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Enhance search results with temporal filtering and suggestions.

        Args:
            query: User query
            search_results: Search results to enhance
            language: Query language for localized messages

        Returns:
            (enhanced_results, metadata_with_suggestions)
        """
        temporal_query = self.processor.parse_query(query)

        # If no temporal info, return original results
        if temporal_query.query_type == "none":
            return search_results, {
                "temporal_query": temporal_query,
                "suggestions": None
            }

        # Filter results by temporal range
        filtered_results = self._filter_by_temporal_range(
            search_results,
            temporal_query.temporal_range
        )

        # Generate suggestions if needed
        suggestions = self._generate_suggestions(
            temporal_query,
            filtered_results,
            language
        )

        metadata = {
            "temporal_query": temporal_query,
            "suggestions": suggestions,
            "filtered_count": len(filtered_results),
            "original_count": len(search_results)
        }

        return filtered_results, metadata

    def _filter_by_temporal_range(
        self,
        results: List[Dict[str, Any]],
        temporal_range: TemporalRange
    ) -> List[Dict[str, Any]]:
        """Filter search results by temporal range."""
        if temporal_range.year is None:
            return results

        filtered = []
        for result in results:
            metadata = result.get("metadata", {})
            source = metadata.get("source", "")

            # Extract date from source using the temporal index
            date_info = self.temporal_index._extract_date_from_metadata(metadata)

            if date_info:
                year, month, _ = date_info

                # Check if matches temporal range
                if temporal_range.month:
                    # Year and month specified
                    if year == temporal_range.year and month == temporal_range.month:
                        filtered.append(result)
                else:
                    # Only year specified
                    if year == temporal_range.year:
                        filtered.append(result)
            else:
                # No date info, keep it
                filtered.append(result)

        return filtered

    def _generate_suggestions(
        self,
        temporal_query: TemporalQuery,
        filtered_results: List[Dict[str, Any]],
        language: str = "en"
    ) -> Optional[str]:
        """Generate helpful suggestions when exact match not found."""
        # If we have results, no suggestions needed
        if len(filtered_results) > 0:
            return None

        # No results found - generate suggestions
        suggestions = []

        if temporal_query.query_type == "specific_month":
            year = temporal_query.temporal_range.year
            month = temporal_query.temporal_range.month

            # Check if we have the same month in a different year
            for (y, m) in self.temporal_index.available_dates:
                if m == month and y != year:
                    month_name = get_month_name(m, language)
                    suggestions.append(f"{month_name} {y}")

            # Check for nearby months
            nearby = self.temporal_index.get_dates_around(year, month, radius=1)
            for (y, m) in nearby[:3]:  # Top 3 closest
                if (y, m) != (year, month):
                    month_name = get_month_name(m, language)
                    suggestions.append(f"{month_name} {y}")

            if suggestions:
                return self._format_suggestions(temporal_query, suggestions, language)

        elif temporal_query.query_type == "latest":
            # Suggest the latest available date with localized message
            latest = self.temporal_index.get_latest_date()
            if latest:
                year, month = latest
                month_name = get_month_name(month, language)

                latest_messages = {
                    "en": f"The latest available Info-parents is from {month_name} {year}.",
                    "fr": f"Les derniers Info-parents disponibles sont ceux de {month_name} {year}.",
                    "zh": f"最新的 Info-parents 是 {year}年{month_name} 的。",
                }
                return latest_messages.get(language, latest_messages["en"])

        return None

    def _format_suggestions(self, temporal_query: TemporalQuery, suggestions: List[str], language: str = "en") -> str:
        """Format suggestions into a helpful message with language support."""
        if temporal_query.query_type == "specific_month":
            inferred_year = temporal_query.inferred_year
            month = temporal_query.temporal_range.month

            month_name = get_month_name(month, language)

            # Localized messages
            not_found_messages = {
                "en": f"Sorry, I couldn't find Info-parents for {month_name} {inferred_year}.",
                "fr": f"Désolé, je n'ai pas trouvé d'Info-parents pour {month_name} {inferred_year}.",
                "zh": f"抱歉，我没有找到 {inferred_year}年{month_name} 的 Info-parents。",
            }

            assumed_messages = {
                "en": f" (I assumed you meant {inferred_year} since no year was specified)",
                "fr": f" (J'ai supposé que vous vouliez dire {inferred_year} car aucune année n'a été spécifiée)",
                "zh": f" （我假设您指的是 {inferred_year} 年，因为没有指定年份）",
            }

            found_messages = {
                "en": "\n\nHowever, I found Info-parents for:\n",
                "fr": "\n\nCependant, j'ai trouvé des Info-parents pour:\n",
                "zh": "\n\n不过，我找到了以下月份的 Info-parents：\n",
            }

            msg = not_found_messages.get(language, not_found_messages["en"])

            if temporal_query.confidence < 0.9:
                msg += assumed_messages.get(language, assumed_messages["en"])

            if suggestions:
                msg += found_messages.get(language, found_messages["en"])
                msg += "\n".join(f"  - {s}" for s in suggestions[:5])

            return msg

        # Default fallback message
        fallback_messages = {
            "en": "Sorry, I couldn't find what you're looking for.",
            "fr": "Désolé, je n'ai pas trouvé ce que vous cherchiez.",
            "zh": "抱歉，我没有找到您要找的内容。",
        }
        return fallback_messages.get(language, fallback_messages["en"])

    def get_enhanced_search_terms(self, query: str) -> List[str]:
        """
        Generate additional search terms based on temporal understanding.

        For example, if user asks for "February" (without year) and current
        date is Feb 2026, we should search for both "February 2026" and
        potentially "February 2025" as fallback.
        """
        temporal_query = self.processor.parse_query(query)
        enhanced_terms = [query]

        if temporal_query.query_type == "specific_month" and temporal_query.confidence < 1.0:
            # Year was inferred - add alternative years
            month = temporal_query.temporal_range.month
            primary_year = temporal_query.inferred_year

            # Add previous year as fallback
            fallback_year = primary_year - 1
            enhanced_terms.append(f"{month_name_en(month)} {fallback_year}")

        elif temporal_query.query_type == "latest":
            # For "latest" queries, add current month/year
            current_month = self.processor.current_date.month
            current_year = self.processor.current_date.year

            month_name = month_name_en(current_month)
            enhanced_terms.append(f"{month_name} {current_year}")

            # Also add previous month as fallback
            if current_month == 1:
                prev_month = 12
                prev_year = current_year - 1
            else:
                prev_month = current_month - 1
                prev_year = current_year

            prev_month_name = month_name_en(prev_month)
            enhanced_terms.append(f"{prev_month_name} {prev_year}")

        return list(set(enhanced_terms))  # Remove duplicates


def month_name_en(month: int) -> str:
    """Get English month name."""
    names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    return names[month - 1]


def month_name_fr(month: int) -> str:
    """Get French month name."""
    names = [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"
    ]
    return names[month - 1]


def month_name_zh(month: int) -> str:
    """Get Chinese month name."""
    names = [
        "一月", "二月", "三月", "四月", "五月", "六月",
        "七月", "八月", "九月", "十月", "十一月", "十二月"
    ]
    return names[month - 1]


def get_month_name(month: int, language: str) -> str:
    """Get localized month name."""
    if language == "zh":
        return month_name_zh(month)
    elif language == "fr":
        return month_name_fr(month)
    else:
        return month_name_en(month)
