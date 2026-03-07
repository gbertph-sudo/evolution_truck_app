// static/dashboard.js

function $(id) { return document.getElementById(id); }

// --- JWT decode (sin librerías) ---
function parseJwt(token) {
  try {
    if (!token) return null;

    // por si guardaron "Bearer <token>"
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
  // usa el que tú tienes en tu app
  const t = localStorage.getItem("access_token") || localStorage.getItem("token") || "";
  return String(t || "").trim();
}

function isTokenExpired(payload) {
  // exp viene en segundos (unix). Date.now() en ms.
  try {
    const exp = payload?.exp;
    if (!exp) return false; // si no trae exp, no bloqueamos
    return (Date.now() / 1000) >= Number(exp);
  } catch {
    return false;
  }
}

function getRoleName() {
  // 1) si lo guardaste directo
  const direct = (localStorage.getItem("role_name") || localStorage.getItem("role") || "").trim();
  if (direct) return direct.toUpperCase();

  // 2) si viene dentro del JWT
  const token = getToken();
  const payload = token ? parseJwt(token) : null;

  // puede venir como role (tu backend lo manda así)
  const rn = payload?.role_name || payload?.role || payload?.roleName || "";
  return String(rn || "").trim().toUpperCase();
}

function isAdminRole(roleName) {
  return roleName === "ADMIN" || roleName === "SUPERADMIN";
}

function redirectToLogin() {
  window.location.replace("/static/index.html");
}

document.addEventListener("DOMContentLoaded", () => {
  // --- proteger dashboard ---
  const token = getToken();
  if (!token) {
    redirectToLogin();
    return;
  }

  // --- validar expiración ---
  const payload = parseJwt(token);
  if (!payload) {
    // token corrupto
    redirectToLogin();
    return;
  }

  if (isTokenExpired(payload)) {
    // token vencido
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
    localStorage.removeItem("token_type");
    localStorage.removeItem("role_name");
    localStorage.removeItem("role");
    redirectToLogin();
    return;
  }

  // --- estado ---
  const msg = $("msg");
  if (msg) {
    msg.textContent = "✅ Session active.";
    msg.style.color = "green";
  }

  // --- INVENTORY ---
  const goInventoryBtn = $("goInventoryBtn");
  if (goInventoryBtn) {
    goInventoryBtn.addEventListener("click", () => {
      window.location.href = "/static/inventory.html";
    });
  } else {
    console.log("❌ No encuentro #goInventoryBtn en dashboard.html");
  }

  // --- CUSTOMERS ---
  const goCustomersBtn = $("goCustomersBtn");
  if (goCustomersBtn) {
    goCustomersBtn.addEventListener("click", () => {
      window.location.href = "/static/customers.html";
    });
  } else {
    console.log("ℹ️ No encuentro #goCustomersBtn (si todavía no lo pusiste, ok)");
  }

  // --- ✅ COMPANIES (NUEVO) ---
  const goCompaniesBtn = $("goCompaniesBtn");
  if (goCompaniesBtn) {
    goCompaniesBtn.addEventListener("click", () => {
      window.location.href = "/static/companies.html";
    });
  } else {
    console.log("ℹ️ No encuentro #goCompaniesBtn (revisa que el botón exista en dashboard.html)");
  }

  // --- VEHICLES ---
  const goVehiclesBtn = $("goVehiclesBtn");
  if (goVehiclesBtn) {
    goVehiclesBtn.addEventListener("click", () => {
      window.location.href = "/static/vehicles.html";
    });
  } else {
    console.log("ℹ️ No encuentro #goVehiclesBtn (si todavía no lo pusiste, ok)");
  }
  
    // --- WORK ORDERS ---
  const goWorkOrdersBtn = $("goWorkOrdersBtn");
  if (goWorkOrdersBtn) {
    goWorkOrdersBtn.addEventListener("click", () => {
      window.location.href = "/static/workorders.html";
    });
  } else {
    console.log("ℹ️ No encuentro #goWorkOrdersBtn (revisa que el botón exista en dashboard.html)");
  }

  // Invoices tile
const tileInvoices = document.getElementById("tileInvoices");
const btnInvoices = document.getElementById("btnInvoices");

function goInvoices(){
  window.location.href = "/static/invoices.html";
}

if (btnInvoices) btnInvoices.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  goInvoices();
});

if (tileInvoices) tileInvoices.addEventListener("click", () => {
  goInvoices();
});

  // --- USERS (ADMIN/SUPERADMIN) ---
  const roleName = getRoleName();
  const admin = isAdminRole(roleName);

  console.log("ROLE:", roleName, "ADMIN?:", admin);

  const createUsersCard = $("createUsersCard");  // ID del HTML
  const goUsersBtn = $("goUsersBtn");            // ID del HTML

  if (createUsersCard) {
    createUsersCard.style.display = admin ? "flex" : "none";
  }

  if (goUsersBtn) {
    goUsersBtn.addEventListener("click", () => {
      window.location.href = "/static/users.html";
    });
  }

  // --- LOGOUT ---
  const logoutBtn = $("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem("access_token");
      localStorage.removeItem("token");
      localStorage.removeItem("token_type");
      localStorage.removeItem("role_name");
      localStorage.removeItem("role");
      redirectToLogin();
    });
  }
});