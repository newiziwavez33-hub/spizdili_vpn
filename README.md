<p align="center">
  <img src="icons/spizdili-logo.png" width="220" alt="SPIZDILI_VPN Logo" />
</p>

<h1 align="center">🦝 SPIZDILI_VPN (v1.2.0)</h1>

<p align="center">
  <b>Современный, автономный и быстрый VPN-клиент для Windows 7/8/10/11 и Linux</b><br>
  <i>Прямое подключение без подписок и логинов • VLESS Reality (XTLS Vision) • WireGuard • AmneziaWG • Оптимизация для AI IDE</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-7%20%7C%208%20%7C%2010%20%7C%2011-0078D6?style=flat-square&logo=windows" alt="Windows" />
  <img src="https://img.shields.io/badge/Linux-Ubuntu%20%7C%20Debian%20%7C%20Arch%20%7C%20Fedora-E95420?style=flat-square&logo=ubuntu" alt="Linux" />
  <img src="https://img.shields.io/badge/Version-v1.2.0-blue?style=flat-square" alt="Version" />
  <img src="https://img.shields.io/badge/Servers-51%20Nodes-success?style=flat-square" alt="Servers" />
  <img src="https://img.shields.io/badge/Protocols-VLESS%20Reality%20%7C%20WireGuard%20%7C%20AWG-purple?style=flat-square" alt="Protocols" />
  <img src="https://img.shields.io/badge/AI%20Optimized-Antigravity%20%7C%20Gemini%20%7C%20Claude%20%7C%20ChatGPT-brightgreen?style=flat-square" alt="AI Optimized" />
  <img src="https://img.shields.io/badge/License-GPL--3.0-green?style=flat-square" alt="License" />
</p>

---

## 🪟 Запуск на Windows 7 / 8 / 10 / 11 (Без установки)

Версия для Windows собрана в виде **автономного `.exe` файла**, работающего «из коробки» на любой версии Windows (7 SP1, 8.1, 10, 11):

1. Перейдите во вкладку **[Releases](https://github.com/newiziwavez33-hub/spizdili_vpn/releases/latest)**.
2. Скачайте **`SPIZDILI_VPN.exe`** (или `SPIZDILI_VPN_v1.2.0_Windows_x64.zip`).
3. Запустите `SPIZDILI_VPN.exe` — приложение готово к работе сразу со всеми 51 серверами, автоподключением к самому быстрому Облаку и AI-оптимизацией!

---

## 🐧 Установка на Linux (Ubuntu / Debian / Astra / Mint / Fedora / Arch)

### Способ 1: Установка готового DEB пакета (Рекомендуется)
Скачайте **`spizdili-vpn_1.2.0_amd64.deb`** из [последнего релиза](https://github.com/newiziwavez33-hub/spizdili_vpn/releases/latest) и установите:
```bash
sudo dpkg -i spizdili-vpn_1.2.0_amd64.deb
```

### Способ 2: Установка из исходного кода
```bash
git clone https://github.com/newiziwavez33-hub/spizdili_vpn.git
cd spizdili_vpn
sudo ./install.sh
```

---

---

## 🌐 Расширение для Google Chrome (Chrome Extension)

В репозиторий добавлено официальное расширение для браузеров **Google Chrome**, **Chromium**, **Yandex Browser**, **Brave** и **Edge**:

### 📥 Установка плагина в Chrome:
1. Скачайте архив **`spizdili_vpn_chrome_extension.zip`** из [Releases](https://github.com/newiziwavez33-hub/spizdili_vpn/releases/latest) и распакуйте в любую папку.
2. В браузере перейдите по адресу `chrome://extensions/` и включите переключатель **«Режим разработчика»** (Developer mode) в правом верхнем углу.
3. Нажмите **«Загрузить распакованное расширение»** (Load unpacked) и укажите распакованную папку `chrome_extension`.
4. Закрепите значок **SPIZDILI_VPN** с енотом на панели расширений!

### 🌟 Возможности расширения:
- 🦝 **Интерфейс с маскотом-енотом:** анимированный статус-круг, Catppuccin Mocha тёмная тема.
- ⚡ **Двойной режим работы:**
  - *Прямое браузерное проксирование:* скоростные проверенные ноды (Финляндия, Швеция, Германия, Нидерланды, США).
  - *Связка с десктопным клиентом:* 1 клик для перенаправления веб-трафика через локальный туннель `127.0.0.1:10808` (VLESS Reality).
- 🛡️ **Умный обход блокировок:** встроенный тумблер исключения для российских сервисов (`.ru`, Госуслуги, банки) без потери скорости.
- 🌍 **Автоматическое определение внешнего IP и страны подключения.**

## 🌟 Ключевые возможности версии 1.0.5

- ⚡ **Автоподключение к самому быстрому серверу «Облако 1–6» при старте:**
  - При запуске приложение за 1 секунду проверяет отклик европейских и американских серверов **«Облако» (с 1 по 6)**.
  - Находит ноду с минимальной задержкой и **автоматически подключается к ней**, избавляя от ручного выбора!
- 🌐 **База из 51 скоростного сервера без подписок:**
  - **14 проверенных нод VLESS Reality** (Швеция, Германия, Нидерланды, США, Сингапур, Корея) со сквозной валидацией реальным трафиком.
  - **37 выделенных европейских серверов** с протоколами VLESS Reality, WireGuard и AmneziaWG.
  - Никаких триалов, логинов, паролей или абонентской платы.
- 🔄 **Широкое и адаптивное окно обновления:**
  - Окно обновления стало в 2 раза шире (720px) и полностью адаптируется под любой экран.
  - Встроен интерактивный индикатор прогресса (ProgressBar) со шкалой процентов и кнопкой мгновенного перезапуска после установки.
  - Раздел «Настройки» теперь отображает текущую установленную версию с динамическим обновлением.
- 📱 **Мгновенная синхронизация профилей:**
  - Выбор сервера в списке «Профили» сразу обновляет селектор на главной вкладке, отображает флаг страны и переключает на экран подключения.
- 🤖 **Специальная оптимизация для AI IDE и разработчиков:**
  - Безупречная работа с **Google Antigravity 2.11**, **Google Gemini**, **ChatGPT**, **Anthropic Claude**, **GitHub Copilot**, **OpenCode** и **Cursor**.
  - Защита длинных потоковых сессий (gRPC / Server-Sent Events / SSE): буфер 64 КБ, `connIdle: 900s`, TCP Keep-Alive (`15s`), отключение Nagle (`tcpNoDelay: true`).
  - Приоритетный DoH (DNS-over-HTTPS) с принудительным `UseIPv4` для мгновенного резолва доменов OpenAI, Anthropic и Google Cloud.
- 🛡️ **Поддержка передовых протоколов:**
  - **VLESS Reality (XTLS-rprx-vision):** маскировка под доверенные ресурсы (`yandex.net`, `cloudflare.com`, `samsung.com`, `x5.ru`, `intel.com`), полная устойчивость к блокировкам провайдеров.
  - **AmneziaWG (AWG):** обфускация заголовков WireGuard (Jc/Jmin/Jmax/S1/S2/H1/H2).
  - **WireGuard:** классический сверхбыстрый туннель.
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

## 🗂️ Список встроенных серверов (51 локация)

| № | Флаг и Страна | Протокол | Маскировка / Хост | Назначение |
|---|---|---|---|---|
| 1 | 🇸🇪 Швеция (Облако #1) | VLESS Reality | `sw.api-yandex.net` (282ms) | Сверхбыстрый, P2P, AI |
| 2 | 🇩🇪 Германия (Облако #2) | VLESS Reality | `www.cloudflare.com` (343ms) | Веб-серфинг, Streaming |
| 3 | 🇳🇱 Нидерланды (Облако #3) | VLESS Reality | `ads.x5.ru` (358ms) | Стабильный, AI IDE |
| 4 | 🇩🇪 Германия (Облако #4) | VLESS Reality | `www.cloudflare.com` (382ms) | Резервный маршрут |
| 5 | 🇳🇱 Нидерланды (Облако #5) | VLESS Reality | `www.samsung.com` (441ms) | Низкий пинг, Media |
| 6 | 🇺🇸 США (Облако #6) | VLESS Reality | `www.intel.com` (861ms) | Доступ к сервисам США |
| 7 | 🇺🇸 США (Облако #7) | VLESS Reality | `www.amd.com` (874ms) | Разработка, AI APIs |
| 8 | 🇺🇸 США (Облако #8) | VLESS Reality | `www.sony.com` (1012ms) | CDN США |
| 9 | 🇺🇸 США (Облако #9) | VLESS Reality | `www.tesla.com` (1041ms) | Защита от блокировок |
| 10 | 🇸🇬 Сингапур (Облако #10) | VLESS Reality | `www.nvidia.com` (1462ms) | Азиатский шлюз |
| 11 | 🇸🇬 Сингапур (Облако #11) | VLESS Reality | `www.nvidia.com` (1476ms) | Резервный азиатский |
| 12 | 🇸🇬 Сингапур (Облако #12) | VLESS Reality | `www.intel.com` (1485ms) | Сверхнадежный |
| 13 | 🇸🇬 Сингапур (Облако #13) | VLESS Reality | `www.amd.com` (2042ms) | Дальний восток |
| 14 | 🇰🇷 Корея (Облако #14) | VLESS Reality | `www.apple.com` (2052ms) | Прямой азиатский |
| 15–51 | 🇪🇺 Европа (37 серверов) | VLESS / AWG / WG | Финляндия, Германия, Нидерланды и др. | Базовый европейский пул |

---

## 🛠️ Сборка из исходников

### Сборка `.deb` пакета для Linux:
```bash
dpkg-deb --root-owner-group -b package_dir spizdili-vpn_1.2.0_amd64.deb
```

### Сборка standalone `.exe` для Windows (PyInstaller):
```bash
python windows/build_exe.py
# Создает dist/SPIZDILI_VPN.exe и dist/SPIZDILI_VPN_v1.2.0_Windows_x64.zip
```
