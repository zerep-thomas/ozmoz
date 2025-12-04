/* --- static/js/settings/replacements.js --- */

let allReplacements = [];
let replacementFilterListenerAttached = false;

/**
 * Loads replacements from backend.
 */
window.loadReplacements = () => {
  if (!window.isApiReady()) {
    displayReplacements([]);
    return;
  }
  window.pywebview.api
    .get_replacements()
    .then((replacements) => {
      allReplacements = replacements || [];
      filterAndDisplayReplacements();
    })
    .catch((err) => {
      console.error("Error loading replacements:", err);
      displayReplacements([]);
    });
};

/**
 * Renders the replacement list.
 * @param {Array} replacementsToDisplay - Filtered replacements.
 */
function displayReplacements(replacementsToDisplay) {
  const list = document.getElementById("replacements-list");
  const noReplacements = document.getElementById("no-replacements");
  const emptySearch = document.getElementById(
    "empty-replacement-search-result"
  );

  if (!list || !noReplacements || !emptySearch) return;

  list.innerHTML = "";

  if (allReplacements.length === 0) {
    noReplacements.style.display = "block";
    emptySearch.style.display = "none";
    list.style.display = "none";
    return;
  }

  noReplacements.style.display = "none";
  list.style.display = "block";

  if (
    replacementsToDisplay.length === 0 &&
    document.getElementById("filter-replacements").value
  ) {
    emptySearch.style.display = "block";
  } else {
    emptySearch.style.display = "none";
  }

  replacementsToDisplay.forEach((item) => {
    if (!item || typeof item.word1 === "undefined") return;
    const originalIndex = allReplacements.findIndex(
      (r) => r.word1 === item.word1 && r.word2 === item.word2
    );

    const li = document.createElement("li");
    li.className = "replacement-item";

    // Basic HTML structure
    li.innerHTML = `
            <div class="replacement-text">
                <span class="original-text" title="${window.escapeHtml(
                  item.word1
                )}">${window.escapeHtml(item.word1)}</span>
                <span class="replacement-arrow-small" aria-hidden="true">→</span>
                <span class="replacement-text-value" title="${window.escapeHtml(
                  item.word2
                )}">${window.escapeHtml(item.word2)}</span>
            </div>
            <button class="button delete-replacement" type="button" aria-label="Delete">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
        `;

    // Attach listener
    const deleteBtn = li.querySelector(".delete-replacement");
    deleteBtn.addEventListener("click", () =>
      window.deleteReplacement(originalIndex)
    );

    list.appendChild(li);
  });
}

window.addReplacement = () => {
  const originalInput = document.getElementById("original-word");
  const replacementInput = document.getElementById("replacement-word");
  if (!originalInput || !replacementInput) return;

  hideReplacementFormFeedback();
  originalInput.style.borderColor = "";
  replacementInput.style.borderColor = "";

  const original = originalInput.value.trim();
  const replacement = replacementInput.value.trim();

  if (original && replacement && original !== replacement) {
    const exists = allReplacements.some(
      (r) => r.word1.toLowerCase() === original.toLowerCase()
    );
    if (exists) {
      showReplacementFormFeedback(
        `Replacement for "${original}" already exists.`
      );
      originalInput.style.borderColor = "var(--color-red)";
      return;
    }

    if (!window.isApiReady()) {
      window.showToast("Error: API not ready.", "error");
      return;
    }

    window.pywebview.api
      .add_replacement(original, replacement)
      .then(() => {
        originalInput.value = "";
        replacementInput.value = "";
        window.loadReplacements();
        originalInput.focus();
      })
      .catch((err) => {
        console.error("Error adding replacement:", err);
        window.showToast("Error adding replacement.", "error");
      });
  } else if (!original) {
    originalInput.style.borderColor = "var(--color-red)";
    originalInput.focus();
  } else if (!replacement) {
    replacementInput.style.borderColor = "var(--color-red)";
    replacementInput.focus();
  }
};

window.deleteReplacement = (originalIndex) => {
  if (originalIndex < 0 || originalIndex >= allReplacements.length) return;

  const item = allReplacements[originalIndex];

  let message = window.t("confirm_delete_replacement");
  message = message
    .replace("{word1}", item.word1)
    .replace("{word2}", item.word2);

  window.showConfirmModal(
    `Delete replacement "${item.word1}" → "${item.word2}"?`,
    () => {
      if (!window.isApiReady()) return;

      window.pywebview.api
        .delete_replacement(originalIndex)
        .then((success) => {
          if (success) {
            window.loadReplacements();
          } else {
            window.showToast("Failed to delete replacement.", "error");
          }
        })
        .catch(() => {
          window.showToast("Error occurred.", "error");
        });
    }
  );
};

function showReplacementFormFeedback(message) {
  const feedbackEl = document.getElementById("replacement-form-feedback");
  if (feedbackEl) {
    feedbackEl.textContent = message;
    feedbackEl.style.display = "block";
  }
}

function hideReplacementFormFeedback() {
  const feedbackEl = document.getElementById("replacement-form-feedback");
  if (feedbackEl) {
    feedbackEl.style.display = "none";
  }
}

window.setupReplacementFilterListener = () => {
  const filterInput = document.getElementById("filter-replacements");
  if (filterInput && !replacementFilterListenerAttached) {
    filterInput.addEventListener(
      "input",
      window.debounce(filterAndDisplayReplacements, 250)
    );
    replacementFilterListenerAttached = true;
  }
};

function filterAndDisplayReplacements() {
  const filterInput = document.getElementById("filter-replacements");
  if (!filterInput) return;
  const query = filterInput.value.toLowerCase();

  if (!query) {
    displayReplacements(allReplacements);
    return;
  }
  const filtered = allReplacements.filter(
    (item) =>
      (item.word1 && item.word1.toLowerCase().includes(query)) ||
      (item.word2 && item.word2.toLowerCase().includes(query))
  );
  displayReplacements(filtered);
}
