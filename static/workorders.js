// static/workorders.js
// Work Orders PRO + Inline Create (Customer/Company/Vehicle) + Parts Cart + Invoice

function $(id){ return document.getElementById(id); }

// --------------------
// AUTH
// --------------------
function getToken(){
  return localStorage.getItem("token") || localStorage.getItem("access_token") || "";
}
function authHeaders(extra = {}){
  const t = getToken();
  const h = { "Content-Type": "application/json", ...extra };
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}
async function apiFetch(url, opts = {}){
  const res = await fetch(url, opts);
  if (!res.ok){
    let msg = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      msg = data?.detail
        ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))
        : msg;
    } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  return await res.text();
}


async function openPdfWithAuth(url){
  const token = getToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(url, { headers });
  if (!res.ok){
    let msg = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      msg = data?.detail
        ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))
        : msg;
    } catch {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const w = window.open(blobUrl, "_blank");
  if (!w) window.location.href = blobUrl;
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 15000);
}

// --------------------
// API autodetect (porque en tu swagger a veces hay /api y a veces no)
// --------------------
const BASE_CANDIDATES = ["", "/api"];
const ENDPOINTS = {
  customers: (b) => `${b}/customers`,
  companies: (b) => `${b}/companies`,
  vehicles: (b) => `${b}/vehicles`,
  users: (b) => `${b}/users`,

  // inventory (tu swagger muestra /inventory/items en otra parte)
  inventoryA: (b) => `${b}/inventory`,
  inventoryItems: (b) => `${b}/inventory/items`,

  // work orders (tu router es /work-orders sin /api)
  workOrders: (b) => `${b}/work-orders`,
};

let API_BASE = ""; // customers/companies/vehicles/users/inventory
let WO_BASE = "";  // work-orders (por default "")

async function detectBase(){
  // intenta customers primero
  for (const b of BASE_CANDIDATES){
    try{
      await apiFetch(ENDPOINTS.customers(b), { headers: authHeaders() });
      API_BASE = b;
      break;
    }catch{}
  }
  // fallback: inventory/items
  if (API_BASE === ""){
    for (const b of BASE_CANDIDATES){
      try{
        await apiFetch(ENDPOINTS.inventoryItems(b), { headers: authHeaders() });
        API_BASE = b;
        break;
      }catch{}
    }
  }

  WO_BASE = "";
  if (window.WO_BASE != null) WO_BASE = String(window.WO_BASE);
}

function urlCustomers(){ return ENDPOINTS.customers(API_BASE); }
function urlCompanies(){ return ENDPOINTS.companies(API_BASE); }
function urlVehicles(){ return ENDPOINTS.vehicles(API_BASE); }
function urlUsers(){ return ENDPOINTS.users(API_BASE); }

function urlWorkOrders(){ return ENDPOINTS.workOrders(WO_BASE); }
function urlWO(id){ return `${urlWorkOrders()}/${id}`; }
function urlWOPdf(id){ return `${urlWorkOrders()}/${id}/pdf`; }
function urlWOItems(id){ return `${urlWorkOrders()}/${id}/items`; }
function urlWOItem(id, woItemId){ return `${urlWorkOrders()}/${id}/items/${woItemId}`; }
function urlWOStatus(id){ return `${urlWorkOrders()}/${id}/status`; }
function urlCreateInvoice(id){ return `${urlWorkOrders()}/${id}/create-invoice`; }
function urlWOLabors(id){ return `${urlWorkOrders()}/${id}/labors`; }
function urlWOLabor(id, laborId){ return `${urlWorkOrders()}/${id}/labors/${laborId}`; }
function urlWOItemPricing(id, woItemId){ return `${urlWorkOrders()}/${id}/items/${woItemId}/pricing`; }

// inventory search: intenta /inventory primero; si falla usa /inventory/items
async function inventorySearch(q){
  const term = (q || "").trim();
  if (!term) return [];

  const params = new URLSearchParams();
  params.set("q", term);
  params.set("limit", "20");

  try {
    return await apiFetch(`/api/inventory?${params.toString()}`, {
      headers: authHeaders()
    });
  } catch (e) {
    return await apiFetch(`/inventory?${params.toString()}`, {
      headers: authHeaders()
    });
  }
}

// --------------------
// State
// --------------------
let CUSTOMERS = [];
let VEHICLES = [];
let USERS = [];
let WORK_ORDERS = [];
let CURRENT_WO = null;

// --------------------
// UI helpers
// --------------------
function setMsg(id, text, isError=false){
  const el = $(id);
  if (!el) return;
  el.textContent = text || "";
  el.className = isError ? "danger" : "muted";
}
function escapeHtml(s){
  return (s ?? "").toString()
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}
function pill(status){
  const s = (status || "").toUpperCase();
  const cls =
    s === "OPEN" ? "open" :
    s === "IN_PROGRESS" ? "inprogress" :
    s === "DONE" ? "done" : "cancel";
  return `<span class="pill ${cls}">${s}</span>`;
}
function fmtVehicle(v){
  if (!v) return "-";
  const unit = v.unit_number ? `Unit ${v.unit_number}` : "";
  const vin = v.vin ? `VIN ${v.vin}` : "";
  const mm = `${v.make || ""} ${v.model || ""}`.trim();
  const yr = v.year ? `${v.year}` : "";
  const parts = [unit, mm, yr, vin].filter(Boolean);
  return parts.length ? parts.join(" · ") : `#${v.id}`;
}
function money(val){
  const n = Number(val ?? 0);
  if (!Number.isFinite(n)) return "$0.00";
  return `$${n.toFixed(2)}`;
}
function num(val, fallback=0){ const n = Number(val); return Number.isFinite(n) ? n : fallback; }
function clone(obj){ return JSON.parse(JSON.stringify(obj || {})); }

// --------------------
// Loaders
// --------------------
async function loadCustomers(){
  const rows = await apiFetch(urlCustomers(), { headers: authHeaders() });
  CUSTOMERS = Array.isArray(rows) ? rows : (rows?.items || []);
}
async function loadVehicles(){
  const rows = await apiFetch(urlVehicles(), { headers: authHeaders() });
  VEHICLES = Array.isArray(rows) ? rows : (rows?.items || []);
}
async function loadUsers(){
  try{
    const rows = await apiFetch(urlUsers(), { headers: authHeaders() });
    USERS = Array.isArray(rows) ? rows : (rows?.items || []);
  }catch{
    USERS = [];
  }
}
async function loadWorkOrders(){
  const q = ($("q")?.value || "").trim();
  const status = ($("statusFilter")?.value || "").trim();

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (status) params.set("status", status);

  const u = params.toString() ? `${urlWorkOrders()}?${params}` : urlWorkOrders();
  const rows = await apiFetch(u, { headers: authHeaders() });
  WORK_ORDERS = Array.isArray(rows) ? rows : (rows?.items || []);
}
async function fetchWorkOrder(id){
  return await apiFetch(urlWO(id), { headers: authHeaders() });
}

// --------------------
// Render list
// --------------------
function renderWorkOrders(){
  const tbody = $("tbody");
  if (!tbody) return;

  if (!WORK_ORDERS.length){
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No work orders found.</td></tr>`;
    return;
  }

  tbody.innerHTML = WORK_ORDERS.map(wo => {
    const woNo = wo.work_order_number || `WO-${wo.id}`;
    const cust = wo.customer?.name || "-";
    const comp = wo.company?.name || "-";
    const vehTxt = wo.vehicle ? fmtVehicle(wo.vehicle) : "-";
    const desc = escapeHtml(wo.description || "");

    return `
      <tr>
        <td><b>${escapeHtml(woNo)}</b><div class="muted">#${wo.id}</div></td>
        <td>${pill(wo.status)}</td>
        <td>${escapeHtml(cust)}</td>
        <td>${escapeHtml(comp)}</td>
        <td>${escapeHtml(vehTxt)}</td>
        <td>${desc}</td>
        <td>
          <div class="actions">
            <button class="ghost" data-action="pdf" data-id="${wo.id}">PDF</button>
            <button class="secondary" data-action="open" data-id="${wo.id}">Open</button>
            ${["OPEN","IN_PROGRESS"].includes(String(wo.status || "").toUpperCase())
              ? `<button class="secondary" data-action="delete" data-id="${wo.id}">Delete</button>`
              : ""}
          </div>
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("button[data-action]").forEach(btn => {
    btn.addEventListener("click", onRowAction);
  });
}

async function onRowAction(e){
  const btn = e.currentTarget;
  const action = btn.getAttribute("data-action");
  const id = parseInt(btn.getAttribute("data-id"), 10);
  if (!Number.isFinite(id)) return;

  if (action === "pdf"){
    const pdfUrl = urlWOPdf(id);
    openPdfWithAuth(pdfUrl).catch(e => alert(e.message || "Could not generate PDF"));
    return;
  }
  if (action === "open"){
    await openDetails(id);
    return;
  }
  if (action === "delete"){
    const wo = WORK_ORDERS.find(x => x.id === id);
    const st = String(wo?.status || "").toUpperCase();
    if (st === "DONE" || st === "CANCELLED"){
      alert("Closed/cancelled work orders cannot be deleted.");
      return;
    }
    if (!confirm("Delete this work order?\n\nIf it has parts, stock will be returned.")) return;
    try{
      setMsg("listMsg", "Deleting work order...");
      await apiFetch(urlWO(id), { method: "DELETE", headers: authHeaders() });
      await loadWorkOrders();
      renderWorkOrders();
      setMsg("listMsg", "Work order deleted.", false);
    }catch(e){
      setMsg("listMsg", e.message || "Error deleting work order", true);
    }
    return;
  }
}

// --------------------
// Select fillers
// --------------------
function fillCustomerSelect(selectId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const list = CUSTOMERS
    .filter(c => c.is_active !== false)
    .sort((a,b) => (a.name||"").localeCompare(b.name||""));

  cacheSelectOptions(selectId, list, c => c.name || `#${c.id}`);
  const first = `<option value="">Select customer...</option>`;
  renderCachedSelect(selectId, $(selectId.includes("details") ? "detailsCustomerSearch" : "customerSearch")?.value || "", first);
  if (selectedId) sel.value = String(selectedId);
}

function getCustomerById(id){
  return CUSTOMERS.find(c => c.id === id) || null;
}

function fillCompanyForCustomer(selectId, customerId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const cust = customerId ? getCustomerById(customerId) : null;
  const companies = (cust?.companies || [])
      .filter(x => x.is_active !== false)
      .sort((a,b) => (a.name||"").localeCompare(b.name||""));

  cacheSelectOptions(selectId, companies, x => x.name || `#${x.id}`);
  const first = `<option value="">Select company (optional)...</option>`;
  renderCachedSelect(selectId, $(selectId.includes("details") ? "detailsCompanySearch" : "companySearch")?.value || "", first);
  if (selectedId) sel.value = String(selectedId);
}

function fillVehiclesForCustomer(selectId, customerId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const list = customerId
    ? VEHICLES.filter(v => v.is_active !== false && v.customer_id === customerId)
    : [];

  const sorted = list.sort((a,b) => (a.unit_number||"").localeCompare(b.unit_number||""));
  cacheSelectOptions(selectId, sorted, v => fmtVehicle(v));
  const first = `<option value="">Select vehicle (optional)...</option>`;
  renderCachedSelect(selectId, $(selectId.includes("details") ? "detailsVehicleSearch" : "vehicleSearch")?.value || "", first);
  if (selectedId) sel.value = String(selectedId);
}


const SELECT_CACHE = {};

function cacheSelectOptions(selectId, list, labelFn){
  SELECT_CACHE[selectId] = (list || []).map(x => ({ value: String(x.id), label: labelFn(x), raw: x }));
}

function renderCachedSelect(selectId, query="", firstOption=""){
  const sel = $(selectId);
  if (!sel) return;
  const q = String(query || "").trim().toLowerCase();
  const rows = (SELECT_CACHE[selectId] || []).filter(x => !q || x.label.toLowerCase().includes(q));
  sel.innerHTML = [firstOption].concat(rows.map(x => `<option value="${x.value}">${escapeHtml(x.label)}</option>`)).join("");
}

function bindFilterInput(inputId, selectId, firstOption=""){
  const input = $(inputId);
  if (!input) return;
  input.addEventListener("input", ()=>renderCachedSelect(selectId, input.value, firstOption));
}

function fillMechanics(selectId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const opts = [`<option value="">Mechanic (optional)</option>`].concat(
    USERS
      .filter(u => u.is_active !== false)
      .sort((a,b) => (a.full_name||a.username||"").localeCompare(b.full_name||b.username||""))
      .map(u => `<option value="${u.id}">${escapeHtml(u.full_name || u.username)}</option>`)
  );
  sel.innerHTML = opts.join("");
  if (selectedId) sel.value = String(selectedId);
}

function laborMechanicLabel(lb){
  return lb?.mechanic_name || lb?.mechanic?.full_name || lb?.mechanic?.username || "-";
}

// --------------------
// Tabs
// --------------------
function setTab(tab){
  ["info","parts","labor","invoice"].forEach(t=>{
    const map = {info:"tabInfo", parts:"tabParts", labor:"tabLabor", invoice:"tabInvoice"};
    const b = $(map[t]);
    if (b) b.classList.toggle("active", t===tab);
    const p = $("panel" + t.charAt(0).toUpperCase() + t.slice(1));
    if (p) p.classList.toggle("active", t===tab);
  });
}

// --------------------
// Modals
// --------------------
function openCreate(){
  $("modalCreateBackdrop").style.display = "flex";
  document.body.style.overflow = "hidden";
}
function closeCreate(){
  $("modalCreateBackdrop").style.display = "none";
  document.body.style.overflow = "";
}

function openDetailsBackdrop(){
  $("modalDetailsBackdrop").style.display = "flex";
  document.body.style.overflow = "hidden";
}
function closeDetailsBackdrop(){
  $("modalDetailsBackdrop").style.display = "none";
  document.body.style.overflow = "";
}

// --------------------
// Create modal reset
// --------------------
function resetCreate(){
  setMsg("createMsg","");

  fillCustomerSelect("customerSelect", null);
  fillCompanyForCustomer("companySelect", null, null);
  fillVehiclesForCustomer("vehicleSelect", null, null);
  fillMechanics("mechanicSelect", null);

  $("woStatus").value = "OPEN";
  $("woDesc").value = "";

  // limpiar inputs inline
  $("custName").value = "";
  $("custPhone").value = "";
  $("custEmail").value = "";

  $("companyName").value = "";

  $("vehVin").value = "";
  $("vehUnit").value = "";
  $("vehMake").value = "";
  $("vehModel").value = "";
  $("vehYear").value = "";

  // ocultar boxes
  $("newCustomerBox").style.display = "none";
  $("newCompanyBox").style.display = "none";
  $("newVehicleBox").style.display = "none";
}

// --------------------
// Inline create helpers
// --------------------
function getSelectedCustomerIdFromCreate(){
  const id = parseInt($("customerSelect")?.value || "", 10);
  return Number.isFinite(id) ? id : null;
}

async function createCustomerInline(){
  const name = ($("custName").value || "").trim();
  const phone = ($("custPhone").value || "").trim();
  const email = ($("custEmail").value || "").trim();

  if (!name){
    setMsg("createMsg","Customer name is required.", true);
    return;
  }

  setMsg("createMsg","Creating customer...");
  const payload = { name, phone: phone || null, email: email || null };

  const created = await apiFetch(urlCustomers(), {
    method:"POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });

  await loadCustomers();
  fillCustomerSelect("customerSelect", created.id);

  fillCompanyForCustomer("companySelect", created.id, null);
  fillVehiclesForCustomer("vehicleSelect", created.id, null);

  $("newCustomerBox").style.display = "none";
  setMsg("createMsg","Customer created and selected.", false);
}

async function createCompanyInline(){
  const custId = getSelectedCustomerIdFromCreate();
  if (!custId){
    setMsg("createMsg","Select a customer first.", true);
    return;
  }

  const name = ($("companyName").value || "").trim();
  if (!name){
    setMsg("createMsg","Company name is required.", true);
    return;
  }

  setMsg("createMsg","Creating company...");
  const company = await apiFetch(urlCompanies(), {
    method:"POST",
    headers: authHeaders(),
    body: JSON.stringify({ name }),
  });

  // Link many-to-many: intentamos varias rutas comunes
  const linkCandidates = [
    `${API_BASE}/customers/${custId}/companies/${company.id}`,
    `/customers/${custId}/companies/${company.id}`,
    `/api/customers/${custId}/companies/${company.id}`,
  ];

  let linked = false;
  for (const u of linkCandidates){
    try{
      await apiFetch(u, { method:"POST", headers: authHeaders() });
      linked = true;
      break;
    }catch{}
  }
  if (!linked){
    throw new Error("Company created but link to customer failed. Verify link endpoint.");
  }

  await loadCustomers();
  fillCustomerSelect("customerSelect", custId);
  fillCompanyForCustomer("companySelect", custId, company.id);

  $("newCompanyBox").style.display = "none";
  setMsg("createMsg","Company created and linked.", false);
}

async function createVehicleInline(){
  const custId = getSelectedCustomerIdFromCreate();
  if (!custId){
    setMsg("createMsg","Select a customer first.", true);
    return;
  }

  const vin = ($("vehVin").value || "").trim();
  const unit_number = ($("vehUnit").value || "").trim();
  const make = ($("vehMake").value || "").trim();
  const model = ($("vehModel").value || "").trim();
  const yearRaw = ($("vehYear").value || "").trim();

  let year = null;
  if (yearRaw){
    const y = parseInt(yearRaw, 10);
    if (!Number.isFinite(y) || y < 1900 || y > 2100){
      setMsg("createMsg","Year invalid. Use 1900-2100.", true);
      return;
    }
    year = y;
  }

  setMsg("createMsg","Creating vehicle...");
  const payload = {
    vin: vin || null,
    unit_number: unit_number || null,
    make: make || null,
    model: model || null,
    year,
    customer_id: custId,
  };

  const created = await apiFetch(urlVehicles(), {
    method:"POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });

  await loadVehicles();
  fillVehiclesForCustomer("vehicleSelect", custId, created.id);

  $("newVehicleBox").style.display = "none";
  setMsg("createMsg","Vehicle created and selected.", false);
}

// --------------------
// Create work order
// --------------------
async function createWorkOrder(){
  const custId = parseInt($("customerSelect").value || "", 10);
  const compId = parseInt($("companySelect").value || "", 10);
  const vehId  = parseInt($("vehicleSelect").value || "", 10);
  const mechId = parseInt($("mechanicSelect").value || "", 10);

  const status = ($("woStatus").value || "OPEN").trim();
  const description = ($("woDesc").value || "").trim();

  if (!description){
    setMsg("createMsg","Description is required.", true);
    return;
  }

  const payload = {
    description,
    status,
    customer_id: Number.isFinite(custId) ? custId : null,
    company_id: Number.isFinite(compId) ? compId : null,
    vehicle_id: Number.isFinite(vehId) ? vehId : null,
    mechanic_id: Number.isFinite(mechId) ? mechId : null,
  };

  setMsg("createMsg","Creating work order...");
  const created = await apiFetch(urlWorkOrders(), {
    method:"POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });

  setMsg("createMsg", `Created ${created.work_order_number || ("WO-"+created.id)}.`, false);

  await loadWorkOrders();
  renderWorkOrders();
  closeCreate();
}

// --------------------
// DETAILS render
// --------------------
function renderDetails(wo){
  CURRENT_WO = wo;

  const title = wo.work_order_number || `WO-${wo.id}`;
  $("detailsTitle").textContent = `Work Order ${title}`;

  $("detailsStatus").value = (wo.status || "OPEN");
  $("detailsDesc").value = (wo.description || "");

  const custId = wo.customer_id || wo.customer?.id || null;

  fillCustomerSelect("detailsCustomer", custId);
  fillCompanyForCustomer("detailsCompany", custId, wo.company_id || wo.company?.id || null);
  fillVehiclesForCustomer("detailsVehicle", custId, wo.vehicle_id || wo.vehicle?.id || null);

  fillMechanics("detailsMechanic", wo.mechanic_id || wo.mechanic?.id || null);

  const custName = wo.customer?.name || "-";
  const compName = wo.company?.name || "-";
  const vehTxt = wo.vehicle ? fmtVehicle(wo.vehicle) : "-";

  $("summaryBox").innerHTML =
    `<div class="muted">Customer: <b>${escapeHtml(custName)}</b></div>
     <div class="muted">Company: <b>${escapeHtml(compName)}</b></div>
     <div class="muted">Vehicle: <b>${escapeHtml(vehTxt)}</b></div>
     <div class="muted">Status: <b>${escapeHtml(wo.status || "-")}</b></div>`;

  const createdAt = wo.created_at ? String(wo.created_at) : "";
  $("detailsMeta").textContent = createdAt ? `Created: ${createdAt}` : "";

  renderWOItems(wo);
  renderWOLabor(wo);
  renderInvoice(wo);
  updateCloseWorkOrderButton(wo);
}

function renderWOItems(wo){
  const tb = $("woItemsTbody");
  const items = wo.items || [];

  if (!items.length){
    tb.innerHTML = `<tr><td colspan="7" class="muted">No parts added yet.</td></tr>`;
    return;
  }

  tb.innerHTML = items.map(it=>{
    const qty = Number(it.qty ?? 0);
    const unit = Number(it.unit_price_snapshot ?? 0);
    const cost = Number(it.cost_snapshot ?? 0);
    const markup = cost > 0 ? (((unit - cost) / cost) * 100) : 0;
    const total = Number(it.line_total ?? (qty*unit));

    return `
      <tr>
        <td>${escapeHtml(it.description_snapshot || "")}</td>
        <td class="rightNum"><input data-woitem-qty="${it.id}" style="min-width:90px;" value="${qty}" /></td>
        <td class="rightNum">${money(cost)}</td>
        <td class="rightNum"><input data-woitem-markup="${it.id}" style="min-width:90px;" value="${markup.toFixed(2)}" /></td>
        <td class="rightNum"><input data-woitem-unit="${it.id}" style="min-width:100px;" value="${unit.toFixed(2)}" /></td>
        <td class="rightNum">${money(total)}</td>
        <td>
          <div class="actions">
            <button class="ghost" data-woitem-save="${it.id}">Save Qty</button>
            <button class="ghost" data-woitem-price="${it.id}">Save Price</button>
            <button class="secondary" data-woitem-del="${it.id}">Delete</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  tb.querySelectorAll("button[data-woitem-save]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      const woItemId = parseInt(b.getAttribute("data-woitem-save"), 10);
      const inp = tb.querySelector(`input[data-woitem-qty="${woItemId}"]`);
      const newQty = (inp?.value || "").trim();
      try{
        setMsg("detailsMsg","Updating qty...");
        await apiFetch(urlWOItem(CURRENT_WO.id, woItemId), {
          method:"PATCH",
          headers: authHeaders(),
          body: JSON.stringify({ qty: newQty }),
        });
        await refreshDetails();
        setMsg("detailsMsg","Qty updated.", false);
      }catch(e){ setMsg("detailsMsg", e.message || "Error updating qty", true); }
    });
  });

  tb.querySelectorAll("button[data-woitem-price]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      const woItemId = parseInt(b.getAttribute("data-woitem-price"), 10);
      const unitInput = tb.querySelector(`input[data-woitem-unit="${woItemId}"]`);
      const markupInput = tb.querySelector(`input[data-woitem-markup="${woItemId}"]`);
      try{
        setMsg("detailsMsg","Updating price...");
        await apiFetch(urlWOItemPricing(CURRENT_WO.id, woItemId), {
          method:"PATCH",
          headers: authHeaders(),
          body: JSON.stringify({ unit_price: unitInput?.value || null, markup_percent: markupInput?.value || null }),
        });
        await refreshDetails();
        setMsg("detailsMsg","Price updated.", false);
      }catch(e){ setMsg("detailsMsg", e.message || "Error updating price", true); }
    });
  });

  tb.querySelectorAll("button[data-woitem-del]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      const woItemId = parseInt(b.getAttribute("data-woitem-del"), 10);
      if (!confirm("Delete this part line? Stock will be returned.")) return;
      try{
        setMsg("detailsMsg","Deleting item...");
        await apiFetch(urlWOItem(CURRENT_WO.id, woItemId), { method:"DELETE", headers: authHeaders() });
        await refreshDetails();
        setMsg("detailsMsg","Item deleted.", false);
      }catch(e){ setMsg("detailsMsg", e.message || "Error deleting item", true); }
    });
  });
}

function renderWOLabor(wo){
  const tb = $("laborTbody");
  if (!tb) return;
  const rows = wo.labors || [];
  if (!rows.length){
    tb.innerHTML = `<tr><td colspan="6" class="muted">No labor lines yet.</td></tr>`;
    return;
  }
  tb.innerHTML = rows.map(lb => {
    const options = [`<option value="">System mechanic...</option>`].concat(
      USERS
        .filter(u => u.is_active !== false)
        .sort((a,b) => (a.full_name||a.username||"").localeCompare(b.full_name||b.username||""))
        .map(u => `<option value="${u.id}" ${Number(lb.mechanic_id||0)===Number(u.id)?"selected":""}>${escapeHtml(u.full_name || u.username)}</option>`)
    ).join("");

    return `
      <tr>
        <td><input data-labor-desc="${lb.id}" style="min-width:260px;" value="${escapeHtml(lb.description || "")}" /></td>
        <td>
          <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
            <select data-labor-mechanic="${lb.id}" style="min-width:180px;">${options}</select>
            <input data-labor-mechanic-name="${lb.id}" style="min-width:180px;" placeholder="Custom mechanic name" value="${escapeHtml(lb.mechanic_name || "")}" />
          </div>
          <div class="muted small" style="margin-top:4px;">Current: ${escapeHtml(laborMechanicLabel(lb))}</div>
        </td>
        <td class="rightNum"><input data-labor-hours="${lb.id}" style="min-width:90px;" value="${Number(lb.hours ?? 0)}" /></td>
        <td class="rightNum"><input data-labor-rate="${lb.id}" style="min-width:100px;" value="${Number(lb.rate ?? 0).toFixed(2)}" /></td>
        <td class="rightNum">${money(lb.line_total)}</td>
        <td><div class="actions"><button class="ghost" data-labor-save="${lb.id}">Save</button><button class="secondary" data-labor-del="${lb.id}">Delete</button></div></td>
      </tr>
    `;
  }).join("");

  tb.querySelectorAll("button[data-labor-save]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      const id = parseInt(b.getAttribute("data-labor-save"), 10);
      try{
        setMsg("detailsMsg","Saving labor...");
        await apiFetch(urlWOLabor(CURRENT_WO.id, id), {
          method:"PATCH", headers: authHeaders(),
          body: JSON.stringify({
            description: tb.querySelector(`input[data-labor-desc="${id}"]`)?.value || "",
            mechanic_id: tb.querySelector(`select[data-labor-mechanic="${id}"]`)?.value || null,
            mechanic_name: tb.querySelector(`input[data-labor-mechanic-name="${id}"]`)?.value || null,
            hours: tb.querySelector(`input[data-labor-hours="${id}"]`)?.value || 0,
            rate: tb.querySelector(`input[data-labor-rate="${id}"]`)?.value || 0,
          })
        });
        await refreshDetails();
        setMsg("detailsMsg","Labor updated.", false);
      }catch(e){ setMsg("detailsMsg", e.message || "Error updating labor", true); }
    });
  });
  tb.querySelectorAll("button[data-labor-del]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      const id = parseInt(b.getAttribute("data-labor-del"), 10);
      if (!confirm("Delete this labor line?")) return;
      try{
        await apiFetch(urlWOLabor(CURRENT_WO.id, id), { method:"DELETE", headers: authHeaders() });
        await refreshDetails();
      }catch(e){ setMsg("detailsMsg", e.message || "Error deleting labor", true); }
    });
  });
}

function renderInvoice(wo){
  const inv = wo.invoice || null;

  if (!inv){
    $("invoiceSummary").textContent = "No invoice yet.";
    $("invoiceItemsTbody").innerHTML = `<tr><td colspan="5" class="muted">No invoice yet.</td></tr>`;
    return;
  }

  $("invoiceSummary").innerHTML =
    `<div class="muted">Invoice #: <b>${escapeHtml(inv.invoice_number || "-")}</b></div>
     <div class="muted">Status: <b>${escapeHtml(inv.status || "-")}</b></div>
     <div class="muted">Subtotal: <b>${money(inv.subtotal)}</b></div>
     <div class="muted">Tax: <b>${money(inv.tax)}</b></div>
     <div class="muted">Total: <b>${money(inv.total)}</b></div>`;

  const items = inv.items || [];
  if (!items.length){
    $("invoiceItemsTbody").innerHTML = `<tr><td colspan="5" class="muted">Invoice has no items.</td></tr>`;
    return;
  }

  $("invoiceItemsTbody").innerHTML = items.map(it=>{
    return `
      <tr>
        <td>${escapeHtml(it.item_type || "")}</td>
        <td>${escapeHtml(it.description || "")}</td>
        <td class="rightNum">${Number(it.qty ?? 0)}</td>
        <td class="rightNum">${money(it.unit_price)}</td>
        <td class="rightNum">${money(it.line_total)}</td>
      </tr>
    `;
  }).join("");
}

// --------------------
// DETAILS open/refresh
// --------------------
async function openDetails(id){
  setTab("info");
  setMsg("detailsMsg","Loading work order...");
  openDetailsBackdrop();

  try{
    const wo = await fetchWorkOrder(id);
    renderDetails(wo);
    renderInvResults([]);
    $("invSearch").value = "";
    setMsg("detailsMsg","",false);
  }catch(e){
    CURRENT_WO = null;
    renderInvResults([]);
    setMsg("detailsMsg", e.message || "Error loading work order", true);
  }
}

async function refreshDetails(){
  if (!CURRENT_WO?.id) return;
  const wo = await fetchWorkOrder(CURRENT_WO.id);
  renderDetails(wo);
}

// --------------------
// DETAILS save actions
// --------------------
async function saveHeader(){
  if (!CURRENT_WO?.id) return;

  const status = ($("detailsStatus").value || "OPEN").trim();
  const mechId = parseInt($("detailsMechanic").value || "", 10);

  try{
    setMsg("detailsMsg","Saving header...");

    // status endpoint: PUT /work-orders/{id}/status
    await apiFetch(urlWOStatus(CURRENT_WO.id), {
      method:"PUT",
      headers: authHeaders(),
      body: JSON.stringify({ status }),
    });

    // mechanic via PATCH /work-orders/{id}
    await apiFetch(urlWO(CURRENT_WO.id), {
      method:"PATCH",
      headers: authHeaders(),
      body: JSON.stringify({ mechanic_id: Number.isFinite(mechId) ? mechId : null }),
    });

    await refreshDetails();
    setMsg("detailsMsg","Saved.", false);
  }catch(e){
    setMsg("detailsMsg", e.message || "Error saving header", true);
  }
}

async function saveDesc(){
  if (!CURRENT_WO?.id) return;

  const description = ($("detailsDesc").value || "").trim();
  if (!description){
    setMsg("detailsMsg","Description cannot be empty.", true);
    return;
  }

  try{
    setMsg("detailsMsg","Saving description...");
    await apiFetch(urlWO(CURRENT_WO.id), {
      method:"PATCH",
      headers: authHeaders(),
      body: JSON.stringify({ description }),
    });
    await refreshDetails();
    setMsg("detailsMsg","Description saved.", false);
  }catch(e){
    setMsg("detailsMsg", e.message || "Error saving description", true);
  }
}

async function saveLinks(){
  if (!CURRENT_WO?.id) return;

  const custId = parseInt($("detailsCustomer").value || "", 10);
  const compId = parseInt($("detailsCompany").value || "", 10);
  const vehId  = parseInt($("detailsVehicle").value || "", 10);

  try{
    setMsg("detailsMsg","Saving links...");
    await apiFetch(urlWO(CURRENT_WO.id), {
      method:"PATCH",
      headers: authHeaders(),
      body: JSON.stringify({
        customer_id: Number.isFinite(custId) ? custId : null,
        company_id: Number.isFinite(compId) ? compId : null,
        vehicle_id: Number.isFinite(vehId) ? vehId : null,
      }),
    });
    await refreshDetails();
    setMsg("detailsMsg","Links saved.", false);
  }catch(e){
    setMsg("detailsMsg", e.message || "Error saving links", true);
  }
}

// --------------------
// PARTS: search + add
// --------------------
function renderInvResults(rows){
  const tb = $("invResults");
  if (!tb) return;
  const items = Array.isArray(rows) ? rows : (rows?.items || []);

  if (!items.length){
    tb.innerHTML = `<tr><td colspan="7" class="muted">No inventory results.</td></tr>`;
    return;
  }

  tb.innerHTML = items.slice(0, 30).map(it=>{
    const onHand = Number(it.quantity_in_stock ?? it.stock ?? 0);
    const code = it.part_code || it.sku || `#${it.id}`;
    const name = it.part_name || it.name || it.description || `Item #${it.id}`;
    const cost = Number(it.cost_price ?? 0);
    const base = Number(it.sale_price_base ?? it.price ?? 0);
    const markup = cost > 0 ? (((base - cost) / cost) * 100) : 0;

    return `
      <tr>
        <td>${escapeHtml(code)}</td>
        <td>${escapeHtml(name)}</td>
        <td class="rightNum">${onHand}</td>
        <td class="rightNum">${money(cost)}</td>
        <td class="rightNum"><input data-inv-markup="${it.id}" style="min-width:90px;" value="${markup.toFixed(2)}" /></td>
        <td class="rightNum"><input data-inv-unit="${it.id}" style="min-width:100px;" value="${base.toFixed(2)}" /></td>
        <td class="rightNum"><input data-inv-qty="${it.id}" style="min-width:90px;" value="1" /></td>
        <td><button class="ghost" data-add-inv="${it.id}">Add</button></td>
      </tr>
    `;
  }).join("");

  tb.querySelectorAll("button[data-add-inv]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      if (!CURRENT_WO?.id){ setMsg("detailsMsg","Open a work order first.", true); return; }
      const invId = parseInt(b.getAttribute("data-add-inv"), 10);
      const qty = (tb.querySelector(`input[data-inv-qty="${invId}"]`)?.value || "1").trim();
      const unit_price = (tb.querySelector(`input[data-inv-unit="${invId}"]`)?.value || "0").trim();
      const markup_percent = (tb.querySelector(`input[data-inv-markup="${invId}"]`)?.value || "0").trim();
      try{
        setMsg("detailsMsg","Adding part (this will decrement stock)...");
        await apiFetch(urlWOItems(CURRENT_WO.id), {
          method:"POST",
          headers: authHeaders(),
          body: JSON.stringify({ inventory_item_id: invId, qty, unit_price, markup_percent }),
        });
        await refreshDetails();
        setMsg("detailsMsg","Part added.", false);
        setTab("parts");
      }catch(e){ setMsg("detailsMsg", e.message || "Error adding part", true); }
    });
  });
}

async function doInvSearch(){
  if (!CURRENT_WO?.id){
    setMsg("detailsMsg", "Open a work order first.", true);
    return;
  }

  const q = ($("invSearch")?.value || "").trim();

  if (!q){
    renderInvResults([]);
    setMsg("detailsMsg", "Type a part name or part number.", false);
    return;
  }

  try{
    setMsg("detailsMsg", "Searching inventory...");
    const rows = await inventorySearch(q);
    renderInvResults(rows);
    setMsg("detailsMsg", rows?.length ? "" : "No inventory results.", false);
  }catch(e){
    console.error(e);
    renderInvResults([]);
    setMsg("detailsMsg", e.message || "Error searching inventory.", true);
  }
}

// --------------------
// PRINT
// --------------------
function buildPrintableHtml(wo){
  const parts = (wo.items || []).map(it => `<tr><td>${escapeHtml(it.description_snapshot || "")}</td><td style="text-align:right;">${Number(it.qty||0)}</td><td style="text-align:right;">${money(it.unit_price_snapshot)}</td><td style="text-align:right;">${money(it.line_total)}</td></tr>`).join("") || `<tr><td colspan="4">No parts.</td></tr>`;
  const labors = (wo.labors || []).map(lb => `<tr><td>${escapeHtml(lb.description || "")}</td><td style="text-align:right;">${money(lb.line_total)}</td></tr>`).join("") || `<tr><td colspan="2">No labor.</td></tr>`;
  const inv = wo.invoice || {};
  const total = inv.total ?? ((wo.items || []).reduce((a,b)=>a+num(b.line_total),0) + (wo.labors || []).reduce((a,b)=>a+num(b.line_total),0));
  return `<!DOCTYPE html><html><head><title>${escapeHtml(wo.work_order_number || `WO-${wo.id}`)}</title><style>body{font-family:Arial,sans-serif;padding:24px;color:#111} h1,h2,h3{margin:0 0 8px} .meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0 18px} table{width:100%;border-collapse:collapse;margin-top:8px} th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left} .tot{margin-top:18px;font-size:18px;font-weight:700;text-align:right}</style></head><body><h1>Work Order ${escapeHtml(wo.work_order_number || `WO-${wo.id}`)}</h1><div class="meta"><div><b>Customer:</b> ${escapeHtml(wo.customer?.name || "-")}</div><div><b>Company:</b> ${escapeHtml(wo.company?.name || "-")}</div><div><b>Vehicle:</b> ${escapeHtml(wo.vehicle ? fmtVehicle(wo.vehicle) : "-")}</div><div><b>Status:</b> ${escapeHtml(wo.status || "-")}</div><div><b>Mechanic:</b> ${escapeHtml(wo.mechanic?.full_name || wo.mechanic?.username || "-")}</div><div><b>Date:</b> ${escapeHtml(String(wo.created_at || ""))}</div></div><h3>Description</h3><div>${escapeHtml(wo.description || "-")}</div><h3 style="margin-top:20px;">Parts</h3><table><thead><tr><th>Description</th><th style="text-align:right;">Qty</th><th style="text-align:right;">Unit</th><th style="text-align:right;">Total</th></tr></thead><tbody>${parts}</tbody></table><h3 style="margin-top:20px;">Labor</h3><table><thead><tr><th>Description</th><th style="text-align:right;">Amount</th></tr></thead><tbody>${labors}</tbody></table><div class="tot">Total: ${money(total)}</div></body></html>`;
}

function printCurrentWorkOrder(){
  if (!CURRENT_WO?.id) return;
  const pdfUrl = urlWOPdf(CURRENT_WO.id);

  let frame = document.getElementById("printPdfFrame");
  if (!frame){
    frame = document.createElement("iframe");
    frame.id = "printPdfFrame";
    frame.style.position = "fixed";
    frame.style.right = "0";
    frame.style.bottom = "0";
    frame.style.width = "0";
    frame.style.height = "0";
    frame.style.border = "0";
    document.body.appendChild(frame);
  }

  setMsg("detailsMsg", "Preparing print...");

  frame.onload = () => {
    try{
      frame.contentWindow.focus();
      frame.contentWindow.print();
      setMsg("detailsMsg", "", false);
    }catch(e){
      openPdfWithAuth(pdfUrl).catch(err => alert(err.message || "Could not generate PDF"));
      setMsg("detailsMsg", "Opened PDF for printing.", false);
    }
  };

  frame.src = pdfUrl + (pdfUrl.includes("?") ? "&" : "?") + "print=1&t=" + Date.now();
}

// --------------------
// INVOICE: create
// --------------------
async function createInvoice(){
  if (!CURRENT_WO?.id) return;
  try{
    setMsg("detailsMsg","Creating invoice...");
    await apiFetch(urlCreateInvoice(CURRENT_WO.id), {
      method:"POST",
      headers: authHeaders(),
    });
    await refreshDetails();
    setMsg("detailsMsg","Invoice created.", false);
    setTab("invoice");
  }catch(e){
    setMsg("detailsMsg", e.message || "Error creating invoice", true);
  }
}

// --------------------
// Init
// --------------------
async function init(){
  // header buttons
  $("backBtn").addEventListener("click", () => window.location.href = "/static/dashboard.html");
  $("logoutBtn").addEventListener("click", () => {
    localStorage.removeItem("token");
    localStorage.removeItem("access_token");
    window.location.href = "/static/index.html";
  });

  // list refresh
  $("refreshBtn").addEventListener("click", async ()=>{
    try{
      setMsg("listMsg","Refreshing...");
      await loadWorkOrders();
      renderWorkOrders();
      setMsg("listMsg", `Loaded ${WORK_ORDERS.length} work orders.`);
    }catch(e){
      setMsg("listMsg", e.message || "Error loading work orders", true);
    }
  });

  $("q").addEventListener("keydown", (e)=>{ if (e.key==="Enter") $("refreshBtn").click(); });
  $("statusFilter").addEventListener("change", ()=>$("refreshBtn").click());

  // create modal open/close
  $("newBtn").addEventListener("click", ()=>{ resetCreate(); openCreate(); });
  $("closeCreateBtn").addEventListener("click", closeCreate);
  $("modalCreateBackdrop").addEventListener("click", (e)=>{ if (e.target === $("modalCreateBackdrop")) closeCreate(); });

  $("resetCreateBtn").addEventListener("click", resetCreate);

  // inline toggles
  $("newCustomerToggleBtn").addEventListener("click", ()=>{
    const box = $("newCustomerBox");
    box.style.display = (box.style.display === "none" || !box.style.display) ? "block" : "none";
  });
  $("newCompanyToggleBtn").addEventListener("click", ()=>{
    const box = $("newCompanyBox");
    box.style.display = (box.style.display === "none" || !box.style.display) ? "block" : "none";
  });
  $("newVehicleToggleBtn").addEventListener("click", ()=>{
    const box = $("newVehicleBox");
    box.style.display = (box.style.display === "none" || !box.style.display) ? "block" : "none";
  });

  // create inline actions
  $("createCustomerBtn").addEventListener("click", async ()=>{
    try{ await createCustomerInline(); }
    catch(e){ setMsg("createMsg", e.message || "Error creating customer", true); }
  });
  $("createCompanyBtn").addEventListener("click", async ()=>{
    try{ await createCompanyInline(); }
    catch(e){ setMsg("createMsg", e.message || "Error creating company", true); }
  });
  $("createVehicleBtn").addEventListener("click", async ()=>{
    try{ await createVehicleInline(); }
    catch(e){ setMsg("createMsg", e.message || "Error creating vehicle", true); }
  });

  // on customer change -> update company/vehicle
  $("customerSelect").addEventListener("change", ()=>{
    const custId = parseInt($("customerSelect").value || "", 10);
    const cid = Number.isFinite(custId) ? custId : null;
    fillCompanyForCustomer("companySelect", cid, null);
    fillVehiclesForCustomer("vehicleSelect", cid, null);
  });

  // create WO
  $("createWoBtn").addEventListener("click", async ()=>{
    try{ await createWorkOrder(); }
    catch(e){ setMsg("createMsg", e.message || "Error creating work order", true); }
  });

  // details modal close
  $("closeDetailsBtn").addEventListener("click", closeDetailsBackdrop);
  $("closeDetailsBtn2").addEventListener("click", closeDetailsBackdrop);
  $("modalDetailsBackdrop").addEventListener("click", (e)=>{ if (e.target === $("modalDetailsBackdrop")) closeDetailsBackdrop(); });

  // tabs
  $("tabInfo").addEventListener("click", ()=>setTab("info"));
  $("tabParts").addEventListener("click", ()=>setTab("parts"));
  $("tabLabor").addEventListener("click", ()=>setTab("labor"));
  $("tabInvoice").addEventListener("click", ()=>setTab("invoice"));

  // details actions
  $("printBtn").addEventListener("click", printCurrentWorkOrder);
  $("pdfBtn").addEventListener("click", ()=>{
    if (!CURRENT_WO?.id) return;
    const pdfUrl = urlWOPdf(CURRENT_WO.id);
    openPdfWithAuth(pdfUrl).catch(e => alert(e.message || "Could not generate PDF"));
  });

  $("detailsRefreshBtn").addEventListener("click", async ()=>{
    try{
      setMsg("detailsMsg","Refreshing...");
      await refreshDetails();
      setMsg("detailsMsg","",false);
    }catch(e){
      setMsg("detailsMsg", e.message || "Error refreshing", true);
    }
  });

  $("saveHeaderBtn").addEventListener("click", saveHeader);
  $("saveDescBtn").addEventListener("click", saveDesc);
  $("saveLinksBtn").addEventListener("click", saveLinks);

  // details customer dependency
  $("detailsCustomer").addEventListener("change", ()=>{
    const custId = parseInt($("detailsCustomer").value || "", 10);
    const cid = Number.isFinite(custId) ? custId : null;
    fillCompanyForCustomer("detailsCompany", cid, null);
    fillVehiclesForCustomer("detailsVehicle", cid, null);
  });

  // filter inputs for selects
  bindFilterInput("customerSearch", "customerSelect", `<option value="">Select customer...</option>`);
  bindFilterInput("companySearch", "companySelect", `<option value="">Select company (optional)...</option>`);
  bindFilterInput("vehicleSearch", "vehicleSelect", `<option value="">Select vehicle (optional)...</option>`);
  bindFilterInput("detailsCustomerSearch", "detailsCustomer", `<option value="">Select customer...</option>`);
  bindFilterInput("detailsCompanySearch", "detailsCompany", `<option value="">Select company (optional)...</option>`);
  bindFilterInput("detailsVehicleSearch", "detailsVehicle", `<option value="">Select vehicle (optional)...</option>`);

  // labor
  $("addLaborBtn").addEventListener("click", async ()=>{
    if (!CURRENT_WO?.id) return setMsg("detailsMsg", "Open a work order first.", true);
    try{
      setMsg("detailsMsg", "Adding labor...");
      await apiFetch(urlWOLabors(CURRENT_WO.id), {
        method:"POST", headers: authHeaders(),
        body: JSON.stringify({
          description: $("laborDesc").value || "",
          mechanic_id: $("laborMechanic").value || null,
          mechanic_name: $("laborMechanicName").value || null,
          hours: $("laborHours").value || 0,
          rate: $("laborRate").value || 0
        })
      });
      $("laborDesc").value = ""; $("laborMechanic").value = ""; $("laborMechanicName").value = ""; $("laborHours").value = "1"; $("laborRate").value = "0";
      await refreshDetails();
      setTab("labor");
      setMsg("detailsMsg", "Labor added.", false);
    }catch(e){ setMsg("detailsMsg", e.message || "Error adding labor", true); }
  });

  // parts
  $("invSearchBtn").addEventListener("click", doInvSearch);
  $("invSearch").addEventListener("keydown", (e)=>{ if (e.key==="Enter") doInvSearch(); });

  // invoice
  $("createInvoiceBtn").addEventListener("click", createInvoice);
  $("closeWorkOrderBtn")?.addEventListener("click", closeWorkOrder);
  if ($("closeWorkOrderBtn")) $("closeWorkOrderBtn").disabled = true;

  // detect + load initial
  setMsg("listMsg","Detecting API routes...");
  await detectBase();

  try{
    setMsg("listMsg","Loading...");
    await Promise.all([loadCustomers(), loadVehicles(), loadUsers(), loadWorkOrders()]);

    // create modal selects
    fillCustomerSelect("customerSelect", null);
    fillCompanyForCustomer("companySelect", null, null);
    fillVehiclesForCustomer("vehicleSelect", null, null);
    fillMechanics("mechanicSelect", null);
    fillMechanics("laborMechanic", null);

    // details modal base (se rellenan al abrir)
    fillCustomerSelect("detailsCustomer", null);
    fillMechanics("detailsMechanic", null);

    renderWorkOrders();
    setMsg("listMsg", `Loaded ${WORK_ORDERS.length} work orders.`);
  }catch(e){
    setMsg("listMsg", e.message || "Error loading data", true);
    $("tbody").innerHTML = `<tr><td colspan="7" class="danger">${escapeHtml(e.message || "Error")}</td></tr>`;
  }
}

init();

// --------------------
// CLOSE WORK ORDER
// --------------------
function updateCloseWorkOrderButton(wo){
  const btn = $("closeWorkOrderBtn");
  if (!btn) return;

  const st = String(wo?.status || "").toUpperCase();
  const closable = st === "OPEN" || st === "IN_PROGRESS";

  btn.disabled = !closable;
  btn.classList.remove("is-hidden");
  btn.textContent = closable ? "Close Work Order" : `Closed (${st || "DONE"})`;
  btn.title = closable ? "Set this work order to DONE" : "This work order is already closed";
}

async function closeWorkOrder(){
  if (!CURRENT_WO?.id) {
    setMsg("detailsMsg", "Open a work order first.", true);
    return;
  }

  const st = String(CURRENT_WO.status || "").toUpperCase();
  if (!(st === "OPEN" || st === "IN_PROGRESS")) {
    setMsg("detailsMsg", "This work order is already closed.", true);
    updateCloseWorkOrderButton(CURRENT_WO);
    return;
  }

  if (!confirm("Close this Work Order?\n\nStatus will change to DONE and parts/labor editing will be blocked.")) {
    return;
  }

  try{
    setMsg("detailsMsg", "Closing work order...");
    await apiFetch(urlWOStatus(CURRENT_WO.id), {
      method:"PUT",
      headers: authHeaders(),
      body: JSON.stringify({ status: "DONE" }),
    });
    await refreshDetails();
    await loadWorkOrders();
    renderWorkOrders();
    setMsg("detailsMsg", "Work order closed.", false);
    setTab("invoice");
  }catch(e){
    setMsg("detailsMsg", e.message || "Error closing work order", true);
  }
}
