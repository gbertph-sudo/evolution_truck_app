// static/invoices.js

function $(id){ return document.getElementById(id); }

const API = {
  invoices: "/invoices",
  invoiceOne: (id) => `/invoices/${id}`,
  invoiceStatus: (id) => `/invoices/${id}/status`,
  invoicePay: (id) => `/invoices/${id}/pay`,
  invoiceItem: (id, itemId) => `/invoices/${id}/items/${itemId}`,
  invoicePdf: (id) => `/invoices/${id}/pdf`,
};

const TAX_RATE = 0.07;
const CARD_FEE_RATE = 0.04;

function getToken(){
  return localStorage.getItem("token") || localStorage.getItem("access_token") || "";
}

function authHeaders(extra = {}){
  const t = getToken();
  const h = { "Content-Type":"application/json", ...extra };
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

function money(n){
  const x = Number(n || 0);
  return `$${x.toFixed(2)}`;
}

function setMsg(id, text, isError=false){
  const el = $(id);
  if (!el) return;
  el.textContent = text || "";
  el.className = isError ? "danger" : "muted";
}

function pill(status){
  const s = (status||"").toUpperCase();
  const cls =
    s === "DRAFT" ? "draft" :
    s === "SENT" ? "sent" :
    s === "PAID" ? "paid" : "void";
  return `<span class="pill ${cls}">${s}</span>`;
}

function escapeHtml(s){
  return (s ?? "").toString()
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}

// --------------------
// Role helpers (Admin only can edit prices)
// --------------------
function parseJwt(token){
  try{
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64).split("").map(c => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join("")
    );
    return JSON.parse(jsonPayload);
  }catch{ return null; }
}

function getRoleName(){
  // if you already store role_name in localStorage:
  const ls = localStorage.getItem("role_name");
  if (ls) return String(ls).toUpperCase();

  // else try from JWT payload
  const t = getToken();
  const payload = t ? parseJwt(t) : null;
  const r = (payload?.role_name || payload?.role || payload?.roleName || "").toString();
  return r.toUpperCase();
}

function isAdmin(){
  const r = getRoleName();
  return r === "ADMIN" || r === "SUPERADMIN";
}

function setPriceEditingEnabled(enabled){
  const tb = $("itemsTbody");
  if (!tb) return;

  tb.querySelectorAll('input[data-markup], input[data-unit]').forEach(inp => {
    inp.disabled = !enabled;
  });
  tb.querySelectorAll('button[data-save]').forEach(btn => {
    btn.disabled = !enabled;
  });
}

// --------------------
// State
// --------------------
let INVOICES = [];
let CURRENT = null;

// =====================
// LIST
// =====================

async function loadInvoices(){
  const q = ($("q")?.value || "").trim();
  const status = ($("statusFilter")?.value || "").trim();

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (status) params.set("status", status);

  const url = params.toString()
    ? `${API.invoices}?${params.toString()}`
    : API.invoices;

  const rows = await apiFetch(url, { headers: authHeaders() });
  INVOICES = Array.isArray(rows) ? rows : (rows?.items || []);
}

function renderKpis(){
  const k = $("kpis");
  if (!k) return;

  const sum = (arr, fn)=> arr.reduce((a,x)=> a + fn(x), 0);

  const draft = INVOICES.filter(x => (x.status||"").toUpperCase()==="DRAFT");
  const sent  = INVOICES.filter(x => (x.status||"").toUpperCase()==="SENT");
  const paid  = INVOICES.filter(x => (x.status||"").toUpperCase()==="PAID");

  const paidTotal = sum(paid, x => Number(x.total || 0));

  k.innerHTML = `
    <div class="kpi">
      <div class="label">DRAFT</div>
      <div class="value">${draft.length}</div>
    </div>
    <div class="kpi">
      <div class="label">SENT</div>
      <div class="value">${sent.length}</div>
    </div>
    <div class="kpi">
      <div class="label">PAID</div>
      <div class="value">${paid.length}</div>
    </div>
    <div class="kpi">
      <div class="label">PAID TOTAL</div>
      <div class="value">${money(paidTotal)}</div>
    </div>
  `;
}

function renderList(){
  const tbody = $("tbody");
  if (!tbody) return;

  if (!INVOICES.length){
    tbody.innerHTML = `<tr><td colspan="9" class="muted">No invoices found.</td></tr>`;
    renderKpis();
    return;
  }

  tbody.innerHTML = INVOICES.map(inv => {
    const no = inv.invoice_number || `INV-${inv.id}`;
    const cust = inv.customer?.name || "-";

    return `
      <tr>
        <td><b>${escapeHtml(no)}</b><div class="muted">#${inv.id}</div></td>
        <td>${pill(inv.status)}</td>
        <td>${escapeHtml(cust)}</td>
        <td>${escapeHtml(inv.payment_method || "-")}</td>
        <td class="right">${money(inv.subtotal)}</td>
        <td class="right">${money(inv.tax)}</td>
        <td class="right">${money(inv.processing_fee || 0)}</td>
        <td class="right"><b>${money(inv.total)}</b></td>
        <td>
          <div class="actions">
            <button class="ghost" data-act="pdf" data-id="${inv.id}">PDF</button>
            <button class="secondary" data-act="open" data-id="${inv.id}">Open</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("button[data-act]").forEach(b => b.addEventListener("click", onRowAction));
  renderKpis();
}

async function onRowAction(e){
  const btn = e.currentTarget;
  const act = btn.getAttribute("data-act");
  const id = parseInt(btn.getAttribute("data-id"), 10);

  if (!Number.isFinite(id)) return;

  if (act === "pdf"){
    window.open(API.invoicePdf(id), "_blank");
    return;
  }

  if (act === "open"){
    await openInvoice(id);
  }
}

// =====================
// MODAL
// =====================

function openModal(){
  $("modalBackdrop").style.display = "flex";
  document.body.style.overflow = "hidden";
}

function closeModal(){
  $("modalBackdrop").style.display = "none";
  document.body.style.overflow = "";
  CURRENT = null;
}

function computeTotals(subtotal, method){
  subtotal = Number(subtotal || 0);
  const m = (method || "").toUpperCase();

  let tax = 0;
  let fee = 0;

  if (m === "CASH"){
    tax = 0; fee = 0;
  } else if (m === "ZELLE"){
    tax = subtotal * TAX_RATE;
  } else if (m === "CARD"){
    tax = subtotal * TAX_RATE;
    fee = (subtotal + tax) * CARD_FEE_RATE;
  }

  const total = subtotal + tax + fee;

  const r = (x)=> Math.round(x * 100) / 100;
  return { subtotal: r(subtotal), tax: r(tax), fee: r(fee), total: r(total) };
}

function renderTotals(inv){
  const method = ($("payMethod")?.value || inv.payment_method || "");
  const t = computeTotals(inv.subtotal, method);

  $("tSubtotal").textContent = money(t.subtotal);
  $("tTax").textContent = money(t.tax);
  $("tFee").textContent = money(t.fee);
  $("tTotal").textContent = money(t.total);
}

// Markup calc helpers
function clamp(n, min, max){
  n = Number(n);
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

function calcUnitFromMarkup(cost, markup){
  const c = Number(cost || 0);
  const m = Number(markup || 0);
  if (c <= 0) return 0;
  const unit = c * (1 + (m/100));
  return Math.round(unit * 100) / 100;
}

function calcMarkupFromUnit(cost, unit){
  const c = Number(cost || 0);
  const u = Number(unit || 0);
  if (c <= 0) return 0;
  const mk = ((u / c) - 1) * 100;
  return Math.round(mk * 100) / 100;
}

function renderItems(inv){
  const items = inv.items || [];
  const tb = $("itemsTbody");

  if (!items.length){
    tb.innerHTML = `<tr><td colspan="8" class="muted">No items.</td></tr>`;
    return;
  }

  tb.innerHTML = items.map(it => {
    const cost = Number(it.cost_snapshot ?? it.cost_price ?? 0);
    const unit = Number(it.unit_price ?? 0);
    const qty  = Number(it.qty ?? 0);

    const markup = cost > 0 ? calcMarkupFromUnit(cost, unit) : 0;

    return `
      <tr data-row="${it.id}">
        <td>${escapeHtml(it.item_type || "")}</td>
        <td>${escapeHtml(it.description || "")}</td>
        <td class="right">${qty}</td>
        <td class="right">${money(cost)}</td>

        <td class="right">
          <input type="number" min="0" max="200" step="0.01"
            value="${markup.toFixed(2)}"
            data-markup="${it.id}" />
        </td>

        <td class="right">
          <input type="number" min="0" step="0.01"
            value="${unit.toFixed(2)}"
            data-unit="${it.id}" />
        </td>

        <td class="right"><b>${money(it.line_total)}</b></td>

        <td>
          <button data-save="${it.id}">Save</button>
        </td>
      </tr>
    `;
  }).join("");

  // When markup changes -> update unit input live (not saving yet)
  tb.querySelectorAll('input[data-markup]').forEach(inp => {
    inp.addEventListener("input", () => {
      const itemId = parseInt(inp.getAttribute("data-markup"), 10);
      const row = tb.querySelector(`tr[data-row="${itemId}"]`);
      if (!row) return;

      const costTxt = row.children[3]?.textContent || "$0.00";
      const cost = Number(costTxt.replace("$","")) || 0;

      const mk = clamp(inp.value, 0, 200);
      inp.value = mk.toFixed(2);

      const unit = calcUnitFromMarkup(cost, mk);
      const unitInp = tb.querySelector(`input[data-unit="${itemId}"]`);
      if (unitInp) unitInp.value = unit.toFixed(2);
    });
  });

  // When unit changes -> update markup input live
  tb.querySelectorAll('input[data-unit]').forEach(inp => {
    inp.addEventListener("input", () => {
      const itemId = parseInt(inp.getAttribute("data-unit"), 10);
      const row = tb.querySelector(`tr[data-row="${itemId}"]`);
      if (!row) return;

      const costTxt = row.children[3]?.textContent || "$0.00";
      const cost = Number(costTxt.replace("$","")) || 0;

      const unit = Number(inp.value);
      if (!Number.isFinite(unit) || unit < 0) return;

      const mk = clamp(calcMarkupFromUnit(cost, unit), 0, 200);
      const mkInp = tb.querySelector(`input[data-markup="${itemId}"]`);
      if (mkInp) mkInp.value = mk.toFixed(2);
    });
  });

  // Save button (PATCH unit_price)
  tb.querySelectorAll('button[data-save]').forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!CURRENT) return;

      const itemId = parseInt(btn.getAttribute("data-save"), 10);
      const unitInp = tb.querySelector(`input[data-unit="${itemId}"]`);
      const newUnit = Number(unitInp?.value);

      if (!Number.isFinite(newUnit) || newUnit < 0){
        setMsg("modalMsg", "Invalid unit price.", true);
        return;
      }

      try{
        setMsg("modalMsg", "Saving price...");
        await apiFetch(API.invoiceItem(CURRENT.id, itemId), {
          method: "PATCH",
          headers: authHeaders(),
          body: JSON.stringify({ unit_price: newUnit }),
        });

        // reload invoice
        await openInvoice(CURRENT.id, true);
        setMsg("modalMsg", "Saved ✅", false);
      }catch(e){
        setMsg("modalMsg", e.message || "Error saving price", true);
      }
    });
  });

  // apply lock based on role + checkbox
  const admin = isAdmin();
  const unlocked = admin && $("unlockPricesChk")?.checked;
  setPriceEditingEnabled(!!unlocked);
}

function applyUnlockUI(){
  const admin = isAdmin();
  const chk = $("unlockPricesChk");
  const hint = $("unlockHint");

  if (!chk || !hint) return;

  if (!admin){
    chk.checked = false;
    chk.disabled = true;
    hint.textContent = "Price editing locked (admin only).";
    setPriceEditingEnabled(false);
  } else {
    chk.disabled = false;
    hint.textContent = chk.checked ? "Price editing ENABLED." : "Price editing locked.";
    setPriceEditingEnabled(chk.checked);
  }
}

function renderInvoiceDetails(inv){
  CURRENT = inv;

  $("modalTitle").textContent = inv.invoice_number || `Invoice #${inv.id}`;

  const metaLines = [];
  metaLines.push(`<b>Status:</b> ${escapeHtml(inv.status || "")}`);
  metaLines.push(`<b>Customer:</b> ${escapeHtml(inv.customer?.name || "-")}`);
  if (inv.created_at) metaLines.push(`<b>Created:</b> ${escapeHtml(inv.created_at)}`);
  if (inv.work_order?.work_order_number) metaLines.push(`<b>WO:</b> ${escapeHtml(inv.work_order.work_order_number)}`);

  $("invMeta").innerHTML = metaLines.join("<br>");

  $("payMethod").value = inv.payment_method || "";

  // Unlock UI
  applyUnlockUI();

  renderItems(inv);
  renderTotals(inv);

  // Buttons status lock
  const st = (inv.status || "").toUpperCase();
  const closed = (st === "PAID" || st === "VOID");
  $("payBtn").disabled = closed;
  $("markSentBtn").disabled = closed || st === "SENT";
  $("voidBtn").disabled = closed;
}

async function openInvoice(id, keepModalOpen=false){
  const inv = await apiFetch(API.invoiceOne(id), { headers: authHeaders() });
  renderInvoiceDetails(inv);
  if (!keepModalOpen) openModal();
}

// =====================
// ACTIONS
// =====================

async function payInvoice(){
  if (!CURRENT) return;

  const method = ($("payMethod").value || "").toUpperCase();
  if (!method){
    setMsg("modalMsg", "Select payment method first.", true);
    return;
  }

  setMsg("modalMsg", "Marking PAID...");
  const updated = await apiFetch(API.invoicePay(CURRENT.id), {
    method:"PUT",
    headers: authHeaders(),
    body: JSON.stringify({ method })
  });

  renderInvoiceDetails(updated);
  await refresh();
  setMsg("modalMsg", "PAID ✅", false);
}

async function markSent(){
  if (!CURRENT) return;

  setMsg("modalMsg", "Marking SENT...");
  const updated = await apiFetch(API.invoiceStatus(CURRENT.id), {
    method:"PUT",
    headers: authHeaders(),
    body: JSON.stringify({ status:"SENT" })
  });

  renderInvoiceDetails(updated);
  await refresh();
  setMsg("modalMsg", "SENT ✅", false);
}

async function voidInvoice(){
  if (!CURRENT) return;

  setMsg("modalMsg", "Voiding invoice...");
  const updated = await apiFetch(API.invoiceStatus(CURRENT.id), {
    method:"PUT",
    headers: authHeaders(),
    body: JSON.stringify({ status:"VOID" })
  });

  renderInvoiceDetails(updated);
  await refresh();
  setMsg("modalMsg", "VOID ✅", false);
}

async function refresh(){
  setMsg("listMsg","Loading...");
  await loadInvoices();
  renderList();
  setMsg("listMsg", `Loaded ${INVOICES.length} invoices.`);
}

// =====================
// INIT
// =====================

async function init(){
  $("backBtn").addEventListener("click", ()=> window.location.href="/static/dashboard.html");
  $("logoutBtn").addEventListener("click", ()=>{
    localStorage.removeItem("token");
    localStorage.removeItem("access_token");
    window.location.href="/static/login.html";
  });

  $("refreshBtn").addEventListener("click", refresh);
  $("q").addEventListener("keydown", e=>{ if (e.key==="Enter") refresh(); });
  $("statusFilter").addEventListener("change", refresh);

  $("closeModalBtn").addEventListener("click", closeModal);
  $("modalBackdrop").addEventListener("click", e=>{
    if (e.target === $("modalBackdrop")) closeModal();
  });

  $("pdfBtn").addEventListener("click", ()=>{
    if (!CURRENT) return;
    window.open(API.invoicePdf(CURRENT.id), "_blank");
  });

  $("markSentBtn").addEventListener("click", ()=> markSent().catch(e=>setMsg("modalMsg", e.message, true)));
  $("voidBtn").addEventListener("click", ()=> voidInvoice().catch(e=>setMsg("modalMsg", e.message, true)));
  $("payBtn").addEventListener("click", ()=> payInvoice().catch(e=>setMsg("modalMsg", e.message, true)));

  $("payMethod").addEventListener("change", ()=>{
    if (!CURRENT) return;
    renderTotals(CURRENT);
  });

  $("unlockPricesChk").addEventListener("change", ()=>{
    applyUnlockUI();
  });

  await refresh();
}

init();