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

// inventory search: intenta /inventory primero; si falla usa /inventory/items
async function inventorySearch(q){
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  try{
    const u = params.toString()
      ? `${ENDPOINTS.inventoryA(API_BASE)}?${params}`
      : ENDPOINTS.inventoryA(API_BASE);
    return await apiFetch(u, { headers: authHeaders() });
  }catch{
    const u2 = params.toString()
      ? `${ENDPOINTS.inventoryItems(API_BASE)}?${params}`
      : ENDPOINTS.inventoryItems(API_BASE);
    return await apiFetch(u2, { headers: authHeaders() });
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
    window.open(urlWOPdf(id), "_blank");
    return;
  }
  if (action === "open"){
    await openDetails(id);
  }
}

// --------------------
// Select fillers
// --------------------
function fillCustomerSelect(selectId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const opts = [`<option value="">Select customer...</option>`].concat(
    CUSTOMERS
      .filter(c => c.is_active !== false)
      .sort((a,b) => (a.name||"").localeCompare(b.name||""))
      .map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`)
  );
  sel.innerHTML = opts.join("");
  if (selectedId) sel.value = String(selectedId);
}

function getCustomerById(id){
  return CUSTOMERS.find(c => c.id === id) || null;
}

function fillCompanyForCustomer(selectId, customerId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const cust = customerId ? getCustomerById(customerId) : null;
  const companies = cust?.companies || [];

  const opts = [`<option value="">Select company (optional)...</option>`].concat(
    companies
      .filter(x => x.is_active !== false)
      .sort((a,b) => (a.name||"").localeCompare(b.name||""))
      .map(x => `<option value="${x.id}">${escapeHtml(x.name)}</option>`)
  );
  sel.innerHTML = opts.join("");
  if (selectedId) sel.value = String(selectedId);
}

function fillVehiclesForCustomer(selectId, customerId, selectedId=null){
  const sel = $(selectId);
  if (!sel) return;

  const list = customerId
    ? VEHICLES.filter(v => v.is_active !== false && v.customer_id === customerId)
    : [];

  const opts = [`<option value="">Select vehicle (optional)...</option>`].concat(
    list
      .sort((a,b) => (a.unit_number||"").localeCompare(b.unit_number||""))
      .map(v => `<option value="${v.id}">${escapeHtml(fmtVehicle(v))}</option>`)
  );
  sel.innerHTML = opts.join("");
  if (selectedId) sel.value = String(selectedId);
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

// --------------------
// Tabs
// --------------------
function setTab(tab){
  ["info","parts","invoice"].forEach(t=>{
    const b = t==="info" ? $("tabInfo") : t==="parts" ? $("tabParts") : $("tabInvoice");
    if (b) b.classList.toggle("active", t===tab);
  });

  $("panelInfo").classList.toggle("active", tab==="info");
  $("panelParts").classList.toggle("active", tab==="parts");
  $("panelInvoice").classList.toggle("active", tab==="invoice");
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
  renderInvoice(wo);
}

function renderWOItems(wo){
  const tb = $("woItemsTbody");
  const items = wo.items || [];

  if (!items.length){
    tb.innerHTML = `<tr><td colspan="5" class="muted">No parts added yet.</td></tr>`;
    return;
  }

  tb.innerHTML = items.map(it=>{
    const qty = Number(it.qty ?? 0);
    const unit = Number(it.unit_price_snapshot ?? 0);
    const total = Number(it.line_total ?? (qty*unit));

    return `
      <tr>
        <td>${escapeHtml(it.description_snapshot || "")}</td>
        <td class="rightNum">
          <input data-woitem-qty="${it.id}" style="min-width:90px;" value="${qty}" />
        </td>
        <td class="rightNum">${money(unit)}</td>
        <td class="rightNum">${money(total)}</td>
        <td>
          <div class="actions">
            <button class="ghost" data-woitem-save="${it.id}">Save Qty</button>
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
      }catch(e){
        setMsg("detailsMsg", e.message || "Error updating qty", true);
      }
    });
  });

  tb.querySelectorAll("button[data-woitem-del]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      const woItemId = parseInt(b.getAttribute("data-woitem-del"), 10);
      if (!confirm("Delete this part line? Stock will be returned.")) return;

      try{
        setMsg("detailsMsg","Deleting item...");
        await apiFetch(urlWOItem(CURRENT_WO.id, woItemId), {
          method:"DELETE",
          headers: authHeaders(),
        });
        await refreshDetails();
        setMsg("detailsMsg","Item deleted.", false);
      }catch(e){
        setMsg("detailsMsg", e.message || "Error deleting item", true);
      }
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
    setMsg("detailsMsg","",false);
  }catch(e){
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
  const items = Array.isArray(rows) ? rows : (rows?.items || []);

  if (!items.length){
    tb.innerHTML = `<tr><td colspan="6" class="muted">No inventory results.</td></tr>`;
    return;
  }

  tb.innerHTML = items.slice(0, 40).map(it=>{
    const onHand = Number(it.quantity_in_stock ?? it.stock ?? 0);
    const code = it.part_code || it.sku || `#${it.id}`;
    const name = it.part_name || it.name || it.description || `Item #${it.id}`;
    const price = Number(it.sale_price_base ?? it.price ?? 0);

    return `
      <tr>
        <td>${escapeHtml(code)}</td>
        <td>${escapeHtml(name)}</td>
        <td class="rightNum">${onHand}</td>
        <td class="rightNum">${money(price)}</td>
        <td class="rightNum">
          <input data-inv-qty="${it.id}" style="min-width:90px;" value="1" />
        </td>
        <td>
          <button class="ghost" data-add-inv="${it.id}">Add</button>
        </td>
      </tr>
    `;
  }).join("");

  tb.querySelectorAll("button[data-add-inv]").forEach(b=>{
    b.addEventListener("click", async ()=>{
      if (!CURRENT_WO?.id){
        setMsg("detailsMsg","Open a work order first.", true);
        return;
      }

      const invId = parseInt(b.getAttribute("data-add-inv"), 10);
      const inp = tb.querySelector(`input[data-inv-qty="${invId}"]`);
      const qty = (inp?.value || "1").trim();

      try{
        setMsg("detailsMsg","Adding part (this will decrement stock)...");
        await apiFetch(urlWOItems(CURRENT_WO.id), {
          method:"POST",
          headers: authHeaders(),
          body: JSON.stringify({ inventory_item_id: invId, qty }),
        });
        await refreshDetails();
        setMsg("detailsMsg","Part added.", false);
      }catch(e){
        setMsg("detailsMsg", e.message || "Error adding part", true);
      }
    });
  });
}

async function doInvSearch(){
  const q = ($("invSearch").value || "").trim();
  if (!q){
    setMsg("detailsMsg","Type something to search inventory.", true);
    return;
  }
  try{
    setMsg("detailsMsg","Searching inventory...");
    const rows = await inventorySearch(q);
    renderInvResults(rows);
    setMsg("detailsMsg","", false);
  }catch(e){
    setMsg("detailsMsg", e.message || "Inventory search failed", true);
  }
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
    window.location.href = "/static/login.html";
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
  $("tabInvoice").addEventListener("click", ()=>setTab("invoice"));

  // details actions
  $("pdfBtn").addEventListener("click", ()=>{
    if (!CURRENT_WO?.id) return;
    window.open(urlWOPdf(CURRENT_WO.id), "_blank");
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

  // parts
  $("invSearchBtn").addEventListener("click", doInvSearch);
  $("invSearch").addEventListener("keydown", (e)=>{ if (e.key==="Enter") doInvSearch(); });

  // invoice
  $("createInvoiceBtn").addEventListener("click", createInvoice);

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