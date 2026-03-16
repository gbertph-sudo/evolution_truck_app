const WARRANTY_RETURNS_CONFIG = {
  key: "warranty_returns",
  title: "Warranty / Returns",
  apiPrefix: "/warranty-returns"
};

async function loadWARRANTY_RETURNSMeta() {
  const statusBox = document.getElementById("module-status");
  if (!statusBox) return;

  statusBox.textContent = "Loading...";
  try {
    const response = await fetch(`${WARRANTY_RETURNS_CONFIG.apiPrefix}/meta`);
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
      <strong>Module:</strong> Warranty / Returns<br>
      <strong>Status:</strong> placeholder only<br>
      <strong>Message:</strong> API router not mounted yet or backend is offline.
    `;
    console.error("Meta load failed:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("open-api-meta");
  if (btn) {
    btn.addEventListener("click", loadWARRANTY_RETURNSMeta);
  }
  loadWARRANTY_RETURNSMeta();
});
