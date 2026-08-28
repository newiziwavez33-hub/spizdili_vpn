/**
 * SPIZDILI_VPN Background Service Worker (Manifest V3)
 * Manages chrome.proxy settings, badge states, and persistence.
 * Features automatic self-healing fallback for proxy bypass rules.
 */

const DEFAULT_BYPASS = [
  "localhost",
  "127.0.0.1"
];

// Initialize on install / update
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.clear();
  await chrome.storage.local.set({ connected: false });
  updateBadge(false);
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

// Apply proxy settings with self-healing fallback
async function applyProxy(server, customBypass = null) {
  const scheme = (server.scheme || "socks5").toLowerCase();
  const host = server.host || "127.0.0.1";
  const port = parseInt(server.port, 10) || 10808;

  let safeBypass = ["localhost", "127.0.0.1"];
  if (Array.isArray(customBypass)) {
    // Strict ASCII filter (0-127 only)
    safeBypass = customBypass
      .filter(item => typeof item === "string" && /^[\x00-\x7F]+$/.test(item.trim()))
      .map(s => s.trim());
  }

  const trySetProxy = (bypass) => {
    return new Promise((resolve, reject) => {
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
      chrome.proxy.settings.set({ value: config, scope: "regular" }, () => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve();
        }
      });
    });
  };

  try {
    await trySetProxy(safeBypass);
  } catch (err) {
    console.warn("Primary proxy rule failed, attempting minimal bypass fallback:", err);
    // Bulletproof fallback: apply minimal localhost bypass
    await trySetProxy(["localhost", "127.0.0.1"]);
  }

  updateBadge(true);
  await chrome.storage.local.set({ connected: true, activeServer: server });
  return true;
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
      .catch((err) => {
        console.error("Proxy error:", err);
        sendResponse({ success: false, error: err.message || String(err) });
      });
    return true; // Async response
  } else if (message.type === "DISCONNECT") {
    clearProxy()
      .then(() => sendResponse({ success: true }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  } else if (message.type === "GET_STATE") {
    chrome.storage.local.get(["connected", "activeServer"]).then((data) => {
      sendResponse(data);
    });
    return true;
  }
});
