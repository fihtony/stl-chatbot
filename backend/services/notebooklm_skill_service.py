"""
NotebookLM Service using ORIGINAL skill code (copied from skills/notebooklm/)

This service imports and uses the EXACT original skill code without modifying
the core logic. Only the configuration paths are adjusted.

The original skill code is in:
  backend/backend/services/notebooklm_skill/scripts/
"""

import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import sys
import json
from pathlib import Path

# Add the skill module to path
_skill_path = Path(__file__).parent / "notebooklm_skill"
if str(_skill_path) not in sys.path:
    sys.path.insert(0, str(_skill_path))

from utils.logger import logger, QueryLogger
from utils.notebooklm_formatter import format_notebooklm_response
from utils.config import config
from utils.constants import ResponseKeys, SourceLabels

# Import the EXACT original function from the skill
from services.notebooklm_skill import ask_notebooklm

# Directory for per-question response files
_RESPONSE_LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "responses"


# Security: Maximum question length to prevent DoS
MAX_QUESTION_LENGTH = 2000

# Security: Dangerous shell metacharacters that must be removed
DANGEROUS_CHARS_PATTERN = re.compile(r'[;&|`$()<>\\]')

# Thread pool for running synchronous Playwright code
_thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notebooklm")


class NotebookLMOriginalSkillService:
    """
    Service for querying NotebookLM using the ORIGINAL skill code.

    This service imports and invokes the original ask_notebooklm function
    from skills/notebooklm/scripts/ask_question.py without modifications.
    """

    def __init__(self):
        """Initialize the NotebookLM service"""
        self.notebook_url = config.NOTEBOOKLM_URL

    def _sanitize_question(self, question: str) -> str:
        """
        Sanitize user input to prevent command injection while allowing international text.

        This function removes dangerous shell metacharacters while preserving
        text in multiple languages (Chinese, French, English, etc.)

        Args:
            question: Raw user question

        Returns:
            Sanitized question

        Raises:
            ValueError: If question exceeds max length or becomes empty after sanitization
        """
        # Check length first
        if len(question) > MAX_QUESTION_LENGTH:
            raise ValueError(f"Question exceeds maximum length of {MAX_QUESTION_LENGTH} characters")

        # Remove dangerous shell metacharacters that could enable command injection
        # This preserves all other characters including international text
        sanitized = DANGEROUS_CHARS_PATTERN.sub('', question.strip())

        # Verify we still have content after sanitization
        if not sanitized:
            raise ValueError("Question cannot be empty or contain only special characters")

        return sanitized

    def _run_query_in_thread(self, question: str, notebook_url: str) -> Dict[str, Any]:
        """
        Run the NotebookLM query in a separate thread to avoid asyncio conflicts

        This calls the EXACT original ask_notebooklm function from the skill.

        Args:
            question: Sanitized question
            notebook_url: NotebookLM notebook URL

        Returns:
            Dict with text, citations, suggestions from NotebookLM
        """
        # Call the original skill function directly
        # Using headless=True for production
        return ask_notebooklm(question, notebook_url, headless=True)

    def query(self, question: str) -> Dict[str, Any]:
        """
        Query NotebookLM with a question

        Args:
            question: The question to ask

        Returns:
            Dict containing answer, sources, language, citations, suggestions

        Raises:
            ValueError: If question is empty, whitespace, or contains invalid characters
            Exception: If query fails or times out
        """
        # Input validation and sanitization
        if not question or not question.strip():
            raise ValueError("Question cannot be empty or whitespace")

        question = self._sanitize_question(question)

        logger.info("Querying NotebookLM")

        # Build request body for logging with clear format
        request_body = f"""Timestamp: {datetime.now().isoformat()}
Notebook URL: {self.notebook_url}
Question:
  {question}"""

        # Log the query request
        query_num = QueryLogger.log_query(request_body)

        try:
            # Use the ORIGINAL skill code via thread pool to avoid asyncio conflicts
            result = _thread_pool.submit(
                self._run_query_in_thread,
                question,
                self.notebook_url
            ).result(timeout=180)

            if result is None:
                logger.error("Query returned no answer")
                QueryLogger.log_response(query_num, "Error: No answer returned from NotebookLM")
                raise Exception("NotebookLM query failed: No answer returned")

            # Handle both old (str) and new (dict) return types
            if isinstance(result, str):
                raw_text = result
                dom_markdown = None
                citations = []
                suggestions = []
            else:
                raw_text = result.get("text", "")
                dom_markdown = result.get("dom_markdown")
                citations = result.get("citations", [])
                suggestions = result.get("suggestions", [])

            # Log the successful response
            QueryLogger.log_response(query_num, raw_text)

            # Use DOM-built markdown with inline citations when available,
            # otherwise fall back to clipboard text
            if dom_markdown and citations:
                # If DOM markdown is much shorter than clipboard, merge citations into clipboard
                dom_len = len(dom_markdown)
                clip_len = len(raw_text)
                if dom_len < clip_len * 0.5 and clip_len > 200:
                    logger.info(f"  ⚠ DOM markdown ({dom_len} chars) much shorter than clipboard ({clip_len} chars)")
                    logger.info(f"  ✓ Merging citations from DOM into clipboard text")
                    merged = self._merge_citations_into_text(raw_text, dom_markdown, citations)
                    parsed = {
                        ResponseKeys.ANSWER: merged,
                        ResponseKeys.SOURCES: [SourceLabels.NOTEBOOKLM],
                        ResponseKeys.LANGUAGE: self._detect_language(merged),
                    }
                else:
                    logger.info(f"  ✓ Using DOM markdown with {len(citations)} inline citations ({dom_len} chars)")
                    parsed = {
                        ResponseKeys.ANSWER: dom_markdown,
                        ResponseKeys.SOURCES: [SourceLabels.NOTEBOOKLM],
                        ResponseKeys.LANGUAGE: self._detect_language(dom_markdown),
                    }
            else:
                parsed = self._parse_response(raw_text)

            parsed["citations"] = citations
            parsed["suggestions"] = suggestions

            # Save per-question file with raw response, formatted response, and metadata
            self._save_question_file(question, raw_text, parsed)

            return parsed

        except Exception as e:
            logger.error(f"Query error: {e}")
            # Log unexpected error
            QueryLogger.log_response(query_num, f"Error: {str(e)}")
            raise

    def _save_question_file(self, question: str, raw_response: str, formatted_result: Dict[str, Any]) -> None:
        """
        Save complete question + response data to a per-question file.
        This makes it easy to find and debug incorrect responses.

        Args:
            question: The original user question
            raw_response: The raw response from NotebookLM (before formatting)
            formatted_result: The parsed/formatted result dict
        """
        try:
            _RESPONSE_LOG_DIR.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"q{QueryLogger._query_counter}_{timestamp}.json"
            filepath = _RESPONSE_LOG_DIR / filename

            file_data = {
                "query_number": QueryLogger._query_counter,
                "timestamp": datetime.now().isoformat(),
                "question": question,
                "raw_response": raw_response,
                "formatted_answer": formatted_result.get(ResponseKeys.ANSWER, ""),
                "language": formatted_result.get(ResponseKeys.LANGUAGE, ""),
                "sources": formatted_result.get(ResponseKeys.SOURCES, []),
                "citations": formatted_result.get("citations", []),
                "suggestions": formatted_result.get("suggestions", []),
            }

            filepath.write_text(
                json.dumps(file_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            logger.info(f"  💾 Saved question file to: {filepath}")

        except Exception as e:
            logger.warning(f"  ! Failed to save question file: {e}")

    def _parse_response(self, output: str) -> Dict[str, Any]:
        """
        Parse the response from NotebookLM.

        When the response comes from clipboard (clean markdown), we use it
        directly with only light cleanup. When it comes from inner_text
        (short responses), we apply the formatters.

        Args:
            output: Raw output from NotebookLM

        Returns:
            Dict with answer, sources, and language
        """
        answer = output.strip()

        # Log raw answer BEFORE any formatting
        logger.info(f"\n--- RAW RESPONSE (before formatting) ---")
        logger.info(f"Length: {len(answer)} chars")
        for line in answer[:2000].split('\n'):
            logger.info(f"  RAW: {repr(line)}")
        if len(answer) > 2000:
            logger.info(f"  ... (truncated, {len(answer) - 2000} more chars)")
        logger.info(f"--- END RAW RESPONSE ---\n")

        # Remove the FOLLOW_UP_REMINDER text that the skill adds
        follow_up_marker = "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know?"
        if follow_up_marker in answer:
            answer = answer.split(follow_up_marker)[0].strip()

        # Detect if this is already clean markdown from clipboard
        # Clipboard markdown has proper formatting (headings, bold, lists with indentation)
        is_clean_markdown = bool(
            re.search(r'(\*\*.*?\*\*|^#{1,6}\s)', answer, re.MULTILINE)
            or (len(answer) > 200 and '\n\n' in answer)
        )

        if is_clean_markdown:
            # Clipboard markdown - use directly with only light cleanup
            logger.info("  ✓ Using clipboard markdown directly (clean format)")
        else:
            # Inner text fallback - apply formatters for cleanup
            logger.info("  ℹ Applying formatters (inner text fallback)")
            answer = format_notebooklm_response(answer)

        # Log formatted answer AFTER formatting
        logger.info(f"\n--- FORMATTED RESPONSE (after formatting) ---")
        logger.info(f"Length: {len(answer)} chars")
        for line in answer[:2000].split('\n'):
            logger.info(f"  FMT: {repr(line)}")
        if len(answer) > 2000:
            logger.info(f"  ... (truncated, {len(answer) - 2000} more chars)")
        logger.info(f"--- END FORMATTED RESPONSE ---\n")

        language = self._detect_language(answer)

        return {
            ResponseKeys.ANSWER: answer,
            ResponseKeys.SOURCES: [SourceLabels.NOTEBOOKLM],
            ResponseKeys.LANGUAGE: language,
        }

    def _merge_citations_into_text(self, clipboard_text: str, dom_markdown: str, citations: list) -> str:
        """
        Merge citation markers from DOM markdown into clipboard text.

        When the DOM extraction is incomplete, we use the full clipboard text
        as the base and insert [^N] markers at positions that match the DOM
        citation locations.

        Args:
            clipboard_text: Full clipboard text (complete but no citations)
            dom_markdown: DOM-built markdown (may be incomplete but has citations)
            citations: List of citation dicts with id, source, etc.

        Returns:
            Clipboard text with citation markers inserted
        """
        merged = clipboard_text

        # Extract citation markers and their surrounding context from DOM markdown
        # Pattern: find [^N] and capture ~50 chars of context before it
        citation_contexts = []
        for match in re.finditer(r'([^\n]{10,80}?)\[\^(\d+)\]', dom_markdown):
            context_before = match.group(1).strip()
            cit_id = int(match.group(2))
            # Clean the context (remove markdown formatting for matching)
            clean_context = re.sub(r'\*\*|[#*]', '', context_before).strip()
            if clean_context:
                citation_contexts.append((cit_id, clean_context))

        # Insert citations into clipboard text, working backwards to preserve positions
        insertions = []
        for cit_id, context in citation_contexts:
            # Find this context in the clipboard text
            # Use the last ~30 chars of context for matching (more unique)
            search_text = context[-60:] if len(context) > 60 else context
            # Clean for regex safety
            search_escaped = re.escape(search_text)
            match = re.search(search_escaped, merged)
            if match:
                insert_pos = match.end()
                insertions.append((insert_pos, cit_id, context))

        # Sort by position descending so we insert from end to start
        insertions.sort(key=lambda x: x[0], reverse=True)

        inserted_ids = set()
        for pos, cit_id, context in insertions:
            # Avoid duplicate markers at same position
            marker = f'[^{cit_id}]'
            # Check if already inserted nearby (within 5 chars)
            nearby = merged[max(0, pos-5):pos+10]
            if marker not in nearby:
                merged = merged[:pos] + marker + merged[pos:]
                inserted_ids.add(cit_id)

        logger.info(f"  ✓ Merged {len(inserted_ids)} citation markers into clipboard text")
        return merged

    def _detect_language(self, text: str) -> str:
        """
        Detect language of text (French, English, or Chinese)

        Args:
            text: Text to analyze

        Returns:
            "fr" for French, "en" for English, "zh" for Chinese
        """
        # Check for Chinese characters
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return "zh"

        # Check for French characters
        french_chars = set("éèêëàâäùüûôöîïç")
        if french_chars & set(text.lower()):
            return "fr"

        return "en"

    def get_notebook_name(self) -> str:
        """
        Get the name of the notebook (cached from config)

        Returns:
            Notebook name from config or default
        """
        return "Saint-Louis"
