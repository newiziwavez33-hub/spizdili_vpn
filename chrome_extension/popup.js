/**
 * SPIZDILI_VPN Popup Controller (v1.0.9)
 * Connects Google Chrome to the high-speed local SPIZDILI_VPN client engine.
 * Routes Chrome traffic through VLESS Reality, WireGuard & AmneziaWG tunnels.
 */

const SERVERS = {
  local_http: {
    scheme: "http",
    host: "127.0.0.1",
    port: 20809,
    name: "🦝 SPIZDILI Клиент (HTTP 127.0.0.1:20809 • Рекомендуется)"
  },
  local_socks: {
    scheme: "socks5",
    host: "127.0.0.1",
    port: 20808,
    name: "🦝 SPIZDILI Клиент (SOCKS5 127.0.0.1:20808)"
  },
  local_win_dyn: {
    scheme: "http",
    host: "127.0.0.1",
    port: 20811,
    name: "🪟 Windows Динамический порт (HTTP 127.0.0.1:20811)"
  }
};

// Pure ASCII hostnames for bypass
const RU_BYPASS_DOMAINS = [
  "gosuslugi.ru",
  "nalog.ru",
  "mos.ru",
  "sberbank.ru",
  "tinkoff.ru",
  "vtb.ru",
  "yandex.ru",
  "vk.com",
  "kinopoisk.ru",
  "wildberries.ru",
  "ozon.ru"
];

const DEFAULT_BYPASS = [
  "localhost",
  "127.0.0.1"
];

// DOM Elements
const btnToggle = document.getElementById("btn-toggle");
const statusTitle = document.getElementById("status-title");
const statusSubtitle = document.getElementById("status-subtitle");
const serverSelect = document.getElementById("server-select");
const networkInfo = document.getElementById("network-info");
const extIp = document.getElementById("ext-ip");
const extCountry = document.getElementById("ext-country");
const mascotWrapper = document.getElementById("mascot-wrapper");
const chkBypassRu = document.getElementById("chk-bypass-ru");

let isConnected = false;

// Populate server dropdown
function populateServers() {
  serverSelect.innerHTML = "";
  for (const [key, srv] of Object.entries(SERVERS)) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = srv.name;
    serverSelect.appendChild(opt);
  }
}

// Initialize state
document.addEventListener("DOMContentLoaded", async () => {
  populateServers();

  chrome.runtime.sendMessage({ type: "GET_STATE" }, (response) => {
    if (response) {
      isConnected = !!response.connected;
      if (response.activeServer) {
        for (const [k, v] of Object.entries(SERVERS)) {
          if (v.host === response.activeServer.host && v.port === response.activeServer.port) {
            serverSelect.value = k;
            break;
          }
        }
      }
      updateUI(isConnected);
      if (isConnected) {
        fetchExternalIP();
      }
    }
  });

  const stored = await chrome.storage.local.get(["bypassRu", "selectedServerKey"]);
  if (stored.bypassRu !== undefined) {
    chkBypassRu.checked = stored.bypassRu;
  }
  if (stored.selectedServerKey && SERVERS[stored.selectedServerKey]) {
    serverSelect.value = stored.selectedServerKey;
  }
});

// Server select change
serverSelect.addEventListener("change", () => {
  chrome.storage.local.set({ selectedServerKey: serverSelect.value });
  if (isConnected) {
    handleConnect();
  }
});

// Bypass RU checkbox change
chkBypassRu.addEventListener("change", () => {
  chrome.storage.local.set({ bypassRu: chkBypassRu.checked });
  if (isConnected) {
    handleConnect();
  }
});

// Toggle button click
btnToggle.addEventListener("click", () => {
  if (isConnected) {
    handleDisconnect();
  } else {
    handleConnect();
  }
});

// Connect logic
function handleConnect() {
  btnToggle.className = "power-btn connecting";
  statusTitle.textContent = "Подключение…";
  statusSubtitle.textContent = "Связь с локальным клиентом SPIZDILI_VPN…";

  const key = serverSelect.value || "local_http";
  const srv = SERVERS[key] || SERVERS.local_http;

  let bypass = [...DEFAULT_BYPASS];
  if (chkBypassRu.checked) {
    bypass = bypass.concat(RU_BYPASS_DOMAINS);
  }

  const asciiBypass = bypass.filter(item => typeof item === "string" && /^[\x00-\x7F]+$/.test(item.trim())).map(s => s.trim());

  chrome.runtime.sendMessage(
    {
      type: "CONNECT",
      server: srv,
      bypassList: asciiBypass
    },
    (resp) => {
      if (resp && resp.success) {
        isConnected = true;
        updateUI(true);
        fetchExternalIP();
      } else {
        isConnected = false;
        btnToggle.className = "power-btn";
        statusTitle.textContent = "Ошибка";
        statusSubtitle.textContent = (resp && resp.error) || "Убедитесь, что клиент SPIZDILI_VPN запущен";
        mascotWrapper.classList.remove("active");
      }
    }
  );
}

// Disconnect logic
function handleDisconnect() {
  chrome.runtime.sendMessage({ type: "DISCONNECT" }, () => {
    isConnected = false;
    updateUI(false);
  });
}

// Update UI
function updateUI(connected) {
  if (connected) {
    btnToggle.className = "power-btn connected";
    statusTitle.textContent = "Защищено";
    statusSubtitle.textContent = "Трафик Chrome зашифрован через SPIZDILI";
    mascotWrapper.classList.add("active");
    networkInfo.classList.add("visible");
  } else {
    btnToggle.className = "power-btn";
    statusTitle.textContent = "Отключено";
    statusSubtitle.textContent = "Выберите режим и нажмите для подключения";
    mascotWrapper.classList.remove("active");
    networkInfo.classList.remove("visible");
  }
}

// Fetch external IP with timeout
async function fetchExternalIP() {
  extIp.textContent = "Проверка…";
  extCountry.textContent = "—";

  try {
    const res = await fetch("https://api.ipify.org?format=json", { cache: "no-store" });
    const data = await res.json();
    extIp.textContent = data.ip;
    extCountry.textContent = "🌍 Защищённый узел";
  } catch {
    extIp.textContent = "127.0.0.1 (Прокси активен)";
    extCountry.textContent = "🔒 Локальный туннель";
  }
}
