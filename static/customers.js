//* customers.js - Evolution Truck
// UI en inglés. Comentarios en español.

const API = {
  customers: "/api/customers",
  companies: "/api/companies",
  toggleActive: (id) => `/api/customers/${id}/active`,
};

const $ = (id) => document.getElementById(id);

function goLogin(){ window.location.href = "/static/index.html"; }

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

async function apiGet(url){
  const res = await fetch(url, { headers: { ...getAuthHeaders() }});
  if (await handleUnauthorized(res)) return null;
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function apiSend(url, method, payload){
  const opts = { method, headers: { ...getAuthHeaders() } };
  if (payload !== null && payload !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(payload);
  }
  const res = await fetch(url, opts);
  if (await handleUnauthorized(res)) return null;

  if (res.status === 403) throw new Error("Forbidden: you don't have permission.");

  if (!res.ok) throw new Error(await res.text());
  try { return await res.json(); } catch { return null; }
}

function setPill(id, text){ const el = $(id); if (el) el.textContent = text; }
function setMsg(text, isError=false){
  const el = $("msg"); if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "crimson" : "green";
}

function getSelectedCompanyIds(){
  const sel = $("company_ids");
  if (!sel) return [];
  return Array.from(sel.selectedOptions)
    .map(o => parseInt(o.value, 10))
    .filter(n => Number.isFinite(n));
}

function renderCompaniesSelect(list){
  const sel = $("company_ids");
  if (!sel) return;

  if (!list || !list.length) {
    sel.innerHTML = "";
    return;
  }

  sel.innerHTML = list
    .map(c => `<option value="${c.id}">${c.name ?? `Company ${c.id}`}</option>`)
    .join("");
}

function renderCustomersTable(list){
  const tbody = $("tbody");
  if (!tbody) return;

  if (!Array.isArray(list) || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No customers.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(c => {
    const comps = (c.companies || []).map(x => x.name).filter(Boolean).join(", ");
    const active = (c.is_active !== false); // default true si no viene
    const status = active ? "ACTIVE" : "INACTIVE";
    const btnText = active ? "Deactivate" : "Activate";
    const btnClass = active ? "ghost" : ""; // si quieres, lo cambias

    return `
      <tr>
        <td>${c.id}</td>
        <td><b>${c.name ?? ""}</b></td>
        <td>${comps || "—"}</td>
        <td>${c.phone ?? "—"}</td>
        <td>${c.email ?? "—"}</td>
        <td><b>${status}</b></td>
        <td>
          <button
            type="button"
            class="${btnClass}"
            data-toggle-id="${c.id}"
            data-next="${active ? "0" : "1"}"
            style="padding:8px 10px; border-radius:10px;"
          >${btnText}</button>
        </td>
      </tr>
    `;
  }).join("");

  // Hook de botones
  tbody.querySelectorAll("button[data-toggle-id]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = parseInt(btn.getAttribute("data-toggle-id"), 10);
      const next = btn.getAttribute("data-next") === "1";

      const ok = confirm(`Are you sure you want to ${next ? "ACTIVATE" : "DEACTIVATE"} this customer?`);
      if (!ok) return;

      try {
        setMsg("Saving...");
        await apiSend(API.toggleActive(id), "PATCH", { is_active: next });
        setMsg("Saved ✅");
        await refreshCustomersOnly();
      } catch (e) {
        console.error(e);
        setMsg(String(e?.message || "Error"), true);
      }
    });
  });
}

async function loadCompanies(){
  const data = await apiGet(API.companies);
  if (!data) return [];
  return Array.isArray(data) ? data : [];
}

async function loadCustomers(){
  const showInactive = !!$("chkShowInactive")?.checked;
  const url = showInactive ? `${API.customers}?include_inactive=true` : API.customers;

  const data = await apiGet(url);
  if (!data) return [];
  return Array.isArray(data) ? data : [];
}

async function refreshCustomersOnly(){
  const custs = await loadCustomers();
  renderCustomersTable(custs);
}

async function refreshAll(){
  try{
    setPill("apiStatus","API: checking...");

    const comps = await loadCompanies();
    const custs = await loadCustomers();

    setPill("apiStatus","API: OK");

    renderCompaniesSelect(comps);
    renderCustomersTable(custs);

  } catch (e){
    console.error(e);
    setPill("apiStatus","API: ERROR");
    setMsg("API error. Check console.", true);
  }
}

async function createCustomer(){
  const name = ($("name")?.value || "").trim();
  if (!name) { setMsg("Name is required.", true); return; }

  const payload = {
    name,
    phone: ($("phone")?.value || "").trim() || null,
    email: ($("email")?.value || "").trim() || null,
    company_ids: getSelectedCompanyIds(),
  };

  try{
    setMsg("Creating...");
    const saved = await apiSend(API.customers, "POST", payload);
    if (!saved) return;

    setMsg("Created ✅");
    $("name").value = "";
    $("phone").value = "";
    $("email").value = "";
    Array.from($("company_ids").options).forEach(o => o.selected = false);

    await refreshCustomersOnly();
  } catch (e){
    console.error(e);
    setMsg("Create error. Check console.", true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!readToken()) { goLogin(); return; }

  $("btnBack")?.addEventListener("click", () => window.location.href = "/static/dashboard.html");
  $("btnRefresh")?.addEventListener("click", refreshAll);
  $("btnCreate")?.addEventListener("click", createCustomer);

  // ✅ checkbox show inactive
  $("chkShowInactive")?.addEventListener("change", refreshCustomersOnly);

  await refreshAll();
});