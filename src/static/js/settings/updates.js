/* --- src/static/js/settings/updates.js --- */

// State variable to store the download URL received from the backend
window.currentUpdateUrl = null;

/**
 * Called by the Python backend during the download process.
 * Updates the progress bar in the sidebar button.
 * @param {number} percent - The current download percentage (0-100).
 */
window.updateDownloadProgress = (percent) => {
  const btn = document.getElementById("update-app-sidebar-button");
  if (btn) {
    btn.classList.add("downloading");
    // Update CSS variable for the gradient effect
    btn.style.setProperty("--download-progress", percent + "%");

    const textSpan = btn.querySelector(".button-text");
    if (textSpan) {
      textSpan.textContent = `${Math.round(percent)}%`;
    }
  }
};

/**
 * Called by the Python backend when the download is complete.
 * Updates the UI to indicate installation is starting.
 */
window.finalizeUpdate = () => {
  const btn = document.getElementById("update-app-sidebar-button");
  if (btn) {
    btn.style.setProperty("--download-progress", "100%");
    const textSpan = btn.querySelector(".button-text");
    if (textSpan) textSpan.textContent = "Installation...";
  }
};

/**
 * Called by the Python backend if an error occurs during the update.
 * Resets the UI and displays a toast error.
 * @param {string} errorMessage - The error details.
 */
window.showUpdateError = (errorMessage) => {
  console.error(errorMessage);
  window.showToast("Update failed", "error");

  const btn = document.getElementById("update-app-sidebar-button");
  if (btn) {
    btn.classList.remove("downloading");
    btn.style.removeProperty("--download-progress");
    const textSpan = btn.querySelector(".button-text");
    if (textSpan) textSpan.textContent = "Mettre à jour";
  }
};

/**
 * Queries the backend to check if a new version is available.
 * If yes, it reveals the update button in the sidebar.
 */
window.checkForUpdates = () => {
  if (!window.isApiReady()) return;

  window.pywebview.api
    .check_for_updates()
    .then((response) => {
      if (response && response.update_available) {
        const updateBtn = document.getElementById("update-app-sidebar-button");
        if (updateBtn) {
          // Remove the class that hides the button
          updateBtn.classList.remove("hidden-by-default");
          // Store URL globally for the click handler
          window.currentUpdateUrl = response.update_url;
        }
      }
    })
    .catch((err) => console.error("Update check failed:", err));
};

/**
 * Handles the click on the "Update" button inside the confirmation modal.
 * Closes the modal and triggers the download process.
 */
window.handleUpdateConfirmation = () => {
  if (
    typeof window.currentUpdateUrl !== "undefined" &&
    window.currentUpdateUrl &&
    window.isApiReady()
  ) {
    // 1. Close the modal immediately
    const modal = document.getElementById("update-confirm-modal-backdrop");
    if (modal) {
      modal.classList.remove("visible");
      setTimeout(() => (modal.style.display = "none"), 200);
    }

    // 2. Prepare the sidebar button UI
    const sidebarBtn = document.getElementById("update-app-sidebar-button");
    if (sidebarBtn) {
      sidebarBtn.classList.add("downloading");
      sidebarBtn.style.setProperty("--download-progress", "0%");
      const textSpan = sidebarBtn.querySelector(".button-text");
      if (textSpan) textSpan.textContent = "0%";
    }

    // 3. Trigger backend download
    window.pywebview.api.download_and_run_update(window.currentUpdateUrl);
  }
};
