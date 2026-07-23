// MediFlow AI v2.2 Dashboard Engine
const API_BASE = window.location.origin;
const WS_BASE = window.location.origin.replace(/^http/, 'ws');

let forecastChart = null;
let wsConnection = null;
let latestPredictions = null;
let selectedHorizon = "1h"; // default look-ahead horizon
let activePredictionKey = "beds_required"; // default selected XAI metric

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  setupChart();
  initWebSocket();
  
  // Set up prediction tiles interactivity
  setupPredictionTiles();
  
  // Load initial configurations
  fetchPolicy();
  loadHistoricalData();
  
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
    renderExplanationPanel();
  }
};

// Bind click listeners to prediction tiles
function setupPredictionTiles() {
  const predictionKeys = {
    "pred-beds": "beds_required",
    "pred-icu": "icu_beds_required",
    "pred-docs": "doctors_required",
    "pred-nurses": "nurses_required",
    "pred-oxygen": "oxygen_required",
    "pred-vents": "ventilators_required",
    "pred-queue": "queue_required",
    "pred-ambulances": "ambulances_required",
    "pred-load": "load_required",
    "pred-pressure": "pressure_required",
    "pred-availability": "availability_required"
  };

  for (const [id, key] of Object.entries(predictionKeys)) {
    const element = document.getElementById(id);
    if (element) {
      const tile = element.parentNode;
      tile.style.cursor = "pointer";
      tile.addEventListener("click", () => {
        selectPredictionMetric(key);
      });
    }
  }
}

// Select a specific prediction tile to show XAI attributions
window.selectPredictionMetric = function(key) {
  activePredictionKey = key;
  
  const predictionKeys = {
    "beds_required": "pred-beds",
    "icu_beds_required": "pred-icu",
    "doctors_required": "pred-docs",
    "nurses_required": "pred-nurses",
    "oxygen_required": "pred-oxygen",
    "ventilators_required": "pred-vents",
    "queue_required": "pred-queue",
    "ambulances_required": "pred-ambulances",
    "load_required": "pred-load",
    "pressure_required": "pred-pressure",
    "availability_required": "pred-availability"
  };

  Object.entries(predictionKeys).forEach(([k, id]) => {
    const el = document.getElementById(id);
    if (el) {
      const tile = el.parentNode;
      if (k === key) {
        tile.style.border = "1px solid var(--accent-cyan)";
        tile.style.background = "rgba(6, 182, 212, 0.08)";
      } else {
        tile.style.border = "1px solid var(--card-border)";
        tile.style.background = "rgba(255, 255, 255, 0.025)";
      }
    }
  });

  renderExplanationPanel();
};

// Render explainable SHAP-like panel
function renderExplanationPanel() {
  const panel = document.getElementById("prediction-explanation-detail");
  if (!panel) return;

  if (!latestPredictions || !latestPredictions[activePredictionKey] || !latestPredictions[activePredictionKey][selectedHorizon]) {
    panel.style.display = "none";
    return;
  }

  panel.style.display = "block";
  const data = latestPredictions[activePredictionKey][selectedHorizon];
  
  const metricTitles = {
    "beds_required": "Beds Demand",
    "icu_beds_required": "ICU Bed Demand",
    "doctors_required": "Docs Needed",
    "nurses_required": "Nurses Needed",
    "oxygen_required": "Oxygen Demand",
    "ventilators_required": "Vents Needed",
    "queue_required": "ER Wait Time",
    "ambulances_required": "Ambulance Demand",
    "load_required": "Load Index",
    "pressure_required": "Pressure Index",
    "availability_required": "Beds Free"
  };

  document.getElementById("exp-metric-name").innerText = metricTitles[activePredictionKey] || activePredictionKey;
  document.getElementById("exp-confidence").innerText = `${data.confidence_score || 92.5}%`;
  document.getElementById("exp-reasoning").innerText = data.explanation || "No explanation available.";

  const shapBars = document.getElementById("exp-shap-bars");
  shapBars.innerHTML = "";

  const attributions = data.attributions || [];
  if (attributions.length === 0) {
    shapBars.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted);">Baseline historical factors only.</div>`;
    return;
  }

  attributions.forEach(attr => {
    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = "140px 1fr 45px";
    row.style.alignItems = "center";
    row.style.gap = "0.75rem";
    row.style.fontSize = "0.8rem";

    const barColor = attr.contribution === "positive" ? "hsl(350, 89%, 60%)" : "hsl(142, 70%, 45%)";
    const bgGradient = `linear-gradient(to right, ${barColor} ${attr.percentage}%, rgba(255,255,255,0.03) ${attr.percentage}%)`;

    row.innerHTML = `
      <span style="color: var(--text-secondary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${attr.display_name}</span>
      <div style="height: 0.5rem; background: ${bgGradient}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.03);"></div>
      <span style="text-align: right; font-weight: 700; color: ${barColor};">${attr.percentage}%</span>
    `;
    shapBars.appendChild(row);
  });
}

// Render multi-horizon prediction cards
function renderPredictions(preds, horizon) {
  const targets = {
    "beds_required": { id: "pred-beds", suffix: "", decimals: 0 },
    "icu_beds_required": { id: "pred-icu", suffix: "", decimals: 0 },
    "doctors_required": { id: "pred-docs", suffix: "", decimals: 0 },
    "nurses_required": { id: "pred-nurses", suffix: "", decimals: 0 },
    "oxygen_required": { id: "pred-oxygen", suffix: "%", decimals: 1 },
    "ventilators_required": { id: "pred-vents", suffix: "", decimals: 0 },
    "queue_required": { id: "pred-queue", suffix: " patients", decimals: 0 },
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
    renderExplanationPanel();

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

  // 6. Update Anomalies
  if (data.anomalies) {
    updateAnomaliesFeed(data.anomalies);
  }

  // 7. Update evaluations and model health metrics
  if (data.evaluations) {
    const latencyVal = data.predictions ? data.predictions.prediction_latency || 25.0 : 25.0;
    updateModelHealth(data.evaluations, latencyVal);
  }

  // 8. Update policy dropdown if synced
  if (data.active_policy) {
    const select = document.getElementById("select-policy");
    if (select) select.value = data.active_policy;
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
      <div class="rec-title" style="font-size: 0.95rem; font-weight: 700; color: #ffffff; display: flex; justify-content: space-between; align-items: center;">
        <span>${rec.message}</span>
        <span class="mini-badge" style="background: rgba(6, 182, 212, 0.15); border-color: var(--accent-cyan); color: var(--accent-cyan);">Benefit: ${rec.benefit_score || 50}</span>
      </div>
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

// Real-Time Anomaly Feed
function updateAnomaliesFeed(anomalies) {
  const feed = document.getElementById("anomaly-feed");
  if (!feed) return;

  if (!anomalies || anomalies.length === 0) {
    return;
  }

  if (feed.querySelector(".empty-alerts")) {
    feed.innerHTML = "";
  }

  anomalies.forEach(anom => {
    const existing = document.getElementById(`anom-${anom.timestamp}-${anom.metric_name}`);
    if (existing) return;

    const div = document.createElement("div");
    div.id = `anom-${anom.timestamp}-${anom.metric_name}`;
    div.className = "alert-item warning";
    div.style.borderLeft = "4px solid var(--status-danger)";
    div.style.background = "rgba(239, 68, 68, 0.04)";
    div.style.marginBottom = "0.55rem";
    div.style.padding = "0.6rem 0.8rem";
    div.style.borderRadius = "8px";

    div.innerHTML = `
      <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-muted); margin-bottom: 3px; font-weight: 600;">
        <span style="color: var(--status-danger);">⚠️ ANOMALY SENSOR: ${anom.metric_name.toUpperCase()}</span>
        <span>${anom.timestamp}</span>
      </div>
      <div style="font-size: 0.82rem; color: var(--text-primary); font-weight: 700;">${anom.description}</div>
      <div style="font-size: 0.74rem; color: var(--text-secondary); margin-top: 3px;">
        Observed: <strong>${anom.current_value}</strong> | Baseline Average: <strong>${anom.rolling_mean}</strong> (Std: ${anom.rolling_std})
      </div>
    `;
    feed.insertBefore(div, feed.firstChild);
  });

  while (feed.children.length > 20) {
    feed.removeChild(feed.lastChild);
  }
}

// Update model health performance statistics
function updateModelHealth(evaluations, latency) {
  if (evaluations && evaluations.regression && evaluations.regression["24h"]) {
    const reg = evaluations.regression["24h"];
    if (reg.beds_required && reg.beds_required["1h"]) {
      document.getElementById("val-mae-beds").innerText = `${reg.beds_required["1h"].mae.toFixed(1)} beds`;
    }
    if (reg.icu_beds_required && reg.icu_beds_required["1h"]) {
      document.getElementById("val-mae-icu").innerText = `${reg.icu_beds_required["1h"].mae.toFixed(1)} beds`;
    }
  }
  if (evaluations && evaluations.classification && evaluations.classification["24h"]) {
    const f1 = evaluations.classification["24h"].f1_score;
    document.getElementById("val-f1-admissions").innerText = f1.toFixed(3);
  }
  
  if (latency !== undefined) {
    document.getElementById("val-inference-latency").innerText = `${Math.round(latency)} ms`;
    const status = document.getElementById("val-latency-status");
    if (latency < 100) {
      status.innerText = "Healthy";
      status.style.color = "var(--status-ok)";
    } else if (latency < 300) {
      status.innerText = "Nominal";
      status.style.color = "var(--status-warn)";
    } else {
      status.innerText = "High Latency";
      status.style.color = "var(--status-danger)";
    }
  }
}

// Get/Post policies selector config
async function fetchPolicy() {
  try {
    const res = await fetch(`${API_BASE}/policies`);
    if (res.ok) {
      const data = await res.json();
      const select = document.getElementById("select-policy");
      if (select) select.value = data.policy;
    }
  } catch (err) {
    console.error("Error fetching policy:", err);
  }
}

window.changePolicy = async function(val) {
  try {
    const res = await fetch(`${API_BASE}/policies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy: val })
    });
    if (res.ok) {
      console.log(`Hospital policy changed to: ${val}`);
    }
  } catch (err) {
    console.error("Error changing active policy:", err);
  }
};

// Load initial historical records for anomalies and evaluations
async function loadHistoricalData() {
  try {
    const anomsRes = await fetch(`${API_BASE}/anomalies`);
    if (anomsRes.ok) {
      const anoms = await anomsRes.json();
      updateAnomaliesFeed(anoms);
    }
    
    const evalsRes = await fetch(`${API_BASE}/evaluations`);
    if (evalsRes.ok) {
      const evals = await evalsRes.json();
      updateModelHealth(evals);
    }
  } catch (err) {
    console.error("Error loading historical data:", err);
  }
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
