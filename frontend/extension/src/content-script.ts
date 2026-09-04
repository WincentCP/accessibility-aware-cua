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

const CONTENT_SCRIPT_READY = "__a11yCuaContentScriptReady";

const handleRuntimeMessage = (message: unknown, _sender: chrome.runtime.MessageSender, sendResponse: (response?: unknown) => void): boolean => {
  if (!message || typeof message !== "object") return false;
  const payload = message as { type?: string; text?: string; target?: SemanticFocusTarget; map?: AccessibleTaskMap };
  if (payload.type === "FOCUS_HANDOFF" && payload.target) {
    const result = focusSemanticTarget(payload.target);
    sendResponse(result);
    return false;
  }
  if (payload.type === "UPDATE_TASK_MAP_BRIDGE" && payload.map) {
    sanitizeTaskMap(payload.map);
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

window.addEventListener("a11y-cua:study-onboarding-ready", (event) => {
  const studySessionId = (event as CustomEvent<{ studySessionId?: string }>).detail?.studySessionId
    ?? document.documentElement.dataset.studySessionId;
  if (studySessionId) {
    void chrome.runtime.sendMessage({ type: "STUDY_ONBOARDING_READY", studySessionId })
      .then((result) => {
        window.dispatchEvent(new CustomEvent(
          result?.success ? "a11y-cua:coordinator-ready" : "a11y-cua:coordinator-error",
          { detail: { studySessionId, error: result?.error } }
        ));
      })
      .catch((error) => {
        window.dispatchEvent(new CustomEvent("a11y-cua:coordinator-error", {
          detail: { studySessionId, error: String(error) }
        }));
      });
  }
});
