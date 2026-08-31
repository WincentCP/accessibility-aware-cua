const LOCAL_PAGE = /^http:\/\/127\.0\.0\.1:(?:8000|8015)\//u;
let latestLiveRunId: string | null = null;
let coordinatorCreation: Promise<void> | null = null;

const isStudyPage = (url?: string): boolean => {
  if (!url || !LOCAL_PAGE.test(url)) return false;
  try {
    return new URL(url).searchParams.has("study_session_id");
  } catch {
    return false;
  }
};

const ensureStudyCoordinator = async (): Promise<void> => {
  if (await chrome.offscreen.hasDocument()) return;
  coordinatorCreation ??= chrome.offscreen.createDocument({
    url: "sidepanel.html",
    reasons: [chrome.offscreen.Reason.AUDIO_PLAYBACK],
    justification: "Menjalankan panduan suara penelitian tanpa membuka panel peserta."
  }).finally(() => { coordinatorCreation = null; });
  await coordinatorCreation;
};

const wakeStudyCoordinator = async (): Promise<void> => {
  await ensureStudyCoordinator();
  await chrome.runtime.sendMessage({ type: "COORDINATOR_LOAD_ACTIVE_TASK" });
};

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  if (isStudyPage(tab.url)) void wakeStudyCoordinator();
});

const studyShellTab = async (studySessionId: string): Promise<chrome.tabs.Tab> => {
  const tabs = await chrome.tabs.query({});
  const tab = tabs.find((item) => {
    if (!item.url || !LOCAL_PAGE.test(item.url)) return false;
    return new URL(item.url).searchParams.get("study_session_id") === studySessionId;
  });
  if (typeof tab?.id !== "number") throw new Error("Halaman penelitian tidak ditemukan.");
  return tab;
};

const loadTaskInStudyShell = async (studySessionId: string, taskUrl: string): Promise<void> => {
  const tab = await studyShellTab(studySessionId);
  const absoluteUrl = new URL(taskUrl, new URL(tab.url!).origin).href;
  await chrome.scripting.executeScript({
    target: { tabId: tab.id! },
    args: [absoluteUrl],
    func: async (nextUrl: string) => {
      const frame = document.querySelector<HTMLIFrameElement>("#study-task-frame");
      if (!frame) throw new Error("Area kegiatan tidak ditemukan.");
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error("Halaman kegiatan terlalu lama dimuat.")), 10_000);
        frame.addEventListener("load", () => {
          window.clearTimeout(timeout);
          resolve();
        }, { once: true });
        frame.hidden = false;
        frame.src = nextUrl;
      });
      const task = new URL(nextUrl);
      const shell = new URL(window.location.href);
      shell.searchParams.set("study_session_id", task.searchParams.get("study_session_id") ?? "");
      shell.searchParams.set("session_id", task.searchParams.get("session_id") ?? "");
      window.history.replaceState({}, "", shell);
      document.documentElement.dataset.taskUrl = nextUrl;
    }
  });
};

const activeBenchmarkTab = async (): Promise<{ tabId: number; sessionId: string; studySessionId?: string }> => {
  const tabs = await chrome.tabs.query({});
  const hasBenchmarkSession = (item: chrome.tabs.Tab): boolean => Boolean(
    item.url && LOCAL_PAGE.test(item.url) && new URL(item.url).searchParams.has("session_id")
  );
  const tab = tabs.find((item) => item.active && hasBenchmarkSession(item))
    ?? tabs.find((item) => item.url && LOCAL_PAGE.test(item.url) && new URL(item.url).searchParams.has("session_id"));
  if (typeof tab?.id !== "number" || !tab.url || !LOCAL_PAGE.test(tab.url)) {
    throw new Error("Buka halaman task benchmark terlebih dahulu.");
  }
  const taskUrl = new URL(tab.url);
  const sessionId = taskUrl.searchParams.get("session_id");
  if (!sessionId) throw new Error("Halaman belum memiliki session_id benchmark.");
  const studySessionId = taskUrl.searchParams.get("study_session_id") ?? undefined;
  return { tabId: tab.id, sessionId, studySessionId };
};

const apiJson = async (path: string, init?: RequestInit): Promise<Record<string, unknown>> => {
  const response = await fetch(`http://127.0.0.1:8000${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) }
  });
  const payload = await response.json() as Record<string, unknown>;
  if (!response.ok) throw new Error(String(payload.detail ?? `API ${response.status}`));
  return payload;
};

chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (!message || typeof message !== "object") return false;
  const payload = message as {
    type?: string;
    goal?: string;
    runId?: string;
    command?: string;
    transcript?: string;
    studySessionId?: string;
    taskUrl?: string;
  };
  if (payload.type === "GET_ACTIVE_TASK") {
    void activeBenchmarkTab().then(async ({ sessionId, studySessionId }) => {
      const session = await apiJson(`/api/benchmark/sessions/${sessionId}`);
      const task = session.task as { id?: string; goal?: string } | undefined;
      if (!task?.id || !task.goal) throw new Error("Tujuan task publik tidak tersedia.");
      const study = studySessionId
        ? await apiJson(`/api/study/sessions/${studySessionId}`)
        : null;
      const currentTask = study?.current_task as { instruction?: string } | undefined;
      sendResponse({
        success: true,
        task: {
          session_id: sessionId,
          task_id: task.id,
          ...(studySessionId ? {
            study_session_id: studySessionId,
            instruction: currentTask?.instruction,
            task_index: study?.task_index,
            task_count: study?.task_count,
            participant_name: study?.participant_name
          } : { goal: task.goal })
        }
      });
    }).catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "READ_CURRENT_PAGE") {
    void activeBenchmarkTab().then(async ({ tabId }) => {
      const results = await chrome.scripting.executeScript({
        target: { tabId, allFrames: true },
        func: () => {
          const normalize = (value: string | null | undefined): string =>
            String(value ?? "").replace(/\s+/gu, " ").trim();
          const headings = Array.from(document.querySelectorAll<HTMLElement>("main h1, main h2"))
            .map((element) => normalize(element.innerText))
            .filter(Boolean)
            .slice(0, 4);
          const controls = Array.from(document.querySelectorAll<HTMLElement>(
            "main label, main button, main [role='option'], main select option"
          )).map((element) => normalize(element.innerText || element.textContent))
            .filter((value, index, values) => Boolean(value) && values.indexOf(value) === index)
            .slice(0, 12);
          return { url: window.location.href, title: normalize(document.title), headings, controls };
        }
      });
      const result = results.find((item) => item.result?.url?.includes("session_id="))
        ?? results.find((item) => item.result?.controls?.length);
      sendResponse({ success: true, page: result?.result ?? { headings: [], controls: [] } });
    }).catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "STUDY_ONBOARDING_READY" && payload.studySessionId) {
    void ensureStudyCoordinator()
      .then(() => chrome.runtime.sendMessage({
        type: "COORDINATOR_START_ONBOARDING",
        studySessionId: payload.studySessionId
      }))
      .then(() => sendResponse({ success: true }))
      .catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "LOAD_STUDY_TASK" && payload.studySessionId && payload.taskUrl) {
    void loadTaskInStudyShell(payload.studySessionId, payload.taskUrl)
      .then(() => wakeStudyCoordinator())
      .then(() => sendResponse({ success: true }))
      .catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "COMPLETE_AND_START_NEXT_STUDY_TASK") {
    void activeBenchmarkTab().then(async ({ studySessionId }) => {
      if (!studySessionId) throw new Error("Sesi penelitian tidak ditemukan.");
      const completed = await apiJson(`/api/study/sessions/${studySessionId}/tasks/complete`, {
        method: "POST",
        body: JSON.stringify({ outcome: "AGENT_VERIFIED" })
      });
      if (completed.status === "COMPLETED") {
        sendResponse({ success: true, completed: true, session: completed });
        return;
      }
      if (completed.status === "FEEDBACK") {
        sendResponse({ success: true, completed: false, feedback: true, session: completed });
        return;
      }
      const next = await apiJson(`/api/study/sessions/${studySessionId}/tasks/start`, {
        method: "POST",
        body: "{}"
      });
      await loadTaskInStudyShell(studySessionId, String(next.start_url));
      sendResponse({ success: true, completed: false, session: next });
    }).catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "START_LIVE_AGENT") {
    void activeBenchmarkTab().then(async ({ sessionId }) => apiJson("/api/agent/runs", {
      method: "POST",
      body: JSON.stringify({ benchmark_session_id: sessionId, ...(payload.goal ? { goal: payload.goal } : {}) })
    })).then((result) => {
      latestLiveRunId = String(result.run_id);
      sendResponse({ success: true, run: result });
    })
      .catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "GET_LIVE_RUN" && payload.runId) {
    void apiJson(`/api/agent/runs/${payload.runId}`).then(async (result) => {
      const { tabId } = await activeBenchmarkTab();
      if (result.task_map) void chrome.tabs.sendMessage(tabId, { type: "UPDATE_TASK_MAP_BRIDGE", map: result.task_map });
      sendResponse({ success: true, run: result });
    }).catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "LIVE_COMMAND" && payload.runId && payload.command) {
    void apiJson(`/api/agent/runs/${payload.runId}/commands`, {
      method: "POST",
      body: JSON.stringify({ command: payload.command, ...(payload.transcript ? { transcript: payload.transcript } : {}) })
    }).then((result) => sendResponse({ success: true, run: result }))
      .catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  if (payload.type === "SHARED_CONTROL" && payload.command) {
    if (!latestLiveRunId) {
      sendResponse({ success: false, error: "Belum ada live run aktif." });
      return false;
    }
    void apiJson(`/api/agent/runs/${latestLiveRunId}/commands`, {
      method: "POST",
      body: JSON.stringify({ command: payload.command })
    }).then((result) => sendResponse({ success: true, run: result }))
      .catch((error) => sendResponse({ success: false, error: String(error.message ?? error) }));
    return true;
  }
  return false;
});
