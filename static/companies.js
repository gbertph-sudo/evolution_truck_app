// static/companies.js
// UI en inglés. Comentarios en español.

const API = {
  base: "/api/companies",
};

function $(id) { return document.getElementById(id); }

function setPill(id, text) { const el = $(id); if (el) el.textContent = text; }
function setCount(text){ const el = $("countPill"); if (el) el.textContent = text || "—"; }

function setMsg(text, isError=false) {
  const el = $("msg");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "crimson" : "#2b2f36";
  if (!text) el.style.color = "#666";
}

// ===============================
// AUTH (igual estilo inventory.js)
// ===============================
function goLogin() { window.location.href = "/static/index.html"; }

function readToken() {
  return (
    localStorage.getItem("token") ||
    localStorage.getItem("access_token") ||
    localStorage.getItem("jwt") ||
    sessionStorage.getItem("token") ||
    sessionStorage.getItem("access_token") ||
    ""
  ).trim();
}

function readTokenType() {
  return (
    localStorage.getItem("token_type") ||
    sessionStorage.getItem("token_type") ||
    "bearer"
  ).trim();
}

function getAuthHeaders() {
  const token = readToken();
  if (!token) return {};
  const raw = readTokenType();
  const scheme = raw ? raw[0].toUpperCase() + raw.slice(1).toLowerCase() : "Bearer";
  return { Authorization: `${scheme} ${token}` };
}

async function handleUnauthorized(res) {
  if (res && res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("jwt");
    localStorage.removeItem("token_type");
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("jwt");
    sessionStorage.removeItem("token_type");
    goLogin();
    return true;
  }
  return false;
}

async function apiGet(url) {
  const res = await fetch(url, { headers: { ...getAuthHeaders() } });
  if (await handleUnauthorized(res)) return null;
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function apiSend(url, method, payload) {
  const opts = { method, headers: { ...getAuthHeaders() } };
  if (payload !== null && payload !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(payload);
  }
  const res = await fetch(url, opts);
  if (await handleUnauthorized(res)) return null;

  if (res.status === 403) {
    throw new Error("Forbidden: you don't have permission for this action.");
  }

  if (!res.ok) throw new Error(await res.text());
  try { return await res.json(); } catch { return null; }
}

// ===============================
// STATE
// ===============================
let companies = [];

// ===============================
// UI
// ===============================
function applySearchFilter(list){
  const q = ($("searchBox")?.value || "").trim().toLowerCase();
  if (!q) return list || [];

  return (list || []).filter(c => {
    const hay = [c.id, c.name].map(x => String(x ?? "").toLowerCase()).join(" | ");
    return hay.includes(q);
  });
}

function renderTable(list) {
  const tbody = $("tbody");
  if (!tbody) return;

  const filtered = applySearchFilter(list);

  if (!Array.isArray(filtered) || filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="2" class="muted">No companies found.</td></tr>`;
    setCount("Companies: 0");
    return;
  }

  tbody.innerHTML = filtered.map(c => `
    <tr>
      <td><b>${c.id ?? ""}</b></td>
      <td>${c.name ?? ""}</td>
    </tr>
  `).join("");

  setCount(`Companies: ${filtered.length}`);
}

async function loadCompanies() {
  try {
    setPill("apiStatus", "API: checking...");
    const data = await apiGet(API.base);
    if (!data) return;

    companies = Array.isArray(data) ? data : [];

    setPill("apiStatus", "API: OK");
    renderTable(companies);
  } catch (err) {
    console.error(err);
    setPill("apiStatus", "API: ERROR");
    setMsg("API error loading companies. Check console.", true);
    companies = [];
    renderTable(companies);
  }
}

async function createCompany() {
  const input = $("companyName");
  const name = (input?.value || "").trim();
  if (!name) {
    setMsg("Company name is required.", true);
    return;
  }

  try {
    setMsg("Creating...");
    const created = await apiSend(API.base, "POST", { name });
    if (!created) return;

    setMsg("Created ✅");
    if (input) input.value = "";

    await loadCompanies();
  } catch (err) {
    console.error(err);
    const msg = String(err?.message || err || "Error");
    setMsg(msg, true);
  }
}

// ===============================
// INIT
// ===============================
document.addEventListener("DOMContentLoaded", async () => {
  if (!readToken()) { goLogin(); return; }

  $("btnBack")?.addEventListener("click", () => {
    window.location.href = "/static/dashboard.html";
  });

  $("btnRefresh")?.addEventListener("click", loadCompanies);
  $("btnCreate")?.addEventListener("click", createCompany);

  // Enter para crear
  $("companyName")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") createCompany();
  });

  // ✅ search live
  $("searchBox")?.addEventListener("input", () => renderTable(companies));

  await loadCompanies();
});