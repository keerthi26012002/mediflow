// MediFlow AI v2.3 Dashboard & RBAC Operations Engine
const API_BASE = window.location.origin;
const WS_BASE = window.location.origin.replace(/^http/, 'ws');

let currentUser = null;
let forecastChart = null;
let wsConnection = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let lastStreamSequence = -1;
let liveObservationBuffer = [];
let latestPredictions = null;
let selectedHorizon = "1h"; // default look-ahead horizon
let activePredictionKey = "beds_required"; // default selected XAI metric
let pollingInterval = null;

// ==================== AUTHENTICATION & SESSION MANAGEMENT ====================

function getAuthToken() {
  return localStorage.getItem("mediflow_token") || "";
}

function authHeaders(customHeaders = {}) {
  const token = getAuthToken();
  const headers = { ...customHeaders };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function apiFetch(url, options = {}) {
  options.headers = authHeaders(options.headers || {});
  options.credentials = "include";
  try {
    const res = await fetch(url, options);
    if (res.status === 401 && url.includes("/auth/me")) {
      handleLogout();
      throw new Error("Session expired or unauthorized.");
    }
    return res;
  } catch (err) {
    throw err;
  }
}

// ==================== THEME CONTROLLER (DARK / LIGHT MODE) ====================

function getStoredTheme() {
  try {
    const saved = localStorage.getItem("mediflow-theme");
    if (saved === "light" || saved === "dark") {
      return saved;
    }
  } catch (e) {
    console.warn("Unable to access localStorage for theme:", e);
  }
  return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
}

function getActiveTheme() {
  return document.documentElement.getAttribute("data-theme") || getStoredTheme();
}

window.toggleTheme = function() {
  const current = getActiveTheme();
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next, true);
};

function applyTheme(theme, save = true) {
  document.documentElement.setAttribute("data-theme", theme);
  if (save) {
    try {
      localStorage.setItem("mediflow-theme", theme);
    } catch (e) {
      console.warn("Unable to save theme preference:", e);
    }
  }

  const isDark = theme === "dark";
  const icon = isDark ? "🌙" : "☀️";
  const label = isDark ? "Dark Mode" : "Light Mode";
  const title = isDark ? "Switch to Light Mode" : "Switch to Dark Mode";

  document.querySelectorAll(".theme-toggle-btn").forEach(btn => {
    const iconEl = btn.querySelector(".theme-toggle-icon");
    const textEl = btn.querySelector(".theme-toggle-text");
    if (iconEl) iconEl.innerText = icon;
    if (textEl) textEl.innerText = label;
    btn.title = title;
    btn.setAttribute("aria-label", title);
  });

  updateChartsForTheme(theme);
}

function updateChartsForTheme(theme) {
  if (!forecastChart) return;
  const isDark = theme === "dark";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.08)";
  const tickColor = isDark ? "#94a3b8" : "#475569";
  const legendColor = isDark ? "#cbd5e1" : "#334155";
  const tooltipBg = isDark ? "rgba(15, 23, 42, 0.95)" : "rgba(255, 255, 255, 0.95)";
  const tooltipText = isDark ? "#ffffff" : "#0f172a";
  const tooltipBorder = isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.12)";

  if (forecastChart.options.scales && forecastChart.options.scales.x) {
    if (forecastChart.options.scales.x.grid) forecastChart.options.scales.x.grid.color = gridColor;
    if (forecastChart.options.scales.x.ticks) forecastChart.options.scales.x.ticks.color = tickColor;
  }
  if (forecastChart.options.scales && forecastChart.options.scales.y) {
    if (forecastChart.options.scales.y.grid) forecastChart.options.scales.y.grid.color = gridColor;
    if (forecastChart.options.scales.y.ticks) forecastChart.options.scales.y.ticks.color = tickColor;
  }
  if (forecastChart.options.plugins && forecastChart.options.plugins.legend && forecastChart.options.plugins.legend.labels) {
    forecastChart.options.plugins.legend.labels.color = legendColor;
  }
  if (forecastChart.options.plugins && forecastChart.options.plugins.tooltip) {
    forecastChart.options.plugins.tooltip.backgroundColor = tooltipBg;
    forecastChart.options.plugins.tooltip.bodyColor = tooltipText;
    forecastChart.options.plugins.tooltip.borderColor = tooltipBorder;
  }
  forecastChart.update('none');
}

// Listen for OS system theme changes when no manual override was set
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    try {
      if (!localStorage.getItem("mediflow-theme")) {
        applyTheme(e.matches ? "dark" : "light", false);
      }
    } catch (err) {}
  });
}

// Check session on page load
document.addEventListener("DOMContentLoaded", async () => {
  const initialTheme = getStoredTheme();
  applyTheme(initialTheme, false);
  setupChart();
  setupPredictionTiles();
  selectHorizon(selectedHorizon);
  await checkSession();
});

async function checkSession() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: authHeaders(),
      credentials: "include"
    });
    if (res.ok) {
      const user = await res.json();
      if (window.location.pathname === "/login" || window.location.hash === "#login") {
        window.location.href = "/dashboard";
        return;
      }
      setCurrentUser(user);
      startAuthenticatedDashboard();
    } else {
      showLoginScreen();
    }
  } catch (err) {
    showLoginScreen();
  }
}

function showLoginScreen() {
  const loginScreen = document.getElementById("login-screen");
  const appView = document.getElementById("app-view");
  if (loginScreen) loginScreen.style.display = "grid";
  if (appView) appView.style.display = "none";
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
  if (wsConnection) {
    wsConnection.close();
    wsConnection = null;
  }
  if (window.location.pathname === "/dashboard") {
    window.location.href = "/login";
  }
}

window.quickFillLogin = function(email, password) {
  const emailInput = document.getElementById("login-email");
  const passwordInput = document.getElementById("login-password");
  const errorEl = document.getElementById("login-error");
  if (emailInput) emailInput.value = email;
  if (passwordInput) passwordInput.value = password;
  if (errorEl) errorEl.innerText = "";
  handleLoginSubmit();
};

window.handleLoginSubmit = async function(event) {
  if (event && event.preventDefault) {
    event.preventDefault();
  }
  const emailInput = document.getElementById("login-email");
  const passwordInput = document.getElementById("login-password");
  const errorEl = document.getElementById("login-error");
  const btn = document.getElementById("login-btn");

  if (!emailInput || !passwordInput) return;
  const email = emailInput.value.trim();
  const password = passwordInput.value;

  if (errorEl) errorEl.innerText = "";
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Authenticating...";
  }

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password })
    });

    const data = await res.json();
    if (!res.ok) {
      if (errorEl) errorEl.innerText = data.detail || "Invalid login credentials.";
      if (btn) {
        btn.disabled = false;
        btn.innerText = "Sign In to Control Center";
      }
      return;
    }

    localStorage.setItem("mediflow_token", data.access_token);
    if (window.location.pathname === "/login" || window.location.hash === "#login") {
      window.location.href = "/dashboard";
      return;
    }
    setCurrentUser(data.user);
    startAuthenticatedDashboard();
  } catch (err) {
    if (errorEl) errorEl.innerText = "Connection error. Ensure backend server is running.";
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Sign In to Control Center";
    }
  }
};

window.handleLogout = async function() {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: authHeaders(),
      credentials: "include"
    });
  } catch (e) {
    console.warn("Logout error:", e);
  }
  localStorage.removeItem("mediflow_token");
  currentUser = null;
  window.location.href = "/login";
};

function setCurrentUser(user) {
  currentUser = user;
  const loginScreen = document.getElementById("login-screen");
  const appView = document.getElementById("app-view");
  if (loginScreen) loginScreen.style.display = "none";
  if (appView) appView.style.display = "block";

  const roleBadge = document.getElementById("user-role-badge");
  const emailDisplay = document.getElementById("user-email-display");
  const policyContainer = document.getElementById("policy-selector-container");
  const policySelect = document.getElementById("select-policy");
  
  const tabOverview = document.getElementById("tab-overview");
  const tabClinical = document.getElementById("tab-clinical");
  const tabOperations = document.getElementById("tab-operations");
  const tabAnalytics = document.getElementById("tab-analytics");
  const tabAdmin = document.getElementById("tab-admin");

  if (roleBadge) {
    roleBadge.innerText = user.role;
    roleBadge.className = `role-badge ${user.role.toLowerCase()}`;
  }
  if (emailDisplay) {
    emailDisplay.innerText = user.email;
  }

  // Enforce Policy Selector access
  if (policyContainer && policySelect) {
    if (user.role === "ADMIN" || user.role === "OPERATIONS_MANAGER") {
      policyContainer.style.display = "flex";
      policySelect.disabled = false;
      policySelect.title = "Authorized to update operational policy";
    } else {
      policyContainer.style.display = "none";
      policySelect.disabled = true;
      policySelect.title = "Restricted to ADMIN or OPERATIONS_MANAGER";
    }
  }

  // Adjust role navigation tabs according to permissions
  if (user.role === "ADMIN") {
    if (tabOverview) tabOverview.style.display = "inline-block";
    if (tabClinical) tabClinical.style.display = "inline-block";
    if (tabOperations) tabOperations.style.display = "inline-block";
    if (tabAnalytics) tabAnalytics.style.display = "inline-block";
    if (tabAdmin) tabAdmin.style.display = "inline-block";
    switchRoleView("admin");
  } else if (user.role === "DOCTOR") {
    if (tabOverview) tabOverview.style.display = "none";
    if (tabClinical) tabClinical.style.display = "inline-block";
    if (tabOperations) tabOperations.style.display = "none";
    if (tabAnalytics) tabAnalytics.style.display = "none";
    if (tabAdmin) tabAdmin.style.display = "none";
    switchRoleView("clinical");
  } else if (user.role === "OPERATIONS_MANAGER") {
    if (tabOverview) tabOverview.style.display = "inline-block";
    if (tabClinical) tabClinical.style.display = "none";
    if (tabOperations) tabOperations.style.display = "inline-block";
    if (tabAnalytics) tabAnalytics.style.display = "none";
    if (tabAdmin) tabAdmin.style.display = "none";
    switchRoleView("operations");
  } else if (user.role === "DATA_ANALYST") {
    if (tabOverview) tabOverview.style.display = "inline-block";
    if (tabClinical) tabClinical.style.display = "none";
    if (tabOperations) tabOperations.style.display = "none";
    if (tabAnalytics) tabAnalytics.style.display = "inline-block";
    if (tabAdmin) tabAdmin.style.display = "none";
    switchRoleView("analytics");
  } else {
    switchRoleView("overview");
  }
}

window.resetToAuthorizedWorkspace = function() {
  if (!currentUser) return;
  if (currentUser.role === "DOCTOR") switchRoleView("clinical");
  else if (currentUser.role === "OPERATIONS_MANAGER") switchRoleView("operations");
  else if (currentUser.role === "DATA_ANALYST") switchRoleView("analytics");
  else switchRoleView("admin");
};

window.switchRoleView = function(view) {
  if (!currentUser) return;
  const role = currentUser.role;

  // Authorization matrix for UI workspace views
  const allowedViews = {
    "ADMIN": ["overview", "clinical", "operations", "analytics", "admin"],
    "DOCTOR": ["clinical"],
    "OPERATIONS_MANAGER": ["operations", "overview"],
    "DATA_ANALYST": ["analytics", "overview"]
  };

  const isAllowed = allowedViews[role] && allowedViews[role].includes(view);

  document.querySelectorAll(".role-tab-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`tab-${view}`);
  if (activeBtn) activeBtn.classList.add("active");

  const unauthPanel = document.getElementById("unauthorized-panel");
  const adminPanel = document.getElementById("admin-user-mgmt-panel");
  const doctorPanel = document.getElementById("doctor-assessment-panel");
  const metricsStrip = document.querySelector(".metrics-strip");
  const twinPanel = document.getElementById("twin-panel");
  const predPanel = document.getElementById("predictions-panel");
  const chartPanel = document.getElementById("chart-panel");
  const recsPanel = document.getElementById("alert-recs-panel");
  const anomalyPanel = document.getElementById("anomaly-panel");
  const modelHealthPanel = document.getElementById("model-health-panel");
  const alertPanel = document.getElementById("alert-panel");

  const wsIcon = document.getElementById("ws-banner-icon");
  const wsTitle = document.getElementById("ws-banner-title");
  const wsSub = document.getElementById("ws-banner-subtitle");
  const wsRoleBadge = document.getElementById("ws-banner-role-badge");

  if (wsRoleBadge) {
    wsRoleBadge.innerText = currentUser.role;
    wsRoleBadge.className = `role-badge ${currentUser.role.toLowerCase()}`;
  }

  // If unauthorized view requested, display 403 fallback
  if (!isAllowed) {
    if (unauthPanel) unauthPanel.style.display = "block";
    const detailEl = document.getElementById("unauthorized-detail");
    if (detailEl) {
      detailEl.innerText = `Your authenticated role '${role}' does not have permission to access the '${view.toUpperCase()}' workspace.`;
    }
    if (adminPanel) adminPanel.style.display = "none";
    if (doctorPanel) doctorPanel.style.display = "none";
    if (metricsStrip) metricsStrip.style.display = "none";
    if (twinPanel) twinPanel.style.display = "none";
    if (predPanel) predPanel.style.display = "none";
    if (chartPanel) chartPanel.style.display = "none";
    if (recsPanel) recsPanel.style.display = "none";
    if (anomalyPanel) anomalyPanel.style.display = "none";
    if (modelHealthPanel) modelHealthPanel.style.display = "none";
    if (alertPanel) alertPanel.style.display = "none";
    return;
  }

  if (unauthPanel) unauthPanel.style.display = "none";

  if (view === "admin") {
    if (wsIcon) wsIcon.innerText = "🛡️";
    if (wsTitle) wsTitle.innerText = "Administrator Control Center — User & Policy Management";
    if (wsSub) wsSub.innerText = "Provision hospital users, audit authorization events, and control governance";
    
    if (adminPanel) adminPanel.style.display = "block";
    if (doctorPanel) doctorPanel.style.display = "none";
    if (metricsStrip) metricsStrip.style.display = "grid";
    if (twinPanel) twinPanel.style.display = "block";
    if (predPanel) predPanel.style.display = "block";
    if (chartPanel) chartPanel.style.display = "block";
    if (recsPanel) recsPanel.style.display = "block";
    if (anomalyPanel) anomalyPanel.style.display = "block";
    if (modelHealthPanel) modelHealthPanel.style.display = "block";
    if (alertPanel) alertPanel.style.display = "block";
    loadUsers();
    loadAuditLogs();
    window.scrollTo({ top: 0, behavior: "smooth" });

  } else if (view === "clinical") {
    if (wsIcon) wsIcon.innerText = "🩺";
    if (wsTitle) wsTitle.innerText = "Doctor Clinical Workspace — Triage Assessment & Admission Prediction";
    if (wsSub) wsSub.innerText = "Interactive XGBoost admission likelihood inference, ICU occupancy, and clinical alerts";

    if (adminPanel) adminPanel.style.display = "none";
    if (doctorPanel) doctorPanel.style.display = "block";
    if (metricsStrip) metricsStrip.style.display = "none";
    if (twinPanel) twinPanel.style.display = "block";
    if (predPanel) predPanel.style.display = "none";
    if (chartPanel) chartPanel.style.display = "none";
    if (recsPanel) recsPanel.style.display = "none";
    if (anomalyPanel) anomalyPanel.style.display = "none";
    if (modelHealthPanel) modelHealthPanel.style.display = "none";
    if (alertPanel) alertPanel.style.display = "block";
    window.scrollTo({ top: 0, behavior: "smooth" });

  } else if (view === "operations") {
    if (wsIcon) wsIcon.innerText = "📊";
    if (wsTitle) wsTitle.innerText = "Operations Manager Control Tower — Hospital Capacity & Logistics";
    if (wsSub) wsSub.innerText = "Bed availability, readiness scores, policy optimization, and AI recommendations";

    if (adminPanel) adminPanel.style.display = "none";
    if (doctorPanel) doctorPanel.style.display = "none";
    if (metricsStrip) metricsStrip.style.display = "grid";
    if (twinPanel) twinPanel.style.display = "block";
    if (predPanel) predPanel.style.display = "block";
    if (chartPanel) chartPanel.style.display = "block";
    if (recsPanel) recsPanel.style.display = "block";
    if (anomalyPanel) anomalyPanel.style.display = "none";
    if (modelHealthPanel) modelHealthPanel.style.display = "none";
    if (alertPanel) alertPanel.style.display = "block";
    window.scrollTo({ top: 0, behavior: "smooth" });

  } else if (view === "analytics") {
    if (wsIcon) wsIcon.innerText = "📈";
    if (wsTitle) wsTitle.innerText = "Data Analyst Workspace — MLOps Telemetry & Anomaly Analytics";
    if (wsSub) wsSub.innerText = "Prophet forecasting curves, rolling validation (MAE/RMSE/F1), and statistical outliers";

    if (adminPanel) adminPanel.style.display = "none";
    if (doctorPanel) doctorPanel.style.display = "none";
    if (metricsStrip) metricsStrip.style.display = "none";
    if (twinPanel) twinPanel.style.display = "none";
    if (predPanel) predPanel.style.display = "block";
    if (chartPanel) chartPanel.style.display = "block";
    if (recsPanel) recsPanel.style.display = "none";
    if (anomalyPanel) anomalyPanel.style.display = "block";
    if (modelHealthPanel) modelHealthPanel.style.display = "block";
    if (alertPanel) alertPanel.style.display = "none";
    window.scrollTo({ top: 0, behavior: "smooth" });

  } else {
    // Overview
    if (wsIcon) wsIcon.innerText = "🏥";
    if (wsTitle) wsTitle.innerText = "MediFlow AI Unified Operations Overview";
    if (wsSub) wsSub.innerText = "Real-time digital twin, predictive intelligence, and system-wide monitoring";

    if (adminPanel) adminPanel.style.display = "none";
    if (doctorPanel) doctorPanel.style.display = "none";
    if (metricsStrip) metricsStrip.style.display = (role === "ADMIN" || role === "OPERATIONS_MANAGER") ? "grid" : "none";
    if (twinPanel) twinPanel.style.display = (role === "ADMIN" || role === "DOCTOR" || role === "OPERATIONS_MANAGER") ? "block" : "none";
    if (predPanel) predPanel.style.display = (role === "ADMIN" || role === "OPERATIONS_MANAGER" || role === "DATA_ANALYST") ? "block" : "none";
    if (chartPanel) chartPanel.style.display = (role === "ADMIN" || role === "OPERATIONS_MANAGER" || role === "DATA_ANALYST") ? "block" : "none";
    if (recsPanel) recsPanel.style.display = (role === "ADMIN" || role === "OPERATIONS_MANAGER") ? "block" : "none";
    if (anomalyPanel) anomalyPanel.style.display = (role === "ADMIN" || role === "OPERATIONS_MANAGER" || role === "DATA_ANALYST") ? "block" : "none";
    if (modelHealthPanel) modelHealthPanel.style.display = (role === "ADMIN" || role === "DATA_ANALYST") ? "block" : "none";
    if (alertPanel) alertPanel.style.display = (role === "ADMIN" || role === "DOCTOR" || role === "OPERATIONS_MANAGER") ? "block" : "none";
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
};

function startAuthenticatedDashboard() {
  initWebSocket();
  fetchPolicy();
  loadHistoricalData();
  refreshAllFallback();

  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(() => {
    // Only poll as backup if WebSocket is not open
    if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
      refreshAllFallback();
    }
  }, 5000);
}

// ==================== ADMIN USER MANAGEMENT ====================

window.openCreateUserModal = function() {
  document.getElementById("create-user-modal").style.display = "block";
  document.getElementById("create-user-status").innerText = "";
};

window.closeCreateUserModal = function() {
  document.getElementById("create-user-modal").style.display = "none";
};

window.handleCreateUserSubmit = async function(event) {
  event.preventDefault();
  const email = document.getElementById("new-user-email").value.trim();
  const username = document.getElementById("new-user-username").value.trim();
  const password = document.getElementById("new-user-password").value;
  const role = document.getElementById("new-user-role").value;
  const statusEl = document.getElementById("create-user-status");

  statusEl.innerText = "Saving user...";
  statusEl.style.color = "var(--text-muted)";

  try {
    const res = await apiFetch(`${API_BASE}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, username, password, role, is_active: true })
    });

    const data = await res.json();
    if (!res.ok) {
      statusEl.innerText = data.detail || "Failed to create user.";
      statusEl.style.color = "var(--status-danger)";
      return;
    }

    statusEl.innerText = `User ${email} created successfully with role ${role}.`;
    statusEl.style.color = "var(--status-ok)";
    loadUsers();
    loadAuditLogs();
    setTimeout(() => { closeCreateUserModal(); }, 1500);
  } catch (err) {
    statusEl.innerText = "Error submitting user creation.";
    statusEl.style.color = "var(--status-danger)";
  }
};

async function loadUsers() {
  const tbody = document.getElementById("users-table-body");
  if (!tbody) return;
  try {
    const res = await apiFetch(`${API_BASE}/users`);
    if (!res.ok) return;
    const users = await res.json();
    tbody.innerHTML = "";
    users.forEach(u => {
      const tr = document.createElement("tr");
      const statusBadge = u.is_active 
        ? '<span style="color: var(--status-ok);">● Active</span>' 
        : '<span style="color: var(--status-danger);">○ Inactive</span>';
      
      const actionBtn = u.is_active
        ? `<button class="btn-sm btn-danger" onclick="toggleUserStatus('${u.id}', false)">Deactivate</button>`
        : `<button class="btn-sm btn-secondary" onclick="toggleUserStatus('${u.id}', true)">Reactivate</button>`;

      tr.innerHTML = `
        <td><strong>${u.username}</strong></td>
        <td>${u.email}</td>
        <td><span class="role-badge ${u.role.toLowerCase()}">${u.role}</span></td>
        <td>${statusBadge}</td>
        <td>${u.created_at ? u.created_at.substring(0, 10) : '-'}</td>
        <td>${actionBtn}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading users:", err);
  }
}

window.toggleUserStatus = async function(userId, newStatus) {
  try {
    const res = await apiFetch(`${API_BASE}/users/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: newStatus })
    });
    if (res.ok) {
      loadUsers();
      loadAuditLogs();
    }
  } catch (err) {
    console.error("Error updating user status:", err);
  }
};

window.loadAuditLogs = async function() {
  const tbody = document.getElementById("audit-table-body");
  if (!tbody) return;
  try {
    const res = await apiFetch(`${API_BASE}/audit/logs?limit=25`);
    if (!res.ok) return;
    const logs = await res.json();
    tbody.innerHTML = "";
    logs.forEach(l => {
      const tr = document.createElement("tr");
      const actor = l.actor_email || l.email || "system";
      const statusColor = l.status === "SUCCESS" ? "var(--status-ok)" : "var(--status-danger)";
      tr.innerHTML = `
        <td><small>${l.timestamp || '-'}</small></td>
        <td><strong>${l.event_type}</strong></td>
        <td>${actor}</td>
        <td><small>${l.role || '-'}</small></td>
        <td><span style="color: ${statusColor};">${l.status}</span></td>
        <td><small>${l.details || '-'}</small></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading audit logs:", err);
  }
};

// ==================== DOCTOR CLINICAL ASSESSMENT ====================

window.handlePatientPrediction = async function(event) {
  event.preventDefault();
  const patientId = document.getElementById("triage-patient-id").value;
  const age = parseInt(document.getElementById("triage-age").value);
  const gender = document.getElementById("triage-gender").value;
  const severity = parseInt(document.getElementById("triage-severity").value);
  const waitTime = parseInt(document.getElementById("triage-wait-time").value);
  const department = document.getElementById("triage-department").value;

  const payload = {
    patient_id: patientId,
    timestamp: new Date().toISOString(),
    age: age,
    gender: gender,
    wait_time: waitTime,
    department: department,
    emergency_severity_level: severity,
    icu_beds_available: 15,
    ambulance_requests: 1,
    doctor_availability: 10,
    oxygen_utilization: 65.0
  };

  try {
    const res = await apiFetch(`${API_BASE}/history/predict/admission`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      const data = await res.json();
      const card = document.getElementById("triage-result-card");
      card.style.display = "block";
      document.getElementById("res-patient-id").innerText = data.patient_id;
      
      const probaPct = (data.admission_proba * 100).toFixed(1) + "%";
      document.getElementById("res-proba").innerText = probaPct;
      
      const badge = document.getElementById("res-admission-badge");
      if (data.predicted_admission) {
        badge.innerText = "RECOMMEND ADMISSION";
        badge.className = "role-badge doctor";
        badge.style.color = "var(--status-warn)";
      } else {
        badge.innerText = "DISCHARGE / OUTPATIENT";
        badge.className = "role-badge data_analyst";
        badge.style.color = "var(--status-ok)";
      }
      
      document.getElementById("res-overload").innerText = data.admission_proba > 0.7 ? "HIGH SEVERITY" : "NORMAL";
      document.getElementById("res-ward").innerText = department;
    }
  } catch (err) {
    console.error("Error predicting admission:", err);
  }
};

// ==================== DASHBOARD CORE VISUALIZATION ====================

function setupChart() {
  const chartCanvas = document.getElementById('forecastChart');
  if (!chartCanvas) return;
  if (typeof Chart === 'undefined') {
    console.warn("Chart.js is not loaded yet.");
    return;
  }
  try {
    const isDark = getActiveTheme() === "dark";
    const gridColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.08)";
    const tickColor = isDark ? "#94a3b8" : "#475569";
    const legendColor = isDark ? "#cbd5e1" : "#334155";
    const tooltipBg = isDark ? "rgba(15, 23, 42, 0.95)" : "rgba(255, 255, 255, 0.95)";
    const tooltipText = isDark ? "#ffffff" : "#0f172a";
    const tooltipBorder = isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.12)";

    const ctx = chartCanvas.getContext('2d');
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
            pointBackgroundColor: isDark ? '#ffffff' : '#0891b2',
            pointBorderColor: '#06b6d4',
            pointHoverRadius: 6,
            pointRadius: 3,
            fill: false,
            tension: 0.4,
            yAxisID: 'y'
          },
          {
            label: 'Predicted Hourly Admissions',
            data: [],
            borderColor: '#3b82f6',
            borderWidth: 2,
            borderDash: [5, 5],
            pointBackgroundColor: '#3b82f6',
            pointBorderColor: '#3b82f6',
            pointHoverRadius: 6,
            pointRadius: 3,
            fill: false,
            tension: 0.4,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        scales: {
          x: {
            grid: { color: gridColor },
            ticks: { color: tickColor, font: { size: 12 } }
          },
          y: {
            type: 'linear',
            display: true,
            position: 'left',
            grid: { color: gridColor },
            ticks: { color: tickColor, font: { size: 12 } },
            title: {
              display: true,
              text: 'Occupancy (Beds)',
              color: '#06b6d4',
              font: { family: 'Inter', size: 12, weight: '600' }
            }
          },
          y1: {
            type: 'linear',
            display: true,
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { color: '#3b82f6', font: { size: 12 } },
            title: {
              display: true,
              text: 'Admissions / hr',
              color: '#3b82f6',
              font: { family: 'Inter', size: 12, weight: '600' }
            },
            min: 0
          }
        },
        plugins: {
          legend: {
            labels: { color: legendColor, font: { family: 'Inter', size: 13 } }
          },
          tooltip: {
            backgroundColor: tooltipBg,
            titleColor: '#06b6d4',
            titleFont: { family: 'Inter', size: 13, weight: '600' },
            bodyColor: tooltipText,
            bodyFont: { family: 'Inter', size: 12 },
            borderColor: tooltipBorder,
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: function(context) {
                const label = context.dataset.label || '';
                const val = Number(context.parsed.y);
                const unit = context.datasetIndex === 0 ? ' beds' : ' / hr';
                return `${label}: ${isNaN(val) ? '0.00' : val.toFixed(2)}${unit}`;
              }
            }
          }
        }
      }
    });
  } catch (err) {
    console.warn("Chart initialization skipped:", err);
  }
}

window.selectHorizon = function(horizon) {
  selectedHorizon = horizon;
  const buttons = ["30m", "1h", "6h", "24h"];
  buttons.forEach(h => {
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

window.selectPredictionMetric = function(key) {
  activePredictionKey = key;
  renderExplanationPanel();
};

function updateDashboardState(data) {
  if (!data) return;

  // Enforce monotonic sequence ordering: reject out-of-order stale payloads
  if (data.sequence !== undefined && data.sequence !== null) {
    if (data.sequence < lastStreamSequence) {
      console.warn(`[Stream] Dropping stale payload (seq ${data.sequence} < ${lastStreamSequence})`);
      return;
    }
    lastStreamSequence = data.sequence;
  }

  const simEl = document.getElementById("current-sim-time");
  if (simEl && data.timestamp) {
    const tickInfo = data.tick_id ? ` (Tick #${data.tick_id})` : (data.sequence ? ` (Seq #${data.sequence})` : "");
    simEl.innerText = `${data.timestamp}${tickInfo}`;
  }
  if (data.capacity_metrics) {
    updateReadinessStrip(data.capacity_metrics);
  }
  if (data.digital_twin) {
    updateDigitalTwin(data.digital_twin);
  }
  if (data.predictions) {
    latestPredictions = data.predictions;
    renderPredictions(data.predictions, selectedHorizon);
    renderExplanationPanel();
  }
  if (data.alerts) {
    updateAlertsFeed(data.alerts);
  }
  if (data.recommendations) {
    updateRecommendationsFeed(data.recommendations);
  }
  if (data.anomalies) {
    updateAnomaliesFeed(data.anomalies);
  }
  if (data.evaluations) {
    updateModelHealth(data.evaluations, data.inference_latency_ms);
  }
  if (data.forecast) {
    updateForecastChart(data.forecast);
  } else if (data.predictions && data.predictions.forecast_24h) {
    updateForecastChart(data.predictions.forecast_24h);
  }
}

function updateReadinessStrip(metrics) {
  document.getElementById("val-readiness").innerText = `${(metrics.hospital_readiness_score || 100).toFixed(1)}%`;
  document.getElementById("val-load-index").innerText = (metrics.hospital_load_index || 0.0).toFixed(2);
  document.getElementById("val-capacity-score").innerText = (metrics.capacity_score || 100.0).toFixed(1);
  
  const statusElem = document.getElementById("val-system-status");
  const bottleneckElem = document.getElementById("val-bottleneck");
  
  statusElem.innerText = metrics.bottleneck_detected || "NOMINAL";
  bottleneckElem.innerText = metrics.bottleneck_detected === "NOMINAL" ? "No bottlenecks detected" : `Bottleneck: ${metrics.bottleneck_detected}`;
  
  if (metrics.bottleneck_detected !== "NOMINAL") {
    statusElem.style.color = "var(--status-danger)";
  } else {
    statusElem.style.color = "var(--status-ok)";
  }
}

function updateDigitalTwin(twin) {
  document.getElementById("twin-beds").innerText = `${twin.general_beds_occupied || 0} / ${twin.general_beds_available || 300}`;
  const bedsUtil = Math.round(((twin.general_beds_occupied || 0) / (twin.general_beds_available || 300)) * 100);
  document.getElementById("twin-beds-sub").innerText = `${bedsUtil}% utilization`;

  document.getElementById("twin-icu").innerText = `${twin.icu_beds_occupied || 0} / ${twin.icu_beds_available || 50}`;
  const icuUtil = Math.round(((twin.icu_beds_occupied || 0) / (twin.icu_beds_available || 50)) * 100);
  document.getElementById("twin-icu-sub").innerText = `${icuUtil}% utilization`;

  document.getElementById("twin-docs").innerText = `${twin.doctors_available || 0} / ${twin.doctors_on_shift || 40}`;
  document.getElementById("twin-nurses").innerText = `${twin.nurses_available || 0} / ${twin.nurses_on_shift || 80}`;
  document.getElementById("twin-oxygen").innerText = `${(twin.oxygen_utilization || 0.0).toFixed(1)}%`;
  document.getElementById("twin-vents").innerText = `${twin.ventilators_available || 0} / 25`;
  document.getElementById("twin-ambulances").innerText = twin.ambulances_active || 0;
  document.getElementById("twin-waiting").innerText = twin.patients_waiting || 0;
}

function renderPredictions(preds, horizon) {
  if (!preds) return;

  const getH = (key, defaultVal = 0.0) => {
    if (preds && preds[key] !== undefined) {
      const targetObj = preds[key];
      // If direct numeric (e.g. flat fallback)
      if (typeof targetObj === "number") return targetObj;
      
      // If structured by horizon
      if (targetObj && typeof targetObj === "object") {
        const hObj = targetObj[horizon];
        if (hObj !== undefined) {
          if (typeof hObj === "number") return hObj;
          if (hObj && typeof hObj === "object" && hObj.value !== undefined) {
            return Number(hObj.value) || defaultVal;
          }
        }
        // Fallback to first available horizon if selected horizon missing
        for (const h of ["1h", "30m", "6h", "24h"]) {
          if (targetObj[h] !== undefined) {
            if (typeof targetObj[h] === "number") return targetObj[h];
            if (targetObj[h] && typeof targetObj[h] === "object" && targetObj[h].value !== undefined) {
              return Number(targetObj[h].value) || defaultVal;
            }
          }
        }
      }
    }
    return defaultVal;
  };

  const getCI = (key) => {
    if (preds && preds[key] && typeof preds[key] === "object") {
      const hObj = preds[key][horizon];
      if (hObj && typeof hObj === "object") {
        if (Array.isArray(hObj.ci) && hObj.ci.length >= 2) {
          return `CI: [${Number(hObj.ci[0]).toFixed(1)}, ${Number(hObj.ci[1]).toFixed(1)}]`;
        }
      }
    }
    if (preds && preds.confidence_intervals && preds.confidence_intervals[key] && preds.confidence_intervals[key][horizon]) {
      const ci = preds.confidence_intervals[key][horizon];
      if (Array.isArray(ci)) return `CI: [${Number(ci[0]).toFixed(1)}, ${Number(ci[1]).toFixed(1)}]`;
      if (ci && ci.lower !== undefined) return `CI: [${Number(ci.lower).toFixed(1)}, ${Number(ci.upper).toFixed(1)}]`;
    }
    return "CI: [Nominal]";
  };

  const getExp = (key) => {
    if (preds && preds[key] && typeof preds[key] === "object") {
      const hObj = preds[key][horizon];
      if (hObj && typeof hObj === "object" && hObj.explanation) {
        return hObj.explanation;
      }
    }
    return "";
  };

  const setCard = (valId, ciId, expId, val, ciStr, expStr) => {
    const elVal = document.getElementById(valId);
    const elCi = document.getElementById(ciId);
    const elExp = document.getElementById(expId);
    if (elVal) elVal.innerText = val;
    if (elCi) elCi.innerText = ciStr;
    if (elExp && expStr) elExp.innerText = expStr;
  };

  setCard("pred-beds", "pred-beds-ci", "pred-beds-exp", getH("beds_required").toFixed(1), getCI("beds_required"), getExp("beds_required"));
  setCard("pred-icu", "pred-icu-ci", "pred-icu-exp", getH("icu_beds_required").toFixed(1), getCI("icu_beds_required"), getExp("icu_beds_required"));
  setCard("pred-docs", "pred-docs-ci", "pred-docs-exp", getH("doctors_required").toFixed(1), getCI("doctors_required"), getExp("doctors_required"));
  setCard("pred-nurses", "pred-nurses-ci", "pred-nurses-exp", getH("nurses_required").toFixed(1), getCI("nurses_required"), getExp("nurses_required"));
  setCard("pred-oxygen", "pred-oxygen-ci", "pred-oxygen-exp", `${getH("oxygen_required").toFixed(1)}%`, getCI("oxygen_required"), getExp("oxygen_required"));
  setCard("pred-vents", "pred-vents-ci", "pred-vents-exp", getH("ventilators_required").toFixed(1), getCI("ventilators_required"), getExp("ventilators_required"));
  setCard("pred-queue", "pred-queue-ci", "pred-queue-exp", getH("queue_required").toFixed(1), getCI("queue_required"), getExp("queue_required"));
  setCard("pred-ambulances", "pred-ambulances-ci", "pred-ambulances-exp", getH("ambulances_required").toFixed(1), getCI("ambulances_required"), getExp("ambulances_required"));
  setCard("pred-load", "pred-load-ci", "pred-load-exp", getH("load_required").toFixed(2), getCI("load_required"), getExp("load_required"));
  setCard("pred-pressure", "pred-pressure-ci", "pred-pressure-exp", getH("pressure_required").toFixed(2), getCI("pressure_required"), getExp("pressure_required"));
  setCard("pred-availability", "pred-availability-ci", "pred-availability-exp", getH("availability_required").toFixed(1), getCI("availability_required"), getExp("availability_required"));
}

function renderExplanationPanel() {
  const panel = document.getElementById("prediction-explanation-detail");
  if (!panel || !latestPredictions) return;

  const targetData = latestPredictions[activePredictionKey];
  let horizonData = null;
  if (targetData && typeof targetData === "object") {
    horizonData = targetData[selectedHorizon] || targetData["1h"] || targetData["30m"] || targetData;
  }

  if (!horizonData && latestPredictions.explanations) {
    horizonData = latestPredictions.explanations[activePredictionKey];
  }

  if (!horizonData) {
    panel.style.display = "none";
    return;
  }

  panel.style.display = "block";
  document.getElementById("exp-metric-name").innerText = activePredictionKey.replace(/_/g, " ").toUpperCase() + ` (${selectedHorizon.toUpperCase()})`;
  
  const conf = horizonData.confidence_score !== undefined ? horizonData.confidence_score : ((horizonData.confidence || 0.9) * 100);
  document.getElementById("exp-confidence").innerText = `${Math.round(conf)}%`;
  document.getElementById("exp-reasoning").innerText = horizonData.explanation || horizonData.reasoning || "Multivariate XGBoost regression model inference.";

  const barsContainer = document.getElementById("exp-shap-bars");
  barsContainer.innerHTML = "";

  const attributions = horizonData.attributions || horizonData.feature_importance || [];
  if (attributions.length === 0) {
    barsContainer.innerHTML = '<div style="font-size: 0.845rem; color: var(--text-muted); padding: 4px 0;">Feature weights nominal for current operational state.</div>';
    return;
  }

  attributions.slice(0, 6).forEach(feat => {
    const barWrap = document.createElement("div");
    const val = feat.percentage !== undefined ? feat.percentage : (feat.weight !== undefined ? feat.weight * 100 : 10);
    const weightPct = Math.min(100, Math.max(5, Math.abs(val))).toFixed(0);
    const isPositive = feat.contribution === "positive" || val >= 0;
    const color = isPositive ? "var(--accent-blue)" : "var(--status-danger)";
    const name = feat.display_name || feat.feature || "Feature";
    const displayVal = feat.percentage !== undefined ? `${isPositive ? '+' : ''}${feat.percentage.toFixed(1)}%` : (feat.weight !== undefined ? `${isPositive ? '+' : ''}${feat.weight.toFixed(3)}` : "");

    barWrap.innerHTML = `
      <div style="display: flex; justify-content: space-between; font-size: 0.845rem; margin-bottom: 2px;">
        <span style="color: var(--text-secondary);">${name}</span>
        <span style="color: ${color}; font-weight: 600;">${displayVal}</span>
      </div>
      <div style="background: var(--panel-subtle); height: 4px; border-radius: 2px; overflow: hidden;">
        <div style="background: ${color}; width: ${weightPct}%; height: 100%; transition: width 0.3s ease;"></div>
      </div>
    `;
    barsContainer.appendChild(barWrap);
  });
}

function updateForecastChart(forecastPoints) {
  if (!forecastChart) {
    setupChart();
  }
  if (!forecastChart || !forecastPoints || forecastPoints.length === 0) return;
  
  forecastChart.data.labels = forecastPoints.map(p => {
    if (p.hour) return p.hour;
    if (p.timestamp && typeof p.timestamp === "string" && p.timestamp.length <= 8) return p.timestamp;
    if (p.ts) {
      const parts = String(p.ts).split(" ");
      return parts.length > 1 ? parts[1] : String(p.ts);
    }
    if (p.ds) {
      const parts = String(p.ds).split("T");
      if (parts.length > 1) return parts[1].substring(0, 5);
      const spaceParts = String(p.ds).split(" ");
      if (spaceParts.length > 1) return spaceParts[1].substring(0, 5);
      return String(p.ds);
    }
    return String(p.timestamp || "");
  });

  forecastChart.data.datasets[0].data = forecastPoints.map(p => {
    if (p.occupancy !== undefined && p.occupancy !== null) return Number(p.occupancy);
    if (p.predicted_occupancy !== undefined && p.predicted_occupancy !== null) return Number(p.predicted_occupancy);
    if (p.yhat !== undefined && p.yhat !== null) return Number(p.yhat);
    return 0;
  });

  forecastChart.data.datasets[1].data = forecastPoints.map(p => {
    if (p.inflow !== undefined && p.inflow !== null) return Number(p.inflow);
    if (p.predicted_inflow !== undefined && p.predicted_inflow !== null) return Number(p.predicted_inflow);
    if (p.admissions !== undefined && p.admissions !== null) return Number(p.admissions);
    return 0;
  });

  forecastChart.update();
}

function updateAlertsFeed(alerts) {
  const feed = document.getElementById("alert-feed");
  if (!feed) return;
  if (!alerts || alerts.length === 0) {
    feed.innerHTML = '<div class="empty-alerts"><p>No active hospital overload warnings.</p></div>';
    return;
  }
  feed.innerHTML = "";
  alerts.forEach(a => {
    const item = document.createElement("div");
    item.className = "alert-item";
    item.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <strong style="color: var(--status-danger); font-size: 0.945rem;">${a.title || a.alert_type || 'ALERT'}</strong>
        <small style="color: var(--text-muted); font-size: 0.825rem;">${a.timestamp || ''}</small>
      </div>
      <div style="font-size: 0.885rem; color: var(--text-secondary); margin-top: 2px;">${a.message}</div>
    `;
    feed.appendChild(item);
  });
}

function updateRecommendationsFeed(recs) {
  const feed = document.getElementById("recs-feed");
  if (!feed) return;
  if (!recs || recs.length === 0) {
    feed.innerHTML = '<div class="empty-alerts"><p>Operational metrics nominal; no actions required.</p></div>';
    return;
  }
  feed.innerHTML = "";
  recs.forEach(r => {
    const item = document.createElement("div");
    item.className = "rec-item";
    item.innerHTML = `
      <div class="rec-title">${r.title || r.type}</div>
      <div style="font-size: 0.875rem; color: var(--text-secondary);">${r.reason || ''}</div>
      <div class="rec-actions">
        ${(r.actions || []).map(act => `<div class="rec-action-item">${act}</div>`).join("")}
      </div>
    `;
    feed.appendChild(item);
  });
}

function updateAnomaliesFeed(anomalies) {
  const feed = document.getElementById("anomaly-feed");
  if (!feed) return;
  if (!anomalies || anomalies.length === 0) {
    feed.innerHTML = '<div class="empty-alerts"><p>No operational anomalies detected in recent telemetry.</p></div>';
    return;
  }
  feed.innerHTML = "";
  anomalies.slice(0, 10).forEach(anom => {
    const item = document.createElement("div");
    item.className = "rec-item";
    item.style.borderLeftColor = "var(--status-warn)";
    item.innerHTML = `
      <div style="display: flex; justify-content: space-between;">
        <strong style="color: var(--status-warn); font-size: 0.925rem;">${anom.metric} anomaly (Z: ${anom.z_score ? anom.z_score.toFixed(2) : '-'})</strong>
        <small style="color: var(--text-muted); font-size: 0.825rem;">${anom.timestamp || ''}</small>
      </div>
      <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 2px;">${anom.message || ''}</div>
    `;
    feed.appendChild(item);
  });
}

function updateModelHealth(evaluations, latency) {
  if (evaluations && evaluations.regression) {
    const reg = evaluations.regression["24h"] || evaluations.regression["1h"] || {};
    if (reg.beds_required) {
      const bMae = (reg.beds_required["1h"] && reg.beds_required["1h"].mae !== undefined) ? reg.beds_required["1h"].mae : (reg.beds_required.mae !== undefined ? reg.beds_required.mae : 69.9);
      const el = document.getElementById("val-mae-beds");
      if (el) el.innerText = `${Number(bMae).toFixed(1)} beds`;
    }
    if (reg.icu_beds_required) {
      const iMae = (reg.icu_beds_required["1h"] && reg.icu_beds_required["1h"].mae !== undefined) ? reg.icu_beds_required["1h"].mae : (reg.icu_beds_required.mae !== undefined ? reg.icu_beds_required.mae : 12.5);
      const el = document.getElementById("val-mae-icu");
      if (el) el.innerText = `${Number(iMae).toFixed(1)} beds`;
    }
  }
  if (evaluations && evaluations.classification) {
    const cls = evaluations.classification["24h"] || evaluations.classification["1h"] || {};
    const f1 = (cls.f1_score !== undefined) ? cls.f1_score : 1.0;
    const el = document.getElementById("val-f1-admissions");
    if (el) el.innerText = Number(f1).toFixed(3);
  }
  
  if (latency !== undefined && latency !== null) {
    const el = document.getElementById("val-inference-latency");
    if (el) el.innerText = `${Math.max(1, Math.round(latency))} ms`;
  }
}

// Policies
async function fetchPolicy() {
  if (!currentUser || (currentUser.role !== "ADMIN" && currentUser.role !== "OPERATIONS_MANAGER")) {
    return;
  }
  try {
    const res = await apiFetch(`${API_BASE}/policies`);
    if (res.ok) {
      const data = await res.json();
      const select = document.getElementById("select-policy");
      if (select && data && data.policy) select.value = data.policy;
    }
  } catch (err) {
    console.warn("Policy fetch skipped:", err);
  }
}

window.changePolicy = async function(val) {
  try {
    const res = await apiFetch(`${API_BASE}/policies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy: val })
    });
    if (res.ok) {
      console.log(`Hospital policy changed to: ${val}`);
      if (currentUser && currentUser.role === "ADMIN") {
        loadAuditLogs();
      }
    }
  } catch (err) {
    console.error("Error changing active policy:", err);
  }
};

async function loadHistoricalData() {
  try {
    if (currentUser && (currentUser.role === "ADMIN" || currentUser.role === "DATA_ANALYST" || currentUser.role === "OPERATIONS_MANAGER")) {
      try {
        const anomsRes = await apiFetch(`${API_BASE}/anomalies`);
        if (anomsRes.ok) {
          const anoms = await anomsRes.json();
          updateAnomaliesFeed(anoms);
        }
      } catch (e) {}
    }
    
    if (currentUser && (currentUser.role === "ADMIN" || currentUser.role === "DATA_ANALYST")) {
      try {
        const evalsRes = await apiFetch(`${API_BASE}/evaluations`);
        if (evalsRes.ok) {
          const evals = await evalsRes.json();
          updateModelHealth(evals);
        }
      } catch (e) {}
    }
  } catch (err) {
    console.warn("Historical data load:", err);
  }
}

// WebSocket setup with Exponential Backoff Auto-Reconnect
function initWebSocket() {
  const token = getAuthToken();
  const wsStatus = document.getElementById("websocket-status");
  const wsUrl = `${WS_BASE}/live?token=${encodeURIComponent(token)}`;
  
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  if (wsConnection) {
    try {
      wsConnection.onclose = null;
      wsConnection.onerror = null;
      wsConnection.close();
    } catch (e) {}
  }

  try {
    wsConnection = new WebSocket(wsUrl);
  } catch (err) {
    console.error("Failed to construct WebSocket:", err);
    scheduleWebSocketReconnect();
    return;
  }
  
  wsConnection.onopen = () => {
    reconnectAttempts = 0;
    if (wsStatus) {
      wsStatus.innerText = "LIVE STREAMING";
      wsStatus.style.color = "var(--status-ok)";
    }
    const dot = document.getElementById("pulse-dot");
    if (dot) dot.style.backgroundColor = "var(--status-ok)";
    const connStat = document.getElementById("connection-status");
    if (connStat) connStat.innerText = "Live Connected";
  };
  
  wsConnection.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateDashboardState(data);
    } catch (err) {
      console.warn("Error parsing live stream payload:", err);
    }
  };
  
  wsConnection.onclose = (event) => {
    if (wsStatus) {
      wsStatus.innerText = "RECONNECTING...";
      wsStatus.style.color = "var(--status-warn)";
    }
    const dot = document.getElementById("pulse-dot");
    if (dot) dot.style.backgroundColor = "var(--status-warn)";
    const connStat = document.getElementById("connection-status");
    if (connStat) connStat.innerText = "Reconnecting...";

    scheduleWebSocketReconnect();
  };
  
  wsConnection.onerror = (err) => {
    console.error("WebSocket encountered error:", err);
    try {
      wsConnection.close();
    } catch (e) {}
  };
}

function scheduleWebSocketReconnect() {
  if (reconnectTimer) return;
  const backoff = Math.min(10000, 1000 * Math.pow(1.5, reconnectAttempts));
  reconnectAttempts++;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initWebSocket();
  }, backoff);
}

// Fallback HTTP polling values with Pre-flight RBAC Guards
async function refreshAllFallback() {
  if (!currentUser) return;
  const role = currentUser.role;

  try {
    let state = null;
    let capacity = null;
    let predictions = null;
    let alerts = [];
    let recommendations = [];
    let timestamp = new Date().toLocaleTimeString();

    // 1. Digital Twin state: ADMIN, DOCTOR, OPERATIONS_MANAGER
    if (role === "ADMIN" || role === "DOCTOR" || role === "OPERATIONS_MANAGER") {
      try {
        const stateRes = await apiFetch(`${API_BASE}/hospital/state`);
        if (stateRes.ok) {
          state = await stateRes.json();
          if (state.timestamp) timestamp = state.timestamp;
        }
      } catch (e) {}
    }

    // 2. Capacity metrics: ADMIN, OPERATIONS_MANAGER
    if (role === "ADMIN" || role === "OPERATIONS_MANAGER") {
      try {
        const capRes = await apiFetch(`${API_BASE}/capacity`);
        if (capRes.ok) capacity = await capRes.json();
      } catch (e) {}
    }

    // 3. Predictions: ADMIN, OPERATIONS_MANAGER, DATA_ANALYST
    if (role === "ADMIN" || role === "OPERATIONS_MANAGER" || role === "DATA_ANALYST") {
      try {
        const predRes = await apiFetch(`${API_BASE}/prediction`);
        if (predRes.ok) {
          predictions = await predRes.json();
          if (predictions.timestamp && !state) timestamp = predictions.timestamp;
        }
      } catch (e) {}
    }

    // 4. Active Alerts: ADMIN, DOCTOR, OPERATIONS_MANAGER
    if (role === "ADMIN" || role === "DOCTOR" || role === "OPERATIONS_MANAGER") {
      try {
        const alertsRes = await apiFetch(`${API_BASE}/alerts`);
        if (alertsRes.ok) alerts = await alertsRes.json();
      } catch (e) {}
    }

    // 5. Recommendations: ADMIN, OPERATIONS_MANAGER
    if (role === "ADMIN" || role === "OPERATIONS_MANAGER") {
      try {
        const recsRes = await apiFetch(`${API_BASE}/recommendations`);
        if (recsRes.ok) recommendations = await recsRes.json();
      } catch (e) {}
    }

    // 6. Bed forecast (if not populated): ADMIN, DATA_ANALYST
    if ((role === "ADMIN" || role === "DATA_ANALYST") && (!predictions || !predictions.forecast_24h || predictions.forecast_24h.length === 0)) {
      try {
        const fcRes = await apiFetch(`${API_BASE}/forecast/beds?hours=24`);
        if (fcRes.ok) {
          const fcData = await fcRes.json();
          if (!predictions) predictions = {};
          predictions.forecast_24h = fcData.forecast;
        }
      } catch (e) {}
    }

    const payload = {
      timestamp: timestamp,
      digital_twin: state,
      capacity_metrics: capacity,
      predictions: predictions,
      alerts: alerts,
      recommendations: recommendations
    };
    
    updateDashboardState(payload);
  } catch (err) {
    console.warn("HTTP polling fallback encountered error:", err);
  }
}

