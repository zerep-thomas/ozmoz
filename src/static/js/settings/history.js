/* --- static/js/settings/history.js --- */

let allTranscripts = [];

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
      window.sortAndDisplayTranscripts();
    })
    .catch((err) => {
      console.error("History loading error:", err);
      window.displayTranscripts([]);
    });
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

  transcriptList.innerHTML = "";

  if (allTranscripts.length === 0) {
    noTranscripts.style.display = "block";
    emptySearch.style.display = "none";
    transcriptList.style.display = "none";
    return;
  }

  noTranscripts.style.display = "none";
  transcriptList.style.display = "block";

  if (
    dataToDisplay.length === 0 &&
    document.getElementById("search-transcript").value
  ) {
    emptySearch.style.display = "block";
  } else {
    emptySearch.style.display = "none";
  }

  dataToDisplay.forEach((transcript) => {
    if (!transcript || !transcript.id || !transcript.text) return;

    const li = document.createElement("li");
    li.className = "transcript-item";
    li.id = `transcript-${transcript.id}`;
    li.setAttribute("data-timestamp", transcript.timestamp);

    const date = new Date(transcript.timestamp);
    const time = date.toLocaleString(window.getCurrentLanguage(), {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    // Basic Structure
    li.innerHTML = `
            <div class="transcript-time">${time}</div>
            <div class="transcript-text">${window.escapeHtml(
              transcript.text
            )}</div>
            <div class="transcript-actions">
                <button class="button copy-btn" type="button" aria-label="${window.t(
                  "btn_copy"
                )}">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    <span class="copy-btn-text">${window.t("btn_copy")}</span>
                </button>
            </div>
        `;

    // Attach listener securely
    const copyBtn = li.querySelector(".copy-btn");
    copyBtn.addEventListener("click", () =>
      window.copyTranscript(transcript.id, copyBtn)
    );

    transcriptList.appendChild(li);
  });
};

window.copyTranscript = (id, buttonElement) => {
  const textElement = document.querySelector(
    `#transcript-${id} .transcript-text`
  );
  if (!textElement) return;

  const text = textElement.innerText;
  const textSpan = buttonElement.querySelector(".copy-btn-text");

  if (!window.isApiReady()) {
    window.showToast(window.t("toast_error"), "error");
    return;
  }

  window.pywebview.api
    .copy_text(text)
    .then(() => {
      if (textSpan) textSpan.textContent = window.t("copied");
      buttonElement.classList.add("copié");
      buttonElement.disabled = true;
      setTimeout(() => {
        if (textSpan) textSpan.textContent = window.t("btn_copy");
        buttonElement.classList.remove("copié");
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
  allTranscripts = sorted;
  window.filterTranscripts();
};

window.filterTranscripts = () => {
  const searchInput = document.getElementById("search-transcript");
  if (!searchInput) return;
  const searchText = searchInput.value.toLowerCase();
  const filtered = allTranscripts.filter(
    (item) => item && item.text && item.text.toLowerCase().includes(searchText)
  );
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
