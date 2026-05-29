// Dashboard Client Engine
const API_BASE = window.location.origin;
const WS_BASE = window.location.origin.replace(/^http/, 'ws');

let forecastChart = null;
const DEPARTMENTS = ["Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics", "Self-Referral"];

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  setupChart();
  initWebSocket();
  
  // Initial load
  refreshDashboard();
  
  // Polling intervals (5 seconds for metrics & heatmap, 30 seconds for ML forecast)
  setInterval(refreshDashboard, 5000);
  setInterval(refreshForecast, 30000);
});

async function refreshDashboard() {
  await fetchLiveMetrics();
  await fetchHeatmapData();
}

async function refreshForecast() {
  await fetchForecastData();
}

// 1. Fetch live metrics
async function fetchLiveMetrics() {
  try {
    const res = await fetch(`${API_BASE}/dashboard/live`);
    if (!res.ok) throw new Error("Metrics endpoint failed");
    
    const data = await res.json();
    
    // Update elements
    document.getElementById("val-patients-hr").innerText = data.patients_per_hour;
    document.getElementById("val-icu-beds").innerText = data.icu_beds_free;
    document.getElementById("val-wait-time").innerHTML = `${data.avg_wait_time}<span style="font-size: 1rem; font-weight: 500; margin-left: 2px;">m</span>`;
    document.getElementById("current-sim-time").innerText = `Event Time: ${data.timestamp}`;
    
    // Update system status based on overload
    const statusCard = document.getElementById("metric-status");
    const statusVal = document.getElementById("val-system-status");
    const statusTrend = document.getElementById("trend-system-status");
    
    if (data.overload_status) {
      statusCard.classList.add("danger");
      statusVal.innerText = "OVERLOAD";
      statusTrend.innerText = `${data.active_alerts_count} alert(s) in the last hour`;
    } else {
      statusCard.classList.remove("danger");
      statusVal.innerText = "NOMINAL";
      statusTrend.innerText = "No active warnings";
    }
    
    document.getElementById("connection-status").innerText = "Live Connected";
  } catch (err) {
    console.error("Error fetching live metrics:", err);
    document.getElementById("connection-status").innerText = "Connection Lost";
  }
}

// 2. Setup Chart.js line graph
function setupChart() {
  const ctx = document.getElementById('forecastChart').getContext('2d');
  
  // Create gradient background
  const gradient = ctx.createLinearGradient(0, 0, 0, 300);
  gradient.addColorStop(0, 'rgba(6, 182, 212, 0.4)');
  gradient.addColorStop(1, 'rgba(59, 130, 246, 0.02)');
  
  forecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Predicted Occupancy',
        data: [],
        borderColor: '#06b6d4',
        borderWidth: 3,
        pointBackgroundColor: '#ffffff',
        pointBorderColor: '#06b6d4',
        pointHoverRadius: 7,
        pointRadius: 4,
        fill: true,
        backgroundColor: gradient,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.95)',
          titleFont: { family: 'Outfit', size: 13, weight: 'bold' },
          bodyFont: { family: 'Outfit', size: 12 },
          borderColor: 'rgba(255, 255, 255, 0.08)',
          borderWidth: 1,
          displayColors: false
        }
      },
      scales: {
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.03)' },
          ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } },
          min: 0,
          max: 55
        },
        x: {
          grid: { display: false },
          ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 10 } }
        }
      }
    }
  });
  
  // Fetch forecast right after setup
  refreshForecast();
}

// 3. Fetch Bed Forecast from API
async function fetchForecastData() {
  try {
    const res = await fetch(`${API_BASE}/forecast/beds?hours=24`);
    if (!res.ok) throw new Error("Forecast endpoint failed");
    
    const data = await res.json();
    
    // Update model badge
    document.getElementById("forecast-model-badge").innerText = data.model_loaded ? "Model: Prophet" : "Model: Stubbed";
    
    const labels = data.forecast.map(p => {
      // Return formatted time (e.g. 14:00)
      const date = new Date(p.ts);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });
    
    const occupancies = data.forecast.map(p => p.predicted_occupancy);
    
    forecastChart.data.labels = labels;
    forecastChart.data.datasets[0].data = occupancies;
    forecastChart.update();
  } catch (err) {
    console.error("Error fetching bed forecast:", err);
  }
}

// 4. WebSocket Client for Emergency Alerts
function initWebSocket() {
  const wsStatus = document.getElementById("websocket-status");
  const wsUrl = `${WS_BASE}/ws/alerts`;
  
  console.log(`Connecting WebSocket client to ${wsUrl}...`);
  let socket = new WebSocket(wsUrl);
  
  socket.onopen = () => {
    console.log("WebSocket connection established.");
    wsStatus.innerText = "WS Connected";
    wsStatus.style.borderColor = "rgba(34, 197, 94, 0.2)";
    wsStatus.style.color = "var(--status-ok)";
  };
  
  socket.onmessage = (event) => {
    const alert = JSON.parse(event.data);
    addAlertToFeed(alert);
  };
  
  socket.onclose = () => {
    console.log("WebSocket connection closed. Reconnecting in 5 seconds...");
    wsStatus.innerText = "WS Reconnecting";
    wsStatus.style.borderColor = "rgba(245, 158, 11, 0.2)";
    wsStatus.style.color = "var(--status-warn)";
    setTimeout(initWebSocket, 5000);
  };
  
  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

function addAlertToFeed(alert) {
  const feed = document.getElementById("alert-feed");
  
  // Remove empty container if present
  const empty = feed.querySelector(".empty-alerts");
  if (empty) {
    feed.innerHTML = "";
  }
  
  const alertItem = document.createElement("div");
  const severityClass = alert.severity ? alert.severity.toLowerCase() : "critical";
  alertItem.className = `alert-item ${severityClass}`;
  
  alertItem.innerHTML = `
    <div class="alert-meta">
      <span class="alert-time">${alert.timestamp}</span>
      <span class="alert-badge">${alert.severity || 'CRITICAL'}</span>
    </div>
    <div class="alert-desc">${alert.message}</div>
  `;
  
  // Prepend to show newest first
  feed.insertBefore(alertItem, feed.firstChild);
  
  // Keep size capped at 10 to protect memory
  while (feed.children.length > 10) {
    feed.removeChild(feed.lastChild);
  }
}

// 5. Fetch Heatmap Load Data
async function fetchHeatmapData() {
  try {
    const res = await fetch(`${API_BASE}/history/admissions?limit=100`);
    if (!res.ok) throw new Error("History admissions endpoint failed");
    
    const events = await res.json();
    if (events.length === 0) return;
    
    // Sort events by timestamp ascending
    events.sort((a, b) => {
      const partsA = a.timestamp.split(/[- :]/);
      const partsB = b.timestamp.split(/[- :]/);
      const dateA = new Date(partsA[2], partsA[1] - 1, partsA[0], partsA[3], partsA[4]);
      const dateB = new Date(partsB[2], partsB[1] - 1, partsB[0], partsB[3], partsB[4]);
      return dateA - dateB;
    });

    // Extract hours from the last 8 hours
    const latestEvent = events[events.length - 1];
    const parts = latestEvent.timestamp.split(/[- :]/);
    const latestDate = new Date(parts[2], parts[1] - 1, parts[0], parts[3], parts[4]);
    
    const hourBlocks = [];
    for (let i = 7; i >= 0; i--) {
      const d = new Date(latestDate.getTime() - i * 60 * 60 * 1000);
      d.setMinutes(0, 0, 0); // truncate to hour
      hourBlocks.push(d);
    }
    
    // Render headers
    const headerRow = document.getElementById("heatmap-time-headers");
    headerRow.innerHTML = `<th style="text-align: left; width: 180px;">Department</th>`;
    hourBlocks.forEach(h => {
      const headerStr = h.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      headerRow.innerHTML += `<th>${headerStr}</th>`;
    });
    
    // Process count matrix: { [dept]: { [hour_key]: count } }
    const matrix = {};
    DEPARTMENTS.forEach(dept => {
      matrix[dept] = {};
      hourBlocks.forEach(h => {
        const key = h.toISOString();
        matrix[dept][key] = 0;
      });
    });
    
    events.forEach(e => {
      const eParts = e.timestamp.split(/[- :]/);
      const eDate = new Date(eParts[2], eParts[1] - 1, eParts[0], eParts[3], eParts[4]);
      eDate.setMinutes(0, 0, 0);
      
      const key = eDate.toISOString();
      const dept = e.department || "Self-Referral";
      
      if (matrix[dept] && matrix[dept][key] !== undefined) {
        matrix[dept][key]++;
      }
    });
    
    // Build Heatmap Body rows
    const tbody = document.getElementById("heatmap-body");
    tbody.innerHTML = "";
    
    DEPARTMENTS.forEach(dept => {
      let rowHtml = `<tr><td class="heatmap-row-label">${dept}</td>`;
      
      hourBlocks.forEach(h => {
        const key = h.toISOString();
        const count = matrix[dept][key];
        
        let cellClass = "cell-empty";
        if (count > 0) {
          if (count === 1) cellClass = "cell-vlow";
          else if (count === 2) cellClass = "cell-low";
          else if (count <= 4) cellClass = "cell-mid";
          else if (count <= 6) cellClass = "cell-high";
          else cellClass = "cell-vhigh";
        }
        
        rowHtml += `<td class="${cellClass}" title="${dept} | Hourly Patients: ${count}">${count}</td>`;
      });
      
      rowHtml += "</tr>";
      tbody.innerHTML += rowHtml;
    });
    
  } catch (err) {
    console.error("Error drawing load heatmap:", err);
  }
}
