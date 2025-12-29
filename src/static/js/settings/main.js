/* --- src/static/js/settings/main.js --- */

let isAppInitialized = false;

/**
 * Main Initialization Function.
 * Called when the PyWebView API is ready or DOM is loaded.
 */
window.initApp = async () => {
  if (isAppInitialized) return;
  isAppInitialized = true;

  // 1. Attach Event Listeners to DOM elements
  attachGlobalListeners();

  // 2. Initialize Data from Backend
  if (window.isApiReady()) {
    try {
      const lang = await window.pywebview.api.get_current_language();
      window.applyTranslations(lang || "en");

      await window.populateLanguageDropdown();
      window._updateCustomSelectDisplay(
        "custom-language-select-container",
        lang || "en"
      );

      // Trigger automatic update check
      window.checkForUpdates();

      await window.populateAudioModelDropdown();
      await window.populateModelDropdown();

      window.pywebview.api.get_app_version().then((res) => {
        const el = document.getElementById("version-number");
        if (el) el.textContent = `v${res.version}`;
      });

      window.pywebview.api.get_hotkeys().then(window.updateHotkeyDisplay);
    } catch (e) {
      console.error("Init failed", e);
    }
  }

  // 3. Initialize UI Components
  window.initCustomSelects();

  // 4. Attach Sidebar Navigation
  document.querySelectorAll(".sidebar-item").forEach((item) => {
    item.addEventListener("click", () => {
      window.setActiveSection(item.getAttribute("data-target"));
    });
  });

  // 5. Attach Internal Tabs Navigation (General section)
  document.querySelectorAll(".internal-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const parent = tab.closest(".settings-section");
      // UI Update
      parent
        .querySelectorAll(".internal-tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      parent
        .querySelectorAll(".internal-tab-content")
        .forEach((c) => c.classList.remove("active"));
      const content = document.getElementById(`${tab.dataset.tab}-content`);
      if (content) content.classList.add("active");

      // Logic Trigger
      if (tab.dataset.tab === "api") window.loadApiConfiguration();
      if (tab.dataset.tab === "preferences") window.populateModelDropdown();
      if (tab.dataset.tab === "controls") window.initializeControlsTab();
    });
  });

  // 6. Attach Toggles Logic
  const historySortToggle = document.getElementById("history-sort-toggle");
  if (historySortToggle) {
    historySortToggle.addEventListener("change", function () {
      window.sortAndDisplayTranscripts();
    });
  }

  const dashboardPeriodToggle = document.getElementById(
    "dashboard-period-toggle"
  );
  if (dashboardPeriodToggle) {
    dashboardPeriodToggle.addEventListener("change", function () {
      const days = this.checked ? 7 : 30;
      if (window.isApiReady()) {
        window.pywebview.api.set_dashboard_period(days);
      }
      window.loadActivityChartData();
    });
  }

  // 7. Inputs UX (Enter key focus)
  const agentNameInput = document.getElementById("agent-name");
  const agentTriggerInput = document.getElementById("agent-trigger");
  const agentPromptInput = document.getElementById("agent-prompt");
  if (agentNameInput) {
    agentNameInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") agentTriggerInput?.focus();
    });
  }
  if (agentTriggerInput) {
    agentTriggerInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") agentPromptInput?.focus();
    });
  }

  // 8. Final UI Reveal
  window.setActiveSection("home");
  const container = document.getElementById("container");
  if (container) container.classList.add("fade-in");

  if (window.isApiReady()) {
    window.pywebview.api.get_developer_mode().then((res) => {
      if (res.developer_mode) {
        window.updateLogTabVisibility(true);
      }
    });
  }
};

/**
 * Attaches all click events for buttons throughout the Settings UI.
 */
function attachGlobalListeners() {
  // --- API ---
  document
    .getElementById("save-api-keys-btn")
    ?.addEventListener("click", window.saveApiKeys);

  // --- Replacements ---
  document
    .getElementById("add-replacement-btn")
    ?.addEventListener("click", window.addReplacement);

  // --- Agents ---
  document
    .getElementById("create-agent-btn")
    ?.addEventListener("click", () => window.showAgentModal());
  document
    .getElementById("save-agent-btn")
    ?.addEventListener("click", window.saveAgent);
  document
    .getElementById("cancel-agent-modal-btn")
    ?.addEventListener("click", window.hideAgentModal);
  document
    .getElementById("close-agent-modal-btn")
    ?.addEventListener("click", window.hideAgentModal);

  document
    .getElementById("confirm-delete-agent-btn")
    ?.addEventListener("click", window.confirmDeleteAgent);
  document
    .getElementById("cancel-delete-agent-btn")
    ?.addEventListener("click", window.hideDeleteAgentModal);

  // --- History ---
  document
    .getElementById("clear-history-btn")
    ?.addEventListener("click", window.confirmClearHistory);

  // --- Modals & Misc ---
  document
    .getElementById("conflict-modal-ok-btn")
    ?.addEventListener("click", window.hideConflictModal);
  document
    .getElementById("incompatible-model-ok-btn")
    ?.addEventListener("click", window.hideIncompatibleModelModal);
  document
    .getElementById("missing-key-add-btn")
    ?.addEventListener("click", window.hideMissingKeyModalAndGoToApi);
  document
    .getElementById("missing-key-close-btn")
    ?.addEventListener("click", window.hideMissingKeyModal);

  // --- Logs ---
  document
    .getElementById("refresh-logs-btn")
    ?.addEventListener("click", window.loadLogs);
  document
    .getElementById("export-logs-btn")
    ?.addEventListener("click", window.exportLogs);
  document
    .getElementById("log-search-input")
    ?.addEventListener("input", window.renderFilteredLogs);

  // --- Hotkeys ---
  document.querySelectorAll(".hotkey-edit-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => window.openHotkeyModal(e.target));
  });
  document
    .getElementById("hotkey-modal-cancel-btn")
    ?.addEventListener("click", window.cancelHotkeyCapture);
  document
    .getElementById("hotkey-modal-save-btn")
    ?.addEventListener("click", window.saveCapturedHotkey);

  // --- Toggles ---
  const devModeToggle = document.getElementById("toggle-dev-mode");
  if (devModeToggle)
    devModeToggle.addEventListener("change", (e) =>
      window.handleDevModeToggle(e.target)
    );

  const modelSelect = document.getElementById("model-select");
  if (modelSelect)
    modelSelect.addEventListener("change", (e) =>
      window.pywebview.api.set_model(e.target.value)
    );

  const soundToggle = document.getElementById("toggle-sound");
  if (soundToggle)
    soundToggle.addEventListener("change", (e) =>
      window.pywebview.api.set_sound_enabled(e.target.checked)
    );

  const muteToggle = document.getElementById("toggle-mute");
  if (muteToggle)
    muteToggle.addEventListener("change", (e) =>
      window.pywebview.api.mute_sound(e.target.checked)
    );

  // --- Updates ---
  // 1. Sidebar button click -> Open modal
  const sidebarUpdateBtn = document.getElementById("update-app-sidebar-button");
  if (sidebarUpdateBtn) {
    sidebarUpdateBtn.addEventListener("click", () => {
      const modal = document.getElementById("update-confirm-modal-backdrop");
      if (modal) {
        modal.style.display = "flex";
        setTimeout(() => modal.classList.add("visible"), 10);
      }
    });
  }

  // 2. Confirm Update click -> Start download
  const confirmUpdateBtn = document.getElementById("update-confirm-start");
  if (confirmUpdateBtn) {
    confirmUpdateBtn.addEventListener("click", window.handleUpdateConfirmation);
  }

  // 3. View Notes click -> Open Browser
  const viewNotesBtn = document.getElementById("update-confirm-view-notes");
  if (viewNotesBtn) {
    viewNotesBtn.addEventListener("click", () => {
      const modal = document.getElementById("update-confirm-modal-backdrop");
      if (modal) {
        modal.classList.remove("visible");
        setTimeout(() => (modal.style.display = "none"), 200);
      }
      if (window.isApiReady())
        window.pywebview.api.open_external_link(
          "https://github.com/zerep-thomas/ozmoz/releases"
        );
    });
  }
}

// Bootstrapping the application
window.addEventListener("pywebviewready", window.initApp);
setTimeout(() => {
  if (!isAppInitialized) window.initApp();
}, 300);
setTimeout(() => {
  if (!window.pywebview) window.initApp();
}, 300);
