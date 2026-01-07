/* --- src/static/js/settings/logs.js --- */

/**
 * @fileoverview Log Management Module.
 * Handles fetching, filtering, rendering, and exporting application logs via the backend API.
 */

/**
 * @typedef {Object} LogEntry
 * @property {string} level - The severity level of the log (e.g., DEBUG, INFO, ERROR).
 * @property {string} message - The content of the log message.
 */

/**
 * Buffer storing the latest logs fetched from the backend.
 * @type {LogEntry[]}
 */
let currentLogBuffer = [];

/**
 * ID of the active polling interval, or null if inactive.
 * @type {number|null}
 */
let logUpdateIntervalId = null;

const LOG_POLLING_RATE_MS = 1500;

/**
 * Starts the periodic polling of logs from the backend.
 * Clears any existing interval before starting a new one.
 */
window.startLogPolling = () => {
  if (logUpdateIntervalId) {
    clearInterval(logUpdateIntervalId);
  }
  console.info("[Logs] Starting background polling...");
  // @ts-ignore - setInterval returns a number in browsers
  logUpdateIntervalId = setInterval(window.loadLogs, LOG_POLLING_RATE_MS);
};

/**
 * Stops the log polling process.
 */
window.stopLogPolling = () => {
  if (logUpdateIntervalId) {
    clearInterval(logUpdateIntervalId);
    logUpdateIntervalId = null;
    console.info("[Logs] Polling stopped.");
  }
};

/**
 * Fetches the latest logs from the Python backend.
 * Updates the local buffer and triggers a UI render.
 *
 * @async
 * @returns {Promise<void>}
 */
window.loadLogs = async () => {
  const logContainer = document.getElementById("log-container-terminal");

  // If the UI isn't ready or visible, stop polling to save resources.
  if (!logContainer || !window.isApiReady()) {
    if (logUpdateIntervalId) window.stopLogPolling();
    return;
  }

  try {
    const logsData = await window.pywebview.api.get_logs();
    currentLogBuffer = Array.isArray(logsData) ? logsData : [];
    window.renderFilteredLogs();
  } catch (error) {
    console.error("[Logs] Failed to fetch logs:", error);
    window.stopLogPolling();
  }
};

/**
 * Renders logs into the terminal window based on the current search filter.
 * Maintains scroll position at the bottom if the user was already there.
 */
window.renderFilteredLogs = () => {
  const logDisplayElement = document.getElementById("log-display-terminal");
  const logContainerElement = document.getElementById("log-container-terminal");
  const searchInputElement = document.getElementById("log-search-input");

  if (!logDisplayElement || !logContainerElement || !searchInputElement) return;

  const searchQuery = searchInputElement.value.toLowerCase();

  // Check if user is scrolled to the bottom (allow 20px threshold)
  const isScrolledToBottom =
    logContainerElement.scrollTop >=
    logContainerElement.scrollHeight - logContainerElement.clientHeight - 20;

  // Filter logs based on search query
  const filteredLogs = searchQuery
    ? currentLogBuffer.filter((log) =>
        log.message.toLowerCase().includes(searchQuery)
      )
    : currentLogBuffer;

  // Build HTML string
  let logsHtml = "";
  if (filteredLogs.length > 0) {
    logsHtml = filteredLogs
      .map(
        (log) =>
          `<span class="log-line log-${log.level}">${window.escapeHtml(
            log.message
          )}</span>`
      )
      .join("");
  } else {
    logsHtml = `<span class="log-line log-INFO">No logs to display.</span>`;
  }

  logDisplayElement.innerHTML = logsHtml;

  // Auto-scroll to bottom if the user was already there
  if (isScrolledToBottom) {
    logContainerElement.scrollTop = logContainerElement.scrollHeight;
  }
};

/**
 * Toggles Developer Mode in the backend and updates UI visibility.
 *
 * @param {HTMLInputElement} checkboxElement - The toggle switch element.
 */
window.handleDevModeToggle = (checkboxElement) => {
  const isEnabled = checkboxElement.checked;

  if (window.isApiReady()) {
    window.pywebview.api.set_developer_mode(isEnabled);
  }

  window.updateLogTabVisibility(isEnabled);
};

/**
 * Shows or hides the Logs tab in the sidebar based on Developer Mode state.
 *
 * @param {boolean} isVisible - Whether the logs tab should be visible.
 */
window.updateLogTabVisibility = (isVisible) => {
  const logTabItem = document.getElementById("logs-sidebar-tab");
  const logSection = document.getElementById("logs");

  if (isVisible) {
    logTabItem?.classList.remove("hidden-by-default");
    logSection?.classList.remove("hidden-by-default");
  } else {
    logTabItem?.classList.add("hidden-by-default");
    logSection?.classList.add("hidden-by-default");
  }
};

/**
 * Exports the currently filtered logs to a text file via the backend.
 *
 * @async
 * @returns {Promise<void>}
 */
window.exportLogs = async () => {
  if (!window.isApiReady()) return;

  const searchInputElement = document.getElementById("log-search-input");
  const searchQuery = searchInputElement
    ? searchInputElement.value.toLowerCase()
    : "";

  // Export only what the user currently sees (filtered)
  const logsToExport = (
    searchQuery
      ? currentLogBuffer.filter((log) =>
          log.message.toLowerCase().includes(searchQuery)
        )
      : currentLogBuffer
  ).map((log) => log.message);

  try {
    const response = await window.pywebview.api.export_logs(logsToExport);

    if (response && response.success) {
      console.info("[Logs] Export successful.");
    } else if (response && response.message !== "Cancelled") {
      window.showToast("Log export failed.", "error");
    }
  } catch (error) {
    console.error("[Logs] Export communication error:", error);
    window.showToast("Backend communication error.", "error");
  }
};
