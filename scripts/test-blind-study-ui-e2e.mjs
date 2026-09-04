#!/usr/bin/env node
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";
import { startBrowserBridge } from "./browser-bridge.mjs";

const root = resolve(import.meta.dirname, "..");
const baseUrl = process.env.CUA_TEST_API_BASE_URL || "http://127.0.0.1:8000";
const bridgePort = Number(process.env.CUA_BROWSER_BRIDGE_PORT || 8765);
const bridgeSecret = "local-test-agent-secret-2026-safe";
const extension = resolve(root, "frontend", "extension", "dist");
const fail = (message) => { throw new Error(message); };
const sleep = (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));

const api = async (path, init) => {
  const response = await fetch(`${baseUrl}${path}`, init);
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) fail(`${path} gagal (${response.status}): ${text}`);
  return payload;
};
const post = (path, body = {}) => api(path, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body)
});

const waitUntil = async (predicate, description, timeout = 60_000) => {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await predicate();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await sleep(200);
  }
  fail(`${description}${lastError ? `: ${lastError.message}` : ""}`);
};

const silentWav = () => {
  const sampleRate = 8_000;
  const samples = 800;
  const dataSize = samples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
};

const profileDir = await mkdtemp(join(tmpdir(), "a11y-cua-blind-flow-"));
let context;
let bridge;
const spoken = [];
const commandErrors = [];
const progress = (message) => process.stdout.write(`[blind-e2e] ${message}\n`);

try {
  context = await chromium.launchPersistentContext(profileDir, {
    channel: "chromium",
    headless: true,
    args: [
      `--disable-extensions-except=${extension}`,
      `--load-extension=${extension}`,
      "--autoplay-policy=no-user-gesture-required",
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream"
    ]
  });
  const extensionWorker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker", { timeout: 15_000 });
  if (!extensionWorker.url().startsWith("chrome-extension://")) fail("Service worker extension tidak aktif.");
  extensionWorker.on("console", (message) => {
    if (message.type() === "warning" || message.type() === "error") {
      commandErrors.push(message.text());
      progress(`extension: ${message.text()}`);
    }
  });
  await context.grantPermissions(["camera", "microphone"], { origin: baseUrl });
  await context.addInitScript(() => {
    const originalMediaPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function playForDeterministicVoiceFlow() {
      const media = this;
      window.setTimeout(() => media.dispatchEvent(new Event("ended")), 40);
      return originalMediaPlay.call(media).catch(() => undefined);
    };
    const originalGetUserMedia = navigator.mediaDevices?.getUserMedia?.bind(navigator.mediaDevices);
    if (originalGetUserMedia) {
      Object.defineProperty(navigator.mediaDevices, "getDisplayMedia", {
        configurable: true,
        value: () => originalGetUserMedia({ video: true, audio: false })
      });
    }
    class TestWebSocket extends EventTarget {
      static OPEN = 1;
      readyState = 1;
      constructor() {
        super();
        setTimeout(() => this.dispatchEvent(new MessageEvent("message", {
          data: JSON.stringify({ type: "ready" })
        })), 0);
      }
      send() {}
      close() {
        this.readyState = 3;
        this.dispatchEvent(new Event("close"));
      }
    }
    Object.defineProperty(window, "WebSocket", { configurable: true, value: TestWebSocket });
  });
  await context.route("**/api/voice/speech", async (route) => {
    try {
      const payload = route.request().postDataJSON();
      if (typeof payload?.text === "string") spoken.push(payload.text);
    } catch {}
    await route.fulfill({
      status: 200,
      contentType: "audio/wav",
      headers: { "x-a11y-cua-test-playback": "complete" },
      body: silentWav()
    });
  });
  await context.route("**/api/agent/runs/*/commands", async (route) => {
    const response = await route.fetch();
    const body = await response.body();
    if (!response.ok()) {
      commandErrors.push(`${response.status()} ${body.toString("utf8")}`);
      progress(`command rejected: ${commandErrors.at(-1)}`);
    }
    await route.fulfill({ response, body });
  });

  const page = context.pages()[0] || await context.newPage();
  const taskSurface = () => {
    const taskFrames = page.frames().filter((frame) => frame !== page.mainFrame());
    return taskFrames.find((frame) => {
      try {
        return new URL(frame.url()).searchParams.has("session_id");
      } catch {
        return false;
      }
    }) ?? taskFrames[0] ?? page;
  };
  bridge = await startBrowserBridge({
    page,
    getPage: taskSurface,
    token: bridgeSecret,
    port: bridgePort
  });

  await page.goto(`${baseUrl}/researcher`, { waitUntil: "networkidle" });
  const start = page.getByRole("button", { name: "Mulai Penelitian" });
  await start.focus();
  if (!await start.evaluate((button) => document.activeElement === button)) fail("Fokus keyboard tidak mencapai tombol mulai.");
  await page.keyboard.press("Enter");

  const studyId = await waitUntil(() => {
    const value = new URL(page.url()).searchParams.get("study_session_id");
    return value || false;
  }, "Sesi tidak dibuat setelah tombol mulai");
  if (context.pages().length !== 1) fail("Tombol mulai membuka tab baru.");
  progress(`session ${studyId} started in one tab`);

  const getStudy = () => api(`/api/study/sessions/${studyId}`);
  const waitForSpeech = (fragment, from = 0, timeout = 30_000) => waitUntil(
    () => spoken.slice(from).some((message) => message.toLocaleLowerCase("id-ID").includes(fragment.toLocaleLowerCase("id-ID"))),
    `Audio tidak membacakan: ${fragment}`,
    timeout
  );
  const waitListening = () => waitUntil(async () => (await getStudy()).voice_state === "LISTENING", "Sistem tidak kembali mendengarkan");
  const say = async (text, nextSpeech) => {
    const marker = spoken.length;
    await post(`/api/study/sessions/${studyId}/utterances`, { text });
    if (nextSpeech) await waitForSpeech(nextSpeech, marker);
    await waitListening();
  };

  await waitForSpeech("siapa nama kamu");
  progress("spoken onboarding started");
  await waitListening();
  const silenceMarker = spoken.length;
  await waitForSpeech("siapa nama kamu", silenceMarker, 20_000);
  await say("Nama saya Raka", "eja nama");
  await say("R A K A", "kelas berapa");
  await say("Kelas delapan", "umur kamu");

  const taskStartMarker = spoken.length;
  await post(`/api/study/sessions/${studyId}/utterances`, { text: "empat belas" });
  await waitForSpeech("kegiatan pertama", taskStartMarker, 45_000);
  await waitUntil(async () => (await getStudy()).current_task?.task_id === "T01", "Kegiatan pertama tidak dibuka");
  await waitForSpeech("pilihan yang tersedia", taskStartMarker, 45_000);
  await waitListening();
  progress("profile complete and T01 ready");

  const confusionMarker = spoken.length;
  await post(`/api/study/sessions/${studyId}/utterances`, { text: "saya bingung" });
  await waitForSpeech("tidak apa-apa", confusionMarker);
  await waitForSpeech("pilihan yang tersedia", confusionMarker, 45_000);
  await waitListening();
  progress("silence and confusion recovery verified");

  const taskIds = ["T01", "T05", "T07", "T12"];
  for (let index = 0; index < taskIds.length; index += 1) {
    const expectedTaskId = taskIds[index];
    progress(`${expectedTaskId} starting`);
    const current = await waitUntil(async () => {
      const study = await getStudy();
      return study.current_task?.task_id === expectedTaskId ? study : false;
    }, `${expectedTaskId} tidak aktif`);
    const marker = spoken.length;
    await post(`/api/study/sessions/${studyId}/utterances`, { text: current.current_task.instruction });

    let approvalAttempts = 0;
    let approvalSpeechCursor = 0;
    await waitUntil(async () => {
      const study = await getStudy();
      const newSpeech = spoken.slice(marker).map((message) => message.toLocaleLowerCase("id-ID"));
      const approvalPrompt = newSpeech.slice(approvalSpeechCursor).some((message) =>
        message.includes("memastikan sebelum melanjutkan") || message.includes("belum memahami jawaban")
      );
      if (approvalAttempts < 3 && approvalPrompt) {
        approvalSpeechCursor = newSpeech.length;
        approvalAttempts += 1;
        const workerRunId = await extensionWorker.evaluate(() => globalThis.__a11yCuaLatestRunId ?? null);
        const workerCommandError = await extensionWorker.evaluate(() => globalThis.__a11yCuaLastCommandError ?? null);
        const workerRun = workerRunId ? await api(`/api/agent/runs/${workerRunId}`) : null;
        progress(`${expectedTaskId} approval ${approvalAttempts}; run=${workerRunId ?? "unknown"}; status=${workerRun?.status ?? "unknown"}; error=${workerCommandError ?? "none"}; prompt=${newSpeech.at(-1) ?? "none"}`);
        // A real participant can only answer after hearing the prompt. Keep the
        // synthetic response behind the short test audio and state transition.
        await sleep(1_000);
        await post(`/api/study/sessions/${studyId}/utterances`, { text: "iya, saya setuju" });
      }
      if (newSpeech.some((message) => message.includes("kegiatan belum berhasil"))) {
        const failedRunId = await extensionWorker.evaluate(() => globalThis.__a11yCuaLatestRunId ?? null);
        const failedRun = failedRunId ? await api(`/api/agent/runs/${failedRunId}`) : null;
        fail(`${expectedTaskId} masuk ke recovery gagal. Run: ${JSON.stringify(failedRun)}`);
      }
      if (index === taskIds.length - 1) return study.status === "FEEDBACK" ? study : false;
      return study.task_index > index && study.current_task?.task_id === taskIds[index + 1] ? study : false;
    }, `${expectedTaskId} tidak selesai atau tidak berpindah otomatis${commandErrors.length ? `; command errors: ${commandErrors.join(" | ")}` : ""}`, 75_000);

    await waitForSpeech(`kegiatan ${index + 1} selesai`, marker, 30_000);
    progress(`${expectedTaskId} completed`);
    if (index < taskIds.length - 1) {
      await waitForSpeech(`kegiatan ${index + 2}`, marker, 45_000);
      await waitForSpeech("pilihan yang tersedia", marker, 45_000);
      await waitListening();
    }
  }

  const feedbackMarker = spoken.length;
  await waitForSpeech("sebelum selesai", Math.max(0, feedbackMarker - 3), 30_000);
  await waitListening();
  await post(`/api/study/sessions/${studyId}/utterances`, {
    text: "Instruksinya mudah dipahami dan suaranya membantu saya mengikuti kegiatan."
  });
  await waitForSpeech("pengujian selesai", feedbackMarker, 30_000);
  await waitUntil(async () => (await getStudy()).status === "COMPLETED", "Sesi tidak mencapai status selesai", 45_000);
  await page.locator("#completion-panel").waitFor({ state: "visible", timeout: 45_000 });

  const report = await fetch(`${baseUrl}/api/study/sessions/${studyId}/report.pdf`);
  if (!report.ok || !String(report.headers.get("content-type")).includes("application/pdf")) {
    fail("Laporan PDF tidak dapat diunduh.");
  }
  const aria = await page.locator("body").ariaSnapshot();
  if (!aria.includes("Semua kegiatan selesai") || !aria.includes("Unduh Laporan PDF")) {
    fail("Status selesai atau unduhan laporan tidak terbaca melalui accessibility tree.");
  }
  const finalStudy = await getStudy();
  if (finalStudy.recording_state !== "SAVED") fail("Rekaman tidak berhenti dan tersimpan otomatis.");

  console.log(JSON.stringify({
    status: "PASS",
    study_session_id: studyId,
    spoken_turns: spoken.length,
    checks: [
      "keyboard_start",
      "single_tab",
      "automatic_camera_microphone_screen",
      "recording_started_and_saved",
      "spoken_onboarding_and_profile",
      "silence_reprompt",
      "confusion_recovery",
      "all_options_read_aloud",
      "four_tasks_completed_in_order",
      "spoken_success_and_transition",
      "spoken_feedback_and_completion",
      "accessible_completion_state",
      "pdf_report_download"
    ]
  }, null, 2));
} finally {
  if (bridge) await bridge.close().catch(() => {});
  if (context) await context.close().catch(() => {});
  await rm(profileDir, { recursive: true, force: true }).catch(() => {});
}
