"""
NotebookLM Markdown Builder

Builds markdown with inline citation markers by walking the response DOM.
The JavaScript function walks the DOM nodes, preserves bold/italic formatting,
and inserts [^N] citation markers at the correct inline positions.

Handles both paragraph divs and list items (including nested sub-lists).
Uses original citation numbers from NotebookLM DOM (not grouped by source).
"""

BUILD_MARKDOWN_JS = r"""() => {
    const result = { markdown: '', citations: [], citation_anchors: [], suggestions: [] };

    const containers = document.querySelectorAll('.to-user-container');
    if (containers.length === 0) return result;
    const container = containers[containers.length - 1];

    // --- Pre-processing: expand all collapsed citation indicators (⋯ buttons) ---
    // This is synchronous - click the buttons and they will be expanded before we walk
    try {
        const expandButtons = container.querySelectorAll('button.citation-marker .mat-icon, .mat-icon');
        for (const btn of expandButtons) {
            try {
                const parentBtn = btn.closest('button');
                if (parentBtn) parentBtn.click();
                else btn.click();
            } catch(e) {}
        }
    } catch(e) {}

    // Map of original citation ID -> { id, source, excerpt }
    const citationMap = new Map();

    // Track citation IDs seen in current block (for excerpt assignment)
    let blockCitationIds = [];

    // --- Build inline text for a content element, inserting citation markers ---
    function buildInline(parent) {
        let text = '';
        for (const child of parent.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) {
                text += child.textContent;
                continue;
            }
            if (child.nodeType !== Node.ELEMENT_NODE) continue;

            const tag = child.tagName ? child.tagName.toLowerCase() : '';
            const cls = child.className || '';

            // Skip nested sub-lists - they are handled as separate blocks
            if (tag === 'ul' || tag === 'ol') {
                continue;
            }

            // Citation marker button
            if (cls.includes('citation-marker')) {
                const span = child.querySelector('span[aria-label]');
                if (span) {
                    const label = span.getAttribute('aria-label') || '';
                    const match = label.match(/^(\d+)\s*:\s*(.+)$/);
                    if (match) {
                        const originalId = parseInt(match[1]);
                        const source = match[2].trim();

                        // Store citation with original ID from NotebookLM
                        if (!citationMap.has(originalId)) {
                            citationMap.set(originalId, { id: originalId, source: source, original_ids: [originalId], excerpt: '' });
                        }

                        text += '[^' + originalId + ']';
                        if (blockCitationIds.indexOf(originalId) === -1) {
                            blockCitationIds.push(originalId);
                        }
                    }
                }
                continue;
            }

            // "more_horiz" button (collapsed citations indicator) - skip
            if (child.querySelector && child.querySelector('.mat-icon')) {
                continue;
            }

            // Bold
            if (tag === 'b' || tag === 'strong') {
                text += '**' + buildInline(child) + '**';
                continue;
            }

            // Italic
            if (tag === 'i' || tag === 'em') {
                text += '*' + buildInline(child) + '*';
                continue;
            }

            // Links
            if (tag === 'a') {
                const href = child.getAttribute('href') || '';
                text += '[' + buildInline(child) + '](' + href + ')';
                continue;
            }

            // Other elements (span, etc.) - recurse
            text = text + buildInline(child);
        }
        return text;
    }

    // Helper: get nesting level by counting parent ULs
    function getNestingLevel(element) {
        let level = 0;
        let parent = element.parentElement;
        while (parent && parent !== container) {
            if (parent.tagName && parent.tagName.toLowerCase() === 'ul') {
                level++;
            }
            parent = parent.parentElement;
        }
        return level;
    }

    // --- Walk all structural elements and build markdown blocks ---
    const elements = container.querySelectorAll('labs-tailwind-structural-element-view-v2');
    const blocks = [];
    const blockTypes = []; // Track 'list' or 'paragraph' for smart joining

    for (const elem of elements) {
        // Try to find content: either div.paragraph or li.list-item
        const div = elem.querySelector('div[class*="paragraph"]');
        const li = elem.querySelector('li[class*="list-item"]');
        const contentEl = div || li;
        if (!contentEl) continue;

        const classes = contentEl.className || '';
        const isListItem = contentEl.tagName && contentEl.tagName.toLowerCase() === 'li';

        // Reset block citation tracker
        blockCitationIds = [];

        let inlineText = buildInline(contentEl).trim();
        if (!inlineText) continue;

        let prefix = '';

        if (isListItem) {
            const level = getNestingLevel(contentEl);
            const indent = '    '.repeat(Math.max(0, level - 1));
            prefix = indent + '* ';
        } else if (classes.includes('heading3')) {
            prefix = '### ';
        } else if (classes.includes('heading2')) {
            prefix = '## ';
        } else if (classes.includes('heading1')) {
            prefix = '# ';
        }

        blocks.push(prefix + inlineText);
        blockTypes.push(isListItem ? 'list' : 'paragraph');

        // Set excerpt for citations: use the sentence containing each citation, not the whole paragraph
        const plainText = inlineText.replace(/\*\*/g, '').trim();
        for (let i = 0; i < blockCitationIds.length; i++) {
            const citId = blockCitationIds[i];
            const cit = citationMap.get(citId);
            if (cit && !cit.excerpt) {
                // Find the sentence containing [^citId]
                const marker = '[^' + citId + ']';
                const markerIdx = plainText.indexOf(marker);
                if (markerIdx >= 0) {
                    // Find sentence boundaries (period, question mark, exclamation + space)
                    let sentStart = 0;
                    let sentEnd = plainText.length;
                    // Search backwards for sentence start
                    for (let j = markerIdx - 1; j >= 0; j--) {
                        const ch = plainText[j];
                        if (ch === '.' || ch === '?' || ch === '!') {
                            sentStart = j + 1;
                            break;
                        }
                    }
                    // Search forwards for sentence end
                    for (let j = markerIdx + marker.length; j < plainText.length; j++) {
                        const ch = plainText[j];
                        if ((ch === '.' || ch === '?' || ch === '!') && (j + 1 >= plainText.length || plainText[j + 1] === ' ')) {
                            sentEnd = j + 1;
                            break;
                        }
                    }
                    let sentence = plainText.substring(sentStart, sentEnd).replace(/\[\^\d+\]/g, '').trim();
                    cit.excerpt = sentence.length > 500 ? sentence.substring(0, 500) + '...' : sentence;
                } else {
                    // Fallback to full block text without markers
                    const fallback = plainText.replace(/\[\^\d+\]/g, '').trim();
                    cit.excerpt = fallback.length > 500 ? fallback.substring(0, 500) + '...' : fallback;
                }
            }
        }
    }

    // Smart join: consecutive list items use single newline, others use double newline
    let markdown = '';
    for (let i = 0; i < blocks.length; i++) {
        if (i === 0) {
            markdown = blocks[i];
        } else {
            // Consecutive list items: single newline
            if (blockTypes[i] === 'list' && blockTypes[i-1] === 'list') {
                markdown += '\n' + blocks[i];
            } else {
                markdown += '\n\n' + blocks[i];
            }
        }
    }

    result.markdown = markdown;
    result.citations = Array.from(citationMap.values());

    // --- Extract follow-up suggestions ---
    const allSuggestions = document.querySelectorAll('.suggestions-container');
    if (allSuggestions.length > 0) {
        for (let i = allSuggestions.length - 1; i >= 0; i--) {
            const sugContainer = allSuggestions[i];
            const chips = sugContainer.querySelectorAll('.follow-up-chip');
            if (chips.length > 0) {
                for (const chip of chips) {
                    const line = chip.querySelector('.line');
                    if (line && line.textContent && line.textContent.trim()) {
                        result.suggestions.push(line.textContent.trim());
                    }
                }
                break;
            }
        }
    }

    return result;
}"""
