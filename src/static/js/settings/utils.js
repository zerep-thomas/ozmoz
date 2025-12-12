/* --- static/js/settings/utils.js --- */

/**
 * Checks if the PyWebView API is available and ready.
 * @returns {boolean} True if API is ready.
 */
window.isApiReady = () => {
  return (
    typeof window.pywebview !== "undefined" &&
    window.pywebview.api &&
    typeof window.pywebview.api.get_app_version === "function"
  );
};

/**
 * Escapes HTML characters to prevent XSS.
 * @param {string} text - The text to escape.
 * @returns {string} Escaped text.
 */
window.escapeHtml = (text) => {
  if (typeof text !== "string") return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
};

/**
 * Creates a debounced function that delays invoking func until after wait milliseconds.
 * @param {Function} func - The function to debounce.
 * @param {number} wait - The delay in milliseconds.
 * @returns {Function} The debounced function.
 */
window.debounce = (func, wait) => {
  let timeout;
  return (...args) => {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
};

/**
 * Displays a toast notification.
 * @param {string} message - The message to display.
 * @param {string} [type="info"] - The type of toast (info, error, success).
 * @param {number} [duration=3000] - Duration in ms.
 */
window.showToast = (message, type = "info", duration = 3000) => {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add("show");
  });

  setTimeout(() => {
    toast.classList.remove("show");
    toast.addEventListener("transitionend", () => {
      if (toast.parentElement) {
        toast.remove();
      }
    });
  }, duration);
};

/**
 * Initializes custom dropdown behavior.
 */
window.initCustomSelects = () => {
  const customSelects = document.getElementsByClassName(
    "custom-select-container"
  );

  if (!window._globalSelectCloseAttached) {
    document.addEventListener("click", (e) => {
      Array.from(customSelects).forEach((selectContainer) => {
        const selectedDisplay =
          selectContainer.querySelector(".select-selected");
        const itemsContainer = selectContainer.querySelector(".select-items");
        if (
          selectedDisplay &&
          itemsContainer &&
          !selectContainer.contains(e.target)
        ) {
          itemsContainer.classList.add("select-hide");
          selectedDisplay.classList.remove("select-arrow-active");
        }
      });
    });
    window._globalSelectCloseAttached = true;
  }

  Array.from(customSelects).forEach((selectContainer) => {
    if (selectContainer.dataset.hasInit === "true") return;

    const selectedDisplay = selectContainer.querySelector(".select-selected");
    const itemsContainer = selectContainer.querySelector(".select-items");

    if (selectedDisplay && itemsContainer) {
      selectedDisplay.addEventListener("click", (e) => {
        e.stopPropagation();
        Array.from(customSelects).forEach((otherContainer) => {
          if (otherContainer !== selectContainer) {
            otherContainer
              .querySelector(".select-items")
              ?.classList.add("select-hide");
            otherContainer
              .querySelector(".select-selected")
              ?.classList.remove("select-arrow-active");
          }
        });
        itemsContainer.classList.toggle("select-hide");
        selectedDisplay.classList.toggle("select-arrow-active");
      });
      selectContainer.dataset.hasInit = "true";
    }
  });
};

// --- Modal Utilities ---

window.showConfirmModal = (message, onConfirm, onCancel) => {
  const backdrop = document.getElementById("confirm-modal-backdrop");
  const textElement = document.getElementById("confirm-modal-text");
  const confirmBtn = document.getElementById("confirm-modal-delete");
  const cancelBtn = document.getElementById("confirm-modal-cancel");

  if (!backdrop || !textElement || !confirmBtn || !cancelBtn) return;

  textElement.textContent = message;

  // Remove old listeners by cloning
  const newConfirmBtn = confirmBtn.cloneNode(true);
  confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

  const newCancelBtn = cancelBtn.cloneNode(true);
  cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

  newConfirmBtn.addEventListener("click", () => {
    if (onConfirm) onConfirm();
    window.hideConfirmModal();
  });

  newCancelBtn.addEventListener("click", () => {
    if (onCancel) onCancel();
    window.hideConfirmModal();
  });

  const backdropClickHandler = (event) => {
    if (event.target === backdrop) {
      window.hideConfirmModal();
      backdrop.removeEventListener("click", backdropClickHandler);
    }
  };
  backdrop.addEventListener("click", backdropClickHandler);

  backdrop.style.display = "flex";
  setTimeout(() => backdrop.classList.add("visible"), 10);
};

window.hideConfirmModal = () => {
  const backdrop = document.getElementById("confirm-modal-backdrop");
  if (!backdrop) return;
  backdrop.classList.remove("visible");
  setTimeout(() => (backdrop.style.display = "none"), 200);
};

window.showConflictModal = () => {
  const backdrop = document.getElementById("conflict-modal-backdrop");
  if (!backdrop) return;
  backdrop.style.display = "flex";
  setTimeout(() => backdrop.classList.add("visible"), 10);
};

window.hideConflictModal = () => {
  const backdrop = document.getElementById("conflict-modal-backdrop");
  if (!backdrop) return;
  backdrop.classList.remove("visible");
  setTimeout(() => (backdrop.style.display = "none"), 200);
};
