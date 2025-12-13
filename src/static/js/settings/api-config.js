/* --- src/static/js/settings/api-config.js --- */

let initialApiState = {};

/**
 * Updates the visual display of a custom select dropdown.
 * @param {string} containerId
 * @param {string} newValue
 */
window._updateCustomSelectDisplay = (containerId, newValue) => {
  const container = document.getElementById(containerId);
  if (!container) return;
  const nativeSelect = container.querySelector("select");
  const selectedDisplay = container.querySelector(".select-selected");
  const itemsContainer = container.querySelector(".select-items");

  if (!nativeSelect || !selectedDisplay || !itemsContainer) return;

  nativeSelect.value = newValue;

  const itemToSelect = itemsContainer.querySelector(
    `div[data-value="${newValue}"]`
  );
  if (itemToSelect) {
    selectedDisplay.textContent = "";
    const contentDiv = document.createElement("div");
    contentDiv.className = "select-selected-content";
    contentDiv.innerHTML = itemToSelect.innerHTML;
    selectedDisplay.appendChild(contentDiv);

    Array.from(itemsContainer.children).forEach((child) =>
      child.classList.remove("same-as-selected")
    );
    itemToSelect.classList.add("same-as-selected");
  }
};

/**
 * Initializes event listeners for the Local Model download modal.
 * Designed to be safe against multiple initializations.
 */
window.initLocalModelListeners = () => {
  const backdrop = document.getElementById("local-model-modal-backdrop");
  const cancelBtn = document.getElementById("local-model-cancel-btn");
  const downloadBtn = document.getElementById("local-model-download-btn");

  if (cancelBtn) {
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
      const progress = document.getElementById("local-download-progress");
      const currentBtn = document.getElementById("local-model-download-btn");
      const currentCancel = document.getElementById("local-model-cancel-btn");

      if (currentBtn) currentBtn.style.display = "none";
      if (currentCancel) currentCancel.style.display = "none";
      if (progress) progress.style.display = "block";

      window.pywebview.api.install_local_model();
    });
  }
};

/**
 * Callback exposed to the Python backend to signal download completion.
 * @param {string} status - 'success' or 'error'.
 */
window.onLocalModelInstallFinished = (status) => {
  const backdrop = document.getElementById("local-model-modal-backdrop");
  const downloadBtn = document.getElementById("local-model-download-btn");
  const cancelBtn = document.getElementById("local-model-cancel-btn");
  const progress = document.getElementById("local-download-progress");

  if (backdrop) {
    backdrop.style.display = "none";
    backdrop.classList.remove("visible");
  }

  setTimeout(() => {
    if (downloadBtn) downloadBtn.style.display = "block";
    if (cancelBtn) cancelBtn.style.display = "block";
    if (progress) progress.style.display = "none";
  }, 500);

  if (status === "success") {
    const select = document.getElementById("audio-model-select");
    if (select) {
      select.value = "local-whisper-large-v3-turbo";
      window.pywebview.api.set_audio_model("local-whisper-large-v3-turbo");
      window.populateAudioModelDropdown();
    }
  } else {
    window.showToast("Download failed. Check logs.", "error");
  }
};

/**
 * Populates the language selection dropdown.
 */
window.populateLanguageDropdown = async () => {
  const nativeSelect = document.getElementById("language-select");
  const itemsContainer = document.getElementById("language-select-items");

  if (!nativeSelect || !itemsContainer) return;

  itemsContainer.innerHTML = "";
  nativeSelect.innerHTML = "";

  const languages = window.LANGUAGES_DATA || [];

  languages.forEach((lang) => {
    const translatedName = window.t(lang.key);

    const option = document.createElement("option");
    option.value = lang.value;
    option.id = `${lang.value}-language-option`;
    option.textContent = translatedName;
    nativeSelect.appendChild(option);

    const div = document.createElement("div");
    const nameSpan = document.createElement("span");
    nameSpan.className = "model-name-display";
    nameSpan.textContent = translatedName;

    div.appendChild(nameSpan);

    if (lang.flag) {
      const flagSpan = document.createElement("span");
      flagSpan.innerHTML = ` ${lang.flag}`;
      nameSpan.appendChild(flagSpan);
    }

    div.dataset.value = lang.value;

    div.addEventListener("click", function (e) {
      e.stopPropagation();
      nativeSelect.value = this.dataset.value;

      itemsContainer.classList.add("select-hide");
      const selectedDisplay = document.getElementById(
        "language-select-selected"
      );
      if (selectedDisplay) {
        selectedDisplay.classList.remove("select-arrow-active");
        selectedDisplay.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        selectedDisplay.appendChild(contentDiv);
      }

      Array.from(itemsContainer.children).forEach((child) =>
        child.classList.remove("same-as-selected")
      );
      this.classList.add("same-as-selected");
      nativeSelect.dispatchEvent(new Event("change"));
    });
    itemsContainer.appendChild(div);
  });

  const newSelect = nativeSelect.cloneNode(true);
  nativeSelect.parentNode.replaceChild(newSelect, nativeSelect);
  newSelect.addEventListener("change", handleLanguageChange);
};

/**
 * Handles changes to the language selection.
 * @param {Event} event - The change event.
 */
async function handleLanguageChange(event) {
  const newLanguage = event.target.value;
  window.applyTranslations(newLanguage);

  const itemsContainer = document.getElementById("language-select-items");
  if (itemsContainer) {
    itemsContainer.innerHTML = "";
    window.LANGUAGES_DATA.forEach((lang) => {
      const translatedName = window.t(lang.key);
      const div = document.createElement("div");
      const nameSpan = document.createElement("span");
      nameSpan.className = "model-name-display";
      nameSpan.textContent = translatedName;
      div.appendChild(nameSpan);

      if (lang.flag) {
        const flagSpan = document.createElement("span");
        flagSpan.innerHTML = ` ${lang.flag}`;
        nameSpan.appendChild(flagSpan);
      }

      div.dataset.value = lang.value;

      if (lang.value === newLanguage) {
        div.classList.add("same-as-selected");
        const selectedDisplay = document.getElementById(
          "language-select-selected"
        );
        if (selectedDisplay) {
          selectedDisplay.textContent = "";
          const contentDiv = document.createElement("div");
          contentDiv.className = "select-selected-content";
          contentDiv.innerHTML = div.innerHTML;
          selectedDisplay.appendChild(contentDiv);
        }
      }

      div.addEventListener("click", function (e) {
        e.stopPropagation();
        const nativeSelect = document.getElementById("language-select");
        nativeSelect.value = this.dataset.value;

        const container = document.getElementById("language-select-items");
        const display = document.getElementById("language-select-selected");
        if (container) container.classList.add("select-hide");
        if (display) display.classList.remove("select-arrow-active");

        nativeSelect.dispatchEvent(new Event("change"));
      });
      itemsContainer.appendChild(div);
    });
  }

  try {
    if (!window.isApiReady()) return;

    const response = await window.pywebview.api.set_language(newLanguage);
    const currentAudioModel =
      document.getElementById("audio-model-select").value;
    if (response.final_audio_model !== currentAudioModel) {
      window.showToast(
        `Mode switched to ${response.final_audio_model} (Compatibility).`,
        "info"
      );
    }

    await window.populateAudioModelDropdown();
    await handleAudioModelChange();

    window.loadActivityChartData();
    window.loadDashboardStats();
    window.populateModelDropdown();
  } catch (error) {
    console.error("Language switch error:", error);
  }
}

/**
 * Toggles visibility of the auto-detect option based on model capabilities.
 */
async function handleAudioModelChange() {
  const audioModelSelect = document.getElementById("audio-model-select");
  const autodetectOption = document.getElementById(
    "autodetect-language-option"
  );

  if (!audioModelSelect) return;

  const selectedAudioModel = audioModelSelect.value;
  const isWhisper =
    selectedAudioModel &&
    (selectedAudioModel.startsWith("whisper") ||
      selectedAudioModel === "local-turbo");

  if (autodetectOption) {
    autodetectOption.style.display = isWhisper ? "block" : "none";
  }
}

/**
 * Populates the audio model dropdown.
 * Handles:
 * 1. Remote models (Groq/Deepgram)
 * 2. Local model (Whisper Turbo) with installation status check
 */
window.populateAudioModelDropdown = async () => {
  const nativeSelect = document.getElementById("audio-model-select");
  const selectedDisplay = document.getElementById(
    "audio-model-select-selected"
  );
  const itemsContainer = document.getElementById("audio-model-select-items");

  if (!nativeSelect) return;

  if (!window._localListenersInit) {
    window.initLocalModelListeners();
    window._localListenersInit = true;
  }

  if (nativeSelect.dataset.loading === "true") return;
  nativeSelect.dataset.loading = "true";

  itemsContainer.innerHTML = "";
  nativeSelect.innerHTML = "";

  try {
    const [audioModels, keyStatus, localStatus] = await Promise.all([
      window.pywebview.api.get_translated_audio_models(),
      window.pywebview.api.get_providers_status(),
      window.pywebview.api.get_local_model_status(),
    ]);

    const currentAudioModel =
      await window.pywebview.api.get_current_audio_model();
    const currentLangState = window.getCurrentLanguage() || "en";
    const langToCheck =
      currentLangState === "autodetect" ? "en" : currentLangState;
    const supported = window.NOVA3_SUPPORTED_LANGUAGES || ["en"];

    audioModels.forEach((model) => {
      if (model.name === "nova-3") {
        const langBase = langToCheck.split("-")[0].toLowerCase();
        const isSupported =
          supported.includes(langToCheck) || supported.includes(langBase);
        if (!isSupported) return;
      }

      const isLocal = model.provider === "local";
      const isLocalInstalled = localStatus.installed;
      const isDownloading = localStatus.loading;

      let isLocked = false;
      if (model.provider === "groq" && !keyStatus.groq_audio) isLocked = true;
      if (model.provider === "deepgram" && !keyStatus.deepgram) isLocked = true;

      const nativeOption = document.createElement("option");
      nativeOption.value = model.name;
      nativeOption.textContent = model.name;
      if (isLocked) nativeOption.disabled = true;
      nativeSelect.appendChild(nativeOption);

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

      itemDiv.addEventListener("click", function (e) {
        e.stopPropagation();

        if (isLocal && !isLocalInstalled && !isDownloading) {
          const modal = document.getElementById("local-model-modal-backdrop");
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

        if (this.classList.contains("locked-by-key")) {
          window.showMissingKeyModal(this.dataset.provider);
          return;
        }
        const modelValue = this.dataset.value;
        nativeSelect.value = modelValue;
        window.pywebview.api.set_audio_model(modelValue);

        selectedDisplay.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        selectedDisplay.appendChild(contentDiv);

        itemsContainer.classList.add("select-hide");
        selectedDisplay.classList.remove("select-arrow-active");
        Array.from(itemsContainer.children).forEach((child) =>
          child.classList.remove("same-as-selected")
        );
        this.classList.add("same-as-selected");

        if (typeof handleAudioModelChange === "function") {
          handleAudioModelChange();
        }
      });
      itemsContainer.appendChild(itemDiv);
    });

    if (currentAudioModel) {
      const exists = Array.from(nativeSelect.options).some(
        (opt) => opt.value === currentAudioModel && !opt.disabled
      );

      if (exists) {
        nativeSelect.value = currentAudioModel;
      } else if (nativeSelect.options.length > 0) {
        for (let i = 0; i < nativeSelect.options.length; i++) {
          if (!nativeSelect.options[i].disabled) {
            nativeSelect.value = nativeSelect.options[i].value;
            window.pywebview.api.set_audio_model(nativeSelect.value);
            break;
          }
        }
      }
      window._updateCustomSelectDisplay(
        "custom-audio-model-select-container",
        nativeSelect.value
      );
    }
  } catch (error) {
    console.error("Error populating Audio Dropdown:", error);
  } finally {
    nativeSelect.dataset.loading = "false";
  }
};

/**
 * Populates the Text AI Model dropdown.
 * @param {string} [selectElementId="model-select"]
 * @param {string|null} [valueToPreselect=null]
 */
window.populateModelDropdown = async (
  selectElementId = "model-select",
  valueToPreselect = null
) => {
  const containerName =
    selectElementId === "model-select"
      ? "custom-model-select-container"
      : "custom-agent-model-select-container";
  const nativeSelect = document.getElementById(selectElementId);
  const selectedDisplay = document.getElementById(
    `${selectElementId}-selected`
  );
  const itemsContainer = document.getElementById(`${selectElementId}-items`);

  if (!nativeSelect || nativeSelect.dataset.loading === "true") return;

  nativeSelect.dataset.loading = "true";
  selectedDisplay.textContent = window.t("loading");
  itemsContainer.innerHTML = "";
  nativeSelect.innerHTML = "";

  try {
    const [models, keyStatus] = await Promise.all([
      window.pywebview.api.get_filtered_text_models(),
      window.pywebview.api.get_providers_status(),
    ]);

    if (!models || models.length === 0) {
      selectedDisplay.textContent = window.t("no_models");
      return;
    }

    const currentGeneralModel = await window.pywebview.api.get_current_model();

    models.forEach((model) => {
      let isLocked = false;
      if (model.provider === "groq" && !keyStatus.groq_ai) isLocked = true;
      if (model.provider === "cerebras" && !keyStatus.cerebras) isLocked = true;

      const nativeOption = document.createElement("option");
      nativeOption.value = model.id;
      nativeOption.textContent = model.name;
      if (isLocked) nativeOption.disabled = true;
      nativeSelect.appendChild(nativeOption);

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

      itemDiv.addEventListener("click", function (e) {
        e.stopPropagation();

        if (this.classList.contains("locked-by-key")) {
          window.showMissingKeyModal(this.dataset.provider);
          return;
        }

        if (this.classList.contains("option-disabled")) {
          const isWebSearchOn =
            document.getElementById("toggle-web-search")?.checked;
          const isOcrOn = document.getElementById("toggle-ocr")?.checked;
          let reason = "";

          if (selectElementId === "model-select") {
            if (isWebSearchOn) reason = "web";
            if (isOcrOn) reason = "vision";
          } else {
            if (document.getElementById("agent-screen-vision")?.checked)
              reason = "vision";
          }
          if (reason) {
            window.showIncompatibleModelModal(reason);
            return;
          }
        }

        nativeSelect.value = this.dataset.value;
        nativeSelect.dispatchEvent(new Event("change"));

        selectedDisplay.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        selectedDisplay.appendChild(contentDiv);

        itemsContainer.classList.add("select-hide");
        selectedDisplay.classList.remove("select-arrow-active");

        Array.from(itemsContainer.children).forEach((child) =>
          child.classList.remove("same-as-selected")
        );
        this.classList.add("same-as-selected");
      });

      itemsContainer.appendChild(itemDiv);
    });

    const valueToSelect =
      valueToPreselect !== null ? valueToPreselect : currentGeneralModel;

    let targetVal = valueToSelect;
    const targetDiv = itemsContainer.querySelector(
      `div[data-value="${valueToSelect}"]`
    );
    if (!targetDiv || targetDiv.classList.contains("locked-by-key")) {
      const validDiv = itemsContainer.querySelector(`div:not(.locked-by-key)`);
      if (validDiv) targetVal = validDiv.dataset.value;
    }

    if (targetVal) {
      window._updateCustomSelectDisplay(containerName, targetVal);
    }

    window.updateTogglesAndModelsState();
  } catch (error) {
    console.error("Error loading text models:", error);
    selectedDisplay.textContent = window.t("error_loading");
  } finally {
    nativeSelect.dataset.loading = "false";
  }
};

/**
 * Loads API key configuration and populates input fields.
 */
window.loadApiConfiguration = async () => {
  if (!window.isApiReady()) return;

  const inputs = document.querySelectorAll(".api-input");
  const saveContainer = document.querySelector(".api-actions");

  try {
    const config = await window.pywebview.api.get_api_configuration();
    initialApiState = {};

    inputs.forEach((input) => {
      const val = config[input.id] || "";
      input.value = val;
      initialApiState[input.id] = val;
      updateApiStatusIndicator(input.id, val);

      input.removeEventListener("input", handleApiInputChange);
      input.addEventListener("input", handleApiInputChange);
    });
  } catch (e) {
    console.error("Error loading API config:", e);
  }
  saveContainer.classList.remove("visible");
};

function updateApiStatusIndicator(inputId, value) {
  let type = null;
  if (inputId.includes("audio") || inputId.includes("deepgram")) type = "audio";
  if (inputId.includes("ai") || inputId.includes("cerebras")) type = "ai";

  if (!type) return;
  const indicator = document.getElementById(`status-${type}`);
  const inputsInCard = indicator
    .closest(".api-card")
    .querySelectorAll(".api-input");
  const hasValue = Array.from(inputsInCard).some(
    (i) => i.value.trim().length > 0
  );

  if (indicator) indicator.classList.toggle("valid", hasValue);
}

function handleApiInputChange(e) {
  const input = e.target;
  const saveContainer = document.querySelector(".api-actions");
  updateApiStatusIndicator(input.id, input.value);

  let hasChanged = false;
  document.querySelectorAll(".api-input").forEach((i) => {
    if (i.value !== initialApiState[i.id]) hasChanged = true;
  });

  if (hasChanged) saveContainer.classList.add("visible");
  else saveContainer.classList.remove("visible");
}

/**
 * Saves entered API keys to the backend.
 */
window.saveApiKeys = () => {
  const inputs = document.querySelectorAll(".api-input");
  const saveBtn = document.getElementById("save-api-keys-btn");
  const dataToSend = {};

  inputs.forEach((input) => {
    dataToSend[input.id] = input.value;
  });

  const originalText = saveBtn.innerText;
  saveBtn.innerText = window.t("saving");
  saveBtn.disabled = true;

  window.pywebview.api
    .save_api_keys(dataToSend)
    .then((response) => {
      if (response.success) {
        inputs.forEach((input) => (initialApiState[input.id] = input.value));
        saveBtn.innerText = window.t("saved");
        saveBtn.style.backgroundColor = "var(--color-green)";

        window.populateModelDropdown();
        window.populateAudioModelDropdown();

        setTimeout(() => {
          document.querySelector(".api-actions").classList.remove("visible");
          saveBtn.innerText = originalText;
          saveBtn.style.backgroundColor = "";
          saveBtn.disabled = false;
        }, 1500);
      } else {
        window.showToast("Error saving keys.", "error");
        saveBtn.innerText = originalText;
        saveBtn.disabled = false;
      }
    })
    .catch((err) => {
      console.error("Error saving keys:", err);
      window.showToast("Critical error saving keys.", "error");
      saveBtn.innerText = originalText;
      saveBtn.disabled = false;
    });
};

/**
 * Updates UI state based on available API keys.
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
