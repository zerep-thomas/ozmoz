/* --- src/static/js/settings/api-config.js --- */

/**
 * @typedef {Object} ApiState
 * @description Stores the initial values of API keys to detect changes.
 * @property {string} [api-key-groq-audio]
 * @property {string} [api-key-deepgram]
 * @property {string} [api-key-groq-ai]
 * @property {string} [api-key-cerebras]
 */

// --- Constants & State ---

const DOM_IDS = {
  MODAL: {
    LOCAL_BACKDROP: "local-model-modal-backdrop",
    LOCAL_CANCEL_BTN: "local-model-cancel-btn",
    LOCAL_DOWNLOAD_BTN: "local-model-download-btn",
    LOCAL_PROGRESS: "local-download-progress",
    DELETE_LOCAL_BACKDROP: "delete-local-modal-backdrop", // Nouveau
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
    `div[data-value="${newValue}"]`,
  );

  if (itemToSelect) {
    selectedDisplayElement.textContent = "";
    const contentDiv = document.createElement("div");
    contentDiv.className = "select-selected-content";
    contentDiv.innerHTML = itemToSelect.innerHTML;

    // On retire le bouton delete du visuel sélectionné pour l'esthétique
    const deleteBtn = contentDiv.querySelector(".model-delete-btn");
    if (deleteBtn) deleteBtn.remove();

    selectedDisplayElement.appendChild(contentDiv);

    Array.from(optionsContainer.children).forEach((child) =>
      child.classList.remove("same-as-selected"),
    );
    itemToSelect.classList.add("same-as-selected");
  }
};

/**
 * Initializes event listeners for the Local Model download modal.
 */
window.initLocalModelListeners = () => {
  const backdrop = document.getElementById(DOM_IDS.MODAL.LOCAL_BACKDROP);
  const cancelBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_CANCEL_BTN);
  const downloadBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_DOWNLOAD_BTN);

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
      const progressEl = document.getElementById(DOM_IDS.MODAL.LOCAL_PROGRESS);
      const currentBtn = document.getElementById(
        DOM_IDS.MODAL.LOCAL_DOWNLOAD_BTN,
      );
      const currentCancel = document.getElementById(
        DOM_IDS.MODAL.LOCAL_CANCEL_BTN,
      );

      if (currentBtn) currentBtn.style.display = "none";
      if (currentCancel) currentCancel.style.display = "none";
      if (progressEl) progressEl.style.display = "block";

      const modelToInstall =
        window.currentLocalModelToInstall || "local-whisper-large-v3-turbo";

      window.pywebview.api.install_local_model(modelToInstall);
    });
  }
};

/**
 * Callback exposed to the Python backend.
 */
window.onLocalModelInstallFinished = (status, modelName) => {
  const backdrop = document.getElementById(DOM_IDS.MODAL.LOCAL_BACKDROP);
  const downloadBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_DOWNLOAD_BTN);
  const cancelBtn = document.getElementById(DOM_IDS.MODAL.LOCAL_CANCEL_BTN);
  const progressEl = document.getElementById(DOM_IDS.MODAL.LOCAL_PROGRESS);

  if (backdrop) {
    backdrop.style.display = "none";
    backdrop.classList.remove("visible");
  }

  setTimeout(() => {
    if (downloadBtn) downloadBtn.style.display = "block";
    if (cancelBtn) cancelBtn.style.display = "block";
    if (progressEl) progressEl.style.display = "none";
  }, 500);

  if (status === "success") {
    // Si l'installation réussit, on sélectionne ce modèle
    const audioSelect = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
    if (audioSelect && modelName) {
      audioSelect.value = modelName;
      window.pywebview.api.set_audio_model(modelName);
      window.populateAudioModelDropdown(); // Rafraîchir pour mettre à jour les badges
    }
    window.showToast("Installation terminée avec succès !", "success");
  } else {
    window.showToast("Échec du téléchargement. Vérifiez les logs.", "error");
  }
};

/**
 * Fetches available languages and populates the custom dropdown.
 */
window.populateLanguageDropdown = async () => {
  const nativeSelectElement = document.getElementById(
    DOM_IDS.DROPDOWNS.LANGUAGE,
  );
  const optionsContainer = document.getElementById(
    DOM_IDS.DROPDOWNS.LANGUAGE_ITEMS,
  );

  if (!nativeSelectElement || !optionsContainer) return;

  const currentLang = await window.pywebview.api.get_current_language();
  if (window.setCurrentLanguage) window.setCurrentLanguage(currentLang);

  optionsContainer.innerHTML = "";
  nativeSelectElement.innerHTML = "";

  const languages = window.LANGUAGES_DATA || [];

  languages.forEach((lang) => {
    const translatedName = window.t(lang.key);

    const optionElement = document.createElement("option");
    optionElement.value = lang.value;
    optionElement.id = `${lang.value}-language-option`;
    optionElement.textContent = translatedName;
    nativeSelectElement.appendChild(optionElement);

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

    itemDiv.addEventListener("click", function (event) {
      event.stopPropagation();
      nativeSelectElement.value = this.dataset.value;

      optionsContainer.classList.add("select-hide");
      const selectedDisplay = document.getElementById(
        DOM_IDS.DROPDOWNS.LANGUAGE_SELECTED,
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
        child.classList.remove("same-as-selected"),
      );
      this.classList.add("same-as-selected");

      nativeSelectElement.dispatchEvent(new Event("change"));
    });

    optionsContainer.appendChild(itemDiv);
  });

  window._updateCustomSelectDisplay(
    "custom-language-select-container",
    currentLang || "en",
  );

  const newSelect = nativeSelectElement.cloneNode(true);
  nativeSelectElement.parentNode.replaceChild(newSelect, nativeSelectElement);
  newSelect.addEventListener("change", handleLanguageChange);
};

async function handleLanguageChange(event) {
  const newLanguage = event.target.value;
  window.applyTranslations(newLanguage);

  const optionsContainer = document.getElementById(
    DOM_IDS.DROPDOWNS.LANGUAGE_ITEMS,
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
          DOM_IDS.DROPDOWNS.LANGUAGE_SELECTED,
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
          DOM_IDS.DROPDOWNS.LANGUAGE,
        );
        nativeSelect.value = this.dataset.value;

        const container = document.getElementById(
          DOM_IDS.DROPDOWNS.LANGUAGE_ITEMS,
        );
        const display = document.getElementById(
          DOM_IDS.DROPDOWNS.LANGUAGE_SELECTED,
        );
        if (container) container.classList.add("select-hide");
        if (display) display.classList.remove("select-arrow-active");

        nativeSelect.dispatchEvent(new Event("change"));
      });
      optionsContainer.appendChild(itemDiv);
    });
  }

  try {
    if (!window.isApiReady()) return;

    const response = await window.pywebview.api.set_language(newLanguage);
    const currentAudioModel = document.getElementById(
      DOM_IDS.DROPDOWNS.AUDIO,
    ).value;

    if (response.final_audio_model !== currentAudioModel) {
      window.showToast(
        `Mode switched to ${response.final_audio_model} (Compatibility).`,
        "info",
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

async function handleAudioModelChange() {
  const audioModelSelect = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
  const autodetectOption = document.getElementById(
    DOM_IDS.DROPDOWNS.AUTODETECT_OPTION,
  );

  if (!audioModelSelect) return;

  const selectedAudioModel = audioModelSelect.value;
  const isWhisperBased =
    selectedAudioModel &&
    (selectedAudioModel.startsWith("whisper") ||
      selectedAudioModel.startsWith("local"));

  if (autodetectOption) {
    autodetectOption.style.display = isWhisperBased ? "block" : "none";
  }
}

/**
 * Fetches available audio models and populates the dropdown.
 * Handles local model installation status and API key locking.
 */
window.populateAudioModelDropdown = async () => {
  const nativeSelectElement = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
  const selectedDisplayElement = document.getElementById(
    DOM_IDS.DROPDOWNS.AUDIO_SELECTED,
  );
  const optionsContainer = document.getElementById(
    DOM_IDS.DROPDOWNS.AUDIO_ITEMS,
  );

  if (!nativeSelectElement) return;

  if (!window.hasInitializedLocalListeners) {
    window.initLocalModelListeners();
    window.hasInitializedLocalListeners = true;
  }

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
      // Nova-3 Filtering
      if (model.name === "nova-3") {
        const langBase = languageToCheck.split("-")[0].toLowerCase();
        const isSupported =
          supportedNova3Langs.includes(languageToCheck) ||
          supportedNova3Langs.includes(langBase);
        if (!isSupported) return;
      }

      const isLocal = model.provider === "local";

      // --- CORRECTION DU STATUT D'INSTALLATION SPÉCIFIQUE ---
      // On vérifie si l'objet 'installed' contient la clé spécifique du modèle
      let isLocalInstalled = false;
      if (
        typeof localStatus.installed === "object" &&
        localStatus.installed !== null
      ) {
        // Utilisation du nom du modèle comme clé
        isLocalInstalled = localStatus.installed[model.name] === true;
      } else {
        // Fallback legacy (si l'API renvoie un booléen simple)
        isLocalInstalled = localStatus.installed === true;
      }

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
        if (isDownloading && window.currentLocalModelToInstall === model.name) {
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
      if (model.size) itemDiv.dataset.size = model.size;

      // --- AJOUT DU BOUTON DE SUPPRESSION ---
      // Affiché uniquement pour les modèles locaux installés
      if (isLocal && isLocalInstalled) {
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "model-delete-btn";
        // SVG standard Feather Icons pour une netteté parfaite
        deleteBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                <line x1="10" y1="11" x2="10" y2="17"></line>
                <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
          `;

        deleteBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          window.showDeleteLocalModal(model.name, model.size);
        });

        itemDiv.appendChild(deleteBtn);
      }

      // Event Listener for Item Selection
      itemDiv.addEventListener("click", function (event) {
        event.stopPropagation();

        // Si modèle local non installé, on déclenche le téléchargement
        if (isLocal && !isLocalInstalled && !isDownloading) {
          const modal = document.getElementById(DOM_IDS.MODAL.LOCAL_BACKDROP);
          const sizeDisplay = document.getElementById(
            "local-model-size-display",
          );
          if (sizeDisplay && this.dataset.size) {
            const prefix = window.getCurrentLanguage().startsWith("fr")
              ? "Taille : "
              : "Size: ";
            sizeDisplay.textContent = prefix + this.dataset.size;
          }

          window.currentLocalModelToInstall = this.dataset.value;

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
        nativeSelectElement.value = modelValue;
        window.pywebview.api.set_audio_model(modelValue);

        selectedDisplayElement.textContent = "";
        const contentDiv = document.createElement("div");
        contentDiv.className = "select-selected-content";
        contentDiv.innerHTML = this.innerHTML;
        // On retire le bouton delete du visuel sélectionné pour l'esthétique
        const db = contentDiv.querySelector(".model-delete-btn");
        if (db) db.remove();

        selectedDisplayElement.appendChild(contentDiv);

        optionsContainer.classList.add("select-hide");
        selectedDisplayElement.classList.remove("select-arrow-active");
        Array.from(optionsContainer.children).forEach((child) =>
          child.classList.remove("same-as-selected"),
        );
        this.classList.add("same-as-selected");

        if (typeof handleAudioModelChange === "function") {
          handleAudioModelChange();
        }
      });
      optionsContainer.appendChild(itemDiv);
    });

    if (currentAudioModel) {
      const exists = Array.from(nativeSelectElement.options).some(
        (opt) => opt.value === currentAudioModel && !opt.disabled,
      );

      if (exists) {
        nativeSelectElement.value = currentAudioModel;
      } else if (nativeSelectElement.options.length > 0) {
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
        nativeSelectElement.value,
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
 */
window.populateModelDropdown = async (
  selectElementId = "model-select",
  valueToPreselect = null,
) => {
  const containerName =
    selectElementId === "model-select"
      ? "custom-model-select-container"
      : "custom-agent-model-select-container";

  const nativeSelectElement = document.getElementById(selectElementId);
  const selectedDisplayElement = document.getElementById(
    `${selectElementId}-selected`,
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

      const nativeOption = document.createElement("option");
      nativeOption.value = model.id;
      nativeOption.textContent = model.name;
      if (isLocked) nativeOption.disabled = true;
      nativeSelectElement.appendChild(nativeOption);

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

        if (this.classList.contains("option-disabled")) {
          const isWebSearchOn =
            document.getElementById("toggle-web-search")?.checked;
          const isVisionOn = document.getElementById("toggle-ocr")?.checked;
          const isAgentVisionOn = document.getElementById(
            "agent-screen-vision",
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
          child.classList.remove("same-as-selected"),
        );
        this.classList.add("same-as-selected");
      });

      optionsContainer.appendChild(itemDiv);
    });

    const valueToSelect =
      valueToPreselect !== null ? valueToPreselect : currentGeneralModel;

    let targetVal = valueToSelect;
    const targetDiv = optionsContainer.querySelector(
      `div[data-value="${valueToSelect}"]`,
    );

    if (!targetDiv || targetDiv.classList.contains("locked-by-key")) {
      const validDiv = optionsContainer.querySelector(
        `div:not(.locked-by-key)`,
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

window.loadApiConfiguration = async () => {
  if (!window.isApiReady()) return;

  const inputElements = document.querySelectorAll(
    `.${DOM_IDS.API.INPUT_CLASS}`,
  );

  document.querySelectorAll(".inline-save-btn").forEach((btn) => {
    const newBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(newBtn, btn);

    newBtn.addEventListener("click", (e) => {
      window.saveApiKeys(newBtn);
    });
  });

  try {
    const config = await window.pywebview.api.get_api_configuration();
    initialApiState = {};

    inputElements.forEach((input) => {
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
};

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
    (i) => i.value.trim().length > 0,
  );

  indicator.classList.toggle("valid", hasAnyValue);
}

function handleApiInputChange(e) {
  const input = e.target;
  updateApiStatusIndicator(input.id, input.value);

  const wrapper = input.closest(".input-wrapper");
  const btn = wrapper.querySelector(".inline-save-btn");

  if (btn.classList.contains("saved")) return;

  const initialVal = (initialApiState[input.id] || "").trim();
  const currentVal = input.value.trim();

  if (currentVal !== initialVal) {
    btn.classList.add("visible");
  } else {
    btn.classList.remove("visible");
  }
}

window.saveApiKeys = async (triggerBtn = null) => {
  const inputs = document.querySelectorAll(`.${DOM_IDS.API.INPUT_CLASS}`);
  const dataToSend = {};

  inputs.forEach((input) => {
    dataToSend[input.id] = input.value;
  });

  let originalContent = "";
  if (triggerBtn) {
    originalContent = triggerBtn.innerHTML;
    triggerBtn.innerHTML = `<svg class="spinner" viewBox="0 0 50 50" style="width:14px;height:14px;animation:rotate 2s linear infinite;"><circle cx="25" cy="25" r="20" fill="none" stroke="white" stroke-width="5"></circle></svg>`;
    triggerBtn.disabled = true;
  }

  try {
    const response = await window.pywebview.api.save_api_keys(dataToSend);

    if (response.success) {
      inputs.forEach((input) => (initialApiState[input.id] = input.value));

      await window.populateModelDropdown();
      await window.populateAudioModelDropdown();

      if (triggerBtn) {
        triggerBtn.classList.add("saved");
        triggerBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;

        setTimeout(() => {
          triggerBtn.classList.remove("saved");
          triggerBtn.classList.remove("visible");

          setTimeout(() => {
            triggerBtn.innerHTML = originalContent;
            triggerBtn.disabled = false;
          }, 200);
        }, 2000);
      } else {
        window.showToast("Clés sauvegardées", "success");
      }
    } else {
      window.showToast("Erreur de sauvegarde.", "error");
      if (triggerBtn) {
        triggerBtn.innerHTML = originalContent;
        triggerBtn.disabled = false;
      }
    }
  } catch (err) {
    console.error("Error saving keys:", err);
    window.showToast("Erreur critique.", "error");
    if (triggerBtn) {
      triggerBtn.innerHTML = originalContent;
      triggerBtn.disabled = false;
    }
  }
};

window.updateTogglesAndModelsState = () => {
  const textModelOptions = document.querySelectorAll(
    "#custom-model-select-container .select-items div, #custom-agent-model-select-container .select-items div",
  );

  textModelOptions.forEach((option) => {
    const isKeyMissing = option.classList.contains("locked-by-key");
    option.classList.toggle("option-disabled", isKeyMissing);
  });
};

window.updateAgentModelAvailability = () => {
  const screenVisionToggle = document.getElementById("agent-screen-vision");
  const agentModelOptions = document.querySelectorAll(
    "#custom-agent-model-select-container .select-items div",
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

// --- Local Model Deletion Logic ---

window.showDeleteLocalModal = (modelName, modelSize) => {
  const backdrop = document.getElementById(DOM_IDS.MODAL.DELETE_LOCAL_BACKDROP);
  const textEl = document.getElementById("delete-local-modal-text");
  const inputEl = document.getElementById("model-to-delete-id");

  if (backdrop && textEl && inputEl) {
    inputEl.value = modelName;

    // Use the translation system with placeholder replacement
    let message = window.t("modal_delete_local_text");

    // Safe placeholder replacement
    message = message.replace("{model}", modelName);
    message = message.replace("{size}", modelSize || "~");

    textEl.textContent = message;

    backdrop.style.display = "flex";
    setTimeout(() => backdrop.classList.add("visible"), 10);
  }
};

window.hideDeleteLocalModal = () => {
  const backdrop = document.getElementById(DOM_IDS.MODAL.DELETE_LOCAL_BACKDROP);
  if (backdrop) {
    backdrop.classList.remove("visible");
    setTimeout(() => (backdrop.style.display = "none"), 200);
  }
};

window.confirmDeleteLocalModel = async () => {
  const inputEl = document.getElementById("model-to-delete-id");
  if (!inputEl) return;

  const modelName = inputEl.value;
  window.hideDeleteLocalModal();

  try {
    const response = await window.pywebview.api.delete_local_model(modelName);
    if (response.success) {
      await window.populateAudioModelDropdown();

      // If the deleted model was the active one,
      // the UI will update via populateAudioModelDropdown
      const currentSelect = document.getElementById(DOM_IDS.DROPDOWNS.AUDIO);
      window._updateCustomSelectDisplay(
        "custom-audio-model-select-container",
        currentSelect.value,
      );
    } else {
      window.showToast("Error while deleting the model", "error");
    }
  } catch (e) {
    console.error(e);
    window.showToast("API error", "error");
  }
};
