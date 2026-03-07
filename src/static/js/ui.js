/* --- src/static/js/ui.js --- */

const dh = document.getElementById("dragHandle");
let isDragging = false;

let dragDeltaX = 0;
let dragDeltaY = 0;
let animationFrameId = null;

if (dh) {
  dh.addEventListener("mousedown", (e) => {
    if (e.button === 0) {
      isDragging = true;
      dh.style.cursor = "grabbing";
      e.preventDefault();
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;

    dragDeltaX += e.movementX;
    dragDeltaY += e.movementY;

    if (!animationFrameId) {
      animationFrameId = requestAnimationFrame(() => {
        if (dragDeltaX !== 0 || dragDeltaY !== 0) {
          API.dragWindow(dragDeltaX, dragDeltaY);

          dragDeltaX = 0;
          dragDeltaY = 0;
        }
        animationFrameId = null;
      });
    }
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
    dh.style.cursor = "grab";
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
      dragDeltaX = 0;
      dragDeltaY = 0;
    }
  });
}

/**
 * Enables pointer events on the drag handle.
 */
function enableDrag() {
  if (dh) dh.style.pointerEvents = "auto";
}

/**
 * Disables pointer events on the drag handle (e.g. during text selection).
 */
function disableDrag() {
  if (dh) dh.style.pointerEvents = "none";
}

// --- Recording UI States ---

/**
 * Updates UI when recording starts.
 */
function handleStartRecordingEvent() {
  const btn = document.getElementById("record");
  const lbl = document.getElementById("record-label");
  const backBtn = document.getElementById("back-btn");
  const responseContainer = document.getElementById("ai-response-container");
  const visualizerContainer = document.getElementById("visualizer-container");

  if (responseContainer) responseContainer.style.display = "none";
  if (visualizerContainer) visualizerContainer.style.display = "flex";

  if (typeof startVisualizationOnly === "function") startVisualizationOnly();

  API.resizeWindow(415, 114);
  enableDrag();

  if (btn) btn.classList.add("recording");
  if (lbl) lbl.innerText = "Recording";

  if (backBtn) {
    backBtn.style.display = "none";
    backBtn.style.opacity = "1";
  }
}

/**
 * Updates UI when recording stops.
 */
function handleStopRecordingEvent() {
  const btn = document.getElementById("record");
  const lbl = document.getElementById("record-label");

  if (btn) btn.classList.remove("recording");
  if (lbl) lbl.innerText = "Record";

  if (typeof stopVisualizationOnly === "function") stopVisualizationOnly();
}

// --- AI Button States ---

/**
 * Updates the state of the AI button (labels, classes).
 * @param {string} state - 'recording', 'processing', 'success', or 'idle'.
 * @param {string} [mode="text"] - 'text', 'web', or 'vision'.
 */
function setAIButtonState(state, mode = "text") {
  const wrapper = document.getElementById("ask-ai");
  const label = document.getElementById("ai-label");
  const backBtn = document.getElementById("back-btn");

  if (!wrapper || !label) return;

  wrapper.classList.remove("asking");

  // Hide back button during active states
  if ((state === "recording" || state === "processing") && backBtn) {
    backBtn.style.opacity = "0";
    backBtn.style.pointerEvents = "none";
    backBtn.style.display = "none";
  }

  if (state === "recording") {
    wrapper.classList.add("asking");
    label.innerText = "Asking AI...";
  } else if (state === "processing") {
    wrapper.classList.add("asking");

    const labels = {
      web: "Searching",
      vision: "Analysing",
      default: "Thinking",
    };
    label.innerText = labels[mode] || labels.default;
  } else {
    label.innerText = "Ask AI";
  }
}

// --- Streaming & Markdown Rendering Logic ---

let fullStreamedResponse = "";
let isFirstChunk = true;
let renderInterval = null;

/**
 * Prepares the UI for incoming AI text stream.
 * @param {string} mode - The mode of generation (text, web, etc.).
 */
function setupStreamingUI(mode = "text") {
  fullStreamedResponse = "";
  isFirstChunk = true;
  if (renderInterval) clearInterval(renderInterval);

  const vizContainer = document.getElementById("visualizer-container");
  if (vizContainer) vizContainer.style.display = "none";

  const responseContainer = document.getElementById("ai-response-container");
  if (responseContainer) responseContainer.style.display = "flex";

  const backBtn = document.getElementById("back-btn");
  if (backBtn) backBtn.style.display = "none";

  setAIButtonState("processing", mode);
}

/**
 * Appends a new chunk of text to the buffer and starts rendering if needed.
 * @param {string} chunkText - The partial text received from backend.
 */
function appendaiStreamChunk(chunkText) {
  if (isFirstChunk && chunkText.trim().length > 0) {
    const responseContainer = document.getElementById("ai-response-container");
    if (responseContainer) {
      responseContainer.innerHTML = `<div class="ai-text"></div>`;
      isFirstChunk = false;
      // Start the render loop to avoid UI freezing on every chunk
      renderInterval = setInterval(updateRenderedContent, 200);
    }
  }
  fullStreamedResponse += chunkText;
}

// Alias for consistency (handling casing issues from backend calls)
const appendAiStreamChunk = appendaiStreamChunk;

/**
 * Renders the accumulated markdown text into HTML using markdown-it and KaTeX.
 */
function updateRenderedContent() {
  const textElement = document.querySelector(".ai-text");
  if (!textElement || fullStreamedResponse === null) return;

  // Optimize: Don't re-render if nothing changed
  if (textElement.dataset.lastRendered === fullStreamedResponse) return;

  // Escape specific characters for Latex compatibility within Markdown
  const protectedText = fullStreamedResponse
    .replace(/\\\(/g, "\\\\(")
    .replace(/\\\)/g, "\\\\)")
    .replace(/\\\[/g, "\\\\[")
    .replace(/\\\]/g, "\\\\]");

  // Configure Markdown parser
  const md = window.markdownit({
    html: false,
    linkify: true,
    breaks: true,
    highlight: (str, lang) => {
      if (lang && window.hljs?.getLanguage(lang)) {
        try {
          return `<pre class="hljs"><code>${
            window.hljs.highlight(str, { language: lang }).value
          }</code></pre>`;
        } catch (__) {}
      }
      return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
    },
  });

  const htmlContent = md.render(protectedText);
  textElement.innerHTML = `${htmlContent}<span class="cursor"></span>`;

  // Render Math (KaTeX)
  if (window.renderMathInElement) {
    window.renderMathInElement(textElement, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  }

  textElement.dataset.lastRendered = fullStreamedResponse;

  const container = document.getElementById("ai-response-container");
  if (container) container.scrollTop = container.scrollHeight;

  resizeWindowBasedOnContent();
}

/**
 * Finalizes the stream: stops the render loop, performs the last markdown render,
 * clears the sources section from any previous response, and shows the Back button.
 */
function finalizeStreamedContent() {
  if (renderInterval) clearInterval(renderInterval);

  // Remove any sources section from a previous response before rendering new content
  const existingSources = document.getElementById("web-sources-container");
  if (existingSources) existingSources.remove();

  fullStreamedResponse += "\n\n";

  const textElement = document.querySelector(".ai-text");

  if (textElement) {
    const protectedText = fullStreamedResponse
      .replace(/\\\(/g, "\\\\(")
      .replace(/\\\)/g, "\\\\)")
      .replace(/\\\[/g, "\\\\[")
      .replace(/\\\]/g, "\\\\]");

    const md = window.markdownit({
      html: false,
      linkify: true,
      highlight: (str, lang) => {
        if (lang && window.hljs?.getLanguage(lang)) {
          try {
            return `<pre class="hljs"><code>${
              window.hljs.highlight(str, { language: lang }).value
            }</code></pre>`;
          } catch (__) {}
        }
        return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
      },
    });

    textElement.innerHTML = md.render(protectedText);

    if (window.renderMathInElement) {
      window.renderMathInElement(textElement, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false },
          { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
      });
    }
  }

  // Reveal the Back button with a smooth fade-in
  const backBtn = document.getElementById("back-btn");
  if (backBtn) {
    backBtn.style.display = "flex";
    backBtn.style.pointerEvents = "auto";
    requestAnimationFrame(() => {
      backBtn.style.opacity = "1";
    });
  }

  setAIButtonState("success");
  resizeWindowBasedOnContent();
  disableDrag();
}

/**
 * Renders web search sources below the AI response as clickable chips.
 * Only called when the active model is a web search model (e.g. Groq Compound).
 * Sources are sorted by relevance score and capped at 5 entries.
 *
 * @param {Array<{title: string, url: string, score: number}>} sources
 */
function displayWebSources(sources) {
  if (!sources || sources.length === 0) return;

  const responseContainer = document.getElementById("ai-response-container");
  if (!responseContainer) return;

  // Remove any leftover sources section from a previous response
  const existing = document.getElementById("web-sources-container");
  if (existing) existing.remove();

  // --- Build the sources section ---
  const wrapper = document.createElement("div");
  wrapper.id = "web-sources-container";
  wrapper.className = "web-sources-container";

  const label = document.createElement("span");
  label.className = "web-sources-label";
  label.textContent = "Sources";
  wrapper.appendChild(label);

  const list = document.createElement("div");
  list.className = "web-sources-list";

  // Sort by descending score, keep the top 5 most relevant results
  const topSources = [...sources].sort((a, b) => b.score - a.score).slice(0, 5);

  topSources.forEach((source) => {
    const chip = document.createElement("button");
    chip.className = "web-source-chip";

    // Favicon fetched from Google's public favicon service
    const favicon = document.createElement("img");
    favicon.className = "web-source-favicon";
    try {
      const hostname = new URL(source.url).hostname;
      favicon.src = `https://www.google.com/s2/favicons?domain=${hostname}&sz=16`;
    } catch (_) {
      // Malformed URL — hide favicon gracefully
      favicon.style.display = "none";
    }
    favicon.onerror = () => (favicon.style.display = "none");

    // Truncate long titles to keep chips compact
    const title = document.createElement("span");
    title.className = "web-source-title";
    title.textContent =
      source.title.length > 32
        ? source.title.substring(0, 32) + "…"
        : source.title;

    chip.appendChild(favicon);
    chip.appendChild(title);

    // Open URL in the system default browser via the Python API bridge
    chip.addEventListener("click", () => {
      API.openExternalLink(source.url);
    });

    list.appendChild(chip);
  });

  wrapper.appendChild(list);
  responseContainer.appendChild(wrapper);

  // Recalculate window height to accommodate the new sources section
  resizeWindowBasedOnContent();
}

/**
 * Adjusts the window height dynamically based on the text content height.
 */
function resizeWindowBasedOnContent() {
  const textEl = document.querySelector(".ai-text");
  if (!textEl) return;

  const contentHeight = textEl.scrollHeight + 60;
  const minHeight = 150;
  const maxHeight = 400;
  const newHeight = Math.max(minHeight, Math.min(maxHeight, contentHeight));

  API.resizeWindow(415, newHeight);
}

// --- General UI Helpers ---

/**
 * Displays an error message in the UI for a short duration.
 * @param {string} message - The error message to display.
 */
function displayError(message) {
  const errCont = document.getElementById("error-container");
  const errMsg = document.getElementById("error-message");

  if (errCont && errMsg) {
    errMsg.innerText = message;
    errCont.style.display = "flex";
    setTimeout(() => {
      errCont.style.display = "none";
      resetUI();
      API.hideWindow();
    }, 3000);
  }
}

/**
 * Resets the UI to its initial state (Audio visualizer visible, AI response hidden).
 */
function resetUI() {
  API.setAiResponseVisible(false).then(() => {
    console.log("Context cleared via Back button");
  });

  const responseContainer = document.getElementById("ai-response-container");
  const visualizerContainer = document.getElementById("visualizer-container");
  const errorContainer = document.getElementById("error-container");
  const backBtn = document.getElementById("back-btn");

  if (responseContainer) responseContainer.style.display = "none";
  if (visualizerContainer) visualizerContainer.style.display = "flex";
  if (errorContainer) errorContainer.style.display = "none";

  if (backBtn) {
    backBtn.style.display = "none";
    backBtn.style.opacity = "1";
  }

  handleStopRecordingEvent();
  setAIButtonState("idle");

  API.resizeWindow(415, 114);
  enableDrag();
}

/**
 * Prepares UI specifically for a new AI generation (clears previous text).
 */
function resetUIForNewGeneration() {
  const backBtn = document.getElementById("back-btn");
  const responseContainer = document.getElementById("ai-response-container");
  const visualizerContainer = document.getElementById("visualizer-container");
  const textEl = document.querySelector(".ai-text");

  if (responseContainer) responseContainer.style.display = "none";
  if (visualizerContainer) visualizerContainer.style.display = "flex";
  if (textEl) textEl.innerHTML = "";

  if (backBtn) {
    backBtn.style.display = "none";
    backBtn.style.opacity = "1";
    backBtn.style.pointerEvents = "auto";
  }

  API.resizeWindow(415, 114);
  enableDrag();
}

/**
 * Wrapper to toggle settings via API.
 */
function toggleSettings() {
  API.toggleSettings();
}

/**
 * Sets the visual state of the settings button (enabled/disabled).
 * @param {boolean} busy - True if the app is busy.
 */
function setSettingsButtonState(busy) {
  const btn = document.getElementById("settings-btn");
  if (btn) {
    btn.classList.toggle("disabled", busy);
  }
}

/**
 * Updates UI based on license/auth status.
 * @param {string} status - The status code.
 */
function updateUIForLicenseStatus(status) {
  const indicators = document.querySelector(".indicators-container");
  if (indicators) {
    indicators.style.opacity = "1";
  }
}
