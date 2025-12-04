/* --- static/js/index.js --- */

/**
 * Main Entry Point
 * Initializes event listeners and handles global events.
 */

// --- Backend (PyWebView) Event Listeners ---
window.addEventListener("pywebview", (e) => {
  const msg = e.detail;
  if (msg === "start_recording") {
    handleStartRecordingEvent();
  } else if (msg === "stop_recording") {
    handleStopRecordingEvent();
  } else if (msg === "start_asking") {
    setAIButtonState("recording");
  } else if (msg === "stop_asking") {
    // No-op
  }
});

// Custom Event Listeners
document.addEventListener("start_recording", handleStartRecordingEvent);
document.addEventListener("stop_recording", handleStopRecordingEvent);

console.log("JS: Ready (Full Features)");

// --- DOM Interaction Listeners ---

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  const settingsBtn = document.getElementById("settings-btn");
  if (settingsBtn) {
    settingsBtn.addEventListener("click", toggleSettings);
  }

  const backBtn = document.getElementById("back-btn");
  if (backBtn) {
    backBtn.addEventListener("click", resetUI);
  }

  // Link Interception (Open links in external browser)
  document.body.addEventListener("click", (event) => {
    let target = event.target;
    // Traverse up to find the anchor tag
    while (target && target.tagName !== "A") {
      target = target.parentElement;
    }

    if (target && target.href) {
      event.preventDefault();
      API.openExternalLink(target.href);
    }
  });
});
