document.addEventListener("DOMContentLoaded", () => {
  const user = localStorage.getItem("user_name");
  const role = localStorage.getItem("user_role");

  if (!user) {
    // no está logueado → vuelve al login
    window.location.href = "/static/index.html";
    return;
  }

  const info = document.getElementById("userInfo");
  if (info) {
    info.textContent = '${user} (${role})';
  }

  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.onclick = () => {
      localStorage.clear();
      window.location.href = "/static/index.html";
    };
  }
});