// static/companies.js
// UI en inglés. Comentarios en español.

const API = { base: "/api/companies" };

function $(id) { return document.getElementById(id); }
function setPill(id, text) { const el = $(id); if (el) el.textContent = text; }
function setCount(text) { const el = $("countPill"); if (el) el.textContent = text || "—"; }
function setMsg(text, isError = false) {
  const el = $("msg");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "crimson" : "#2b2f36";
}

function goLogin() { window.location.href = "/static/index.html"; }
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
  if (res.status === 403) throw new Error("Forbidden: you don't have permission for this action.");
  if (!res.ok) throw new Error(await res.text());
  try { return await res.json(); } catch { return null; }
}

let companies = [];
let editingId = null;
let roleName = "";
let isAdminUser = false;

function resetForm() {
  editingId = null;
  const input = $("companyName");
  if (input) input.value = "";
  const title = $("formTitle");
  const btn = $("btnCreate");
  const cancel = $("btnCancelEdit");
  if (title) title.textContent = "Create Company";
  if (btn) btn.textContent = "Create";
  if (cancel) cancel.style.display = "none";
}

function startEdit(id) {
  const company = companies.find(x => Number(x.id) === Number(id));
  if (!company) return;
  editingId = company.id;
  $("companyName").value = company.name || "";
  $("formTitle").textContent = `Edit Company #${company.id}`;
  $("btnCreate").textContent = "Save Changes";
  $("btnCancelEdit").style.display = "inline-block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function applySearchFilter(list) {
  const q = ($("searchBox")?.value || "").trim().toLowerCase();
  if (!q) return list || [];
  return (list || []).filter(c => [c.id, c.name].map(x => String(x ?? "").toLowerCase()).join(" | ").includes(q));
}

function renderTable(list) {
  const tbody = $("tbody");
  if (!tbody) return;
  const filtered = applySearchFilter(list);
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted">No companies found.</td></tr>`;
    setCount("Companies: 0");
    return;
  }

  tbody.innerHTML = filtered.map(c => `
    <tr>
      <td><b>${c.id ?? ""}</b></td>
      <td>${c.name ?? ""}</td>
      <td>
        <button type="button" class="ghost" data-edit-id="${c.id}">Edit</button>
        ${isAdminUser ? `<button type="button" data-delete-id="${c.id}" style="margin-left:8px;">Delete</button>` : ""}
      </td>
    </tr>
  `).join("");

  setCount(`Companies: ${filtered.length}`);

  tbody.querySelectorAll("[data-edit-id]").forEach(btn => btn.addEventListener("click", () => startEdit(btn.dataset.editId)));
  tbody.querySelectorAll("[data-delete-id]").forEach(btn => btn.addEventListener("click", () => deleteCompany(btn.dataset.deleteId)));
}

async function loadCompanies() {
  try {
    setPill("apiStatus", "API: checking...");
    const data = await apiGet(API.base);
    if (!data) return;
    companies = Array.isArray(data) ? data : [];
    setPill("apiStatus", "API: OK");
    renderTable(companies);
  } catch (err) {
    console.error(err);
    setPill("apiStatus", "API: ERROR");
    setMsg("API error loading companies. Check console.", true);
    companies = [];
    renderTable(companies);
  }
}

async function saveCompany() {
  const name = ($("companyName")?.value || "").trim();
  if (!name) {
    setMsg("Company name is required.", true);
    return;
  }

  try {
    setMsg(editingId ? "Saving..." : "Creating...");
    if (editingId) {
      await apiSend(`${API.base}/${editingId}`, "PATCH", { name });
      setMsg("Company updated ✅");
    } else {
      await apiSend(API.base, "POST", { name });
      setMsg("Company created ✅");
    }
    resetForm();
    await loadCompanies();
  } catch (err) {
    console.error(err);
    setMsg(String(err?.message || err || "Error"), true);
  }
}

async function deleteCompany(id) {
  if (!isAdminUser) {
    setMsg("Only ADMIN or SUPERADMIN can delete companies.", true);
    return;
  }
  const company = companies.find(x => Number(x.id) === Number(id));
  const name = company?.name || `#${id}`;
  if (!confirm(`Delete company ${name}? This cannot be undone.`)) return;

  try {
    setMsg("Deleting...");
    await apiSend(`${API.base}/${id}`, "DELETE");
    if (Number(editingId) === Number(id)) resetForm();
    setMsg("Company deleted ✅");
    await loadCompanies();
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
  $("btnRefresh")?.addEventListener("click", loadCompanies);
  $("btnCreate")?.addEventListener("click", saveCompany);
  $("btnCancelEdit")?.addEventListener("click", resetForm);
  $("companyName")?.addEventListener("keydown", (e) => { if (e.key === "Enter") saveCompany(); });
  $("searchBox")?.addEventListener("input", () => renderTable(companies));
  await loadCompanies();
});
