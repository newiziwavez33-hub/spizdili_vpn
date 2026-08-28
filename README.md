<p align="center">
  <img src="icons/spizdili-logo.png" width="220" alt="SPIZDILI_VPN Logo" />
</p>

<h1 align="center">🦝 SPIZDILI_VPN (v1.0.3)</h1>

<p align="center">
  <b>Современный, автономный и быстрый VPN-клиент для Windows 7/8/10/11 и Linux</b><br>
  <i>Прямое подключение без подписок и логинов • VLESS Reality (XTLS Vision) • WireGuard • AmneziaWG • Оптимизация для AI IDE</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-7%20%7C%208%20%7C%2010%20%7C%2011-0078D6?style=flat-square&logo=windows" alt="Windows" />
  <img src="https://img.shields.io/badge/Linux-Ubuntu%20%7C%20Debian%20%7C%20Arch%20%7C%20Fedora-E95420?style=flat-square&logo=ubuntu" alt="Linux" />
  <img src="https://img.shields.io/badge/GUI-Native%20Dark%20%2B%20GTK4-blue?style=flat-square" alt="GUI" />
  <img src="https://img.shields.io/badge/Protocols-VLESS%20Reality%20%7C%20WireGuard%20%7C%20AWG-purple?style=flat-square" alt="Protocols" />
  <img src="https://img.shields.io/badge/AI%20Optimized-Antigravity%20%7C%20Gemini%20%7C%20Claude%20%7C%20ChatGPT-brightgreen?style=flat-square" alt="AI Optimized" />
  <img src="https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square" alt="License" />
</p>

---

## 🪟 Запуск на Windows 7 / 8 / 10 / 11 (Без установки)

Версия для Windows собрана в виде **портативного `.exe` файла**, работающего «из коробки» на любой версии Windows (7 SP1, 8.1, 10, 11):

1. Перейдите во вкладку **[Releases](https://github.com/newiziwavez33-hub/spizdili_vpn/releases)**.
2. Скачайте **`SPIZDILI_VPN.exe`** (или `SPIZDILI_VPN-v1.0.3-Windows-x64.zip`).
3. Запустите `SPIZDILI_VPN.exe` — приложение готово к работе сразу со всеми 37 серверами и AI-оптимизацией!

---

## 🐧 Установка на Linux (Ubuntu / Debian / Pop!_OS / Fedora / Arch)

```bash
# Клонируйте репозиторий
git clone https://github.com/newiziwavez33-hub/spizdili_vpn.git
cd spizdili_vpn

# Запустите автономную установку
sudo ./install.sh
```

---

## 🌟 Ключевые возможности

- 🚀 **100% Автономность без подписок:**
  - Никаких внешних сервисов авторизации, триалов, логинов или паролей.
  - Встроена база из **37 европейских и мировых серверов** с прямым шифрованным подключением.
- 🤖 **Специальная оптимизация для AI IDE и разработчиков:**
  - Безупречная работа с **Google Antigravity 2.11**, **Google Gemini**, **ChatGPT**, **Anthropic Claude**, **GitHub Copilot**, **OpenCode** и **Cursor**.
  - Защита длинных потоковых сессий (gRPC / Server-Sent Events / SSE): буфер 64 КБ, `connIdle: 900s`, TCP Keep-Alive (`15s`), отключение Nagle (`tcpNoDelay: true`).
  - Приоритетный DoH (DNS-over-HTTPS) с принудительным `UseIPv4` для мгновенного резолва доменов OpenAI, Anthropic и Google Cloud.
- 🛡️ **Поддержка передовых протоколов:**
  - **VLESS Reality (XTLS-rprx-vision):** маскировка под доверенные HTTPS-ресурсы, полная устойчивость к блокировкам провайдеров.
  - **AmneziaWG (AWG):** обфускация заголовков WireGuard (Jc/Jmin/Jmax/S1/S2/H1/H2).
  - **Стандартный WireGuard:** классический сверхбыстрый туннель.
- 💻 **Глобальная маршрутизация через ядро Linux (TUN):**
  - Создание виртуального адаптера `tun_wavez` с MTU 1400 и автоматической таблицей маршрутизации `51820`.
  - Все приложения системы (браузеры, терминал, IDE, Docker, cURL) защищены туннелем.
  - Полная интеграция с PolicyKit — подключение в 1 клик **без постоянных запросов sudo пароля**.
- 📊 **Живая аналитика трафика и качества сети:**
  - Реальные счетчики **«↓ Загрузка»** и **«↑ Отдача»**, считываемые напрямую из ядра Linux (`/sys/class/net/`).
  - Отображение пинга до сервера с цветовой индикацией (🟢 <100ms, 🟡 100-250ms, 🔴 >250ms).
  - Определение внешнего IP-адреса и таймер активного соединения.
- 🔍 **Умный поиск и сортировка серверов:**
  - Мгновенный живой поиск по странам, флагам, IP и протоколам.
  - Кнопка «Сортировать по пингу» для быстрого выбора самого скоростного сервера.
- 🇷🇺 **Мультиязычный интерфейс (100% Русский / English):**
  - Переключение языка «на лету» во вкладке настроек.
- 🎛️ **Системный трей:**
  - Индикатор статуса и меню быстрого подключения через AyatanaAppIndicator3.

---

## 📦 Быстрая установка «из коробки»

Установщик полностью автономен. На чистой системе выполните:

```bash
# Клонируйте репозиторий
git clone https://github.com/newiziwavez33-hub/spizdili_vpn.git
cd spizdili_vpn

# Запустите автономную установку
sudo ./install.sh
```

Скрипт автоматически:
1. Установит необходимые зависимости (`GTK4`, `Libadwaita`, `wireguard-tools`, `xray-core`, `python3-gi`).
2. Настроит права ядра `CAP_NET_ADMIN` для сетевого туннеля.
3. Развернет базу из 37 серверов и оптимальные конфигурации.
4. Установит квадратную системную иконку и ярлык в меню приложений.

---

## 🚀 Запуск

- **Из меню приложений:** найдите ярлык **`SPIZDILI_VPN`** 🦝
- **Из терминала:**
  ```bash
  spizdili-vpn
  # или
  wavez-vpn-client
  ```

---

## 📂 Структура проекта

```
spizdili_vpn/
├── app_ui.py                 # GTK4 + Libadwaita графический интерфейс
├── main.py                   # Точка входа, жизненный цикл и обработка сигналов
├── vpn_manager.py            # Управление туннелями, сетевыми счетчиками и DNS
├── xray_manager.py           # Движок VLESS Reality, маршрутизация и DoH
├── settings_manager.py       # Менеджер настроек (JSON)
├── incy_importer.py          # Парсер и генератор профилей серверов
├── subscription_parser.py    # Поддержка импорта ссылок (vless://, wg://, awg://)
├── health_checker.py         # Диагностика и замер задержки серверов
├── tray_subprocess.py        # Изолированный процесс системного трея (GTK3)
├── vpn-helper                # Привилегированный хелпер маршрутизации ядра
├── wavez_servers.json        # Встроенная база 37 автономных серверов
├── install.sh                # Комплексный скрипт установки/удаления
├── icons/                    # Квадратные и векторные иконки приложения
└── com.wavez.vpnclient.*     # Файлы Polkit и .desktop
```

---

## 🛠️ Диагностика и удаление

- **Проверка состояния системы и зависимостей:**
  ```bash
  sudo ./install.sh --check
  ```
- **Полное чистое удаление:**
  ```bash
  sudo ./install.sh --uninstall
  ```

---

## 📄 Лицензия

Распространяется под лицензией [GPL-3.0 License](LICENSE).
