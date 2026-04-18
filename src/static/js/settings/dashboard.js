/* --- src/static/js/settings/dashboard.js --- */

let hasPlayedDashboardAnimation = false;

/**
 * Animates a numeric value element.
 * @param {HTMLElement} obj - The DOM element.
 * @param {number} start - Starting value.
 * @param {number} end - Ending value.
 * @param {number} duration - Animation duration in ms.
 * @param {string} suffix - Suffix to append (e.g., ' min').
 */
function animateValue(obj, start, end, duration, suffix = "") {
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    const currentVal = Math.floor(progress * (end - start) + start);
    obj.textContent = currentVal + suffix;
    if (progress < 1) {
      window.requestAnimationFrame(step);
    } else {
      obj.textContent = end + suffix;
    }
  };
  window.requestAnimationFrame(step);
}

/**
 * Loads dashboard statistics from the API.
 */
window.loadDashboardStats = () => {
  if (
    !window.isApiReady() ||
    typeof window.pywebview.api.get_dashboard_stats !== "function"
  ) {
    setTimeout(window.loadDashboardStats, 100);
    return;
  }

  window.pywebview.api
    .get_dashboard_stats()
    .then((stats) => {
      updateDashboardUI(stats);
    })
    .catch((err) => {
      console.error("Error loading dashboard stats:", err);
      updateDashboardUI({
        total_words: "0",
        average_speed: "0",
        time_saved: "0",
      });
    });
};

function updateDashboardUI(stats) {
  const wordsElement = document.getElementById("active-agents");
  const speedElement = document.getElementById("total-transcriptions");
  const savedElement = document.getElementById("total-replacements");

  const endValWords =
    parseInt(String(stats.total_words ?? "0").replace(/[^0-9]/g, ""), 10) || 0;
  const endValSpeed =
    parseInt(String(stats.average_speed ?? "0").replace(/[^0-9]/g, ""), 10) ||
    0;
  let displayValSaved = 0;
  let suffixSaved = window.t("unit_min");

  if (savedElement) {
    let rawTime = parseFloat(stats.time_saved ?? 0);
    if (isNaN(rawTime)) rawTime = 0;

    if (rawTime > 0 && rawTime < 1) {
      displayValSaved = Math.round(rawTime * 60);
      suffixSaved = window.t("unit_sec");
    } else {
      displayValSaved = Math.round(rawTime);
      suffixSaved = window.t("unit_min");
    }
  }

  const suffixSpeed = window.t("unit_mpm");

  if (
    !hasPlayedDashboardAnimation &&
    wordsElement &&
    speedElement &&
    savedElement
  ) {
    const animDuration = 1500;
    animateValue(wordsElement, 0, endValWords, animDuration, "");
    animateValue(speedElement, 0, endValSpeed, animDuration, suffixSpeed);
    animateValue(savedElement, 0, displayValSaved, animDuration, suffixSaved);
    hasPlayedDashboardAnimation = true;
  } else if (wordsElement && speedElement && savedElement) {
    wordsElement.textContent = endValWords;
    speedElement.textContent = endValSpeed + suffixSpeed;
    savedElement.textContent = displayValSaved + suffixSaved;
  }
}

/**
 * Loads and renders the activity chart.
 */
window.loadActivityChartData = () => {
  const periodToggle = document.getElementById("dashboard-period-toggle");
  const period = periodToggle && periodToggle.checked ? 7 : 30;
  const chartContainer = document.getElementById("activity-chart");
  if (!chartContainer) return;

  if (!window.isApiReady()) {
    console.log("API not ready for chart data, retrying...");
    setTimeout(window.loadActivityChartData, 200);
    return;
  }

  window.pywebview.api
    .get_activity_data(parseInt(period, 10))
    .then((response) => {
      renderActivityChart(response.data || {}, period, response.type || "line");
    })
    .catch((err) => {
      console.error("Error loading activity data:", err);
      renderActivityChart({}, period, "line", true);
    });
};

function renderActivityChart(
  data,
  period,
  chartType = "line",
  isError = false,
) {
  const chartContainer = document.getElementById("activity-chart");
  if (!chartContainer) return;

  let canvas = document.getElementById("activity-chart-canvas");
  if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.id = "activity-chart-canvas";
    chartContainer.innerHTML = "";
    chartContainer.appendChild(canvas);
  }
  const ctx = canvas.getContext("2d");

  if (isError) {
    chartContainer.textContent = "Error loading chart data.";
    chartContainer.style.color = "var(--color-red)";
    chartContainer.style.textAlign = "center";
    chartContainer.style.marginTop = "50px";
    return;
  }

  const dataValues = Object.values(data);
  const hasActualActivity =
    dataValues.length > 0 && dataValues.some((v) => v > 0);
  if (!hasActualActivity || Object.keys(data).length === 0) {
    chartContainer.innerHTML =
      '<p style="text-align:center; color: var(--dark-text-muted); margin-top: 50px;">No activity data available for this period.</p>';
    return;
  }

  const dates = Object.keys(data).sort();
  const currentLang = window.getCurrentLanguage();

  const labels = dates.map((dateStr) => {
    const dateObj = new Date(dateStr + "T00:00:00");
    return dateObj.toLocaleDateString(currentLang, {
      month: "short",
      day: "numeric",
    });
  });

  const originalValues = dates.map((date) => data[date]);

  const isLine = chartType === "line";

  let values;

  if (isLine) {
    const powerValues = originalValues.map((v) =>
      v > 0 ? Math.pow(v, 0.65) : null,
    );

    values = powerValues.map((v, i) => {
      if (v !== null) return v;

      let left = null,
        leftIdx = i - 1;
      while (leftIdx >= 0 && powerValues[leftIdx] === null) leftIdx--;
      if (leftIdx >= 0) left = powerValues[leftIdx];

      let right = null,
        rightIdx = i + 1;
      while (rightIdx < powerValues.length && powerValues[rightIdx] === null)
        rightIdx++;
      if (rightIdx < powerValues.length) right = powerValues[rightIdx];

      if (left !== null && right !== null) return (left + right) / 2;
      if (left !== null) return left;
      if (right !== null) return right;
      return 0;
    });
  } else {
    values = originalValues;
  }

  const chartHeight = chartContainer.offsetHeight;
  const gradient = ctx.createLinearGradient(0, chartHeight, 0, 0);

  if (isLine) {
    gradient.addColorStop(0, "rgba(156, 87, 247, 0)");
    gradient.addColorStop(1, "rgba(156, 87, 247, 0.12)");
  } else {
    gradient.addColorStop(0, "#9c57f7");
    gradient.addColorStop(1, "#b67cf7");
  }

  if (window.myActivityChart) {
    window.myActivityChart.destroy();
  }

  const initialData = values.map(() => 0);

  const backgroundColor = gradient;
  const borderRadius = isLine ? 0 : 6;
  const borderColor = isLine ? "#9c57f7" : "rgba(255, 255, 255, 0.4)";
  const borderWidth = isLine ? 2 : 1.5;
  const hoverRadius = isLine ? 6 : 0;

  window.myActivityChart = new Chart(ctx, {
    type: chartType,
    data: {
      labels: labels,
      datasets: [
        {
          label: window.t("chart_label_words"),
          data: initialData,
          fill: isLine,
          borderColor: borderColor,
          borderWidth: borderWidth,
          backgroundColor: backgroundColor,
          pointBackgroundColor: "#ffffff",
          pointBorderColor: "#9c57f7",
          pointBorderWidth: 2,
          pointRadius: 0,
          pointHitRadius: 15,
          pointHoverRadius: 6,
          pointHoverBackgroundColor: "#ffffff",
          pointHoverBorderColor: "#9c57f7",
          pointHoverBorderWidth: 3,
          tension: 0,
          borderCapStyle: "round",
          borderJoinStyle: "round",
          borderRadius: borderRadius,
          borderSkipped: false,
          spanGaps: true,
          barPercentage: 0.6,
          categoryPercentage: 0.7,
          clip: false,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: {
        padding: {
          left: isLine ? 0 : 20,
          right: isLine ? 0 : 20,
          top: 10,
        },
      },
      animation: { duration: 1200, easing: "easeOutQuart" },
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          display: true,
          offset: !isLine,
          grid: {
            display: true,
            color: "rgba(0, 0, 0, 0.04)",
            drawBorder: false,
            tickLength: 10,
          },
          ticks: {
            display: true,
            color: "rgba(29, 29, 29, 0.5)",
            font: { family: "OpenSauceSans", size: 11 },
            maxTicksLimit: 7,
            autoSkip: true,
            maxRotation: 0,
          },
          border: { display: false },
        },
        y: {
          display: true,
          beginAtZero: true,
          suggestedMax: 10,
          grace: "20%",
          border: { display: false },
          grid: {
            display: false,
          },
          ticks: {
            display: false,
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          backgroundColor: "#ffffff",
          titleColor: "#1d1d1d",
          bodyColor: "#1d1d1d",
          borderColor: "rgba(0,0,0,0.08)",
          borderWidth: 1,
          padding: 12,
          cornerRadius: 10,
          displayColors: false,
          titleFont: { family: "OpenSauceSans", size: 13, weight: "600" },
          bodyFont: { family: "OpenSauceSans", size: 13, weight: "500" },
          callbacks: {
            label: function (context) {
              const originalValue = originalValues[context.dataIndex];
              let label = context.dataset.label || "";
              if (label) label += ": ";
              if (originalValue !== null) label += originalValue;
              return label;
            },
          },
        },
        datalabels: { display: false },
      },
    },
  });

  setTimeout(() => {
    window.myActivityChart.data.datasets[0].data = values;
    window.myActivityChart.update();
  }, 50);
}

/**
 * Called by the Python backend when a new transcription is ready.
 * Updates both the dashboard stats and the history list in real-time.
 */
window.refreshDashboardFull = () => {
  console.log("Full dashboard refresh + History Sync requested...");
  window.loadDashboardStats();
  window.loadActivityChartData();

  // Real-time history update: Re-load transcripts to show the new entry immediately
  if (typeof window.loadTranscripts === "function") {
    window.loadTranscripts();
  }
};
