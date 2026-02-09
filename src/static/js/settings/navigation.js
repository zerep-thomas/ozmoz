/* --- src/static/js/settings/navigation.js --- */

/**
 * Switches the active section in the main view (Sidebar navigation).
 * @param {string} sectionId - The ID of the section to show (e.g., 'home', 'general').
 */
window.setActiveSection = async (sectionId) => {
  // Update CSS classes for visibility
  document
    .querySelectorAll(".settings-section")
    .forEach((section) => section.classList.remove("active"));
  document
    .querySelectorAll(".sidebar-item")
    .forEach((item) => item.classList.remove("active"));

  const sectionElement = document.getElementById(sectionId);
  const sidebarItem = document.querySelector(
    `.sidebar-item[data-target="${sectionId}"]`
  );

  if (sectionElement) sectionElement.classList.add("active");
  if (sidebarItem) sidebarItem.classList.add("active");

  // Trigger specific logic based on the section
  if (sectionId === "logs") {
    window.loadLogs();
    window.startLogPolling();
  } else {
    window.stopLogPolling();
  }

  if (sectionId === "history") window.loadTranscripts();

  if (sectionId === "replacement") {
    window.loadReplacements();
    window.setupReplacementFilterListener();
  }

  if (sectionId === "agent") {
    window.loadAgents();
    window.setupAgentFilterListener();
  }

  if (sectionId === "home") {
    window.loadDashboardStats();
    window.loadActivityChartData();
  }

  if (sectionId === "general") {
    // Handle sub-tabs in General settings
    const activeTab = document.querySelector("#general .internal-tab.active");
    const tabName = activeTab ? activeTab.dataset.tab : "preferences";

    if (tabName === "api") window.loadApiConfiguration();
    if (tabName === "preferences") {
      await window.populateLanguageDropdown();
      await window.populateAudioModelDropdown();
      window.populateModelDropdown();
    }
    if (tabName === "controls") {
      window.initializeControlsTab();
    }
  }
};
