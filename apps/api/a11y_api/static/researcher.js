(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const setup = byId("study-setup");
  const isMinor = byId("is-minor");
  const guardian = byId("guardian-consent");
  const setupError = byId("setup-error");
  const consentFlow = byId("consent-flow");
  const consentList = byId("consent-list");
  const checkFlow = byId("check-flow");
  const checkList = byId("check-list");
  const taskFlow = byId("task-flow");
  const feedbackFlow = byId("feedback-flow");
  const taskNote = byId("task-note");
  let session = null;

  const consentQuestions = [
    ["store_name", "Menyimpan nama peserta", "Apakah kamu bersedia jika nama kamu disimpan untuk keperluan penelitian ini?"],
    ["photo", "Mengambil foto dokumentasi", "Apakah kamu bersedia jika peneliti mengambil foto untuk dokumentasi?"],
    ["webcam_audio", "Merekam webcam dan suara", "Apakah kamu bersedia jika wajah dan suara kamu direkam selama kegiatan?"],
    ["screen", "Merekam layar", "Apakah kamu bersedia jika layar kegiatan direkam selama sesi?"]
  ];
  const readinessQuestions = [
    ["audio", "Suara terdengar jelas", "Apakah suara saya terdengar dengan jelas?"],
    ["screen_reader", "Pembaca layar siap", "Apakah pembaca layar sudah aktif dan suaranya terdengar jelas?"]
  ];

  const api = async (path, body) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `API ${response.status}`);
    return payload;
  };

  const speak = (text) => {
    if (!("speechSynthesis" in window)) {
      taskNote.textContent = "Suara browser tidak tersedia. Bacakan naskah yang tampil.";
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "id-ID";
    utterance.rate = 0.94;
    window.speechSynthesis.speak(utterance);
  };

  const renderEvents = () => {
    const list = byId("event-list");
    list.replaceChildren();
    const events = session?.events?.length ? session.events : [{ kind: "SESSION_READY", at: new Date().toISOString() }];
    for (const event of events.slice().reverse()) {
      const item = document.createElement("li");
      item.textContent = `${event.kind.replaceAll("_", " ").toLowerCase()} - ${new Date(event.at).toLocaleTimeString("id-ID")}`;
      list.append(item);
    }
  };

  const renderConsent = () => {
    consentList.replaceChildren();
    for (const [key, label, question] of consentQuestions) {
      const row = document.createElement("div");
      row.className = "consent-row";
      const text = document.createElement("p");
      text.textContent = label;
      text.title = question;
      const actions = document.createElement("div");
      actions.className = "consent-actions";
      for (const [granted, buttonLabel] of [[true, "Setuju"], [false, "Tidak"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = granted ? "button-secondary" : "button-quiet";
        button.textContent = buttonLabel;
        button.setAttribute("aria-pressed", String(session.consent[key] === granted));
        button.addEventListener("click", async () => {
          session = await api(`/api/study/sessions/${session.study_session_id}/consent`, { key, granted });
          render();
          const next = consentQuestions.find(([nextKey]) => session.consent[nextKey] === null);
          if (next) speak(next[2]);
          else speak("Semua jawaban sudah dicatat. Prototipe ini belum memulai perekaman. Sekarang kita mengecek suara dan pembaca layar.");
        });
        actions.append(button);
      }
      row.append(text, actions);
      consentList.append(row);
    }
  };

  const renderChecks = () => {
    checkList.replaceChildren();
    for (const [key, label, question] of readinessQuestions) {
      const row = document.createElement("div");
      row.className = "consent-row";
      const text = document.createElement("p");
      text.textContent = label;
      const actions = document.createElement("div");
      actions.className = "consent-actions";
      for (const [passed, buttonLabel] of [[true, "Siap"], [false, "Belum"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = passed ? "button-secondary" : "button-quiet";
        button.textContent = buttonLabel;
        button.setAttribute("aria-pressed", String(session.readiness_checks[key] === passed));
        button.addEventListener("click", async () => {
          session = await api(`/api/study/sessions/${session.study_session_id}/checks`, { key, passed });
          render();
          if (!passed) {
            speak("Baik, kita berhenti sebentar sampai perangkat siap.");
            return;
          }
          const next = readinessQuestions.find(([nextKey]) => session.readiness_checks[nextKey] !== true);
          if (next) speak(next[2]);
          else if (session.current_task) speak(session.current_task.instruction);
        });
        actions.append(button);
      }
      const replay = document.createElement("button");
      replay.type = "button";
      replay.className = "button-quiet";
      replay.textContent = "Bacakan lagi";
      replay.addEventListener("click", () => speak(question));
      actions.append(replay);
      row.append(text, actions);
      checkList.append(row);
    }
  };

  const render = () => {
    byId("session-summary").textContent = session
      ? `${session.participant_code}, kondisi ${session.condition_id}`
      : "Belum ada sesi aktif.";
    byId("session-state").textContent = session?.status?.replaceAll("_", " ").toLowerCase() || "Belum siap";
    consentFlow.hidden = !session || session.status !== "CONSENT";
    checkFlow.hidden = !session || session.status !== "CHECKS";
    taskFlow.hidden = !session || !["READY", "BETWEEN_TASKS", "TASK_ACTIVE"].includes(session.status);
    feedbackFlow.hidden = session?.status !== "FEEDBACK";
    if (session?.status === "CONSENT") renderConsent();
    if (session?.status === "CHECKS") renderChecks();
    if (session?.current_task) {
      byId("task-position").textContent = `Kegiatan ${session.task_index + 1} dari ${session.task_count}`;
      byId("task-label").textContent = session.current_task.label;
      byId("task-instruction").textContent = session.current_task.instruction;
      byId("open-task").hidden = session.status === "TASK_ACTIVE";
      byId("complete-task").hidden = session.status !== "TASK_ACTIVE";
    }
    renderEvents();
  };

  isMinor.addEventListener("change", () => {
    guardian.disabled = !isMinor.checked;
    if (!isMinor.checked) guardian.checked = false;
  });

  setup.addEventListener("submit", async (event) => {
    event.preventDefault();
    setupError.hidden = true;
    try {
      session = await api("/api/study/sessions", {
        participant_code: byId("participant-code").value,
        condition_id: byId("condition-id").value,
        is_minor: isMinor.checked,
        guardian_consent_confirmed: guardian.checked
      });
      setup.querySelectorAll("input, select, button").forEach((control) => { control.disabled = true; });
      render();
      speak(`Halo. Kegiatan ini bertujuan melihat apakah asisten dapat digunakan dengan mudah melalui suara. Tidak ada jawaban benar atau salah. Sebelum mulai, saya akan menanyakan beberapa persetujuan, satu per satu. ${consentQuestions[0][2]}`);
    } catch (error) {
      setupError.textContent = error.message;
      setupError.hidden = false;
    }
  });

  byId("read-instruction").addEventListener("click", async () => {
    if (!session?.current_task) return;
    speak(session.current_task.instruction);
    session = await api(`/api/study/sessions/${session.study_session_id}/events`, {
      kind: "TASK_INSTRUCTION_REPEAT",
      detail: "Instruksi dibacakan dari Researcher Console."
    });
    render();
  });

  byId("open-task").addEventListener("click", async () => {
    try {
      const result = await api(`/api/study/sessions/${session.study_session_id}/tasks/start`, {});
      session = result;
      taskNote.textContent = "Kegiatan dibuka. Peserta dapat berbicara tanpa menekan tombol.";
      window.open(result.start_url, "cua-participant");
      render();
    } catch (error) {
      taskNote.textContent = error.message;
    }
  });

  byId("complete-task").addEventListener("click", async () => {
    session = await api(`/api/study/sessions/${session.study_session_id}/tasks/complete`, { outcome: "RESEARCHER_CONFIRMED" });
    taskNote.textContent = session.status === "FEEDBACK" ? "Lanjutkan ke feedback singkat." : "Kegiatan berikutnya siap.";
    render();
    if (session.current_task) speak(session.current_task.instruction);
  });
})();
