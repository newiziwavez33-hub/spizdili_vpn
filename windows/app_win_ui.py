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
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Any
from PIL import Image, ImageTk

from windows.win_proxy import WindowsProxyManager
from windows.xray_win import WindowsXrayManager, HTTP_PORT, SOCKS_PORT


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent.parent


class SpizdiliVPNWinApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SPIZDILI_VPN (v 1.0.3)")
        self.root.geometry("480x680")
        self.root.minsize(400, 580)
        self.root.configure(bg="#1e1e2e")

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

        # Dark theme colors
        self.style.configure(".", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        self.style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        self.style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#89b4fa")
        self.style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#a6adc8")
        self.style.configure("Status.TLabel", font=("Segoe UI", 14, "bold"), foreground="#a6adc8")
        self.style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), foreground="#ffffff")
        self.style.configure("Ver.TLabel", font=("Segoe UI", 10, "bold"), foreground="#89b4fa")
        self.style.configure("Metric.TLabel", font=("Segoe UI", 10), foreground="#a6adc8")
        self.style.configure("MetricVal.TLabel", font=("Segoe UI", 10, "bold"), foreground="#cdd6f4")

        # Buttons
        self.style.configure(
            "Connect.TButton",
            font=("Segoe UI", 12, "bold"),
            background="#a6e3a1",
            foreground="#11111b",
            padding=10,
            borderwidth=0
        )
        self.style.map("Connect.TButton", background=[("active", "#94e2d5")])

        self.style.configure(
            "Disconnect.TButton",
            font=("Segoe UI", 12, "bold"),
            background="#f38ba8",
            foreground="#11111b",
            padding=10,
            borderwidth=0
        )
        self.style.map("Disconnect.TButton", background=[("active", "#eba0ac")])

        self.style.configure("TCombobox", fieldbackground="#313244", background="#45475a", foreground="#cdd6f4")

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)

        # ── Header Title & Version ──────────────────────────────────────
        hdr_frame = ttk.Frame(container)
        hdr_frame.pack(fill="x", pady=(0, 10))

        lbl_title = ttk.Label(hdr_frame, text="SPIZDILI_VPN", style="Header.TLabel", anchor="center")
        lbl_title.pack()

        lbl_ver = ttk.Label(hdr_frame, text="v 1.0.3  •  Windows Edition", style="Ver.TLabel", anchor="center")
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
                lbl_logo = tk.Label(container, image=self.logo_tk, bg="#1e1e2e")
                lbl_logo.pack(pady=(0, 10))
            except Exception:
                pass

        # ── Status ──────────────────────────────────────────────────────
        self.lbl_status = ttk.Label(container, text="⚪ Отключено", style="Status.TLabel", anchor="center")
        self.lbl_status.pack(pady=(0, 5))

        self.lbl_subtitle = ttk.Label(container, text="Выберите сервер и нажмите «Подключить»", style="Sub.TLabel", anchor="center")
        self.lbl_subtitle.pack(pady=(0, 15))

        # ── Server Selector ─────────────────────────────────────────────
        sel_frame = ttk.LabelFrame(container, text="  Выбор локации (37 серверов)  ", padding=10)
        sel_frame.pack(fill="x", pady=(0, 15))

        server_names = [s.get("name", f"Server {i+1}") for i, s in enumerate(self.servers)]
        if not server_names:
            server_names = ["🇪🇺 ⚡️ Авто | Самый быстрый", "🇳🇱 🎮 Нидерланды", "🇩🇪 Германия"]

        self.server_var = tk.StringVar(value=server_names[0])
        self.combo_server = ttk.Combobox(sel_frame, textvariable=self.server_var, values=server_names, state="readonly", font=("Segoe UI", 10))
        self.combo_server.pack(fill="x", pady=5)

        # ── Main Connect / Disconnect Button ────────────────────────────
        self.btn_action = ttk.Button(container, text="⚡ Подключить", style="Connect.TButton", command=self._toggle_connection)
        self.btn_action.pack(fill="x", ipady=4, pady=(0, 15))

        # ── Connection Metrics Card ─────────────────────────────────────
        self.card_frame = ttk.LabelFrame(container, text="  Параметры соединения  ", padding=10)
        self.card_frame.pack(fill="x", pady=(0, 15))

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
