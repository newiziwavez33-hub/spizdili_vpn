/**
 * SPIZDILI_VPN Background Service Worker (Manifest V3)
 * Manages chrome.proxy settings, badge states, and persistence.
 */

const DEFAULT_BYPASS = [
  "localhost",
  "127.0.0.1",
  "<local>",
  "*.local"
];

// Initialize on install
chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get(["connected", "bypassList"]);
  if (!data.bypassList) {
    await chrome.storage.local.set({ bypassList: DEFAULT_BYPASS });
  }
  if (data.connected) {
    updateBadge(true);
  } else {
    updateBadge(false);
  }
});

// Update extension icon badge
function updateBadge(connected) {
  if (connected) {
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#2ec27e" });
  } else {
    chrome.action.setBadgeText({ text: "" });
  }
}

// Apply proxy settings
async function applyProxy(server, customBypass = null) {
  const data = await chrome.storage.local.get(["bypassList"]);
  const bypass = customBypass || data.bypassList || DEFAULT_BYPASS;

  const scheme = (server.scheme || "socks5").toLowerCase();
  const host = server.host || "127.0.0.1";
  const port = parseInt(server.port, 10) || 10808;

  const config = {
    mode: "fixed_servers",
    rules: {
      singleProxy: {
        scheme: scheme,
        host: host,
        port: port
      },
      bypassList: bypass
    }
  };

  return new Promise((resolve, reject) => {
    chrome.proxy.settings.set({ value: config, scope: "regular" }, () => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError);
      } else {
        updateBadge(true);
        chrome.storage.local.set({ connected: true, activeServer: server });
        resolve(true);
      }
    });
  });
}

// Clear proxy settings
async function clearProxy() {
  return new Promise((resolve) => {
    chrome.proxy.settings.clear({ scope: "regular" }, () => {
      updateBadge(false);
      chrome.storage.local.set({ connected: false });
      resolve(true);
    });
  });
}

// Message router from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CONNECT") {
    applyProxy(message.server, message.bypassList)
      .then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // Async response
  } else if (message.type === "DISCONNECT") {
    clearProxy()
      .then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  } else if (message.type === "GET_STATE") {
    chrome.storage.local.get(["connected", "activeServer", "bypassList"]).then((data) => {
      sendResponse(data);
    });
    return true;
  }
});
