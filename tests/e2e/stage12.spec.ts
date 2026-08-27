import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const panelUrl = "http://127.0.0.1:4173/sidepanel.html";

const sampleMap = {
  schema_version: "1.0.0", map_id: "map-1", session_id: "session-1", run_id: "run-1",
  version: 3, observation_version: 8, goal: "Cari artikel aksesibilitas",
  progress_label: "1 langkah terverifikasi selesai; 1 langkah belum pasti",
  verified_completed: [{ item_id: "done", label: "Halaman pencarian dibuka", status: "VERIFIED_COMPLETED", semantic_ref: null, observation_version: 8, verification_id: "verify-1", evidence: ["URL berubah"], reason: null }],
  relevant_options: [
    { item_id: "fresh", label: "Artikel A", status: "RELEVANT", semantic_ref: "link:Artikel A", observation_version: 8, verification_id: null, evidence: [], reason: "sesuai tujuan" },
    { item_id: "stale", label: "Artikel lama", status: "RELEVANT", semantic_ref: "link:lama", observation_version: 7, verification_id: null, evidence: [], reason: "lama" }
  ],
  next_action: { item_id: "next", label: "Buka Artikel A", status: "PLANNED", semantic_ref: "link:Artikel A", observation_version: 8, verification_id: null, evidence: [], reason: "rencana" },
  uncertain_items: [{ item_id: "uncertain", label: "Filter mungkin aktif", status: "UNCERTAIN", semantic_ref: null, observation_version: 8, verification_id: "verify-2", evidence: [], reason: "tidak pasti" }],
  control_state: { paused: false, takeover_active: false, approval_pending: true, handoff_status: "NONE" },
  final_summary: null, stale_invalidated_count: 0, generated_at: "2026-08-25T00:00:00Z"
};

test.beforeEach(async ({ page }) => { await page.goto(panelUrl); });

test("panel passes automated accessibility scan and keyboard reflow", async ({ page }) => {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 320, height: 800 });
  const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
  expect(noOverflow).toBe(true);
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
});

test("map keeps verified, planned, uncertain, and stale content separate", async ({ page }) => {
  await page.evaluate((map) => window.dispatchEvent(new CustomEvent("a11y-cua:task-map", { detail: map })), sampleMap);
  await expect(page.locator("#verified-list")).toContainText("Halaman pencarian dibuka");
  await expect(page.locator("#next-action")).toContainText("direncanakan, belum selesai");
  await expect(page.locator("#uncertain-list")).toContainText("Filter mungkin aktif");
  await expect(page.locator("#relevant-list")).not.toContainText("Artikel lama");
  await expect(page.locator("#approval-alert")).toContainText("Persetujuan diperlukan");
});

test("transcript requires review and shared-control shortcuts work", async ({ page }) => {
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("a11y-cua:voice-transcript", { detail: { transcript: "buka artikel aksesibilitas" } })));
  await expect(page.locator("#transcript")).toBeFocused();
  await page.locator("#confirm-transcript").click();
  await expect(page.locator("#goal")).toHaveValue("buka artikel aksesibilitas");
  await page.keyboard.press("Alt+p");
  await expect(page.locator("#status")).toHaveText("Agen dijeda.");
  await page.keyboard.press("Escape");
  await expect(page.locator("#status")).toHaveText("Tindakan ditolak.");
});

test("microphone denial preserves complete text fallback", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => { throw new Error("denied"); } } });
    class FakeRecorder {}
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeRecorder });
  });
  await page.reload();
  await page.locator("#fallback-tools").getByText("Kontrol cadangan").click();
  await page.locator("#voice").click();
  await expect(page.locator("#status")).toContainText("Mikrofon tidak diizinkan");
  await page.locator("#goal").fill("gunakan teks");
  await page.locator("#submit-goal").click();
  await expect(page.locator("#active-goal")).toHaveText("gunakan teks");
});

test("in-page bridge is first landmark and restores real DOM focus for four task types", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/focus-fixture.html");
  await expect(page.locator("body > aside").first()).toHaveAttribute("id", "a11y-cua-in-page-panel");
  await expect(page.locator("#a11y-cua-open-panel")).toHaveText("Mulai dan buka asisten");
  await page.locator("#a11y-cua-open-panel").click();
  await expect(page.locator("#a11y-cua-bridge-status")).toHaveText("Asisten terbuka. Lanjutkan di panel sebelah kanan.");
  await expect(page.locator("#a11y-cua-open-panel")).toBeEnabled();
  await expect(page.locator("#a11y-cua-open-panel")).toHaveText("Buka kembali asisten");
  const cases = [
    ["button", "Pilih rute", "travel"],
    ["textbox", "Cari produk", "marketplace"],
    ["combobox", "Pilih dokter", "appointment"],
    ["checkbox", "Notifikasi email", "account"]
  ];
  for (const [role, name, id] of cases) {
    const result = await page.evaluate(({ role, name }) => new Promise((resolve) => {
      const listener = (window as typeof window & { bridgeListener?: Function }).bridgeListener;
      listener?.({ type: "FOCUS_HANDOFF", target: { role, name } }, {}, resolve);
    }), { role, name });
    expect(result).toMatchObject({ success: true, matchCount: 1 });
    await expect(page.locator(`#${id}`)).toBeFocused();
  }
});
