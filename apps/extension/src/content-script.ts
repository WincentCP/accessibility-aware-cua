import { focusSemanticTarget, type SemanticFocusTarget } from "./focus-bridge";
import type { AccessibleTaskMap } from "./contracts";
import { sanitizeTaskMap } from "./task-map";

const PANEL_ID = "a11y-cua-in-page-panel";
const CONTENT_SCRIPT_READY = "__a11yCuaContentScriptReady";

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
    <button id="a11y-cua-open-panel" type="button">Mulai dan buka asisten</button>
    <button type="button" data-a11y-cua-command="PAUSE">Jeda agen</button>
    <button type="button" data-a11y-cua-command="TAKE_OVER">Ambil alih</button>
    <a href="${skipTarget}">Lewati panel agen ke halaman web</a>`;
  document.body.prepend(panel);
  panel.querySelector<HTMLButtonElement>("#a11y-cua-open-panel")?.addEventListener("click", async (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    const status = panel.querySelector<HTMLElement>("#a11y-cua-bridge-status");
    button.disabled = true;
    if (status) status.textContent = "Membuka asisten.";
    try {
      const result = await chrome.runtime.sendMessage({ type: "OPEN_SIDE_PANEL" }) as { success?: boolean };
      if (!result?.success) throw new Error("Side panel tidak dapat dibuka.");
      if (status) status.textContent = "Asisten terbuka. Lanjutkan di panel sebelah kanan.";
      button.textContent = "Buka kembali asisten";
      button.disabled = false;
    } catch {
      button.disabled = false;
      if (status) status.textContent = "Asisten belum dapat dibuka. Tekan tombol ini untuk mencoba lagi.";
    }
  });
  panel.querySelectorAll<HTMLButtonElement>("[data-a11y-cua-command]").forEach((button) => {
    button.addEventListener("click", () => {
      void chrome.runtime.sendMessage({ type: "SHARED_CONTROL", command: button.dataset.a11yCuaCommand });
    });
  });
};

const handleRuntimeMessage = (message: unknown, _sender: chrome.runtime.MessageSender, sendResponse: (response?: unknown) => void): boolean => {
  if (!message || typeof message !== "object") return false;
  const payload = message as { type?: string; text?: string; target?: SemanticFocusTarget; map?: AccessibleTaskMap };
  if (payload.type === "ENSURE_IN_PAGE_PANEL") {
    injectPanel();
    sendResponse({ success: Boolean(document.getElementById(PANEL_ID)) });
    return false;
  }
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
};

const contentWindow = window as typeof window & { [CONTENT_SCRIPT_READY]?: boolean };
if (!contentWindow[CONTENT_SCRIPT_READY]) {
  contentWindow[CONTENT_SCRIPT_READY] = true;
  chrome.runtime.onMessage.addListener(handleRuntimeMessage);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", injectPanel, { once: true });
} else {
  injectPanel();
}
