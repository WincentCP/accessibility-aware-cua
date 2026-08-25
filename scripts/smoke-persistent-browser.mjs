#!/usr/bin/env node
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";

const runtime = resolve(import.meta.dirname, "..", ".runtime");
await mkdir(runtime, { recursive: true });
const profile = await mkdtemp(resolve(runtime, "persistent-smoke-"));

try {
  const context = await chromium.launchPersistentContext(profile, { headless: true });
  const page = context.pages()[0] ?? await context.newPage();
  await page.setContent('<html lang="id"><title>Smoke</title><h1>Browser siap</h1></html>');
  const visible = await page.getByRole("heading", { name: "Browser siap" }).isVisible();
  if (!visible) throw new Error("Persistent page did not render its heading.");
  await context.close();
  console.log("Persistent Chromium PASS: isolated project profile rendered successfully.");
} finally {
  await rm(profile, { recursive: true, force: true });
}
