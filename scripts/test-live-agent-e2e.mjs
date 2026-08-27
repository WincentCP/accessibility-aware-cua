#!/usr/bin/env node
import { chromium } from "playwright";
import { startBrowserBridge } from "./browser-bridge.mjs";

const baseUrl = process.env.CUA_TEST_API_BASE_URL || "http://127.0.0.1:8000";
const secret = "local-test-agent-secret-2026-safe";
const fail = (message) => { throw new Error(message); };
const api = async (path, init) => {
  const response = await fetch(`${baseUrl}${path}`, init);
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  return { response, payload };
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
let bridge;
try {
  const { response: resetResponse, payload: reset } = await api("/api/benchmark/reset", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ task_id: "T01", condition_id: "C0", seed: 970000 })
  });
  if (!resetResponse.ok) fail(`Reset gagal: ${JSON.stringify(reset)}`);
  await page.goto(`${baseUrl}${reset.start_url}`, { waitUntil: "networkidle" });
  bridge = await startBrowserBridge({ page, token: secret, port: 8765 });

  const ariaResponse = await fetch("http://127.0.0.1:8765/page/aria", {
    method: "POST",
    headers: { authorization: `Bearer ${secret}`, "content-type": "application/json" },
    body: JSON.stringify({ selector: "body" })
  });
  const aria = await ariaResponse.json();
  if (!aria.snapshot?.includes("Pilih rute 09:45")) fail("Accessibility snapshot tidak memuat rute target.");

  const { response: startResponse, payload: started } = await api("/api/agent/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      benchmark_session_id: reset.session_id,
      goal: "Pilih perjalanan jam 09.00 sampai 11.30 dengan harga maksimal Rp900.000 dan berhenti sebelum pemesanan."
    })
  });
  if (startResponse.status !== 202) fail(`Live run gagal dimulai: ${JSON.stringify(started)}`);

  let run = started;
  let approved = false;
  const deadline = Date.now() + 30_000;
  while (!["COMPLETED", "FAILED", "CANCELLED"].includes(run.status) && Date.now() < deadline) {
    if (run.status === "WAITING_USER" && run.task_map?.control_state?.approval_pending && !approved) {
      const approval = await api(`/api/agent/runs/${started.run_id}/commands`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ command: "APPROVE", transcript: "saya setuju" })
      });
      if (!approval.response.ok) fail(`Persetujuan suara gagal: ${JSON.stringify(approval.payload)}`);
      run = approval.payload;
      approved = true;
      continue;
    }
    await page.waitForTimeout(250);
    ({ payload: run } = await api(`/api/agent/runs/${started.run_id}`));
  }
  if (run.status !== "COMPLETED") fail(`Run tidak selesai: ${JSON.stringify(run)}`);
  if (!run.task_map?.verified_completed || run.task_map.verified_completed.length !== 2) {
    fail("Task map tidak memuat dua langkah yang lolos verifikasi pasca-aksi.");
  }
  if (!await page.getByRole("status").filter({ hasText: /Rute dipilih/u }).isVisible()) {
    fail("Status akhir halaman tidak terlihat.");
  }
  if (!await page.getByRole("radio", { name: "Pilih rute 09:45" }).isChecked()) {
    fail("Agent tidak memilih rute melalui kontrol semantik.");
  }

  await bridge.close();
  bridge = undefined;
  const { response: errorResponse, payload: errorPayload } = await api("/api/agent/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ benchmark_session_id: reset.session_id, goal: "Ulangi tugas." })
  });
  if (errorResponse.status !== 503 || !String(errorPayload.detail || "").trim()) {
    fail(`Bridge failure tidak fail-closed: ${JSON.stringify(errorPayload)}`);
  }

  console.log(JSON.stringify({
    status: "PASS",
    checks: [
      "accessibility_tree_observed",
      "semantic_actions_executed",
      "post_action_verification_passed",
      "explicit_voice_approval_consumed_once",
      "verified_task_map_updated",
      "final_ui_state_visible",
      "bridge_error_failed_closed"
    ]
  }, null, 2));
} finally {
  if (bridge) await bridge.close().catch(() => {});
  await browser.close();
}
