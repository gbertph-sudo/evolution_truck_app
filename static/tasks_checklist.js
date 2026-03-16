const ROLES_PERMISSIONS_CONFIG = {
  key: "roles_permissions",
  title: "Roles & Permissions",
  apiPrefix: "/roles-permissions"
};

async function loadROLES_PERMISSIONSMeta() {
  const statusBox = document.getElementById("module-status");
  if (!statusBox) return;

  statusBox.textContent = "Loading...";
  try {
    const response = await fetch(`${ROLES_PERMISSIONS_CONFIG.apiPrefix}/meta`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    statusBox.innerHTML = `
      <strong>Connected:</strong> Yes<br>
      <strong>Module:</strong> ${data.title}<br>
      <strong>Status:</strong> ${data.status}<br>
      <strong>Message:</strong> ${data.message}
    `;
  } catch (error) {
    statusBox.innerHTML = `
      <strong>Connected:</strong> No<br>
      <strong>Module:</strong> Roles & Permissions<br>
      <strong>Status:</strong> placeholder only<br>
      <strong>Message:</strong> API router not mounted yet or backend is offline.
    `;
    console.error("Meta load failed:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("open-api-meta");
  if (btn) {
    btn.addEventListener("click", loadROLES_PERMISSIONSMeta);
  }
  loadROLES_PERMISSIONSMeta();
});
