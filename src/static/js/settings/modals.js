/* --- src/static/js/settings/modals.js --- */

// --- Incompatible Model Modal ---
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

// --- Missing API Key Modal ---
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

// --- Local Model Download Modal ---
window.showLocalModelModal = () => {
  const backdrop = document.getElementById("local-model-modal-backdrop");
  if (backdrop) {
    backdrop.style.display = "flex";
    setTimeout(() => backdrop.classList.add("visible"), 10);
  }
};

window.hideLocalModelModal = () => {
  const backdrop = document.getElementById("local-model-modal-backdrop");
  if (backdrop) {
    backdrop.classList.remove("visible");
    setTimeout(() => (backdrop.style.display = "none"), 200);
  }
};
