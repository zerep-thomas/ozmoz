/* --- static/js/settings/logs.js --- */

let cachedLogs = [];
let logPollingInterval = null;

window.startLogPolling = () => {
  if (logPollingInterval) clearInterval(logPollingInterval);
  console.log("Starting log polling...");
  logPollingInterval = setInterval(window.loadLogs, 1500);
};

window.stopLogPolling = () => {
  if (logPollingInterval) {
    clearInterval(logPollingInterval);
    logPollingInterval = null;
  }
};

window.loadLogs = async () => {
  const logContainer = document.getElementById("log-container-terminal");
  if (!logContainer || !window.isApiReady()) {
    if (logPollingInterval) window.stopLogPolling();
    return;
  }
  try {
    const logsData = await window.pywebview.api.get_logs();
    cachedLogs = Array.isArray(logsData) ? logsData : [];
    window.renderFilteredLogs();
  } catch (error) {
    console.error("Error loading logs:", error);
    window.stopLogPolling();
  }
};

window.renderFilteredLogs = () => {
  const logDisplay = document.getElementById("log-display-terminal");
  const logContainer = document.getElementById("log-container-terminal");
  const searchInput = document.getElementById("log-search-input");

  if (!logDisplay || !logContainer || !searchInput) return;

  const query = searchInput.value.toLowerCase();
  const isNearBottom =
    logContainer.scrollTop >=
    logContainer.scrollHeight - logContainer.clientHeight - 20;

  let htmlContent = "";
  const filteredLogs = query
    ? cachedLogs.filter((log) => log.message.toLowerCase().includes(query))
    : cachedLogs;

  if (filteredLogs.length > 0) {
    filteredLogs.forEach((log) => {
      htmlContent += `<span class="log-line log-${
        log.level
      }">${window.escapeHtml(log.message)}</span>`;
    });
  } else {
    htmlContent = `<span class="log-line log-INFO">No logs to display.</span>`;
  }

  logDisplay.innerHTML = htmlContent;
  if (isNearBottom) {
    logContainer.scrollTop = logContainer.scrollHeight;
  }
};

window.handleDevModeToggle = (checkbox) => {
  const isEnabled = checkbox.checked;
  if (window.isApiReady()) {
    window.pywebview.api.set_developer_mode(isEnabled);
  }
  window.updateLogTabVisibility(isEnabled);
};

window.updateLogTabVisibility = (isVisible) => {
  const logTab = document.getElementById("logs-sidebar-tab");
  const logSection = document.getElementById("logs");
  if (isVisible) {
    logTab?.classList.remove("hidden-by-default");
    logSection?.classList.remove("hidden-by-default");
  } else {
    logTab?.classList.add("hidden-by-default");
    logSection?.classList.add("hidden-by-default");
  }
};

window.exportLogs = async () => {
  if (!window.isApiReady()) return;

  const searchInput = document.getElementById("log-search-input");
  const query = searchInput.value.toLowerCase();

  const logsToExport = (
    query
      ? cachedLogs.filter((log) => log.message.toLowerCase().includes(query))
      : cachedLogs
  ).map((log) => log.message);

  try {
    const response = await window.pywebview.api.export_logs(logsToExport);

    if (response && response.success) {
      console.log("Export réussi");
    } else if (response && response.message !== "Cancelled") {
      window.showToast("Échec de l'export.", "error");
    }
  } catch (error) {
    console.error(error);
    window.showToast("Erreur de communication.", "error");
  }
};
