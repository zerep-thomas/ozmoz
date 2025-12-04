/* --- static/js/settings/i18n.js --- */

let currentLanguage = "en";

window.getCurrentLanguage = () => currentLanguage;
window.setCurrentLanguage = (lang) => {
  currentLanguage = lang;
};

/**
 * Translates a key using the current language.
 * @param {string} key - The translation key.
 * @returns {string} Translated text or the key itself if not found.
 */
window.t = (key) => {
  if (window.locales?.[currentLanguage]?.[key]) {
    return window.locales[currentLanguage][key];
  }
  // Fallback to English
  if (window.locales?.["en"]?.[key]) {
    return window.locales["en"][key];
  }
  return key;
};

/**
 * Applies translations to the entire DOM.
 * @param {string} lang - The language code to apply.
 */
window.applyTranslations = (lang) => {
  const uiLang = window.locales?.[lang] ? lang : "en";
  currentLanguage = uiLang;

  // Text Content
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = window.t(el.getAttribute("data-i18n"));
  });

  // Placeholders
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = window.t(el.getAttribute("data-i18n-placeholder"));
  });

  // Update Toggle Buttons Labels (CSS content attributes)
  const periodLabel = document.querySelector(".dashboard-period-label");
  if (periodLabel) {
    periodLabel.setAttribute("data-on", window.t("dash_7_days"));
    periodLabel.setAttribute("data-off", window.t("dash_30_days"));
  }

  const sortLabel = document.querySelector(".history-sort-label");
  if (sortLabel) {
    sortLabel.setAttribute("data-on", window.t("sort_recent"));
    sortLabel.setAttribute("data-off", window.t("sort_old"));
  }

  // Chart update
  if (window.myActivityChart?.data?.datasets?.[0]) {
    window.myActivityChart.data.datasets[0].label =
      window.t("chart_label_words");
    window.myActivityChart.update();
  }
};
