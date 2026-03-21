// vehicles.js - Evolution Truck
// UI en inglés. Comentarios en español.

const API = {
  vehicles: "/api/vehicles",
  customers: "/api/customers",
};
const $ = (id) => document.getElementById(id);

function goLogin(){ window.location.href = "/static/index.html"; }
function readToken() {
  return (
    localStorage.getItem("token") || localStorage.getItem("access_token") || localStorage.getItem("jwt") ||
    sessionStorage.getItem("token") || sessionStorage.getItem("access_token") || ""
  ).trim();
}
function readTokenType() { return (localStorage.getItem("token_type") || sessionStorage.getItem("token_type") || "bearer").trim(); }
function getAuthHeaders() {
  const token = readToken(); if (!token) return {};
  const raw = readTokenType();
  const scheme = raw ? raw[0].toUpperCase() + raw.slice(1).toLowerCase() : "Bearer";
  return { Authorization: `${scheme} ${token}` };
}
function parseJwt(token) {
  try {
    const part = token.split(".")[1]; if (!part) return null;
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(atob(base64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join(""));
    return JSON.parse(jsonPayload);
  } catch { return null; }
}
function getRoleName() {
  const payload = parseJwt(readToken());
  const rn = payload?.role_name || payload?.role || payload?.roleName || localStorage.getItem("role_name") || "";
  if (typeof rn === "object" && rn && rn.name) return String(rn.name).toUpperCase();
  return String(rn || "").toUpperCase();
}
function isAdminRole(roleName) { return roleName === "ADMIN" || roleName === "SUPERADMIN"; }
async function handleUnauthorized(res) {
  if (res && res.status === 401) {
    ["token","access_token","jwt","token_type","role_name"].forEach(k => { localStorage.removeItem(k); sessionStorage.removeItem(k); });
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
function setCount(text){ const el = $("countPill"); if (el) el.textContent = text || "—"; }
function setMsg(text, isError=false){ const el = $("msg"); if (!el) return; el.textContent = text || ""; el.style.color = isError ? "crimson" : "green"; }

let customers = [];
let vehicles = [];
let customersById = new Map();
let editingVehicleId = null;
let roleName = "";
let isAdminUser = false;

function renderCustomersSelect(list){
  const sel = $("customer_id"); if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">— No customer —</option>' + (list || []).map(c => `<option value="${c.id}">${c.name ?? `Customer ${c.id}`}</option>`).join("");
  sel.value = current || "";
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
    const hay = [v.id,v.vin,v.unit_number,v.year,v.make,v.model,v.customer_id,cname].map(x => String(x ?? "").toLowerCase()).join(" | ");
    return hay.includes(q);
  });
}
function resetForm() {
  editingVehicleId = null;
  ["vin","unit_number","year","make","model"].forEach(id => { if ($(id)) $(id).value = ""; });
  if ($("customer_id")) $("customer_id").value = "";
  $("btnCreate").textContent = "Create";
  $("formTitle").textContent = "Create Vehicle";
  $("btnCancelEdit").style.display = "none";
}
function fillForm(vehicle) {
  editingVehicleId = vehicle.id;
  $("vin").value = vehicle.vin || "";
  $("unit_number").value = vehicle.unit_number || "";
  $("year").value = vehicle.year || "";
  $("make").value = vehicle.make || "";
  $("model").value = vehicle.model || "";
  $("customer_id").value = vehicle.customer_id || "";
  $("btnCreate").textContent = "Save Changes";
  $("formTitle").textContent = `Edit Vehicle #${vehicle.id}`;
  $("btnCancelEdit").style.display = "inline-block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function renderVehiclesTable(list){
  const tbody = $("tbody"); if (!tbody) return;
  const filtered = applySearchFilter(list);
  if (!filtered || !filtered.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">No vehicles found.</td></tr>';
    setCount("Vehicles: 0");
    return;
  }
  tbody.innerHTML = filtered.map(v => `
    <tr>
      <td><b>${v.id}</b></td>
      <td>${v.vin ?? "—"}</td>
      <td>${v.unit_number ?? "—"}</td>
      <td>${v.year ?? "—"}</td>
      <td>${v.make ?? "—"}</td>
      <td>${v.model ?? "—"}</td>
      <td><small>${getCustomerLabel(v.customer_id)}</small></td>
      <td>
        <button type="button" class="ghost" data-edit-id="${v.id}">Edit</button>
        ${isAdminUser ? `<button type="button" data-delete-id="${v.id}" style="margin-left:8px;">Delete</button>` : ""}
      </td>
    </tr>
  `).join("");
  setCount(`Vehicles: ${filtered.length}`);
  tbody.querySelectorAll("[data-edit-id]").forEach(btn => btn.addEventListener("click", () => {
    const v = vehicles.find(x => Number(x.id) === Number(btn.dataset.editId));
    if (v) fillForm(v);
  }));
  tbody.querySelectorAll("[data-delete-id]").forEach(btn => btn.addEventListener("click", () => deleteVehicle(btn.dataset.deleteId)));
}
async function loadCustomers(){
  customers = (await apiGet(`${API.customers}?include_inactive=true`)) || [];
  customersById = new Map(customers.map(c => [Number(c.id), c]));
  renderCustomersSelect(customers);
}
async function loadVehicles(){
  vehicles = (await apiGet(API.vehicles)) || [];
  renderVehiclesTable(vehicles);
}
function buildPayload() {
  return {
    vin: ($("vin")?.value || "").trim() || null,
    unit_number: ($("unit_number")?.value || "").trim() || null,
    year: ($("year")?.value || "").trim() ? Number($("year").value) : null,
    make: ($("make")?.value || "").trim() || null,
    model: ($("model")?.value || "").trim() || null,
    customer_id: ($("customer_id")?.value || "").trim() ? Number($("customer_id").value) : null,
  };
}
async function saveVehicle(){
  try {
    if (editingVehicleId) {
      setMsg("Saving vehicle...");
      await apiSend(`${API.vehicles}/${editingVehicleId}`, "PATCH", buildPayload());
      setMsg("Vehicle updated ✅");
    } else {
      setMsg("Creating vehicle...");
      await apiSend(API.vehicles, "POST", buildPayload());
      setMsg("Vehicle created ✅");
    }
    resetForm();
    await loadVehicles();
  } catch (err) {
    console.error(err);
    setMsg(String(err?.message || err || "Error"), true);
  }
}
async function deleteVehicle(id) {
  if (!isAdminUser) {
    setMsg("Only ADMIN or SUPERADMIN can delete vehicles.", true);
    return;
  }
  const vehicle = vehicles.find(x => Number(x.id) === Number(id));
  const label = vehicle?.vin || vehicle?.unit_number || `#${id}`;
  if (!confirm(`Delete vehicle ${label}? This cannot be undone.`)) return;
  try {
    setMsg("Deleting vehicle...");
    await apiSend(`${API.vehicles}/${id}`, "DELETE");
    if (Number(editingVehicleId) === Number(id)) resetForm();
    setMsg("Vehicle deleted ✅");
    await loadVehicles();
  } catch (err) {
    console.error(err);
    setMsg(String(err?.message || err || "Error"), true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!readToken()) { goLogin(); return; }
  roleName = getRoleName();
  isAdminUser = isAdminRole(roleName);
  $("btnBack")?.addEventListener("click", () => { window.location.href = "/static/dashboard.html"; });
  $("btnRefresh")?.addEventListener("click", loadVehicles);
  $("btnCreate")?.addEventListener("click", saveVehicle);
  $("btnCancelEdit")?.addEventListener("click", resetForm);
  $("searchBox")?.addEventListener("input", () => renderVehiclesTable(vehicles));
  await loadCustomers();
  await loadVehicles();
  resetForm();
});
