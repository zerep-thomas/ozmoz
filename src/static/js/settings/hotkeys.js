/* --- src/static/js/settings/hotkeys.js --- */

// State variables for hotkey recording
let capturedHotkey = null;
let isCapturingHotkey = false;

/**
 * Opens the modal to record a new hotkey.
 * Disables global hotkeys in the backend while recording.
 * @param {HTMLElement} buttonElement - The button clicked (contains data-action).
 */
window.openHotkeyModal = (buttonElement) => {
  const action = buttonElement.getAttribute("data-action");
  const modal = document.getElementById("hotkey-modal-backdrop");
  const titleDisplay = document.getElementById("hotkey-action-name-display");
  const captureDisplay = document.getElementById("captured-hotkey-display");
  const saveButton = document.getElementById("hotkey-modal-save-btn");
  const actionNameInput = document.getElementById("hotkey-modal-action-name");

  if (!modal) return;

  // Temporarily disable app hotkeys so typing doesn't trigger them
  if (window.isApiReady()) {
    window.pywebview.api.temporarily_disable_all_hotkeys();
  }

  // Reset UI state
  titleDisplay.textContent = "";
  actionNameInput.value = action;
  capturedHotkey = null;
  isCapturingHotkey = true;

  captureDisplay.textContent = window.t("modal_waiting_input");
  captureDisplay.classList.add("placeholder");
  saveButton.disabled = true;

  // Show modal
  modal.style.display = "flex";
  setTimeout(() => modal.classList.add("visible"), 10);

  // Start listening for keystrokes
  document.addEventListener("keydown", window.handleHotkeyCapture);
};

/**
 * Event handler for keydown events during recording.
 * construct the hotkey string (e.g., "ctrl+alt+down").
 * @param {KeyboardEvent} event
 */
window.handleHotkeyCapture = (event) => {
  if (!isCapturingHotkey) return;
  event.preventDefault();
  event.stopPropagation();

  if (event.key === "Escape") {
    window.cancelHotkeyCapture();
    return;
  }

  const parts = [];

  if (event.ctrlKey) parts.push("ctrl");
  if (event.metaKey) parts.push("cmd");
  if (event.getModifierState("AltGraph")) {
    parts.push("altgr");
  } else if (event.altKey) {
    parts.push("alt");
  }
  if (event.shiftKey) parts.push("shift");

  const keyLocation = event.location;
  let keyName = event.key;
  let code = event.code;

  const modifiers = ["Control", "Alt", "Shift", "Meta", "AltGraph"];

  if (!modifiers.includes(keyName)) {
    const specialKeys = {
      ArrowDown: "down",
      ArrowUp: "up",
      ArrowLeft: "left",
      ArrowRight: "right",
      Enter: "enter",
      Backspace: "backspace",
      Tab: "tab",
      Space: "space",
      " ": "space",
      Escape: "esc",
      Delete: "delete",
      Insert: "insert",
      Home: "home",
      End: "end",
      PageUp: "pageup",
      PageDown: "pagedown",
      Pause: "pause",
      PrintScreen: "print_screen",
      ScrollLock: "scroll_lock",
      CapsLock: "caps_lock",
      NumLock: "num_lock",
    };

    if (/^F\d+$/.test(keyName)) {
      parts.push(keyName.toLowerCase());
    } else if (specialKeys[keyName]) {
      parts.push(specialKeys[keyName]);
    } else {
      if (keyName.length === 1) {
        parts.push(keyName.toLowerCase());
      } else if (code.startsWith("Numpad")) {
        parts.push(code.toLowerCase());
      } else {
        parts.push(keyName.toLowerCase());
      }
    }
  }

  // Suppression des doublons (au cas où) et assemblage
  const uniqueParts = [...new Set(parts)];

  // Update UI if we have a valid combination
  if (uniqueParts.length > 0) {
    capturedHotkey = uniqueParts.join("+");
    document.getElementById("captured-hotkey-display").textContent =
      capturedHotkey;
    document.getElementById("hotkey-modal-save-btn").disabled = false;
  }
};

/**
 * Saves the recorded hotkey to the backend configuration.
 */
window.saveCapturedHotkey = () => {
  const action = document.getElementById("hotkey-modal-action-name").value;
  if (!capturedHotkey || !action) return;

  document.removeEventListener("keydown", window.handleHotkeyCapture);
  isCapturingHotkey = false;

  if (window.isApiReady()) {
    window.pywebview.api.set_hotkey(action, capturedHotkey).then((res) => {
      if (res.success) {
        window.updateHotkeyDisplay(res.new_hotkeys);
        window.cancelHotkeyCapture(); // Close modal
      } else {
        alert("Error saving hotkey");
      }
    });
  }
};

/**
 * Cancels the recording process, closes the modal, and restores global hotkeys.
 */
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

/**
 * Updates the UI text elements with the currently configured hotkeys.
 * @param {Object} hotkeys - Dictionary of hotkeys {action: combination}.
 */
window.updateHotkeyDisplay = (hotkeys) => {
  if (!hotkeys) return;
  for (const [key, value] of Object.entries(hotkeys)) {
    const el = document.getElementById(`hotkey-display-${key}`);
    if (el) el.textContent = value;
  }
};

/**
 * Called when the Controls tab is opened to refresh hotkey display.
 */
window.initializeControlsTab = () => {
  console.log("Initializing Controls Tab");
  if (!window.isApiReady()) {
    const el = document.getElementById("hotkey-display-toggle_visibility");
    if (el) el.textContent = "Error";
    return;
  }
  window.pywebview.api.get_hotkeys().then((hotkeys) => {
    if (hotkeys) {
      window.updateHotkeyDisplay(hotkeys);
    }
  });
};
