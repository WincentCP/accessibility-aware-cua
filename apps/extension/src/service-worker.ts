chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

const LOCAL_PAGE = /^http:\/\/127\.0\.0\.1:(?:8000|8015)\//u;
let latestLiveRunId: string | null = null;

const ensureInPageLauncher = async (tabId: number, url?: string): Promise<void> => {
  if (url && !LOCAL_PAGE.test(url)) return;
  try {
    await chrome.tabs.sendMessage(tabId, { type: "ENSURE_IN_PAGE_PANEL" });
  } catch {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content-script.js"] });
    } catch {
      // Non-benchmark and browser-internal pages are intentionally ignored.
    }
  }
};

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") void ensureInPageLauncher(tabId, tab.url);
});

const activeBenchmarkTab = async (): Promise<{ tabId: number; sessionId: string }> => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (typeof tab?.id !== "number" || !tab.url || !LOCAL_PAGE.test(tab.url)) {
    throw new Error("Buka halaman task benchmark terlebih dahulu.");
  }
  const sessionId = new URL(tab.url).searchParams.get("session_id");
  if (!sessionId) throw new Error("Halaman belum memiliki session_id benchmark.");
  return { tabId: tab.id, sessionId };
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

chrome.runtime.onMessage.addListener((message: unknown, sender, sendResponse) => {
  if (!message || typeof message !== "object") return false;
  const payload = message as { type?: string; goal?: string; runId?: string; command?: string };
  if (payload.type === "GET_ACTIVE_TASK") {
    void activeBenchmarkTab().then(async ({ sessionId }) => {
      const session = await apiJson(`/api/benchmark/sessions/${sessionId}`);
      const task = session.task as { id?: string; goal?: string } | undefined;
      if (!task?.id || !task.goal) throw new Error("Tujuan task publik tidak tersedia.");
      sendResponse({
        success: true,
        task: { session_id: sessionId, task_id: task.id, goal: task.goal }
      });
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
      body: JSON.stringify({ command: payload.command })
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
  if (payload.type !== "OPEN_SIDE_PANEL") return false;
  const windowId = sender.tab?.windowId;
  if (typeof windowId !== "number") {
    sendResponse({ success: false, error: "WINDOW_NOT_FOUND" });
    return false;
  }
  void chrome.sidePanel.open({ windowId }).then(
    () => sendResponse({ success: true }),
    () => sendResponse({ success: false, error: "OPEN_FAILED" })
  );
  return true;
});
