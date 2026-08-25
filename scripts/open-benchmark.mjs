#!/usr/bin/env node
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { chromium } from "playwright";

const root = resolve(import.meta.dirname, "..");
const envPath = resolve(root, ".env");
if (existsSync(envPath)) {
  for (const rawLine of readFileSync(envPath, "utf8").split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...parts] = line.split("=");
    if (!(key in process.env)) process.env[key] = parts.join("=").trim();
  }
}

const flags = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const key = process.argv[index];
  if (!key.startsWith("--")) continue;
  const next = process.argv[index + 1];
  if (next && !next.startsWith("--")) {
    flags.set(key, next);
    index += 1;
  } else {
    flags.set(key, true);
  }
}

const taskId = String(flags.get("--task") ?? "T01");
const conditionId = String(flags.get("--condition") ?? "C0");
if (!/^T(?:0[1-9]|1[0-2])$/u.test(taskId)) throw new Error("--task harus T01 sampai T12.");
if (!/^C[0-2]$/u.test(conditionId)) throw new Error("--condition harus C0, C1, atau C2.");

const stableInt = (text, digits) => {
  const hex = createHash("sha256").update(text).digest("hex").slice(0, 15);
  return Number(BigInt(`0x${hex}`) % (10n ** BigInt(digits)));
};
const repetition = 1;
const defaultSeed = 300_000_000 + stableInt(`final-v1|${taskId}|${conditionId}|${repetition}`, 8);
const seed = Number(flags.get("--seed") ?? defaultSeed);
if (!Number.isSafeInteger(seed) || seed < 0) throw new Error("--seed harus integer non-negatif.");

const baseUrl = String(flags.get("--base-url") ?? "http://127.0.0.1:8000").replace(/\/$/u, "");
const resetResponse = await fetch(`${baseUrl}/api/benchmark/reset`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ task_id: taskId, condition_id: conditionId, seed })
}).catch((error) => {
  throw new Error(`API tidak dapat dihubungi di ${baseUrl}. Jalankan server terlebih dahulu.`, { cause: error });
});
if (!resetResponse.ok) throw new Error(`Reset API gagal: ${await resetResponse.text()}`);
const reset = await resetResponse.json();

const profileValue = process.env.CUA_BROWSER_PROFILE_DIR ?? ".runtime/playwright-profile";
const profile = resolve(root, profileValue);
if (!(profile === root || profile.startsWith(`${root}${sep}`))) {
  throw new Error("Profil browser harus berada di dalam project; profil Chrome pribadi dilarang.");
}

const withExtension = flags.has("--with-extension");
const extension = resolve(root, "apps", "extension", "dist");
const browserArgs = [];
if (withExtension) {
  if (!existsSync(resolve(extension, "manifest.json"))) {
    throw new Error("Build extension dahulu dengan: npm run extension:build");
  }
  browserArgs.push(`--disable-extensions-except=${extension}`, `--load-extension=${extension}`);
}
const headless = flags.has("--headless") || process.env.CUA_BROWSER_HEADLESS === "true";
const context = await chromium.launchPersistentContext(profile, { headless, args: browserArgs });
const page = context.pages()[0] ?? await context.newPage();
const taskUrl = `${baseUrl}${reset.start_url}`;
await page.goto(taskUrl, { waitUntil: "networkidle" });
console.log(`Membuka ${taskId} (${conditionId}, seed ${seed}) di ${taskUrl}`);
console.log("Tekan Enter di terminal untuk menutup browser.");
const readline = createInterface({ input: stdin, output: stdout });
await readline.question("");
readline.close();
await context.close().catch((error) => {
  if (!String(error).includes("Target page, context or browser has been closed")) throw error;
});
