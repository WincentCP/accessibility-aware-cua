export interface SemanticFocusTarget {
  role: string;
  name: string;
}

export interface FocusBridgeResult {
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

export const focusSemanticTarget = (target: SemanticFocusTarget): FocusBridgeResult => {
  const extensionRoot = document.querySelector("[data-a11y-cua-extension]");
  const candidates = [...document.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea, [role]")]
    .filter((element) => !extensionRoot?.contains(element))
    .filter((element) => nativeRole(element) === target.role.toLowerCase())
    .filter((element) => accessibleName(element) === normalize(target.name));
  if (candidates.length !== 1) {
    return {
      success: false,
      matchCount: candidates.length,
      announcement:
        candidates.length === 0
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
