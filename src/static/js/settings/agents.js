/* --- static/js/settings/agents.js --- */

let allAgents = [];
let agentFilterListenerAttached = false;
let editingAgentId = null;

/**
 * Loads agents from the backend and updates the UI.
 */
window.loadAgents = () => {
  if (!window.isApiReady()) {
    displayAgents([]);
    return;
  }
  window.pywebview.api
    .get_agents()
    .then((agents) => {
      allAgents = agents || [];
      filterAndDisplayAgents();
      window.setupAgentFilterListener();
    })
    .catch((err) => {
      console.error("Error loading agents:", err);
      displayAgents([]);
    });
};

/**
 * Renders the list of agents to the DOM safely.
 * @param {Array} agentsToDisplay - The filtered list of agents.
 */
function displayAgents(agentsToDisplay) {
  const list = document.getElementById("agents-list");
  const noAgents = document.getElementById("no-agents");
  const emptySearch = document.getElementById("empty-agent-search-result");

  if (!list || !noAgents || !emptySearch) return;

  list.innerHTML = "";

  if (allAgents.length === 0) {
    noAgents.style.display = "block";
    emptySearch.style.display = "none";
    list.style.display = "none";
    return;
  }

  noAgents.style.display = "none";
  list.style.display = "grid";

  if (
    agentsToDisplay.length === 0 &&
    document.getElementById("filter-agents").value
  ) {
    emptySearch.style.display = "block";
  } else {
    emptySearch.style.display = "none";
  }

  agentsToDisplay.forEach((agent) => {
    if (!agent || typeof agent.id === "undefined") return;

    const card = document.createElement("div");
    card.className = `agent-card ${agent.active ? "active" : ""}`;
    card.id = `agent-${agent.id}`;

    const statusText = agent.active
      ? window.t("status_active")
      : window.t("status_inactive");

    // Create the structure with placeholders for text content
    card.innerHTML = `
            <div class="agent-header">
                <h4 class="agent-title"></h4>
                <div class="agent-status-toggle"> 
                    <span class="status-badge ${
                      agent.active ? "status-active" : "status-inactive"
                    }">
                        ${statusText}
                    </span>
                    <label class="toggle-switch">
                        <input class="toggle-input" id="toggle-${
                          agent.id
                        }" type="checkbox" ${agent.active ? "checked" : ""}>
                        <label class="toggle-label" for="toggle-${
                          agent.id
                        }"></label>
                    </label>
                </div> 
            </div>
            <div class="agent-body">
                <div class="agent-property">
                    <div class="agent-property-label" data-i18n="lbl_model_ai">${window.t(
                      "lbl_model_ai"
                    )}</div>
                    <div class="agent-property-value model-value"></div>
                </div>
                <div class="agent-property">
                    <div class="agent-property-label" data-i18n="lbl_agent_prompt">${window.t(
                      "lbl_agent_prompt"
                    )}</div>
                    <div class="agent-property-value agent-prompt-preview"></div>
                </div>
            </div>
            <div class="agent-actions">
                <div class="agent-action-buttons">
                    <button class="button agent-action-btn edit-btn" type="button" data-i18n="btn_edit">${window.t(
                      "btn_edit"
                    )}</button>
                    <button class="button danger agent-action-btn delete-btn" type="button" data-i18n="btn_delete">${window.t(
                      "btn_delete"
                    )}</button>
                </div>
            </div>
        `;

    // Inject Text Content safely
    const titleEl = card.querySelector(".agent-title");
    titleEl.textContent = agent.name;
    titleEl.title = agent.name;

    const modelEl = card.querySelector(".model-value");
    if (agent.model) {
      modelEl.textContent = agent.model;
    } else {
      modelEl.innerHTML = "<i>" + window.t("no_model") + "</i>";
    }

    const promptEl = card.querySelector(".agent-prompt-preview");
    if (agent.prompt) {
      promptEl.textContent = agent.prompt;
      promptEl.title = agent.prompt;
    } else {
      promptEl.innerHTML = "<i>No prompt defined</i>";
    }

    // Attach Event Listeners
    const toggleInput = card.querySelector(".toggle-input");
    toggleInput.addEventListener("change", (e) =>
      window.toggleAgentActive(agent.id, e.target.checked)
    );

    const editBtn = card.querySelector(".edit-btn");
    editBtn.addEventListener("click", () => window.editAgent(agent.id));

    const deleteBtn = card.querySelector(".delete-btn");
    deleteBtn.addEventListener("click", () =>
      window.showDeleteAgentModal(agent.id)
    );

    list.appendChild(card);
  });
}

window.setupAgentFilterListener = () => {
  const filterInput = document.getElementById("filter-agents");
  if (filterInput && !agentFilterListenerAttached) {
    filterInput.addEventListener(
      "input",
      window.debounce(filterAndDisplayAgents, 250)
    );
    agentFilterListenerAttached = true;
  }
};

function filterAndDisplayAgents() {
  const filterInput = document.getElementById("filter-agents");
  if (!filterInput) return;
  const query = filterInput.value.toLowerCase();

  if (!query) {
    displayAgents(allAgents);
    return;
  }
  const filtered = allAgents.filter(
    (agent) =>
      (agent.name && agent.name.toLowerCase().includes(query)) ||
      (agent.trigger && agent.trigger.toLowerCase().includes(query))
  );
  displayAgents(filtered);
}

// --- Modal Logic ---

window.showAgentModal = async (agentId = null) => {
  const backdrop = document.getElementById("agent-modal-backdrop");
  const title = document.getElementById("agent-modal-title");
  const saveBtn = document.getElementById("save-agent-btn");
  const nameInput = document.getElementById("agent-name");
  const triggerInput = document.getElementById("agent-trigger");
  const promptInput = document.getElementById("agent-prompt");
  const editIdInput = document.getElementById("agent-edit-id");
  const autopasteToggle = document.getElementById("agent-autopaste");
  const screenVisionToggle = document.getElementById("agent-screen-vision");
  const feedbackEl = document.getElementById("agent-modal-feedback");

  if (feedbackEl) feedbackEl.style.display = "none";
  if (!backdrop) return;

  editIdInput.value = "";
  nameInput.value = "";
  triggerInput.value = "";
  promptInput.value = "";
  nameInput.classList.remove("error");
  let agentModelToSelect = null;

  if (agentId) {
    const agent = allAgents.find((a) => a.id === agentId);
    if (agent) {
      editingAgentId = agentId;
      editIdInput.value = agentId;
      title.textContent = window.t("modal_agent_edit_title");
      saveBtn.textContent = window.t("btn_save_changes");
      nameInput.value = agent.name || "";
      triggerInput.value = agent.trigger || "";
      promptInput.value = agent.prompt || "";
      agentModelToSelect = agent.model || "";
      autopasteToggle.checked = agent.autopaste !== false;
      screenVisionToggle.checked = agent.screen_vision || false;
    }
  } else {
    editingAgentId = null;
    title.textContent = window.t("modal_agent_create_title");
    saveBtn.textContent = window.t("btn_create_agent");

    if (window.isApiReady()) {
      try {
        agentModelToSelect = await window.pywebview.api.get_current_model();
      } catch (e) {
        console.error(e);
      }
    }
    autopasteToggle.checked = true;
    screenVisionToggle.checked = false;
  }

  await window.populateModelDropdown("agent-model-select", agentModelToSelect);
  window.updateAgentModelAvailability();

  backdrop.style.display = "flex";
  setTimeout(() => backdrop.classList.add("visible"), 10);
  nameInput.focus();
};

window.hideAgentModal = () => {
  const backdrop = document.getElementById("agent-modal-backdrop");
  if (!backdrop) return;
  backdrop.classList.remove("visible");
  setTimeout(() => {
    backdrop.style.display = "none";
  }, 200);
  editingAgentId = null;
};

window.saveAgent = () => {
  const name = document.getElementById("agent-name").value.trim();
  const trigger = document.getElementById("agent-trigger").value.trim() || null;
  const prompt = document.getElementById("agent-prompt").value.trim();
  const agentId = document.getElementById("agent-edit-id").value;
  const model = document.getElementById("agent-model-select")?.value || "";
  const autopaste = document.getElementById("agent-autopaste").checked;
  const screenVision = document.getElementById("agent-screen-vision").checked;
  const saveBtn = document.getElementById("save-agent-btn");
  const feedbackEl = document.getElementById("agent-modal-feedback");

  if (!name || !prompt) {
    if (feedbackEl) {
      feedbackEl.textContent = "Name and prompt are required.";
      feedbackEl.style.display = "block";
    }
    return;
  }

  const agentData = {
    id: agentId || null,
    name,
    trigger,
    prompt,
    model,
    autopaste,
    screen_vision: screenVision,
  };

  const apiCall = agentId
    ? window.pywebview.api.update_agent
    : window.pywebview.api.add_agent;

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";

  apiCall(agentData)
    .then((response) => {
      if (response && response.success) {
        window.hideAgentModal();
        window.loadAgents();
      } else {
        alert(`Error saving agent: ${response.error || "Unknown"}`);
      }
    })
    .catch((err) => {
      console.error("Save agent error:", err);
      alert("System error while saving agent.");
    })
    .finally(() => {
      saveBtn.disabled = false;
      saveBtn.textContent = window.t("btn_save");
    });
};

window.editAgent = (agentId) => {
  window.showAgentModal(agentId).catch(console.error);
};

window.showDeleteAgentModal = (agentId) => {
  const backdrop = document.getElementById("delete-agent-modal-backdrop");
  const textElement = document.getElementById("delete-agent-modal-text");
  const agent = allAgents.find((a) => a.id === agentId);
  const deleteIdInput = document.getElementById("agent-delete-id");

  if (agent && backdrop && textElement) {
    const message = window
      .t("confirm_delete_agent")
      .replace("{name}", window.escapeHtml(agent.name));
    textElement.innerHTML = message;
    deleteIdInput.value = agentId;
    backdrop.style.display = "flex";
    setTimeout(() => backdrop.classList.add("visible"), 10);
  }
};

window.hideDeleteAgentModal = () => {
  const backdrop = document.getElementById("delete-agent-modal-backdrop");
  if (!backdrop) return;
  backdrop.classList.remove("visible");
  setTimeout(() => {
    backdrop.style.display = "none";
    document.getElementById("agent-delete-id").value = "";
  }, 200);
};

window.confirmDeleteAgent = () => {
  const agentId = document.getElementById("agent-delete-id").value;
  if (!window.isApiReady() || !agentId) return;

  window.pywebview.api
    .delete_agent(agentId)
    .then((success) => {
      if (success) {
        window.hideDeleteAgentModal();
        window.loadAgents();
      } else {
        window.showToast("Failed to delete agent.", "error");
      }
    })
    .catch((err) => {
      console.error("Delete agent error:", err);
      window.showToast("Error communicating with backend.", "error");
    });
};

window.toggleAgentActive = (agentId, isActive) => {
  if (!window.isApiReady()) return;

  window.pywebview.api
    .toggle_agent_status(agentId, isActive)
    .then((response) => {
      if (response && response.success) {
        const agentIndex = allAgents.findIndex((a) => a.id === agentId);
        if (agentIndex > -1) allAgents[agentIndex].active = isActive;
        window.loadAgents();
      } else {
        window.loadAgents();
      }
    })
    .catch((err) => {
      console.error("Toggle error:", err);
      window.loadAgents();
    });
};

window.handleAgentScreenVisionToggle = (checkboxElement) => {
  const isChecked = checkboxElement.checked;
  const priorityMultimodal = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
  ];
  const itemsContainer = document.getElementById("agent-model-select-items");

  let newModelId = null;

  if (itemsContainer) {
    if (isChecked) {
      for (const modelId of priorityMultimodal) {
        if (itemsContainer.querySelector(`div[data-value="${modelId}"]`)) {
          newModelId = modelId;
          break;
        }
      }
      if (!newModelId) {
        const fallback = itemsContainer.querySelector(
          'div[data-multimodal="true"]'
        );
        if (fallback) newModelId = fallback.dataset.value;
      }
    }

    if (newModelId) {
      window._updateCustomSelectDisplay(
        "custom-agent-model-select-container",
        newModelId
      );
    }
  }
  window.updateAgentModelAvailability();
};
