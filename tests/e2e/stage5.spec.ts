import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const tasks = [
  ["T01", "/travel/search"],
  ["T02", "/travel/results"],
  ["T03", "/travel/passenger"],
  ["T04", "/marketplace/search"],
  ["T05", "/marketplace/product/mp10"],
  ["T06", "/marketplace/address-draft"],
  ["T07", "/appointment/slots"],
  ["T08", "/appointment/new"],
  ["T09", "/appointment/manage/DEMO-A09"],
  ["T10", "/account/notifications"],
  ["T11", "/account/appearance"],
  ["T12", "/account/profile"]
] as const;

for (const condition of ["C0", "C1", "C2"] as const) {
  test(`36-case rendered accessibility scan: ${condition}`, async ({ page, request }) => {
    for (const [index, [taskId, route]] of tasks.entries()) {
      const response = await request.post("/api/benchmark/reset", {
        data: { task_id: taskId, condition_id: condition, seed: 880_000 + index }
      });
      expect(response.ok()).toBeTruthy();
      const reset = await response.json();
      const externalRequests: string[] = [];
      page.on("request", (item) => {
        const url = new URL(item.url());
        if (url.hostname !== "127.0.0.1") externalRequests.push(item.url());
      });
      await page.goto(reset.start_url);
      await expect(page).toHaveURL(new RegExp(`${route.replaceAll("/", "\\/")}\\?session_id=`));
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      if (process.env.CAPTURE_STAGE5_EVIDENCE === "1" && taskId === "T01") {
        await page.screenshot({
          path: `evidence/stage5_T01_${condition}.png`,
          fullPage: true
        });
      }
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations, `${taskId}-${condition}`).toEqual([]);
      expect(externalRequests, `${taskId}-${condition}`).toEqual([]);
    }
  });
}

test("keyboard can reach and operate every task form", async ({ page, request }) => {
  for (const [index, [taskId]] of tasks.entries()) {
    const response = await request.post("/api/benchmark/reset", {
      data: { task_id: taskId, condition_id: "C0", seed: 890_000 + index }
    });
    const reset = await response.json();
    await page.goto(reset.start_url);
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveClass(/skip-link/);
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    const controls = page.locator("form input, form select, form textarea, form button");
    expect(await controls.count(), taskId).toBeGreaterThan(0);
    for (let controlIndex = 0; controlIndex < await controls.count(); controlIndex += 1) {
      await expect(controls.nth(controlIndex), `${taskId} control ${controlIndex}`).toBeEnabled();
    }
  }
});
