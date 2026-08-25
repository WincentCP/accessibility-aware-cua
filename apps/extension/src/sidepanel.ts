import "./styles.css";
import type { AccessibleTaskMap, TaskMapItem } from "./contracts";
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
    ? "Persetujuan diperlukan. Pilih Setujui, Ubah, atau Tolak." : "";
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

submitGoal.addEventListener("click", () => {
  const value = goal.value.trim();
  if (!value) {
    announce("Tujuan masih kosong. Ketik tujuan atau gunakan input suara.");
    goal.focus();
    return;
  }
  byId("active-goal").textContent = value;
  announce("Tujuan diterima. Agen akan menampilkan tindakan sebagai direncanakan sebelum menjalankannya.");
  window.dispatchEvent(new CustomEvent("a11y-cua:goal", { detail: { goal: value } }));
});

const runCommand = (command: Command): void => {
  const labels: Record<Command, string> = {
    APPROVE: "Persetujuan dikirim.", EDIT: "Ubah dipilih. Fokus kembali ke tujuan.",
    REJECT: "Tindakan ditolak.", PAUSE: "Agen dijeda.",
    TAKE_OVER: "Mode ambil alih aktif. Fokus dikembalikan ke halaman web.",
    RESUME: "Agen dilanjutkan dari observasi baru.", CANCEL: "Tugas dibatalkan."
  };
  approvalAlert.hidden = true;
  announce(labels[command]);
  window.dispatchEvent(new CustomEvent("a11y-cua:command", { detail: { command } }));
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
