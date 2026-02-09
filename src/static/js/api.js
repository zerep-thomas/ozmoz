/* --- src/static/js/api.js --- */

/**
 * Wrapper object for Python-backend communication via pywebview.
 * Handles window management and external links.
 */
const API = {
  /**
   * Initiates a native window drag.
   */
  startDrag: () => {
    if (window.pywebview?.api) {
      window.pywebview.api.start_drag();
    }
  },

  /**
   * Drags the window by a relative amount.
   * @param {number} deltaX - Movement on X axis.
   * @param {number} deltaY - Movement on Y axis.
   */
  dragWindow: (deltaX, deltaY) => {
    if (window.pywebview?.api) {
      window.pywebview.api.drag_window(deltaX, deltaY);
    }
  },

  /**
   * Retrieves the current window position.
   * @returns {Promise<{x: number, y: number}>} - A promise resolving to the coordinates.
   */
  getWindowPos: () => {
    if (window.pywebview?.api) {
      return window.pywebview.api.getWindowPos();
    }
    return Promise.resolve({ x: 0, y: 0 });
  },

  /**
   * Resizes the application window.
   * @param {number} width - New width in pixels.
   * @param {number} height - New height in pixels.
   */
  resizeWindow: (width, height) => {
    if (window.pywebview?.api) {
      window.pywebview.api.resize_window(width, height);
    }
  },

  /**
   * Toggles the settings window visibility.
   */
  toggleSettings: () => {
    if (window.pywebview?.api) {
      window.pywebview.api.toggle_settings();
    }
  },

  /**
   * Opens a URL in the default system browser.
   * @param {string} url - The URL to open.
   */
  openExternalLink: (url) => {
    if (window.pywebview?.api) {
      window.pywebview.api.open_external_link(url);
    }
  },

  /**
   * Sets the visibility state of the AI response container in the backend.
   * @param {boolean} visible - True to show, false to hide.
   * @returns {Promise<void>}
   */
  setAiResponseVisible: (visible) => {
    if (window.pywebview?.api) {
      return window.pywebview.api.set_ai_response_visible(visible);
    }
    return Promise.resolve();
  },

  /**
   * Hides the main window completely.
   */
  hideWindow: () => {
    if (window.pywebview?.api) {
      window.pywebview.api.hide_window();
    }
  },
};
