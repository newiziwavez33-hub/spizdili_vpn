<p align="center">
  <img src="icons/spizdili-logo.png" width="220" alt="SPIZDILI_VPN Logo" />
</p>

<h1 align="center">🦝 SPIZDILI_VPN (v1.2.6)</h1>

<p align="center">
  <b>Современный, автономный и быстрый VPN-клиент нового поколения для Windows и Linux</b><br>
  <i>Прямое подключение без подписок и логинов • Модальный аудит и отсев серверов • VLESS Reality (XTLS Vision) • Личный Cloudflare WARP Anycast • WireGuard & AmneziaWG • Ускорение YouTube 4K • Оптимизация для AI IDE</i>
</p>

<p align="center">
  <img src="docs/spizdili_vpn_dashboard_preview.png" width="760" alt="SPIZDILI_VPN Modern Studio Dashboard Interface" style="border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-7%20%7C%208%20%7C%2010%20%7C%2011-0078D6?style=flat-square&logo=windows" alt="Windows" />
  <img src="https://img.shields.io/badge/Linux-Ubuntu%20%7C%20Debian%20%7C%20Arch%20%7C%20Fedora%20%7C%20Astra-E95420?style=flat-square&logo=ubuntu" alt="Linux" />
  <img src="https://img.shields.io/badge/Version-v1.2.6-blue?style=flat-square" alt="Version" />
  <img src="https://img.shields.io/badge/Servers-Auto--Cleaned-success?style=flat-square" alt="Servers" />
  <img src="https://img.shields.io/badge/Protocols-VLESS%20Reality%20%7C%20Cloudflare%20WARP%20%7C%20WireGuard%20%7C%20AWG-purple?style=flat-square" alt="Protocols" />
  <img src="https://img.shields.io/badge/AI%20Optimized-Antigravity%20%7C%20Gemini%20%7C%20Claude%20%7C%20ChatGPT-brightgreen?style=flat-square" alt="AI Optimized" />
  <img src="https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square" alt="License" />
</p>

---

## 🪟 Запуск на Windows 7 / 8 / 10 / 11 (Без установки)

Версия для Windows собрана в виде **автономного `.exe` файла**, работающего «из коробки» на любой версии Windows:

1. Перейдите во вкладку **[Releases](https://github.com/newiziwavez33-hub/spizdili_vpn/releases/latest)**.
2. Скачайте **`SPIZDILI_VPN.exe`** (или `SPIZDILI_VPN_v1.2.6_Windows_x64.zip`).
3. Запустите `SPIZDILI_VPN.exe` — всё готово к работе сразу со всеми серверами, автоподключением к скоростным узлам и AI-оптимизацией!

---

## 🐧 Установка на Linux (Ubuntu / Debian / Astra / Mint / Fedora / Arch)

### Способ 1: Установка готового DEB пакета (Рекомендуется)
Скачайте **`spizdili-vpn_1.2.6_amd64.deb`** из [последнего релиза](https://github.com/newiziwavez33-hub/spizdili_vpn/releases/latest) и установите:
```bash
sudo dpkg -i spizdili-vpn_1.2.6_amd64.deb
```

### Способ 2: Установка из исходного кода
```bash
git clone https://github.com/newiziwavez33-hub/spizdili_vpn.git
cd spizdili_vpn
sudo ./install.sh
```

---

## 🌐 Расширение для Google Chrome (Chrome Extension)

В репозиторий добавлено официальное расширение для браузеров **Google Chrome**, **Chromium**, **Yandex Browser**, **Brave** и **Edge**:

### 📥 Установка плагина в Chrome:
1. Скачайте архив **`spizdili_vpn_chrome_extension.zip`** из [Releases](https://github.com/newiziwavez33-hub/spizdili_vpn/releases/latest) и распакуйте в любую папку.
2. В браузере перейдите по адресу `chrome://extensions/` и включите переключатель **«Режим разработчика»** (Developer mode) в правом верхнем углу.
3. Нажмите **«Загрузить распакованное расширение»** (Load unpacked) и укажите распакованную папку `chrome_extension`.
4. Закрепите значок **SPIZDILI_VPN** с енотом на панели расширений!

---

## 🌟 Ключевые возможности версии v1.2.6

### 📡 1. Детальная проверка и автоматический отсев мёртвых серверов
- **Модальное окно с показометром (ProgressBar) при запуске:**
  - При каждом старте приложения открывается интерактивное окно глубокого аудита.
  - Проводится параллельная TLS/TCP-проверка отклика узлов сети с измерением времени задержки.
  - **Все неработающие, недоступные и заблокированные узлы автоматически отсекаются и полностью удаляются из списков и файлов конфигурации!**
  - Подключение автоматически устанавливается к наилучшему доступному серверу.
- **Гарантированный доступ к ключевым сервисам:**
  - 🎬 **YouTube 4K & Google Video** (без буферизации и троттлинга).
  - 🔍 **Яндекс и российские ресурсы** (прямой доступ без блокировок).
  - 🤖 **AI IDE & API:** Google Antigravity, Gemini, ChatGPT, Claude, Cursor, Copilot.

### 🛡️ 2. Cloudflare WARP Anycast с регистрацией через VPN-шлюз
- Регистрация ключа через активный локальный прокси (`127.0.0.1:10808`), обходя блокировку `api.cloudflareclient.com` в РФ.
- Пул устойчивых чистых IP Anycast (`162.159.193.x`, `162.159.192.x`, `188.114.9x.x`) с портами `2408`, `1701`, `500`, `4500`.
- Наглядная индикация на дашборде: **«🛡️ Cloudflare WARP • АКТИВЕН»**.

### 🎨 3. Studio Dashboard & Круговой спидометр Cairo
- Тёмная стеклянная тема Glassmorphism, анимированная круглая кнопка питания со статусом и световыми эффектами.
- Круговой неоновый тахометр 0–200 Мбит/с с интерполяцией 60 FPS.

---

## 🛠️ Сборка из исходников

### Сборка `.deb` пакета для Linux:
```bash
dpkg-deb --root-owner-group -b package_dir spizdili-vpn_1.2.6_amd64.deb
```

### Сборка standalone `.exe` для Windows (PyInstaller):
```bash
python windows/build_exe.py
# Создает dist/SPIZDILI_VPN.exe и dist/SPIZDILI_VPN_v1.2.6_Windows_x64.zip
```
