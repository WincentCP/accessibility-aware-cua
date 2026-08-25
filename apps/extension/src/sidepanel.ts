import "./styles.css";

interface SpeechRecognitionEventLike extends Event {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechWindow = Window & typeof globalThis & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

const goal = document.querySelector<HTMLTextAreaElement>("#goal");
const voiceButton = document.querySelector<HTMLButtonElement>("#voice");
const submitButton = document.querySelector<HTMLButtonElement>("#submit-goal");
const status = document.querySelector<HTMLElement>("#status");

if (!goal || !voiceButton || !submitButton || !status) {
  throw new Error("Accessible shell elements are incomplete.");
}

const speechWindow = window as SpeechWindow;
const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
let recognition: SpeechRecognitionLike | null = null;
let listening = false;

const setListening = (active: boolean): void => {
  listening = active;
  voiceButton.setAttribute("aria-pressed", String(active));
  voiceButton.textContent = active ? "Hentikan input suara" : "Mulai input suara";
};

if (!Recognition) {
  voiceButton.disabled = true;
  voiceButton.title = "Pengenal suara tidak tersedia pada browser ini";
} else {
  recognition = new Recognition();
  recognition.lang = "id-ID";
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript ?? "";
    goal.value = transcript;
    status.textContent = "Input suara diterima. Periksa teks sebelum menjalankan tujuan.";
    goal.focus();
  };
  recognition.onend = () => setListening(false);
  recognition.onerror = () => {
    setListening(false);
    status.textContent = "Input suara tidak berhasil. Gunakan teks atau coba lagi.";
  };
}

voiceButton.addEventListener("click", () => {
  if (!recognition) return;
  if (listening) {
    recognition.stop();
    return;
  }
  setListening(true);
  status.textContent = "Mendengarkan input suara…";
  recognition.start();
});

submitButton.addEventListener("click", () => {
  if (!goal.value.trim()) {
    status.textContent = "Tujuan masih kosong. Tulis atau ucapkan tujuan terlebih dahulu.";
    goal.focus();
    return;
  }
  status.textContent = "Tujuan tersimpan di shell. Koneksi ke agent ditambahkan pada tahap berikutnya.";
});
