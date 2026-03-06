from dataclasses import dataclass
from typing import Optional
from langdetect import detect, LangDetectException

@dataclass
class QueryRoute:
    language: str
    needs_translation: bool
    requires_variations: bool

    def __post_init__(self):
        if self.language == "unknown":
            self.language = "fr"

class LanguageDetectionQueryRouter:
    LANGUAGE_MAP = {
        "fr": "fr", "en": "en", "zh": "zh", "zh-cn": "zh", "zh-tw": "zh",
    }

    def __init__(self):
        self._cache = {}

    def route(self, query: str) -> QueryRoute:
        if query in self._cache:
            return self._cache[query]

        if not query or len(query.strip()) < 2:
            route = QueryRoute(language="fr", needs_translation=False, requires_variations=False)
            self._cache[query] = route
            return route

        detected_lang = self._detect_language(query)

        if detected_lang == "fr":
            route = QueryRoute(language="fr", needs_translation=False, requires_variations=False)
        else:
            route = QueryRoute(language=detected_lang, needs_translation=True, requires_variations=True)

        self._cache[query] = route
        return route

    def _detect_language(self, query: str) -> str:
        # First check for Chinese characters explicitly (IMPORTANT: check first!)
        if any("\u4e00" <= char <= "\u9fff" for char in query):
            return "zh"

        # Simple heuristic for English: check for common English words
        query_lower = query.lower()
        common_english_words = {
            "can", "you", "tell", "about", "what", "where", "when", "how", "why",
            "who", "which", "that", "this", "with", "from", "have", "been", "will",
            "would", "could", "should", "student", "school", "activity", "program",
            "available", "please", "thank", "hello", "recent", "latest", "newest"
        }
        # Count English words
        english_word_count = sum(1 for word in query_lower.split() if word in common_english_words)

        # If we have multiple English words, it's likely English
        if english_word_count >= 2:
            return "en"

        # Use langdetect as fallback for French or ambiguous cases
        try:
            detected = detect(query)
            for key, value in self.LANGUAGE_MAP.items():
                if detected.lower().startswith(key):
                    return value
            return "fr"
        except (LangDetectException, Exception):
            return "fr"
