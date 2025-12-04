/* --- static/js/settings/main.js --- */

// --- Hotkey Logic ---
let capturedHotkey = null;
let isCapturingHotkey = false;

window.openHotkeyModal = (buttonElement) => {
  const action = buttonElement.getAttribute("data-action");
  const modal = document.getElementById("hotkey-modal-backdrop");
  const titleDisplay = document.getElementById("hotkey-action-name-display");
  const captureDisplay = document.getElementById("captured-hotkey-display");
  const saveButton = document.getElementById("hotkey-modal-save-btn");
  const actionNameInput = document.getElementById("hotkey-modal-action-name");

  if (!modal) return;

  if (window.isApiReady()) {
    window.pywebview.api.temporarily_disable_all_hotkeys();
  }

  titleDisplay.textContent = "";
  actionNameInput.value = action;
  capturedHotkey = null;
  isCapturingHotkey = true;

  captureDisplay.textContent = window.t("modal_waiting_input");
  captureDisplay.classList.add("placeholder");
  saveButton.disabled = true;

  modal.style.display = "flex";
  setTimeout(() => modal.classList.add("visible"), 10);

  document.addEventListener("keydown", window.handleHotkeyCapture);
};

window.handleHotkeyCapture = (event) => {
  if (!isCapturingHotkey) return;
  event.preventDefault();
  if (event.key === "Escape") {
    window.cancelHotkeyCapture();
    return;
  }

  const parts = [];
  if (event.ctrlKey) parts.push("ctrl");
  if (event.altKey) parts.push("alt");
  if (event.shiftKey) parts.push("shift");

  let keyName = event.key.toLowerCase();
  if (keyName === " ") keyName = "space";
  if (
    !["control", "alt", "shift", "meta"].includes(keyName) &&
    !parts.includes(keyName)
  ) {
    parts.push(keyName);
  }

  if (parts.length > 0) {
    capturedHotkey = parts.join("+");
    document.getElementById("captured-hotkey-display").textContent =
      capturedHotkey;
    document.getElementById("hotkey-modal-save-btn").disabled = false;
  }
};

window.saveCapturedHotkey = () => {
  const action = document.getElementById("hotkey-modal-action-name").value;
  if (!capturedHotkey || !action) return;

  document.removeEventListener("keydown", window.handleHotkeyCapture);
  isCapturingHotkey = false;

  if (window.isApiReady()) {
    window.pywebview.api.set_hotkey(action, capturedHotkey).then((res) => {
      if (res.success) {
        window.updateHotkeyDisplay(res.new_hotkeys);
        window.cancelHotkeyCapture();
      } else {
        alert("Error saving hotkey");
      }
    });
  }
};

window.cancelHotkeyCapture = () => {
  document.removeEventListener("keydown", window.handleHotkeyCapture);
  isCapturingHotkey = false;
  const modal = document.getElementById("hotkey-modal-backdrop");
  if (modal) {
    modal.classList.remove("visible");
    setTimeout(() => (modal.style.display = "none"), 200);
  }
  if (window.isApiReady()) window.pywebview.api.restore_all_hotkeys();
};

window.updateHotkeyDisplay = (hotkeys) => {
  if (!hotkeys) return;
  for (const [key, value] of Object.entries(hotkeys)) {
    const el = document.getElementById(`hotkey-display-${key}`);
    if (el) el.textContent = value;
  }
};

window.initializeControlsTab = () => {
  console.log("Initializing Controls Tab");
  if (!window.isApiReady()) {
    document.getElementById("hotkey-display-toggle_visibility").textContent =
      "Error";
    return;
  }
  window.pywebview.api.get_hotkeys().then((hotkeys) => {
    if (hotkeys) {
      window.updateHotkeyDisplay(hotkeys);
    }
  });
};

// --- Navigation Logic ---
window.setActiveSection = async (sectionId) => {
  document
    .querySelectorAll(".settings-section")
    .forEach((section) => section.classList.remove("active"));
  document
    .querySelectorAll(".sidebar-item")
    .forEach((item) => item.classList.remove("active"));

  const sectionElement = document.getElementById(sectionId);
  const sidebarItem = document.querySelector(
    `.sidebar-item[data-target="${sectionId}"]`
  );

  if (sectionElement) sectionElement.classList.add("active");
  if (sidebarItem) sidebarItem.classList.add("active");

  if (sectionId === "logs") {
    window.loadLogs();
    window.startLogPolling();
  } else {
    window.stopLogPolling();
  }

  if (sectionId === "history") window.loadTranscripts();
  if (sectionId === "replacement") {
    window.loadReplacements();
    window.setupReplacementFilterListener();
  }
  if (sectionId === "agent") {
    window.loadAgents();
    window.setupAgentFilterListener();
  }
  if (sectionId === "home") {
    window.loadDashboardStats();
    window.loadActivityChartData();
  }
  if (sectionId === "general") {
    const activeTab = document.querySelector("#general .internal-tab.active");
    const tabName = activeTab ? activeTab.dataset.tab : "preferences";

    if (tabName === "api") window.loadApiConfiguration();
    if (tabName === "preferences") {
      await window.populateLanguageDropdown();
      await window.populateAudioModelDropdown();
      window.populateModelDropdown();
    }
    if (tabName === "controls") {
      window.initializeControlsTab();
    }
  }
};

// --- Modal Helpers ---

window.showIncompatibleModelModal = (reason) => {
  const backdrop = document.getElementById("incompatible-model-modal-backdrop");
  const textElement = document.getElementById("incompatible-model-modal-text");
  if (!backdrop || !textElement) return;
  if (reason === "web") {
    textElement.textContent = window.t("model_incompatible_web");
  } else if (reason === "vision") {
    textElement.textContent = window.t("model_incompatible_vision");
  } else {
    textElement.textContent = window.t("model_incompatible_generic");
  }
  backdrop.style.display = "flex";
  setTimeout(() => backdrop.classList.add("visible"), 10);
};

window.hideIncompatibleModelModal = () => {
  document
    .getElementById("incompatible-model-modal-backdrop")
    ?.classList.remove("visible");
  setTimeout(() => {
    const el = document.getElementById("incompatible-model-modal-backdrop");
    if (el) el.style.display = "none";
  }, 200);
};

window.showMissingKeyModal = (provider) => {
  const backdrop = document.getElementById("missing-key-modal-backdrop");
  const text = document.getElementById("missing-key-modal-text");
  if (text) {
    const msg = window.t("missing_api_key_msg").replace("{provider}", provider);
    text.innerHTML = msg;
  }
  if (backdrop) {
    backdrop.style.display = "flex";
    setTimeout(() => backdrop.classList.add("visible"), 10);
  }
};

window.hideMissingKeyModal = () => {
  const el = document.getElementById("missing-key-modal-backdrop");
  el?.classList.remove("visible");
  setTimeout(() => {
    if (el) el.style.display = "none";
  }, 200);
};

window.hideMissingKeyModalAndGoToApi = () => {
  window.hideMissingKeyModal();
  document.querySelector('.internal-tab[data-tab="api"]')?.click();
};

// --- Initialization ---

window.initApp = async () => {
  // Attach Global Listeners (Replaces Inline onclicks)
  attachGlobalListeners();

  if (window.isApiReady()) {
    try {
      const lang = await window.pywebview.api.get_current_language();
      window.applyTranslations(lang || "en");

      await window.populateLanguageDropdown();
      window._updateCustomSelectDisplay(
        "custom-language-select-container",
        lang || "en"
      );

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

  window.initCustomSelects();

  // Sidebar Listeners
  document.querySelectorAll(".sidebar-item").forEach((item) => {
    item.addEventListener("click", () => {
      window.setActiveSection(item.getAttribute("data-target"));
    });
  });

  // Tab Listeners
  document.querySelectorAll(".internal-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const parent = tab.closest(".settings-section");
      parent
        .querySelectorAll(".internal-tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      parent
        .querySelectorAll(".internal-tab-content")
        .forEach((c) => c.classList.remove("active"));

      const content = document.getElementById(`${tab.dataset.tab}-content`);
      if (content) content.classList.add("active");

      if (tab.dataset.tab === "api") window.loadApiConfiguration();
      if (tab.dataset.tab === "preferences") window.populateModelDropdown();
      if (tab.dataset.tab === "controls") window.initializeControlsTab();
    });
  });

  // Toggles and Inputs
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

function attachGlobalListeners() {
  // API
  document
    .getElementById("save-api-keys-btn")
    ?.addEventListener("click", window.saveApiKeys);

  // Replacements
  document
    .getElementById("add-replacement-btn")
    ?.addEventListener("click", window.addReplacement);

  // Agents
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

  // History
  document
    .getElementById("clear-history-btn")
    ?.addEventListener("click", window.confirmClearHistory);

  // Modals & Misc
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

  // Logs
  document
    .getElementById("refresh-logs-btn")
    ?.addEventListener("click", window.loadLogs);
  document
    .getElementById("export-logs-btn")
    ?.addEventListener("click", window.exportLogs);
  document
    .getElementById("log-search-input")
    ?.addEventListener("input", window.renderFilteredLogs);

  // Hotkeys
  document.querySelectorAll(".hotkey-edit-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => window.openHotkeyModal(e.target));
  });
  document
    .getElementById("hotkey-modal-cancel-btn")
    ?.addEventListener("click", window.cancelHotkeyCapture);
  document
    .getElementById("hotkey-modal-save-btn")
    ?.addEventListener("click", window.saveCapturedHotkey);

  // Toggles
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
}

window.addEventListener("pywebviewready", window.initApp);
setTimeout(() => {
  if (!window.pywebview) window.initApp();
}, 300);
