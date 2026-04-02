"""
NotebookLM Service using ORIGINAL skill code (copied from skills/notebooklm/)

Each session gets its own service instance with isolated citation cache
and suggestions. The browser is shared via a single thread pool because:
1. Chromium only allows one instance per profile directory
2. All sessions share the same Google authentication
3. Playwright objects are bound to the thread that created them

CRITICAL CONSTRAINT: Playwright's sync API creates a running asyncio event
loop on the thread where sync_playwright().start() is called. A second
sync_playwright().start() on the same thread will fail with "It looks like
you are using Playwright Sync API inside the asyncio loop" if the first
loop is still alive. Therefore, all sessions must share ONE browser instance
at a time, and the previous browser must be fully stopped before a new one
can start.

Session isolation is achieved through:
- Per-session citation cache (_prefetched_citations)
- Per-session browser state tracking
- Per-session prefetch futures
"""

import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
import sys
import json
import time
import asyncio
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
from services.notebooklm_skill import ask_notebooklm, fetch_citation_from_page, close_browser_state, prefetch_all_citations

# Directory for per-question response files
_RESPONSE_LOG_DIR = Path(__file__).parent.parent.parent / "logs" / "responses"


# Security: Maximum question length to prevent DoS
MAX_QUESTION_LENGTH = 2000

# Security: Dangerous shell metacharacters that must be removed
DANGEROUS_CHARS_PATTERN = re.compile(r'[;&|`$()<>\\]')

# Shared thread pool for all Playwright operations.
# max_workers=1 ensures serialization — critical because:
# 1. Playwright objects are bound to their creating thread
# 2. Chromium only allows one instance per profile directory
# 3. Prevents concurrent browser access that would cause race conditions
_shared_thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notebooklm")

# Module-level tracking of the currently active browser state.
# Since Playwright sync API creates a running event loop, only ONE browser
# can be alive at a time per thread. Any new query must stop the previous
# browser before starting a new one, regardless of which session owns it.
_active_browser_state: Optional[Dict[str, Any]] = None
_active_browser_owner: Optional[str] = None  # session_id of the owner


def _stop_active_browser():
    """Stop any currently active browser, regardless of session ownership.

    Must be called from within the shared thread pool thread.
    This ensures the playwright event loop is fully cleaned up before
    a new sync_playwright().start() is attempted.
    """
    global _active_browser_state, _active_browser_owner

    if _active_browser_state:
        logger.info("  🧹 Stopping previously active browser (owned by session '%s')",
                     _active_browser_owner or "unknown")
        close_browser_state(_active_browser_state)
        _active_browser_state = None
        _active_browser_owner = None

        # After playwright.stop(), clean up the residual event loop
        # so the next sync_playwright().start() won't see a running loop.
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_running() and not loop.is_closed():
                loop.close()
        except (RuntimeError, Exception):
            pass
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass


class NotebookLMOriginalSkillService:
    """
    Service for querying NotebookLM using the ORIGINAL skill code.

    Each session has its own citation cache and browser state tracking,
    but shares the underlying thread pool (and thus the browser thread).

    Session isolation:
    - Own citation cache (per-session prefetched data)
    - Own browser state reference (which page/context to use)
    - Shared thread pool for Playwright operations
    """

    def __init__(self, session_id: str = "default"):
        """Initialize the NotebookLM service with per-session citation cache."""
        self.session_id = session_id
        self.notebook_url = config.NOTEBOOKLM_URL
        self._browser_state = None
        self._browser_last_used = 0
        self._prefetched_citations = {}
        self._prefetch_future: Optional[Future] = None
        logger.info(f"  📦 Created service instance for session '{session_id}'")

    def shutdown(self):
        """Clean up resources for this session."""
        self._cleanup_browser()
        logger.info(f"  📦 Shut down service for session '{self.session_id}'")

    def _sanitize_question(self, question: str) -> str:
        if len(question) > MAX_QUESTION_LENGTH:
            raise ValueError(f"Question exceeds maximum length of {MAX_QUESTION_LENGTH} characters")
        sanitized = DANGEROUS_CHARS_PATTERN.sub('', question.strip())
        if not sanitized:
            raise ValueError("Question cannot be empty or contain only special characters")
        return sanitized

    def _run_query_in_thread(self, question: str, notebook_url: str) -> Dict[str, Any]:
        """Run the NotebookLM query in the shared Playwright thread."""
        global _active_browser_state, _active_browser_owner

        # Stop ANY active browser (from any session) before starting a new one.
        # This is required because Playwright's sync API only allows one running
        # event loop per thread. If a previous session's browser is still alive
        # (e.g., kept alive for prefetch), its event loop will prevent a new
        # sync_playwright().start() from succeeding.
        _stop_active_browser()

        # Cancel any pending prefetch from this session
        if self._prefetch_future and not self._prefetch_future.done():
            self._prefetch_future.cancel()
        self._prefetch_future = None
        self._browser_state = None

        result = ask_notebooklm(
            question, notebook_url, headless=True,
            browser_state=None,
            keep_browser=True,
        )

        if result and result.get("browser_state"):
            self._browser_state = result.pop("browser_state")
            self._browser_last_used = time.time()

            # Register as the globally active browser
            _active_browser_state = self._browser_state
            _active_browser_owner = self.session_id

            logger.info("  🔗 Browser kept alive for citation loading (session=%s)", self.session_id)

            citations = result.get("citations", [])
            if citations:
                self._prefetch_citations(citations)

        return result

    def query(self, question: str) -> Dict[str, Any]:
        """Query NotebookLM with a question."""
        if not question or not question.strip():
            raise ValueError("Question cannot be empty or whitespace")
        question = self._sanitize_question(question)
        logger.info("Querying NotebookLM")

        request_body = f"""Timestamp: {datetime.now().isoformat()}
Notebook URL: {self.notebook_url}
Question:
  {question}"""
        query_num = QueryLogger.log_query(request_body)

        try:
            result = _shared_thread_pool.submit(
                self._run_query_in_thread, question, self.notebook_url
            ).result(timeout=180)

            if result is None:
                logger.error("Query returned no answer")
                QueryLogger.log_response(query_num, "Error: No answer returned from NotebookLM")
                raise Exception("NotebookLM query failed: No answer returned")

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

            QueryLogger.log_response(query_num, raw_text)

            if dom_markdown and citations:
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
            self._save_question_file(question, raw_text, parsed)
            return parsed

        except Exception as e:
            logger.error(f"Query error: {e}")
            QueryLogger.log_response(query_num, f"Error: {str(e)}")
            raise

    def _save_question_file(self, question: str, raw_response: str, formatted_result: Dict[str, Any]) -> None:
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
            filepath.write_text(json.dumps(file_data, indent=2, ensure_ascii=False), encoding='utf-8')
            logger.info(f"  💾 Saved question file to: {filepath}")
        except Exception as e:
            logger.warning(f"  ! Failed to save question file: {e}")

    def _parse_response(self, output: str) -> Dict[str, Any]:
        answer = output.strip()
        logger.info(f"\n--- RAW RESPONSE (before formatting) ---")
        logger.info(f"Length: {len(answer)} chars")
        for line in answer[:2000].split('\n'):
            logger.info(f"  RAW: {repr(line)}")
        if len(answer) > 2000:
            logger.info(f"  ... (truncated, {len(answer) - 2000} more chars)")
        logger.info(f"--- END RAW RESPONSE ---\n")

        follow_up_marker = "\n\nEXTREMELY IMPORTANT: Is that ALL you need to know?"
        if follow_up_marker in answer:
            answer = answer.split(follow_up_marker)[0].strip()

        is_clean_markdown = bool(
            re.search(r'(\*\*.*?\*\*|^#{1,6}\s)', answer, re.MULTILINE)
            or (len(answer) > 200 and '\n\n' in answer)
        )
        if is_clean_markdown:
            logger.info("  ✓ Using clipboard markdown directly (clean format)")
        else:
            logger.info("  ℹ Applying formatters (inner text fallback)")
            answer = format_notebooklm_response(answer)

        logger.info(f"\n--- FORMATTED RESPONSE (after formatting) ---")
        logger.info(f"Length: {len(answer)} chars")
        for line in answer[:2000].split('\n'):
            logger.info(f"  FMT: {repr(line)}")
        if len(answer) > 2000:
            logger.info(f"  ... (truncated, {len(answer) - 2000} more chars)")
        logger.info(f"--- END FORMATTED RESPONSE ---\n")

        return {
            ResponseKeys.ANSWER: answer,
            ResponseKeys.SOURCES: [SourceLabels.NOTEBOOKLM],
            ResponseKeys.LANGUAGE: self._detect_language(answer),
        }

    def _merge_citations_into_text(self, clipboard_text: str, dom_markdown: str, citations: list) -> str:
        merged = clipboard_text
        citation_contexts = []
        for match in re.finditer(r'([^\n]{10,80}?)\[\^(\d+)\]', dom_markdown):
            context_before = match.group(1).strip()
            cit_id = int(match.group(2))
            clean_context = re.sub(r'\*\*|[#*]', '', context_before).strip()
            if clean_context:
                citation_contexts.append((cit_id, clean_context))
        insertions = []
        for cit_id, context in citation_contexts:
            search_text = context[-60:] if len(context) > 60 else context
            search_escaped = re.escape(search_text)
            match = re.search(search_escaped, merged)
            if match:
                insertions.append((match.end(), cit_id, context))
        insertions.sort(key=lambda x: x[0], reverse=True)
        inserted_ids = set()
        for pos, cit_id, context in insertions:
            marker = f'[^{cit_id}]'
            nearby = merged[max(0, pos-5):pos+10]
            if marker not in nearby:
                merged = merged[:pos] + marker + merged[pos:]
                inserted_ids.add(cit_id)
        logger.info(f"  ✓ Merged {len(inserted_ids)} citation markers into clipboard text")
        return merged

    def _detect_language(self, text: str) -> str:
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return "zh"
        french_chars = set("éèêëàâäùüûôöîïç")
        if french_chars & set(text.lower()):
            return "fr"
        return "en"

    def get_notebook_name(self) -> str:
        return "Saint-Louis"

    def _cleanup_browser(self):
        """Close stored browser state if it exists. Preserves prefetched citation cache."""
        global _active_browser_state, _active_browser_owner

        # Cancel pending prefetch
        if self._prefetch_future and not self._prefetch_future.done():
            self._prefetch_future.cancel()
        self._prefetch_future = None

        if self._browser_state:
            logger.info("  🧹 Cleaning up browser session (session=%s)", self.session_id)
            close_browser_state(self._browser_state)
            self._browser_state = None
            self._browser_last_used = 0

            # Clear module-level active browser if we own it
            if _active_browser_owner == self.session_id:
                _active_browser_state = None
                _active_browser_owner = None

            # Clean up residual asyncio event loop from playwright.stop()
            try:
                loop = asyncio.get_event_loop()
                if loop and not loop.is_running() and not loop.is_closed():
                    loop.close()
            except (RuntimeError, Exception):
                pass
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass

        # NOTE: Do NOT clear _prefetched_citations - cached data is still valid

    def _prefetch_citations(self, citations: list):
        """Synchronously prefetch all citation contents in the current thread.

        This runs as part of _run_query_in_thread, so it executes in the
        shared thread pool thread. Since max_workers=1, this blocks any
        citation hover requests until complete. However, this ensures all
        citations are cached before the chat response is returned to the
        user, so subsequent hover requests are served instantly from cache.
        """
        if not self._browser_state or not self._browser_state.get('page'):
            logger.warning("  ! Prefetch: no browser state available")
            return

        try:
            page = self._browser_state['page']
            results = prefetch_all_citations(page, citations)
            self._prefetched_citations.update(results)
            self._browser_last_used = time.time()
            logger.info(f"  ✅ Prefetch done: {sum(1 for r in results.values() if r.get('success'))}/{len(citations)} fetched")
        except Exception as e:
            logger.warning(f"  ! Prefetch error: {e}")

    async def fetch_citation_content(self, citation_id: int, original_ids: list = None) -> Dict[str, Any]:
        """
        Fetch citation source content. Non-blocking — runs in shared thread pool.

        Called on-demand when user hovers over a citation in the frontend.
        Checks prefetch cache first for instant response.
        """
        # 1. Check prefetch cache (instant)
        cached = self._prefetched_citations.get(citation_id)
        if cached and cached.get('success'):
            logger.info(f"  ✓ Citation {citation_id} served from cache")
            return cached

        # 2. Wait for in-progress prefetch to complete
        if self._prefetch_future and not self._prefetch_future.done():
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, self._prefetch_future.result, 60)
            except Exception:
                pass
            cached = self._prefetched_citations.get(citation_id)
            if cached and cached.get('success'):
                logger.info(f"  ✓ Citation {citation_id} served from cache (after prefetch)")
                return cached

        # 3. Check browser state
        if not self._browser_state or not self._browser_state.get('page'):
            logger.warning(f"  ! No browser session for citation {citation_id} (session={self.session_id})")
            return {"content": "", "success": False, "error": "No browser session"}

        if time.time() - self._browser_last_used > 300:
            logger.info("  ⏰ Browser session expired (5 min)")
            self._cleanup_browser()
            return {"content": "", "success": False, "error": "Session expired"}

        # 4. Live fetch in shared thread pool
        logger.info(f"  📎 Live fetching citation {citation_id} (ids={original_ids})")
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                _shared_thread_pool,
                self._fetch_citation_in_thread,
                citation_id,
                original_ids
            )
            self._browser_last_used = time.time()
            if result.get('success'):
                self._prefetched_citations[citation_id] = result
            return result
        except Exception as e:
            logger.error(f"  ! Citation fetch error: {e}")
            return {"content": "", "success": False, "error": str(e)}

    def _fetch_citation_in_thread(self, citation_id: int, original_ids: list = None) -> Dict[str, Any]:
        """Fetch citation content in the shared thread (sync Playwright)."""
        if not self._browser_state or not self._browser_state.get('page'):
            return {"content": "", "success": False, "error": "Browser state lost"}
        page = self._browser_state['page']
        try:
            return fetch_citation_from_page(page, citation_id, original_ids)
        except Exception as e:
            logger.error(f"  ! Citation thread fetch error: {e}")
            return {"content": "", "success": False, "error": str(e)}
