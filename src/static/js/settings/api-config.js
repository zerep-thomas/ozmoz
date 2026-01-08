/* --- src/static/js/settings/api-config.js --- */

/**
 * @typedef {Object} ApiState
 * @description Stores the initial values of API keys to detect changes.
 * @property {string} [api-key-groq-audio]
 * @property {string} [api-key-deepgram]
 * @property {string} [api-key-groq-ai]
 * @property {string} [api-key-cerebras]
 */

/**
 * @typedef {Object} ModelData
 * @property {string} id - The model identifier.
 * @property {string} name - Display name.
 * @property {string} provider - 'groq', 'cerebras', 'deepgram', or 'local'.
 * @property {string} [advantage] - Short description/badge text.
 * @property {boolean} is_multimodal - Whether the model supports vision.
 * @property {boolean} is_web_model - Whether the model supports tools/web search.
 */

/**
 * @typedef {Object} KeyStatus
 * @property {boolean} groq_audio
 * @property {boolean} deepgram
 * @property {boolean} groq_ai
 * @property {boolean} cerebras
 */

// --- Constants & State ---

const DOM_IDS = {
  MODAL: {
    LOCAL_BACKDROP: "local-model-modal-backdrop",
    LOCAL_CANCEL_BTN: "local-model-cancel-btn",
    LOCAL_DOWNLOAD_BTN: "local-model-download-btn",
    LOCAL_PROGRESS: "local-download-progress",
  },
  DROPDOWNS: {
    AUDIO: "audio-model-select",
    AUDIO_ITEMS: "audio-model-select-items",
    AUDIO_SELECTED: "audio-model-select-selected",
    LANGUAGE: "language-select",
    LANGUAGE_ITEMS: "language-select-items",
    LANGUAGE_SELECTED: "language-select-selected",
    AUTODETECT_OPTION: "autodetect-language-option",
  },
  API: {
    INPUT_CLASS: "api-input",
    ACTIONS_CONTAINER: ".api-actions",
    SAVE_BTN: "save-api-keys-btn",
  },
};

/** @type {ApiState} */
let initialApiState = {};

/** @type {boolean} */
window.hasInitializedLocalListeners = false;

// --- Helper Functions ---

/**
 * Updates the visual display of a custom select dropdown to match the native select's value.
 * Used when setting values programmatically.
 *
 * @param {string} containerId - The ID of the wrapper div for the custom select.
 * @param {string} newValue - The value to select.
 */
window._updateCustomSelectDisplay = (containerId, newValue) => {
  const container = document.getElementById(containerId);
  if (!container) return;

  const nativeSelectElement = container.querySelector("select");
  const selectedDisplayElement = container.querySelector(".select-selected");
  const optionsContainer = container.querySelector(".select-items");

  if (!nativeSelectElement || !selectedDisplayElement || !optionsContainer)
    return;

  nativeSelectElement.value = newValue;

  const itemToSelect = optionsContainer.querySelector(
    `div[data-value="${newValue}"]`
  );

  if (itemToSelect) {
    selectedDisplayElement.textContent = "";
    const contentDiv = document.createElement("div");
    contentDiv.className = "select-selected-content";
    contentDiv.innerHTML = itemToSelect.innerHTML;
    selectedDisplayElement.appendChild(contentDiv);

    Array.from(optionsContainer.children).forEach((child) =>
      child.classList.remove("same-as-selected")
    );
    itemToSelect.classList.add("same-as-selected");
  }
};

/**
 * Initializes event listeners for the Local Model download modal.
 * Uses cloneNode to ensure listeners are not attached multiple times.
 */
window.initLocalModelListeners = () => {
  const backdrop = document.getElementById(DOM_IDS.MODAL.LOCAL_BACKDROP);
  const cancelBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_CANCEL_BTN);
  const downloadBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_DOWNLOAD_BTN);

  if (cancelBtn) {
    // Clone to strip existing listeners
    const newCancelBtn = cancelBtn.cloneNode(true);
    cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

    newCancelBtn.addEventListener("click", () => {
      if (backdrop) {
        backdrop.style.display = "none";
        backdrop.classList.remove("visible");
      }
    });
  }

  if (downloadBtn) {
    const newDownloadBtn = downloadBtn.cloneNode(true);
    downloadBtn.parentNode.replaceChild(newDownloadBtn, downloadBtn);

    newDownloadBtn.addEventListener("click", () => {
      const progressEl = document.getElementById(DOM_IDS.MODAL.LOCAL_PROGRESS);
      const currentBtn = document.getElementById(
        DOM_IDS.MODAL.LOCAL_DOWNLOAD_BTN
      );
      const currentCancel = document.getElementById(
        DOM_IDS.MODAL.LOCAL_CANCEL_BTN
      );

      if (currentBtn) currentBtn.style.display = "none";
      if (currentCancel) currentCancel.style.display = "none";
      if (progressEl) progressEl.style.display = "block";

      // Trigger backend process
      window.pywebview.api.install_local_model();
    });
  }
};

/**
 * Callback exposed to the Python backend.
 * Triggered when the local model download finishes.
 *
 * @param {string} status - 'success' or 'error'.
 */
window.onLocalModelInstallFinished = (status) => {
  const backdrop = document.getElementById(DOM_IDS.MODAL.LOCAL_BACKDROP);
  const downloadBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_DOWNLOAD_BTN);
  const cancelBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_CANCEL_BTN);
  const progressEl = document.getElementById(DOM_IDS.MODAL.LOCAL_PROGRESS);

  if (backdrop) {
    backdrop.style.display = "none";
    backdrop.classList.remove("visible");
  }

  // Reset modal state after a delay
  setTimeout(() => {
    if (downloadBtn) downloadBtn.style.display = "block";
    if (cancelBtn) cancelBtn.style.display = "block";
    if (progressEl) progressEl.style.display = "none";
  }, 500);

  if (status === "success") {
    const audioSelect = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
    if (audioSelect) {
      const localModelId = "local-whisper-large-v3-turbo";
      audioSelect.value = localModelId;
      window.pywebview.api.set_audio_model(localModelId);
      window.populateAudioModelDropdown();
    }
  } else {
    window.showToast("Download failed. Check logs.", "error");
  }
};

/**
 * Fetches available languages and populates the custom dropdown.
 * @returns {Promise<void>}
 */
window.populateLanguageDropdown = async () => {
  const nativeSelectElement = document.getElementById(
    DOM_IDS.DROPDOWNS.LANGUAGE
  );
  const optionsContainer = document.getElementById(
    DOM_IDS.DROPDOWNS.LANGUAGE_ITEMS
  );

  if (!nativeSelectElement || !optionsContainer) return;

  optionsContainer.innerHTML = "";
  nativeSelectElement.innerHTML = "";

  const languages = window.LANGUAGES_DATA || [];

  languages.forEach((lang) => {
    const translatedName = window.t(lang.key);

    // Create native <option>
    const optionElement = document.createElement("option");
    optionElement.value = lang.value;
    optionElement.id = `${lang.value}-language-option`;
    optionElement.textContent = translatedName;
    nativeSelectElement.appendChild(optionElement);

    // Create custom UI item
    const itemDiv = document.createElement("div");
    const nameSpan = document.createElement("span");
    nameSpan.className = "model-name-display";
    nameSpan.textContent = translatedName;

    itemDiv.appendChild(nameSpan);

    if (lang.flag) {
      const flagSpan = document.createElement("span");
      flagSpan.innerHTML = ` ${lang.flag}`;
      nameSpan.appendChild(flagSpan);
    }

    itemDiv.dataset.value = lang.value;

    // Attach click listener for custom item
    itemDiv.addEventListener("click", function (event) {
      event.stopPropagation();
      nativeSelectElement.value = this.dataset.value;

      optionsContainer.classList.add("select-hide");
      const selectedDisplay = document.getElementById(
        DOM_IDS.DROPDOWNS.LANGUAGE_SELECTED
      );

      if (selectedDisplay) {
        selectedDisplay.classList.remove("select-arrow-active");
        selectedDisplay.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        selectedDisplay.appendChild(contentDiv);
      }

      Array.from(optionsContainer.children).forEach((child) =>
        child.classList.remove("same-as-selected")
      );
      this.classList.add("same-as-selected");

      // Trigger change event manually
      nativeSelectElement.dispatchEvent(new Event("change"));
    });

    optionsContainer.appendChild(itemDiv);
  });

  try {
    const currentLang = await window.pywebview.api.get_current_language();
    window._updateCustomSelectDisplay(
      "custom-language-select-container",
      currentLang || "en"
    );
  } catch (e) {
    console.error("Erreur lors de la synchro initiale de la langue:", e);
  }

  // Re-attach change listener to native select (clean way)
  const newSelect = nativeSelectElement.cloneNode(true);
  nativeSelectElement.parentNode.replaceChild(newSelect, nativeSelectElement);
  newSelect.addEventListener("change", handleLanguageChange);
};

/**
 * Handles logic when the language changes (UI update + Backend sync).
 * @param {Event} event - The change event from the select element.
 */
async function handleLanguageChange(event) {
  const newLanguage = event.target.value;
  window.applyTranslations(newLanguage);

  // Re-render custom dropdown items to reflect new translations
  const optionsContainer = document.getElementById(
    DOM_IDS.DROPDOWNS.LANGUAGE_ITEMS
  );
  if (optionsContainer) {
    optionsContainer.innerHTML = "";
    window.LANGUAGES_DATA.forEach((lang) => {
      const translatedName = window.t(lang.key);
      const itemDiv = document.createElement("div");
      const nameSpan = document.createElement("span");
      nameSpan.className = "model-name-display";
      nameSpan.textContent = translatedName;
      itemDiv.appendChild(nameSpan);

      if (lang.flag) {
        const flagSpan = document.createElement("span");
        flagSpan.innerHTML = ` ${lang.flag}`;
        nameSpan.appendChild(flagSpan);
      }

      itemDiv.dataset.value = lang.value;

      if (lang.value === newLanguage) {
        itemDiv.classList.add("same-as-selected");
        const selectedDisplay = document.getElementById(
          DOM_IDS.DROPDOWNS.LANGUAGE_SELECTED
        );
        if (selectedDisplay) {
          selectedDisplay.textContent = "";
          const contentDiv = document.createElement("div");
          contentDiv.className = "select-selected-content";
          contentDiv.innerHTML = itemDiv.innerHTML;
          selectedDisplay.appendChild(contentDiv);
        }
      }

      itemDiv.addEventListener("click", function (e) {
        e.stopPropagation();
        const nativeSelect = document.getElementById(
          DOM_IDS.DROPDOWNS.LANGUAGE
        );
        nativeSelect.value = this.dataset.value;

        const container = document.getElementById(
          DOM_IDS.DROPDOWNS.LANGUAGE_ITEMS
        );
        const display = document.getElementById(
          DOM_IDS.DROPDOWNS.LANGUAGE_SELECTED
        );
        if (container) container.classList.add("select-hide");
        if (display) display.classList.remove("select-arrow-active");

        nativeSelect.dispatchEvent(new Event("change"));
      });
      optionsContainer.appendChild(itemDiv);
    });
  }

  // Sync with Backend
  try {
    if (!window.isApiReady()) return;

    const response = await window.pywebview.api.set_language(newLanguage);
    const currentAudioModel = document.getElementById(
      DOM_IDS.DROPDOWNS.AUDIO
    ).value;

    // Check if backend downgraded the model (e.g. Nova-3 not supported in this lang)
    if (response.final_audio_model !== currentAudioModel) {
      window.showToast(
        `Mode switched to ${response.final_audio_model} (Compatibility).`,
        "info"
      );
    }

    await window.populateAudioModelDropdown();
    await handleAudioModelChange();

    // Refresh data dependent on language
    window.loadActivityChartData();
    window.loadDashboardStats();
    window.populateModelDropdown();
  } catch (error) {
    console.error("Language switch error:", error);
  }
}

/**
 * Shows or hides the "Auto Detect" option depending on whether the selected model supports it.
 * Whisper models support auto-detect; others might not.
 */
async function handleAudioModelChange() {
  const audioModelSelect = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
  const autodetectOption = document.getElementById(
    DOM_IDS.DROPDOWNS.AUTODETECT_OPTION
  );

  if (!audioModelSelect) return;

  const selectedAudioModel = audioModelSelect.value;
  const isWhisperBased =
    selectedAudioModel &&
    (selectedAudioModel.startsWith("whisper") ||
      selectedAudioModel === "local-whisper-large-v3-turbo");

  if (autodetectOption) {
    autodetectOption.style.display = isWhisperBased ? "block" : "none";
  }
}

/**
 * Fetches available audio models and populates the dropdown.
 * Handles local model installation status and API key locking.
 * @returns {Promise<void>}
 */
window.populateAudioModelDropdown = async () => {
  const nativeSelectElement = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
  const selectedDisplayElement = document.getElementById(
    DOM_IDS.DROPDOWNS.AUDIO_SELECTED
  );
  const optionsContainer = document.getElementById(
    DOM_IDS.DROPDOWNS.AUDIO_ITEMS
  );

  if (!nativeSelectElement) return;

  // Ensure listeners for local model are attached once
  if (!window.hasInitializedLocalListeners) {
    window.initLocalModelListeners();
    window.hasInitializedLocalListeners = true;
  }

  // Prevent concurrent loading
  if (nativeSelectElement.dataset.loading === "true") return;
  nativeSelectElement.dataset.loading = "true";

  optionsContainer.innerHTML = "";
  nativeSelectElement.innerHTML = "";

  try {
    const [audioModels, keyStatus, localStatus] = await Promise.all([
      window.pywebview.api.get_translated_audio_models(),
      window.pywebview.api.get_providers_status(),
      window.pywebview.api.get_local_model_status(),
    ]);

    const currentAudioModel =
      await window.pywebview.api.get_current_audio_model();
    const currentLangState = window.getCurrentLanguage() || "en";
    const languageToCheck =
      currentLangState === "autodetect" ? "en" : currentLangState;
    const supportedNova3Langs = window.NOVA3_SUPPORTED_LANGUAGES || ["en"];

    audioModels.forEach((model) => {
      // Filter out Nova-3 if language is unsupported
      if (model.name === "nova-3") {
        const langBase = languageToCheck.split("-")[0].toLowerCase();
        const isSupported =
          supportedNova3Langs.includes(languageToCheck) ||
          supportedNova3Langs.includes(langBase);
        if (!isSupported) return;
      }

      const isLocal = model.provider === "local";
      const isLocalInstalled = localStatus.installed;
      const isDownloading = localStatus.loading;

      let isLocked = false;
      if (model.provider === "groq" && !keyStatus.groq_audio) isLocked = true;
      if (model.provider === "deepgram" && !keyStatus.deepgram) isLocked = true;

      // Native Option
      const nativeOption = document.createElement("option");
      nativeOption.value = model.name;
      nativeOption.textContent = model.name;
      if (isLocked) nativeOption.disabled = true;
      nativeSelectElement.appendChild(nativeOption);

      // Custom Option
      const itemDiv = document.createElement("div");
      const nameSpan = document.createElement("span");
      nameSpan.className = "model-name-display";
      nameSpan.textContent = model.name;

      const badgeSpan = document.createElement("span");
      badgeSpan.className = "model-feature-badge";

      if (isLocal) {
        if (isDownloading) {
          badgeSpan.textContent = window.t("badge_downloading");
          badgeSpan.style.backgroundColor = "var(--color-accent)";
        } else if (isLocalInstalled) {
          badgeSpan.textContent = window.t("badge_ready_local");
          badgeSpan.style.backgroundColor = "var(--color-accent)";
        } else {
          badgeSpan.textContent = window.t("badge_need_download");
          badgeSpan.style.backgroundColor = "var(--color-text-tertiary)";
        }
      } else {
        badgeSpan.textContent = model.advantage || window.t("badge_standard");
      }

      if (isLocked) itemDiv.classList.add("option-disabled", "locked-by-key");

      itemDiv.appendChild(nameSpan);
      itemDiv.appendChild(badgeSpan);

      itemDiv.dataset.value = model.name;
      itemDiv.dataset.provider = model.provider;

      // Event Listener for Item Selection
      itemDiv.addEventListener("click", function (event) {
        event.stopPropagation();

        // Handle Local Model Download Logic
        if (isLocal && !isLocalInstalled && !isDownloading) {
          const modal = document.getElementById(DOM_IDS.MODAL.LOCAL_BACKDROP);
          if (modal) {
            modal.style.display = "flex";
            setTimeout(() => modal.classList.add("visible"), 10);
          }
          return;
        }
        if (isLocal && isDownloading) {
          window.showToast(window.t("badge_downloading"), "info");
          return;
        }

        // Handle Missing Keys
        if (this.classList.contains("locked-by-key")) {
          window.showMissingKeyModal(this.dataset.provider);
          return;
        }

        const modelValue = this.dataset.value;
        nativeSelectElement.value = modelValue;
        window.pywebview.api.set_audio_model(modelValue);

        selectedDisplayElement.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        selectedDisplayElement.appendChild(contentDiv);

        optionsContainer.classList.add("select-hide");
        selectedDisplayElement.classList.remove("select-arrow-active");
        Array.from(optionsContainer.children).forEach((child) =>
          child.classList.remove("same-as-selected")
        );
        this.classList.add("same-as-selected");

        if (typeof handleAudioModelChange === "function") {
          handleAudioModelChange();
        }
      });
      optionsContainer.appendChild(itemDiv);
    });

    // Set initial selection
    if (currentAudioModel) {
      const exists = Array.from(nativeSelectElement.options).some(
        (opt) => opt.value === currentAudioModel && !opt.disabled
      );

      if (exists) {
        nativeSelectElement.value = currentAudioModel;
      } else if (nativeSelectElement.options.length > 0) {
        // Fallback to first available
        for (let i = 0; i < nativeSelectElement.options.length; i++) {
          if (!nativeSelectElement.options[i].disabled) {
            nativeSelectElement.value = nativeSelectElement.options[i].value;
            window.pywebview.api.set_audio_model(nativeSelectElement.value);
            break;
          }
        }
      }
      window._updateCustomSelectDisplay(
        "custom-audio-model-select-container",
        nativeSelectElement.value
      );
    }
  } catch (error) {
    console.error("Error populating Audio Dropdown:", error);
  } finally {
    nativeSelectElement.dataset.loading = "false";
  }
};

/**
 * Fetches available text AI models and populates the dropdown.
 * Handles locking based on missing keys and capability filtering.
 *
 * @param {string} [selectElementId="model-select"] - ID of the select element.
 * @param {string|null} [valueToPreselect=null] - Optional value to force selection.
 * @returns {Promise<void>}
 */
window.populateModelDropdown = async (
  selectElementId = "model-select",
  valueToPreselect = null
) => {
  const containerName =
    selectElementId === "model-select"
      ? "custom-model-select-container"
      : "custom-agent-model-select-container";

  const nativeSelectElement = document.getElementById(selectElementId);
  const selectedDisplayElement = document.getElementById(
    `${selectElementId}-selected`
  );
  const optionsContainer = document.getElementById(`${selectElementId}-items`);

  if (!nativeSelectElement || nativeSelectElement.dataset.loading === "true")
    return;

  nativeSelectElement.dataset.loading = "true";
  selectedDisplayElement.textContent = window.t("loading");
  optionsContainer.innerHTML = "";
  nativeSelectElement.innerHTML = "";

  try {
    const [models, keyStatus] = await Promise.all([
      window.pywebview.api.get_filtered_text_models(),
      window.pywebview.api.get_providers_status(),
    ]);

    if (!models || models.length === 0) {
      selectedDisplayElement.textContent = window.t("no_models");
      return;
    }

    const currentGeneralModel = await window.pywebview.api.get_current_model();

    models.forEach((model) => {
      let isLocked = false;
      if (model.provider === "groq" && !keyStatus.groq_ai) isLocked = true;
      if (model.provider === "cerebras" && !keyStatus.cerebras) isLocked = true;

      // Native Option
      const nativeOption = document.createElement("option");
      nativeOption.value = model.id;
      nativeOption.textContent = model.name;
      if (isLocked) nativeOption.disabled = true;
      nativeSelectElement.appendChild(nativeOption);

      // Custom Option
      const itemDiv = document.createElement("div");
      const nameSpan = document.createElement("span");
      nameSpan.className = "model-name-display";
      nameSpan.textContent = model.name;

      const badgeSpan = document.createElement("span");
      badgeSpan.className = "model-feature-badge";
      badgeSpan.textContent = model.advantage || "General";

      if (isLocked) itemDiv.classList.add("option-disabled", "locked-by-key");

      itemDiv.appendChild(nameSpan);
      itemDiv.appendChild(badgeSpan);

      itemDiv.dataset.value = model.id;
      itemDiv.dataset.multimodal = String(model.is_multimodal);
      itemDiv.dataset.web = String(model.is_web_model);
      itemDiv.dataset.provider = model.provider;

      itemDiv.addEventListener("click", function (event) {
        event.stopPropagation();

        if (this.classList.contains("locked-by-key")) {
          window.showMissingKeyModal(this.dataset.provider);
          return;
        }

        // Logic to prevent selecting incompatible models when features are active
        if (this.classList.contains("option-disabled")) {
          const isWebSearchOn =
            document.getElementById("toggle-web-search")?.checked;
          const isVisionOn = document.getElementById("toggle-ocr")?.checked;
          const isAgentVisionOn = document.getElementById(
            "agent-screen-vision"
          )?.checked;
          let reason = "";

          if (selectElementId === "model-select") {
            if (isWebSearchOn) reason = "web";
            if (isVisionOn) reason = "vision";
          } else {
            if (isAgentVisionOn) reason = "vision";
          }

          if (reason) {
            window.showIncompatibleModelModal(reason);
            return;
          }
        }

        nativeSelectElement.value = this.dataset.value;
        nativeSelectElement.dispatchEvent(new Event("change"));

        selectedDisplayElement.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        selectedDisplayElement.appendChild(contentDiv);

        optionsContainer.classList.add("select-hide");
        selectedDisplayElement.classList.remove("select-arrow-active");

        Array.from(optionsContainer.children).forEach((child) =>
          child.classList.remove("same-as-selected")
        );
        this.classList.add("same-as-selected");
      });

      optionsContainer.appendChild(itemDiv);
    });

    // Determine value to select initially
    const valueToSelect =
      valueToPreselect !== null ? valueToPreselect : currentGeneralModel;

    let targetVal = valueToSelect;
    const targetDiv = optionsContainer.querySelector(
      `div[data-value="${valueToSelect}"]`
    );

    // If preselected model is locked, fallback to the first available
    if (!targetDiv || targetDiv.classList.contains("locked-by-key")) {
      const validDiv = optionsContainer.querySelector(
        `div:not(.locked-by-key)`
      );
      if (validDiv) targetVal = validDiv.dataset.value;
    }

    if (targetVal) {
      window._updateCustomSelectDisplay(containerName, targetVal);
    }

    window.updateTogglesAndModelsState();
  } catch (error) {
    console.error("Error loading text models:", error);
    selectedDisplayElement.textContent = window.t("error_loading");
  } finally {
    nativeSelectElement.dataset.loading = "false";
  }
};

/**
 * Loads API key configuration from the backend and fills input fields.
 * Initializes dirty state tracking.
 * @returns {Promise<void>}
 */
window.loadApiConfiguration = async () => {
  if (!window.isApiReady()) return;

  const inputElements = document.querySelectorAll(
    `.${DOM_IDS.API.INPUT_CLASS}`
  );
  const saveContainer = document.querySelector(DOM_IDS.API.ACTIONS_CONTAINER);

  try {
    const config = await window.pywebview.api.get_api_configuration();
    initialApiState = {};

    inputElements.forEach((input) => {
      const val = config[input.id] || "";
      input.value = val;
      // Store initial state to check for changes
      initialApiState[input.id] = val;
      updateApiStatusIndicator(input.id, val);

      // Re-attach listeners to handle dirty state
      input.removeEventListener("input", handleApiInputChange);
      input.addEventListener("input", handleApiInputChange);
    });
  } catch (e) {
    console.error("Error loading API config:", e);
  }
  saveContainer.classList.remove("visible");
};

/**
 * Updates the visual status indicator (dot) next to the API section title.
 * @param {string} inputId - ID of the input field.
 * @param {string} value - Current value.
 */
function updateApiStatusIndicator(inputId, value) {
  let type = null;
  if (inputId.includes("audio") || inputId.includes("deepgram")) type = "audio";
  if (inputId.includes("ai") || inputId.includes("cerebras")) type = "ai";

  if (!type) return;

  const indicator = document.getElementById(`status-${type}`);
  if (!indicator) return;

  const inputsInCard = indicator
    .closest(".api-card")
    .querySelectorAll(`.${DOM_IDS.API.INPUT_CLASS}`);
  const hasAnyValue = Array.from(inputsInCard).some(
    (i) => i.value.trim().length > 0
  );

  indicator.classList.toggle("valid", hasAnyValue);
}

/**
 * Event handler for API input changes. Checks if changes differ from initial state to show Save button.
 * @param {Event} e
 */
function handleApiInputChange(e) {
  const input = e.target;
  const saveContainer = document.querySelector(DOM_IDS.API.ACTIONS_CONTAINER);
  updateApiStatusIndicator(input.id, input.value);

  let hasChanged = false;
  document.querySelectorAll(`.${DOM_IDS.API.INPUT_CLASS}`).forEach((i) => {
    if (i.value !== initialApiState[i.id]) hasChanged = true;
  });

  if (hasChanged) saveContainer.classList.add("visible");
  else saveContainer.classList.remove("visible");
}

/**
 * Saves entered API keys to the backend.
 * Refreshes dropdowns on success.
 */
window.saveApiKeys = async () => {
  const inputs = document.querySelectorAll(`.${DOM_IDS.API.INPUT_CLASS}`);
  const saveBtn = document.getElementById(DOM_IDS.API.SAVE_BTN);
  const dataToSend = {};

  inputs.forEach((input) => {
    dataToSend[input.id] = input.value;
  });

  const originalText = saveBtn.innerText;
  saveBtn.innerText = window.t("saving");
  saveBtn.disabled = true;

  try {
    const response = await window.pywebview.api.save_api_keys(dataToSend);

    if (response.success) {
      // Update initial state to match saved data
      inputs.forEach((input) => (initialApiState[input.id] = input.value));

      saveBtn.innerText = window.t("saved");
      saveBtn.style.backgroundColor = "var(--color-green)";

      // Refresh data dependent on keys
      await window.populateModelDropdown();
      await window.populateAudioModelDropdown();

      setTimeout(() => {
        document
          .querySelector(DOM_IDS.API.ACTIONS_CONTAINER)
          .classList.remove("visible");
        saveBtn.innerText = originalText;
        saveBtn.style.backgroundColor = "";
        saveBtn.disabled = false;
      }, 1500);
    } else {
      window.showToast("Error saving keys.", "error");
      saveBtn.innerText = originalText;
      saveBtn.disabled = false;
    }
  } catch (err) {
    console.error("Error saving keys:", err);
    window.showToast("Critical error saving keys.", "error");
    saveBtn.innerText = originalText;
    saveBtn.disabled = false;
  }
};

/**
 * Updates option styles (disabled/enabled) based on key availability.
 * Called when models are loaded or keys are updated.
 */
window.updateTogglesAndModelsState = () => {
  const textModelOptions = document.querySelectorAll(
    "#custom-model-select-container .select-items div, #custom-agent-model-select-container .select-items div"
  );

  textModelOptions.forEach((option) => {
    const isKeyMissing = option.classList.contains("locked-by-key");
    option.classList.toggle("option-disabled", isKeyMissing);
  });
};

/**
 * Filters agent models based on screen vision capabilities.
 * If Vision is enabled for an agent, non-multimodal models are disabled.
 */
window.updateAgentModelAvailability = () => {
  const screenVisionToggle = document.getElementById("agent-screen-vision");
  const agentModelOptions = document.querySelectorAll(
    "#custom-agent-model-select-container .select-items div"
  );
  if (!screenVisionToggle) return;

  const isScreenVisionEnabled = screenVisionToggle.checked;

  agentModelOptions.forEach((option) => {
    const isMultimodal =
      String(option.dataset.multimodal).toLowerCase() === "true";
    const isKeyLocked = option.classList.contains("locked-by-key");

    const isDisabled = isKeyLocked || (isScreenVisionEnabled && !isMultimodal);
    option.classList.toggle("option-disabled", isDisabled);
  });
};
