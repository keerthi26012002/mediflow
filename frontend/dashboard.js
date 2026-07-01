// MediFlow AI v2.1 Dashboard Engine
const API_BASE = window.location.origin;
const WS_BASE = window.location.origin.replace(/^http/, 'ws');

let forecastChart = null;
let wsConnection = null;
let latestPredictions = null;
let selectedHorizon = "1h"; // default look-ahead horizon

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  setupChart();
  initWebSocket();
  
  // Initial fallback load
  refreshAllFallback();
  
  // Set up polling backup every 5 seconds
  setInterval(() => {
    if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
      refreshAllFallback();
    }
  }, 5000);
});

// Setup Chart.js line graph (Prophet 24h Trend)
function setupChart() {
  const ctx = document.getElementById('forecastChart').getContext('2d');
  
  forecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Forecasted Bed Occupancy (Prophet)',
          data: [],
          borderColor: '#06b6d4',
          borderWidth: 3,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: '#06b6d4',
          pointHoverRadius: 6,
          pointRadius: 3,
          fill: false,
          tension: 0.4
        },
        {
          label: 'Predicted Hourly Admissions',
          data: [],
          borderColor: '#3b82f6',
          borderWidth: 2,
          borderDash: [5, 5],
          pointBackgroundColor: '#3b82f6',
          pointRadius: 0,
          fill: false,
          tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { 
          display: true,
          labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
        },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.95)',
          titleFont: { family: 'Outfit', size: 13, weight: 'bold' },
          bodyFont: { family: 'Outfit', size: 12 },
          borderColor: 'rgba(255, 255, 255, 0.08)',
          borderWidth: 1
        }
      },
      scales: {
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.03)' },
          ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } },
          min: 0,
          max: 300
        },
        x: {
          grid: { display: false },
          ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 10 } }
        }
      }
    }
  });
}

// Client-side horizon tab selector
window.selectHorizon = function(horizon) {
  selectedHorizon = horizon;
  
  // Update button active classes
  const horizons = ["30m", "1h", "6h", "24h"];
  horizons.forEach(h => {
    const btn = document.getElementById(`btn-${h}`);
    if (btn) {
      if (h === horizon) {
        btn.style.background = "var(--accent-blue)";
        btn.style.color = "var(--bg-primary)";
        btn.style.fontWeight = "700";
      } else {
        btn.style.background = "transparent";
        btn.style.color = "var(--text-secondary)";
        btn.style.fontWeight = "600";
      }
    }
  });

  if (latestPredictions) {
    renderPredictions(latestPredictions, selectedHorizon);
  }
};

// Render multi-horizon prediction cards
function renderPredictions(preds, horizon) {
  // Target mappings to card elements
  const targets = {
    "beds_required": { id: "pred-beds", suffix: "", decimals: 0 },
    "icu_beds_required": { id: "pred-icu", suffix: "", decimals: 0 },
    "doctors_required": { id: "pred-docs", suffix: "", decimals: 0 },
    "nurses_required": { id: "pred-nurses", suffix: "", decimals: 0 },
    "oxygen_required": { id: "pred-oxygen", suffix: "%", decimals: 1 },
    "ventilators_required": { id: "pred-vents", suffix: "", decimals: 0 },
    "queue_required": { id: "pred-queue", suffix: "m", decimals: 0 },
    "ambulances_required": { id: "pred-ambulances", suffix: "", decimals: 0 },
    "load_required": { id: "pred-load", suffix: "", decimals: 1 },
    "pressure_required": { id: "pred-pressure", suffix: "", decimals: 1 },
    "availability_required": { id: "pred-availability", suffix: "", decimals: 0 }
  };

  for (const [key, config] of Object.entries(targets)) {
    const predVal = preds[key];
    const elVal = document.getElementById(config.id);
    const elCI = document.getElementById(`${config.id}-ci`);
    const elExp = document.getElementById(`${config.id}-exp`);
    
    if (predVal && predVal[horizon]) {
      const dataPoint = predVal[horizon];
      const val = dataPoint.value;
      const ci = dataPoint.ci;
      const exp = dataPoint.explanation;
      
      if (elVal) elVal.innerText = `${val.toFixed(config.decimals)}${config.suffix}`;
      if (elCI) elCI.innerText = `CI: [${ci[0]}${config.suffix}, ${ci[1]}${config.suffix}]`;
      if (elExp) elExp.innerText = exp;
    } else {
      if (elVal) elVal.innerText = "-";
      if (elCI) elCI.innerText = "CI: [0, 0]";
      if (elExp) elExp.innerText = "-";
    }
  }
}

// Unified state updater
function updateDashboardState(data) {
  if (!data) return;

  const timestamp = data.timestamp || new Date().toLocaleString();
  document.getElementById("current-sim-time").innerText = `Simulation Time: ${timestamp}`;

  // 1. Update Readiness KPI Ribbon
  if (data.capacity_metrics) {
    const metrics = data.capacity_metrics;
    document.getElementById("val-readiness").innerText = `${metrics.hospital_readiness_score}%`;
    document.getElementById("val-load-index").innerText = metrics.hospital_load_index;
    document.getElementById("val-capacity-score").innerText = metrics.capacity_score;
    
    const statusVal = document.getElementById("val-system-status");
    const statusTrend = document.getElementById("val-bottleneck");
    const statusCard = document.getElementById("metric-status");
    
    const bottleneck = metrics.bottleneck_detected || "NOMINAL";
    statusTrend.innerText = bottleneck;
    
    if (bottleneck !== "NOMINAL") {
      statusVal.innerText = "WARNING";
      statusCard.className = "glass-card metric-card card-status danger";
    } else {
      statusVal.innerText = "NOMINAL";
      statusCard.className = "glass-card metric-card card-status";
    }
  }

  // 2. Update Digital Twin Values
  if (data.digital_twin) {
    const twin = data.digital_twin;
    
    const generalBedsUtil = ((twin.general_beds_occupied / 300) * 100).toFixed(1);
    document.getElementById("twin-beds").innerText = `${twin.general_beds_occupied} / 300`;
    document.getElementById("twin-beds-sub").innerText = `${generalBedsUtil}% utilization`;

    const icuBedsUtil = ((twin.icu_beds_occupied / 50) * 100).toFixed(1);
    document.getElementById("twin-icu").innerText = `${twin.icu_beds_occupied} / 50`;
    document.getElementById("twin-icu-sub").innerText = `${icuBedsUtil}% utilization`;

    const docUtil = (((40 - twin.doctors_available) / 40) * 100).toFixed(1);
    document.getElementById("twin-docs").innerText = `${twin.doctors_available} / 40`;
    document.getElementById("twin-docs-sub").innerText = `${docUtil}% shift utilization`;

    const nurseUtil = (((80 - twin.nurses_available) / 80) * 100).toFixed(1);
    document.getElementById("twin-nurses").innerText = `${twin.nurses_available} / 80`;
    document.getElementById("twin-nurses-sub").innerText = `${nurseUtil}% shift utilization`;

    document.getElementById("twin-oxygen").innerText = `${twin.oxygen_utilization}%`;
    
    const ventUtil = (((25 - twin.ventilators_available) / 25) * 100).toFixed(1);
    document.getElementById("twin-vents").innerText = `${twin.ventilators_available} / 25`;
    document.getElementById("twin-vents-sub").innerText = `${ventUtil}% utilization`;

    document.getElementById("twin-ambulances").innerText = twin.ambulances_active;
    document.getElementById("twin-waiting").innerText = twin.patients_waiting;
  }

  // 3. Update Multi-Horizon Predictions
  if (data.predictions) {
    latestPredictions = data.predictions;
    renderPredictions(latestPredictions, selectedHorizon);

    // Update Prophet forecasting curves
    if (latestPredictions.forecast_24h && latestPredictions.forecast_24h.length > 0) {
      const labels = [];
      const bedOccupancies = [];
      const admissions = [];
      
      latestPredictions.forecast_24h.forEach(pt => {
        const d = new Date(pt.ts);
        labels.push(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        bedOccupancies.push(pt.predicted_occupancy);
        admissions.push(pt.admissions || 0);
      });

      forecastChart.data.labels = labels;
      forecastChart.data.datasets[0].data = bedOccupancies;
      forecastChart.data.datasets[1].data = admissions;
      forecastChart.update();
    }
  }

  // 4. Update Alerts feed
  if (data.alerts) {
    updateAlertsFeed(data.alerts);
  }

  // 5. Update Recommendations
  if (data.recommendations) {
    updateRecommendations(data.recommendations);
  }
}

function updateAlertsFeed(alerts) {
  const feed = document.getElementById("alert-feed");
  if (alerts.length === 0) {
    feed.innerHTML = `<div class="empty-alerts"><p>Listening for real-time warnings...</p></div>`;
    return;
  }

  feed.innerHTML = "";
  alerts.forEach(alert => {
    const alertItem = document.createElement("div");
    const sev = alert.severity ? alert.severity.toLowerCase() : "warning";
    alertItem.className = `alert-item ${sev}`;
    
    // Display all metadata parameters: time to overload, impact, recommended action
    alertItem.innerHTML = `
      <div class="alert-meta">
        <span class="alert-time">${alert.timestamp}</span>
        <span class="alert-badge">${alert.severity || "WARNING"}</span>
      </div>
      <div class="alert-desc" style="font-weight: 600;">${alert.message}</div>
      <div class="alert-desc" style="margin-top: 4px; font-size: 0.8rem; opacity: 0.85;">
        <strong>Impact:</strong> ${alert.predicted_impact || "None"} | <strong>Horizon:</strong> ${alert.estimated_time_until_overload || "Immediate"}
      </div>
      <div class="alert-desc" style="margin-top: 4px; font-size: 0.8rem; color: var(--accent-cyan);">
        <strong>Action Required:</strong> ${alert.recommended_action || "Monitor state."}
      </div>
    `;
    feed.appendChild(alertItem);
  });
}

function updateRecommendations(recs) {
  const feed = document.getElementById("recs-feed");
  if (recs.length === 0) {
    feed.innerHTML = `<div class="empty-alerts"><p>No active recommendations.</p></div>`;
    return;
  }

  feed.innerHTML = "";
  recs.forEach(rec => {
    const recItem = document.createElement("div");
    recItem.className = "rec-item";
    recItem.setAttribute("data-type", rec.recommendation_type);

    recItem.innerHTML = `
      <div class="rec-title" style="font-size: 0.95rem; font-weight: 700; color: #ffffff;">${rec.message}</div>
      <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px;">Category: ${rec.recommendation_type} | Confidence: ${Math.round(rec.confidence_score * 100)}%</div>
      <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 6px;"><strong>Reasoning:</strong> ${rec.reasoning}</div>
      <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 6px;"><strong>Expected Benefit:</strong> ${rec.expected_operational_benefit}</div>
      <div style="font-size: 0.8rem; color: var(--accent-cyan); font-weight: 600;"><strong>Est. Improvement:</strong> ${rec.estimated_improvement}</div>
      <button class="rec-btn" onclick="executeRecommendation(this, '${rec.recommendation_type}')">Acknowledge & Deploy</button>
    `;
    feed.appendChild(recItem);
  });
}

function executeRecommendation(btn, recType) {
  btn.innerText = "Deploying Protocol...";
  btn.style.opacity = 0.6;
  btn.disabled = true;
  setTimeout(() => {
    btn.innerText = "Protocol Active";
    btn.style.background = "var(--status-ok)";
    btn.style.color = "#ffffff";
    console.log(`Operational protocol deployed for: ${recType}`);
  }, 1000);
}

// WebSocket setup
function initWebSocket() {
  const wsStatus = document.getElementById("websocket-status");
  const wsUrl = `${WS_BASE}/live`;
  
  console.log(`Connecting WebSocket to ${wsUrl}...`);
  wsConnection = new WebSocket(wsUrl);
  
  wsConnection.onopen = () => {
    console.log("WebSocket connected.");
    wsStatus.innerText = "LIVE CONNECTION";
    wsStatus.style.color = "var(--status-ok)";
    document.getElementById("pulse-dot").style.backgroundColor = "var(--status-ok)";
    document.getElementById("connection-status").innerText = "Live Connected";
  };
  
  wsConnection.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateDashboardState(data);
  };
  
  wsConnection.onclose = () => {
    console.log("WebSocket disconnected. Retrying in 5 seconds...");
    wsStatus.innerText = "DISCONNECTED (POLLING BACKUP)";
    wsStatus.style.color = "var(--status-warn)";
    document.getElementById("pulse-dot").style.backgroundColor = "var(--status-warn)";
    document.getElementById("connection-status").innerText = "Polling Backup";
  };
  
  wsConnection.onerror = (err) => {
    console.error("WebSocket encountered error:", err);
  };
}

// Fallback HTTP polling values
async function refreshAllFallback() {
  try {
    const stateRes = await fetch(`${API_BASE}/hospital/state`);
    const capacityRes = await fetch(`${API_BASE}/capacity`);
    const predRes = await fetch(`${API_BASE}/prediction`);
    const alertsRes = await fetch(`${API_BASE}/alerts`);
    const recsRes = await fetch(`${API_BASE}/recommendations`);

    if (stateRes.ok && capacityRes.ok && predRes.ok) {
      const state = await stateRes.json();
      const capacity = await capacityRes.json();
      const predictions = await predRes.json();
      const alerts = alertsRes.ok ? await alertsRes.json() : [];
      const recommendations = recsRes.ok ? await recsRes.json() : [];

      const payload = {
        timestamp: state.timestamp,
        digital_twin: state,
        capacity_metrics: capacity,
        predictions: predictions,
        alerts: alerts,
        recommendations: recommendations
      };
      
      updateDashboardState(payload);
    }
  } catch (err) {
    console.error("Error running HTTP polling fallback:", err);
  }
}
