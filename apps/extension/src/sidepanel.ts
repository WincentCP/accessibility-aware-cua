import "./styles.css";
import type { AccessibleTaskMap, ActiveBenchmarkTask, LiveRunResponse, TaskMapItem } from "./contracts";
import { sanitizeTaskMap } from "./task-map";
import { postToWhisperAdapter, WhisperPushToTalkAdapter } from "./voice";

type Command = "APPROVE" | "EDIT" | "REJECT" | "PAUSE" | "TAKE_OVER" | "RESUME" | "CANCEL";
type AgentActivity = {
  key: string;
  phase: string;
  detail: string;
  progress: string;
  spoken: string;
};

const byId = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing accessible panel element: ${id}`);
  return element as T;
};

const goal = byId<HTMLTextAreaElement>("goal");
const voiceButton = byId<HTMLButtonElement>("voice");
const cancelVoice = byId<HTMLButtonElement>("cancel-voice");
const transcriptReview = byId<HTMLElement>("transcript-review");
const transcript = byId<HTMLTextAreaElement>("transcript");
const confirmTranscript = byId<HTMLButtonElement>("confirm-transcript");
const editTranscript = byId<HTMLButtonElement>("edit-transcript");
const submitGoal = byId<HTMLButtonElement>("submit-goal");
const repeatGuide = byId<HTMLButtonElement>("repeat-guide");
const toggleGuide = byId<HTMLButtonElement>("toggle-guide");
const status = byId<HTMLElement>("status");
const voiceState = byId<HTMLElement>("voice-state");
const activityPhase = byId<HTMLElement>("activity-phase");
const activityDetail = byId<HTMLElement>("activity-detail");
const activityProgress = byId<HTMLElement>("activity-progress");
const approvalAlert = byId<HTMLElement>("approval-alert");
let activeRunId: string | null = null;
let pollTimer: number | null = null;
let activeBenchmarkTask: ActiveBenchmarkTask | null = null;
let voiceGuideEnabled = true;
let activeGuideAudio: HTMLAudioElement | null = null;
let activeGuideAudioUrl: string | null = null;
let speechRequestSequence = 0;
let lastSpokenActivityKey: string | null = null;

const announce = (message: string): void => { status.textContent = message; };

const stopSpeech = (): void => {
  speechRequestSequence += 1;
  if (activeGuideAudio) {
    activeGuideAudio.pause();
    activeGuideAudio = null;
  }
  if (activeGuideAudioUrl) {
    URL.revokeObjectURL(activeGuideAudioUrl);
    activeGuideAudioUrl = null;
  }
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
};

const findIndonesianBrowserVoice = (): SpeechSynthesisVoice | null => {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  return voices.find((item) => item.lang.toLowerCase() === "id-id")
    ?? voices.find((item) => item.lang.toLowerCase().startsWith("id"))
    ?? null;
};

const waitForIndonesianBrowserVoice = async (): Promise<SpeechSynthesisVoice | null> => {
  const existing = findIndonesianBrowserVoice();
  if (existing || !("speechSynthesis" in window)) return existing;
  return await new Promise((resolve) => {
    let settled = false;
    const finish = (): void => {
      if (settled) return;
      settled = true;
      window.speechSynthesis.removeEventListener("voiceschanged", onVoicesChanged);
      resolve(findIndonesianBrowserVoice());
    };
    const onVoicesChanged = (): void => finish();
    window.speechSynthesis.addEventListener("voiceschanged", onVoicesChanged, { once: true });
    window.setTimeout(finish, 700);
  });
};

const speakWithBrowserIndonesian = async (message: string): Promise<boolean> => {
  if (!voiceGuideEnabled || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return false;
  const indonesianVoice = await waitForIndonesianBrowserVoice();
  if (!indonesianVoice) return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = "id-ID";
  utterance.voice = indonesianVoice;
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
  return true;
};

const speak = async (message: string): Promise<void> => {
  if (!voiceGuideEnabled) return;
  stopSpeech();
  const requestSequence = speechRequestSequence;
  try {
    const response = await fetch("http://127.0.0.1:8000/api/voice/speech", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: message })
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Speech API ${response.status}${detail ? `: ${detail}` : ""}`);
    }
    const audioBlob = await response.blob();
    if (!voiceGuideEnabled || requestSequence !== speechRequestSequence) return;
    activeGuideAudioUrl = URL.createObjectURL(audioBlob);
    activeGuideAudio = new Audio(activeGuideAudioUrl);
    activeGuideAudio.addEventListener("ended", () => {
      if (activeGuideAudioUrl) URL.revokeObjectURL(activeGuideAudioUrl);
      activeGuideAudio = null;
      activeGuideAudioUrl = null;
    }, { once: true });
    await activeGuideAudio.play();
    voiceState.textContent = "Panduan suara Indonesia aktif melalui Gemini.";
  } catch (error) {
    if (!voiceGuideEnabled || requestSequence !== speechRequestSequence) return;
    const usedIndonesianFallback = await speakWithBrowserIndonesian(message);
    if (usedIndonesianFallback) {
      voiceState.textContent = "Gemini TTS sementara tidak tersedia. Menggunakan suara Bahasa Indonesia dari perangkat.";
    } else {
      voiceState.textContent = "Panduan suara Indonesia sementara tidak tersedia. Fallback suara Inggris sengaja tidak digunakan.";
      console.warn("Indonesian voice unavailable", error);
    }
  }
};

const renderItems = (targetId: string, items: TaskMapItem[], empty: string): void => {
  const target = byId<HTMLElement>(targetId);
  target.replaceChildren();
  const visibleItems = items.length ? items : [{ label: empty } as TaskMapItem];
  for (const source of visibleItems) {
    const item = document.createElement("li");
    item.textContent = source.label;
    if (source.evidence?.length) item.title = `Bukti: ${source.evidence.join("; ")}`;
    target.append(item);
  }
};

const renderTaskMap = (source: AccessibleTaskMap): void => {
  const { map } = sanitizeTaskMap(source);
  byId("active-goal").textContent = map.goal;
  byId("progress").textContent = map.progress_label;
  renderItems("verified-list", map.verified_completed, "Belum ada.");
  renderItems("relevant-list", map.relevant_options, "Belum ada.");
  renderItems("uncertain-list", map.uncertain_items, "Belum ada.");
  byId("next-action").textContent = map.next_action
    ? `${map.next_action.label}. Status: direncanakan, belum selesai.` : "Belum ada.";
  byId("final-summary").textContent = map.final_summary ?? "Tugas belum selesai.";
  approvalAlert.hidden = !map.control_state.approval_pending;
  approvalAlert.textContent = map.control_state.approval_pending
    ? activeRunId
      ? "Tindakan sensitif dihentikan dengan aman. Live MVP belum melanjutkan approval; pilih Tolak atau Batalkan."
      : "Persetujuan diperlukan. Pilih Setujui, Ubah, atau Tolak."
    : "";
};

const activityForRun = (run: LiveRunResponse): AgentActivity => {
  const map = run.task_map;
  const progress = map?.progress_label ?? "0 langkah terverifikasi selesai.";
  const announcement = run.announcement.toLowerCase();

  if (run.status === "QUEUED") {
    return { key: "queued", phase: "Bersiap", detail: "Tugas diterima. Agen sedang menyiapkan sesi browser.", progress, spoken: "Tugas diterima. Saya sedang bersiap." };
  }
  if (run.status === "WAITING_USER") {
    return { key: `waiting:${run.announcement}`, phase: "Menunggu Anda", detail: run.announcement, progress, spoken: `Saya berhenti sementara dan membutuhkan bantuan Anda. ${run.announcement}` };
  }
  if (run.status === "COMPLETED") {
    return { key: "completed", phase: "Selesai", detail: "Semua tindakan yang diklaim selesai sudah melewati verifikasi pasca-aksi.", progress, spoken: "Tugas selesai. Hasil tindakan sudah diverifikasi." };
  }
  if (run.status === "FAILED") {
    return { key: `failed:${run.error ?? "unknown"}`, phase: "Belum berhasil", detail: run.error ? `${run.announcement} ${run.error}` : run.announcement, progress, spoken: "Tugas belum berhasil. Agen berhenti dengan aman." };
  }
  if (run.status === "CANCELLED") {
    return { key: "cancelled", phase: "Dibatalkan", detail: "Tugas dihentikan oleh pengguna.", progress, spoken: "Tugas dibatalkan." };
  }

  if (announcement.includes("diverifikasi") || announcement.includes("verifikasi")) {
    return { key: `verify:${map?.next_action?.item_id ?? progress}`, phase: "Memverifikasi hasil", detail: map?.next_action ? `Memeriksa hasil dari tindakan: ${map.next_action.label}.` : "Memeriksa apakah tindakan terakhir benar-benar berhasil.", progress, spoken: "Saya sedang memeriksa apakah tindakan terakhir berhasil." };
  }
  if (announcement.includes("recovery") || announcement.includes("pemulihan")) {
    return { key: `recover:${progress}`, phase: "Memulihkan langkah", detail: "Hasil belum sesuai. Agen menjalankan pemulihan terbatas lalu akan membaca halaman lagi.", progress, spoken: "Hasil belum sesuai. Saya sedang mencoba langkah pemulihan." };
  }
  if (map?.next_action) {
    return { key: `action:${map.next_action.item_id}`, phase: "Menyiapkan tindakan", detail: `Tindakan berikutnya: ${map.next_action.label}. Tindakan ini masih direncanakan dan belum dianggap selesai.`, progress, spoken: `Saya sedang menyiapkan tindakan berikutnya: ${map.next_action.label}.` };
  }
  if (map?.relevant_options?.length) {
    return { key: `plan:${map.observation_version}:${map.relevant_options.length}`, phase: "Menganalisis pilihan", detail: `Ditemukan ${map.relevant_options.length} kontrol yang relevan. AI sedang menentukan tindakan yang paling sesuai dengan tujuan dan batasan Anda.`, progress, spoken: "Saya sudah membaca halaman. Sekarang saya sedang menganalisis pilihan yang tersedia." };
  }
  if (announcement.includes("mengamati") || announcement.includes("diamati")) {
    return { key: `observe:${map?.observation_version ?? 0}`, phase: "Membaca halaman", detail: "Agen sedang membaca accessibility tree untuk memahami kontrol dan isi halaman tanpa bergantung pada tampilan visual.", progress, spoken: "Saya sedang membaca struktur halaman." };
  }
  return { key: `running:${run.announcement}`, phase: "Memproses tujuan", detail: run.announcement, progress, spoken: "Saya sedang memproses tujuan Anda." };
};

const renderActivity = (run: LiveRunResponse): void => {
  const activity = activityForRun(run);
  activityPhase.textContent = activity.phase;
  activityDetail.textContent = activity.detail;
  activityProgress.textContent = activity.progress;
  if (activity.key !== lastSpokenActivityKey) {
    lastSpokenActivityKey = activity.key;
    void speak(activity.spoken);
  }
};

const voice = new WhisperPushToTalkAdapter({
  transcribe: postToWhisperAdapter,
  onUpdate: (update) => {
    announce(update.message);
    const listening = update.state === "LISTENING";
    voiceButton.setAttribute("aria-pressed", String(listening));
    voiceButton.textContent = listening ? "Berhenti dan proses suara" : "Mulai input suara";
    cancelVoice.disabled = !["LISTENING", "PROCESSING"].includes(update.state);
    if (update.state === "REVIEW" && update.transcript) {
      transcript.value = update.transcript;
      transcriptReview.hidden = false;
      transcript.focus();
    }
  }
});

voiceButton.addEventListener("click", () => {
  if (voice.state === "LISTENING") voice.stop(); else void voice.start();
});
cancelVoice.addEventListener("click", () => voice.cancel());
confirmTranscript.addEventListener("click", () => {
  goal.value = transcript.value.trim();
  transcriptReview.hidden = true;
  announce("Transkrip dikonfirmasi. Periksa tujuan lalu jalankan.");
  submitGoal.focus();
});
editTranscript.addEventListener("click", () => transcript.focus());

const loadActiveTask = async (): Promise<void> => {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) {
    submitGoal.disabled = false;
    return;
  }
  announce("Mengambil tujuan task yang sedang dibuka.");
  try {
    const result = await chrome.runtime.sendMessage({ type: "GET_ACTIVE_TASK" });
    if (!result?.success || !result.task) throw new Error(result?.error ?? "Task tidak ditemukan.");
    activeBenchmarkTask = result.task as ActiveBenchmarkTask;
    goal.value = activeBenchmarkTask.goal;
    byId("active-goal").textContent = activeBenchmarkTask.goal;
    submitGoal.disabled = false;
    repeatGuide.disabled = false;
    const instruction = `Halo! Saya panduan suara AI. Tugas ${activeBenchmarkTask.task_id} sudah siap. ${activeBenchmarkTask.goal} Tekan tombol Mulai tugas untuk memulai.`;
    announce(`Tugas ${activeBenchmarkTask.task_id} dimuat otomatis. Tekan Mulai tugas.`);
    void speak(instruction);
    submitGoal.focus();
  } catch (error) {
    activeBenchmarkTask = null;
    submitGoal.disabled = false;
    announce(`Tujuan otomatis belum tersedia. Gunakan input teks atau suara. ${error instanceof Error ? error.message : String(error)}`);
    goal.focus();
  }
};

const applyLiveRun = (run: LiveRunResponse): void => {
  activeRunId = run.run_id;
  announce(run.error ? `${run.announcement} ${run.error}` : run.announcement);
  if (run.task_map) renderTaskMap(run.task_map);
  renderActivity(run);
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(run.status);
  if (terminal && pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
    submitGoal.disabled = false;
  }
};

const stopMissingRunPolling = (message: string): void => {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = null;
  activeRunId = null;
  submitGoal.disabled = false;
  activityPhase.textContent = "Run tidak tersedia";
  activityDetail.textContent = message;
  announce(message);
};

const pollLiveRun = (): void => {
  if (!activeRunId || typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  void chrome.runtime.sendMessage({ type: "GET_LIVE_RUN", runId: activeRunId }).then((result) => {
    if (result?.success && result.run) {
      applyLiveRun(result.run as LiveRunResponse);
      return;
    }
    if (result && result.success === false) {
      stopMissingRunPolling("Run lama tidak ditemukan, biasanya karena backend baru direstart. Tekan Mulai tugas untuk membuat run baru.");
    }
  }).catch(() => {
    stopMissingRunPolling("Status agen tidak dapat dibaca. Pastikan backend masih berjalan, lalu mulai tugas kembali.");
  });
};

submitGoal.addEventListener("click", async () => {
  const value = goal.value.trim();
  if (!value) {
    announce("Tujuan masih kosong. Ketik tujuan atau gunakan input suara.");
    goal.focus();
    return;
  }
  byId("active-goal").textContent = value;
  activityPhase.textContent = "Mengirim tujuan";
  activityDetail.textContent = "Tujuan sedang dikirim ke live agent.";
  activityProgress.textContent = "0 langkah terverifikasi selesai.";
  lastSpokenActivityKey = null;
  announce("Tujuan diterima. Agen akan menampilkan tindakan sebagai direncanakan sebelum menjalankannya.");
  window.dispatchEvent(new CustomEvent("a11y-cua:goal", { detail: { goal: value } }));
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  submitGoal.disabled = true;
  try {
    const unchangedBenchmarkGoal = activeBenchmarkTask?.goal === value;
    const result = await chrome.runtime.sendMessage({
      type: "START_LIVE_AGENT",
      ...(unchangedBenchmarkGoal ? {} : { goal: value })
    });
    if (!result?.success || !result.run) throw new Error(result?.error ?? "Live agent tidak dapat dimulai.");
    applyLiveRun(result.run as LiveRunResponse);
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = window.setInterval(pollLiveRun, 750);
  } catch (error) {
    submitGoal.disabled = false;
    announce(`Live agent belum berjalan. ${error instanceof Error ? error.message : String(error)}`);
  }
});

repeatGuide.addEventListener("click", () => {
  if (!activeBenchmarkTask) {
    announce("Instruksi task belum tersedia.");
    return;
  }
  void speak(`Tugas ${activeBenchmarkTask.task_id}. ${activeBenchmarkTask.goal} Tekan tombol Mulai tugas untuk memulai.`);
});

toggleGuide.addEventListener("click", () => {
  voiceGuideEnabled = !voiceGuideEnabled;
  toggleGuide.setAttribute("aria-pressed", String(voiceGuideEnabled));
  toggleGuide.textContent = `Panduan suara: ${voiceGuideEnabled ? "aktif" : "mati"}`;
  if (voiceGuideEnabled) {
    void speak("Panduan suara Bahasa Indonesia aktif.");
  } else {
    stopSpeech();
    voiceState.textContent = "Panduan suara dimatikan.";
    announce("Panduan suara dimatikan. Semua informasi tetap tersedia sebagai teks.");
  }
});

const runCommand = (command: Command): void => {
  const labels: Record<Command, string> = {
    APPROVE: "Persetujuan dikirim.", EDIT: "Ubah dipilih. Fokus kembali ke tujuan.",
    REJECT: "Tindakan ditolak.", PAUSE: "Agen dijeda.",
    TAKE_OVER: "Mode ambil alih aktif. Fokus dikembalikan ke halaman web.",
    RESUME: "Agen dilanjutkan dari observasi baru.", CANCEL: "Tugas dibatalkan."
  };
  if (activeRunId && (command === "APPROVE" || command === "EDIT")) {
    announce(command === "APPROVE"
      ? "Persetujuan live belum diaktifkan. Agen tetap berhenti dan tindakan tidak dijalankan."
      : "Batalkan run ini terlebih dahulu, ubah tujuan, lalu jalankan kembali.");
    if (command === "EDIT") goal.focus();
    return;
  }
  approvalAlert.hidden = true;
  announce(labels[command]);
  window.dispatchEvent(new CustomEvent("a11y-cua:command", { detail: { command } }));
  if (activeRunId && typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
    const supported = command === "PAUSE" || command === "TAKE_OVER" || command === "RESUME" || command === "CANCEL" || command === "REJECT";
    if (supported) void chrome.runtime.sendMessage({ type: "LIVE_COMMAND", runId: activeRunId, command });
  }
  if (command === "EDIT") goal.focus();
};

document.querySelectorAll<HTMLButtonElement>("[data-command]").forEach((button) => {
  button.addEventListener("click", () => runCommand(button.dataset.command as Command));
});

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  const shortcut: Command | undefined = event.key === "Escape" ? "REJECT"
    : event.altKey ? ({ a: "APPROVE", e: "EDIT", p: "PAUSE", t: "TAKE_OVER", r: "RESUME", c: "CANCEL" } as Record<string, Command>)[key]
      : undefined;
  if (!shortcut) return;
  event.preventDefault();
  runCommand(shortcut);
});

window.addEventListener("a11y-cua:task-map", (event) => {
  renderTaskMap((event as CustomEvent<AccessibleTaskMap>).detail);
});

// Deterministic QA hook; production transcripts still come only from the voice adapter.
window.addEventListener("a11y-cua:voice-transcript", (event) => {
  transcript.value = (event as CustomEvent<{ transcript: string }>).detail.transcript;
  transcriptReview.hidden = false;
  announce("Transkrip siap. Periksa lalu konfirmasi atau ubah.");
  transcript.focus();
});

void loadActiveTask();
