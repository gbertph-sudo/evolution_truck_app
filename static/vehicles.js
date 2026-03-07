//* vehicles.js - Evolution Truck
// UI en inglés. Comentarios en español.

const API = {
  vehicles: "/api/vehicles",
  customers: "/api/customers",
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
  if (!res.ok) throw new Error(await res.text());
  try { return await res.json(); } catch { return null; }
}

function setPill(id, text){ const el = $(id); if (el) el.textContent = text; }
function setCount(text){ const el = $("countPill"); if (el) el.textContent = text || "—"; }

function setMsg(text, isError=false){
  const el = $("msg"); if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "crimson" : "green";
}

/* ==========================
   STATE
========================== */
let customers = [];
let vehicles = [];
let customersById = new Map();

/* ==========================
   UI HELPERS
========================== */
function renderCustomersSelect(list){
  const sel = $("customer_id");
  if (!sel) return;

  sel.innerHTML =
    '<option value="">— No customer —</option>' +
    (list || []).map(c =>
      `<option value="${c.id}">${c.name ?? `Customer ${c.id}`}</option>`
    ).join("");
}

function getCustomerLabel(customer_id){
  if (!customer_id) return "—";
  const c = customersById.get(Number(customer_id));
  if (!c) return `#${customer_id}`;
  return `${c.name ?? `Customer #${customer_id}`} (ID ${customer_id})`;
}

function applySearchFilter(list){
  const q = ($("searchBox")?.value || "").trim().toLowerCase();
  if (!q) return list;

  return (list || []).filter(v => {
    const cid = v.customer_id ?? null;
    const cname = cid ? (customersById.get(Number(cid))?.name || "") : "";

    const hay = [
      v.id,
      v.vin,
      v.unit_number,
      v.year,
      v.make,
      v.model,
      v.customer_id,
      cname,
    ].map(x => String(x ?? "").toLowerCase()).join(" | ");

    return hay.includes(q);
  });
}

function renderVehiclesTable(list){
  const tbody = $("tbody");
  if (!tbody) return;

  const filtered = applySearchFilter(list);

  if (!filtered || !filtered.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No vehicles found.</td></tr>';
    setCount("Vehicles: 0");
    return;
  }

  tbody.innerHTML = filtered.map(v => {
    const customerLabel = getCustomerLabel(v.customer_id);
    return `
      <tr>
        <td><b>${v.id}</b></td>
        <td>${v.vin ?? "—"}</td>
        <td>${v.unit_number ?? "—"}</td>
        <td>${v.year ?? "—"}</td>
        <td>${v.make ?? "—"}</td>
        <td>${v.model ?? "—"}</td>
        <td><small>${customerLabel}</small></td>
      </tr>
    `;
  }).join("");

  setCount(`Vehicles: ${filtered.length}`);
}

/* ==========================
   LOAD
========================== */
function rebuildCustomerMap(){
  customersById = new Map();
  for (const c of (customers || [])) {
    customersById.set(Number(c.id), c);
  }
}

async function refreshAll(){
  try{
    setPill("apiStatus","API: checking...");

    const custs = await apiGet(API.customers);
    const vehs  = await apiGet(API.vehicles);

    if (!custs || !vehs) return;

    customers = Array.isArray(custs) ? custs : [];
    vehicles  = Array.isArray(vehs) ? vehs : [];

    rebuildCustomerMap();

    setPill("apiStatus","API: OK");

    renderCustomersSelect(customers);
    renderVehiclesTable(vehicles);

  } catch (e){
    console.error(e);
    setPill("apiStatus","API: ERROR");
    setMsg("API error. Check console.", true);
  }
}

/* ==========================
   CREATE
========================== */
function normalizeVin(v){
  const vv = String(v || "").trim().toUpperCase();
  if (!vv) return null;
  return vv;
}

async function createVehicle(){
  const vinRaw = $("vin")?.value || "";
  const vin = normalizeVin(vinRaw);

  // si vin viene pero no es 17, avisamos (el schema también valida)
  if (vin && vin.length !== 17) {
    setMsg("VIN must be exactly 17 characters (or leave empty).", true);
    return;
  }

  const yearStr = ($("year")?.value || "").trim();
  const year = yearStr ? parseInt(yearStr, 10) : null;
  if (yearStr && !Number.isFinite(year)) {
    setMsg("Year must be a number.", true);
    return;
  }

  const payload = {
    vin,
    unit_number: ($("unit_number")?.value || "").trim() || null,
    make: ($("make")?.value || "").trim() || null,
    model: ($("model")?.value || "").trim() || null,
    year,
    customer_id: ($("customer_id")?.value || "").trim()
      ? parseInt($("customer_id").value, 10)
      : null,
  };

  try{
    setMsg("Creating...");
    const saved = await apiSend(API.vehicles, "POST", payload);
    if (!saved) return;

    setMsg("Created ✅");

    ["vin","unit_number","make","model","year"].forEach(id => { if ($(id)) $(id).value = ""; });
    if ($("customer_id")) $("customer_id").value = "";

    await refreshAll();
  } catch (e){
    console.error(e);
    setMsg("Create error. Check console.", true);
  }
}

/* ==========================
   INIT
========================== */
document.addEventListener("DOMContentLoaded", async () => {
  if (!readToken()) { goLogin(); return; }

  $("btnBack")?.addEventListener("click", () => window.location.href = "/static/dashboard.html");
  $("btnRefresh")?.addEventListener("click", refreshAll);
  $("btnCreate")?.addEventListener("click", createVehicle);

  // ✅ search live
  $("searchBox")?.addEventListener("input", () => renderVehiclesTable(vehicles));

  await refreshAll();
});