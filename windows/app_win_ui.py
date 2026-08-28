"""
SPIZDILI_VPN v1.0.3 — Modern Native Windows GUI
Built with pure Python Tkinter / TTK + PIL for 100% Out-of-the-Box Windows 7/8/10/11 compatibility.
Zero complex runtime dependencies, native dark theme, raccoon mascot, 37 servers, and AI IDE tuning.
"""

import sys
import os
import json
import time
import threading
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Any
from PIL import Image, ImageTk

try:
    from version import __version__ as APP_VERSION, GITHUB_REPO_URL
except ImportError:
    try:
        from ..version import __version__ as APP_VERSION, GITHUB_REPO_URL
    except Exception:
        APP_VERSION = "1.0.3"
        GITHUB_REPO_URL = "https://github.com/newiziwavez33-hub/spizdili_vpn"

try:
    from updater import default_updater, UpdateInfo, is_newer_version
except ImportError:
    try:
        from ..updater import default_updater, UpdateInfo, is_newer_version
    except Exception:
        default_updater = None
        UpdateInfo = None
        is_newer_version = lambda a, b: False

try:
    from windows.win_proxy import WindowsProxyManager
    from windows.xray_win import WindowsXrayManager, HTTP_PORT, SOCKS_PORT
except ImportError:
    try:
        from win_proxy import WindowsProxyManager
        from xray_win import WindowsXrayManager, HTTP_PORT, SOCKS_PORT
    except ImportError:
        pass


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent.parent


class SpizdiliVPNWinApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"SPIZDILI_VPN (v {APP_VERSION})")
        self.root.geometry("480x680")
        self.root.minsize(400, 580)
        self.root.configure(bg="#141226")

        self.base_dir = get_base_dir()
        self.xray = WindowsXrayManager(self.base_dir)

        # Set Window Icon
        ico_candidates = [
            self.base_dir / "icons" / "spizdili-vpn.ico",
            self.base_dir / "icons" / "spizdili-vpn.png",
        ]
        for ic in ico_candidates:
            if ic.is_file():
                try:
                    if ic.suffix == ".ico":
                        self.root.iconbitmap(str(ic))
                    break
                except Exception:
                    pass

        # Load 37 servers database
        self.servers = self._load_servers()

        # State
        self.connected = False
        self.connecting = False
        self.active_server_name = ""
        self.connect_time = None
        self.ping_val = None
        self.ext_ip = None

        self._setup_styles()
        self._build_ui()
        self._start_background_timers()
        self.root.after(1000, self._auto_select_fastest_cloud)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_servers(self) -> list[dict[str, Any]]:
        candidates = [
            self.base_dir / "wavez_servers.json",
            Path(sys.executable).parent / "wavez_servers.json",
        ]
        for c in candidates:
            if c.is_file():
                try:
                    data = json.loads(c.read_text(encoding="utf-8"))
                    return data.get("servers", [])
                except Exception:
                    pass
        return []

    def _setup_styles(self) -> None:
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # AetherVPN Deep Violet Theme Colors
        self.style.configure(".", background="#141226", foreground="#f1f5f9", font=("Segoe UI", 10))
        self.style.configure("TLabel", background="#141226", foreground="#f1f5f9")
        self.style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#38bdf8")
        self.style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#94a3b8")
        self.style.configure("Status.TLabel", font=("Segoe UI", 15, "bold"), foreground="#94a3b8")
        self.style.configure("Header.TLabel", font=("Segoe UI", 19, "bold"), foreground="#ffffff")
        self.style.configure("Ver.TLabel", font=("Segoe UI", 10, "bold"), foreground="#818cf8")
        self.style.configure("Metric.TLabel", font=("Segoe UI", 10), foreground="#94a3b8")
        self.style.configure("MetricVal.TLabel", font=("Segoe UI", 10, "bold"), foreground="#f1f5f9")

        # Buttons
        self.style.configure(
            "Connect.TButton",
            font=("Segoe UI", 13, "bold"),
            background="#00d2ff",
            foreground="#0b1329",
            padding=12,
            borderwidth=0
        )
        self.style.map("Connect.TButton", background=[("active", "#38ef7d")])

        self.style.configure(
            "Disconnect.TButton",
            font=("Segoe UI", 13, "bold"),
            background="#f43f5e",
            foreground="#ffffff",
            padding=12,
            borderwidth=0
        )
        self.style.map("Disconnect.TButton", background=[("active", "#e11d48")])

        self.style.configure(
            "Update.TButton",
            font=("Segoe UI", 9, "bold"),
            background="#89b4fa",
            foreground="#11111b",
            padding=6,
            borderwidth=0,
        )
        self.style.map("Update.TButton", background=[("active", "#b4befe")])

        self.style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            background="#313244",
            foreground="#cdd6f4",
            padding=6,
            borderwidth=0,
        )
        self.style.map("Secondary.TButton", background=[("active", "#45475a")])

        self.style.configure("TCombobox", fieldbackground="#313244", background="#45475a", foreground="#cdd6f4")

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)

        # ── Header Title & Version ──────────────────────────────────────
        hdr_frame = ttk.Frame(container)
        hdr_frame.pack(fill="x", pady=(0, 10))

        lbl_title = ttk.Label(hdr_frame, text="SPIZDILI_VPN", style="Header.TLabel", anchor="center")
        lbl_title.pack()

        lbl_ver = ttk.Label(hdr_frame, text=f"v {APP_VERSION}  •  Windows Edition", style="Ver.TLabel", anchor="center")
        lbl_ver.pack()

        # ── Mascot Image ────────────────────────────────────────────────
        logo_path = self.base_dir / "icons" / "spizdili-logo.png"
        if not logo_path.is_file():
            logo_path = self.base_dir / "icons" / "spizdili-vpn.png"

        if logo_path.is_file():
            try:
                pil_img = Image.open(logo_path).convert("RGBA")
                pil_img = pil_img.resize((140, 140), Image.Resampling.LANCZOS)
                self.logo_tk = ImageTk.PhotoImage(pil_img)
                lbl_logo = tk.Label(container, image=self.logo_tk, bg="#141226")
                lbl_logo.pack(pady=(0, 10))
            except Exception:
                pass

        # ── Status ──────────────────────────────────────────────────────
        self.lbl_status = ttk.Label(container, text="⚪ Отключено", style="Status.TLabel", anchor="center")
        self.lbl_status.pack(pady=(0, 5))

        self.lbl_subtitle = ttk.Label(container, text="Выберите сервер и нажмите «Подключить»", style="Sub.TLabel", anchor="center")
        self.lbl_subtitle.pack(pady=(0, 15))

        # ── Server Selector ─────────────────────────────────────────────
        sel_frame = ttk.LabelFrame(container, text=f"  Выбор локации ({len(self.servers)} серверов)  ", padding=10)
        sel_frame.pack(fill="x", pady=(0, 15))

        server_names = [s.get("name", f"Server {i+1}") for i, s in enumerate(self.servers)]
        if not server_names:
            server_names = ["🇪🇺 ⚡️ Авто | Самый быстрый", "🇳🇱 🎮 Нидерланды", "🇩🇪 Германия"]

        self.server_var = tk.StringVar(value=server_names[0])
        self.combo_server = ttk.Combobox(sel_frame, textvariable=self.server_var, values=server_names, state="readonly", font=("Segoe UI", 10))
        self.combo_server.pack(fill="x", pady=5)

        self.btn_cloud_fetch = ttk.Button(sel_frame, text="🌐 Загрузить свежие серверы из сети", style="Secondary.TButton", command=self._on_fetch_cloud_servers)
        self.btn_cloud_fetch.pack(fill="x", pady=(4, 0))

        # ── Main Connect / Disconnect Button ────────────────────
        self.btn_action = ttk.Button(container, text="⚡ Подключить", style="Connect.TButton", command=self._toggle_connection)
        self.btn_action.pack(fill="x", ipady=4, pady=(0, 15))

        # ── Connection Metrics Card ─────────────────────────────────────
        self.card_frame = ttk.LabelFrame(container, text="  Параметры соединения  ", padding=10)
        self.card_frame.pack(fill="x", pady=(0, 12))

        # Grid metrics
        ttk.Label(self.card_frame, text="Внешний IP:", style="Metric.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.lbl_ip_val = ttk.Label(self.card_frame, text="—", style="MetricVal.TLabel")
        self.lbl_ip_val.grid(row=0, column=1, sticky="e", pady=3)

        ttk.Label(self.card_frame, text="Пинг:", style="Metric.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        self.lbl_ping_val = ttk.Label(self.card_frame, text="—", style="MetricVal.TLabel")
        self.lbl_ping_val.grid(row=1, column=1, sticky="e", pady=3)

        ttk.Label(self.card_frame, text="Время работы:", style="Metric.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        self.lbl_uptime_val = ttk.Label(self.card_frame, text="00:00:00", style="MetricVal.TLabel")
        self.lbl_uptime_val.grid(row=2, column=1, sticky="e", pady=3)

        self.card_frame.columnconfigure(0, weight=1)
        self.card_frame.columnconfigure(1, weight=1)

        # ── Updates & Releases Card ─────────────────────────────────────
        upd_frame = ttk.LabelFrame(container, text="  Обновления программы  ", padding=10)
        upd_frame.pack(fill="x", pady=(0, 10))
        upd_frame.columnconfigure(0, weight=1)
        upd_frame.columnconfigure(1, weight=1)

        self.lbl_update_ver = ttk.Label(upd_frame, text=f"Версия: v{APP_VERSION}", style="Metric.TLabel")
        self.lbl_update_ver.grid(row=0, column=0, sticky="w", pady=2)

        self.btn_check_update = ttk.Button(
            upd_frame,
            text="🔄 Проверить",
            style="Secondary.TButton",
            command=lambda: self._check_updates_async(manual=True)
        )
        self.btn_check_update.grid(row=0, column=1, sticky="e", pady=2)

        self.lbl_update_status = ttk.Label(upd_frame, text="", style="Sub.TLabel")
        self.lbl_update_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))

        # ── AI IDE Optimization Badge ───────────────────────────────────
        ai_frame = ttk.Frame(container)
        ai_frame.pack(fill="x", pady=(0, 5))
        lbl_ai = ttk.Label(
            ai_frame,
            text="🤖 AI IDE Оптимизация: Активна (Google Antigravity, Gemini, ChatGPT, Claude, OpenCode)",
            font=("Segoe UI", 8, "italic"),
            foreground="#a6e3a1",
            anchor="center"
        )
        lbl_ai.pack()

    def _toggle_connection(self) -> None:
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        if self.connecting:
            return
        self.connecting = True
        self.lbl_status.config(text="🟡 Подключение…", foreground="#f9e2af")
        self.btn_action.config(text="Подключение…", state="disabled")

        selected_name = self.server_var.get()
        target_server = None
        for s in self.servers:
            if s.get("name") == selected_name:
                target_server = s
                break
        if not target_server and self.servers:
            target_server = self.servers[0]

        def worker() -> None:
            ok, msg = self.xray.start(target_server or {})
            if ok:
                WindowsProxyManager.enable_proxy("127.0.0.1", HTTP_PORT, SOCKS_PORT)
                self.root.after(0, self._on_connected_ui, selected_name)
            else:
                self.root.after(0, self._on_connect_failed, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_connected_ui(self, server_name: str) -> None:
        self.connected = True
        self.connecting = False
        self.active_server_name = server_name
        self.connect_time = time.time()

        self.lbl_status.config(text="🟢 Подключено", foreground="#a6e3a1")
        self.lbl_subtitle.config(text=f"Защищено: {server_name}")
        self.btn_action.config(text="🔴 Отключить", style="Disconnect.TButton", state="normal")

        # Fetch IP and Ping
        self._fetch_network_diagnostics()

    def _on_connect_failed(self, error_msg: str) -> None:
        self.connected = False
        self.connecting = False
        self.lbl_status.config(text="🔴 Ошибка", foreground="#f38ba8")
        self.lbl_subtitle.config(text=error_msg)
        self.btn_action.config(text="⚡ Подключить", style="Connect.TButton", state="normal")
        messagebox.showerror("Ошибка подключения", f"Не удалось запустить Xray туннель:\n{error_msg}")

    def _disconnect(self) -> None:
        self.lbl_status.config(text="🟡 Отключение…", foreground="#f9e2af")
        self.btn_action.config(state="disabled")

        def worker() -> None:
            WindowsProxyManager.disable_proxy()
            self.xray.stop()
            self.root.after(0, self._on_disconnected_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _on_disconnected_ui(self) -> None:
        self.connected = False
        self.connecting = False
        self.connect_time = None
        self.lbl_status.config(text="⚪ Отключено", foreground="#a6adc8")
        self.lbl_subtitle.config(text="Выберите сервер и нажмите «Подключить»")
        self.btn_action.config(text="⚡ Подключить", style="Connect.TButton", state="normal")

        self.lbl_ip_val.config(text="—")
        self.lbl_ping_val.config(text="—")
        self.lbl_uptime_val.config(text="00:00:00")

    def _fetch_network_diagnostics(self) -> None:
        def worker() -> None:
            # External IP
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{HTTP_PORT}", "https": f"http://127.0.0.1:{HTTP_PORT}"}))
                req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "curl/7.88.1"})
                with opener.open(req, timeout=4) as resp:
                    ip = resp.read().decode("utf-8").strip()
                    self.root.after(0, lambda: self.lbl_ip_val.config(text=ip))
            except Exception:
                pass

            # Ping
            try:
                t0 = time.time()
                req = urllib.request.Request("https://www.gstatic.com/generate_204", headers={"User-Agent": "Mozilla/5.0"})
                with opener.open(req, timeout=4) as resp:
                    rtt = int((time.time() - t0) * 1000)
                    self.root.after(0, lambda: self.lbl_ping_val.config(text=f"{rtt} мс"))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _start_background_timers(self) -> None:
        def update_uptime() -> None:
            if self.connected and self.connect_time:
                elapsed = int(time.time() - self.connect_time)
                h = elapsed // 3600
                m = (elapsed % 3600) // 60
                s = elapsed % 60
                self.lbl_uptime_val.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.root.after(1000, update_uptime)

        self.root.after(1000, update_uptime)
        self.root.after(2200, self._auto_check_updates_startup)

    def _auto_check_updates_startup(self) -> None:
        self._check_updates_async(manual=False)

    def _check_updates_async(self, manual: bool = False) -> None:
        if default_updater is None:
            if manual:
                messagebox.showinfo("Обновление", "Модуль обновления недоступен.")
            return

        if manual:
            self.lbl_update_status.configure(text="⏳ Проверка обновлений на GitHub...", foreground="#a6adc8")

        def _worker():
            try:
                info = default_updater.check_for_updates()
            except Exception:
                info = None
            self.root.after(0, lambda: self._on_update_check_result(info, manual))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_update_check_result(self, info: Optional[Any], manual: bool) -> None:
        if info is None:
            self.lbl_update_status.configure(text="Не удалось проверить обновления", foreground="#f38ba8")
            if manual:
                messagebox.showwarning("Обновление", "Не удалось связаться с сервером GitHub Releases.")
            return

        if info.has_update:
            self.lbl_update_status.configure(
                text=f"🎉 Доступна новая версия: v{info.latest_version}!",
                foreground="#89b4fa"
            )
            self._show_update_modal(info)
        else:
            self.lbl_update_status.configure(
                text=f"✓ У вас установлена актуальная версия (v{APP_VERSION})",
                foreground="#a6e3a1"
            )
            if manual:
                messagebox.showinfo("Обновление", f"У вас установлена последняя версия SPIZDILI_VPN (v{APP_VERSION}).")

    def _show_update_modal(self, info: Any) -> None:
        modal = tk.Toplevel(self.root)
        modal.title(f"Обновление SPIZDILI_VPN v{info.latest_version}")
        modal.geometry("480x440")
        modal.minsize(420, 380)
        modal.configure(bg="#141226")
        modal.transient(self.root)
        modal.grab_set()

        try:
            ico_path = self.base_dir / "icons" / "spizdili-vpn.ico"
            if ico_path.is_file():
                modal.iconbitmap(str(ico_path))
        except Exception:
            pass

        frame = ttk.Frame(modal, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        title_lbl = ttk.Label(
            frame,
            text=f"🎉 Доступна версия v{info.latest_version}!",
            style="Header.TLabel",
            anchor="center",
            font=("Segoe UI", 13, "bold"),
        )
        title_lbl.pack(fill="x", pady=(0, 4))

        sub_txt = f"Текущая версия: v{APP_VERSION}"
        if getattr(info, "published_at", None):
            sub_txt += f" • Выпущено: {info.published_at[:10]}"
        sub_lbl = ttk.Label(frame, text=sub_txt, style="Sub.TLabel", anchor="center")
        sub_lbl.pack(fill="x", pady=(0, 10))

        # Changelog / Notes Box
        notes_frame = ttk.LabelFrame(frame, text="  Что нового  ", padding=8)
        notes_frame.pack(fill="both", expand=True, pady=(0, 10))

        txt = tk.Text(
            notes_frame,
            bg="#313244",
            fg="#cdd6f4",
            insertbackground="#89b4fa",
            relief="flat",
            wrap="word",
            font=("Segoe UI", 9),
            height=7,
        )
        txt.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=txt.yview)
        scroll.pack(side="right", fill="y")
        txt.configure(yscrollcommand=scroll.set)

        notes_body = info.release_notes or info.title or "Официальный релиз клиента."
        txt.insert("1.0", notes_body)
        txt.configure(state="disabled")

        # Progress / Status
        status_lbl = ttk.Label(frame, text="", style="Sub.TLabel", anchor="center")
        status_lbl.pack(fill="x", pady=(0, 4))

        prog_bar = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        prog_bar.pack(fill="x", pady=(0, 10))
        prog_bar.pack_forget()

        # Action Buttons
        btn_box = ttk.Frame(frame)
        btn_box.pack(fill="x", pady=(4, 0))
        btn_box.columnconfigure(0, weight=1)
        btn_box.columnconfigure(1, weight=1)

        def _on_start_download():
            btn_dl.configure(state="disabled", text="⏳ Скачивание...")
            prog_bar.pack(fill="x", pady=(0, 10))
            status_lbl.configure(text="Подключение к GitHub...")

            def _dl_task():
                exe_url = info.exe_asset_url or info.zip_asset_url
                if not exe_url:
                    for a in getattr(info, "all_assets", []):
                        aname = a.get("name", "").lower()
                        if aname.endswith(".exe") or aname.endswith(".zip"):
                            exe_url = a.get("browser_download_url")
                            break

                if not exe_url:
                    modal.after(0, lambda: status_lbl.configure(text="EXE файл не найден в релизе. Откройте GitHub."))
                    modal.after(0, lambda: btn_dl.configure(state="normal", text="⚡ Скачать и обновить"))
                    return

                temp_dir = Path(os.environ.get("TEMP", tempfile.gettempdir()))
                dest_file = temp_dir / (info.exe_asset_name or f"SPIZDILI_VPN_v{info.latest_version}.exe")

                def _prog(dl, tot):
                    if tot > 0:
                        pct = int((dl / tot) * 100)
                        mb_dl = dl / (1024 * 1024)
                        mb_tot = tot / (1024 * 1024)
                        modal.after(0, lambda: prog_bar.configure(value=pct))
                        modal.after(0, lambda: status_lbl.configure(text=f"Скачано: {mb_dl:.1f} / {mb_tot:.1f} MB ({pct}%)"))

                ok = default_updater.download_file(exe_url, dest_file, progress_cb=_prog)
                if not ok:
                    modal.after(0, lambda: status_lbl.configure(text="❌ Ошибка скачивания."))
                    modal.after(0, lambda: btn_dl.configure(state="normal", text="⚡ Скачать и обновить"))
                    return

                modal.after(0, lambda: status_lbl.configure(text="Применение обновления..."))
                ok_app, app_msg = default_updater.apply_windows_update(dest_file)
                if ok_app:
                    modal.after(0, lambda: status_lbl.configure(text="✓ Обновление применено! Перезапуск..."))
                    time.sleep(1.2)
                    self.root.destroy()
                    sys.exit(0)
                else:
                    modal.after(0, lambda: status_lbl.configure(text=f"Ошибка: {app_msg}"))
                    modal.after(0, lambda: btn_dl.configure(state="normal", text="⚡ Скачать и обновить"))

            threading.Thread(target=_dl_task, daemon=True).start()

        btn_dl = ttk.Button(btn_box, text="⚡ Скачать и обновить", style="Update.TButton", command=_on_start_download)
        btn_dl.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        def _open_gh():
            webbrowser.open(info.release_url or GITHUB_REPO_URL)

        btn_gh = ttk.Button(btn_box, text="🌐 На GitHub", style="Secondary.TButton", command=_open_gh)
        btn_gh.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _on_fetch_cloud_servers(self) -> None:
        self.btn_cloud_fetch.configure(state="disabled", text="⏳ Поиск и замер задержки...")
        self.lbl_subtitle.configure(text="Загрузка свежих серверов VLESS Reality из сети...")

        def _task():
            try:
                import reality_fetcher
                servers = reality_fetcher.fetch_and_test_reality_servers(max_servers=25)
                if servers:
                    reality_fetcher.save_servers_to_system(servers)
                    self.servers = servers + self.servers
                    names = [s.get("name", f"Server {i+1}") for i, s in enumerate(self.servers)]

                    def _update_ui():
                        self.combo_server.configure(values=names)
                        self.server_var.set(names[0])
                        self.lbl_subtitle.configure(text=f"✓ Добавлено {len(servers)} серверов Reality!")
                        self.btn_cloud_fetch.configure(state="normal", text="🌐 Загрузить свежие серверы из сети")

                    self.root.after(0, _update_ui)
                else:
                    self.root.after(0, lambda: self.btn_cloud_fetch.configure(state="normal", text="🌐 Загрузить свежие серверы из сети"))
            except Exception as exc:
                self.root.after(0, lambda: self.lbl_subtitle.configure(text=f"Ошибка: {exc}"))
                self.root.after(0, lambda: self.btn_cloud_fetch.configure(state="normal", text="🌐 Загрузить свежие серверы из сети"))

        threading.Thread(target=_task, daemon=True).start()

    def _auto_select_fastest_cloud(self) -> None:
        def _worker():
            cloud_servers = [s for s in self.servers if s.get("ascii_name", "").startswith("Cloud-")][:6]
            if not cloud_servers:
                return
            best_server = None
            best_ping = 999999.0
            for s in cloud_servers:
                addr = s.get("address")
                port = s.get("port", 443)
                try:
                    import socket, time
                    t0 = time.perf_counter()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1.2)
                    sock.connect((addr, int(port)))
                    sock.close()
                    lat = (time.perf_counter() - t0) * 1000
                    if lat < best_ping:
                        best_ping = lat
                        best_server = s
                except Exception:
                    pass
            if best_server:
                def _apply():
                    if not self.connected and not self.connecting:
                        name = best_server.get("name", "")
                        self.server_var.set(name)
                        self.lbl_subtitle.configure(text=f"⚡ Самый быстрый: {name} ({int(best_ping)} ms) — подключаем!")
                        self._toggle_connection()
                self.root.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_close(self) -> None:
        if self.connected:
            if messagebox.askyesno("Выход", "VPN соединение активно. Отключить и выйти?"):
                WindowsProxyManager.disable_proxy()
                self.xray.stop()
                self.root.destroy()
        else:
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = SpizdiliVPNWinApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
