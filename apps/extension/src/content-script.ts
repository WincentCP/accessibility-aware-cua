import { focusSemanticTarget, type SemanticFocusTarget } from "./focus-bridge";
import type { AccessibleTaskMap } from "./contracts";
import { sanitizeTaskMap } from "./task-map";

const PANEL_ID = "a11y-cua-in-page-panel";

const injectPanel = (): void => {
  if (!document.body || document.getElementById(PANEL_ID)) return;
  const pageMain = document.querySelector<HTMLElement>("main");
  if (pageMain && !pageMain.id) pageMain.id = "a11y-cua-page-content";
  const skipTarget = pageMain?.id ? `#${pageMain.id}` : "#a11y-cua-open-panel";
  const panel = document.createElement("aside");
  panel.id = PANEL_ID;
  panel.dataset.a11yCuaExtension = "true";
  panel.setAttribute("aria-label", "Accessibility-Aware CUA extension panel");
  panel.innerHTML = `
    <style>
      #${PANEL_ID}{font:16px/1.5 system-ui,sans-serif;padding:.75rem;border:3px solid #075db7;background:#fff;color:#17202a}
      #${PANEL_ID} h2{font-size:1.1rem;margin:0 0 .35rem}
      #${PANEL_ID} p{margin:.25rem 0}
      #${PANEL_ID} button,#${PANEL_ID} a{display:inline-block;margin:.25rem .5rem .25rem 0;padding:.5rem;min-height:44px}
      #${PANEL_ID} :focus-visible{outline:4px solid #ffbf47;outline-offset:2px}
    </style>
    <h2>Panel agen aksesibel</h2>
    <p id="a11y-cua-bridge-status" role="status" aria-live="polite" aria-atomic="true">Panel siap.</p>
    <p><strong>Tujuan:</strong> <span id="a11y-cua-bridge-goal">Belum ada.</span></p>
    <p><strong>Progres:</strong> <span id="a11y-cua-bridge-progress">0 langkah terverifikasi selesai.</span></p>
    <p><strong>Berikutnya, direncanakan:</strong> <span id="a11y-cua-bridge-next">Belum ada.</span></p>
    <button id="a11y-cua-open-panel" type="button">Buka kontrol dan peta tugas</button>
    <button type="button" data-a11y-cua-command="PAUSE">Jeda agen</button>
    <button type="button" data-a11y-cua-command="TAKE_OVER">Ambil alih</button>
    <a href="${skipTarget}">Lewati panel agen ke halaman web</a>`;
  document.body.prepend(panel);
  panel.querySelector<HTMLButtonElement>("#a11y-cua-open-panel")?.addEventListener("click", () => {
    void chrome.runtime.sendMessage({ type: "OPEN_SIDE_PANEL" });
  });
  panel.querySelectorAll<HTMLButtonElement>("[data-a11y-cua-command]").forEach((button) => {
    button.addEventListener("click", () => {
      void chrome.runtime.sendMessage({ type: "SHARED_CONTROL", command: button.dataset.a11yCuaCommand });
    });
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", injectPanel, { once: true });
} else {
  injectPanel();
}

chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (!message || typeof message !== "object") return false;
  const payload = message as { type?: string; text?: string; target?: SemanticFocusTarget; map?: AccessibleTaskMap };
  const status = document.querySelector<HTMLElement>("#a11y-cua-bridge-status");
  if (payload.type === "UPDATE_BRIDGE_STATUS" && typeof payload.text === "string") {
    if (status) status.textContent = payload.text;
    sendResponse({ success: true });
    return false;
  }
  if (payload.type === "FOCUS_HANDOFF" && payload.target) {
    const result = focusSemanticTarget(payload.target);
    if (status) status.textContent = result.announcement;
    sendResponse(result);
    return false;
  }
  if (payload.type === "UPDATE_TASK_MAP_BRIDGE" && payload.map) {
    const map = sanitizeTaskMap(payload.map).map;
    const goal = document.querySelector<HTMLElement>("#a11y-cua-bridge-goal");
    const progress = document.querySelector<HTMLElement>("#a11y-cua-bridge-progress");
    const next = document.querySelector<HTMLElement>("#a11y-cua-bridge-next");
    if (goal) goal.textContent = map.goal;
    if (progress) progress.textContent = map.progress_label;
    if (next) next.textContent = map.next_action?.label ?? "Belum ada.";
    if (status) status.textContent = "Peta tugas di halaman diperbarui.";
    sendResponse({ success: true });
    return false;
  }
  return false;
});
