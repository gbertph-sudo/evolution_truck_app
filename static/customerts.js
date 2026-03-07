//* customers.js - Evolution Truck
// UI en inglés. Comentarios en español.

const API = {
  customers: "/api/customers",
  companies: "/api/companies",
  vehicles: "/api/vehicles",
  toggleActive: (id) => `/api/customers/${id}/active`,
};

const $ = (id) => document.getElementById(id);

function goLogin(){ window.location.href = "/static/index.html"; }

// ===============================
// AUTH
// ===============================
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
    ["token","access_token","jwt","token_type"].forEach(k => {
      localStorage.removeItem(k);
      sessionStorage.removeItem(k);
    });
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

// ===============================
// UI helpers
// ===============================
function setPill(id, text){ const el = $(id); if (el) el.textContent = text; }
function setMsg(text, isError=false){
  const el = $("msg"); if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "crimson" : "#2b2f36";
}

function debounce(fn, ms=250){
  let t=null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// ===============================
// Companies picker (sin Ctrl)
// ===============================
let companiesCache = [];

function getSelectedCompanyIdsFromBox(){
  const box = $("companyBox");
  if (!box) return [];
  return Array.from(box.querySelectorAll("input[data-company-id]:checked"))
    .map(chk => parseInt(chk.getAttribute("data-company-id"), 10))
    .filter(n => Number.isFinite(n));
}

function renderCompaniesBox(list){
  const box = $("companyBox");
  if (!box) return;

  if (!Array.isArray(list) || list.length === 0) {
    box.innerHTML = `<div class="muted">No companies.</div>`;
    return;
  }

  box.innerHTML = list.map(c => `
    <label class="company-item">
      <input type="checkbox" data-company-id="${c.id}" />
      <span><b>${escapeHtml(c.name ?? "")}</b> <span class="muted">(#${c.id})</span></span>
    </label>
  `).join("");
}

function filterCompanies(){
  const q = ($("companyFilter")?.value || "").trim().toLowerCase();
  const filtered = !q
    ? companiesCache
    : companiesCache.filter(c => String(c.name || "").toLowerCase().includes(q));
  renderCompaniesBox(filtered);
}

async function quickAddCompany(){
  const name = prompt("New company name:");
  if (!name) return;

  try{
    setMsg("Creating company...");
    await apiSend(API.companies, "POST", { name: name.trim() });
    setMsg("Company created ✅");

    // recargar companies y mantener filtro
    await loadCompanies();
    filterCompanies();
  } catch (e){
    console.error(e);
    setMsg(String(e?.message || "Error creating company"), true);
  }
}

async function loadCompanies(){
  const data = await apiGet(API.companies);
  companiesCache = Array.isArray(data) ? data : [];
  // default render
  renderCompaniesBox(companiesCache);
}

// ===============================
// Customers list
// ===============================
function escapeHtml(s){
  return String(s ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

function renderCustomersTable(list){
  const tbody = $("tbody");
  if (!tbody) return;

  if (!Array.isArray(list) || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No customers.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(c => {
    const comps = (c.companies || []).map(x => x.name).filter(Boolean);
    const active = (c.is_active !== false);
    const status = active ? "ACTIVE" : "INACTIVE";

    const compTags = comps.length
      ? comps.map(n => `<span class="tag">${escapeHtml(n)}</span>`).join("")
      : "—";

    return `
      <tr>
        <td>${c.id}</td>
        <td><b>${escapeHtml(c.name ?? "")}</b></td>
        <td>${compTags}</td>
        <td>${escapeHtml(c.phone ?? "—")}</td>
        <td>${escapeHtml(c.email ?? "—")}</td>
        <td class="${active ? "status-active" : "status-inactive"}">${status}</td>
        <td>
          <button class="ghost" type="button" data-add-veh="${c.id}">+ Vehicle</button>
          <button class="ghost" type="button" data-toggle-id="${c.id}" data-next="${active ? "0":"1"}">
            ${active ? "Deactivate" : "Activate"}
          </button>
        </td>
      </tr>
    `;
  }).join("");

  // Toggle active
  tbody.querySelectorAll("button[data-toggle-id]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = parseInt(btn.getAttribute("data-toggle-id"), 10);
      const next = btn.getAttribute("data-next") === "1";
      const ok = confirm(`Are you sure you want to ${next ? "ACTIVATE" : "DEACTIVATE"} this customer?`);
      if (!ok) return;

      try{
        setMsg("Saving...");
        await apiSend(API.toggleActive(id), "PATCH", { is_active: next });
        setMsg("Saved ✅");
        await refreshCustomersOnly();
      } catch(e){
        console.error(e);
        setMsg(String(e?.message || "Error"), true);
      }
    });
  });

  // Quick add vehicle (prompt rápido)
  tbody.querySelectorAll("button[data-add-veh]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const customerId = parseInt(btn.getAttribute("data-add-veh"), 10);

      const vin = (prompt("VIN (17 chars) (optional):") || "").trim();
      const unit_number = (prompt("Unit # (optional):") || "").trim();
      const yearRaw = (prompt("Year (optional):") || "").trim();
      const make = (prompt("Make (optional):") || "").trim();
      const model = (prompt("Model (optional):") || "").trim();

      const payload = {
        vin: vin || null,
        unit_number: unit_number || null,
        year: yearRaw ? parseInt(yearRaw, 10) : null,
        make: make || null,
        model: model || null,
        customer_id: customerId,
      };

      try{
        setMsg("Creating vehicle...");
        await apiSend(API.vehicles, "POST", payload);
        setMsg("Vehicle created ✅");
      } catch(e){
        console.error(e);
        setMsg(String(e?.message || "Error creating vehicle"), true);
      }
    });
  });
}

async function loadCustomers(){
  const showInactive = !!$("chkShowInactive")?.checked;
  const q = ($("q")?.value || "").trim();

  const params = new URLSearchParams();
  if (showInactive) params.set("include_inactive", "true");
  if (q) params.set("q", q);

  const url = params.toString() ? `${API.customers}?${params.toString()}` : API.customers;

  const data = await apiGet(url);
  return Array.isArray(data) ? data : [];
}

async function refreshCustomersOnly(){
  const custs = await loadCustomers();
  renderCustomersTable(custs);
}

async function refreshAll(){
  try{
    setPill("apiStatus","API: checking...");
    await loadCompanies();
    await refreshCustomersOnly();
    setPill("apiStatus","API: OK");
  } catch(e){
    console.error(e);
    setPill("apiStatus","API: ERROR");
    setMsg("API error. Check console.", true);
  }
}

// ===============================
// Create flow: Customer + (optional) Vehicle
// ===============================
function clearCreateForm(){
  ["name","phone","email"].forEach(id => { if ($(id)) $(id).value = ""; });
  // uncheck companies
  const box = $("companyBox");
  if (box) box.querySelectorAll("input[data-company-id]").forEach(chk => chk.checked = false);

  // vehicle fields
  ["v_vin","v_unit","v_year","v_make","v_model"].forEach(id => { if ($(id)) $(id).value = ""; });
  if ($("chkAddVehicleNow")) $("chkAddVehicleNow").checked = false;
  if ($("vehicleQuickWrap")) $("vehicleQuickWrap").style.display = "none";
}

async function createCustomer(){
  const name = ($("name")?.value || "").trim();
  if (!name) { setMsg("Name is required.", true); return; }

  const payload = {
    name,
    phone: ($("phone")?.value || "").trim() || null,
    email: ($("email")?.value || "").trim() || null,
    company_ids: getSelectedCompanyIdsFromBox(),
  };

  try{
    setMsg("Creating customer...");
    const created = await apiSend(API.customers, "POST", payload);
    if (!created?.id) {
      setMsg("Customer created but no ID returned.", true);
      return;
    }

    // opcional: crear vehículo inmediatamente
    const addVeh = !!$("chkAddVehicleNow")?.checked;
    if (addVeh) {
      const vPayload = {
        vin: ($("v_vin")?.value || "").trim() || null,
        unit_number: ($("v_unit")?.value || "").trim() || null,
        year: ($("v_year")?.value || "").trim() ? parseInt($("v_year").value, 10) : null,
        make: ($("v_make")?.value || "").trim() || null,
        model: ($("v_model")?.value || "").trim() || null,
        customer_id: created.id,
      };

      setMsg("Creating customer + vehicle...");
      await apiSend(API.vehicles, "POST", vPayload);
      setMsg("Customer + Vehicle created ✅");
    } else {
      setMsg("Customer created ✅");
    }

    clearCreateForm();
    await refreshCustomersOnly();

    // UX: vuelve al Name listo para el próximo
    $("name")?.focus();

  } catch(e){
    console.error(e);
    setMsg(String(e?.message || "Create error"), true);
  }
}

// ===============================
// INIT
// ===============================
document.addEventListener("DOMContentLoaded", async () => {
  if (!readToken()) { goLogin(); return; }

  $("btnBack")?.addEventListener("click", () => window.location.href = "/static/dashboard.html");
  $("btnRefresh")?.addEventListener("click", refreshAll);
  $("btnCreate")?.addEventListener("click", createCustomer);

  $("btnQuickAddCompany")?.addEventListener("click", quickAddCompany);
  $("companyFilter")?.addEventListener("input", debounce(filterCompanies, 200));

  // show inactive toggle
  $("chkShowInactive")?.addEventListener("change", refreshCustomersOnly);

  // search customers (typing)
  $("q")?.addEventListener("input", debounce(refreshCustomersOnly, 250));

  // enter en Name crea rápido
  $("name")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") createCustomer();
  });

  // vehicle quick toggle
  $("chkAddVehicleNow")?.addEventListener("change", () => {
    const on = !!$("chkAddVehicleNow")?.checked;
    if ($("vehicleQuickWrap")) $("vehicleQuickWrap").style.display = on ? "block" : "none";
  });

  await refreshAll();

  // foco inicial para trabajar rápido
  $("name")?.focus();
});