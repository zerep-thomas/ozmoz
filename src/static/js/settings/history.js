/* --- src/static/js/settings/history.js --- */

let allTranscripts = [];
let fuseInstance = null;

/**
 * Loads transcription history from the backend.
 */
window.loadTranscripts = () => {
  if (!window.isApiReady()) {
    console.error("API not available for history.");
    window.displayTranscripts([]);
    return;
  }
  window.pywebview.api
    .get_history()
    .then((data) => {
      allTranscripts = data || [];

      // Initialize/Update Fuzzy Search Index when data loads
      window.initFuzzySearch();

      window.sortAndDisplayTranscripts();
    })
    .catch((err) => {
      console.error("History loading error:", err);
      window.displayTranscripts([]);
    });
};

/**
 * Initializes the Fuse.js fuzzy search engine using the local library.
 */
window.initFuzzySearch = () => {
  if (typeof window.Fuse === "undefined") {
    console.error("Fuse.js library not loaded.");
    return;
  }

  const options = {
    keys: ["text"], // Search in the text content
    includeScore: true,
    threshold: 0.4, // 0.0 = exact match, 1.0 = match anything. 0.4 is good for typos.
    ignoreLocation: true, // Search anywhere in the string
    minMatchCharLength: 2,
  };

  fuseInstance = new window.Fuse(allTranscripts, options);
};

/**
 * Renders the transcript list.
 * @param {Array} dataToDisplay - Filtered transcripts.
 */
window.displayTranscripts = (dataToDisplay) => {
  const transcriptList = document.getElementById("transcript-list");
  const noTranscripts = document.getElementById("no-transcripts");
  const emptySearch = document.getElementById("empty-search-result");

  if (!transcriptList || !noTranscripts || !emptySearch) return;

  // Initialize Markdown rendering using local library
  let md = null;
  if (typeof window.markdownit !== "undefined") {
    md = window.markdownit({
      html: true,
      linkify: true,
      breaks: true,
      typographer: true,
    });
  } else {
    console.warn("Markdown-it library not loaded.");
  }

  transcriptList.innerHTML = "";

  if (allTranscripts.length === 0) {
    noTranscripts.style.display = "block";
    emptySearch.style.display = "none";
    transcriptList.style.display = "none";
    return;
  }

  noTranscripts.style.display = "none";
  transcriptList.style.display = "block";

  const searchValue = document.getElementById("search-transcript").value;
  if (dataToDisplay.length === 0 && searchValue) {
    emptySearch.style.display = "block";
  } else {
    emptySearch.style.display = "none";
  }

  dataToDisplay.forEach((transcript, index) => {
    if (!transcript || !transcript.id || !transcript.text) return;

    const li = document.createElement("li");
    li.className = "transcript-item";
    li.id = `transcript-${transcript.id}`;
    li.setAttribute("data-timestamp", transcript.timestamp);

    // Animation Stagger
    li.style.animationDelay = `${index * 0.05}s`;

    const date = new Date(transcript.timestamp);
    const time = date.toLocaleString(window.getCurrentLanguage(), {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    // 1. Initial cleanup
    let rawText = (transcript.text || "").trim();

    // Markdown Parsing
    let contentHtml = "";
    if (md) {
      // Fix Markdown spacing
      let formattedText = rawText.replace(/(\])\s*(#)/g, "$1\n\n$2");

      // Escape LaTeX
      const protectedText = formattedText
        .replace(/\\\(/g, "\\\\(")
        .replace(/\\\)/g, "\\\\)")
        .replace(/\\\[/g, "\\\\[")
        .replace(/\\\]/g, "\\\\]");

      contentHtml = md.render(protectedText);

      // 2. HTML Cleanup (Remove empty blocks at end)
      contentHtml = contentHtml.replace(
        /(<p>\s*<\/p>\s*|<br\s*\/?>\s*|\n)+$/gi,
        ""
      );
    } else {
      contentHtml = window.escapeHtml(rawText).replace(/\n/g, "<br>");
    }

    li.innerHTML = `
            <div class="transcript-time">${time}</div>
            <div class="transcript-text">${contentHtml}</div>
            <div class="transcript-actions">
                <button class="button copy-btn" type="button" aria-label="${window.t(
                  "btn_copy"
                )}">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    <span class="copy-btn-text">${window.t("btn_copy")}</span>
                </button>
            </div>
        `;

    if (window.renderMathInElement) {
      setTimeout(() => {
        const textContainer = li.querySelector(".transcript-text");
        if (textContainer) {
          try {
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
            console.warn("Math render error", e);
          }
        }
      }, 0);
    }

    const copyBtn = li.querySelector(".copy-btn");
    copyBtn.addEventListener("click", () => {
      window.copyTranscriptText(rawText, copyBtn);
    });

    transcriptList.appendChild(li);
  });
};

/**
 * Copies transcript text to clipboard.
 */
window.copyTranscriptText = (textToCopy, buttonElement) => {
  const textSpan = buttonElement.querySelector(".copy-btn-text");

  if (!window.isApiReady()) {
    window.showToast(window.t("toast_error"), "error");
    return;
  }

  window.pywebview.api
    .copy_text(textToCopy)
    .then(() => {
      if (textSpan) textSpan.textContent = window.t("copied");
      buttonElement.classList.add("copied");
      buttonElement.disabled = true;
      setTimeout(() => {
        if (textSpan) textSpan.textContent = window.t("btn_copy");
        buttonElement.classList.remove("copied");
        buttonElement.disabled = false;
      }, 2000);
    })
    .catch((err) => {
      console.error("Copy error: ", err);
      window.showToast(window.t("toast_error"), "error");
    });
};

window.sortAndDisplayTranscripts = () => {
  const sortToggle = document.getElementById("history-sort-toggle");
  const sortOrder = sortToggle && sortToggle.checked ? "newest" : "oldest";
  const sorted = [...allTranscripts].sort((a, b) => {
    const timeA = new Date(a.timestamp || 0).getTime();
    const timeB = new Date(b.timestamp || 0).getTime();
    return sortOrder === "newest" ? timeB - timeA : timeA - timeB;
  });

  // Re-initialize Fuse with sorted data if needed, or just let filter handle it
  if (fuseInstance) {
    fuseInstance.setCollection(sorted);
  }

  // Keep the sorted reference for fallback
  allTranscripts = sorted;
  window.filterTranscripts();
};

/**
 * Intelligent Filter using Fuse.js if available, falling back to simple includes.
 */
window.filterTranscripts = () => {
  const searchInput = document.getElementById("search-transcript");
  if (!searchInput) return;
  const searchText = searchInput.value.trim();

  let filtered = [];

  if (!searchText) {
    // If no search, show all (which are already sorted)
    filtered = allTranscripts;
  } else if (fuseInstance) {
    const results = fuseInstance.search(searchText);
    // Fuse returns { item, score, ... }, we just need the item
    filtered = results.map((result) => result.item);
  } else {
    // Fallback: Basic string matching
    const lowerSearch = searchText.toLowerCase();
    filtered = allTranscripts.filter(
      (item) =>
        item && item.text && item.text.toLowerCase().includes(lowerSearch)
    );
  }

  window.displayTranscripts(filtered);
};

window.confirmClearHistory = () => {
  window.showConfirmModal(window.t("confirm_clear_history_text"), () => {
    if (!window.isApiReady()) return;
    window.pywebview.api
      .delete_history()
      .then((success) => {
        if (success) {
          allTranscripts = [];
          if (fuseInstance) fuseInstance.setCollection([]);
          const searchInput = document.getElementById("search-transcript");
          if (searchInput) searchInput.value = "";
          window.displayTranscripts([]);
        } else {
          window.showToast("Failed to delete history.", "error");
        }
      })
      .catch((err) => {
        console.error("Error deleting history:", err);
        window.showToast("An error occurred.", "error");
      });
  });
};

// Add listener to the search input to trigger intelligent filtering
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-transcript");
  if (searchInput) {
    searchInput.addEventListener("input", window.filterTranscripts);
  }
});
