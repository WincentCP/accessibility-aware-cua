(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const startButton = byId("start-research");
  const liveSession = byId("live-session");
  const stateLabel = byId("session-state");
  const sessionMessage = byId("session-message");
  const sessionError = byId("session-error");
  const cameraPreview = byId("camera-preview");
  const recordingState = byId("recording-state");
  const taskState = byId("task-state");
  const voiceState = byId("voice-state");
  const transcriptPreview = byId("transcript-preview");
  const studyFrame = byId("study-task-frame");
  const downloadReport = byId("download-report");

  let session = null;
  let userStream = null;
  let screenStream = null;
  let compositeScreenStream = null;
  let compositeCanvas = null;
  let compositeFrame = null;
  let screenPreview = null;
  let recorders = [];
  let uploadQueue = Promise.resolve();
  let pollTimer = null;
  let audioContext = null;
  let transcriptionSocket = null;
  let transcriptionReconnectTimer = null;
  let shouldStreamSpeech = false;
  let lastFinalTranscript = "";
  let lastFinalAt = 0;

  const api = async (path, body = {}) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `API ${response.status}`);
    return payload;
  };

  const setState = (state, message) => {
    document.documentElement.dataset.researchState = state.toLowerCase();
    stateLabel.textContent = {
      INITIALIZING: "Menyiapkan sesi",
      SPEAKING: "AI sedang berbicara",
      LISTENING: "Giliran kamu berbicara",
      PROCESSING: "AI memahami jawaban",
      AGENT_WORKING: "AI sedang bekerja",
      COMPLETE: "Sesi selesai",
      ERROR: "Perlu bantuan"
    }[state] || "Menunggu";
    sessionMessage.textContent = message;
  };

  const postRecordingChunk = (kind, sequence, chunk) => {
    uploadQueue = uploadQueue.then(async () => {
      const response = await fetch(
        `/api/study/sessions/${session.study_session_id}/recordings/${kind}?sequence=${sequence}`,
        { method: "POST", headers: { "content-type": chunk.type || "video/webm" }, body: chunk }
      );
      if (!response.ok) throw new Error(`Rekaman ${kind} tidak dapat disimpan.`);
    });
    return uploadQueue;
  };

  const createRecorder = (kind, stream) => {
    const mimeType = MediaRecorder.isTypeSupported("video/webm;codecs=vp8,opus")
      ? "video/webm;codecs=vp8,opus"
      : "video/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    let sequence = 0;
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) void postRecordingChunk(kind, sequence++, event.data);
    });
    recorder.start(5_000);
    recorders.push(recorder);
  };

  const roundedRectangle = (context, x, y, width, height, radius) => {
    const safeRadius = Math.min(radius, width / 2, height / 2);
    context.beginPath();
    context.moveTo(x + safeRadius, y);
    context.arcTo(x + width, y, x + width, y + height, safeRadius);
    context.arcTo(x + width, y + height, x, y + height, safeRadius);
    context.arcTo(x, y + height, x, y, safeRadius);
    context.arcTo(x, y, x + width, y, safeRadius);
    context.closePath();
  };

  const createCompositeScreenStream = async () => {
    if (typeof HTMLCanvasElement.prototype.captureStream !== "function") return screenStream;
    const screenTrack = screenStream.getVideoTracks()[0];
    const settings = screenTrack?.getSettings?.() || {};
    compositeCanvas = document.createElement("canvas");
    compositeCanvas.width = Number(settings.width) || 1280;
    compositeCanvas.height = Number(settings.height) || 720;
    compositeCanvas.hidden = true;
    document.body.append(compositeCanvas);

    screenPreview = document.createElement("video");
    screenPreview.muted = true;
    screenPreview.playsInline = true;
    screenPreview.srcObject = screenStream;
    void screenPreview.play().catch(() => undefined);
    void cameraPreview.play().catch(() => undefined);
    const context = compositeCanvas.getContext("2d", { alpha: false });
    if (!context) return screenStream;

    const draw = () => {
      const width = compositeCanvas.width;
      const height = compositeCanvas.height;
      try {
        context.drawImage(screenPreview, 0, 0, width, height);
        if (cameraPreview.readyState >= 2) {
          const margin = Math.max(18, Math.round(width * 0.018));
          const frameWidth = Math.min(420, Math.max(220, Math.round(width * 0.23)));
          const cameraRatio = cameraPreview.videoWidth && cameraPreview.videoHeight
            ? cameraPreview.videoWidth / cameraPreview.videoHeight
            : 16 / 9;
          const frameHeight = Math.round(frameWidth / cameraRatio);
          const x = width - frameWidth - margin;
          const y = height - frameHeight - margin;
          const radius = Math.max(14, Math.round(frameWidth * 0.055));
          context.save();
          context.shadowColor = "rgba(15, 23, 42, 0.28)";
          context.shadowBlur = Math.round(frameWidth * 0.06);
          roundedRectangle(context, x - 4, y - 4, frameWidth + 8, frameHeight + 8, radius + 4);
          context.fillStyle = "#ffffff";
          context.fill();
          context.restore();
          context.save();
          roundedRectangle(context, x, y, frameWidth, frameHeight, radius);
          context.clip();
          context.drawImage(cameraPreview, x, y, frameWidth, frameHeight);
          context.restore();
        }
      } catch {
        // A new frame will be attempted as soon as both video sources are ready.
      }
      compositeFrame = window.requestAnimationFrame(draw);
    };
    draw();

    compositeScreenStream = compositeCanvas.captureStream(25);
    userStream.getAudioTracks().forEach((track) => {
      if (typeof MediaStreamTrack !== "undefined" && track instanceof MediaStreamTrack) {
        compositeScreenStream.addTrack(typeof track.clone === "function" ? track.clone() : track);
      }
    });
    return compositeScreenStream;
  };

  const startRecording = async () => {
    createRecorder("user", userStream);
    createRecorder("screen", await createCompositeScreenStream());
    session = await api(`/api/study/sessions/${session.study_session_id}/recording-state`, { state: "RECORDING" });
    recordingState.textContent = "Rekaman aktif";
  };

  const openingGuide = "Yuk, kita mulai. Browser akan meminta izin kamera, mikrofon, dan layar. Pilih Izinkan. Untuk layar, pilih Seluruh layar, lalu pilih Bagikan. Saya akan menunggu.";

  const requestIndonesianSpeech = async (text) => {
    const response = await fetch("/api/voice/speech", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text })
    });
    if (!response.ok) throw new Error("Panduan suara Bahasa Indonesia belum siap.");
    return response.blob();
  };

  const playSpeechBlob = async (blob) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    await new Promise((resolve, reject) => {
      audio.addEventListener("ended", resolve, { once: true });
      audio.addEventListener("error", () => reject(new Error("Panduan suara tidak dapat diputar.")), { once: true });
      void audio.play().catch(reject);
    });
    URL.revokeObjectURL(url);
  };

  const speakWithIndonesianDeviceVoice = async (text) => {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return false;
    const voice = window.speechSynthesis.getVoices()
      .find((candidate) => candidate.lang.toLowerCase().startsWith("id"));
    if (!voice) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "id-ID";
    utterance.voice = voice;
    utterance.rate = 0.95;
    await new Promise((resolve) => {
      utterance.addEventListener("end", resolve, { once: true });
      utterance.addEventListener("error", resolve, { once: true });
      window.speechSynthesis.speak(utterance);
    });
    return true;
  };

  const playGuide = async (text, preparedSpeech) => {
    try {
      const blob = await (preparedSpeech || requestIndonesianSpeech(text));
      if (!blob) throw new Error("Audio belum tersedia.");
      await playSpeechBlob(blob);
    } catch (error) {
      if (!await speakWithIndonesianDeviceVoice(text)) throw error;
    }
  };

  const openingGuideSpeech = requestIndonesianSpeech(openingGuide).catch(() => null);

  const stopRecording = async () => {
    if (!recorders.length) return;
    recordingState.textContent = "Rekaman sedang disimpan";
    await api(`/api/study/sessions/${session.study_session_id}/recording-state`, { state: "STOPPING" });
    const stopped = recorders.map((recorder) => new Promise((resolve) => {
      if (recorder.state === "inactive") return resolve();
      recorder.addEventListener("stop", resolve, { once: true });
      recorder.stop();
    }));
    await Promise.all(stopped);
    await uploadQueue;
    recorders = [];
    userStream?.getTracks().forEach((track) => track.stop());
    screenStream?.getTracks().forEach((track) => track.stop());
    compositeScreenStream?.getTracks().forEach((track) => track.stop());
    if (compositeFrame !== null) window.cancelAnimationFrame(compositeFrame);
    compositeCanvas?.remove();
    compositeScreenStream = null;
    compositeCanvas = null;
    compositeFrame = null;
    screenPreview = null;
    transcriptionSocket?.close();
    if (audioContext?.state !== "closed") await audioContext?.close?.();
    session = await api(`/api/study/sessions/${session.study_session_id}/recording-state`, { state: "SAVED" });
    recordingState.textContent = "Rekaman tersimpan";
  };

  const bytesToBase64 = (bytes) => {
    let binary = "";
    const size = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += size) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + size));
    }
    return btoa(binary);
  };

  const downsampleTo16k = (input, inputRate) => {
    const ratio = inputRate / 16_000;
    const length = Math.max(1, Math.floor(input.length / ratio));
    const output = new Int16Array(length);
    for (let index = 0; index < length; index += 1) {
      const start = Math.floor(index * ratio);
      const end = Math.min(input.length, Math.floor((index + 1) * ratio));
      let sum = 0;
      for (let sample = start; sample < end; sample += 1) sum += input[sample];
      const value = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
      output[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
    }
    return new Uint8Array(output.buffer);
  };

  const openTranscriptionSocket = () => new Promise((resolve, reject) => {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    transcriptionSocket = new WebSocket(
      `${protocol}://${location.host}/api/voice/live-transcription?study_session_id=${encodeURIComponent(session.study_session_id)}`
    );
    const timeout = window.setTimeout(() => reject(new Error("Transkripsi belum siap.")), 10_000);
    transcriptionSocket.addEventListener("message", async (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "ready") {
        window.clearTimeout(timeout);
        voiceState.textContent = "Siap";
        resolve();
      }
      if (message.type === "interim" && message.text) {
        transcriptPreview.textContent = `Mendengar: ${message.text}`;
      }
      if (message.type === "final" && message.text) {
        const normalized = String(message.text).trim();
        const now = Date.now();
        if (!normalized || (normalized === lastFinalTranscript && now - lastFinalAt < 3_000)) return;
        lastFinalTranscript = normalized;
        lastFinalAt = now;
        shouldStreamSpeech = false;
        transcriptPreview.textContent = `Peserta berkata: ${normalized}`;
        await api(`/api/study/sessions/${session.study_session_id}/utterances`, { text: normalized });
      }
    });
    transcriptionSocket.addEventListener("close", () => {
      window.clearTimeout(timeout);
      if (session?.status !== "COMPLETED") {
        voiceState.textContent = "Menyambungkan ulang";
        window.clearTimeout(transcriptionReconnectTimer);
        transcriptionReconnectTimer = window.setTimeout(() => {
          void openTranscriptionSocket().catch(() => undefined);
        }, 1_000);
      }
    });
    transcriptionSocket.addEventListener("error", () => reject(new Error("Transkripsi langsung tidak dapat tersambung.")), { once: true });
  });

  const connectLiveTranscription = async () => {
    await openTranscriptionSocket();

    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(userStream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    processor.addEventListener("audioprocess", (event) => {
      if (!shouldStreamSpeech || transcriptionSocket?.readyState !== WebSocket.OPEN) return;
      const pcm = downsampleTo16k(event.inputBuffer.getChannelData(0), audioContext.sampleRate);
      transcriptionSocket.send(JSON.stringify({ audio: bytesToBase64(pcm) }));
    });
    source.connect(processor);
    processor.connect(silentGain);
    silentGain.connect(audioContext.destination);
  };

  const pollSession = async () => {
    if (!session) return;
    try {
      const response = await fetch(`/api/study/sessions/${session.study_session_id}`);
      session = await response.json();
      const taskNumber = Math.min(session.task_index + 1, session.task_count);
      taskState.textContent = session.status === "COMPLETED"
        ? "Semua kegiatan selesai"
        : `Kegiatan ${taskNumber} dari ${session.task_count}`;
      voiceState.textContent = {
        SPEAKING: "AI sedang berbicara",
        LISTENING: "Silakan berbicara",
        PROCESSING: "Memahami jawaban",
        AGENT_WORKING: "Asisten sedang bekerja",
        COMPLETE: "Selesai",
        ERROR: "Perlu bantuan"
      }[session.voice_state] || "Menunggu";
      shouldStreamSpeech = session.voice_state === "LISTENING";
      if (shouldStreamSpeech) setState("LISTENING", "Silakan berbicara. Sistem sedang mendengarkan.");
      else if (session.voice_state === "SPEAKING") setState("SPEAKING", "AI Guide sedang berbicara.");
      else if (session.voice_state === "AGENT_WORKING") setState("AGENT_WORKING", "Asisten sedang menyelesaikan kegiatan.");
      if (session.status === "COMPLETED") {
        window.clearInterval(pollTimer);
        pollTimer = null;
        setState("COMPLETE", "Semua kegiatan selesai. Perekaman sedang disimpan.");
        await stopRecording();
        setState("COMPLETE", "Pengujian selesai. Perekaman sudah disimpan.");
        downloadReport.href = `/api/study/sessions/${session.study_session_id}/report.pdf`;
        downloadReport.hidden = false;
      }
    } catch (error) {
      sessionError.hidden = false;
      sessionError.textContent = `Status sesi tidak dapat diperbarui: ${error.message}`;
    }
  };

  const start = async () => {
    startButton.disabled = true;
    liveSession.hidden = false;
    sessionError.hidden = true;
    setState("INITIALIZING", "Ikuti petunjuk suara untuk memberikan izin perangkat.");
    try {
      const openingVoice = playGuide(openingGuide, openingGuideSpeech);
      const userPermission = navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      const screenPermission = navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: "monitor" },
        audio: false
      });
      [userStream, screenStream] = await Promise.all([userPermission, screenPermission]);
      await openingVoice;
      cameraPreview.srcObject = userStream;

      const healthResponse = await fetch("/api/study/readiness");
      if (!healthResponse.ok) throw new Error("Backend atau database belum siap.");
      const health = await healthResponse.json();
      if (!health.ready) throw new Error("Backend, database, browser, atau agent belum siap.");
      const agentReady = health.agent?.status === "ready";

      session = await api("/api/study/automatic", { condition_id: "C0" });
      const shellUrl = new URL(window.location.href);
      shellUrl.searchParams.set("study_session_id", session.study_session_id);
      window.history.replaceState({}, "", shellUrl);
      document.documentElement.dataset.studySessionId = session.study_session_id;
      await startRecording();
      await playGuide("Sip, semua izin sudah siap. Rekaman dimulai sekarang. Sebelum kegiatan pertama, kita kenalan sebentar ya.");
      await connectLiveTranscription();
      session = await api(`/api/study/sessions/${session.study_session_id}/automatic-readiness`, {
        checks: {
          backend: true,
          agent: agentReady,
          microphone: userStream.getAudioTracks().length > 0,
          camera: userStream.getVideoTracks().length > 0,
          screen: screenStream.getVideoTracks().length > 0,
          audio: typeof Audio !== "undefined"
        }
      });
      if (session.status !== "PROFILE") throw new Error("Salah satu perangkat belum siap.");
      pollTimer = window.setInterval(() => void pollSession(), 500);
      setState("SPEAKING", "AI Guide sedang berkenalan dengan peserta.");
      window.dispatchEvent(new CustomEvent("a11y-cua:study-onboarding-ready", {
        detail: { studySessionId: session.study_session_id }
      }));
    } catch (error) {
      sessionError.hidden = false;
      sessionError.textContent = error.message;
      setState("ERROR", "Persiapan belum berhasil. Periksa izin browser lalu coba lagi.");
      startButton.disabled = false;
      userStream?.getTracks().forEach((track) => track.stop());
      screenStream?.getTracks().forEach((track) => track.stop());
      if (session) await api(`/api/study/sessions/${session.study_session_id}/recording-state`, { state: "FAILED" }).catch(() => {});
    }
  };

  startButton.addEventListener("click", () => void start());
  window.addEventListener("beforeunload", () => {
    recorders.forEach((recorder) => { if (recorder.state === "recording") recorder.stop(); });
    userStream?.getTracks().forEach((track) => track.stop());
    screenStream?.getTracks().forEach((track) => track.stop());
  });
})();
