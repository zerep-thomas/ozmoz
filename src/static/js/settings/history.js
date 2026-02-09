/* --- src/static/js/settings/history.js --- */

/**
 * @fileoverview History Management Module.
 * Handles fetching, searching, sorting, and rendering of transcription history.
 */

/**
 * @typedef {Object} TranscriptEntry
 * @property {number} id - Unique identifier.
 * @property {string} text - The transcribed text content.
 * @property {number} timestamp - Unix timestamp of creation.
 */

/**
 * Local buffer for history entries to enable fast filtering/sorting.
 * @type {TranscriptEntry[]}
 */
let transcriptHistoryBuffer = [];

/**
 * Currently filtered list used for display and infinite scrolling.
 * @type {TranscriptEntry[]}
 */
let currentFilteredData = [];

/**
 * Pagination state for infinite scrolling.
 */
let historyRenderIndex = 0;
const HISTORY_BATCH_SIZE = 20;
let markdownParserInstance = null;

/**
 * Fuse.js instance for fuzzy searching.
 * @type {Object|null}
 */
let fuseSearchInstance = null;

/**
 * Fetches history from the backend and initializes the view.
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

/**
 * Initializes or re-initializes the Fuse.js search index.
 */
window.initFuzzySearch = () => {
  // @ts-ignore - Fuse is loaded globally via vendor script
  if (typeof window.Fuse === "undefined") {
    console.warn("[History] Fuse.js library missing. Search disabled.");
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

/**
 * Initializes the Markdown parser once to avoid overhead.
 */
function initMarkdownParser() {
  if (markdownParserInstance) return;

  // @ts-ignore
  if (typeof window.markdownit !== "undefined") {
    // @ts-ignore
    markdownParserInstance = window.markdownit({
      html: false, // Security: disable raw HTML
      linkify: true,
      breaks: true,
      typographer: true,
      highlight: (str, lang) => {
        // @ts-ignore
        if (lang && window.hljs && window.hljs.getLanguage(lang)) {
          try {
            return (
              '<pre class="hljs"><code>' +
              // @ts-ignore
              window.hljs.highlight(str, {
                language: lang,
                ignoreIllegals: true,
              }).value +
              "</code></pre>"
            );
          } catch (__) {}
        }
        return (
          '<pre class="hljs"><code>' + window.escapeHtml(str) + "</code></pre>"
        );
      },
    });
  }
}

/**
 * Renders the list of transcripts into the DOM.
 * Resets the infinite scroll state and renders the first batch.
 *
 * @param {TranscriptEntry[]} dataToDisplay - Filtered list of transcripts.
 */
window.displayTranscripts = (dataToDisplay) => {
  const listContainer = document.getElementById("transcript-list");
  const noDataMessage = document.getElementById("no-transcripts");
  const emptySearchMessage = document.getElementById("empty-search-result");
  const searchInput = document.getElementById("search-transcript");

  if (!listContainer || !noDataMessage || !emptySearchMessage) return;

  // Update global state for scrolling
  currentFilteredData = dataToDisplay;
  historyRenderIndex = 0;

  // Initialize parser if needed
  initMarkdownParser();

  // Clear current view
  listContainer.innerHTML = "";

  // 1. Handle Empty State (No history at all)
  if (transcriptHistoryBuffer.length === 0) {
    noDataMessage.style.display = "block";
    emptySearchMessage.style.display = "none";
    listContainer.style.display = "none";
    return;
  }

  noDataMessage.style.display = "none";
  listContainer.style.display = "block";

  // 2. Handle Search State (History exists, but filter matches nothing)
  const isSearchActive = searchInput && searchInput.value.length > 0;
  if (dataToDisplay.length === 0 && isSearchActive) {
    emptySearchMessage.style.display = "block";
  } else {
    emptySearchMessage.style.display = "none";
    // Render first batch
    window.renderNextHistoryBatch();
  }
};

/**
 * Appends the next batch of items to the DOM.
 * Used for infinite scrolling to prevent UI lag.
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

    // Only animate the first batch to avoid flickering during scroll
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
      // --- Pre-processing for Markdown & LaTeX ---
      let processedText = rawText;

      // 1. Remove chat prefixes (User/AI)
      processedText = processedText.replace(/^\[(User|AI)\]\s*/gim, "");

      // 2. Protect Block Equations: \[ ... \] -> $$ ... $$
      // We perform three critical fixes inside the callback:
      // a. Replace \[ with $$ to use a safer delimiter for Markdown.
      // b. Remove newlines (\n) inside the block, otherwise Markdown inserts <br> which breaks KaTeX.
      // c. Double backslashes (e.g., \int -> \\int) so Markdown doesn't eat them.
      processedText = processedText.replace(
        /\\\[([\s\S]*?)\\\]/g,
        (match, content) => {
          const cleanContent = content
            .replace(/\\/g, "\\\\")
            .replace(/\n/g, " ");
          return `$$${cleanContent}$$`;
        },
      );

      // 3. Protect Inline Equations: \( ... \) -> \\( ... \\)
      // Same logic: protect backslashes and remove newlines.
      processedText = processedText.replace(
        /\\\(([\s\S]*?)\\\)/g,
        (match, content) => {
          const cleanContent = content
            .replace(/\\/g, "\\\\")
            .replace(/\n/g, " ");
          return `\\\\(${cleanContent}\\\\)`;
        },
      );

      // 4. Render Markdown
      renderedHtml = markdownParserInstance.render(processedText);

      // 5. Cleanup Markdown artifacts
      // Remove empty paragraphs or excessive breaks
      renderedHtml = renderedHtml.replace(
        /(<p>\s*<\/p>|<br\s*\/?>|\n)+$/gi,
        "",
      );
      renderedHtml = renderedHtml.replace(/(<br\s*\/?>\s*){3,}/gi, "<br><br>");
    } else {
      // Fallback if parser fails
      renderedHtml = window.escapeHtml(rawText).replace(/\n/g, "<br>");
    }

    listItem.innerHTML = `
        <div class="transcript-header">
            <div class="transcript-time">${formattedTime}</div>
            <div class="transcript-actions">
                <button class="button copy-btn" type="button" aria-label="${window.t(
                  "btn_copy",
                )}">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
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

  // Render Math (KaTeX) only on the new items
  // @ts-ignore
  if (window.renderMathInElement) {
    setTimeout(() => {
      // Optimization: Select only items from the current batch
      const allItems = listContainer.querySelectorAll(".transcript-text");
      const start = Math.max(0, allItems.length - batch.length);

      for (let i = start; i < allItems.length; i++) {
        try {
          // @ts-ignore
          window.renderMathInElement(allItems[i], {
            delimiters: [
              { left: "$$", right: "$$", display: true }, // Main block delimiter
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

/**
 * Copies text to clipboard and provides visual feedback on the button.
 *
 * @param {string} textToCopy - The content to copy.
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

    // Success Feedback
    if (textSpan) textSpan.textContent = window.t("copied");
    buttonElement.classList.add("copied");
    buttonElement.disabled = true;

    // Revert after delay
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

/**
 * Sorts the global buffer based on UI toggle and re-renders the list.
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

  // Update Fuse index with sorted data
  if (fuseSearchInstance) {
    fuseSearchInstance.setCollection(sortedBuffer);
  }

  transcriptHistoryBuffer = sortedBuffer;
  window.filterTranscripts();
};

/**
 * Filters transcripts based on the search input value.
 * Uses Fuse.js if available, otherwise simple string matching.
 */
window.filterTranscripts = () => {
  const searchInput = document.getElementById("search-transcript");
  if (!searchInput) return;

  // @ts-ignore
  const searchText = searchInput.value.trim();
  let filteredResults = [];

  if (!searchText) {
    filteredResults = transcriptHistoryBuffer;
  } else if (fuseSearchInstance) {
    const results = fuseSearchInstance.search(searchText);
    filteredResults = results.map((res) => res.item);
  } else {
    // Fallback: Simple case-insensitive includes
    const searchLower = searchText.toLowerCase();
    filteredResults = transcriptHistoryBuffer.filter(
      (item) =>
        item && item.text && item.text.toLowerCase().includes(searchLower),
    );
  }

  window.displayTranscripts(filteredResults);
};

/**
 * Triggers the deletion confirmation modal.
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
      window.showToast("An error occurred.", "error");
    }
  });
};

/**
 * Sets up the scroll listener for infinite scrolling.
 * Attached to the main content container which holds the list.
 */
window.setupHistoryInfiniteScroll = () => {
  const scrollContainer = document.querySelector(".main-content");
  if (!scrollContainer) return;

  scrollContainer.addEventListener("scroll", () => {
    const listElement = document.getElementById("transcript-list");
    // Only execute if history tab is active and visible
    if (!listElement || listElement.offsetParent === null) return;

    const { scrollTop, scrollHeight, clientHeight } = scrollContainer;

    // Check if we are near the bottom (within 100px)
    if (scrollTop + clientHeight >= scrollHeight - 100) {
      // Load next batch if available
      if (historyRenderIndex < currentFilteredData.length) {
        window.renderNextHistoryBatch();
      }
    }
  });
};

// Initialize search listener
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-transcript");
  if (searchInput) {
    searchInput.addEventListener("input", window.filterTranscripts);
  }
});
