/* =============================================================================
   src/static/js/settings/history.js
   ============================================================================= */

/**
 * @fileoverview History Management Module.
 * Handles fetching, searching, sorting, and rendering of transcription history.
 */

/**
 * @typedef {Object} TranscriptEntry
 * @property {number} id        - Unique identifier.
 * @property {string} text      - The transcribed text content.
 * @property {number} timestamp - Unix timestamp of creation.
 */

/**
 * Local buffer for all history entries, enabling fast in-memory filtering and sorting.
 * @type {TranscriptEntry[]}
 */
let transcriptHistoryBuffer = [];

/**
 * Currently active (filtered) list, used for display and infinite scrolling.
 * @type {TranscriptEntry[]}
 */
let currentFilteredData = [];

/**
 * Pagination cursor for infinite scrolling.
 */
let historyRenderIndex = 0;
const HISTORY_BATCH_SIZE = 20;
let markdownParserInstance = null;

/**
 * Fuse.js instance used for fuzzy text searching.
 * @type {Object|null}
 */
let fuseSearchInstance = null;

/* =============================================================================
   DATA LOADING
   ============================================================================= */

/**
 * Fetches the transcription history from the backend and initializes the view.
 *
 * @async
 * @returns {Promise<void>}
 */
window.loadTranscripts = async () => {
  if (!window.isApiReady()) {
    console.error("[History] API unavailable.");
    window.displayTranscripts([]);
    return;
  }

  try {
    const historyData = await window.pywebview.api.get_history();
    transcriptHistoryBuffer = Array.isArray(historyData) ? historyData : [];
    window.initFuzzySearch();
    window.sortAndDisplayTranscripts();
  } catch (error) {
    console.error("[History] Load error:", error);
    window.displayTranscripts([]);
  }
};

/* =============================================================================
   SEARCH — Fuse.js
   ============================================================================= */

/**
 * Initializes (or re-initializes) the Fuse.js fuzzy search index
 * against the current history buffer.
 */
window.initFuzzySearch = () => {
  // @ts-ignore — Fuse is injected globally via a vendor script
  if (typeof window.Fuse === "undefined") {
    console.warn("[History] Fuse.js library not found. Search disabled.");
    return;
  }

  const searchOptions = {
    keys: ["text"],
    includeScore: true,
    threshold: 0.4,
    ignoreLocation: true,
    minMatchCharLength: 2,
  };

  // @ts-ignore
  fuseSearchInstance = new window.Fuse(transcriptHistoryBuffer, searchOptions);
};

/* =============================================================================
   MARKDOWN PARSER — Initialization
   ============================================================================= */

/**
 * Lazily initializes the Markdown parser with a custom code fence renderer.
 * The renderer generates a collapsible accordion for blocks exceeding 20 lines,
 * and a static (always-visible) block for shorter snippets.
 */
function initMarkdownParser() {
  if (markdownParserInstance) return;

  // @ts-ignore — markdown-it is loaded globally
  if (typeof window.markdownit === "undefined") return;

  // @ts-ignore
  markdownParserInstance = window.markdownit({
    html: false,
    linkify: true,
    breaks: true,
    typographer: true,
    highlight: (str, lang) => {
      if (lang && window.hljs && window.hljs.getLanguage(lang)) {
        try {
          return window.hljs.highlight(str, {
            language: lang,
            ignoreIllegals: true,
          }).value;
        } catch (_) {}
      }
      return window.escapeHtml(str);
    },
  });

  /**
   * Custom fence renderer:
   * - Blocks with more than 20 lines → collapsible accordion with an arrow icon.
   * - Shorter blocks              → static (always expanded), no arrow.
   */
  markdownParserInstance.renderer.rules.fence = function (
    tokens,
    idx,
    options,
    env,
    slf,
  ) {
    const token = tokens[idx];
    const info = token.info ? token.info.trim() : "";
    const langName = info ? info.split(/\s+/)[0] : "";
    const content = token.content ? token.content.trim() : "";

    // Determine whether the block is long enough to warrant collapsing
    const lineCount = content.split(/\r\n|\r|\n/).length;
    const isCollapsible = lineCount > 20;

    // Syntax-highlight the content
    let highlightedContent = "";
    if (options.highlight) {
      highlightedContent =
        options.highlight(content, langName) || window.escapeHtml(content);
    } else {
      highlightedContent = window.escapeHtml(content);
    }

    // Arrow icon — only rendered for collapsible blocks
    const arrowIcon = isCollapsible
      ? `<svg class="code-arrow" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <polyline points="9 18 15 12 9 6"></polyline>
         </svg>`
      : "";

    const staticClass = isCollapsible ? "" : "static";

    return `
      <div class="code-accordion ${staticClass}">
        <div class="code-header-ui">
          ${arrowIcon}
          ${langName ? `<span class="code-lang-badge">${window.escapeHtml(langName)}</span>` : ""}
          <div class="code-controls">
            <button type="button" class="btn-copy-action" title="Copy">
              <svg class="icon-copy" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              <svg class="icon-check" style="display:none;" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#30d158" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </button>
          </div>
        </div>
        <pre class="hljs"><code>${highlightedContent}</code></pre>
      </div>
    `;
  };
}

/* =============================================================================
   RENDERING
   ============================================================================= */

/**
 * Resets the infinite scroll state and renders the first batch of transcripts.
 *
 * @param {TranscriptEntry[]} dataToDisplay - The filtered list of entries to render.
 */
window.displayTranscripts = (dataToDisplay) => {
  const listContainer = document.getElementById("transcript-list");
  const noDataMessage = document.getElementById("no-transcripts");
  const emptySearchMsg = document.getElementById("empty-search-result");
  const searchInput = document.getElementById("search-transcript");

  if (!listContainer || !noDataMessage || !emptySearchMsg) return;

  // Update shared state consumed by the infinite scroll handler
  currentFilteredData = dataToDisplay;
  historyRenderIndex = 0;

  initMarkdownParser();
  listContainer.innerHTML = "";

  // Case 1: No history entries at all
  if (transcriptHistoryBuffer.length === 0) {
    noDataMessage.style.display = "block";
    emptySearchMsg.style.display = "none";
    listContainer.style.display = "none";
    return;
  }

  noDataMessage.style.display = "none";
  listContainer.style.display = "block";

  // Case 2: History exists but the current filter matches nothing
  const isSearchActive = searchInput && searchInput.value.length > 0;
  if (dataToDisplay.length === 0 && isSearchActive) {
    emptySearchMsg.style.display = "block";
  } else {
    emptySearchMsg.style.display = "none";
    window.renderNextHistoryBatch();
  }
};

/**
 * Appends the next paginated batch of items to the DOM.
 * Called on initial render and each time the user scrolls near the bottom.
 */
window.renderNextHistoryBatch = () => {
  const listContainer = document.getElementById("transcript-list");
  if (!listContainer) return;

  const batch = currentFilteredData.slice(
    historyRenderIndex,
    historyRenderIndex + HISTORY_BATCH_SIZE,
  );

  if (batch.length === 0) return;

  const fragment = document.createDocumentFragment();

  batch.forEach((transcript, index) => {
    if (!transcript || !transcript.id || !transcript.text) return;

    const listItem = document.createElement("li");
    listItem.className = "transcript-item";
    listItem.id = `transcript-${transcript.id}`;
    listItem.setAttribute("data-timestamp", String(transcript.timestamp));

    // Animate only the very first batch to avoid flickering during scroll loads
    if (historyRenderIndex === 0) {
      listItem.style.animationDelay = `${index * 0.05}s`;
    } else {
      listItem.style.animation = "none";
      listItem.style.opacity = "1";
      listItem.style.transform = "none";
    }

    const dateObj = new Date(transcript.timestamp);
    const formattedTime = dateObj.toLocaleString(window.getCurrentLanguage(), {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    const rawText = (transcript.text || "").trim();
    let renderedHtml = "";

    if (markdownParserInstance) {
      let processedText = rawText;

      // Step 1 — Strip chat role prefixes (e.g. "[User]", "[AI]")
      processedText = processedText.replace(/^\[(User|AI)\]\s*/gim, "");

      // Step 2 — Convert block LaTeX delimiters: \[ ... \] → $$ ... $$
      //   a. Switch to $$ so markdown-it doesn't misinterpret \[
      //   b. Collapse newlines inside the equation to prevent spurious <br> tags
      //   c. Escape backslashes so markdown-it doesn't consume them
      processedText = processedText.replace(
        /\\\[([\s\S]*?)\\\]/g,
        (match, content) => {
          const clean = content.replace(/\\/g, "\\\\").replace(/\n/g, " ");
          return `$$${clean}$$`;
        },
      );

      // Step 3 — Protect inline LaTeX: \( ... \) → \\( ... \\)
      //   Same escaping logic as above.
      processedText = processedText.replace(
        /\\\(([\s\S]*?)\\\)/g,
        (match, content) => {
          const clean = content.replace(/\\/g, "\\\\").replace(/\n/g, " ");
          return `\\\\(${clean}\\\\)`;
        },
      );

      // Step 4 — Render Markdown to HTML
      renderedHtml = markdownParserInstance.render(processedText);

      // Step 5 — Clean up Markdown artifacts (trailing empty paragraphs / breaks)
      renderedHtml = renderedHtml.replace(
        /(<p>\s*<\/p>|<br\s*\/?>|\n)+$/gi,
        "",
      );
      renderedHtml = renderedHtml.replace(/(<br\s*\/?>\s*){3,}/gi, "<br><br>");
    } else {
      // Fallback: plain-text rendering if the parser failed to initialize
      renderedHtml = window.escapeHtml(rawText).replace(/\n/g, "<br>");
    }

    listItem.innerHTML = `
      <div class="transcript-header">
        <div class="transcript-time">${formattedTime}</div>
        <div class="transcript-actions">
          <button class="button copy-btn" type="button" aria-label="${window.t("btn_copy")}">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span class="copy-btn-text">${window.t("btn_copy")}</span>
          </button>
        </div>
      </div>
      <div class="transcript-content-wrapper">
        <div class="transcript-text">${renderedHtml}</div>
      </div>
    `;

    const copyButton = listItem.querySelector(".copy-btn");
    copyButton?.addEventListener("click", () => {
      // @ts-ignore
      window.copyTranscriptText(rawText, copyButton);
    });

    fragment.appendChild(listItem);
  });

  listContainer.appendChild(fragment);

  // Render math (KaTeX) only on the newly appended items to avoid reprocessing the DOM
  // @ts-ignore
  if (window.renderMathInElement) {
    setTimeout(() => {
      const allItems = listContainer.querySelectorAll(".transcript-text");

      // Target only the items added in this batch
      const startIndex = Math.max(0, allItems.length - batch.length);

      for (let i = startIndex; i < allItems.length; i++) {
        try {
          // @ts-ignore
          window.renderMathInElement(allItems[i], {
            delimiters: [
              { left: "$$", right: "$$", display: true }, // Block equations
              { left: "\\[", right: "\\]", display: true },
              { left: "\\(", right: "\\)", display: false },
              { left: "$", right: "$", display: false },
            ],
            throwOnError: false,
          });
        } catch (e) {
          console.warn("[History] Math render warning:", e);
        }
      }
    }, 0);
  }

  historyRenderIndex += batch.length;
};

/* =============================================================================
   COPY TO CLIPBOARD
   ============================================================================= */

/**
 * Copies the given text to the clipboard via the native API
 * and provides visual feedback on the trigger button.
 *
 * @param {string}            textToCopy    - The content to copy.
 * @param {HTMLButtonElement} buttonElement - The button that triggered the action.
 */
window.copyTranscriptText = async (textToCopy, buttonElement) => {
  const textSpan = buttonElement.querySelector(".copy-btn-text");

  if (!window.isApiReady()) {
    window.showToast(window.t("toast_error"), "error");
    return;
  }

  try {
    await window.pywebview.api.copy_text(textToCopy);

    // Success state
    if (textSpan) textSpan.textContent = window.t("copied");
    buttonElement.classList.add("copied");
    buttonElement.disabled = true;

    // Revert to default state after 2 seconds
    setTimeout(() => {
      if (textSpan) textSpan.textContent = window.t("btn_copy");
      buttonElement.classList.remove("copied");
      buttonElement.disabled = false;
    }, 2000);
  } catch (error) {
    console.error("[History] Copy failed:", error);
    window.showToast(window.t("toast_error"), "error");
  }
};

/* =============================================================================
   SORTING & FILTERING
   ============================================================================= */

/**
 * Reads the sort toggle from the UI, sorts the history buffer accordingly,
 * then re-applies the active search filter and re-renders.
 */
window.sortAndDisplayTranscripts = () => {
  const sortToggle = document.getElementById("history-sort-toggle");
  // @ts-ignore
  const isNewestFirst = sortToggle && sortToggle.checked;

  const sortedBuffer = [...transcriptHistoryBuffer].sort((a, b) => {
    const timeA = new Date(a.timestamp || 0).getTime();
    const timeB = new Date(b.timestamp || 0).getTime();
    return isNewestFirst ? timeB - timeA : timeA - timeB;
  });

  // Keep the Fuse index in sync with the new sort order
  if (fuseSearchInstance) {
    fuseSearchInstance.setCollection(sortedBuffer);
  }

  transcriptHistoryBuffer = sortedBuffer;
  window.filterTranscripts();
};

/**
 * Filters the history buffer against the current search input value.
 * Uses Fuse.js for fuzzy matching when available; falls back to
 * a simple case-insensitive substring match.
 */
window.filterTranscripts = () => {
  const searchInput = document.getElementById("search-transcript");
  if (!searchInput) return;

  // @ts-ignore
  const searchText = searchInput.value.trim();
  let filteredResults = [];

  if (!searchText) {
    // No query — show everything
    filteredResults = transcriptHistoryBuffer;
  } else if (fuseSearchInstance) {
    // Fuzzy search via Fuse.js
    const results = fuseSearchInstance.search(searchText);
    filteredResults = results.map((res) => res.item);
  } else {
    // Fallback: plain case-insensitive substring match
    const queryLower = searchText.toLowerCase();
    filteredResults = transcriptHistoryBuffer.filter((item) =>
      item?.text?.toLowerCase().includes(queryLower),
    );
  }

  window.displayTranscripts(filteredResults);
};

/* =============================================================================
   HISTORY DELETION
   ============================================================================= */

/**
 * Prompts the user with a confirmation modal before permanently clearing
 * all transcription history.
 */
window.confirmClearHistory = () => {
  window.showConfirmModal(window.t("confirm_clear_history_text"), async () => {
    if (!window.isApiReady()) return;

    try {
      const success = await window.pywebview.api.delete_history();

      if (success) {
        transcriptHistoryBuffer = [];
        currentFilteredData = [];
        if (fuseSearchInstance) fuseSearchInstance.setCollection([]);

        const searchInput = document.getElementById("search-transcript");
        // @ts-ignore
        if (searchInput) searchInput.value = "";

        window.displayTranscripts([]);
      } else {
        window.showToast("Failed to delete history.", "error");
      }
    } catch (error) {
      console.error("[History] Delete failed:", error);
      window.showToast("An error occurred while deleting history.", "error");
    }
  });
};

/* =============================================================================
   INFINITE SCROLL
   ============================================================================= */

/**
 * Attaches a scroll listener to the main content container.
 * Triggers the next batch render when the user scrolls within 100px of the bottom.
 */
window.setupHistoryInfiniteScroll = () => {
  const scrollContainer = document.querySelector(".main-content");
  if (!scrollContainer) return;

  scrollContainer.addEventListener("scroll", () => {
    const listElement = document.getElementById("transcript-list");

    // Only run when the history tab is active and visible in the layout
    if (!listElement || listElement.offsetParent === null) return;

    const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
    const isNearBottom = scrollTop + clientHeight >= scrollHeight - 100;

    if (isNearBottom && historyRenderIndex < currentFilteredData.length) {
      window.renderNextHistoryBatch();
    }
  });
};

/* =============================================================================
   DOM EVENT LISTENERS
   ============================================================================= */

document.addEventListener("DOMContentLoaded", () => {
  const transcriptList = document.getElementById("transcript-list");

  if (transcriptList) {
    transcriptList.addEventListener("click", async (e) => {
      // ── Copy button inside a code accordion ──────────────────────────────
      const copyBtn = e.target.closest(".btn-copy-action");
      if (copyBtn) {
        e.stopPropagation();
        e.preventDefault();

        const accordion = copyBtn.closest(".code-accordion");
        const codeElement = accordion?.querySelector("code");

        if (codeElement) {
          const textToCopy = codeElement.innerText;
          try {
            await navigator.clipboard.writeText(textToCopy);
            triggerCopyFeedback(copyBtn);
          } catch (_) {
            // Fallback for webviews that block the Clipboard API
            const textarea = document.createElement("textarea");
            textarea.value = textToCopy;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
            triggerCopyFeedback(copyBtn);
          }
        }
        return;
      }

      // ── Accordion expand / collapse ──────────────────────────────────────
      const accordion = e.target.closest(".code-accordion");

      // Static (short) blocks are always expanded — do not toggle them
      if (accordion && !accordion.classList.contains("static")) {
        // Ignore clicks that are part of a text selection
        const selection = window.getSelection();
        if (selection && selection.toString().length > 0) return;

        accordion.classList.toggle("expanded");
      }
    });
  }

  /**
   * Swaps the copy icon for a checkmark and reverts after 2 seconds.
   *
   * @param {HTMLButtonElement} btn - The copy button element.
   */
  function triggerCopyFeedback(btn) {
    const iconCopy = btn.querySelector(".icon-copy");
    const iconCheck = btn.querySelector(".icon-check");

    if (iconCopy && iconCheck) {
      iconCopy.style.display = "none";
      iconCheck.style.display = "block";

      setTimeout(() => {
        iconCheck.style.display = "none";
        iconCopy.style.display = "block";
      }, 2000);
    }
  }

  // Live search as the user types
  const searchInput = document.getElementById("search-transcript");
  if (searchInput) {
    searchInput.addEventListener("input", window.filterTranscripts);
  }
});
