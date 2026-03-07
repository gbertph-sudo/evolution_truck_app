// static/users.js
(() => {
  const $ = (id) => document.getElementById(id);

  // ==== CONFIG ====
  // Si tu backend está en el mismo host, deja API = "".
  const API = "";                 // e.g. "http://127.0.0.1:8000"
  const API_PREFIX = "";      // tu router tiene prefix="/api"

  // cache simple para mapear role_id -> role_name (para el select)
  const ROLES_MAP = {}; // { [id]: "ADMIN" }

  // Mantener users en memoria para el modal
  window.__users = [];

  function setMsg(el, msg, ok = true) {
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = ok ? "#0d7a3a" : "#8a1c1c";
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[m]));
  }

  function getToken() {
    return (
      localStorage.getItem("access_token") ||
      localStorage.getItem("accessToken") ||
      localStorage.getItem("token") ||
      ""
    ).trim();
  }

  function logoutAndGo() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("accessToken");
    localStorage.removeItem("token");
    window.location.href = "/static/index.html";
  }

  function authHeaders() {
    const token = getToken();
    const base = { "Content-Type": "application/json" };
    if (!token) return base;
    return { ...base, Authorization: "Bearer " + token };
  }

  function apiUrl(path) {
    // path debe venir como "/users" o "/roles" etc.
    return API + API_PREFIX + path;
  }

  async function apiReq(method, path, payload) {
    const res = await fetch(apiUrl(path), {
      method,
      headers: authHeaders(),
      body: payload ? JSON.stringify(payload) : undefined,
    });

    let data;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) data = await res.json();
    else data = { detail: await res.text() };

    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      if (typeof data?.detail === "string") msg = data.detail;
      else if (Array.isArray(data?.detail)) msg = data.detail.map(e => e.msg).join(", ");
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  const apiGet = (path) => apiReq("GET", path);
  const apiPost = (path, payload) => apiReq("POST", path, payload);
  const apiPut = (path, payload) => apiReq("PUT", path, payload);
  const apiPatch = (path, payload) => apiReq("PATCH", path, payload);

  function handleAuthError(e) {
    if (e && (e.status === 401 || e.status === 403)) {
      return true;
    }
    return false;
  }

  // ==== UI HELPERS ====
  function setLoading(isLoading) {
    const btn = $("btnRefresh");
    if (btn) btn.disabled = !!isLoading;

    const saveBtn = document.querySelector('button[type="submit"]');
    if (saveBtn) saveBtn.disabled = !!isLoading;
  }

  // ===== Password Modal Logic =====
  const pwModal = () => $("pwModal");
  const pwUserInfo = () => $("pwUserInfo");
  const pwNew = () => $("pwNew");
  const pwConfirm = () => $("pwConfirm");
  const pwMsg = () => $("pwMsg");
  const pwSaveBtn = () => $("pwSaveBtn");
  const pwCloseBtn = () => $("pwCloseBtn");
  const pwCancelBtn = () => $("pwCancelBtn");

  let pwTargetUserId = null;

  function openPasswordModal(user) {
    pwTargetUserId = user.id;
    pwUserInfo().textContent = `User: ${user.username} (ID ${user.id}) — Role: ${user.role_name || ""}`;
    pwNew().value = "";
    pwConfirm().value = "";
    pwMsg().textContent = "";
    pwMsg().style.color = "#111";
    pwModal().style.display = "flex";
    setTimeout(() => pwNew().focus(), 50);
  }

  function closePasswordModal() {
    pwModal().style.display = "none";
    pwTargetUserId = null;
  }

  async function adminChangePassword(userId, newPassword) {
    // backend espera: { new_password: "..." }
    return apiPatch(`/users/${userId}/password`, { new_password: newPassword });
  }

  function wirePasswordModalOnce() {
    // si el modal no existe, no hacemos nada
    if (!$("pwModal")) return;

    pwCloseBtn().addEventListener("click", closePasswordModal);
    pwCancelBtn().addEventListener("click", closePasswordModal);

    pwModal().addEventListener("click", (e) => {
      if (e.target === pwModal()) closePasswordModal();
    });

    pwSaveBtn().addEventListener("click", async () => {
      const a = pwNew().value.trim();
      const b = pwConfirm().value.trim();

      if (!pwTargetUserId) return;

      if (!a || a.length < 6) {
        pwMsg().style.color = "#8a1c1c";
        pwMsg().textContent = "Password min 6";
        return;
      }
      if (a !== b) {
        pwMsg().style.color = "#8a1c1c";
        pwMsg().textContent = "Passwords do not match";
        return;
      }

      pwSaveBtn().disabled = true;
      pwMsg().style.color = "#111";
      pwMsg().textContent = "Saving...";

      try {
        await adminChangePassword(pwTargetUserId, a);
        pwMsg().style.color = "#0d7a3a";
        pwMsg().textContent = "Password updated ✅";
        setTimeout(() => closePasswordModal(), 600);
      } catch (e) {
        console.error("adminChangePassword error:", e);
        pwMsg().style.color = "#8a1c1c";
        pwMsg().textContent = handleAuthError(e)
          ? `${e.message} (not authorized)`
          : `${e.message}`;
      } finally {
        pwSaveBtn().disabled = false;
      }
    });
  }

  function renderUsers(users) {
    const tbody = $("usersTbody");
    if (!tbody) return;

    tbody.innerHTML = "";
    window.__users = Array.isArray(users) ? users : [];

    users.forEach((u) => {
      const tr = document.createElement("tr");

      // tu backend retorna role_name en UserOut
      const roleName = u.role_name || "";

      tr.innerHTML = `
        <td>${u.id ?? ""}</td>
        <td>${escapeHtml(u.username)}</td>
        <td>${escapeHtml(u.full_name)}</td>
        <td>${escapeHtml(u.email)}</td>
        <td>${escapeHtml(roleName)}</td>
        <td>${u.is_active ? '<span class="pill on">ON</span>' : '<span class="pill off">OFF</span>'}</td>
        <td><button class="secondary" type="button" data-action="pw" data-id="${u.id}">Change password</button></td>
      `;

      tbody.appendChild(tr);
    });

    // Delegated click (una sola vez)
    tbody.onclick = (e) => {
      const btn = e.target.closest("button[data-action='pw']");
      if (!btn) return;
      const userId = Number(btn.dataset.id);
      const user = window.__users.find(x => x.id === userId);
      if (!user) return alert("User not found");
      openPasswordModal(user);
    };
  }

  async function loadRoles() {
    const formMsg = $("formMsg");
    const select = $("role_id");
    if (!select) return;

    setMsg(formMsg, "Loading roles...", true);
    select.innerHTML = `<option value="">Loading...</option>`;

    const roles = await apiGet("/roles"); // GET /api/roles

    Object.keys(ROLES_MAP).forEach((k) => delete ROLES_MAP[k]);
    select.innerHTML = `<option value="">Select role</option>`;

    roles.forEach((r) => {
      ROLES_MAP[r.id] = r.name;

      const opt = document.createElement("option");
      opt.value = String(r.id);
      opt.textContent = r.name;
      select.appendChild(opt);
    });

    setMsg(formMsg, `✅ Roles loaded: ${roles.length}`, true);
  }

  async function loadUsers() {
    const formMsg = $("formMsg");
    setMsg(formMsg, "Loading users...", true);

    const users = await apiGet("/users"); // GET /api/users
    renderUsers(users);

    setMsg(formMsg, `✅ Users loaded: ${users.length}`, true);
  }

  async function refreshAll() {
    const formMsg = $("formMsg");
    try {
      setLoading(true);
      await loadRoles();
      await loadUsers();
    } catch (e) {
      console.error("refreshAll error:", e);
      if (handleAuthError(e)) {
        setMsg(formMsg, `❌ ${e.message} (check token/role)`, false);
      } else {
        setMsg(formMsg, `❌ ${e.message}`, false);
      }
    } finally {
      setLoading(false);
    }
  }

  async function createUser(payload) {
    return apiPost("/users", payload); // POST /api/users
  }

  // ==== INIT ====
  document.addEventListener("DOMContentLoaded", async () => {
    const formMsg = $("formMsg");

    // wire modal
    wirePasswordModalOnce();

    // botones header
    const dash = $("goDashboardBtn");
    const logout = $("logoutBtn");

    if (dash) {
      dash.addEventListener("click", () => {
        window.location.href = "/static/dashboard.html";
      });
    }

    if (logout) {
      logout.addEventListener("click", () => {
        logoutAndGo();
      });
    }

    // botón refresh
    const btnRefresh = $("btnRefresh");
    if (btnRefresh) btnRefresh.addEventListener("click", refreshAll);

    // submit form
    const form = $("userForm");
    if (form) {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();

        const roleSelect = $("role_id");
        const role_name = roleSelect?.options[roleSelect.selectedIndex]?.text;

        const payload = {
          username: $("username")?.value.trim(),
          full_name: $("full_name")?.value.trim(),
          email: $("email")?.value.trim(),
          password: $("password")?.value,
          role_name: role_name, // backend espera role_name
        };

        if (!payload.username || !payload.email || !payload.password || !payload.role_name) {
          setMsg(formMsg, "❌ Fill username, email, password and role.", false);
          return;
        }
        if (payload.password.length < 6) {
          setMsg(formMsg, "❌ Password must be at least 6 chars.", false);
          return;
        }

        try {
          setLoading(true);
          setMsg(formMsg, "Saving user...", true);

          await createUser(payload);

          setMsg(formMsg, "✅ User created successfully!", true);

          $("username").value = "";
          $("full_name").value = "";
          $("email").value = "";
          $("password").value = "";

          await loadUsers();
        } catch (e) {
          console.error("createUser error:", e);
          if (handleAuthError(e)) {
            setMsg(formMsg, `❌ ${e.message} (not authorized)`, false);
          } else {
            setMsg(formMsg, `❌ ${e.message}`, false);
          }
        } finally {
          setLoading(false);
        }
      });
    }

    if (!getToken()) {
      setMsg(formMsg, "⚠️ No token found. Login first (index.html).", false);
      return;
    }

    await refreshAll();
  });
})();
