/* --- src/static/js/settings/history.js --- */

let allTranscripts = [];
let fuseInstance = null;

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
      window.initFuzzySearch();
      window.sortAndDisplayTranscripts();
    })
    .catch((err) => {
      console.error("History loading error:", err);
      window.displayTranscripts([]);
    });
};

window.initFuzzySearch = () => {
  if (typeof window.Fuse === "undefined") {
    console.error("Fuse.js library not loaded.");
    return;
  }
  const options = {
    keys: ["text"],
    includeScore: true,
    threshold: 0.4,
    ignoreLocation: true,
    minMatchCharLength: 2,
  };
  fuseInstance = new window.Fuse(allTranscripts, options);
};

window.displayTranscripts = (dataToDisplay) => {
  const transcriptList = document.getElementById("transcript-list");
  const noTranscripts = document.getElementById("no-transcripts");
  const emptySearch = document.getElementById("empty-search-result");

  if (!transcriptList || !noTranscripts || !emptySearch) return;

  let md = null;
  if (typeof window.markdownit !== "undefined") {
    md = window.markdownit({
      html: true,
      linkify: true,
      breaks: true,
      typographer: true,
      highlight: function (str, lang) {
        if (lang && window.hljs && window.hljs.getLanguage(lang)) {
          try {
            return (
              '<pre class="hljs"><code>' +
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

    let rawText = (transcript.text || "").trim();
    let contentHtml = "";

    if (md) {
      let formattedText = rawText;

      formattedText = formattedText.replace(/^\[(User|AI)\]\s*/gim, "");

      formattedText = formattedText.replace(/([^\n])\s*(```)/g, "$1\n\n$2");
      formattedText = formattedText.replace(/(```[^\n]*)\n{3,}/g, "$1\n\n");
      formattedText = formattedText.replace(/(```\s*)\n{2,}([^\n])/g, "$1\n$2");

      let hasChanged = true;
      let loopCount = 0;
      while (hasChanged && loopCount < 10) {
        hasChanged = false;
        const newText = formattedText.replace(/(\|.*)\n{2,}(\s*\|)/g, "$1\n$2");
        if (newText !== formattedText) {
          formattedText = newText;
          hasChanged = true;
        }
        loopCount++;
      }

      formattedText = formattedText.replace(
        /((?:\s*\|[^\n]+\|\s*\n?)+)/g,
        function (tableBlock) {
          const lines = tableBlock
            .trim()
            .split("\n")
            .filter((l) => l.trim());

          if (lines.length < 2) return tableBlock;

          const secondLine = lines[1].trim();
          const isSeparator = /^\|[\s\-:|]+\|$/.test(secondLine);

          if (isSeparator) return tableBlock;

          const firstLine = lines[0];
          const pipeCount = (firstLine.match(/\|/g) || []).length;
          const colCount = Math.max(1, pipeCount - 1);
          const separator = "|" + " --- |".repeat(colCount);

          const newLines = [lines[0], separator, ...lines.slice(1)];
          return "\n" + newLines.join("\n") + "\n";
        }
      );

      formattedText = formattedText.replace(/([^\n\|])\n(\|)/g, "$1\n\n$2");
      formattedText = formattedText.replace(
        /(\|[^\n]+)\n([^\|\n])/g,
        "$1\n\n$2"
      );

      formattedText = formattedText.replace(/\n{3,}/g, "\n\n");

      const protectedText = formattedText
        .replace(/\\\(/g, "\\\\(")
        .replace(/\\\)/g, "\\\\)")
        .replace(/\\\[/g, "\\\\[")
        .replace(/\\\]/g, "\\\\]");

      contentHtml = md.render(protectedText);

      contentHtml = contentHtml.replace(/(<p>\s*<\/p>|<br\s*\/?>|\n)+$/gi, "");

      contentHtml = contentHtml.replace(/(<br\s*\/?>\s*){3,}/gi, "<br><br>");
    } else {
      contentHtml = window.escapeHtml(rawText).replace(/\n/g, "<br>");
    }

    li.innerHTML = `
        <div class="transcript-header">
            <div class="transcript-time">${time}</div>
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
            <div class="transcript-text">${contentHtml}</div>
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
  if (fuseInstance) {
    fuseInstance.setCollection(sorted);
  }
  allTranscripts = sorted;
  window.filterTranscripts();
};

window.filterTranscripts = () => {
  const searchInput = document.getElementById("search-transcript");
  if (!searchInput) return;
  const searchText = searchInput.value.trim();
  let filtered = [];
  if (!searchText) {
    filtered = allTranscripts;
  } else if (fuseInstance) {
    const results = fuseInstance.search(searchText);
    filtered = results.map((result) => result.item);
  } else {
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

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-transcript");
  if (searchInput) {
    searchInput.addEventListener("input", window.filterTranscripts);
  }
});
