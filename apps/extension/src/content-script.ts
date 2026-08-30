import type { AccessibleTaskMap, TaskMapItem } from "./contracts";

interface SemanticFocusTarget {
  role: string;
  name: string;
}

interface FocusBridgeResult {
  success: boolean;
  matchCount: number;
  announcement: string;
}

const normalize = (value: string): string => value.replace(/\s+/gu, " ").trim();

const nativeRole = (element: HTMLElement): string => {
  const explicit = element.getAttribute("role");
  if (explicit) return explicit.toLowerCase();
  if (element instanceof HTMLButtonElement) return "button";
  if (element instanceof HTMLAnchorElement && element.hasAttribute("href")) return "link";
  if (element instanceof HTMLSelectElement) return "combobox";
  if (element instanceof HTMLTextAreaElement) return "textbox";
  if (element instanceof HTMLInputElement) {
    if (element.type === "checkbox") return "checkbox";
    if (element.type === "radio") return "radio";
    if (element.type === "button" || element.type === "submit") return "button";
    return "textbox";
  }
  return "";
};

const accessibleName = (element: HTMLElement): string => {
  const ariaLabel = element.getAttribute("aria-label");
  if (ariaLabel) return normalize(ariaLabel);
  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const label = labelledBy
      .split(/\s+/u)
      .map((id) => document.getElementById(id)?.textContent ?? "")
      .join(" ");
    if (normalize(label)) return normalize(label);
  }
  if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
    if (element.labels?.length) return normalize([...element.labels].map((label) => label.textContent ?? "").join(" "));
  }
  return normalize(element.textContent || element.getAttribute("value") || "");
};

const focusSemanticTarget = (target: SemanticFocusTarget): FocusBridgeResult => {
  const extensionRoot = document.querySelector("[data-a11y-cua-extension]");
  const candidates = [...document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea, [role]")]
    .filter((element) => !extensionRoot?.contains(element))
    .filter((element) => nativeRole(element) === target.role.toLowerCase())
    .filter((element) => accessibleName(element) === normalize(target.name));
  if (candidates.length !== 1) {
    return {
      success: false,
      matchCount: candidates.length,
      announcement: candidates.length === 0
        ? `Target ${target.name} tidak ditemukan. Gunakan heading atau Tab untuk melanjutkan.`
        : `Target ${target.name} tidak unik. Gunakan heading atau Tab untuk memilih kontrol yang tepat.`
    };
  }
  candidates[0].focus();
  const success = document.activeElement === candidates[0];
  return {
    success,
    matchCount: 1,
    announcement: success
      ? `Fokus dipindahkan ke ${target.role} ${target.name}.`
      : `Fokus ke ${target.name} gagal. Gunakan heading atau Tab untuk melanjutkan.`
  };
};

const isAuditableCompleted = (item: TaskMapItem): boolean =>
  item.status === "VERIFIED_COMPLETED" && Boolean(item.verification_id) && item.evidence.length > 0;

const isFreshSemanticItem = (item: TaskMapItem, version: number): boolean =>
  item.observation_version === version && Boolean(item.semantic_ref);

const sanitizeTaskMap = (source: AccessibleTaskMap): { map: AccessibleTaskMap; invalidatedCount: number } => {
  let invalidatedCount = source.stale_invalidated_count;
  const completed = source.verified_completed.filter((item) => {
    const keep = isAuditableCompleted(item);
    if (!keep) invalidatedCount += 1;
    return keep;
  });
  const relevant = source.relevant_options.filter((item) => {
    const keep = item.status === "RELEVANT" && isFreshSemanticItem(item, source.observation_version);
    if (!keep) invalidatedCount += 1;
    return keep;
  });
  const next = source.next_action;
  const nextAction = next && next.status === "PLANNED" && isFreshSemanticItem(next, source.observation_version)
    ? next : null;
  if (next && !nextAction) invalidatedCount += 1;
  return {
    map: {
      ...source,
      verified_completed: completed,
      relevant_options: relevant,
      next_action: nextAction,
      uncertain_items: source.uncertain_items.filter((item) => item.status === "UNCERTAIN"),
      stale_invalidated_count: invalidatedCount
    },
    invalidatedCount
  };
};

const PANEL_ID = "a11y-cua-in-page-panel";
const CONTENT_SCRIPT_READY = "__a11yCuaContentScriptReady";

const injectPanel = (): void => {
  if (!document.body || document.getElementById(PANEL_ID)) return;
  const studyMode = new URL(window.location.href).searchParams.has("study_session_id");
  if (studyMode) return;
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
