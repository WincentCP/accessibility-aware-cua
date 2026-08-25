chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

const LOCAL_PAGE = /^http:\/\/127\.0\.0\.1:(?:8000|8015)\//u;

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

chrome.runtime.onMessage.addListener((message: unknown, sender, sendResponse) => {
  if (!message || typeof message !== "object" || (message as { type?: string }).type !== "OPEN_SIDE_PANEL") {
    return false;
  }
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
