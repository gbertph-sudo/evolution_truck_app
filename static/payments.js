const TASKS_CHECKLIST_CONFIG = {
  key: "tasks_checklist",
  title: "Tasks / Checklist",
  apiPrefix: "/tasks-checklist"
};

async function loadTASKS_CHECKLISTMeta() {
  const statusBox = document.getElementById("module-status");
  if (!statusBox) return;

  statusBox.textContent = "Loading...";
  try {
    const response = await fetch(`${TASKS_CHECKLIST_CONFIG.apiPrefix}/meta`);
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
      <strong>Module:</strong> Tasks / Checklist<br>
      <strong>Status:</strong> placeholder only<br>
      <strong>Message:</strong> API router not mounted yet or backend is offline.
    `;
    console.error("Meta load failed:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("open-api-meta");
  if (btn) {
    btn.addEventListener("click", loadTASKS_CHECKLISTMeta);
  }
  loadTASKS_CHECKLISTMeta();
});
