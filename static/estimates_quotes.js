const QUOTES_API = "/api/quotes";

function byId(id){ return document.getElementById(id); }

function getToken(){
  return (localStorage.getItem("access_token") || localStorage.getItem("token") || "").trim();
}

function authHeaders(extra = {}){
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

function money(value){
  const num = Number(value || 0);
  return num.toLocaleString(undefined, { style:"currency", currency:"USD" });
}

function fmtDate(value){
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString();
}

function statusPill(status){
  const v = String(status || "").toUpperCase();
  const cls = {QUOTE:"quote",EXPIRED:"expired",UNPAID:"unpaid",PAID:"paid",VOID:"void"}[v] || "quote";
  return `<span class="pill ${cls}">${v || "-"}</span>`;
}

function expiresText(row){
  if (!row?.expires_at) return "-";
  const now = Date.now();
  const exp = new Date(row.expires_at).getTime();
  if (Number.isNaN(exp)) return "-";
  const diff = exp - now;
  if (diff <= 0) return "Expired";
  const hrs = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  return `${hrs}h ${mins}m`;
}

let QUOTES_CACHE = [];
let ACTIVE_QUOTE = null;

async function fetchJson(url, options = {}){
  const response = await fetch(url, {
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options.headers || {}),
    }),
  });
  if (response.status === 401) {
    window.location.replace("/static/index.html");
    throw new Error("Unauthorized");
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      detail = data?.detail || data?.message || detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function loadKpis(){
  try{
    const data = await fetchJson(`${QUOTES_API}/kpis`);
    byId("kpiActive").textContent = String(data.active_quotes ?? 0);
    byId("kpiSoon").textContent = String(data.expiring_soon ?? 0);
    byId("kpiExpired").textContent = String(data.expired_quotes ?? 0);
    byId("kpiUnpaid").textContent = String(data.unpaid_quotes ?? 0);
    byId("kpiOpenAmount").textContent = money(data.open_amount ?? 0);
  }catch(error){
    console.error(error);
  }
}

function sortRows(rows){
  const mode = byId("sortMode")?.value || "newest";
  const clone = [...rows];
  if (mode === "oldest") {
    clone.sort((a,b)=> new Date(a.created_at || 0) - new Date(b.created_at || 0));
  } else if (mode === "expires_soon") {
    clone.sort((a,b)=> new Date(a.expires_at || "9999-12-31") - new Date(b.expires_at || "9999-12-31"));
  } else if (mode === "highest_total") {
    clone.sort((a,b)=> Number(b.total || 0) - Number(a.total || 0));
  } else {
    clone.sort((a,b)=> new Date(b.created_at || 0) - new Date(a.created_at || 0));
  }
  return clone;
}

function renderTable(rows){
  const tbody = byId("quotesTableBody");
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No quotes found.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(row => `
    <tr>
      <td>
        <div style="font-weight:900">${row.invoice_number || `INV-${String(row.id).padStart(6, "0")}`}</div>
        <div class="muted">${row.document_label || "Quote"}</div>
      </td>
      <td>
        <div style="font-weight:800">${row.customer?.name || "Walk-in / No customer"}</div>
        <div class="muted">${row.customer?.phone || row.customer?.email || "-"}</div>
      </td>
      <td>${statusPill(row.status)}</td>
      <td>${fmtDate(row.created_at)}</td>
      <td>
        <div>${fmtDate(row.expires_at)}</div>
        <div class="muted">${expiresText(row)}</div>
      </td>
      <td style="font-weight:900">${money(row.total)}</td>
      <td>
        <div class="row-actions">
          <button class="btn btn-ghost" type="button" onclick="openQuote(${row.id})">Open</button>
          <button class="btn btn-ghost" type="button" onclick="window.open('${QUOTES_API}/${row.id}/pdf','_blank')">PDF</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function setDetailVisible(show){
  byId("detailEmpty").style.display = show ? "none" : "block";
  byId("detailContent").style.display = show ? "flex" : "none";
}

function resetDetail(){
  ACTIVE_QUOTE = null;
  setDetailVisible(false);
  byId("detailTitle").textContent = "Quote Details";
  byId("detailSubtitle").textContent = "Select a quote from the list.";
}

function renderDetail(row){
  ACTIVE_QUOTE = row;
  setDetailVisible(true);
  byId("detailTitle").textContent = row.invoice_number || `Quote #${row.id}`;
  byId("detailSubtitle").textContent = `${row.customer?.name || "No customer"} • ${row.status}`;
  byId("detailStatus").innerHTML = statusPill(row.status);
  byId("detailDocument").textContent = row.document_label || "Quote";
  byId("detailCustomer").textContent = row.customer?.name || "Walk-in / No customer";
  byId("detailPhone").textContent = row.customer?.phone || row.customer?.email || "-";
  byId("detailExpires").textContent = fmtDate(row.expires_at);
  byId("detailInventoryApplied").textContent = row.inventory_applied ? "YES" : "NO";
  byId("detailNumber").textContent = row.invoice_number || `INV-${String(row.id).padStart(6, "0")}`;
  byId("detailWorkOrder").textContent = row.work_order?.work_order_number || "-";
  byId("detailSettlement").textContent = row.settlement_type || "-";
  byId("detailPaymentMethod").textContent = row.payment_label || row.payment_method || "-";
  byId("detailSubtotal").textContent = money(row.subtotal);
  byId("detailTax").textContent = money(row.tax);
  byId("detailTotal").textContent = money(row.total);
  byId("detailNotes").textContent = row.notes || "-";

  byId("detailItems").innerHTML = (row.items || []).map(item => `
    <div class="line">
      <div class="line-top">
        <div>
          <div class="line-name">${item.description || "-"}</div>
          <div class="muted">Inventory ID: ${item.inventory_item_id || "-"}</div>
        </div>
        <div style="text-align:right">
          <div style="font-weight:900">${money(item.line_total)}</div>
          <div class="muted">Qty ${item.qty} × ${money(item.unit_price)}</div>
        </div>
      </div>
    </div>
  `).join("") || `<div class="empty">No line items.</div>`;

  const status = String(row.status || "").toUpperCase();
  const paidOrVoid = status === "PAID" || status === "VOID";
  byId("markPaidBtn").disabled = paidOrVoid;
  byId("convertSaleBtn").disabled = status !== "QUOTE";
  byId("chargeArBtn").disabled = status !== "QUOTE";
  byId("voidBtn").disabled = status === "VOID" || status === "PAID";
}

async function openQuote(id){
  try{
    const row = await fetchJson(`${QUOTES_API}/${id}`);
    renderDetail(row);
  }catch(error){
    alert(error.message || "Could not open quote");
  }
}

async function loadQuotes(){
  try{
    const params = new URLSearchParams();
    const q = byId("searchInput")?.value?.trim();
    const status = byId("statusFilter")?.value?.trim();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    const qs = params.toString();
    const rows = await fetchJson(qs ? `${QUOTES_API}?${qs}` : QUOTES_API);
    QUOTES_CACHE = sortRows(rows || []);
    renderTable(QUOTES_CACHE);
    await loadKpis();
    if (ACTIVE_QUOTE) {
      const stillThere = QUOTES_CACHE.find(x => x.id === ACTIVE_QUOTE.id);
      if (!stillThere) resetDetail();
    }
  }catch(error){
    console.error(error);
    byId("quotesTableBody").innerHTML = `<tr><td colspan="7" class="muted">${error.message || "Failed to load quotes."}</td></tr>`;
  }
}

async function cleanupExpired(){
  try{
    const data = await fetchJson(`${QUOTES_API}/cleanup-expired`, { method:"POST" });
    alert(`Expired quotes updated: ${data.expired_now ?? 0}`);
    await loadQuotes();
  }catch(error){
    alert(error.message || "Cleanup failed");
  }
}

async function markPaid(){
  if (!ACTIVE_QUOTE) return;
  const payment_method = prompt("Payment method: CASH, CARD, ZELLE or CHECK", "CASH");
  if (!payment_method) return;
  const notes = prompt("Optional internal note", "") || "";
  try{
    await fetchJson(`${QUOTES_API}/${ACTIVE_QUOTE.id}/mark-paid`, {
      method:"POST",
      body: JSON.stringify({ payment_method, notes })
    });
    await loadQuotes();
    alert("Quote moved to Invoices as PAID.");
    window.location.href = "/static/invoices.html";
  }catch(error){
    alert(error.message || "Could not mark paid");
  }
}

async function convertToSale(settlement_type){
  if (!ACTIVE_QUOTE) return;
  let payment_method = null;
  if (settlement_type === "PAY_NOW") {
    payment_method = prompt("Payment method: CASH, CARD, ZELLE or CHECK", "CASH");
    if (!payment_method) return;
  }
  const notes = prompt("Optional internal note", "") || "";
  try{
    await fetchJson(`${QUOTES_API}/${ACTIVE_QUOTE.id}/convert`, {
      method:"POST",
      body: JSON.stringify({ settlement_type, payment_method, notes })
    });
    await loadQuotes();
    alert("Quote converted to sale and moved to Invoices.");
    window.location.href = "/static/invoices.html";
  }catch(error){
    alert(error.message || "Conversion failed");
  }
}

async function voidQuote(){
  if (!ACTIVE_QUOTE) return;
  if (!confirm("Void this quote?")) return;
  const notes = prompt("Optional void note", "") || "";
  try{
    await fetchJson(`${QUOTES_API}/${ACTIVE_QUOTE.id}/void`, {
      method:"POST",
      body: JSON.stringify({ notes })
    });
    await loadQuotes();
    await openQuote(ACTIVE_QUOTE.id);
  }catch(error){
    alert(error.message || "Could not void quote");
  }
}

function clearFilters(){
  byId("searchInput").value = "";
  byId("statusFilter").value = "";
  byId("sortMode").value = "newest";
  loadQuotes();
}

document.addEventListener("DOMContentLoaded", () => {
  byId("applyBtn")?.addEventListener("click", loadQuotes);
  byId("clearBtn")?.addEventListener("click", clearFilters);
  byId("refreshBtn")?.addEventListener("click", loadQuotes);
  byId("cleanupBtn")?.addEventListener("click", cleanupExpired);
  byId("pdfBtn")?.addEventListener("click", () => {
    if (ACTIVE_QUOTE) window.open(`${QUOTES_API}/${ACTIVE_QUOTE.id}/pdf`, "_blank");
  });
  byId("markPaidBtn")?.addEventListener("click", markPaid);
  byId("convertSaleBtn")?.addEventListener("click", () => convertToSale("PAY_NOW"));
  byId("chargeArBtn")?.addEventListener("click", () => convertToSale("CHARGE_ACCOUNT"));
  byId("voidBtn")?.addEventListener("click", voidQuote);
  byId("searchInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadQuotes();
  });
  loadQuotes();
});
