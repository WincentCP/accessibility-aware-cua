#!/usr/bin/env node
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";
import { startBrowserBridge } from "./browser-bridge.mjs";

const root = resolve(import.meta.dirname, "..");
const checkMode = process.argv.includes("--check");
const env = { ...process.env };
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const envPath = resolve(root, ".env");
if (existsSync(envPath)) {
  for (const raw of readFileSync(envPath, "utf8").split(/\r?\n/u)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...parts] = line.split("=");
    if (!(key in env)) env[key] = parts.join("=").trim();
  }
}
env.CUA_PLANNER_PROVIDER = checkMode ? "deterministic" : "gemini";
env.CUA_TTS_PROVIDER = "gemini";
const apiPort = Number(env.CUA_PORT || 8000);
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
env.CUA_TEST_API_BASE_URL = apiBaseUrl;

const pythonCandidates = process.platform === "win32"
  ? [resolve(root, ".venv", "Scripts", "python.exe"), "python"]
  : [resolve(root, ".venv", "bin", "python"), "python3"];
const python = pythonCandidates.find((candidate) => candidate === "python" || candidate === "python3" || existsSync(candidate));
if (!python) throw new Error("Python project tidak ditemukan. Jalankan setup satu kali terlebih dahulu.");

const children = [];
const run = (command, args, options = {}) => new Promise((resolvePromise, reject) => {
  const child = spawn(command, args, {
    cwd: root,
    env,
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options
  });
  child.once("error", reject);
  child.once("exit", (code) => code === 0 ? resolvePromise() : reject(new Error(`${command} selesai dengan kode ${code}`)));
});
const waitForHealth = async () => {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${apiBaseUrl}/health`);
      if (response.ok) {
        const health = await response.json();
        if (health.planner_provider !== env.CUA_PLANNER_PROVIDER) {
          throw new Error(
            `Server aktif memakai ${health.planner_provider}, bukan ${env.CUA_PLANNER_PROVIDER}. Tutup sesi aktif lalu coba lagi.`
          );
        }
        return;
      }
    } catch (error) {
      if (error instanceof Error && error.message.startsWith("Server aktif memakai")) throw error;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
  throw new Error("Server tidak siap dalam 30 detik. Periksa .runtime/logs atau output launcher.");
};
const stopChildren = () => {
  for (const child of children) if (!child.killed) child.kill();
};
process.once("SIGINT", () => { stopChildren(); process.exit(130); });
process.once("SIGTERM", () => { stopChildren(); process.exit(143); });

try {
  if (!checkMode && !env.GEMINI_API_KEY) {
    throw new Error("GEMINI_API_KEY belum diisi di .env. Runtime penelitian hanya memakai Gemini.");
  }
  if (!checkMode && String(env.CUA_REQUIRE_POSTGRES).toLowerCase() === "true") {
    console.log("Menyiapkan database penelitian...");
    await run("docker", ["compose", "up", "-d", "postgres"]);
    let databaseReady = false;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        await run("docker", ["compose", "exec", "-T", "postgres", "pg_isready", "-U", "cua", "-d", "cua"]);
        databaseReady = true;
        break;
      } catch {
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 500));
      }
    }
    if (!databaseReady) throw new Error("PostgreSQL belum siap. Pastikan Docker Desktop sedang berjalan.");
  }
  console.log("Menyiapkan tampilan asisten...");
  await run(npmCommand, ["run", "extension:build"]);
  let ownsServer = false;
  let existingResponse = null;
  try {
    existingResponse = await fetch(`${apiBaseUrl}/health`);
  } catch {}
  if (existingResponse?.ok) {
    const health = await existingResponse.json();
    if (health.planner_provider !== env.CUA_PLANNER_PROVIDER) {
      throw new Error(
        `Server pada port ${apiPort} sedang memakai ${health.planner_provider}. Tutup sesi tersebut terlebih dahulu.`
      );
    }
  } else {
    const serverArgs = checkMode
      ? ["scripts/run_live_test_server.py"]
      : ["-m", "uvicorn", "apps.api.a11y_api.app:app", "--host", "127.0.0.1", "--port", String(apiPort)];
    const server = spawn(python, serverArgs, { cwd: root, env, stdio: "inherit" });
    children.push(server);
    ownsServer = true;
  }
  await waitForHealth();

  if (checkMode) {
    await run("node", ["scripts/test-live-agent-e2e.mjs"]);
    console.log("Pemeriksaan otomatis selesai dan semua pemeriksaan utama lulus.");
  } else {
    const extension = resolve(root, "apps", "extension", "dist");
    const profile = resolve(root, env.CUA_BROWSER_PROFILE_DIR || ".runtime/playwright-profile");
    const context = await chromium.launchPersistentContext(profile, {
      headless: false,
      args: [
        `--disable-extensions-except=${extension}`,
        `--load-extension=${extension}`,
        "--autoplay-policy=no-user-gesture-required"
      ]
    });
    await (context.serviceWorkers()[0] ? Promise.resolve() : context.waitForEvent("serviceworker"));
    const researcher = context.pages()[0] ?? await context.newPage();
    const taskSurface = () => researcher.frames().find((frame) => {
      try {
        const url = new URL(frame.url());
        return url.hostname === "127.0.0.1" && url.searchParams.has("session_id");
      } catch { return false; }
    }) ?? researcher;
    const bridge = await startBrowserBridge({
      page: researcher,
      getPage: taskSurface,
      token: env.CUA_APP_SECRET,
      port: Number(env.CUA_BROWSER_BRIDGE_PORT || 8765)
    });
    await researcher.goto(`${apiBaseUrl}/researcher`, { waitUntil: "networkidle" });
    console.log("Researcher Console siap. Tutup browser untuk menghentikan seluruh service.");
    await new Promise((resolvePromise) => context.once("close", resolvePromise));
    await bridge.close();
  }
  if (ownsServer) stopChildren();
} catch (error) {
  stopChildren();
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
