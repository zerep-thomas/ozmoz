/* --- static/js/settings/agents.js --- */

/**
 * @typedef {Object} Agent
 * @property {string} id - Unique identifier (UUID).
 * @property {string} name - Display name of the agent.
 * @property {string} [trigger] - Keyword triggering the agent.
 * @property {string} prompt - System instructions.
 * @property {string} model - Model ID used by the agent.
 * @property {boolean} active - Whether the agent is enabled.
 * @property {boolean} autopaste - Whether to paste results automatically.
 * @property {boolean} screen_vision - Whether the agent has visual context.
 */

// --- State Management ---

/** @type {Agent[]} */
let cachedAgentsList = [];

/** @type {boolean} */
let isAgentFilterAttached = false;

/** @type {string|null} */
let currentEditingAgentId = null;

// --- Constants ---

const DOM = {
  LIST: "agents-list",
  NO_AGENTS_MSG: "no-agents",
  EMPTY_SEARCH: "empty-agent-search-result",
  FILTER_INPUT: "filter-agents",
  MODAL: {
    BACKDROP: "agent-modal-backdrop",
    TITLE: "agent-modal-title",
    SAVE_BTN: "save-agent-btn",
    FEEDBACK: "agent-modal-feedback",
    INPUT_ID: "agent-edit-id",
    INPUT_NAME: "agent-name",
    INPUT_TRIGGER: "agent-trigger",
    INPUT_PROMPT: "agent-prompt",
    SELECT_MODEL: "agent-model-select",
    TOGGLE_AUTOPASTE: "agent-autopaste",
    TOGGLE_VISION: "agent-screen-vision",
  },
  DELETE_MODAL: {
    BACKDROP: "delete-agent-modal-backdrop",
    TEXT: "delete-agent-modal-text",
    INPUT_ID: "agent-delete-id",
  },
};

/**
 * Fetches agents from the Python backend and refreshes the UI.
 * Entry point for this module.
 * @returns {Promise<void>}
 */
window.loadAgents = async () => {
  if (!window.isApiReady()) {
    displayAgents([]);
    return;
  }

  try {
    const agents = await window.pywebview.api.get_agents();
    cachedAgentsList = agents || [];
    filterAndDisplayAgents();
    window.setupAgentFilterListener();
  } catch (error) {
    console.error("[Agents] Error loading agents:", error);
    displayAgents([]);
  }
};

/**
 * Renders the list of agents into the DOM.
 * Handles empty states and search results visibility.
 *
 * @param {Agent[]} agentsToDisplay - The filtered list of agents to render.
 */
function displayAgents(agentsToDisplay) {
  const listContainer = document.getElementById(DOM.LIST);
  const noAgentsEl = document.getElementById(DOM.NO_AGENTS_MSG);
  const emptySearchEl = document.getElementById(DOM.EMPTY_SEARCH);
  const filterInput = document.getElementById(DOM.FILTER_INPUT);

  if (!listContainer || !noAgentsEl || !emptySearchEl) return;

  // Clear current list
  listContainer.innerHTML = "";

  // Case 1: No agents exist at all
  if (cachedAgentsList.length === 0) {
    noAgentsEl.style.display = "block";
    emptySearchEl.style.display = "none";
    listContainer.style.display = "none";
    return;
  }

  noAgentsEl.style.display = "none";
  listContainer.style.display = "grid";

  // Case 2: Agents exist but filter returned no results
  if (agentsToDisplay.length === 0 && filterInput?.value) {
    emptySearchEl.style.display = "block";
  } else {
    emptySearchEl.style.display = "none";
  }

  // Render cards
  agentsToDisplay.forEach((agent) => {
    if (!agent || typeof agent.id === "undefined") return;
    const cardElement = createAgentCardElement(agent);
    listContainer.appendChild(cardElement);
  });
}

/**
 * Creates a DOM element representing an Agent card.
 * Encapsulates HTML structure generation and event binding.
 *
 * @param {Agent} agent - The agent data object.
 * @returns {HTMLDivElement} The constructed card element.
 */
function createAgentCardElement(agent) {
  const card = document.createElement("div");
  card.className = `agent-card ${agent.active ? "active" : ""}`;
  card.id = `agent-${agent.id}`;

  const statusText = agent.active
    ? window.t("status_active")
    : window.t("status_inactive");

  // Construct HTML layout
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

  // Safely inject text content to prevent XSS
  const titleEl = card.querySelector(".agent-title");
  titleEl.textContent = agent.name;
  titleEl.title = agent.name;

  const modelEl = card.querySelector(".model-value");
  if (agent.model) {
    modelEl.textContent = agent.model;
  } else {
    modelEl.innerHTML = `<i>${window.t("no_model")}</i>`;
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

  return card;
}

/**
 * Attaches a debounced event listener to the filter input.
 * Ensures the listener is attached only once.
 */
window.setupAgentFilterListener = () => {
  const filterInput = document.getElementById(DOM.FILTER_INPUT);
  if (filterInput && !isAgentFilterAttached) {
    filterInput.addEventListener(
      "input",
      window.debounce(filterAndDisplayAgents, 250)
    );
    isAgentFilterAttached = true;
  }
};

/**
 * Filters the cached agent list based on user input and updates the UI.
 */
function filterAndDisplayAgents() {
  const filterInput = document.getElementById(DOM.FILTER_INPUT);
  if (!filterInput) return;

  const query = filterInput.value.toLowerCase().trim();

  if (!query) {
    displayAgents(cachedAgentsList);
    return;
  }

  const filtered = cachedAgentsList.filter((agent) => {
    const nameMatch = agent.name && agent.name.toLowerCase().includes(query);
    const triggerMatch =
      agent.trigger && agent.trigger.toLowerCase().includes(query);
    return nameMatch || triggerMatch;
  });

  displayAgents(filtered);
}

// --- Modal Logic (Create / Edit) ---

/**
 * Opens the agent configuration modal.
 * Handles both creating a new agent (agentId=null) and editing an existing one.
 *
 * @param {string|null} [agentId=null] - The UUID of the agent to edit, or null to create.
 * @returns {Promise<void>}
 */
window.showAgentModal = async (agentId = null) => {
  const backdrop = document.getElementById(DOM.MODAL.BACKDROP);
  const title = document.getElementById(DOM.MODAL.TITLE);
  const saveBtn = document.getElementById(DOM.MODAL.SAVE_BTN);
  const nameInput = document.getElementById(DOM.MODAL.INPUT_NAME);
  const triggerInput = document.getElementById(DOM.MODAL.INPUT_TRIGGER);
  const promptInput = document.getElementById(DOM.MODAL.INPUT_PROMPT);
  const editIdInput = document.getElementById(DOM.MODAL.INPUT_ID);
  const autopasteToggle = document.getElementById(DOM.MODAL.TOGGLE_AUTOPASTE);
  const screenVisionToggle = document.getElementById(DOM.MODAL.TOGGLE_VISION);
  const feedbackEl = document.getElementById(DOM.MODAL.FEEDBACK);

  if (feedbackEl) feedbackEl.style.display = "none";
  if (!backdrop) return;

  // Reset form state
  editIdInput.value = "";
  nameInput.value = "";
  triggerInput.value = "";
  promptInput.value = "";
  nameInput.classList.remove("error");

  let agentModelToSelect = null;

  if (agentId) {
    // EDIT MODE
    const agent = cachedAgentsList.find((a) => a.id === agentId);
    if (agent) {
      currentEditingAgentId = agentId;
      editIdInput.value = agentId;
      title.textContent = window.t("modal_agent_edit_title");
      saveBtn.textContent = window.t("btn_save_changes");

      nameInput.value = agent.name || "";
      triggerInput.value = agent.trigger || "";
      promptInput.value = agent.prompt || "";
      agentModelToSelect = agent.model || "";
      autopasteToggle.checked = agent.autopaste !== false; // Default to true
      screenVisionToggle.checked = agent.screen_vision || false;
    }
  } else {
    // CREATE MODE
    currentEditingAgentId = null;
    title.textContent = window.t("modal_agent_create_title");
    saveBtn.textContent = window.t("btn_create_agent");

    if (window.isApiReady()) {
      try {
        agentModelToSelect = await window.pywebview.api.get_current_model();
      } catch (e) {
        console.error("[Agents] Failed to get current model:", e);
      }
    }
    autopasteToggle.checked = true;
    screenVisionToggle.checked = false;
  }

  // Populate model dropdown dynamically
  await window.populateModelDropdown(
    DOM.MODAL.SELECT_MODEL,
    agentModelToSelect
  );
  window.updateAgentModelAvailability();

  // Show Modal
  backdrop.style.display = "flex";
  // Small delay to allow CSS transition to trigger
  setTimeout(() => backdrop.classList.add("visible"), 10);
  nameInput.focus();
};

/**
 * Closes the agent modal with a fade-out animation.
 */
window.hideAgentModal = () => {
  const backdrop = document.getElementById(DOM.MODAL.BACKDROP);
  if (!backdrop) return;

  backdrop.classList.remove("visible");
  setTimeout(() => {
    backdrop.style.display = "none";
  }, 200);
  currentEditingAgentId = null;
};

/**
 * Validates form input and submits the agent data to the backend.
 * Handles both creation and updates.
 */
window.saveAgent = async () => {
  const nameInput = document.getElementById(DOM.MODAL.INPUT_NAME);
  const promptInput = document.getElementById(DOM.MODAL.INPUT_PROMPT);
  const triggerInput = document.getElementById(DOM.MODAL.INPUT_TRIGGER);
  const idInput = document.getElementById(DOM.MODAL.INPUT_ID);
  const modelSelect = document.getElementById(DOM.MODAL.SELECT_MODEL);
  const autopasteToggle = document.getElementById(DOM.MODAL.TOGGLE_AUTOPASTE);
  const visionToggle = document.getElementById(DOM.MODAL.TOGGLE_VISION);
  const saveBtn = document.getElementById(DOM.MODAL.SAVE_BTN);
  const feedbackEl = document.getElementById(DOM.MODAL.FEEDBACK);

  const name = nameInput.value.trim();
  const trigger = triggerInput.value.trim() || null;
  const prompt = promptInput.value.trim();
  const agentId = idInput.value;
  const model = modelSelect?.value || "";
  const autopaste = autopasteToggle.checked;
  const screenVision = visionToggle.checked;

  // Validation
  if (!name || !prompt) {
    if (feedbackEl) {
      feedbackEl.textContent = "Name and prompt are required.";
      feedbackEl.style.display = "block";
    }
    return;
  }

  const agentPayload = {
    id: agentId || null,
    name,
    trigger,
    prompt,
    model,
    autopaste,
    screen_vision: screenVision,
  };

  // Determine API method
  const apiCall = agentId
    ? window.pywebview.api.update_agent
    : window.pywebview.api.add_agent;

  // UI Feedback
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";

  try {
    const response = await apiCall(agentPayload);

    if (response && response.success) {
      window.hideAgentModal();
      window.loadAgents();
    } else {
      alert(`Error saving agent: ${response.error || "Unknown error"}`);
    }
  } catch (err) {
    console.error("[Agents] Save error:", err);
    alert("System error while saving agent.");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = window.t("btn_save");
  }
};

/**
 * Wrapper to open the modal in edit mode.
 * @param {string} agentId
 */
window.editAgent = (agentId) => {
  window.showAgentModal(agentId).catch(console.error);
};

// --- Deletion Logic ---

/**
 * Shows the confirmation modal for deleting an agent.
 * @param {string} agentId
 */
window.showDeleteAgentModal = (agentId) => {
  const backdrop = document.getElementById(DOM.DELETE_MODAL.BACKDROP);
  const textElement = document.getElementById(DOM.DELETE_MODAL.TEXT);
  const deleteIdInput = document.getElementById(DOM.DELETE_MODAL.INPUT_ID);

  const agent = cachedAgentsList.find((a) => a.id === agentId);

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

/**
 * Closes the delete confirmation modal.
 */
window.hideDeleteAgentModal = () => {
  const backdrop = document.getElementById(DOM.DELETE_MODAL.BACKDROP);
  if (!backdrop) return;

  backdrop.classList.remove("visible");
  setTimeout(() => {
    backdrop.style.display = "none";
    document.getElementById(DOM.DELETE_MODAL.INPUT_ID).value = "";
  }, 200);
};

/**
 * Confirms deletion via API call.
 */
window.confirmDeleteAgent = async () => {
  const agentId = document.getElementById(DOM.DELETE_MODAL.INPUT_ID).value;
  if (!window.isApiReady() || !agentId) return;

  try {
    const success = await window.pywebview.api.delete_agent(agentId);
    if (success) {
      window.hideDeleteAgentModal();
      window.loadAgents();
    } else {
      window.showToast("Failed to delete agent.", "error");
    }
  } catch (err) {
    console.error("[Agents] Delete error:", err);
    window.showToast("Error communicating with backend.", "error");
  }
};

// --- Activation / Toggles ---

/**
 * Toggles the active status of an agent.
 * @param {string} agentId
 * @param {boolean} isActive
 */
window.toggleAgentActive = async (agentId, isActive) => {
  if (!window.isApiReady()) return;

  try {
    const response = await window.pywebview.api.toggle_agent_status(
      agentId,
      isActive
    );

    if (response && response.success) {
      // Optimistic UI update or refresh
      const agentIndex = cachedAgentsList.findIndex((a) => a.id === agentId);
      if (agentIndex > -1) cachedAgentsList[agentIndex].active = isActive;
      window.loadAgents(); // Reload to ensure sync
    } else {
      console.warn("[Agents] Toggle failed, reverting UI.");
      window.loadAgents();
    }
  } catch (err) {
    console.error("[Agents] Toggle error:", err);
    window.loadAgents();
  }
};

/**
 * Handles the logic when the "Screen Vision" toggle is switched.
 * It attempts to auto-select a compatible multimodal model.
 *
 * @param {HTMLInputElement} checkboxElement
 */
window.handleAgentScreenVisionToggle = (checkboxElement) => {
  const isChecked = checkboxElement.checked;
  const itemsContainer = document.getElementById("agent-model-select-items");

  // Priority list of models known to support vision well
  const priorityMultimodalModels = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
  ];

  let newModelId = null;

  if (itemsContainer && isChecked) {
    // 1. Try to find a priority model in the available list
    for (const modelId of priorityMultimodalModels) {
      if (itemsContainer.querySelector(`div[data-value="${modelId}"]`)) {
        newModelId = modelId;
        break;
      }
    }

    // 2. If no priority model found, find ANY multimodal model
    if (!newModelId) {
      const fallback = itemsContainer.querySelector(
        'div[data-multimodal="true"]'
      );
      if (fallback) newModelId = fallback.dataset.value;
    }

    // 3. Update the dropdown selection if a better model was found
    if (newModelId) {
      window._updateCustomSelectDisplay(
        "custom-agent-model-select-container",
        newModelId
      );
    }
  }

  // Refresh UI states (disable incompatible options)
  window.updateAgentModelAvailability();
};
