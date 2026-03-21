// customers.js - Evolution Truck
// UI en inglés. Comentarios en español.

const API = {
  customers: "/api/customers",
  companies: "/api/companies",
  vehicles: "/api/vehicles",
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
  return (localStorage.getItem("token_type") || sessionStorage.getItem("token_type") || "bearer").trim();
}
function getAuthHeaders() {
  const token = readToken();
  if (!token) return {};
  const raw = readTokenType();
  const scheme = raw ? raw[0].toUpperCase() + raw.slice(1).toLowerCase() : "Bearer";
  return { Authorization: `${scheme} ${token}` };
}
function parseJwt(token) {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(atob(base64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join(""));
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
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
    ["token","access_token","jwt","token_type","role_name"].forEach(k => {
      localStorage.removeItem(k); sessionStorage.removeItem(k);
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

function setMsg(text, isError=false){
  const el = $("msg"); if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "crimson" : "green";
}

let companies = [];
let customers = [];
let editingCustomerId = null;
let roleName = "";
let isAdminUser = false;

function selectedCompanyIdsFromBox(){
  return Array.from(document.querySelectorAll('#companyBox input[type="checkbox"]:checked'))
    .map(el => parseInt(el.value, 10))
    .filter(Number.isFinite);
}

function renderCompanyBox(list, selectedIds = []) {
  const box = $("companyBox");
  if (!box) return;
  if (!list.length) {
    box.innerHTML = '<div class="muted">No companies available.</div>';
    return;
  }
  const selected = new Set((selectedIds || []).map(Number));
  box.innerHTML = list.map(c => `
    <label class="company-item">
      <input type="checkbox" value="${c.id}" ${selected.has(Number(c.id)) ? "checked" : ""} />
      <span><b>#${c.id}</b> - ${c.name ?? ""}</span>
    </label>
  `).join("");
}

function filterCompanyBox() {
  const q = ($("companyFilter")?.value || "").trim().toLowerCase();
  const filtered = !q ? companies : companies.filter(c => `${c.id} ${c.name || ""}`.toLowerCase().includes(q));
  renderCompanyBox(filtered, selectedCompanyIdsFromBox());
}

function clearCustomerForm() {
  editingCustomerId = null;
  ["name","phone","email","v_vin","v_unit","v_year","v_make","v_model","companyFilter","q"].forEach(id => { if ($(id) && ["q"].indexOf(id) === -1) $(id).value = id === "q" ? $(id).value : ""; });
  if ($("chkAddVehicleNow")) $("chkAddVehicleNow").checked = false;
  if ($("vehicleQuickWrap")) $("vehicleQuickWrap").style.display = "none";
  $("btnCreate").textContent = "Create Customer";
  $("formTitle").textContent = "Create Customer";
  $("btnCancelEdit").style.display = "none";
  renderCompanyBox(companies, []);
}

function fillCustomerForm(customer) {
  editingCustomerId = customer.id;
  $("name").value = customer.name || "";
  $("phone").value = customer.phone || "";
  $("email").value = customer.email || "";
  $("btnCreate").textContent = "Save Changes";
  $("formTitle").textContent = `Edit Customer #${customer.id}`;
  $("btnCancelEdit").style.display = "inline-block";
  renderCompanyBox(companies, customer.company_ids || (customer.companies || []).map(x => x.id));
  if ($("chkAddVehicleNow")) $("chkAddVehicleNow").checked = false;
  if ($("vehicleQuickWrap")) $("vehicleQuickWrap").style.display = "none";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderCustomersTable(list){
  const tbody = $("tbody");
  if (!tbody) return;

  if (!Array.isArray(list) || list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">No customers.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(c => {
    const comps = (c.companies || []).map(x => x.name).filter(Boolean).join(", ");
    const active = (c.is_active !== false);
    return `
      <tr>
        <td>${c.id}</td>
        <td><b>${c.name ?? ""}</b></td>
        <td>${comps || "—"}</td>
        <td>${c.phone ?? "—"}</td>
        <td>${c.email ?? "—"}</td>
        <td><b>${active ? "ACTIVE" : "INACTIVE"}</b></td>
        <td>
          <button type="button" class="ghost" data-edit-id="${c.id}">Edit</button>
          ${isAdminUser ? `<button type="button" data-delete-id="${c.id}" style="margin-left:8px;">Delete</button>` : ""}
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("[data-edit-id]").forEach(btn => btn.addEventListener("click", () => {
    const c = customers.find(x => Number(x.id) === Number(btn.dataset.editId));
    if (c) fillCustomerForm(c);
  }));
  tbody.querySelectorAll("[data-delete-id]").forEach(btn => btn.addEventListener("click", () => deleteCustomer(btn.dataset.deleteId)));
}

async function loadCompanies(){
  companies = (await apiGet(API.companies)) || [];
  renderCompanyBox(companies, selectedCompanyIdsFromBox());
}

async function loadCustomers(){
  const q = ($("q")?.value || "").trim();
  const includeInactive = $("chkShowInactive")?.checked ? "true" : "false";
  const url = `${API.customers}?include_inactive=${includeInactive}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  customers = (await apiGet(url)) || [];
  renderCustomersTable(customers);
}

async function createQuickCompany(){
  const name = prompt("New company name:");
  if (!name || !name.trim()) return;
  try {
    await apiSend(API.companies, "POST", { name: name.trim() });
    await loadCompanies();
    setMsg("Company created ✅");
  } catch (err) {
    setMsg(String(err?.message || err || "Error"), true);
  }
}

function getCustomerPayload() {
  return {
    name: ($("name")?.value || "").trim(),
    phone: ($("phone")?.value || "").trim() || null,
    email: ($("email")?.value || "").trim() || null,
    company_ids: selectedCompanyIdsFromBox(),
  };
}

function getVehicleQuickPayload(customerId) {
  return {
    vin: ($("v_vin")?.value || "").trim() || null,
    unit_number: ($("v_unit")?.value || "").trim() || null,
    year: ($("v_year")?.value || "").trim() ? Number(("" + $("v_year").value).trim()) : null,
    make: ($("v_make")?.value || "").trim() || null,
    model: ($("v_model")?.value || "").trim() || null,
    customer_id: customerId,
  };
}

function vehicleQuickHasData() {
  return ["v_vin","v_unit","v_year","v_make","v_model"].some(id => ($(id)?.value || "").trim() !== "");
}

async function saveCustomer(){
  const payload = getCustomerPayload();
  if (!payload.name) {
    setMsg("Customer name is required.", true);
    return;
  }

  try {
    let customer;
    if (editingCustomerId) {
      setMsg("Saving customer...");
      customer = await apiSend(`${API.customers}/${editingCustomerId}`, "PATCH", payload);
    } else {
      setMsg("Creating customer...");
      customer = await apiSend(API.customers, "POST", payload);
    }
    if (!customer) return;

    if (!editingCustomerId && $("chkAddVehicleNow")?.checked && vehicleQuickHasData()) {
      await apiSend(API.vehicles, "POST", getVehicleQuickPayload(customer.id));
    }

    setMsg(editingCustomerId ? "Customer updated ✅" : "Customer created ✅");
    clearCustomerForm();
    await loadCustomers();
  } catch (err) {
    console.error(err);
    setMsg(String(err?.message || err || "Error"), true);
  }
}

async function deleteCustomer(id) {
  if (!isAdminUser) {
    setMsg("Only ADMIN or SUPERADMIN can delete customers.", true);
    return;
  }
  const customer = customers.find(x => Number(x.id) === Number(id));
  const label = customer?.name || `#${id}`;
  if (!confirm(`Delete customer ${label}? This cannot be undone.`)) return;
  try {
    setMsg("Deleting customer...");
    await apiSend(`${API.customers}/${id}`, "DELETE");
    if (Number(editingCustomerId) === Number(id)) clearCustomerForm();
    setMsg("Customer deleted ✅");
    await loadCustomers();
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
  $("btnCreate")?.addEventListener("click", saveCustomer);
  $("btnRefresh")?.addEventListener("click", loadCustomers);
  $("btnQuickAddCompany")?.addEventListener("click", createQuickCompany);
  $("btnCancelEdit")?.addEventListener("click", clearCustomerForm);
  $("companyFilter")?.addEventListener("input", filterCompanyBox);
  $("q")?.addEventListener("input", loadCustomers);
  $("chkShowInactive")?.addEventListener("change", loadCustomers);
  $("chkAddVehicleNow")?.addEventListener("change", (e) => {
    $("vehicleQuickWrap").style.display = e.target.checked ? "block" : "none";
  });

  await loadCompanies();
  await loadCustomers();
  clearCustomerForm();
});
