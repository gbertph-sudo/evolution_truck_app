//* inventory.js - Evolution Truck (PRO + MEC) */
// UI en inglés. Comentarios en español.

const API = {
  items: "/api/inventory",
  suppliers: "/api/inventory/suppliers",
  adjust: (id) => `/api/inventory/${id}/adjust`,
  imagesList: (id) => `/api/inventory/${id}/images`,
  imageUpload: (id) => `/api/inventory/${id}/images/upload`,
  imageDelete: (imageId) => `/api/inventory/images/${imageId}`,

  // ✅ Movements global
  moves: "/api/inventory/movements",

  // ✅ Activate / Deactivate item
  active: (id) => `/api/inventory/${id}/active`,
};

const $ = (id) => document.getElementById(id);

function setPill(id, text) { const el = $(id); if (el) el.textContent = text; }
function setMsg(id, text, isError=false) {
  const el = $(id); if (!el) return;
  el.textContent = text;
  el.style.color = isError ? "crimson" : "green";
}
function toInt(val, fallback=0) { const n = parseInt(val, 10); return Number.isFinite(n) ? n : fallback; }
function toFloat(val, fallback=0) { const n = parseFloat(val); return Number.isFinite(n) ? n : fallback; }
function nowStamp() { return new Date().toLocaleString(); }

// ===============================
// SESSION / AUTH
// ===============================

function goLogin() {
  window.location.href = "/static/index.html";
}

function readToken() {
  return (
    localStorage.getItem("token") ||
    localStorage.getItem("access_token") ||
    localStorage.getItem("jwt") ||
    sessionStorage.getItem("token") ||
    sessionStorage.getItem("access_token") ||
    sessionStorage.getItem("jwt") ||
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
    console.warn("401 Unauthorized → redirecting to login");
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

// ===============================
// ROLE / PERMISSIONS (FRONT)
// ===============================

function parseJwt(token) {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

function getRoleNameFromToken() {
  const token = readToken();
  if (!token) return "";

  const payload = parseJwt(token);
  if (!payload) return "";

  const rn =
    payload.role_name ||
    payload.role ||
    (payload.role && payload.role.name) ||
    payload.roleName ||
    payload.rol ||
    "";

  if (typeof rn === "object" && rn && rn.name) return String(rn.name).toUpperCase();

  return String(rn || "").toUpperCase();
}

function isAdminRole(roleName) {
  return roleName === "ADMIN" || roleName === "SUPERADMIN";
}

let roleName = "";
let isAdminUser = false;

function applyPermissionsUI() {
  const navMoves = $("navMoves");
  const viewMoves = $("viewMoves");

  if (!isAdminUser) {
    if (navMoves) navMoves.style.display = "none";
    if (viewMoves) viewMoves.style.display = "none";
  } else {
    if (navMoves) navMoves.style.display = "";
  }
}

let items = [];
let currentItemId = null;
let suppliers = [];

// Movements
let moves = [];
let movesCount = 0;

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
  if (!res.ok) throw new Error(await res.text());
  try { return await res.json(); } catch { return null; }
}

/* Views */
function showView(name){
  const list = $("viewList");
  const form = $("viewForm");
  const movesView = $("viewMoves");

  if (!isAdminUser && name === "moves") name = "list";

  if (list)  list.style.display  = (name === "list")  ? "" : "none";
  if (form)  form.style.display  = (name === "form")  ? "" : "none";
  if (movesView) movesView.style.display = (name === "moves") ? "" : "none";
}

function setActiveTile(id){
  document.querySelectorAll(".tile").forEach(t => t.classList.remove("active"));
  const el = document.getElementById(id);
  if (el) el.classList.add("active");
}

/* ===== TILE COUNTERS ===== */
function setTileTitle(id, baseTitle, count, prefixIcon = "") {
  const tile = document.getElementById(id);
  if (!tile) return;
  const h3 = tile.querySelector("h3");
  if (!h3) return;
  const icon = prefixIcon ? `${prefixIcon} ` : "";
  const showCount = (count === "" || count === null || count === undefined) ? "" : ` (${count})`;
  h3.textContent = `${icon}${baseTitle}${showCount}`;
}

function applyTileAlerts(stats){
  const lowTile = document.getElementById("navLow");
  if (!lowTile) return;

  const danger = (stats.low > 0 || stats.out > 0);
  lowTile.classList.toggle("has-alert", danger);

  const btn = lowTile.querySelector("button");
  if (btn) {
    if (danger) {
      btn.style.background = "var(--et-red, #e10600)";
      btn.style.color = "#fff";
    } else {
      btn.style.background = "#eceff3";
      btn.style.color = "#2b2f36";
    }
  }
}

function computeStats(list){
  let low = 0;
  let out = 0;

  for (const it of list) {
    const qty = it.quantity_in_stock ?? 0;
    const min = it.minimum_stock ?? 0;
    if (qty <= 0) out++;
    if ((it.is_active !== false) && qty <= min) low++;
  }

  return { total: list.length, low, out };
}

function updateTilesFromItems(){
  const stats = computeStats(items);

  setTileTitle("navList", "All Items", stats.total, "📦");
  setTileTitle("navLow", "Low Stock", stats.low, "⚠️");

  if (isAdminUser) {
    setTileTitle("navMoves", "Movements", (movesCount ? movesCount : "—"), "🔄");
  }

  setTileTitle("navNew", "New Item", "", "➕");

  applyTileAlerts(stats);
}

/* Payloads */
function readCreatePayload() {
  return {
    part_code: $("part_code").value.trim(),
    part_name: $("part_name").value.trim(),
    brand: $("brand").value.trim() || null,
    category: $("category").value.trim() || null,
    sub_category: $("sub_category").value.trim() || null,
    oem_reference: $("oem_reference").value.trim() || null,

    quantity_in_stock: toInt($("quantity_in_stock").value, 0),
    minimum_stock: toInt($("minimum_stock").value, 0),
    reorder_quantity: toInt($("reorder_quantity").value, 0),

    location: $("location").value.trim() || null,
    cost_price: toFloat($("cost_price").value, 0),
    markup_percent: toFloat($("markup_percent").value, 0),
    sale_price_base: toFloat($("sale_price_base").value, 0),
    taxable: $("taxable").value === "true",

    supplier_id: $("supplier_id").value ? toInt($("supplier_id").value, null) : null,
    supplier_part_number: $("supplier_part_number").value.trim() || null,

    engine_type: $("engine_type").value.trim() || null,
    vehicle_make_model: $("vehicle_make_model") ? ($("vehicle_make_model").value.trim() || null) : null,

    description: $("description").value.trim() || null,
    technical_notes: $("technical_notes").value.trim() || null,
  };
}

function readUpdatePayload() {
  const payload = readCreatePayload();
  delete payload.part_code;
  delete payload.quantity_in_stock;
  return payload;
}

/* Form helpers */
function fillFormFromItem(item) {
  $("part_code").value = item.part_code ?? "";
  $("part_name").value = item.part_name ?? "";
  $("brand").value = item.brand ?? "";
  $("category").value = item.category ?? "";
  $("sub_category").value = item.sub_category ?? "";
  $("oem_reference").value = item.oem_reference ?? "";

  $("quantity_in_stock").value = item.quantity_in_stock ?? 0;
  $("minimum_stock").value = item.minimum_stock ?? 0;
  $("reorder_quantity").value = item.reorder_quantity ?? 0;

  $("location").value = item.location ?? "";
  $("cost_price").value = item.cost_price ?? 0;
  if ($("markup_percent")) $("markup_percent").value = item.markup_percent ?? 0;
  $("sale_price_base").value = item.sale_price_base ?? 0;
  $("taxable").value = String(item.taxable ?? true);

  $("supplier_id").value = item.supplier_id ?? "";
  $("supplier_part_number").value = item.supplier_part_number ?? "";

  $("engine_type").value = item.engine_type ?? "";
  if ($("vehicle_make_model")) {
    $("vehicle_make_model").value = item.vehicle_make_model ?? "";
  }

  $("description").value = item.description ?? "";
  $("technical_notes").value = item.technical_notes ?? "";
  calculateSalePrice();
}

function resetFormToNew() {
  currentItemId = null;
  $("inventoryForm").reset();

  $("formTitle").textContent = "Create / Edit Item";
  $("formMode").textContent = "New";

  $("btnOpenImages").disabled = true;
  $("btnAdjust").disabled = true;

  $("part_code").disabled = false;
  $("quantity_in_stock").disabled = false;

  setMsg("formMsg", "");
}

/* Table */
function statusChip(item) {
  const isActive = item.is_active !== false;
  const qty = item.quantity_in_stock ?? 0;
  const min = item.minimum_stock ?? 0;

  if (!isActive) return '<span class="chip inactive">INACTIVE</span>';
  if (qty <= 0) return '<span class="chip bad">OUT</span>';
  if (qty <= min) return '<span class="chip warn">LOW</span>';
  return '<span class="chip ok">OK</span>';
}

function renderTable(list) {
  const tbody = $("itemsTbody");
  if (!tbody) return;

  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">No items found.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(item => {
    const qty = item.quantity_in_stock ?? 0;
    const min = item.minimum_stock ?? 0;
    const isInactive = item.is_active === false;

    const adminButtons = isAdminUser
      ? (
          isInactive
            ? `<button class="secondary" type="button" data-act="activate" data-id="${item.id}">Activate</button>`
            : `<button class="danger" type="button" data-act="deact" data-id="${item.id}">Deactivate</button>`
        )
      : "";

    return `
      <tr class="${isInactive ? "inactive-row" : ""}">
        <td><b class="${isInactive ? "inactive-text" : ""}">${item.part_code ?? ""}</b></td>
        <td><span class="${isInactive ? "inactive-text" : ""}">${item.part_name ?? ""}</span></td>
        <td>${qty}</td>
        <td>${min}</td>
        <td>${statusChip(item)}</td>
        <td>
          <button class="ghost" type="button" data-act="edit" data-id="${item.id}">View / Edit</button>
          ${adminButtons}
        </td>
      </tr>
    `;
  }).join("");

  tbody.onclick = async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;

    const act = btn.dataset.act;
    const id = btn.dataset.id ? parseInt(btn.dataset.id, 10) : null;

    if (act === "edit" && id) {
      openEdit(id);
      return;
    }

    if (act === "deact" && id) {
      if (!isAdminUser) return;

      try {
        setPill("apiStatus", "API: updating...");
        await apiSend(API.active(id), "PATCH", { is_active: false });
        await loadInventory();
        setPill("apiStatus", "API: OK");
      } catch (err) {
        console.error(err);
        setPill("apiStatus", "API: ERROR");
        alert("Deactivate error. Check console.");
      }
      return;
    }

    if (act === "activate" && id) {
      if (!isAdminUser) return;

      try {
        setPill("apiStatus", "API: updating...");
        await apiSend(API.active(id), "PATCH", { is_active: true });
        await loadInventory();
        setPill("apiStatus", "API: OK");
      } catch (err) {
        console.error(err);
        setPill("apiStatus", "API: ERROR");
        alert("Activate error. Check console.");
      }
      return;
    }
  };
}

function applyFiltersAndRender() {
  const q = ($("searchBox").value || "").trim().toLowerCase();
  const b = ($("filterBrand").value || "").trim().toLowerCase();
  const c = ($("filterCategory").value || "").trim().toLowerCase();
  const lowOnly = $("lowStockOnly").checked;

  const filtered = items.filter(it => {
    const isActive = it.is_active !== false;
    const qty = it.quantity_in_stock ?? 0;
    const min = it.minimum_stock ?? 0;

    if (!isAdminUser && !isActive) return false;
    if (lowOnly && (!isActive || !(qty <= min))) return false;
    if (b && !String(it.brand ?? "").toLowerCase().includes(b)) return false;
    if (c && !String(it.category ?? "").toLowerCase().includes(c)) return false;

    if (!q) return true;

    const hay = [
      it.part_code, it.part_name, it.brand, it.category, it.sub_category, it.oem_reference
    ].map(x => String(x ?? "").toLowerCase()).join(" | ");

    return hay.includes(q);
  });

  renderTable(filtered);
  setPill("itemsCount", `Items: ${filtered.length}`);
}

/* Load */
async function loadInventory() {
  try {
    setPill("apiStatus", "API: checking...");
    const data = await apiGet(API.items);
    if (!data) return;

    items = Array.isArray(data) ? data : (data.items ?? []);

    setPill("apiStatus", "API: OK");
    setPill("itemsCount", `Items: ${items.length}`);

    const lr = $("lastRefresh");
    if (lr) lr.textContent = `Updated: ${nowStamp()}`;

    updateTilesFromItems();
    applyFiltersAndRender();
  } catch (err) {
    console.error(err);
    setPill("apiStatus", "API: ERROR");
    const tbody = $("itemsTbody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="muted">API error. Check console.</td></tr>';
  }
}

async function loadSuppliers() {
  try {
    const data = await apiGet(API.suppliers);
    if (!data) return;

    suppliers = Array.isArray(data) ? data : [];

    const sel = $("supplier_id");
    if (!sel) return;

    sel.innerHTML =
      '<option value="">— No supplier —</option>' +
      suppliers.map(s => `<option value="${s.id}">${s.name ?? `Supplier ${s.id}`}</option>`).join("");
  } catch (err) {
    console.error("Suppliers load error:", err);
  }
}

/* ===== MOVEMENTS ===== */
function formatMoveDate(x){
  if (!x) return "";
  try {
    const d = new Date(x);
    if (Number.isNaN(d.getTime())) return String(x);
    return d.toLocaleString();
  } catch {
    return String(x);
  }
}

function applyMovesFilters(list){
  const q = ($("movesSearch")?.value || "").trim().toLowerCase();
  const type = ($("movesType")?.value || "").trim().toUpperCase();
  const from = ($("movesFrom")?.value || "").trim();
  const to = ($("movesTo")?.value || "").trim();

  return list.filter(m => {
    const mt = String(m.movement_type || "").toUpperCase();
    const mtNormalized = mt === "ADJUSTMENT" ? "ADJUST" : mt;

    if (type && mtNormalized !== type) return false;

    const d = String(m.movement_date || m.created_at || "");
    if (from && d && d.slice(0,10) < from) return false;
    if (to && d && d.slice(0,10) > to) return false;

    if (!q) return true;

    const hay = [
      m.part_code, m.part_name, m.username, m.movement_notes
    ].map(x => String(x ?? "").toLowerCase()).join(" | ");

    return hay.includes(q);
  });
}

function renderMovesTable(list){
  const tbody = $("movesTbody");
  if (!tbody) return;

  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No movements found.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(m => {
    const who = m.username || (m.user_id ? `User #${m.user_id}` : "—");
    const typeLabel = String(m.movement_type || "").toUpperCase() === "ADJUSTMENT"
      ? "ADJUST"
      : String(m.movement_type || "").toUpperCase();

    return `
      <tr>
        <td>${formatMoveDate(m.movement_date || m.created_at)}</td>
        <td><b>${typeLabel}</b></td>
        <td>${m.quantity_moved ?? ""}</td>
        <td>${m.part_code ?? ""}</td>
        <td>${m.part_name ?? ""}</td>
        <td>${who}</td>
        <td>${m.movement_notes ?? ""}</td>
      </tr>
    `;
  }).join("");
}

async function loadMovements(){
  if (!isAdminUser) {
    moves = [];
    movesCount = 0;
    updateTilesFromItems();
    return;
  }

  try {
    setMsg("movesMsg", "Loading...");
    const data = await apiGet(API.moves);
    if (!data) return;

    moves = Array.isArray(data) ? data : (data.items ?? []);
    movesCount = moves.length;

    const lr = $("movesLastRefresh");
    if (lr) lr.textContent = `Updated: ${nowStamp()}`;

    updateTilesFromItems();

    const filtered = applyMovesFilters(moves);
    renderMovesTable(filtered);

    setMsg("movesMsg", `Loaded: ${filtered.length}`);
  } catch (err) {
    console.error(err);
    setMsg("movesMsg", "Movements error. Check console.", true);
    const tbody = $("movesTbody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="muted">API error loading movements.</td></tr>';
  }
}

/* Actions */
function openEdit(id) {
  const item = items.find(x => x.id === id);
  if (!item) return;

  currentItemId = id;
  $("formMode").textContent = "Edit";
  $("formTitle").textContent = "Create / Edit Item";

  fillFormFromItem(item);

  $("part_code").disabled = true;
  $("quantity_in_stock").disabled = true;

  $("btnOpenImages").disabled = false;
  $("btnAdjust").disabled = (item.is_active === false);

  setMsg("formMsg", item.is_active === false ? "Inactive item: stock adjustment disabled." : "");

  showView("form");
  setActiveTile("navNew");
}

async function saveItem() {
  try {
    setMsg("formMsg", "Saving...");

    if (!currentItemId) {
      const payload = readCreatePayload();
      if (!payload.part_code || !payload.part_name) {
        setMsg("formMsg", "Part code and Part name are required.", true);
        return;
      }

      const saved = await apiSend(API.items, "POST", payload);
      if (!saved) return;

      setMsg("formMsg", "Saved ✅");

      if (saved?.id) {
        currentItemId = saved.id;
        $("formMode").textContent = "Edit";
        $("part_code").disabled = true;
        $("quantity_in_stock").disabled = true;
        $("btnOpenImages").disabled = false;
        $("btnAdjust").disabled = false;
      }
    } else {
      const payload = readUpdatePayload();
      if (!payload.part_name) {
        setMsg("formMsg", "Part name is required.", true);
        return;
      }

      const updated = await apiSend(`${API.items}/${currentItemId}`, "PATCH", payload);
      if (!updated) return;

      setMsg("formMsg", "Updated ✅");
    }

    await loadInventory();
  } catch (err) {
    console.error(err);
    setMsg("formMsg", "Save error. Check console.", true);
  }
}

async function createSupplierQuick() {
  const nameInput = $("supplier_name");
  const msg = $("formMsg");

  if (!nameInput || !nameInput.value.trim()) {
    if (msg) msg.textContent = "Supplier name required.";
    return;
  }

  if (msg) msg.textContent = "Creating supplier...";

  try {
    const res = await fetch(API.suppliers, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ name: nameInput.value.trim() })
    });

    if (await handleUnauthorized(res)) return;

    let data = null;
    try { data = await res.json(); } catch {}

    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || `Error ${res.status}`;
      if (msg) msg.textContent = `Create supplier failed: ${detail}`;
      return;
    }

    if (msg) msg.textContent = `Supplier created: ${data.name ?? "OK"}`;
    nameInput.value = "";
    await loadSuppliers();
  } catch (err) {
    console.error(err);
    if (msg) msg.textContent = "Network error creating supplier.";
  }
}

/* Modals */
function openModal(id) { $(id)?.classList.add("open"); }
function closeModal(id) { $(id)?.classList.remove("open"); }

function refreshAdjustUI() {
  const t = $("adj_type")?.value;
  const costWrap = $("adj_unit_cost_wrap");
  const costInput = $("adj_unit_cost");

  if (!costWrap || !costInput) return;

  const isIn = (t === "in");
  costWrap.style.display = isIn ? "" : "none";

  if (isIn && currentItemId) {
    const it = items.find(x => x.id === currentItemId);
    if (it && (costInput.value === "" || costInput.value === "0" || costInput.value === "0.00")) {
      const guess = it.last_purchase_price ?? it.cost_price ?? "";
      if (guess !== null && guess !== undefined && guess !== "") costInput.value = String(guess);
    }
  }
}

async function doAdjustStock() {
  if (!currentItemId) return;

  const currentItem = items.find(x => x.id === currentItemId);
  if (currentItem && currentItem.is_active === false) {
    setMsg("adjMsg", "Inactive item. Reactivate first.", true);
    return;
  }

  const movement_type = $("adj_type").value;
  const qty = toInt($("adj_qty").value, 1);
  const notes = ($("adj_notes").value || "").trim();

  const unitCostEl = $("adj_unit_cost");
  const unit_cost_raw = unitCostEl ? String(unitCostEl.value || "").trim() : "";
  const unit_cost_num = toFloat(unit_cost_raw, NaN);

  try {
    setMsg("adjMsg", "Applying...");

    const payload = {
      movement_type,
      qty,
      notes: notes || null,
    };

    if (movement_type === "in") {
      if (!unit_cost_raw || !Number.isFinite(unit_cost_num)) {
        setMsg("adjMsg", "Unit cost is required for IN (e.g. 12.50).", true);
        return;
      }
      payload.unit_cost = unit_cost_raw;
    }

    const res = await apiSend(API.adjust(currentItemId), "POST", payload);
    if (!res) return;

    setMsg("adjMsg", "Applied ✅");
    $("adj_notes").value = "";
    if (unitCostEl) unitCostEl.value = "";

    await loadInventory();
    if (isAdminUser) await loadMovements();

    const item = items.find(x => x.id === currentItemId);
    if (item) $("quantity_in_stock").value = item.quantity_in_stock ?? 0;

  } catch (err) {
    console.error(err);
    setMsg("adjMsg", "Adjust error. Check console.", true);
  }
}

/* Images */
async function loadImages() {
  if (!currentItemId) return;

  try {
    setMsg("imgMsg", "Loading...");
    const data = await apiGet(API.imagesList(currentItemId));
    if (!data) return;

    const list = Array.isArray(data) ? data : [];
    renderImages(list);
    setMsg("imgMsg", "");
  } catch (err) {
    console.error(err);
    setMsg("imgMsg", "Images load error. Check console.", true);
  }
}

function setGalleryMainImage(url, altText = "") {
  const mainImg = $("galleryMainImage");
  const empty = $("galleryEmpty");
  if (!mainImg || !empty) return;

  if (!url) {
    mainImg.src = "";
    mainImg.alt = altText || "Item photo";
    mainImg.style.display = "none";
    empty.style.display = "";
    return;
  }

  mainImg.src = url;
  mainImg.alt = altText || "Item photo";
  mainImg.style.display = "";
  empty.style.display = "none";
}

function renderImages(list) {
  const grid = $("imagesGrid");
  if (!grid) return;

  if (!list.length) {
    grid.innerHTML = "";
    setGalleryMainImage("", "");
    return;
  }

  const selected = list.find(img => img.is_primary) || list[0];
  setGalleryMainImage(selected?.image_url || "", selected?.alt_text || "");

  grid.innerHTML = list.map(img => {
    const url = img.image_url ?? "";
    const primary = img.is_primary ?? false;
    const safeAlt = img.alt_text ?? "";

    return `
      <div class="gallery-thumb ${primary ? "active" : ""}" data-imgpick="${img.id}">
        <img src="${url}" alt="${safeAlt}">
        <div class="cap">
          <span class="tag ${primary ? "primary" : ""}">${primary ? "PRIMARY" : "IMG"}</span>
          <button class="danger" type="button" data-imgdel="${img.id}">Delete</button>
        </div>
      </div>
    `;
  }).join("");

  grid.onclick = async (e) => {
    const delBtn = e.target.closest("button[data-imgdel]");
    if (delBtn) {
      const imageId = delBtn.dataset.imgdel ? parseInt(delBtn.dataset.imgdel, 10) : null;
      if (!imageId) return;

      try {
        const res = await apiSend(API.imageDelete(imageId), "DELETE", null);
        if (!res && res !== null) return;

        await loadImages();
        setMsg("imgMsg", "Deleted ✅");
      } catch (err) {
        console.error(err);
        setMsg("imgMsg", "Delete error. Check console.", true);
      }
      return;
    }

    const card = e.target.closest("[data-imgpick]");
    if (!card) return;

    const imageId = card.dataset.imgpick ? parseInt(card.dataset.imgpick, 10) : null;
    const picked = list.find(x => x.id === imageId);
    if (!picked) return;

    grid.querySelectorAll(".gallery-thumb").forEach(el => el.classList.remove("active"));
    card.classList.add("active");
    setGalleryMainImage(picked.image_url ?? "", picked.alt_text ?? "");
  };
}

function updateImagePreview() {
  const fileInput = $("img_file");
  const wrap = $("imgPreviewWrap");
  const img = $("imgPreview");
  if (!fileInput || !wrap || !img) return;

  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    wrap.style.display = "none";
    img.src = "";
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    img.src = reader.result;
    wrap.style.display = "";
  };
  reader.readAsDataURL(file);
}

async function addImage() {
  if (!currentItemId) return;

  const fileInput = $("img_file");
  const file = fileInput?.files?.[0] || null;
  const is_primary = $("img_primary").value === "true";
  const alt_text = ($("img_alt").value || "").trim();

  if (!file) {
    setMsg("imgMsg", "Please choose an image file.", true);
    return;
  }

  const fd = new FormData();
  fd.append("file", file);
  fd.append("is_primary", String(is_primary));
  fd.append("alt_text", alt_text || "");
  fd.append("position", "0");

  try {
    setMsg("imgMsg", "Uploading...");
    const res = await fetch(API.imageUpload(currentItemId), {
      method: "POST",
      headers: { ...getAuthHeaders() },
      body: fd,
    });
    if (await handleUnauthorized(res)) return;
    if (!res.ok) throw new Error(await res.text());

    fileInput.value = "";
    $("img_alt").value = "";
    $("img_primary").value = "false";
    updateImagePreview();

    await loadImages();
    setMsg("imgMsg", "Uploaded ✅");
  } catch (err) {
    console.error(err);
    setMsg("imgMsg", "Upload image error. Check console.", true);
  }
}

/* Init */
document.addEventListener("DOMContentLoaded", async () => {
  if (!readToken()) {
    goLogin();
    return;
  }

  roleName = getRoleNameFromToken();
  isAdminUser = isAdminRole(roleName);

  applyPermissionsUI();

  const form = $("inventoryForm");
  if (!form) return;

  ["searchBox","filterBrand","filterCategory"].forEach(id => $(id)?.addEventListener("input", applyFiltersAndRender));
  $("lowStockOnly")?.addEventListener("change", applyFiltersAndRender);

  if (isAdminUser) {
    ["movesSearch","movesFrom","movesTo"].forEach(id => $(id)?.addEventListener("input", () => {
      const filtered = applyMovesFilters(moves);
      renderMovesTable(filtered);
      setMsg("movesMsg", `Loaded: ${filtered.length}`);
    }));
    $("movesType")?.addEventListener("change", () => {
      const filtered = applyMovesFilters(moves);
      renderMovesTable(filtered);
      setMsg("movesMsg", `Loaded: ${filtered.length}`);
    });
  }

  $("btnRefresh")?.addEventListener("click", loadInventory);
  $("btnNew")?.addEventListener("click", () => {
    resetFormToNew();
    showView("form");
    setActiveTile("navNew");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await saveItem();
  });

  $("btnReset")?.addEventListener("click", () => resetFormToNew());
  $("btnCreateSupplier")?.addEventListener("click", createSupplierQuick);

  $("btnAdjust")?.addEventListener("click", () => {
    setMsg("adjMsg","");
    openModal("modalAdjust");
    refreshAdjustUI();
  });
  $("closeAdjust")?.addEventListener("click", (e) => { e.preventDefault(); closeModal("modalAdjust"); });
  $("btnDoAdjust")?.addEventListener("click", doAdjustStock);
  $("adj_type")?.addEventListener("change", refreshAdjustUI);

  $("btnOpenImages")?.addEventListener("click", async () => { setMsg("imgMsg",""); openModal("modalImages"); updateImagePreview(); await loadImages(); });
  $("closeImages")?.addEventListener("click", (e) => { e.preventDefault(); closeModal("modalImages"); });
  $("img_file")?.addEventListener("change", updateImagePreview);
  $("btnAddImage")?.addEventListener("click", addImage);

  $("navNew")?.addEventListener("click", () => { showView("form"); resetFormToNew(); setActiveTile("navNew"); });
  $("navList")?.addEventListener("click", async () => { showView("list"); setActiveTile("navList"); await loadInventory(); });
  $("navLow")?.addEventListener("click", async () => {
    showView("list");
    setActiveTile("navLow");
    if ($("lowStockOnly")) $("lowStockOnly").checked = true;
    applyFiltersAndRender();
  });

  $("navMoves")?.addEventListener("click", async () => {
    if (!isAdminUser) return;
    showView("moves");
    setActiveTile("navMoves");
    await loadMovements();
  });

  $("btnMovesRefresh")?.addEventListener("click", () => { if (isAdminUser) loadMovements(); });
  $("btnMovesBack")?.addEventListener("click", async () => {
    showView("list");
    setActiveTile("navList");
    await loadInventory();
  });

  resetFormToNew();
  showView("list");
  setActiveTile("navList");

  await loadSuppliers();
  await loadInventory();

  if (isAdminUser) {
    await loadMovements();
  } else {
    moves = [];
    movesCount = 0;
    updateTilesFromItems();
  }
});

function calculateSalePrice() {
  const costEl = document.getElementById("cost_price");
  const markupEl = document.getElementById("markup_percent");
  const saleEl = document.getElementById("sale_price_base");
  if (!costEl || !markupEl || !saleEl) return;

  const cost = parseFloat(costEl.value) || 0;
  const markup = parseFloat(markupEl.value) || 0;
  const sale = cost * (1 + markup / 100);
  saleEl.value = sale.toFixed(2);
}

document.addEventListener("input", function (e) {
  if (e.target && (e.target.id === "cost_price" || e.target.id === "markup_percent")) {
    calculateSalePrice();
  }
});
