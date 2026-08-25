import "./styles.css";
import type { AccessibleTaskMap, LiveRunResponse, TaskMapItem } from "./contracts";
import { sanitizeTaskMap } from "./task-map";
import { postToWhisperAdapter, WhisperPushToTalkAdapter } from "./voice";

type Command = "APPROVE" | "EDIT" | "REJECT" | "PAUSE" | "TAKE_OVER" | "RESUME" | "CANCEL";

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
const status = byId<HTMLElement>("status");
const approvalAlert = byId<HTMLElement>("approval-alert");
let activeRunId: string | null = null;
let pollTimer: number | null = null;

const announce = (message: string): void => { status.textContent = message; };

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
  const { map, invalidatedCount } = sanitizeTaskMap(source);
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
  announce(invalidatedCount
    ? `Peta tugas diperbarui. ${invalidatedCount} item lama disembunyikan.`
    : `Peta tugas diperbarui. ${map.progress_label}`);
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

const applyLiveRun = (run: LiveRunResponse): void => {
  activeRunId = run.run_id;
  announce(run.error ? `${run.announcement} ${run.error}` : run.announcement);
  if (run.task_map) renderTaskMap(run.task_map);
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(run.status);
  if (terminal && pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
    submitGoal.disabled = false;
  }
};

const pollLiveRun = (): void => {
  if (!activeRunId || typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  void chrome.runtime.sendMessage({ type: "GET_LIVE_RUN", runId: activeRunId }).then((result) => {
    if (result?.success && result.run) applyLiveRun(result.run as LiveRunResponse);
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
  announce("Tujuan diterima. Agen akan menampilkan tindakan sebagai direncanakan sebelum menjalankannya.");
  window.dispatchEvent(new CustomEvent("a11y-cua:goal", { detail: { goal: value } }));
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  submitGoal.disabled = true;
  try {
    const result = await chrome.runtime.sendMessage({ type: "START_LIVE_AGENT", goal: value });
    if (!result?.success || !result.run) throw new Error(result?.error ?? "Live agent tidak dapat dimulai.");
    applyLiveRun(result.run as LiveRunResponse);
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = window.setInterval(pollLiveRun, 750);
  } catch (error) {
    submitGoal.disabled = false;
    announce(`Live agent belum berjalan. ${error instanceof Error ? error.message : String(error)}`);
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
