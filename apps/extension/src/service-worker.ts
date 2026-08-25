chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
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
