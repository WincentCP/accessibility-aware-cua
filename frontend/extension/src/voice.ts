export type TranscriptState =
  | "IDLE"
  | "LISTENING"
  | "PROCESSING"
  | "REVIEW"
  | "CONFIRMED"
  | "CANCELED"
  | "ERROR";

export interface TranscriptUpdate {
  state: TranscriptState;
  transcript?: string;
  message: string;
  errorCode?: "MICROPHONE_DENIED" | "TRANSCRIPTION_FAILED" | "UNSUPPORTED";
}

export type TranscribeAudio = (audio: Blob) => Promise<string>;

export interface VoiceAdapter {
  readonly state: TranscriptState;
  start(): Promise<void>;
  stop(): void;
  cancel(): void;
}

export interface PushToTalkOptions {
  maxDurationMs?: number;
  transcribe: TranscribeAudio;
  onUpdate: (update: TranscriptUpdate) => void;
}

/**
 * Push-to-talk transport for a Whisper-compatible transcriber.
 * Raw audio exists only in memory and is discarded immediately after transcription/cancel.
 */
export class WhisperPushToTalkAdapter implements VoiceAdapter {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private timeoutId: number | null = null;
  private canceled = false;
  private currentState: TranscriptState = "IDLE";
  private readonly maxDurationMs: number;

  constructor(private readonly options: PushToTalkOptions) {
    this.maxDurationMs = options.maxDurationMs ?? 20_000;
  }

  get state(): TranscriptState {
    return this.currentState;
  }

  private update(update: TranscriptUpdate): void {
    this.currentState = update.state;
    this.options.onUpdate(update);
  }

  private cleanup(): void {
    if (this.timeoutId !== null) window.clearTimeout(this.timeoutId);
    this.timeoutId = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
  }

  async start(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      this.update({
        state: "ERROR",
        message: "Input suara tidak didukung. Gunakan kolom teks.",
        errorCode: "UNSUPPORTED"
      });
      return;
    }
    if (this.currentState === "LISTENING" || this.currentState === "PROCESSING") return;
    this.canceled = false;
    this.chunks = [];
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch {
      this.cleanup();
      this.update({
        state: "ERROR",
        message: "Mikrofon tidak diizinkan. Gunakan teks; semua fungsi tetap tersedia.",
        errorCode: "MICROPHONE_DENIED"
      });
      return;
    }
    this.recorder = new MediaRecorder(this.stream);
    this.recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    });
    this.recorder.addEventListener("stop", () => void this.finishRecording(), { once: true });
    this.recorder.start();
    this.update({ state: "LISTENING", message: "Mendengarkan. Tekan lagi untuk berhenti." });
    this.timeoutId = window.setTimeout(() => this.stop(), this.maxDurationMs);
  }

  stop(): void {
    if (this.recorder?.state === "recording") this.recorder.stop();
  }

  cancel(): void {
    this.canceled = true;
    if (this.recorder?.state === "recording") {
      this.recorder.stop();
    } else {
      this.cleanup();
      this.update({ state: "CANCELED", message: "Input suara dibatalkan. Audio tidak disimpan." });
    }
  }

  private async finishRecording(): Promise<void> {
    if (this.canceled) {
      this.cleanup();
      this.update({ state: "CANCELED", message: "Input suara dibatalkan. Audio tidak disimpan." });
      return;
    }
    this.update({ state: "PROCESSING", message: "Mengubah suara menjadi teks…" });
    const audio = new Blob(this.chunks, { type: this.recorder?.mimeType || "audio/webm" });
    this.chunks = [];
    try {
      const transcript = (await this.options.transcribe(audio)).trim();
      if (!transcript) throw new Error("empty transcript");
      this.update({
        state: "REVIEW",
        transcript,
        message: "Transkrip siap. Periksa lalu konfirmasi atau ubah."
      });
    } catch {
      this.update({
        state: "ERROR",
        message: "Transkripsi gagal. Coba lagi atau gunakan teks.",
        errorCode: "TRANSCRIPTION_FAILED"
      });
    } finally {
      this.cleanup();
    }
  }
}

export const postToWhisperAdapter: TranscribeAudio = async (audio) => {
  const response = await fetch("http://127.0.0.1:8000/api/voice/transcribe", {
    method: "POST",
    headers: { "content-type": audio.type || "audio/webm" },
    body: audio
  });
  if (!response.ok) throw new Error(`transcription endpoint returned ${response.status}`);
  const payload = (await response.json()) as { transcript?: unknown };
  if (typeof payload.transcript !== "string") throw new Error("invalid transcript response");
  return payload.transcript;
};
