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
 * Renders the list of transcripts into the DOM.
 * Handles Markdown parsing, syntax highlighting, and math rendering.
 *
 * @param {TranscriptEntry[]} dataToDisplay - Filtered list of transcripts.
 */
window.displayTranscripts = (dataToDisplay) => {
  const listContainer = document.getElementById("transcript-list");
  const noDataMessage = document.getElementById("no-transcripts");
  const emptySearchMessage = document.getElementById("empty-search-result");
  const searchInput = document.getElementById("search-transcript");

  if (!listContainer || !noDataMessage || !emptySearchMessage) return;

  // Initialize Markdown-it parser if available
  let markdownParser = null;
  // @ts-ignore
  if (typeof window.markdownit !== "undefined") {
    // @ts-ignore
    markdownParser = window.markdownit({
      html: false,
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
  }

  // 3. Render Items
  dataToDisplay.forEach((transcript, index) => {
    if (!transcript || !transcript.id || !transcript.text) return;

    const listItem = document.createElement("li");
    listItem.className = "transcript-item";
    listItem.id = `transcript-${transcript.id}`;
    listItem.setAttribute("data-timestamp", String(transcript.timestamp));
    // Staggered animation effect
    listItem.style.animationDelay = `${index * 0.05}s`;

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

    if (markdownParser) {
      // --- Pre-processing for Markdown ---
      let processedText = rawText;

      // Remove chat prefixes like [User] or [AI]
      processedText = processedText.replace(/^\[(User|AI)\]\s*/gim, "");

      // Ensure code blocks are properly spaced
      processedText = processedText.replace(/([^\n])\s*(```)/g, "$1\n\n$2");
      processedText = processedText.replace(/(```[^\n]*)\n{3,}/g, "$1\n\n");
      processedText = processedText.replace(/(```\s*)\n{2,}([^\n])/g, "$1\n$2");

      // Fix table formatting iteratively
      let hasTableChanged = true;
      let iterations = 0;
      while (hasTableChanged && iterations < 10) {
        hasTableChanged = false;
        const newText = processedText.replace(/(\|.*)\n{2,}(\s*\|)/g, "$1\n$2");
        if (newText !== processedText) {
          processedText = newText;
          hasTableChanged = true;
        }
        iterations++;
      }

      // Ensure tables have headers separator row
      processedText = processedText.replace(
        /((?:\s*\|[^\n]+\|\s*\n?)+)/g,
        (tableBlock) => {
          const lines = tableBlock
            .trim()
            .split("\n")
            .filter((l) => l.trim());
          if (lines.length < 2) return tableBlock;

          const secondLine = lines[1].trim();
          // Check if separator line exists (e.g. |---|---|)
          if (/^\|[\s\-:|]+\|$/.test(secondLine)) return tableBlock;

          // Generate separator line
          const firstLine = lines[0];
          const colCount = Math.max(
            1,
            (firstLine.match(/\|/g) || []).length - 1
          );
          const separator = "|" + " --- |".repeat(colCount);

          return (
            "\n" + [lines[0], separator, ...lines.slice(1)].join("\n") + "\n"
          );
        }
      );

      // Escape LaTeX delimiters to prevent MD parser from eating them
      const protectedText = processedText
        .replace(/\\\(/g, "\\\\(")
        .replace(/\\\)/g, "\\\\)")
        .replace(/\\\[/g, "\\\\[")
        .replace(/\\\]/g, "\\\\]");

      renderedHtml = markdownParser.render(protectedText);

      // Clean up excess newlines/breaks in generated HTML
      renderedHtml = renderedHtml.replace(
        /(<p>\s*<\/p>|<br\s*\/?>|\n)+$/gi,
        ""
      );
      renderedHtml = renderedHtml.replace(/(<br\s*\/?>\s*){3,}/gi, "<br><br>");
    } else {
      // Fallback: Simple text escaping
      renderedHtml = window.escapeHtml(rawText).replace(/\n/g, "<br>");
    }

    listItem.innerHTML = `
        <div class="transcript-header">
            <div class="transcript-time">${formattedTime}</div>
            <div class="transcript-actions">
                <button class="button copy-btn" type="button" aria-label="${window.t(
                  "btn_copy"
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

    // Render Math (KaTeX) if available
    // @ts-ignore
    if (window.renderMathInElement) {
      setTimeout(() => {
        const textContainer = listItem.querySelector(".transcript-text");
        if (textContainer) {
          try {
            // @ts-ignore
            window.renderMathInElement(textContainer, {
              delimiters: [
                { left: "$$", right: "$$", display: true },
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

    // Bind Copy Event
    const copyButton = listItem.querySelector(".copy-btn");
    copyButton?.addEventListener("click", () => {
      // @ts-ignore
      window.copyTranscriptText(rawText, copyButton);
    });

    listContainer.appendChild(listItem);
  });
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
        item && item.text && item.text.toLowerCase().includes(searchLower)
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

// Initialize search listener
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-transcript");
  if (searchInput) {
    searchInput.addEventListener("input", window.filterTranscripts);
  }
});
