"""Query variation handling for different ways of asking the same question."""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .zhipuai_llm import ZhipuAIClient


@dataclass
class QueryVariation:
    """A variation of a query."""
    text: str
    variation_type: str  # 'paraphrase', 'simplified', 'expanded', 'translated'
    confidence: float = 1.0


class QueryVariationHandler:
    """
    Handle different ways of asking the same question.

    This improves retrieval by:
    1. Generating query paraphrases
    2. Simplifying complex queries
    3. Expanding brief queries with context
    4. Handling translations
    """

    def __init__(self, llm_client: Optional[ZhipuAIClient] = None):
        """
        Initialize query variation handler.

        Args:
            llm_client: Optional LLM client for generating variations
        """
        self.llm_client = llm_client

        # Common proper nouns that should be preserved in queries
        self.proper_nouns = {
            "info-parents", "info parents", "infoparents",
            "collège saint-louis", "college saint-louis", "csl",
            "brigitte cool", "isabelle gauthier",
        }

        # Common paraphrase patterns for French/English
        self.question_patterns = {
            # French
            "quand": ["à quelle date", "quel jour", "date de"],
            "combien": ["quel montant", "quelle quantité", "nombre de"],
            "qui": ["quelle personne", "nom de", "quel est le"],
            "quoi": ["quel", "quelle chose", "de quoi il s'agit"],
            "où": ["dans quel lieu", "à quel endroit"],
            # English
            "when": ["at what time", "on which date", "date of"],
            "how much": ["what amount", "what quantity", "number of"],
            "who": ["which person", "name of", "who is"],
            "what": ["which thing", "describe"],
            "where": ["in which place", "at which location"],
            # Chinese
            "什么时候": ["哪天", "何时", "日期"],
            "多少": ["几个", "数量", "金额"],
            "谁": ["哪个人", "名字", "是谁"],
            "什么": ["哪个", "描述"],
        }

        # Cross-language synonym expansion (key improvement for BGE-M3)
        # Maps terms across languages to help retrieval
        self.cross_language_synonyms = {
            # School leadership
            "principal": ["directeur", "directrice", "director", "head", "chef d'établissement"],
            "director": ["directeur", "directrice", "principal", "head of school"],
            "head": ["directeur", "directrice", "principal", "chef"],
            # Educational programs
            "program": ["programme", "programme d'études", "curriculum", "cours"],
            "programme": ["program", "curriculum", "course of study", "studies"],
            "studies": ["études", "programme", "cursus", "academic program"],
            # Student services
            "services": ["services", "service", "aides", "support", "ressources"],
            "cafeteria": ["cafétéria", "cantine", "restaurant", "dining hall", "food service"],
            "library": ["bibliothèque", "biblio", "resource center", "médiathèque"],
            "uniform": ["uniforme", "code vestimentaire", "dress code", "tenue", "apparence"],
            # Activities - IMPORTANT: Map to document terminology
            "activities": ["activités", "activity", "extracurricular", "para-scolaire", "extrascolaire", "activites midi", "parascolaire"],
            "课外活动": ["activités", "activités midi", "parascolaire", "para-scolaire", "extrascolaire", "extracurricular activities", "clubs"],
            "sports": ["sport", "athlétisme", "athletics", "physical education", "éducation physique"],
            "club": ["club", "clubs", "activités", "groupes", "groups"],
            # Admissions
            "admission": ["admission", "inscription", "registration", "enrollment", "application"],
            "register": ["inscription", "enroll", "register", "apply", "s'inscrire"],
            "enroll": ["inscription", "register", "admission", "s'inscrire"],
            # Schedule/Calendar
            "schedule": ["horaire", "calendrier", "calendar", "timetable", "planning"],
            "calendar": ["calendrier", "horaire", "schedule", "dates importantes"],
            # Information/Communication
            "information": ["information", "infos", "renseignements", "details", "information"],
            "news": ["actualités", "nouvelles", "news", "informations", "avis"],
            "newsletter": ["info-parents", "newsletter", "bulletin", "communication"],
            # Meetings/Events
            "meeting": ["réunion", "meeting", "rencontre", "assemblée", "gathering"],
            "open house": ["journee portes ouvertes", "porte ouverte", "open house", "visite"],
            # Academic terms
            "courses": ["cours", "matières", "subjects", "classes", "programs"],
            "subjects": ["matières", "cours", "subjects", "disciplines"],
            "exam": ["examen", "test", "evaluation", "évaluation", "assessment"],
            # 课程 (courses/subjects in Chinese)
            "课程": ["cours", "matières", "subjects", "programs", "programme d'études"],
        }

        # Domain-specific term expansion for education
        self.education_terms = {
            "student": ["élève", "etudiant", "étudiante", "student", "pupil"],
            "teacher": ["professeur", "enseignant", "prof", "teacher", "instructor", "maitre", "maître"],
            "parent": ["parent", "parents", "family", "famille", "tuteur", "guardian"],
            "class": ["classe", "class", "classroom", "groupe", "course"],
            "grade": ["niveau", "grade", "année", "year", "secondary", "secondaire"],
            "school": ["école", "school", "collège", "college", "etablissement", "établissement"],
        }

        # Grade level mapping for Chinese/French/English queries
        # Maps user input to secondary school equivalents
        # Since all documents are about secondary school (Collège Saint-Louis)
        self.grade_mapping = {
            # Chinese grade mapping (default to secondary)
            "1年级": "1re secondaire", "1年": "1re secondaire",
            "2年级": "2e secondaire", "2年": "2e secondaire",
            "3年级": "3e secondaire", "3年": "3e secondaire",
            "4年级": "4e secondaire", "4年": "4e secondaire",
            "5年级": "5e secondaire", "5年": "5e secondaire",
            # Grade numbers in digits
            "1": "1re secondaire",
            "2": "2e secondaire",
            "3": "3e secondaire",
            "4": "4e secondaire",
            "5": "5e secondaire",
            # English grade mapping
            "grade 1": "1re secondaire", "grade 2": "2e secondaire",
            "grade 3": "3e secondaire", "grade 4": "4e secondaire", "grade 5": "5e secondaire",
            "year 1": "1re secondaire", "year 2": "2e secondaire",
            "year 3": "3e secondaire", "year 4": "4e secondaire", "year 5": "5e secondaire",
            # French grade mapping
            "1re année": "1re secondaire", "2e année": "2e secondaire",
            "3e année": "3e secondaire", "4e année": "4e secondaire", "5e année": "5e secondaire",
            # Cycle mapping (secondary school structure)
            "1er cycle": "1re cycle", "1er cycle": "1re cycle",
            "2e cycle": "2e cycle", "2eme cycle": "2e cycle",
        }

    def generate_rule_based_variations(self, query: str, language: str) -> List[QueryVariation]:
        """
        Generate query variations using rule-based patterns.

        Args:
            query: Original query
            language: Query language

        Returns:
            List of QueryVariation objects
        """
        variations = []
        query_lower = query.lower()

        # Pattern-based paraphrases
        for pattern, replacements in self.question_patterns.items():
            if pattern in query_lower:
                for replacement in replacements[:2]:  # Limit to 2 replacements per pattern
                    new_query = query_lower.replace(pattern, replacement, 1)
                    if new_query != query_lower:
                        variations.append(QueryVariation(
                            text=new_query,
                            variation_type="paraphrase",
                            confidence=0.8
                        ))

        # NEW: Handle Chinese question word variations for activity queries
        # "有什么" and "有哪些" should be treated interchangeably
        if language == "zh" and "课外活动" in query_lower:
            # Replace "有什么" with "有哪些" for better matching
            if "有什么" in query_lower:
                variations.append(QueryVariation(
                    text=query_lower.replace("有什么", "有哪些"),
                    variation_type="question_word",
                    confidence=0.9
                ))
            # Also try removing the question word entirely
            base_query = query_lower.replace("有什么", "").replace("有哪些", "").strip()
            if base_query != query_lower:
                variations.append(QueryVariation(
                    text=base_query,
                    variation_type="simplified",
                    confidence=0.7
                ))

        # Extract key terms for simplified queries
        # Remove question words and keep content
        content_words = re.sub(
            r'^(quand|combien|qui|quoi|où|when|how much|who|what|where|什么时候|多少|谁|什么)\s+(?:est\s+|sont\s+|is\s+|are\s+)?',
            '',
            query_lower
        )

        if content_words and len(content_words) < len(query_lower):
            variations.append(QueryVariation(
                text=content_words.strip(),
                variation_type="simplified",
                confidence=0.7
            ))

        return variations

    def expand_chinese_activity_query(
        self,
        query: str
    ) -> List[str]:
        """
        Special handling for Chinese queries about activities.

        Chinese terms for activities don't match well with French document terms,
        so we need to add explicit French variations.

        IMPORTANT: Don't combine terms - keep them separate for better retrieval.

        Args:
            query: Original Chinese query

        Returns:
            List of expanded queries with French terminology
        """
        expanded = []

        # Check if query contains activity-related terms
        activity_keywords = ["课外活动", "活动", "社团", "俱乐部", "运动", "体育"]
        if not any(kw in query for kw in activity_keywords):
            return expanded

        # Add pure French activity terms as separate queries (NOT combined)
        # This allows the retrieval system to find relevant documents
        expanded.append("activités midi")
        expanded.append("activités parascolaires")
        expanded.append("parascolaire")

        return expanded

    def expand_with_synonyms(
        self,
        query: str,
        language: str
    ) -> List[str]:
        """
        Expand query with cross-language and domain-specific synonyms.

        This is a key improvement for multilingual retrieval with BGE-M3.

        Args:
            query: Original query
            language: Query language

        Returns:
            List of expanded queries with synonyms
        """
        expanded = [query]
        query_lower = query.lower()

        # Try to find and expand key terms
        for term, synonyms in self.cross_language_synonyms.items():
            if term in query_lower:
                # Create variations with synonyms
                for synonym in synonyms[:2]:  # Limit to avoid explosion
                    # Replace term with synonym
                    variant = query_lower.replace(term, synonym, 1)
                    if variant != query_lower:
                        expanded.append(variant)

                # Also add French translations for English terms and vice versa
                if language == "en":
                    # Add French synonyms
                    fr_synonyms = [s for s in synonyms if self._looks_french(s)]
                    for fr_syn in fr_synonyms[:1]:
                        variant = query_lower.replace(term, fr_syn, 1)
                        if variant != query_lower:
                            expanded.append(variant)
                elif language == "zh":
                    # For Chinese, add English and French terms
                    en_fr_synonyms = [s for s in synonyms if not self._looks_chinese(s)]
                    for syn in en_fr_synonyms[:1]:
                        variant = f"{query} {syn}"
                        expanded.append(variant)

        # Also check education terms
        for term, synonyms in self.education_terms.items():
            if term in query_lower:
                for synonym in synonyms[:2]:
                    variant = query_lower.replace(term, synonym, 1)
                    if variant != query_lower:
                        expanded.append(variant)

        return expanded

    def _looks_french(self, text: str) -> bool:
        """Check if text appears to be French (has accents or common French patterns)."""
        french_chars = set("àâäéèêëïîôùûüÿç")
        return any(char in text for char in french_chars) or any(pattern in text for pattern in ["le ", "la ", "les ", "de ", "du ", "des "])

    def _looks_chinese(self, text: str) -> bool:
        """Check if text contains Chinese characters."""
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    def normalize_query(self, query: str) -> str:
        """
        Normalize query for better matching.

        - Remove accents for French text
        - Standardize spacing
        - Lowercase

        Args:
            query: Original query

        Returns:
            Normalized query
        """
        import unicodedata

        # Remove accents
        normalized = unicodedata.normalize('NFKD', query)
        without_accents = ''.join(
            c for c in normalized
            if not unicodedata.combining(c)
        )

        # Normalize spacing
        cleaned = ' '.join(without_accents.split())

        return cleaned.lower()

    def normalize_grade_references(
        self,
        query: str,
        language: str
    ) -> List[str]:
        """
        Normalize grade references for secondary school context.

        Since all documents are about Collège Saint-Louis (secondary school),
        map grade references to the appropriate secondary school level.

        IMPORTANT: Activities are organized by CYCLE (1er cycle vs 2e cycle),
        not by individual grades. So we need to map:
        - Grades 1-2 → 1er cycle
        - Grades 3-4-5 → 2e cycle

        Args:
            query: Original query
            language: Query language

        Returns:
            List of queries with normalized grade references
        """
        normalized = [query]
        query_lower = query.lower()

        # Grade to cycle mapping (more comprehensive)
        grade_to_cycle = {
            # Chinese
            "1年级": "1er cycle", "1年": "1er cycle",
            "2年级": "1er cycle", "2年": "1er cycle",
            "3年级": "2e cycle", "3年": "2e cycle",
            "4年级": "2e cycle", "4年": "2e cycle",
            "5年级": "2e cycle", "5年": "2e cycle",
            # English
            "grade 1": "1er cycle", "grade 2": "1er cycle",
            "grade 3": "2e cycle", "grade 4": "2e cycle", "grade 5": "2e cycle",
            "year 1": "1er cycle", "year 2": "1er cycle",
            "year 3": "2e cycle", "year 4": "2e cycle", "year 5": "2e cycle",
        }

        # Check if query contains grade references
        for grade_ref, cycle_equiv in grade_to_cycle.items():
            if grade_ref in query_lower:
                # Create variation with cycle equivalent (for activities)
                cycle_query = query_lower.replace(grade_ref, cycle_equiv, 1)
                if cycle_query != query_lower:
                    normalized.append(cycle_query)

                # Also add secondary school grade equivalent (for academics)
                if grade_ref in self.grade_mapping:
                    secondary_query = query_lower.replace(grade_ref, self.grade_mapping[grade_ref], 1)
                    if secondary_query != query_lower and secondary_query != cycle_query:
                        normalized.append(secondary_query)

                # NEW: For Chinese activity queries, add separate cycle and activity terms
                # Don't combine them - let the retrieval system find docs from both queries
                if language == "zh" and any(kw in query_lower for kw in ["课外活动", "活动", "社团"]):
                    # Add cycle term as a separate query
                    normalized.append(cycle_equiv)

                    # Add activity terms as separate queries
                    normalized.append("activités midi")
                    normalized.append("activités parascolaires")
                    normalized.append("parascolaire")

                    # NEW: Add cycle + 有哪些活动 combination (works better than 课外活动)
                    # But DON'T add "课外活动" combinations as they can cause timeouts
                    if "课外活动" in query_lower:
                        normalized.append(f"{cycle_equiv}有哪些活动")

                # Stop after first match (avoid multiple replacements)
                break

        return normalized

    def detect_latest_query(self, query: str) -> bool:
        """
        Detect if query is asking for the latest/newest/most recent information.

        Args:
            query: The query string

        Returns:
            True if this is a "latest" type query
        """
        latest_patterns = [
            # English
            r'\b(?:latest|newest|most recent|recent)\b',
            # French (including plural forms)
            r'\b(?:derniers?|dernières?|récents?|récent|plus récent)\b',
            # Chinese (no word boundaries - they don't work with CJK characters)
            r'(?:最新|最近|最新的)',
        ]
        query_lower = query.lower()
        return any(re.search(pattern, query_lower) for pattern in latest_patterns)

    def enhance_latest_query(self, query: str, language: str) -> List[str]:
        """
        Enhance queries asking for "latest" information with specific month variations.
        This improves retrieval for temporal queries like "latest info-parents".

        Args:
            query: Original query
            language: Query language

        Returns:
            List of enhanced query variations
        """
        variations = []

        # Extract the subject matter (what they're looking for)
        query_lower = query.lower()

        # Pattern to match "latest [subject]"
        # English: "latest info-parents", "most recent report", etc.
        # French: "derniers info-parents", "informations récentes", etc.
        # Chinese: "最新info-parents", "最近的报告", etc.

        # For info-parents specifically, add month variations
        if re.search(r'info[-\s]?parents?', query_lower):
            month_variations = [
                "février 2026 info-parents",
                "janvier 2026 info-parents",
                "Info-parents de février 2026",
                "Info-parents de janvier 2026",
            ]
            variations.extend(month_variations)

        # For general "latest" queries, add temporal markers
        latest_enhancements = {
            "en": [
                f"{query} February 2026",
                f"{query} January 2026",
                "most recent 2026",
            ],
            "fr": [
                f"{query} février 2026",
                f"{query} janvier 2026",
                "plus récent 2026",
            ],
            "zh": [
                f"{query} 2026年2月",
                f"{query} 2026年1月",
                "2026年最新的",
            ],
        }

        variations.extend(latest_enhancements.get(language, []))

        return variations

    def _enhance_temporal_query(self, query: str, language: str) -> List[str]:
        """
        Enhance temporal queries (containing month names) with year inference.

        For queries like "February info-parents", add variations with "2026" to help find
        the most recent documents.

        Args:
            query: Original query
            language: Query language

        Returns:
            List of enhanced query variations, or empty list if not a temporal query
        """
        import re

        # Month name patterns in different languages
        month_patterns = {
            'en': r'\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
            'fr': r'\b(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|fevrier|decembre)\b',
        }

        query_lower = query.lower()

        # Check if query contains a month name
        has_month = False
        matched_month = None
        for lang, pattern in month_patterns.items():
            match = re.search(pattern, query_lower)
            if match:
                has_month = True
                matched_month = match.group(1)
                break

        # Check for Chinese date format: "2026年2月" or "二月"
        chinese_date_match = re.search(r'(\d{4})年(\d{1,2})月', query_lower)
        chinese_month_match = re.search(r'(一月|二月|三月|四月|五月|六月|七月|八月|九月|十月|十一月|十二月)', query_lower)

        variations = []

        # Handle Chinese date format queries
        if chinese_date_match or chinese_month_match:
            # Extract year and month
            if chinese_date_match:
                year = chinese_date_match.group(1)
                month_num = int(chinese_date_match.group(2))
            else:
                # Default to 2026 if year not specified
                year = "2026"
                # Map Chinese month name to number
                zh_to_num = {
                    '一月': 1, '二月': 2, '三月': 3, '四月': 4,
                    '五月': 5, '六月': 6, '七月': 7, '八月': 8,
                    '九月': 9, '十月': 10, '十一月': 11, '十二月': 12
                }
                month_num = zh_to_num.get(chinese_month_match.group(1))

            if month_num:
                # Map to French month (without accents to match filenames)
                num_to_fr_month = {
                    1: 'janvier', 2: 'fevrier', 3: 'mars', 4: 'avril',
                    5: 'mai', 6: 'juin', 7: 'juillet', 8: 'aout',
                    9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'decembre'
                }
                fr_month = num_to_fr_month.get(month_num)

                if fr_month:
                    # Generate French variations to match document filenames
                    variations.append(f"{fr_month} {year} info-parents")
                    variations.append(f"Info-parents de {fr_month} {year}")
                    variations.append(f"info-parents {fr_month}-{year}")

        if not has_month and not chinese_date_match and not chinese_month_match:
            return []  # Not a temporal query

        # Also handle English/French month names
        if has_month and matched_month:
            # Add year 2026 to the query
            variations.append(f"{query} 2026")

            # Also add French variations for English month queries
            if language == 'en' and matched_month:
                # Map English months to French (without accents to match filenames)
                en_to_fr_month = {
                    'january': 'janvier', 'jan': 'janvier',
                    'february': 'fevrier', 'feb': 'fevrier',
                    'march': 'mars', 'mar': 'mars',
                    'april': 'avril', 'apr': 'avril',
                    'may': 'mai',
                    'june': 'juin', 'jun': 'juin',
                    'july': 'juillet', 'jul': 'juillet',
                    'august': 'aout', 'aug': 'aout',
                    'september': 'septembre', 'sep': 'septembre',
                    'october': 'octobre', 'oct': 'octobre',
                    'november': 'novembre', 'nov': 'novembre',
                    'december': 'decembre', 'dec': 'decembre',
                }

                fr_month = en_to_fr_month.get(matched_month.lower())
                if fr_month:
                    # Preserve other parts of query (like "info-parents")
                    query_without_month = re.sub(matched_month, '', query_lower, flags=re.IGNORECASE).strip()
                    variations.append(f"{fr_month} 2026 {query_without_month}")
                    variations.append(f"info-parents {fr_month} 2026")

        return variations

    def generate_llm_variations(
        self,
        query: str,
        language: str,
        num_variations: int = 2
    ) -> List[QueryVariation]:
        """
        Generate query variations using LLM.

        Args:
            query: Original query
            language: Query language
            num_variations: Number of variations to generate

        Returns:
            List of QueryVariation objects
        """
        if not self.llm_client:
            return []

        lang_names = {"fr": "French", "en": "English", "zh": "Chinese"}
        lang_name = lang_names.get(language, "the same language")

        prompt = f"""Generate {num_variations} different ways to ask the following question in {lang_name}.
The variations should mean the same thing but use different words or structures.

Original question: {query}

Return ONLY a JSON array of strings:
["variation1", "variation2", ...]

Keep variations natural and concise."""

        try:
            result = self.llm_client.chat(prompt, temperature=0.7)
            if result["success"]:
                import json
                response = result["response"]
                # Extract JSON array
                json_match = re.search(r'\[.*?\]', response, re.DOTALL)
                if json_match:
                    variations_list = json.loads(json_match.group())
                    return [
                        QueryVariation(
                            text=var,
                            variation_type="llm_paraphrase",
                            confidence=0.9
                        )
                        for var in variations_list
                    ]
        except Exception as e:
            pass

        return []

    def get_all_variations(
        self,
        query: str,
        language: str,
        use_llm: bool = True
    ) -> List[str]:
        """
        Get all query variations including the original.

        Args:
            query: Original query
            language: Query language
            use_llm: Whether to use LLM for variations

        Returns:
            List of query strings
        """
        queries = [query]  # Always include original

        # NEW: Normalize grade references for secondary school context
        # This should be early as it affects the query significantly
        grade_variations = self.normalize_grade_references(query, language)
        queries.extend(grade_variations)

        # Check if this is a "latest" type query and add enhanced variations
        if self.detect_latest_query(query):
            latest_variations = self.enhance_latest_query(query, language)
            queries.extend(latest_variations)

        # Check if this is a temporal query (contains month names) and enhance with year
        temporal_variations = self._enhance_temporal_query(query, language)
        if temporal_variations:
            queries.extend(temporal_variations)

        # NEW: Expand with synonyms (cross-language and domain-specific)
        synonym_variations = self.expand_with_synonyms(query, language)
        queries.extend(synonym_variations)

        # NEW: Special handling for Chinese activity queries
        if language == "zh":
            chinese_activity_variations = self.expand_chinese_activity_query(query)
            queries.extend(chinese_activity_variations)

        # Rule-based variations
        rule_variations = self.generate_rule_based_variations(query, language)
        queries.extend([v.text for v in rule_variations])

        # LLM variations
        if use_llm and self.llm_client:
            llm_variations = self.generate_llm_variations(query, language)
            queries.extend([v.text for v in llm_variations])

        # Remove duplicates while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            q_normalized = q.lower().strip()
            if q_normalized not in seen:
                seen.add(q_normalized)
                unique_queries.append(q)

        # DEBUG: Log variations for problematic queries
        if language == "zh" and ("年级" in query or "课外活动" in query):
            print(f"🔍 Query variations for '{query}':")
            for i, v in enumerate(unique_queries[:10]):  # Show first 10
                print(f"  {i+1}. {v}")

        return unique_queries

    def expand_with_context(
        self,
        query: str,
        context_terms: List[str],
        language: str
    ) -> List[str]:
        """
        Expand query with relevant context terms.

        Args:
            query: Original query
            context_terms: Relevant terms from document collection
            language: Query language

        Returns:
            List of expanded queries
        """
        expanded = [query]

        # Add context terms to query
        for term in context_terms[:3]:  # Limit to 3 terms
            expanded.append(f"{query} {term}")

        return expanded

    def search_with_variations(
        self,
        query: str,
        query_embedding,
        retriever,
        top_k: int = 5,
        language: str = "fr",
        is_latest_query: bool = False,
        is_temporal_query: bool = False,
        embedding_client=None,
    ) -> List[Dict[str, Any]]:
        """
        Search using query variations to improve recall.

        Args:
            query: Original query
            query_embedding: Query embedding vector (for original query only)
            retriever: Retriever instance
            top_k: Number of results
            language: Query language
            is_latest_query: Whether this is a "latest" type query (for date boosting)
            is_temporal_query: Whether this is a temporal/date-based query
            embedding_client: Embedding client to generate embeddings for each variation

        Returns:
            Combined results from all query variations
        """
        variations = self.get_all_variations(query, language, use_llm=False)

        # Collect results from all variations
        all_results = {}  # {unique_id: result}

        # Determine fetch_k and return_k based on query type
        # For temporal queries (specific dates), we need more results because
        # the target month might not be in top positions by semantic similarity
        if is_latest_query or is_temporal_query:
            fetch_k = max(30, top_k * 6)  # Fetch many more for date queries
            return_k = max(10, top_k * 2)  # Return more results for temporal filtering
        else:
            fetch_k = top_k * 3  # Standard fetch for regular queries
            return_k = top_k  # Standard return for regular queries

        for i, variation in enumerate(variations):
            # Use original query embedding for first variation, generate new ones for others
            if i == 0:
                variation_embedding = query_embedding
            elif embedding_client:
                variation_embedding = embedding_client.embed_query(variation)
            else:
                variation_embedding = query_embedding  # Fallback to original

            results = retriever.search(variation, variation_embedding, fetch_k)

            for result in results:
                # Use combination of source and page as unique identifier
                metadata = result["metadata"]
                source = metadata.get("source", "")
                page = metadata.get("page", 0)
                chunk_index = metadata.get("chunk_index", 0)

                # Create a unique ID from source + page + chunk_index
                unique_id = f"{source}_{page}_{chunk_index}"
                current_score = result["score"]

                # Keep best score for each chunk
                if unique_id not in all_results:
                    all_results[unique_id] = result
                elif current_score > all_results[unique_id]["score"]:
                    all_results[unique_id] = result

        # Convert to sorted list
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x["score"],
            reverse=True
        )[:return_k]

        return sorted_results


def create_query_variation_handler(llm_client: Optional[ZhipuAIClient] = None) -> QueryVariationHandler:
    """Factory function to create a query variation handler."""
    return QueryVariationHandler(llm_client)
