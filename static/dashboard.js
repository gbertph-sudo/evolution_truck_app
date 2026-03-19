// static/dashboard.js

function $(id) { return document.getElementById(id); }

// --- JWT decode (sin librerías) ---
function parseJwt(token) {
  try {
    if (!token) return null;

    const parts0 = String(token).trim().split(" ");
    const raw = (parts0.length === 2 && parts0[0].toLowerCase() === "bearer") ? parts0[1] : token;

    const parts = raw.split(".");
    if (parts.length !== 3) return null;

    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

function getToken() {
  const t = localStorage.getItem("access_token") || localStorage.getItem("token") || "";
  return String(t || "").trim();
}

function isTokenExpired(payload) {
  try {
    const exp = payload?.exp;
    if (!exp) return false;
    return (Date.now() / 1000) >= Number(exp);
  } catch {
    return false;
  }
}

function getRoleName() {
  const direct = (localStorage.getItem("role_name") || localStorage.getItem("role") || "").trim();
  if (direct) return direct.toUpperCase();

  const token = getToken();
  const payload = token ? parseJwt(token) : null;
  const rn = payload?.role_name || payload?.role || payload?.roleName || "";
  return String(rn || "").trim().toUpperCase();
}

function getUserName() {
  const direct = (localStorage.getItem("full_name") || localStorage.getItem("username") || "").trim();
  if (direct) return direct;

  const token = getToken();
  const payload = token ? parseJwt(token) : null;
  return payload?.username || "Signed in";
}

function isAdminRole(roleName) {
  return roleName === "ADMIN" || roleName === "SUPERADMIN";
}

function redirectToLogin() {
  window.location.replace("/static/index.html");
}

function setText(id, value){
  const el = $(id);
  if (el) el.textContent = value;
}

function formatToday() {
  const d = new Date();
  return d.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

async function fetchJson(url) {
  const token = getToken();
  const headers = token ? { "Authorization": `Bearer ${token}` } : {};
  const res = await fetch(url, { headers });
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("HTTP 401");
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadKpis() {
  try {
    const workOrders = await fetchJson("/work-orders");
    if (Array.isArray(workOrders)) {
      const openCount = workOrders.filter(x => {
        const s = String(x.status || "").toUpperCase();
        return s === "OPEN" || s === "IN_PROGRESS";
      }).length;
      setText("kpiWorkOrders", String(openCount));
    } else {
      setText("kpiWorkOrders", "0");
    }
  } catch {
    setText("kpiWorkOrders", "--");
  }

  try {
    const invoices = await fetchJson("/invoices");
    if (Array.isArray(invoices)) {
      const draftCount = invoices.filter(x => {
        const s = String(x.status || "").toUpperCase();
        return s === "DRAFT" || s === "OPEN" || s === "PENDING";
      }).length;
      setText("kpiInvoices", String(draftCount));
    } else {
      setText("kpiInvoices", "0");
    }
  } catch {
    setText("kpiInvoices", "--");
  }

  try {
    const inventory = await fetchJson("/api/inventory");
    if (Array.isArray(inventory)) {
      const lowStockCount = inventory.filter(x => {
        const qty = Number(x.quantity_in_stock || 0);
        const min = Number(x.minimum_stock || 0);
        return qty <= min;
      }).length;
      setText("kpiInventory", String(lowStockCount));
    } else {
      setText("kpiInventory", "0");
    }
  } catch {
    setText("kpiInventory", "--");
  }
}

function setupSearch() {
  const searchInput = $("moduleSearch");
  const clearBtn = $("clearSearchBtn");
  const items = Array.from(document.querySelectorAll(".module-item"));

  function applyFilter() {
    const q = String(searchInput?.value || "").trim().toLowerCase();
    items.forEach(card => {
      const hay = (card.dataset.search || "") + " " + card.textContent;
      const match = !q || hay.toLowerCase().includes(q);
      card.classList.toggle("hidden-by-search", !match);
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFilter);
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      applyFilter();
      if (searchInput) searchInput.focus();
    });
  }
}

function bindNavButton(id, route) {
  const el = $(id);
  if (el) {
    el.addEventListener("click", () => {
      window.location.href = route;
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const token = getToken();
  if (!token) {
    redirectToLogin();
    return;
  }

  const payload = parseJwt(token);
  if (!payload) {
    redirectToLogin();
    return;
  }

  if (isTokenExpired(payload)) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    localStorage.removeItem("token_type");
    localStorage.removeItem("role_name");
    localStorage.removeItem("role");
    redirectToLogin();
    return;
  }

  const msg = $("msg");
  if (msg) {
    msg.textContent = "✅ Session active.";
    msg.style.color = "#86efac";
  }

  setText("userNameValue", getUserName());
  setText("roleNameValue", getRoleName() || "-");
  setText("todayValue", formatToday());

  bindNavButton("goInventoryBtn", "/static/inventory.html");
  bindNavButton("goCustomersBtn", "/static/customers.html");
  bindNavButton("goCompaniesBtn", "/static/companies.html");
  bindNavButton("goVehiclesBtn", "/static/vehicles.html");
  bindNavButton("goWorkOrdersBtn", "/static/workorders.html");
  bindNavButton("btnInvoices", "/static/invoices.html");

  bindNavButton("goPosBtn", "/static/parts_store.html");
  bindNavButton("goServiceHistoryBtn", "/static/service_history.html");
  bindNavButton("goVendorsBtn", "/static/vendors.html");
  bindNavButton("goPurchaseOrdersBtn", "/static/purchase_orders.html");
  bindNavButton("goQuotesBtn", "/static/estimates_quotes.html");
  bindNavButton("goPaymentsBtn", "/static/payments.html");
  bindNavButton("goAccountingBtn", "/static/accounting.html");
  bindNavButton("goLaborTrackingBtn", "/static/labor_tracking.html");
  bindNavButton("goAppointmentsBtn", "/static/appointments.html");
  bindNavButton("goTasksBtn", "/static/tasks.html");
  bindNavButton("goWarrantyBtn", "/static/warranty.html");
  bindNavButton("goReportsBtn", "/static/reports.html");
  bindNavButton("goAnalyticsBtn", "/static/analytics.html");
  bindNavButton("goRolesBtn", "/static/roles.html");
  bindNavButton("goSettingsBtn", "/static/settings.html");
  bindNavButton("goAuditLogBtn", "/static/audit_log.html");

  const roleName = getRoleName();
  const admin = isAdminRole(roleName);
  const createUsersCard = $("createUsersCard");
  if (createUsersCard) {
    createUsersCard.style.display = admin ? "flex" : "none";
  }
  bindNavButton("goUsersBtn", "/static/users.html");

  const logoutBtn = $("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem("access_token");
      localStorage.removeItem("token");
      localStorage.removeItem("token_type");
      localStorage.removeItem("role_name");
      localStorage.removeItem("role");
      localStorage.removeItem("username");
      localStorage.removeItem("full_name");
      redirectToLogin();
    });
  }

  setupSearch();
  loadKpis();
});
