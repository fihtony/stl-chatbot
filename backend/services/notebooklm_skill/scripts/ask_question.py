#!/usr/bin/env python3
"""
Simple NotebookLM Question Interface
Based on MCP server implementation - simplified without sessions

Implements hybrid auth approach:
- Persistent browser profile (user_data_dir) for fingerprint consistency
- Manual cookie injection from state.json for session cookies (Playwright bug workaround)
See: https://github.com/microsoft/playwright/issues/36139
"""

import argparse
import sys
import time
import re
from pathlib import Path

from patchright.sync_api import sync_playwright
import asyncio

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_manager import AuthManager
from notebook_manager import NotebookLibrary
from config import QUERY_INPUT_SELECTORS, RESPONSE_SELECTORS, BROWSER_PROFILE_DIR
from browser_utils import BrowserFactory, StealthUtils
from markdown_builder import BUILD_MARKDOWN_JS


def _safe_start_playwright():
    """
    Start sync_playwright safely, handling residual asyncio event loop state.

    When running inside a ThreadPoolExecutor, playwright.stop() can leave behind
    a closed asyncio event loop in the thread-local state. The next
    sync_playwright().start() detects this and raises:
      "It looks like you are using Playwright Sync API inside the asyncio loop."

    Fix: detect and clean up the stale event loop before starting a new one.
    """
    try:
        return sync_playwright().start()
    except Exception as e:
        err_msg = str(e)
        if "asyncio" in err_msg.lower() or "event loop" in err_msg.lower():
            # Clean up stale asyncio event loop from a previous playwright.stop()
            try:
                loop = asyncio.get_event_loop()
                if loop and not loop.is_running():
                    loop.close()
            except (RuntimeError, Exception):
                pass
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            # Retry
            return sync_playwright().start()
        raise


def _try_copy_button(response_element, page) -> str:
    """
    Try to click the copy button associated with a specific response element.

    Args:
        response_element: The Playwright element handle for the response
        page: The Playwright page object

    Returns:
        Clipboard text if successful, None otherwise
    """
    try:
        # Search for the copy button within the same container as the response
        # This ensures we get the copy button for THIS response, not an old one
        result = page.evaluate("""(element) => {
            // Find the container of this response
            let container = element;

            // Try different container levels
            const possibleContainers = [
                element,
                element.parentElement,  // Parent
                element.parentElement?.parentElement,  // Grandparent
                element.closest('.to-user-container'),  // Closest message container
                element.closest('[data-message-author="bot"]'),  // Bot message container
                element.closest('[data-message-author="assistant"]'),  // Assistant container
            ];

            let copyButton = null;

            // Search for copy button in each container level
            for (const cont of possibleContainers) {
                if (!cont) continue;

                // Try multiple selectors for copy button
                const selectors = [
                    'button[aria-label="Copy model response to clipboard"]',
                    'button[aria-label*="copy" i]',
                    'button[class*="copy" i]',
                    'button[title*="copy" i]',
                    '.copy-button',
                    'button[aria-label*="Copy"]',
                ];

                for (const selector of selectors) {
                    const buttons = cont.querySelectorAll(selector);
                    if (buttons.length > 0) {
                        // Get the first copy button in this container
                        copyButton = buttons[0];
                        break;
                    }
                }

                if (copyButton) break;
            }

            if (!copyButton) {
                return { found: false, error: 'No copy button found in response container' };
            }

            // Click the button
            copyButton.click();

            return { found: true, buttonHTML: copyButton.outerHTML };
        }""", response_element)

        if not result or not result.get('found'):
            print(f"  ! Copy button not found: {result.get('error', 'Unknown error')}")
            return None

        print("  ✓ Clicked copy button")

        # Wait for clipboard to be populated
        StealthUtils.random_delay(500, 1000)

        # Read clipboard
        clipboard_text = page.evaluate("() => navigator.clipboard.readText()")

        if not clipboard_text:
            print("  ! Clipboard is empty")
            return None

        print(f"  📋 Got clipboard content ({len(clipboard_text)} chars)")

        # Validate clipboard content matches response roughly
        # The clipboard might have markdown formatting, so it could be longer
        # But it shouldn't be drastically different
        response_text = response_element.inner_text().strip()
        clipboard_ratio = len(clipboard_text) / len(response_text) if len(response_text) > 0 else 0

        # Accept clipboard if ratio is reasonable (0.3 to 5.0)
        # Markdown formatting can make it significantly longer or shorter
        if 0.3 <= clipboard_ratio <= 5.0:
            print(f"  ✓ Clipboard content validated (ratio: {clipboard_ratio:.2f})")
            return clipboard_text
        else:
            print(f"  ! Clipboard content seems off (ratio: {clipboard_ratio:.2f}), ignoring")
            return None

    except Exception as e:
        print(f"  ! Copy button error: {e}")
        return None


def ask_notebooklm(question: str, notebook_url: str, headless: bool = True,
                   browser_state: dict = None, keep_browser: bool = False,
                   user_data_dir: str = None) -> dict:
    """
    Ask a question to NotebookLM

    Args:
        question: Question to ask
        notebook_url: NotebookLM notebook URL
        headless: Run browser in headless mode
        browser_state: Optional existing browser state dict {playwright, context, page}
                       to reuse instead of creating a new browser
        keep_browser: If True, return browser state in result (don't close browser)
        user_data_dir: Optional custom browser profile directory (for session isolation)

    Returns:
        Dict with answer text, citations, suggestions, and optionally browser_state
    """
    auth = AuthManager()

    if not auth.is_authenticated():
        print("⚠️ Not authenticated. Run: python auth_manager.py setup")
        return None

    print(f"💬 Asking: {question}")
    print(f"📚 Notebook: {notebook_url}")

    playwright = None
    context = None
    page = None
    reused_browser = False

    try:
        if browser_state and browser_state.get('page'):
            # Reuse existing browser
            try:
                page = browser_state['page']
                page.evaluate("1+1")  # Check if page is alive
                playwright = browser_state['playwright']
                context = browser_state['context']
                reused_browser = True
                print("  ♻️ Reusing existing browser session")
            except Exception as e:
                print(f"  ! Existing browser stale: {e}")
                playwright = None
                context = None
                page = None

        if not reused_browser:
            # Start playwright
            playwright = _safe_start_playwright()

            # Launch persistent browser context using factory
            context = BrowserFactory.launch_persistent_context(
                playwright,
                headless=headless,
                user_data_dir=user_data_dir or str(BROWSER_PROFILE_DIR)
            )

            # Navigate to notebook
            page = context.new_page()
        print("  🌐 Opening notebook...")
        page.goto(notebook_url, wait_until="domcontentloaded")

        # Wait for NotebookLM (longer timeout for new profiles that need auth redirects)
        page.wait_for_url(re.compile(r"^https://notebooklm\.google\.com/"), timeout=30000)

        # Wait for query input (MCP approach)
        print("  ⏳ Waiting for query input...")
        query_element = None

        for selector in QUERY_INPUT_SELECTORS:
            try:
                query_element = page.wait_for_selector(
                    selector,
                    timeout=10000,
                    state="visible"  # Only check visibility, not disabled!
                )
                if query_element:
                    print(f"  ✓ Found input: {selector}")
                    break
            except:
                continue

        if not query_element:
            print("  ❌ Could not find query input")
            return None

        # Type question (human-like, fast) - ORIGINAL SKILL APPROACH: No clearing
        print("  ⏳ Typing question...")
        input_selector = QUERY_INPUT_SELECTORS[0]
        StealthUtils.human_type(page, input_selector, question)

        # Submit
        print("  📤 Submitting...")
        page.keyboard.press("Enter")

        # Small pause
        StealthUtils.random_delay(500, 1500)

        # Wait for response (MCP approach: poll for stable text)
        print("  ⏳ Waiting for answer...")

        answer = None
        stable_count = 0
        last_text = None
        deadline = time.time() + 120  # 2 minutes timeout

        # Rate limit detection patterns
        RATE_LIMIT_PATTERNS = [
            "The system was unable to answer",
            "Unable to answer",
            "Daily limit reached",
            "Rate limit exceeded",
        ]

        while time.time() < deadline:
            # Check if NotebookLM is still thinking (most reliable indicator)
            try:
                thinking_element = page.query_selector('div.thinking-message')
                if thinking_element and thinking_element.is_visible():
                    time.sleep(1)
                    continue  # Still thinking, wait
            except:
                pass

            # Get the current response text
            current_text = None
            current_element = None  # Store the element for copy button search

            for selector in RESPONSE_SELECTORS:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        # Get last (newest) response
                        current_element = elements[-1]
                        text = current_element.inner_text().strip()

                        if text:
                            current_text = text
                            break
                except:
                    continue

            # Check if we have a response
            if current_text:
                # Check for rate limit messages
                is_rate_limit = any(pattern.lower() in current_text.lower() for pattern in RATE_LIMIT_PATTERNS)
                if is_rate_limit:
                    print(f"  ⚠️ Rate limit detected: {current_text}")
                    answer = current_text
                    break

                # Check stability
                if current_text == last_text:
                    stable_count += 1
                    if stable_count >= 3:  # Stable for 3 consecutive polls
                        print(f"  ✓ Response stable (length: {len(current_text)} chars)")

                        # Determine if we should try copy button or use direct text
                        # For short responses (single line), use direct text
                        # For longer responses, try copy button for clean markdown
                        if len(current_text) < 100 or '\n' not in current_text:
                            # Short response - use direct text
                            print("  ✓ Using direct text (short response)")
                            answer = current_text
                            break
                        else:
                            # Longer response - try copy button first
                            print("  📋 Trying copy button for clean markdown...")
                            markdown = _try_copy_button(current_element, page)
                            if markdown:
                                answer = markdown
                                break
                            else:
                                # Fallback to direct text
                                print("  ! Copy button failed, using direct text")
                                answer = current_text
                                break
                else:
                    stable_count = 0
                    last_text = current_text
                    print(f"  ⏳ Response changing... (length: {len(current_text)} chars)")

            time.sleep(1)

        if not answer:
            print("  ❌ Timeout waiting for answer")
            return None

        print("  ✅ Got answer!")

        # Expand collapsed citation indicators (⋯ buttons) before extraction
        # Quick JS click - no timeouts, keeps response fast
        try:
            page.evaluate(r"""() => {
                const container = document.querySelectorAll('.to-user-container');
                if (container.length === 0) return 0;
                const last = container[container.length - 1];
                const btns = last.querySelectorAll('.mat-icon');
                let count = 0;
                for (const btn of btns) {
                    try {
                        const parent = btn.closest('button');
                        if (parent) { parent.click(); count++; }
                    } catch(e) {}
                }
                return count;
            }""")
        except Exception as e:
            print(f"  ! Citation expansion: {e}")

        # Build markdown with inline citations from DOM
        citations = []
        suggestions = []
        dom_markdown = None

        try:
            from markdown_builder import BUILD_MARKDOWN_JS
            extracted = page.evaluate(BUILD_MARKDOWN_JS)

            citations = extracted.get('citations', [])
            suggestions = extracted.get('suggestions', [])
            dom_markdown = extracted.get('markdown', '')
            print(f"  📎 Citations: {len(citations)} unique sources")
            print(f"  💡 Suggestions: {len(suggestions)} follow-up questions")
            print(f"  📝 DOM markdown length: {len(dom_markdown)} chars")

        except Exception as e:
            print(f"  ! DOM markdown extraction failed: {e}")
            import traceback
            traceback.print_exc()

        # NOTE: Citation dialog clicking removed - it causes timeouts.
        # Citation content is fetched on-demand when user hovers (lazy loading).

        # Save HTML for debugging
        try:
            from config import DATA_DIR
            html_debug_dir = DATA_DIR / "html_debug"
            html_debug_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            html_file = html_debug_dir / f"response_{timestamp}.html"
            html_file.write_text(page.content(), encoding='utf-8')
            print(f"  💾 Saved HTML to: {html_file}")
        except Exception as e:
            print(f"  ! HTML save failed: {e}")

        result = {
            "text": answer,  # clipboard text (fallback)
            "dom_markdown": dom_markdown,  # DOM-built text with inline [^N] citations
            "citations": citations,
            "suggestions": suggestions,
        }

        if keep_browser:
            # Return browser state for reuse (e.g., lazy citation fetching)
            result["browser_state"] = {
                "playwright": playwright,
                "context": context,
                "page": page,
            }
            print("  🔗 Keeping browser alive for lazy citation loading")
            # Prevent finally from cleaning up
            playwright = None
            context = None

        return result

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        # Clean up browser (only if not kept alive)
        if context:
            try:
                context.close()
            except:
                pass
        if playwright:
            try:
                playwright.stop()
            except:
                pass


def fetch_citation_from_page(page, citation_id: int, original_ids: list = None) -> dict:
    """
    Fetch citation source content from an already-open NotebookLM page.

    Hovers over the citation marker to trigger the tooltip popup, extracts
    the content, then moves the mouse away to dismiss it.

    Args:
        page: Playwright page object with NotebookLM response visible
        citation_id: The citation ID to fetch
        original_ids: Original NotebookLM citation IDs to try

    Returns:
        Dict with 'content' (source text) and 'success' (bool)
    """
    ids_to_try = original_ids or [citation_id]

    # First close any open dialogs (feedback dialog, etc.)
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except:
        pass

    # Expand any collapsed citation indicators (⋯ buttons) in the last response
    try:
        expanded = page.evaluate(r"""() => {
            const containers = document.querySelectorAll('.to-user-container');
            if (containers.length === 0) return 0;
            const last = containers[containers.length - 1];
            let count = 0;
            // Click mat-icon buttons (expand ⋯ indicators)
            const btns = last.querySelectorAll('.mat-icon');
            for (const btn of btns) {
                try {
                    const parent = btn.closest('button');
                    if (parent) { parent.click(); count++; }
                } catch(e) {}
            }
            return count;
        }""")
        if expanded > 0:
            print(f"  📖 Expanded {expanded} citation indicators")
            time.sleep(0.5)
    except Exception as e:
        print(f"  ! Citation expansion: {e}")

    for cid in ids_to_try:
        try:
            # Close any existing overlays first
            page.evaluate("() => { document.querySelectorAll('.cdk-overlay-backdrop').forEach(e => e.click()); }")
            time.sleep(0.3)
            page.keyboard.press("Escape")
            time.sleep(0.3)

            # Use JS to dispatch hover events directly on the citation button
            # This bypasses coordinate-based mouse movement issues
            found = page.evaluate(r"""(cid) => {
                const containers = document.querySelectorAll('.to-user-container');
                if (containers.length === 0) return null;
                const last = containers[containers.length - 1];

                const buttons = last.querySelectorAll('button.xap-inline-dialog.citation-marker');
                for (const btn of buttons) {
                    const label = btn.querySelector('span[aria-label]');
                    if (label) {
                        const labelText = label.getAttribute('aria-label') || '';
                        const match = labelText.match(/^(\d+)\s*:/);
                        if (match && parseInt(match[1]) === cid) {
                            // Dispatch mouseenter/mouseover events to trigger Angular hover
                            const events = ['mouseenter', 'mouseover', 'pointerenter', 'pointerover'];
                            for (const eventType of events) {
                                btn.dispatchEvent(new MouseEvent(eventType, {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window,
                                }));
                            }
                            return { found: true, label: labelText };
                        }
                    }
                }
                return null;
            }""", cid)

            if not found or not found.get('found'):
                print(f"  ! Citation {cid} not found in DOM")
                continue

            print(f"  📎 Dispatched hover events on citation {cid}: {found.get('label', '')}")

            # Wait for the inline dialog to be created by Angular
            time.sleep(2.0)

            # Quick check if popup appeared
            popup_found = page.evaluate(r"""() => {
                const el = document.querySelector('.citation-tooltip-content');
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 10 && rect.height > 10;
                }
                return false;
            }""")
            if popup_found:
                print(f"  ✓ Citation popup appeared")
            else:
                print(f"  ⚠️ No citation popup found, checking alternatives...")

            # Now try to extract the citation popup content (text + images)
            # First, scroll the tooltip to load all content (innerHeight of the scrollable element)
            page.evaluate(r"""() => {
                const tc = document.querySelector('.citation-tooltip-content');
                if (tc) tc.scrollTop = tc.scrollHeight;
            }""")
            time.sleep(0.5)

            extracted = page.evaluate(r"""() => {
                // The hover creates an xap-inline-dialog-container element with:
                // - header.xap-dialog-header-container (source title)
                // - xap-dialog-layout-content.citation-tooltip-content (content + images)
                //   Within .citation-tooltip-content, there's a scrollable area with the source text
                //   and possibly a div.citation-tooltip-text (highlighted excerpt, may be empty)
                //
                // Key issues:
                // 1. innerText respects CSS overflow — text beyond visible area is excluded
                // 2. DOM order may differ from visual order due to CSS flex/layout
                // Fix: use textContent for complete text, then manually extract sub-elements

                let result = { text: null, images: [] };

                // Strategy 1: Target the precise citation tooltip content
                const tooltipContent = document.querySelector('.citation-tooltip-content');
                if (tooltipContent) {
                    const rect = tooltipContent.getBoundingClientRect();
                    if (rect.width > 10 && rect.height > 10) {
                        // Scroll to top first to get all content
                        tooltipContent.scrollTop = 0;

                        // Collect images
                        const imgs = tooltipContent.querySelectorAll('img');
                        for (const img of imgs) {
                            if (img.src && img.src.startsWith('http')) {
                                result.images.push(img.src);
                            }
                        }

                        // Extract text from child elements in order, using textContent
                        // to get full text regardless of CSS overflow
                        // We want the main content text, not the header title
                        const contentParts = [];

                        // Get all text nodes from the scrollable content area
                        // Exclude the header (.xap-dialog-header-container) which is the source title
                        const walker = document.createTreeWalker(
                            tooltipContent,
                            NodeFilter.SHOW_TEXT,
                            null
                        );
                        let node;
                        while (node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text) contentParts.push(text);
                        }

                        const fullText = contentParts.join('\n').trim();
                        if (fullText.length > 5) {
                            result.text = fullText;
                            return result;
                        }

                        // Fallback: use textContent directly
                        const rawText = (tooltipContent.textContent || '').trim();
                        if (rawText.length > 5) {
                            // Clean up whitespace from textContent
                            result.text = rawText.replace(/\s+/g, ' ').replace(/\s*\n\s*/g, '\n');
                            return result;
                        }
                    }
                }

                // Strategy 2: Look for the full dialog container
                const dialogContainers = document.querySelectorAll(
                    '.xap-inline-dialog-container[aria-label="Citation Details"]'
                );
                for (const dc of dialogContainers) {
                    const rect = dc.getBoundingClientRect();
                    if (rect.width < 10 || rect.height < 10) continue;

                    // Extract images
                    const imgs = dc.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.src && img.src.startsWith('http')) result.images.push(img.src);
                    }

                    // Try to get content without the header
                    const contentEl = dc.querySelector('.citation-tooltip-content, .xap-dialog-layout-content');
                    if (contentEl) {
                        const rawText = (contentEl.textContent || '').trim();
                        if (rawText.length > 5) {
                            result.text = rawText.replace(/\s+/g, ' ').replace(/\s*\n\s*/g, '\n');
                            return result;
                        }
                    }

                    // Last resort: full container text
                    const fullText = (dc.textContent || '').trim();
                    if (fullText.length > 10) {
                        result.text = fullText.replace(/\s+/g, ' ').replace(/\s*\n\s*/g, '\n');
                        return result;
                    }
                }

                // Strategy 3: Generic dialog containers
                const genericContainers = document.querySelectorAll(
                    '.xap-inline-dialog-container, [class*="inline-dialog-container"]'
                );
                for (const dc of genericContainers) {
                    const rect = dc.getBoundingClientRect();
                    if (rect.width < 10 || rect.height < 10) continue;
                    const text = (dc.textContent || '').trim();
                    if (text.length > 10) {
                        result.text = text.replace(/\s+/g, ' ').replace(/\s*\n\s*/g, '\n');
                        const imgs = dc.querySelectorAll('img');
                        for (const img of imgs) {
                            if (img.src && img.src.startsWith('http')) result.images.push(img.src);
                        }
                        return result;
                    }
                }

                return result;
            }""")

            source_content = extracted.get('text') if isinstance(extracted, dict) else extracted
            images = extracted.get('images', []) if isinstance(extracted, dict) else []

            if source_content:
                # Dismiss popup by dispatching mouseout
                page.evaluate(r"""() => {
                    const markers = document.querySelectorAll('button.xap-inline-dialog.citation-marker');
                    for (const m of markers) {
                        m.dispatchEvent(new MouseEvent('mouseleave', {bubbles: true}));
                        m.dispatchEvent(new MouseEvent('mouseout', {bubbles: true}));
                    }
                }""")
                time.sleep(0.5)
                img_count = len(images)
                print(f"  ✓ Got citation content ({len(source_content)} chars, {img_count} images)")
                result = {"content": source_content, "success": True}
                if images:
                    result["images"] = images
                return result

            # If JS hover didn't work, try Playwright element.hover()
            print(f"  ! JS hover didn't create popup, trying Playwright hover()...")
            try:
                # Find the button using Playwright selector
                container_count = page.evaluate("document.querySelectorAll('.to-user-container').length")
                button = page.query_selector(
                    f'.to-user-container:nth-child({container_count}) button.xap-inline-dialog.citation-marker span[aria-label^="{cid}:"]'
                )
                if not button:
                    # Broader search
                    button = page.query_selector(f'span[aria-label^="{cid}: "]')
                if button:
                    button.hover()
                    time.sleep(2.0)

                    # Re-check for popup
                    source_content = page.evaluate(r"""() => {
                        const dcs = document.querySelectorAll('.xap-inline-dialog-container, [class*="inline-dialog-container"]');
                        for (const dc of dcs) {
                            const rect = dc.getBoundingClientRect();
                            if (rect.width < 10 || rect.height < 10) continue;
                            return (dc.innerText || '').trim();
                        }
                        return null;
                    }""")

                    if source_content and len(source_content) > 10:
                        print(f"  ✓ Got citation via Playwright hover ({len(source_content)} chars)")
                        page.mouse.move(0, 0)
                        return {"content": source_content, "success": True}
            except Exception as e2:
                print(f"  ! Playwright hover fallback failed: {e2}")

            # Dismiss any popup
            page.keyboard.press("Escape")
            time.sleep(0.3)

        except Exception as e:
            print(f"  ! Citation {cid} fetch error: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.keyboard.press("Escape")
                time.sleep(0.3)
            except:
                pass

    return {"content": "", "success": False}


def prefetch_all_citations(page, citations: list) -> dict:
    """
    Pre-fetch all citation contents in the background after getting an answer.

    Iterates through all citations, hovers each one, extracts content,
    and stores results in a dict keyed by citation ID.

    Args:
        page: Playwright page object with NotebookLM response visible
        citations: List of citation dicts with 'id' and 'original_ids'

    Returns:
        Dict mapping citation_id -> {"content": str, "images": list, "success": bool}
    """
    results = {}
    if not citations:
        return results

    print(f"  🔄 Pre-fetching {len(citations)} citations in background...")

    # Expand collapsed citation indicators first
    try:
        expanded = page.evaluate(r"""() => {
            const containers = document.querySelectorAll('.to-user-container');
            if (containers.length === 0) return 0;
            const last = containers[containers.length - 1];
            let count = 0;
            const btns = last.querySelectorAll('.mat-icon');
            for (const btn of btns) {
                try {
                    const parent = btn.closest('button');
                    if (parent) { parent.click(); count++; }
                } catch(e) {}
            }
            return count;
        }""")
        if expanded > 0:
            print(f"  📖 Expanded {expanded} indicators for prefetch")
            time.sleep(0.5)
    except:
        pass

    for citation in citations:
        cid = citation.get('id')
        original_ids = citation.get('original_ids', [cid])
        if not cid:
            continue

        try:
            result = fetch_citation_from_page(page, cid, original_ids)
            results[cid] = result
        except Exception as e:
            print(f"  ! Prefetch citation {cid} failed: {e}")
            results[cid] = {"content": "", "success": False, "error": str(e)}

        # Small delay between citations
        time.sleep(0.3)

    successful = sum(1 for r in results.values() if r.get('success'))
    print(f"  ✅ Pre-fetch complete: {successful}/{len(citations)} citations fetched")
    return results


def close_browser_state(browser_state: dict):
    """Close browser state returned by ask_notebooklm with keep_browser=True."""
    if not browser_state:
        return
    if browser_state.get('context'):
        try:
            browser_state['context'].close()
        except:
            pass
    if browser_state.get('playwright'):
        try:
            browser_state['playwright'].stop()
        except:
            pass


def main():
    parser = argparse.ArgumentParser(description='Ask NotebookLM a question')

    parser.add_argument('--question', required=True, help='Question to ask')
    parser.add_argument('--notebook-url', help='NotebookLM notebook URL')
    parser.add_argument('--notebook-id', help='Notebook ID from library')
    parser.add_argument('--show-browser', action='store_true', help='Show browser')

    args = parser.parse_args()

    # Resolve notebook URL
    notebook_url = args.notebook_url

    if not notebook_url and args.notebook_id:
        library = NotebookLibrary()
        notebook = library.get_notebook(args.notebook_id)
        if notebook:
            notebook_url = notebook['url']
        else:
            print(f"❌ Notebook '{args.notebook_id}' not found")
            return 1

    if not notebook_url:
        # Check for active notebook first
        library = NotebookLibrary()
        active = library.get_active_notebook()
        if active:
            notebook_url = active['url']
            print(f"📚 Using active notebook: {active['name']}")
        else:
            # Show available notebooks
            notebooks = library.list_notebooks()
            if notebooks:
                print("\n📚 Available notebooks:")
                for nb in notebooks:
                    mark = " [ACTIVE]" if nb.get('id') == library.active_notebook_id else ""
                    print(f"  {nb['id']}: {nb['name']}{mark}")
                print("\nSpecify with --notebook-id or set active:")
                print("python scripts/run.py notebook_manager.py activate --id ID")
            else:
                print("❌ No notebooks in library. Add one first:")
                print("python scripts/run.py notebook_manager.py add --url URL --name NAME --description DESC --topics TOPICS")
            return 1

    # Ask the question
    result = ask_notebooklm(
        question=args.question,
        notebook_url=notebook_url,
        headless=not args.show_browser
    )

    if result:
        print("\n" + "=" * 60)
        print(f"Question: {args.question}")
        print("=" * 60)
        print()
        if isinstance(result, dict):
            print(result.get("text", ""))
            if result.get("citations"):
                print("\n--- Citations ---")
                for c in result["citations"]:
                    print(f"  [{c['id']}] {c['source']}")
            if result.get("suggestions"):
                print("\n--- Suggestions ---")
                for s in result["suggestions"]:
                    print(f"  • {s}")
        else:
            print(result)
        print()
        print("=" * 60)
        return 0
    else:
        print("\n❌ Failed to get answer")
        return 1


if __name__ == "__main__":
    sys.exit(main())
