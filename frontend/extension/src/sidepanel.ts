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
const assistantPrompt = byId<HTMLElement>("assistant-prompt");
const heardText = byId<HTMLElement>("heard-text");
const voiceState = byId<HTMLElement>("voice-state");
const activityPhase = byId<HTMLElement>("activity-phase");
const activityDetail = byId<HTMLElement>("activity-detail");
const activityProgress = byId<HTMLElement>("activity-progress");
const approvalAlert = byId<HTMLElement>("approval-alert");
const controlHelp = byId<HTMLElement>("control-help");
const root = document.documentElement;
const commandButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-command]"));
let activeRunId: string | null = null;
let pollTimer: number | null = null;
let activeBenchmarkTask: ActiveBenchmarkTask | null = null;
let voiceGuideEnabled = true;
let activeGuideAudio: HTMLAudioElement | null = null;
let activeGuideAudioUrl: string | null = null;
let speechRequestSequence = 0;
let lastSpokenActivityKey: string | null = null;
let commandContextReady = false;
let handsFreeRecognition: HandsFreeRecognition | null = null;
let utterancePollTimer: number | null = null;
let lastUtteranceId = 0;
let lastGuideMessage = "";
let terminalHandled = false;
let lastWaitingAnnouncement = "";
let feedbackMode = false;
type DialogueContext = "AWAITING_REQUEST" | "AGENT_WORKING" | "AWAITING_APPROVAL" | "FEEDBACK" | "COMPLETE";
let dialogueContext: DialogueContext = "AWAITING_REQUEST";
let loadingActiveTask = false;
let loadedTaskKey: string | null = null;
type OnboardingStage = "IDLE" | "ASK_NAME" | "ASK_SPELLING" | "ASK_CLASS" | "ASK_AGE";
let onboardingStage: OnboardingStage = "IDLE";
let activeStudySessionId: string | null = null;
let participantName = "";
let profileDraft = { name: "", nameSpelling: "", participantClass: "" };
let silenceTimer: number | null = null;
let silencePromptCount = 0;
let workAcknowledgementTimer: number | null = null;

interface HandsFreeRecognitionResultEvent {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface HandsFreeRecognitionErrorEvent { error: string }

interface HandsFreeRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: HandsFreeRecognitionResultEvent) => void) | null;
  onerror: ((event: HandsFreeRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type HandsFreeRecognitionConstructor = new () => HandsFreeRecognition;

const announce = (message: string): void => { status.textContent = message; };
const promptParticipant = (message: string): void => { assistantPrompt.textContent = message; };
const setAgentState = (state: string): void => { root.dataset.agentState = state.toLowerCase(); };
const studyApi = async (path: string, body?: Record<string, unknown>): Promise<Record<string, unknown>> => {
  const response = await fetch(`http://127.0.0.1:8000${path}`, {
    ...(body ? {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    } : {})
  });
  const payload = await response.json() as Record<string, unknown>;
  if (!response.ok) throw new Error(String(payload.detail ?? `API ${response.status}`));
  return payload;
};

const setStudyVoiceState = async (stateValue: string): Promise<void> => {
  const studyId = activeBenchmarkTask?.study_session_id ?? activeStudySessionId;
  if (!studyId) return;
  await studyApi(`/api/study/sessions/${studyId}/voice-state`, { state: stateValue });
};
const setCommandContextReady = (ready: boolean): void => {
  commandContextReady = ready;
  commandButtons.forEach((button) => { button.disabled = !ready; });
  controlHelp.textContent = ready
    ? "Jeda, koreksi, atau ambil alih kapan saja. Pintasan bekerja saat panel aktif."
    : "Kontrol aktif setelah tujuan dikonfirmasi atau tugas dimulai.";
};

const stopSpeech = (): void => {
  if (silenceTimer !== null) window.clearTimeout(silenceTimer);
  silenceTimer = null;
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
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = "id-ID";
  if (indonesianVoice) utterance.voice = indonesianVoice;
  utterance.rate = 0.95;
  return await new Promise((resolve) => {
    let settled = false;
    const finish = (played: boolean): void => {
      if (settled) return;
      settled = true;
      resolve(played);
    };
    utterance.addEventListener("end", () => finish(true), { once: true });
    utterance.addEventListener("error", () => finish(false), { once: true });
    window.speechSynthesis.speak(utterance);
    window.setTimeout(() => finish(false), Math.max(4_000, message.length * 120));
  });
};

const speak = async (message: string): Promise<void> => {
  if (!voiceGuideEnabled) return;
  stopSpeech();
  lastGuideMessage = message;
  await setStudyVoiceState("SPEAKING").catch(() => undefined);
  setAgentState("speaking");
  voiceState.textContent = "AI sedang berbicara. Tunggu sampai selesai.";
  const requestSequence = speechRequestSequence;
  const studySessionId = activeBenchmarkTask?.study_session_id ?? activeStudySessionId;
  if (studySessionId && typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
    try {
      const result = await chrome.runtime.sendMessage({
        type: "PLAY_STUDY_SPEECH",
        studySessionId,
        text: message
      }) as { success?: boolean; provider?: string; error?: string };
      if (!voiceGuideEnabled || requestSequence !== speechRequestSequence) return;
      if (result?.success) {
        voiceState.textContent = result.provider?.startsWith("browser")
          ? "Menggunakan suara Bahasa Indonesia dari perangkat."
          : "Panduan suara Indonesia aktif melalui Gemini.";
        return;
      }
      console.warn("Study speech unavailable", result?.error ?? "unknown error");
      const usedDeviceFallback = await speakWithBrowserIndonesian(message);
      if (usedDeviceFallback) {
        voiceState.textContent = "Gemini TTS sementara tidak tersedia. Menggunakan suara perangkat.";
        return;
      }
      throw new Error(result?.error ?? "Panduan suara tidak dapat diputar di tab penelitian.");
    } catch (error) {
      console.warn("Study tab playback unavailable", error);
    }
  }
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
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(
        () => reject(new Error("Pemutaran audio Gemini melewati batas waktu.")),
        Math.max(8_000, message.length * 140)
      );
      const finish = (error?: Error): void => {
        window.clearTimeout(timeout);
        if (error) reject(error); else resolve();
      };
      activeGuideAudio?.addEventListener("ended", () => finish(), { once: true });
      activeGuideAudio?.addEventListener("error", () => finish(new Error("Audio Gemini gagal diputar.")), { once: true });
      void activeGuideAudio?.play().catch(reject);
    });
    if (activeGuideAudioUrl) URL.revokeObjectURL(activeGuideAudioUrl);
    activeGuideAudio = null;
    activeGuideAudioUrl = null;
    voiceState.textContent = "Panduan suara Indonesia aktif melalui Gemini.";
  } catch (error) {
    if (!voiceGuideEnabled || requestSequence !== speechRequestSequence) return;
    const usedIndonesianFallback = await speakWithBrowserIndonesian(message);
    if (usedIndonesianFallback) {
      voiceState.textContent = "Gemini TTS sementara tidak tersedia. Menggunakan suara Bahasa Indonesia dari perangkat.";
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(900, message.length * 55)));
    } else {
      voiceState.textContent = "Panduan suara belum tersedia.";
      console.warn("Indonesian voice unavailable", error);
      throw error;
    }
  }
};

const clearWorkAcknowledgement = (): void => {
  if (workAcknowledgementTimer !== null) window.clearTimeout(workAcknowledgementTimer);
  workAcknowledgementTimer = null;
};

const scheduleWorkAcknowledgement = (delay = 9_000): void => {
  clearWorkAcknowledgement();
  if (!activeBenchmarkTask?.study_session_id) return;
  workAcknowledgementTimer = window.setTimeout(() => {
    workAcknowledgementTimer = null;
    if (dialogueContext !== "AGENT_WORKING") return;
    void speak("Saya masih bekerja. Tunggu sebentar ya.")
      .then(() => setStudyVoiceState("AGENT_WORKING"))
      .catch((error) => console.warn("Work acknowledgement unavailable", error))
      .finally(() => {
        if (dialogueContext === "AGENT_WORKING") scheduleWorkAcknowledgement(15_000);
      });
  }, delay);
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
  setCommandContextReady(true);
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
  root.dataset.agentPhase = activity.key.split(":")[0];
  activityPhase.textContent = activity.phase;
  activityDetail.textContent = activity.detail;
  activityProgress.textContent = activity.progress;
  if (activeBenchmarkTask?.study_session_id) return;
  if (activity.key !== lastSpokenActivityKey) {
    lastSpokenActivityKey = activity.key;
    void speak(activity.spoken);
  }
};

const startLiveGoal = async (value: string): Promise<void> => {
  const normalized = value.trim();
  if (!normalized) {
    promptParticipant("Saya belum mendengar permintaanmu. Silakan coba sekali lagi.");
    return;
  }
  goal.value = normalized;
  heardText.hidden = false;
  const heardValue = heardText.querySelector("span");
  if (heardValue) heardValue.textContent = normalized;
  byId("active-goal").textContent = normalized;
  setCommandContextReady(true);
  activityPhase.textContent = "Memahami permintaan";
  activityDetail.textContent = "Saya sedang menyiapkan bantuan. Tidak perlu menjawab dulu.";
  activityProgress.textContent = "Belum ada hasil yang diperiksa.";
  promptParticipant("Baik, saya akan mulai membantu. Tidak perlu menjawab dulu.");
  await setStudyVoiceState("AGENT_WORKING").catch(() => undefined);
  dialogueContext = "AGENT_WORKING";
  lastSpokenActivityKey = null;
  setAgentState("starting");
  announce("Permintaan diterima. Saya sedang menyiapkan bantuan.");
  window.dispatchEvent(new CustomEvent("a11y-cua:goal", { detail: { goal: normalized } }));
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  submitGoal.disabled = true;
  try {
    const runRequest = chrome.runtime.sendMessage({ type: "START_LIVE_AGENT", goal: normalized });
    await speak(`Oke${participantName ? `, ${participantName}` : ""}. Saya bantu sekarang ya. Kamu tidak perlu melakukan apa-apa dulu.`);
    await setStudyVoiceState("AGENT_WORKING").catch(() => undefined);
    scheduleWorkAcknowledgement();
    const result = await runRequest;
    if (!result?.success || !result.run) throw new Error(result?.error ?? "Asisten tidak dapat dimulai.");
    applyLiveRun(result.run as LiveRunResponse);
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = window.setInterval(pollLiveRun, 750);
  } catch (error) {
    clearWorkAcknowledgement();
    submitGoal.disabled = false;
    setAgentState("error");
    const participantMessage = "Bantuan belum dapat dimulai. Saya akan mendengarkan lagi.";
    promptParticipant(participantMessage);
    announce(participantMessage);
    dialogueContext = "AWAITING_REQUEST";
    await setStudyVoiceState("ERROR").catch(() => undefined);
    console.warn("Live goal failed", error);
    await speak("Maaf, bantuan belum dapat dimulai. Coba ucapkan kembali permintaanmu dengan singkat.").catch(() => undefined);
    await enterAutomaticListening().catch(() => undefined);
  }
};

const beginHandsFreeListening = (): void => {
  const speechWindow = window as typeof window & {
    SpeechRecognition?: HandsFreeRecognitionConstructor;
    webkitSpeechRecognition?: HandsFreeRecognitionConstructor;
  };
  const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
  if (!Recognition) {
    setAgentState("error");
    promptParticipant("Saya belum dapat mendengar otomatis di perangkat ini. Minta peneliti membantu.");
    announce("Input suara otomatis tidak tersedia. Kontrol cadangan tetap tersedia untuk peneliti.");
    return;
  }
  handsFreeRecognition?.stop();
  const recognition = new Recognition();
  handsFreeRecognition = recognition;
  recognition.lang = "id-ID";
  recognition.continuous = false;
  recognition.interimResults = false;
  let received = false;
  recognition.onstart = () => {
    setAgentState("listening");
    activityPhase.textContent = "Saya mendengarkan";
    activityDetail.textContent = "Ceritakan bantuan yang kamu inginkan dengan kata-katamu sendiri.";
    promptParticipant("Saya siap membantu. Ceritakan apa yang ingin kamu lakukan.");
    announce("Saya mendengarkan.");
  };
  recognition.onresult = (event) => {
    received = true;
    recognition.stop();
    const transcriptValue = event.results[0]?.[0]?.transcript ?? "";
    void startLiveGoal(transcriptValue);
  };
  recognition.onerror = (event) => {
    received = true;
    setAgentState("error");
    const denied = event.error === "not-allowed" || event.error === "service-not-allowed";
    promptParticipant(denied
      ? "Mikrofon belum diizinkan. Minta peneliti membantu."
      : "Saya belum mendengar dengan jelas. Minta peneliti membantu atau gunakan kontrol cadangan.");
  };
  recognition.onend = () => {
    handsFreeRecognition = null;
    if (!received) {
      setAgentState("waiting_user");
      promptParticipant("Saya belum mendengar jawaban. Silakan bicara lagi saat kamu siap.");
      window.setTimeout(beginHandsFreeListening, 800);
    }
  };
  try {
    recognition.start();
  } catch {
    promptParticipant("Input suara belum siap. Minta peneliti membantu.");
  }
};

const enterAutomaticListening = async (): Promise<void> => {
  const studyId = activeBenchmarkTask?.study_session_id ?? activeStudySessionId;
  if (!studyId) return;
  setAgentState("listening");
  promptParticipant("Sekarang giliran kamu. Silakan berbicara.");
  voiceState.textContent = "Silakan berbicara sekarang.";
  announce("Mikrofon aktif. Silakan berbicara.");
  await setStudyVoiceState("LISTENING");
  if (silenceTimer !== null) window.clearTimeout(silenceTimer);
  silenceTimer = window.setTimeout(() => {
    silenceTimer = null;
    void handleParticipantSilence();
  }, silencePromptCount === 0 ? 8_000 : 14_000);
};

const normalizeIntentText = (value: string): string =>
  value.toLocaleLowerCase("id-ID").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

const isAny = (value: string, phrases: string[]): boolean => {
  const normalizedValue = ` ${normalizeIntentText(value)} `;
  return phrases.some((phrase) => {
    const normalizedPhrase = normalizeIntentText(phrase);
    return normalizedPhrase.length > 0 && normalizedValue.includes(` ${normalizedPhrase} `);
  });
};

const readCurrentPage = async (): Promise<void> => {
  try {
    const result = await chrome.runtime.sendMessage({ type: "READ_CURRENT_PAGE" }) as {
      success?: boolean;
      page?: { headings?: string[]; controls?: string[] };
    };
    if (!result?.success) throw new Error("Isi halaman belum tersedia.");
    const controls = (result.page?.controls ?? []).filter(Boolean).slice(0, 8);
    const heading = result.page?.headings?.find(Boolean);
    if (!controls.length) {
      await speak("Maaf, pilihan di halaman ini belum terbaca. Kamu bisa menyebutkan kembali instruksi yang ingin dijalankan.");
    } else {
      await speak(`${heading ? `${heading}. ` : ""}Pilihan yang tersedia adalah: ${controls.join(". ")}. Sekarang, sebutkan pilihan atau tindakan yang sesuai dengan instruksi kegiatan tadi.`);
    }
  } catch {
    await speak("Saya belum dapat membacakan halaman. Coba ceritakan bantuan yang kamu inginkan.");
  }
  dialogueContext = "AWAITING_REQUEST";
  await enterAutomaticListening();
};

const repeatCurrentGuidance = async (): Promise<void> => {
  if (onboardingStage !== "IDLE") {
    const prompts: Record<Exclude<OnboardingStage, "IDLE">, string> = {
      ASK_NAME: "Siapa nama kamu?",
      ASK_SPELLING: `Tolong eja nama ${profileDraft.name || "kamu"}, huruf per huruf.`,
      ASK_CLASS: `${profileDraft.name || "Kamu"} sekarang kelas berapa?`,
      ASK_AGE: `Terakhir, umur ${profileDraft.name || "kamu"} berapa tahun?`
    };
    await speak(prompts[onboardingStage]);
    await enterAutomaticListening();
    return;
  }
  if (feedbackMode) {
    await speak(`${participantName ? `${participantName}, ` : ""}sebelum selesai, ceritakan singkat apa yang terasa mudah atau sulit, dan apa yang perlu diperbaiki.`);
    await enterAutomaticListening();
    return;
  }
  if (activeBenchmarkTask?.instruction) {
    await studyApi(`/api/study/sessions/${activeBenchmarkTask.study_session_id}/events`, {
      kind: "TASK_INSTRUCTION_REPEAT",
      detail: "AI mengulang instruksi setelah peserta tidak merespons."
    }).catch(() => undefined);
    await speak(`${participantName ? `${participantName}, ` : ""}tidak apa-apa, kita pelan-pelan ya. Saya bacakan lagi instruksinya. ${activeBenchmarkTask.instruction}`);
    await readCurrentPage();
    return;
  }
  await speak("Tidak apa-apa. Saya masih di sini dan siap mendengarkan.");
  await enterAutomaticListening();
};

const handleParticipantSilence = async (): Promise<void> => {
  silencePromptCount += 1;
  await repeatCurrentGuidance();
};

const parseAge = (spoken: string): number | null => {
  const numeric = spoken.match(/\b([5-9]|[12][0-9]|30)\b/u);
  if (numeric) return Number(numeric[1]);
  const words: Record<string, number> = {
    lima: 5, enam: 6, tujuh: 7, delapan: 8, sembilan: 9, sepuluh: 10,
    sebelas: 11, "dua belas": 12, "tiga belas": 13, "empat belas": 14,
    "lima belas": 15, "enam belas": 16, "tujuh belas": 17, "delapan belas": 18,
    "sembilan belas": 19, "dua puluh": 20, "dua puluh satu": 21,
    "dua puluh dua": 22, "dua puluh tiga": 23, "dua puluh empat": 24,
    "dua puluh lima": 25, "dua puluh enam": 26, "dua puluh tujuh": 27,
    "dua puluh delapan": 28, "dua puluh sembilan": 29, "tiga puluh": 30
  };
  const normalized = spoken.toLocaleLowerCase("id-ID");
  return Object.entries(words).find(([word]) => normalized.includes(word))?.[1] ?? null;
};

const handleOnboardingUtterance = async (spoken: string): Promise<boolean> => {
  if (onboardingStage === "IDLE" || !activeStudySessionId) return false;
  if (onboardingStage === "ASK_NAME") {
    profileDraft.name = spoken.replace(/^(?:nama saya|saya|namaku)\s+/iu, "").trim();
    participantName = profileDraft.name;
    onboardingStage = "ASK_SPELLING";
    await speak(`Senang kenalan denganmu, ${participantName}. Sekarang tolong eja nama ${participantName}, huruf per huruf.`);
    await enterAutomaticListening();
    return true;
  }
  if (onboardingStage === "ASK_SPELLING") {
    profileDraft.nameSpelling = spoken;
    onboardingStage = "ASK_CLASS";
    await speak(`Terima kasih, ${participantName}. Sekarang kamu kelas berapa?`);
    await enterAutomaticListening();
    return true;
  }
  if (onboardingStage === "ASK_CLASS") {
    profileDraft.participantClass = spoken;
    onboardingStage = "ASK_AGE";
    await speak(`Baik. Terakhir, umur kamu berapa tahun, ${participantName}?`);
    await enterAutomaticListening();
    return true;
  }
  const age = parseAge(spoken);
  if (age === null) {
    await speak(`Maaf ${participantName}, saya belum menangkap umurnya. Sebutkan angka umur kamu sekali lagi ya.`);
    await enterAutomaticListening();
    return true;
  }
  await studyApi(`/api/study/sessions/${activeStudySessionId}/participant-profile`, {
    name: profileDraft.name,
    name_spelling: profileDraft.nameSpelling,
    participant_class: profileDraft.participantClass,
    age
  });
  onboardingStage = "IDLE";
  await speak(`Terima kasih, ${participantName}. Kita mulai kegiatan pertama sekarang. Saya akan membacakan instruksi dan semua pilihan yang tersedia.`);
  const task = await studyApi(`/api/study/sessions/${activeStudySessionId}/tasks/start`, {});
  const result = await chrome.runtime.sendMessage({
    type: "LOAD_STUDY_TASK",
    studySessionId: activeStudySessionId,
    taskUrl: task.start_url
  });
  if (!result?.success) throw new Error(result?.error ?? "Kegiatan pertama belum dapat dibuka.");
  loadedTaskKey = null;
  return true;
};

const handleStudyUtterance = async (spoken: string): Promise<void> => {
  if (!activeBenchmarkTask?.study_session_id && !activeStudySessionId) return;
  if (silenceTimer !== null) window.clearTimeout(silenceTimer);
  silenceTimer = null;
  silencePromptCount = 0;
  const normalized = spoken.trim().toLocaleLowerCase("id-ID");
  if (!normalized) {
    await enterAutomaticListening();
    return;
  }
  heardText.hidden = false;
  const heardValue = heardText.querySelector("span");
  if (heardValue) heardValue.textContent = spoken;
  await setStudyVoiceState("PROCESSING");
  setAgentState("processing");

  if (await handleOnboardingUtterance(spoken)) return;
  if (!activeBenchmarkTask) return;

  if (isAny(normalized, ["ulang", "ulangi", "sekali lagi", "yang tadi"])) {
    await repeatCurrentGuidance();
    return;
  }

  if (feedbackMode) {
    feedbackMode = false;
    const studyId = activeBenchmarkTask.study_session_id;
    await studyApi(`/api/study/sessions/${studyId}/feedback`, { text: spoken });
    await speak("Terima kasih. Jawabanmu sudah tersimpan. Pengujian selesai dan perekaman sekarang dihentikan.");
    await studyApi(`/api/study/sessions/${studyId}/complete`, {});
    if (utterancePollTimer !== null) window.clearInterval(utterancePollTimer);
    utterancePollTimer = null;
    activeRunId = null;
    await setStudyVoiceState("COMPLETE");
    dialogueContext = "COMPLETE";
    setAgentState("complete");
    promptParticipant("Pengujian selesai. Terima kasih.");
    return;
  }

  if (isAny(normalized, ["bacakan halaman", "baca halaman", "bacakan pilihan", "baca pilihannya", "pilihannya apa", "opsinya apa"])) {
    await readCurrentPage();
    return;
  }

  const affirmation = isAny(normalized, ["iya", "ya", "siap", "lanjut", "sudah", "udah", "boleh", "oke", "ok"]);
  if (isAny(normalized, ["saya bingung", "aku bingung", "harus bagaimana", "harus gimana", "saya harus apa"])) {
    dialogueContext = "AWAITING_REQUEST";
    await speak(`${participantName ? `${participantName}, ` : ""}tidak apa-apa. Saya akan membacakan kembali instruksi dan pilihannya secara pelan-pelan.`);
    await repeatCurrentGuidance();
    return;
  }

  if (activeRunId) {
    if (dialogueContext === "AWAITING_APPROVAL" && isAny(normalized, ["setujui", "saya setuju"])) {
      const result = await chrome.runtime.sendMessage({
        type: "LIVE_COMMAND",
        runId: activeRunId,
        command: "APPROVE",
        transcript: spoken
      });
      if (result?.success && result.run) {
        await setStudyVoiceState("AGENT_WORKING");
        dialogueContext = "AGENT_WORKING";
        applyLiveRun(result.run as LiveRunResponse);
        return;
      }
      console.warn("Study approval failed", result?.error ?? "unknown error");
    } else if (dialogueContext === "AWAITING_APPROVAL" && isAny(normalized, ["iya", "ya", "oke", "ok", "lanjut"])) {
      await speak("Kalau kamu setuju, katakan: saya setuju. Kalau tidak, katakan: tidak.");
      await enterAutomaticListening();
      return;
    }
    await speak(dialogueContext === "AGENT_WORKING"
      ? "Saya masih menyelesaikan permintaanmu. Tunggu sebentar."
      : "Saya belum memahami jawaban itu. Coba jawab iya, tidak, atau jelaskan pilihanmu dengan singkat.");
    await enterAutomaticListening();
    return;
  }

  if (affirmation) {
    dialogueContext = "AWAITING_REQUEST";
    await speak("Baik. Sekarang sebutkan pilihan atau tindakan yang sesuai dengan instruksi kegiatan tadi.");
    await enterAutomaticListening();
    return;
  }

  await startLiveGoal(spoken);
};

const pollStudyUtterances = async (): Promise<void> => {
  const studyId = activeBenchmarkTask?.study_session_id ?? activeStudySessionId;
  if (!studyId) return;
  try {
    const study = await studyApi(`/api/study/sessions/${studyId}`);
    const utterances = Array.isArray(study.utterances)
      ? study.utterances as Array<{ utterance_id?: number; text?: string }>
      : [];
    const next = utterances.find((item) => Number(item.utterance_id) > lastUtteranceId);
    if (!next?.text || !next.utterance_id) return;
    lastUtteranceId = next.utterance_id;
    await handleStudyUtterance(next.text);
  } catch (error) {
    console.warn("Study utterance polling failed", error);
  }
};

const startStudyUtterancePolling = (): void => {
  if (utterancePollTimer !== null) window.clearInterval(utterancePollTimer);
  utterancePollTimer = window.setInterval(() => void pollStudyUtterances(), 450);
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
  setCommandContextReady(Boolean(goal.value));
  announce("Transkrip dikonfirmasi. Periksa tujuan lalu jalankan.");
  submitGoal.focus();
});
editTranscript.addEventListener("click", () => transcript.focus());

const loadActiveTask = async (): Promise<void> => {
  if (loadingActiveTask) return;
  loadingActiveTask = true;
  setAgentState("loading");
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) {
    submitGoal.disabled = false;
    setAgentState("ready");
    loadingActiveTask = false;
    return;
  }
  announce("Menyiapkan kegiatan yang sedang dibuka.");
  try {
    const result = await chrome.runtime.sendMessage({ type: "GET_ACTIVE_TASK" });
    if (!result?.success || !result.task) throw new Error(result?.error ?? "Task tidak ditemukan.");
    const nextTask = result.task as ActiveBenchmarkTask;
    if (["FEEDBACK", "COMPLETED"].includes(nextTask.study_status ?? "")) return;
    const taskKey = `${nextTask.study_session_id ?? "manual"}:${nextTask.task_id}:${nextTask.task_index ?? 0}`;
    if (taskKey === loadedTaskKey) return;
    loadedTaskKey = taskKey;
    activeBenchmarkTask = nextTask;
    activeStudySessionId = nextTask.study_session_id ?? activeStudySessionId;
    participantName = nextTask.participant_name ?? participantName;
    goal.value = activeBenchmarkTask.goal ?? "";
    setCommandContextReady(Boolean(activeBenchmarkTask.goal));
    byId("active-goal").textContent = activeBenchmarkTask.goal ?? "Menunggu permintaan peserta.";
    submitGoal.disabled = false;
    repeatGuide.disabled = false;
    const handsFree = Boolean(activeBenchmarkTask.study_session_id);
    const instruction = handsFree
      ? activeBenchmarkTask.instruction ?? "Ceritakan apa yang ingin kamu lakukan."
      : `Tugas ${activeBenchmarkTask.task_id} siap. Gunakan kontrol cadangan untuk memulai.`;
    promptParticipant(instruction);
    announce(handsFree ? "Kegiatan siap. Saya akan mulai mendengarkan." : `Tugas ${activeBenchmarkTask.task_id} siap.`);
    setAgentState("ready");
    if (handsFree) {
      terminalHandled = false;
      feedbackMode = false;
      activeRunId = null;
      const position = (activeBenchmarkTask.task_index ?? 0) + 1;
      const greeting = position === 1
        ? `${participantName ? `${participantName}, ` : ""}ini kegiatan pertama. ${instruction}`
        : `${participantName ? `${participantName}, ` : ""}kita lanjut ke kegiatan ${position}. ${instruction}`;
      dialogueContext = "AWAITING_REQUEST";
      await speak(greeting);
      startStudyUtterancePolling();
      await readCurrentPage();
    } else {
      void speak(instruction);
    }
  } catch (error) {
    activeBenchmarkTask = null;
    submitGoal.disabled = false;
    setAgentState("error");
    promptParticipant("Kegiatan belum siap. Minta peneliti membantu.");
    announce(`Kegiatan belum tersedia. ${error instanceof Error ? error.message : String(error)}`);
    goal.focus();
  } finally {
    loadingActiveTask = false;
  }
};

const startStudyOnboarding = async (studySessionId: string): Promise<void> => {
  activeStudySessionId = studySessionId;
  activeBenchmarkTask = null;
  loadedTaskKey = null;
  const study = await studyApi(`/api/study/sessions/${studySessionId}`);
  const utterances = Array.isArray(study.utterances)
    ? study.utterances as Array<{ utterance_id?: number }>
    : [];
  lastUtteranceId = Math.max(0, ...utterances.map((item) => Number(item.utterance_id) || 0));
  if (study.participant_name) {
    participantName = String(study.participant_name);
    return;
  }
  profileDraft = { name: "", nameSpelling: "", participantClass: "" };
  onboardingStage = "ASK_NAME";
  silencePromptCount = 0;
  startStudyUtterancePolling();
  await speak("Hai, sebelum mulai kita kenalan sebentar ya. Siapa nama kamu?");
  await enterAutomaticListening();
};

const advanceStudyAfterCompletion = async (): Promise<void> => {
  if (!activeBenchmarkTask?.study_session_id || terminalHandled) return;
  clearWorkAcknowledgement();
  terminalHandled = true;
  const currentPosition = (activeBenchmarkTask.task_index ?? 0) + 1;
  await speak(`Kegiatan ${currentPosition} selesai dan hasilnya sudah diperiksa.`);
  const result = await chrome.runtime.sendMessage({ type: "COMPLETE_AND_START_NEXT_STUDY_TASK" });
  if (!result?.success) {
    terminalHandled = false;
    await setStudyVoiceState("ERROR");
    promptParticipant("Kegiatan berikutnya belum dapat dibuka. Minta peneliti membantu.");
    return;
  }
  if (result.completed) {
    activeRunId = null;
    if (utterancePollTimer !== null) window.clearInterval(utterancePollTimer);
    utterancePollTimer = null;
    await speak("Semua kegiatan sudah selesai. Terima kasih. Perekaman sekarang dihentikan dan disimpan.");
    await setStudyVoiceState("COMPLETE");
    dialogueContext = "COMPLETE";
    setAgentState("complete");
    promptParticipant("Pengujian selesai. Terima kasih.");
    return;
  }
  if (result.feedback) {
    activeRunId = null;
    feedbackMode = true;
    dialogueContext = "FEEDBACK";
    await speak("Sebelum selesai, ceritakan singkat apa yang terasa mudah atau sulit, dan apa yang perlu diperbaiki.");
    await enterAutomaticListening();
    return;
  }
  activeRunId = null;
  lastSpokenActivityKey = null;
  lastWaitingAnnouncement = "";
  window.setTimeout(() => void loadActiveTask(), 1_200);
};

const handleWaitingStudyRun = async (run: LiveRunResponse): Promise<void> => {
  if (!activeBenchmarkTask?.study_session_id || run.announcement === lastWaitingAnnouncement) return;
  clearWorkAcknowledgement();
  lastWaitingAnnouncement = run.announcement;
  dialogueContext = "AWAITING_APPROVAL";
  await speak(`Saya perlu memastikan sebelum melanjutkan. ${run.announcement} Kalau kamu setuju, katakan: saya setuju. Kalau tidak, katakan: tidak.`);
  await enterAutomaticListening();
};

const handleFailedStudyRun = async (): Promise<void> => {
  if (!activeBenchmarkTask?.study_session_id || terminalHandled) return;
  clearWorkAcknowledgement();
  terminalHandled = true;
  activeRunId = null;
  dialogueContext = "AWAITING_REQUEST";
  await speak("Kegiatan belum berhasil. Coba jelaskan kembali apa yang ingin kamu lakukan.");
  terminalHandled = false;
  await enterAutomaticListening();
};

const applyLiveRun = (run: LiveRunResponse): void => {
  activeRunId = run.run_id;
  setAgentState(run.status);
  announce(run.error ? `${run.announcement} ${run.error}` : run.announcement);
  if (run.task_map) renderTaskMap(run.task_map);
  renderActivity(run);
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(run.status);
  if (terminal) clearWorkAcknowledgement();
  setCommandContextReady(!terminal);
  if (terminal && pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
    submitGoal.disabled = false;
  }
  if (run.status === "COMPLETED") void advanceStudyAfterCompletion();
  if (run.status === "WAITING_USER") void handleWaitingStudyRun(run);
  if (run.status === "FAILED") void handleFailedStudyRun();
};

const stopMissingRunPolling = (message: string): void => {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = null;
  activeRunId = null;
  setCommandContextReady(false);
  submitGoal.disabled = false;
  setAgentState("error");
  activityPhase.textContent = "Run tidak tersedia";
  activityDetail.textContent = message;
  announce(message);
};

const pollLiveRun = (): void => {
  if (!activeRunId || typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  const requestedRunId = activeRunId;
  void chrome.runtime.sendMessage({ type: "GET_LIVE_RUN", runId: requestedRunId }).then((result) => {
    if (activeRunId !== requestedRunId) return;
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
  await startLiveGoal(value);
});

repeatGuide.addEventListener("click", () => {
  if (!activeBenchmarkTask) {
    announce("Instruksi task belum tersedia.");
    return;
  }
  void speak(activeBenchmarkTask.study_session_id
    ? "Saya siap membantu. Ceritakan apa yang ingin kamu lakukan."
    : `Tugas ${activeBenchmarkTask.task_id} siap. Gunakan kontrol cadangan untuk memulai.`);
});

toggleGuide.addEventListener("click", () => {
  voiceGuideEnabled = !voiceGuideEnabled;
  toggleGuide.setAttribute("aria-pressed", String(voiceGuideEnabled));
  toggleGuide.textContent = `Suara: ${voiceGuideEnabled ? "aktif" : "mati"}`;
  if (voiceGuideEnabled) {
    void speak("Panduan suara Bahasa Indonesia aktif.");
  } else {
    stopSpeech();
    voiceState.textContent = "Panduan suara dimatikan.";
    announce("Panduan suara dimatikan. Semua informasi tetap tersedia sebagai teks.");
  }
});

const runCommand = (command: Command): void => {
  if (!commandContextReady) return;
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
  if (command === "CANCEL" || command === "REJECT") setCommandContextReady(false);
};

commandButtons.forEach((button) => {
  button.addEventListener("click", () => runCommand(button.dataset.command as Command));
});

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  const shortcut: Command | undefined = event.key === "Escape" ? "REJECT"
    : event.altKey ? ({ a: "APPROVE", e: "EDIT", p: "PAUSE", t: "TAKE_OVER", r: "RESUME", c: "CANCEL" } as Record<string, Command>)[key]
      : undefined;
  if (!shortcut) return;
  const shortcutButton = commandButtons.find((button) => button.dataset.command === shortcut);
  if (!shortcutButton || shortcutButton.disabled) return;
  event.preventDefault();
  runCommand(shortcut);
});

window.addEventListener("a11y-cua:task-map", (event) => {
  renderTaskMap((event as CustomEvent<AccessibleTaskMap>).detail);
});

// Deterministic QA hook; production transcripts still come only from the voice adapter.
window.addEventListener("a11y-cua:voice-transcript", (event) => {
  const spoken = (event as CustomEvent<{ transcript: string }>).detail.transcript;
  if (activeBenchmarkTask?.study_session_id) {
    void handleStudyUtterance(spoken);
    return;
  }
  transcript.value = spoken;
  transcriptReview.hidden = false;
  announce("Transkrip siap. Periksa lalu konfirmasi atau ubah.");
  transcript.focus();
});

if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
    if (!message || typeof message !== "object") return false;
    const payload = message as { type?: string; studySessionId?: string };
    const operation = payload.type === "COORDINATOR_LOAD_ACTIVE_TASK"
      ? loadActiveTask()
      : payload.type === "COORDINATOR_START_ONBOARDING" && payload.studySessionId
        ? startStudyOnboarding(payload.studySessionId)
        : null;
    if (!operation) return false;
    void operation
      .then(() => sendResponse({ success: true }))
      .catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  });
}

void loadActiveTask();
