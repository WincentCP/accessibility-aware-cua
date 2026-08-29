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
const post = (path, body = {}) => api(path, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body)
});

const tasks = [
  { id: "T01", target: "Pilih rute 09:30", verified: 2, status: "Rute dipilih" },
  { id: "T05", target: "Warna", verified: 4, status: "Variasi ditambahkan" },
  { id: "T07", target: "Pilih Selasa 13:35 dengan Rina", verified: 2, status: "Slot dipilih untuk review" },
  { id: "T12", target: "Nama tampilan dummy", verified: 3, status: "Profil dummy disimpan sebagai draft" }
];

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
let bridge;
let lastBenchmarkSessionId;
try {
  const created = await post("/api/study/automatic", { condition_id: "C0" });
  if (!created.response.ok) fail(`Sesi otomatis gagal: ${JSON.stringify(created.payload)}`);
  const studyId = created.payload.study_session_id;
  await post(`/api/study/sessions/${studyId}/recording-state`, { state: "RECORDING" });
  const readiness = await post(`/api/study/sessions/${studyId}/automatic-readiness`, {
    checks: { backend: true, agent: true, microphone: true, camera: true, screen: true, audio: true }
  });
  if (readiness.payload.status !== "READY") fail("Pemeriksaan otomatis tidak menghasilkan READY.");

  let startedTask = await post(`/api/study/sessions/${studyId}/tasks/start`);
  if (!startedTask.response.ok) fail(`Task pertama gagal dibuka: ${JSON.stringify(startedTask.payload)}`);
  await page.goto(`${baseUrl}${startedTask.payload.start_url}`, { waitUntil: "networkidle" });
  bridge = await startBrowserBridge({ page, token: secret, port: 8765 });

  for (let index = 0; index < tasks.length; index += 1) {
    const expected = tasks[index];
    if (startedTask.payload.current_task?.task_id !== expected.id) {
      fail(`Urutan task salah: ${JSON.stringify(startedTask.payload.current_task)}`);
    }
    lastBenchmarkSessionId = startedTask.payload.active_benchmark_session_id;
    const ariaResponse = await fetch("http://127.0.0.1:8765/page/aria", {
      method: "POST",
      headers: { authorization: `Bearer ${secret}`, "content-type": "application/json" },
      body: JSON.stringify({ selector: "body" })
    });
    const aria = await ariaResponse.json();
    if (!aria.snapshot?.includes(expected.target)) {
      fail(`Accessibility snapshot ${expected.id} tidak memuat ${expected.target}.`);
    }

    await post(`/api/study/sessions/${studyId}/voice-state`, { state: "LISTENING" });
    await post(`/api/study/sessions/${studyId}/utterances`, { text: index === 0 ? "iya" : "lanjut" });
    await post(`/api/study/sessions/${studyId}/voice-state`, { state: "AGENT_WORKING" });
    const runStart = await post("/api/agent/runs", {
      benchmark_session_id: lastBenchmarkSessionId,
      goal: startedTask.payload.instruction
    });
    if (runStart.response.status !== 202) fail(`Run ${expected.id} gagal dimulai: ${JSON.stringify(runStart.payload)}`);

    let run = runStart.payload;
    let approved = false;
    const deadline = Date.now() + 45_000;
    while (!["COMPLETED", "FAILED", "CANCELLED"].includes(run.status) && Date.now() < deadline) {
      if (run.status === "WAITING_USER" && run.task_map?.control_state?.approval_pending && !approved) {
        const approval = await post(`/api/agent/runs/${runStart.payload.run_id}/commands`, {
          command: "APPROVE",
          transcript: "saya setuju"
        });
        if (!approval.response.ok) fail(`Persetujuan suara ${expected.id} gagal: ${JSON.stringify(approval.payload)}`);
        run = approval.payload;
        approved = true;
        continue;
      }
      await page.waitForTimeout(200);
      ({ payload: run } = await api(`/api/agent/runs/${runStart.payload.run_id}`));
    }
    if (run.status !== "COMPLETED") fail(`Run ${expected.id} tidak selesai: ${JSON.stringify(run)}`);
    if (run.task_map?.verified_completed?.length !== expected.verified) {
      fail(`${expected.id} tidak memuat ${expected.verified} langkah terverifikasi.`);
    }
    if (!await page.getByRole("status").filter({ hasText: expected.status }).isVisible()) {
      fail(`Status akhir ${expected.id} tidak terlihat.`);
    }

    const completed = await post(`/api/study/sessions/${studyId}/tasks/complete`, { outcome: "AGENT_VERIFIED" });
    if (index === tasks.length - 1) {
      if (completed.payload.status !== "FEEDBACK") fail("Feedback tidak dimulai otomatis setelah Task 4.");
      break;
    }
    startedTask = await post(`/api/study/sessions/${studyId}/tasks/start`);
    await page.goto(`${baseUrl}${startedTask.payload.start_url}`, { waitUntil: "networkidle" });
  }

  await post(`/api/study/sessions/${studyId}/utterances`, {
    text: "Mudah digunakan, tetapi respons suara bisa sedikit lebih cepat."
  });
  const feedback = await post(`/api/study/sessions/${studyId}/feedback`, {
    text: "Mudah digunakan, tetapi respons suara bisa sedikit lebih cepat."
  });
  if (feedback.payload.status !== "CLOSING") fail("Feedback suara tidak tersimpan sebelum penutupan.");
  const finished = await post(`/api/study/sessions/${studyId}/complete`);
  if (finished.payload.status !== "COMPLETED") fail("Sesi tidak selesai setelah feedback suara.");

  await post(`/api/study/sessions/${studyId}/recording-state`, { state: "SAVED" });
  const finalSession = await api(`/api/study/sessions/${studyId}`);
  if (finalSession.payload.recording_state !== "SAVED" || finalSession.payload.voice_state !== "COMPLETE") {
    fail("Lifecycle perekaman atau percakapan tidak selesai dengan benar.");
  }

  await bridge.close();
  bridge = undefined;
  const errorRun = await post("/api/agent/runs", {
    benchmark_session_id: lastBenchmarkSessionId,
    goal: "Ulangi tugas."
  });
  if (errorRun.response.status !== 503 || !String(errorRun.payload.detail || "").trim()) {
    fail(`Bridge failure tidak fail-closed: ${JSON.stringify(errorRun.payload)}`);
  }

  console.log(JSON.stringify({
    status: "PASS",
    tasks: tasks.map((task) => task.id),
    checks: [
      "four_tasks_same_order",
      "accessibility_tree_observed_each_task",
      "semantic_actions_executed",
      "post_action_verification_passed",
      "natural_utterances_recorded",
      "automatic_task_transition",
      "spoken_feedback_saved_before_recording_stop",
      "recording_lifecycle_completed",
      "bridge_error_failed_closed"
    ]
  }, null, 2));
} finally {
  if (bridge) await bridge.close().catch(() => {});
  await browser.close();
}
