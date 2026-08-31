import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(resolve(root, "dist/manifest.json"), "utf8"));
const html = await readFile(resolve(root, "dist/sidepanel.html"), "utf8");
const contentScript = await readFile(resolve(root, "dist/content-script.js"), "utf8");
const assets = (await import("node:fs/promises")).readdir(resolve(root, "dist/assets"));

const failures = [];
if (manifest.manifest_version !== 3) failures.push("manifest_version must be 3");
if (manifest.side_panel) failures.push("participant-facing side_panel must not be registered");
if (manifest.permissions?.includes("tabs")) failures.push("broad tabs permission is not allowed");
if (manifest.permissions?.includes("sidePanel")) failures.push("sidePanel permission is not allowed");
if (!manifest.permissions?.includes("scripting")) failures.push("targeted scripting fallback is missing");
if (!manifest.permissions?.includes("offscreen")) failures.push("background study coordinator permission is missing");
if (!manifest.content_scripts?.[0]?.js?.includes("content-script.js")) failures.push("content script is missing");
if (!html.includes('lang="id"')) failures.push("side panel language is missing");
if (!html.includes("main-content")) failures.push("skip target is missing");
if (!html.includes("task-map")) failures.push("task-map landmark is missing");
for (const control of ["APPROVE", "EDIT", "REJECT", "PAUSE", "TAKE_OVER", "RESUME", "CANCEL"]) {
  if (!html.includes(`data-command="${control}"`)) failures.push(`${control} control is missing`);
}
if (contentScript.includes("a11y-cua-in-page-panel")) failures.push("participant-facing in-page panel is still bundled");
if (!contentScript.includes("study-onboarding-ready")) failures.push("hands-free onboarding bridge is missing");
if (/^\s*import\s/mu.test(contentScript)) failures.push("manifest content script must be a standalone classic script");
if (!(await assets).some((name) => name.endsWith(".js"))) failures.push("side-panel bundle is missing");
if (failures.length) {
  throw new Error(failures.join("; "));
}
console.log("Extension artifact PASS: MV3, background coordinator, focus bridge, and least privilege.");
