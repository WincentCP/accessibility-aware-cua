import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("researcher can prepare a hands-free cold-start session", async ({ page }) => {
  await page.goto("/researcher");
  await expect(page.getByRole("heading", { name: "Siapkan satu sesi" })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

  await page.getByLabel("Kode peserta").fill("P01");
  await page.getByRole("button", { name: "Siapkan sesi" }).click();
  await expect(page.getByRole("heading", { name: "Catat jawaban persetujuan" })).toBeVisible();

  for (const label of [
    "Menyimpan nama peserta",
    "Mengambil foto dokumentasi",
    "Merekam webcam dan suara",
    "Merekam layar"
  ]) {
    const row = page.locator(".consent-row").filter({ hasText: label });
    await row.getByRole("button", { name: "Setuju" }).click();
  }

  await expect(page.getByRole("heading", { name: "Cek singkat sebelum mulai" })).toBeVisible();
  for (const label of ["Suara terdengar jelas", "Pembaca layar siap"]) {
    const row = page.locator(".consent-row").filter({ hasText: label });
    await row.getByRole("button", { name: "Siap" }).click();
  }

  await expect(page.getByText("Kegiatan 1 dari 4")).toBeVisible();
  await expect(page.locator("#task-instruction")).toContainText("Medan ke Bali");
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Buka kegiatan" }).click();
  const participant = await popupPromise;
  await participant.waitForLoadState("domcontentloaded");

  await expect(participant).toHaveURL(/study_session_id=/u);
  await expect(participant.getByText("Cari rute Medan")).toHaveCount(0);
  await expect(participant.getByText(/C0|seed/u)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Tandai selesai" })).toBeVisible();
});

test("minor session cannot begin without guardian verification", async ({ page }) => {
  await page.goto("/researcher");
  await page.getByLabel("Kode peserta").fill("P02");
  await page.getByLabel("Peserta masih di bawah umur").check();
  await page.getByRole("button", { name: "Siapkan sesi" }).click();
  await expect(page.getByRole("alert")).toContainText("orang tua atau wali");
});
