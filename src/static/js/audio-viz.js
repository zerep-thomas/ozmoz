/* --- src/static/js/audio-viz.js --- */

const NBR_OF_BARS = 80;
const visualizerContainer = document.getElementById("visualizer-container");
let isVisualizerRunning = false;

/**
 * Initializes the visualizer bars in the DOM.
 */
const initVisualizer = () => {
  if (!visualizerContainer) return;

  for (let i = 0; i < NBR_OF_BARS; i++) {
    const bar = document.createElement("div");
    bar.id = `bar${i}`;
    bar.className = "visualizer-container__bar";

    // Calculate initial opacity based on distance from center
    const centerIndex = NBR_OF_BARS / 2;
    const fadeFactor = Math.pow(
      1 - Math.abs(i - centerIndex) / (NBR_OF_BARS / 2),
      2.5
    );
    const opacity = 0.0 + (0.8 - 0.0) * fadeFactor;

    bar.style.backgroundColor = `rgba(255, 255, 255, ${opacity})`;
    bar.style.height = "1px";
    visualizerContainer.appendChild(bar);
  }
};

// Run initialization immediately
initVisualizer();

/**
 * Updates the visualizer bars based on audio frequency data.
 * @param {Array<number>} data - Array of frequency values.
 */
function updateVisualizer(data) {
  if (!isVisualizerRunning) return;

  // Use loop limit based on whichever is smaller: max bars or data length
  const limit = Math.min(NBR_OF_BARS, data.length);

  for (let i = 0; i < limit; i++) {
    const bar = document.getElementById(`bar${i}`);
    if (!bar) continue;

    const centerIndex = NBR_OF_BARS / 2;
    const fade = Math.pow(1 - Math.abs(i - centerIndex) / (NBR_OF_BARS / 2), 2);

    const maxCenter = 60;
    const maxEdge = 3;
    const dynamicMax = maxEdge + (maxCenter - maxEdge) * fade;

    // Calculate height with a clamp
    const height = Math.max(1, Math.min(data[i] * 1.2, dynamicMax));

    bar.style.transition = "height 0.1s linear";
    bar.style.height = `${height}px`;
  }
}

/**
 * Resets all visualizer bars to their resting state (1px height).
 */
function resetVisualizerBars() {
  for (let i = 0; i < NBR_OF_BARS; i++) {
    const bar = document.getElementById(`bar${i}`);
    if (bar) {
      bar.style.transition = "none";
      bar.style.height = "1px";
    }
  }
}

/**
 * Sets the visualizer state to running.
 */
function startVisualizationOnly() {
  isVisualizerRunning = true;
}

/**
 * Stops the visualizer and resets bars.
 */
function stopVisualizationOnly() {
  isVisualizerRunning = false;
  requestAnimationFrame(() => {
    resetVisualizerBars();
  });
}
