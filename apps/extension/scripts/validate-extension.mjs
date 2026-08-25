import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(resolve(root, "dist/manifest.json"), "utf8"));
const html = await readFile(resolve(root, "dist/sidepanel.html"), "utf8");

const failures = [];
if (manifest.manifest_version !== 3) failures.push("manifest_version must be 3");
if (!manifest.side_panel?.default_path) failures.push("side_panel.default_path is missing");
if (manifest.permissions?.includes("tabs")) failures.push("broad tabs permission is not allowed");
if (!html.includes('lang="id"')) failures.push("side panel language is missing");
if (!html.includes("main-content")) failures.push("skip target is missing");
if (!html.includes("task-map")) failures.push("task-map landmark is missing");
if (failures.length) {
  throw new Error(failures.join("; "));
}
console.log("Extension artifact PASS: MV3, side panel, least privilege, and accessible shell present.");
