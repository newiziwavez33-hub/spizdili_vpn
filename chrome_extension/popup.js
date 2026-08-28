/**
 * SPIZDILI_VPN Popup Controller
 * Manages user interface, proxy toggling, raccoon animations, and IP checking.
 */

const SERVERS = {
  local: {
    scheme: "socks5",
    host: "127.0.0.1",
    port: 10808,
    name: "🦝 Локальный туннель SPIZDILI (127.0.0.1:10808)"
  },
  fi1: {
    scheme: "socks5",
    host: "31.77.202.252",
    port: 10808,
    name: "🇫🇮 Финляндия • Облако #1 (cloudflare.com)"
  },
  se: {
    scheme: "socks5",
    host: "84.32.106.178",
    port: 10808,
    name: "🇸🇪 Швеция • Облако #2 (yandex.net)"
  },
  fi2: {
    scheme: "socks5",
    host: "31.77.202.252",
    port: 20532,
    name: "🇫🇮 Финляндия • Облако #3 (cloudflare.com)"
  },
  nl: {
    scheme: "socks5",
    host: "50.7.240.210",
    port: 10808,
    name: "🇳🇱 Нидерланды • Облако #4 (samsung.com)"
  },
  us1: {
    scheme: "socks5",
    host: "45.33.107.60",
    port: 10974,
    name: "🇺🇸 США • Облако #5 (intel.com)"
  },
  us2: {
    scheme: "socks5",
    host: "172.233.139.46",
    port: 53734,
    name: "🇺🇸 США • Облако #6 (tesla.com)"
  },
  us3: {
    scheme: "socks5",
    host: "192.155.87.188",
    port: 10092,
    name: "🇺🇸 США • Облако #7 (amd.com)"
  },
  us4: {
    scheme: "socks5",
    host: "172.236.252.35",
    port: 46645,
    name: "🇺🇸 США • Облако #8 (sony.com)"
  },
  sg: {
    scheme: "socks5",
    host: "54.169.200.246",
    port: 41688,
    name: "🇸🇬 Сингапур • Облако #9 (intel.com)"
  },
  kr: {
    scheme: "socks5",
    host: "43.108.86.165",
    port: 25636,
    name: "🇰🇷 Корея • Облако #10 (apple.com)"
  }
};

// ONLY VALID ASCII PUNYCODE - never put raw Cyrillic in rules.bypassList
const RU_BYPASS_DOMAINS = [
  "*.ru",
  "*.su",
  "*.xn--p1ai",
  "gosuslugi.ru",
  "*.gosuslugi.ru",
  "nalog.ru",
  "*.nalog.ru",
  "mos.ru",
  "*.mos.ru",
  "sberbank.ru",
  "*.sberbank.ru",
  "tinkoff.ru",
  "*.tinkoff.ru",
  "vtb.ru",
  "*.vtb.ru",
  "yandex.ru",
  "*.yandex.ru",
  "vk.com",
  "*.vk.com",
  "kinopoisk.ru",
  "*.kinopoisk.ru",
  "wildberries.ru",
  "*.wildberries.ru",
  "ozon.ru",
  "*.ozon.ru"
];

const DEFAULT_BYPASS = [
  "localhost",
  "127.0.0.1",
  "<local>",
  "*.local"
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

// Initialize state
document.addEventListener("DOMContentLoaded", async () => {
  chrome.runtime.sendMessage({ type: "GET_STATE" }, (response) => {
    if (response) {
      isConnected = !!response.connected;
      if (response.activeServer) {
        // Match active server
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

  // Load saved prefs
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
  statusSubtitle.textContent = "Установка безопасного туннеля…";

  const key = serverSelect.value || "local";
  const srv = SERVERS[key] || SERVERS.local;

  let bypass = [...DEFAULT_BYPASS];
  if (chkBypassRu.checked) {
    bypass = bypass.concat(RU_BYPASS_DOMAINS);
  }

  // Ensure pure ASCII
  const asciiBypass = bypass.filter(item => typeof item === "string" && /^[\x00-\x7F]+$/.test(item.trim()));

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
        statusTitle.textContent = "Ошибка подключения";
        statusSubtitle.textContent = (resp && resp.error) || "Не удалось включить прокси";
        mascotWrapper.classList.remove("active");
      }
    }
  );
}

// Disconnect logic
function handleDisconnect() {
  btnToggle.className = "power-btn";
  statusTitle.textContent = "Отключение…";

  chrome.runtime.sendMessage({ type: "DISCONNECT" }, () => {
    isConnected = false;
    updateUI(false);
  });
}

// Update UI presentation
function updateUI(connected) {
  if (connected) {
    btnToggle.className = "power-btn connected";
    statusTitle.textContent = "Защищено";
    const sName = (SERVERS[serverSelect.value] && SERVERS[serverSelect.value].name) || "Туннель";
    statusSubtitle.textContent = `Активен: ${sName}`;
    mascotWrapper.classList.add("active");
    networkInfo.classList.add("visible");
  } else {
    btnToggle.className = "power-btn";
    statusTitle.textContent = "Отключено";
    statusSubtitle.textContent = "Выберите сервер и нажмите для подключения";
    mascotWrapper.classList.remove("active");
    networkInfo.classList.remove("visible");
    extIp.textContent = "Определение…";
    extCountry.textContent = "—";
  }
}

// Check real external IP
async function fetchExternalIP() {
  extIp.textContent = "Запрос…";
  try {
    const res = await fetch("https://api.ipify.org?format=json");
    if (res.ok) {
      const data = await res.json();
      extIp.textContent = data.ip;

      // Query country
      try {
        const geoRes = await fetch(`http://ip-api.com/json/${data.ip}?fields=country,countryCode,city`);
        if (geoRes.ok) {
          const geo = await geoRes.json();
          extCountry.textContent = `${geo.country || ""} (${geo.city || ""})`;
        }
      } catch (e) {
        extCountry.textContent = "Защищено";
      }
    } else {
      extIp.textContent = "Скрыт";
    }
  } catch (e) {
    extIp.textContent = "Скрыт туннелем";
    extCountry.textContent = "Шифрование активно";
  }
}
