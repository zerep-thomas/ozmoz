/* --- src/static/js/settings/main.js --- */

/**
 * @fileoverview Main entry point for the Settings window logic.
 * Orchestrates initialization, event binding, and navigation handling.
 */

/**
 * Flag to prevent double initialization of the application.
 * @type {boolean}
 */
let isApplicationInitialized = false;

/**
 * Main Initialization Function.
 * Called when the PyWebView API is ready or the DOM is fully loaded.
 *
 * This function performs the following:
 * 1. Attaches global event listeners to DOM elements.
 * 2. Fetches initial data from the backend (Language, Models, Version, Hotkeys).
 * 3. Initializes UI components (Custom Selects, Sidebar, Tabs).
 * 4. Reveals the UI once setup is complete.
 *
 * @async
 * @returns {Promise<void>}
 */
window.initApp = async () => {
  if (isApplicationInitialized) return;
  isApplicationInitialized = true;

  // 1. Attach Event Listeners to DOM elements (Buttons, Inputs, Toggles)
  attachGlobalEventHandlers();

  // Setup infinite scroll for history
  if (window.setupHistoryInfiniteScroll) {
    window.setupHistoryInfiniteScroll();
  }

  // 2. Initialize Data from Backend
  if (window.isApiReady()) {
    try {
      // Language Setup
      const currentLanguage = await window.pywebview.api.get_current_language();
      window.applyTranslations(currentLanguage || "en");

      await window.populateLanguageDropdown();
      window._updateCustomSelectDisplay(
        "custom-language-select-container",
        currentLanguage || "en",
      );

      // Trigger automatic update check
      window.checkForUpdates();

      // Models Setup
      await window.populateAudioModelDropdown();
      await window.populateModelDropdown();

      // Application Version
      window.pywebview.api.get_app_version().then((response) => {
        const versionElement = document.getElementById("version-number");
        if (versionElement) {
          versionElement.textContent = `v${response.version}`;
        }
      });

      // Hotkeys Display
      window.pywebview.api.get_hotkeys().then((hotkeys) => {
        if (window.updateHotkeyDisplay) {
          window.updateHotkeyDisplay(hotkeys);
        }
      });
    } catch (error) {
      console.error("[Main] Initialization failed:", error);
    }
  }

  // 3. Initialize UI Components
  if (window.initCustomSelects) {
    window.initCustomSelects();
  }

  // 4. Attach Sidebar Navigation Logic
  const sidebarItems = document.querySelectorAll(".sidebar-item");
  sidebarItems.forEach((item) => {
    item.addEventListener("click", () => {
      const targetSection = item.getAttribute("data-target");
      if (targetSection) {
        window.setActiveSection(targetSection);
      }
    });
  });

  // 5. Attach Internal Tabs Navigation Logic (General section sub-tabs)
  const internalTabs = document.querySelectorAll(".internal-tab");
  internalTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const parentSection = tab.closest(".settings-section");
      if (!parentSection) return;

      // Update Tab UI State
      parentSection
        .querySelectorAll(".internal-tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      // Switch Content Visibility
      parentSection
        .querySelectorAll(".internal-tab-content")
        .forEach((content) => content.classList.remove("active"));

      const targetContentId = `${tab.dataset.tab}-content`;
      const targetContent = document.getElementById(targetContentId);
      if (targetContent) {
        targetContent.classList.add("active");
      }

      // Trigger Logic Specific to the Tab
      switch (tab.dataset.tab) {
        case "api":
          if (window.loadApiConfiguration) window.loadApiConfiguration();
          break;
        case "preferences":
          if (window.populateModelDropdown) window.populateModelDropdown();
          break;
        case "controls":
          if (window.initializeControlsTab) window.initializeControlsTab();
          break;
      }
    });
  });

  // 6. Attach Toggles Logic
  const historySortToggle = document.getElementById("history-sort-toggle");
  if (historySortToggle) {
    historySortToggle.addEventListener("change", () => {
      if (window.sortAndDisplayTranscripts) {
        window.sortAndDisplayTranscripts();
      }
    });
  }

  const dashboardPeriodToggle = document.getElementById(
    "dashboard-period-toggle",
  );
  if (dashboardPeriodToggle) {
    dashboardPeriodToggle.addEventListener("change", (event) => {
      // @ts-ignore - 'checked' property exists on checkbox input
      const isChecked = event.target.checked;
      const days = isChecked ? 7 : 30;

      if (window.isApiReady()) {
        window.pywebview.api.set_dashboard_period(days);
      }
      if (window.loadActivityChartData) {
        window.loadActivityChartData();
      }
    });
  }

  // 7. Enhance Inputs UX (Enter key moves focus to next logical input)
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
  if (window.setActiveSection) {
    window.setActiveSection("home");
  }
  const mainContainer = document.getElementById("container");
  if (mainContainer) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        mainContainer.classList.add("fade-in");
      });
    });
  }

  // Check Developer Mode Status
  if (window.isApiReady()) {
    window.pywebview.api.get_developer_mode().then((response) => {
      if (response.developer_mode && window.updateLogTabVisibility) {
        window.updateLogTabVisibility(true);
      }
    });
  }
};

/**
 * Attaches all global click and change event listeners for the Settings UI.
 * This function aggregates listeners for API, Agents, History, Logs, Hotkeys, and Updates.
 */
function attachGlobalEventHandlers() {
  // --- API Configuration ---
  document
    .getElementById("save-api-keys-btn")
    ?.addEventListener("click", window.saveApiKeys);

  // --- Replacements ---
  document
    .getElementById("add-replacement-btn")
    ?.addEventListener("click", window.addReplacement);

  // --- Agents Management ---
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

  // --- History Management ---
  document
    .getElementById("clear-history-btn")
    ?.addEventListener("click", window.confirmClearHistory);

  // --- General Modals & Misc ---
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

  // --- Logs & Debugging ---
  document
    .getElementById("refresh-logs-btn")
    ?.addEventListener("click", window.loadLogs);

  document
    .getElementById("export-logs-btn")
    ?.addEventListener("click", window.exportLogs);

  document
    .getElementById("log-search-input")
    ?.addEventListener("input", window.renderFilteredLogs);

  // --- Hotkeys Configuration ---
  document.querySelectorAll(".hotkey-edit-btn").forEach((button) => {
    button.addEventListener("click", (event) =>
      window.openHotkeyModal(event.target),
    );
  });

  document
    .getElementById("hotkey-modal-cancel-btn")
    ?.addEventListener("click", window.cancelHotkeyCapture);

  document
    .getElementById("hotkey-modal-save-btn")
    ?.addEventListener("click", window.saveCapturedHotkey);

  // --- Global Toggles & Selects ---
  const developerModeToggle = document.getElementById("toggle-dev-mode");
  if (developerModeToggle) {
    developerModeToggle.addEventListener("change", (event) =>
      window.handleDevModeToggle(event.target),
    );
  }

  const chartTypeToggle = document.getElementById("toggle-chart-type");
  if (chartTypeToggle) {
    chartTypeToggle.addEventListener("change", (event) => {
      // @ts-ignore
      const isChecked = event.target.checked;
      const type = isChecked ? "line" : "bar";

      if (window.isApiReady()) {
        window.pywebview.api.set_chart_type(type).then((res) => {
          if (res.success) {
            window.loadActivityChartData();
          }
        });
      }
    });
  }

  const modelSelectElement = document.getElementById("model-select");
  if (modelSelectElement) {
    modelSelectElement.addEventListener("change", (event) => {
      // @ts-ignore
      const selectedValue = event.target.value;
      window.pywebview.api.set_model(selectedValue);
    });
  }

  const soundToggle = document.getElementById("toggle-sound");
  if (soundToggle) {
    soundToggle.addEventListener("change", (event) => {
      // @ts-ignore
      const isChecked = event.target.checked;
      window.pywebview.api.set_sound_enabled(isChecked);
    });
  }

  const muteToggle = document.getElementById("toggle-mute");
  if (muteToggle) {
    muteToggle.addEventListener("change", (event) => {
      // @ts-ignore
      const isChecked = event.target.checked;
      window.pywebview.api.mute_sound(isChecked);
    });
  }

  // --- Application Updates ---
  // 1. Sidebar button click -> Open confirmation modal
  const updateSidebarButton = document.getElementById(
    "update-app-sidebar-button",
  );
  if (updateSidebarButton) {
    updateSidebarButton.addEventListener("click", () => {
      const modalBackdrop = document.getElementById(
        "update-confirm-modal-backdrop",
      );
      if (modalBackdrop) {
        modalBackdrop.style.display = "flex";
        setTimeout(() => modalBackdrop.classList.add("visible"), 10);
      }
    });
  }

  // 2. Confirm Update click -> Trigger download logic
  const confirmUpdateStartButton = document.getElementById(
    "update-confirm-start",
  );
  if (confirmUpdateStartButton) {
    confirmUpdateStartButton.addEventListener(
      "click",
      window.handleUpdateConfirmation,
    );
  }

  // 3. View Notes click -> Open Browser to Release Page
  const viewNotesButton = document.getElementById("update-confirm-view-notes");
  if (viewNotesButton) {
    viewNotesButton.addEventListener("click", () => {
      const modalBackdrop = document.getElementById(
        "update-confirm-modal-backdrop",
      );
      if (modalBackdrop) {
        modalBackdrop.classList.remove("visible");
        setTimeout(() => (modalBackdrop.style.display = "none"), 200);
      }
      if (window.isApiReady()) {
        window.pywebview.api.open_external_link(
          "https://github.com/zerep-thomas/ozmoz/releases",
        );
      }
    });
  }
}

// --- Application Bootstrap ---

// Listen for the pywebview ready event to start initialization
window.addEventListener("pywebviewready", window.initApp);

// Fallback timeouts in case the event fails or fires before listener attachment
setTimeout(() => {
  if (!isApplicationInitialized) window.initApp();
}, 300);

setTimeout(() => {
  // @ts-ignore - pywebview global check
  if (!window.pywebview && !isApplicationInitialized) {
    console.warn("[Main] pywebview not detected, attempting fallback init.");
    window.initApp();
  }
}, 600);
