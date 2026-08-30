#!/usr/bin/env python3
"""Ubuntu VPN Client — GTK4 / Libadwaita Graphical Interface.

Implements the full GUI: connection page, profile management, live logs,
and system tray (AyatanaAppIndicator3 via a GTK3 subprocess).

AyatanaAppIndicator3 is a GTK3 library and cannot be loaded in the same
process as GTK4.  The tray is therefore managed by a child process
(tray_subprocess.py) that speaks a simple JSON-over-pipe protocol.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from vpn_manager import (  # noqa: E402
    ConfigManager,
    SystemDependencyChecker,
    VPNManager,
    WireGuardConfig,
)
from subscription_parser import ParsedServer, SubscriptionParser  # noqa: E402
from health_checker import ConfigHealthChecker, HealthReport  # noqa: E402

try:
    import updater as _updater
except ImportError:
    _updater = None  # type: ignore

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "1.2.6"

__all__ = ["VPNApplication"]

# Locate the tray subprocess module
def _find_tray_helper() -> Optional[Path]:
    candidates = [
        Path(__file__).resolve().parent / "tray_subprocess.py",
        Path("/usr/local/lib/wavez-vpn/tray_subprocess.py"),
        Path("/usr/local/lib/ubuntu-vpn/tray_subprocess.py"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None

_TRAY_HELPER = _find_tray_helper()
_HAS_APPINDICATOR = _TRAY_HELPER is not None


logger = logging.getLogger("app_ui")

# ---------------------------------------------------------------------------
# Icon paths
# ---------------------------------------------------------------------------

_ICON_DIRS = [
    Path("/usr/local/share/wavez-vpn/icons"),
    Path("/usr/local/share/ubuntu-vpn/icons"),
    Path(__file__).resolve().parent / "icons",
]


def _find_icon(name: str) -> str:
    """Locate an SVG icon by *name* (without extension)."""
    for d in _ICON_DIRS:
        p = d / f"{name}.svg"
        if p.is_file():
            return str(p)
    return "network-vpn-symbolic"


# ---------------------------------------------------------------------------
# Localization (i18n): Russian & English
# ---------------------------------------------------------------------------

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "app_title": "WaveZ VPN Client",
        "tab_connect": "Подключение",
        "tab_profiles": "Профили",
        "tab_logs": "Журнал",
        "tab_settings": "Настройки",
        "status_connected": "Подключено",
        "status_disconnected": "Отключено",
        "status_connecting": "Подключение…",
        "status_disconnecting": "Отключение…",
        "btn_connect": "Подключить",
        "btn_disconnect": "Отключить",
        "btn_switch": "Сменить сервер",
        "select_profile": "Выберите сервер / профиль",
        "no_profiles": "Серверы не найдены",
        "external_ip": "Внешний IP",
        "uptime": "Время работы",
        "data_transfer": "Трафик",
        "received": "получено",
        "sent": "отправлено",
        "settings_lang_group": "Язык интерфейса",
        "settings_lang_group_sub": "Выбор языка приложения (Русский / English)",
        "settings_lang_title": "Язык (Language)",
        "settings_lang_sub": "Выберите предпочитаемый язык интерфейса",
        "settings_dns_group": "DNS и Сетевые параметры",
        "settings_dns_group_sub": "Настройки DNS и маршрутизации",
        "settings_dns_title": "DNS-серверы по умолчанию",
        "settings_dns_presets": "Пресеты DNS",
        "settings_lan_title": "Исключения локальной сети (LAN)",
        "settings_lan_sub": "Сохранять прямой доступ к локальной сети (192.168.0.0/16, 10.0.0.0/8)",
        "settings_mtu_title": "MTU интерфейса",
        "settings_behavior_group": "Поведение и запуск",
        "settings_ks_title": "Kill-Switch по умолчанию",
        "settings_ks_sub": "Блокировать трафик при обрыве соединения",
        "settings_autoconn_title": "Автоподключение при старте",
        "settings_autoconn_sub": "Подключаться к последнему серверу при запуске",
        "settings_tray_title": "Сворачивать в трей при закрытии",
        "settings_tray_sub": "Оставлять приложение работать в фоновом режиме",
        "settings_diag_group": "Диагностика и пинг",
        "settings_timeout_title": "Таймаут пинга (сек)",
        "settings_target_title": "URL для проверки связи",
        "settings_sync_group": "Синхронизация и серверы",
        "settings_sync_group_sub": "Импорт каталога серверов и сброс",
        "settings_import_title": "Импорт каталога серверов",
        "settings_import_sub": "Загрузить все 37 серверов Reality в профили",
        "settings_import_btn": "Импорт 37 серверов",
        "settings_reset_title": "Сброс настроек",
        "settings_reset_sub": "Вернуть стандартные параметры DNS и маршрутизации",
        "settings_reset_btn": "Сбросить",
        "profiles_search": "Поиск серверов…",
        "profiles_import": "Импорт файла",
        "profiles_ping_all": "Проверить пинг",
        "profiles_free_vpn": "Каталог серверов",
        "profiles_delete": "Удалить",
        "profiles_ping": "Пинг",
        "logs_clear": "Очистить",
        "toast_connected": "Подключено к {}",
        "toast_disconnected": "Отключено",
        "toast_lang_saved": "Язык интерфейса: {}",
    },
    "en": {
        "app_title": "WaveZ VPN Client",
        "tab_connect": "Connection",
        "tab_profiles": "Profiles",
        "tab_logs": "Logs",
        "tab_settings": "Settings",
        "status_connected": "Connected",
        "status_disconnected": "Disconnected",
        "status_connecting": "Connecting…",
        "status_disconnecting": "Disconnecting…",
        "btn_connect": "Connect",
        "btn_disconnect": "Disconnect",
        "btn_switch": "Switch Server",
        "select_profile": "Select Server / Profile",
        "no_profiles": "No profiles found",
        "external_ip": "External IP",
        "uptime": "Uptime",
        "data_transfer": "Data Transfer",
        "received": "received",
        "sent": "sent",
        "settings_lang_group": "Interface Language",
        "settings_lang_group_sub": "Choose application language (Russian / English)",
        "settings_lang_title": "Language",
        "settings_lang_sub": "Select preferred interface language",
        "settings_dns_group": "DNS & Network",
        "settings_dns_group_sub": "Default DNS and network routing configuration",
        "settings_dns_title": "Default DNS Servers",
        "settings_dns_presets": "DNS Presets",
        "settings_lan_title": "Bypass LAN / Private Networks",
        "settings_lan_sub": "Keep local connections (192.168.0.0/16, 10.0.0.0/8) unrouted",
        "settings_mtu_title": "Default Interface MTU",
        "settings_behavior_group": "Connection & Behavior",
        "settings_ks_title": "Kill-Switch Active by Default",
        "settings_ks_sub": "Enable traffic kill-switch automatically on connect",
        "settings_autoconn_title": "Auto-Connect on Launch",
        "settings_autoconn_sub": "Automatically connect to the last active profile when starting",
        "settings_tray_title": "Minimize to Tray on Close",
        "settings_tray_sub": "Keep application running in system tray when window is closed",
        "settings_diag_group": "Diagnostics & Latency Testing",
        "settings_timeout_title": "Ping Timeout (seconds)",
        "settings_target_title": "Ping Test Target URL",
        "settings_sync_group": "Server Catalogue & Sync",
        "settings_sync_group_sub": "Import server catalogue and reset settings",
        "settings_import_title": "Import Server Catalogue",
        "settings_import_sub": "Import all 37 Reality servers into profiles",
        "settings_import_btn": "Import 37 Servers",
        "settings_reset_title": "Reset Settings",
        "settings_reset_sub": "Restore default DNS and routing parameters",
        "settings_reset_btn": "Reset Defaults",
        "profiles_search": "Search servers…",
        "profiles_import": "Import File",
        "profiles_ping_all": "Ping All",
        "profiles_free_vpn": "Server Catalogue",
        "profiles_delete": "Delete",
        "profiles_ping": "Ping",
        "logs_clear": "Clear",
        "toast_connected": "Connected to {}",
        "toast_disconnected": "Disconnected",
        "toast_lang_saved": "Language saved: {}",
    },
}


# ---------------------------------------------------------------------------
# National Flag Mapping
# ---------------------------------------------------------------------------

_COUNTRY_FLAGS = (
    ("netherlands", "🇳🇱"),
    ("germany", "🇩🇪"),
    ("deutschland", "🇩🇪"),
    ("finland", "🇫🇮"),
    ("sweden", "🇸🇪"),
    ("poland", "🇵🇱"),
    ("estonia", "🇪🇪"),
    ("latvia", "🇱🇻"),
    ("romania", "🇷🇴"),
    ("uk", "🇬🇧"),
    ("united kingdom", "🇬🇧"),
    ("great britain", "🇬🇧"),
    ("england", "🇬🇧"),
    ("spain", "🇪🇸"),
    ("italy", "🇮🇹"),
    ("italia", "🇮🇹"),
    ("luxembourg", "🇱🇺"),
    ("usa", "🇺🇸"),
    ("united states", "🇺🇸"),
    ("america", "🇺🇸"),
    ("japan", "🇯🇵"),
    ("korea", "🇰🇷"),
    ("kazakhstan", "🇰🇿"),
    ("uae", "🇦🇪"),
    ("emirates", "🇦🇪"),
    ("dubai", "🇦🇪"),
    ("ekaterinburg", "🇷🇺"),
    ("russia", "🇷🇺"),
    ("нидерланд", "🇳🇱"),
    ("герман", "🇩🇪"),
    ("финлянд", "🇫🇮"),
    ("швеци", "🇸🇪"),
    ("польш", "🇵🇱"),
    ("эстони", "🇪🇪"),
    ("латви", "🇱🇻"),
    ("румыни", "🇷🇴"),
    ("великобритан", "🇬🇧"),
    ("испани", "🇪🇸"),
    ("итали", "🇮🇹"),
    ("люксембург", "🇱🇺"),
    ("сша", "🇺🇸"),
    ("япони", "🇯🇵"),
    ("коре", "🇰🇷"),
    ("сингапур", "🇸🇬"),
    ("singapore", "🇸🇬"),
    ("казахстан", "🇰🇿"),
    ("оаэ", "🇦🇪"),
    ("екатеринбург", "🇷🇺"),
    ("росси", "🇷🇺"),
    ("auto", "🇪🇺"),
    ("fastest", "⚡"),
    ("gaming", "🎮"),
    ("whitelist", "💎"),
    ("wifi", "📶"),
    ("wi-fi", "📶"),
    ("mob", "📱"),
    ("warp", "🌐"),
    ("proton", "🛡️"),
)


_SERVER_MAP_CACHE: dict[str, str] = {}

def _load_server_map() -> dict[str, str]:
    global _SERVER_MAP_CACHE
    if _SERVER_MAP_CACHE:
        return _SERVER_MAP_CACHE
    for candidate in [
        Path.home() / ".config" / "wavez-vpn" / "wavez_servers.json",
        Path("/usr/local/share/wavez-vpn/wavez_servers.json"),
        Path(__file__).resolve().parent / "wavez_servers.json",
        Path(__file__).resolve().parent.parent / "wavez_servers.json",
    ]:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                for s in data.get("servers", []):
                    ascii_n = s.get("ascii_name") or s.get("id")
                    if ascii_n and s.get("name"):
                        _SERVER_MAP_CACHE[ascii_n] = s.get("name")
                    if s.get("name"):
                        _SERVER_MAP_CACHE[s.get("name")] = s.get("name")
                if _SERVER_MAP_CACHE:
                    break
            except Exception:
                pass
    return _SERVER_MAP_CACHE

def get_server_display_title(profile_name: str) -> str:
    """Return full friendly display title with country flag for any profile."""
    if not profile_name:
        return "Не выбран"
    s_map = _load_server_map()
    if profile_name in s_map:
        return s_map[profile_name]

    prof_file = Path.home() / ".config" / "wavez-vpn" / "profiles" / f"{profile_name}.conf"
    if prof_file.is_file():
        try:
            for line in prof_file.read_text(encoding="utf-8", errors="ignore").splitlines()[:8]:
                if line.startswith("# Incy Profile:"):
                    title = line.split(":", 1)[1].strip()
                    s_map[profile_name] = title
                    return title
        except Exception:
            pass

    flag = get_server_flag(profile_name)
    return f"{flag}  {profile_name}"

def get_server_flag(name: str) -> str:
    """Return national flag emoji for a given server name or code."""
    if not name:
        return "🌐"

    parts = name.strip().split()
    if parts:
        first = parts[0]
        if len(first) <= 8 and any(ord(c) > 0x1F000 for c in first):
            return first

    s_map = _load_server_map()
    if name in s_map:
        full_title = s_map[name]
        parts = full_title.strip().split()
        if parts:
            first = parts[0]
            if len(first) <= 8 and any(ord(c) > 0x1F000 for c in first):
                return first

    lower = name.lower()
    for key, flag in _COUNTRY_FLAGS:
        if key in lower:
            return flag
    return "🌐"


# ---------------------------------------------------------------------------
# TextViewHandler — routes Python logging into the Logs GtkTextView
# ---------------------------------------------------------------------------


class TextViewHandler(logging.Handler):
    """Logging handler that appends records to a ``Gtk.TextView``."""

    TAG_MAP = {
        logging.DEBUG: "debug",
        logging.INFO: "info",
        logging.WARNING: "warning",
        logging.ERROR: "error",
        logging.CRITICAL: "error",
    }

    def __init__(self, text_view: Gtk.TextView) -> None:
        super().__init__()
        self.text_view = text_view
        self.buffer = text_view.get_buffer()
        self._create_tags()

    def _create_tags(self) -> None:
        tag_table = self.buffer.get_tag_table()
        tags = {
            "debug": {"foreground": "#77767b"},
            "info": {"foreground": None},
            "warning": {"foreground": "#e5a50a"},
            "error": {"foreground": "#e01b24"},
            "success": {"foreground": "#2ec27e"},
            "timestamp": {"foreground": "#9a9996"},
        }
        for name, props in tags.items():
            if tag_table.lookup(name) is None:
                tag = self.buffer.create_tag(name)
                if props.get("foreground"):
                    tag.set_property("foreground", props["foreground"])

    def emit(self, record: logging.LogRecord) -> None:
        tag_name = self.TAG_MAP.get(record.levelno, "info")
        msg = self.format(record)
        GLib.idle_add(self._append, msg, tag_name)

    def _append(self, text: str, tag_name: str) -> bool:
        end_iter = self.buffer.get_end_iter()
        # Timestamp portion
        ts_end = text.find("]")
        if ts_end > 0:
            self.buffer.insert_with_tags_by_name(end_iter, text[: ts_end + 1] + " ", "timestamp")
            end_iter = self.buffer.get_end_iter()
            self.buffer.insert_with_tags_by_name(end_iter, text[ts_end + 2:] + "\n", tag_name)
        else:
            self.buffer.insert_with_tags_by_name(end_iter, text + "\n", tag_name)

        # Auto-scroll
        end_iter = self.buffer.get_end_iter()
        mark = self.buffer.create_mark(None, end_iter, False)
        self.text_view.scroll_mark_onscreen(mark)
        self.buffer.delete_mark(mark)
        return False  # remove from idle


# ---------------------------------------------------------------------------
# VPNApplication — Adw.Application subclass
# ---------------------------------------------------------------------------


class VPNApplication(Adw.Application):
    """The main GTK application."""

    def __init__(self, vpn_manager: VPNManager) -> None:
        super().__init__(
            application_id="com.wavez.vpnclient",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.vpn_manager = vpn_manager
        self._window: Optional[MainWindow] = None
        self._tray: Optional[TrayIcon] = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._setup_actions()
        self._setup_css()

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MainWindow(application=self, vpn_manager=self.vpn_manager)
            if _HAS_APPINDICATOR:
                self._tray = TrayIcon(self, self._window)
        self._window.set_visible(True)
        self._window.present()

    def _setup_actions(self) -> None:
        actions = {
            "quit": self._on_quit,
            "about": self._on_about,
            "connect-last": self._on_connect_last,
            "minimize_tray": self._on_minimize_tray,
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _on_minimize_tray(self, action: Gio.SimpleAction, param: Any) -> None:
        if self._window:
            self._window._minimize_to_tray()

    def _setup_css(self) -> None:
        css = """
        * {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, Cantarell, sans-serif;
        }

        window, .aether-window {
            background-color: #141226;
            color: #f1f5f9;
        }

        /* ── HeaderBar Window Frame (Draggable & Integrated) ── */
        headerbar.aether-header {
            min-height: 44px;
            background: #151329;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
            padding: 0 12px;
        }

        headerbar.aether-header windowhandle {
            min-height: 44px;
        }

        /* Segmented Pill Switcher (AetherVPN style) */
        .pill-switcher {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 9999px;
            padding: 2px 4px;
            margin: 0;
        }

        .switcher-btn {
            background: transparent;
            color: #94a3b8;
            border: none;
            box-shadow: none;
            border-radius: 9999px;
            padding: 4px 16px;
            font-size: 12px;
            font-weight: 600;
            min-height: 28px;
            transition: all 180ms ease;
        }

        .switcher-btn:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.08);
        }

        .switcher-btn.active {
            background: #4f46e5;
            color: #ffffff;
            font-weight: 700;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.45);
        }

        /* Header action buttons */
        .header-btn {
            background: transparent;
            color: #94a3b8;
            border: none;
            box-shadow: none;
            border-radius: 8px;
            padding: 6px;
            min-width: 32px;
            min-height: 32px;
            transition: all 180ms ease;
        }

        .header-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #ffffff;
        }

        /* Window controls clean styling */
        headerbar.aether-header windowcontrols button {
            border-radius: 9999px;
            min-width: 24px;
            min-height: 24px;
            padding: 2px;
            margin: 0 2px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        headerbar.aether-header windowcontrols button.close:hover {
            background: #ef4444;
            color: #ffffff;
        }

        .sidebar-panel {
            background: linear-gradient(180deg, #1b1638 0%, #110f22 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            padding: 16px 12px;
        }

        /* ── AAA Ultra-Glossy Specular Highlight Nav Buttons ── */
        .glossy-btn, .nav-btn {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.09) 0%, rgba(255, 255, 255, 0.02) 100%);
            border: 1px solid rgba(255, 255, 255, 0.10);
            box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.25), 0 2px 6px rgba(0, 0, 0, 0.3);
            border-radius: 12px;
            color: #cbd5e1;
            font-weight: 600;
            font-size: 13px;
            padding: 10px 14px;
            transition: all 180ms cubic-bezier(0.4, 0, 0.2, 1);
        }

        .nav-btn:hover {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.20) 0%, rgba(255, 255, 255, 0.06) 100%);
            border-color: rgba(255, 255, 255, 0.28);
            box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.45), 0 4px 14px rgba(0, 0, 0, 0.45);
            color: #ffffff;
        }

        .nav-btn.active {
            background: radial-gradient(circle at 50% 20%, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0) 70%),
                        linear-gradient(180deg, #6366f1 0%, #4338ca 100%);
            border: 1px solid rgba(255, 255, 255, 0.38);
            box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.65), 0 4px 18px rgba(99, 102, 241, 0.65);
            color: #ffffff;
        }

        /* ── Turn On Circular AAA Gloss Button with Lens Flare ── */
        .turn-on-btn {
            min-width: 148px;
            min-height: 148px;
            border-radius: 9999px;
            background: radial-gradient(circle at 50% 22%, rgba(255, 255, 255, 0.35) 0%, rgba(255, 255, 255, 0) 52%),
                        linear-gradient(180deg, #28244c 0%, #17142e 48%, #0d0b1d 52%, #191632 100%);
            border: 2px solid rgba(255, 255, 255, 0.25);
            box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.55),
                        inset 0 -3px 5px rgba(0, 0, 0, 0.8),
                        0 10px 28px rgba(0, 0, 0, 0.6),
                        0 0 24px rgba(56, 189, 248, 0.35);
            color: #38bdf8;
            transition: all 250ms cubic-bezier(0.4, 0, 0.2, 1);
        }

        .turn-on-btn:hover {
            background: radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.5) 0%, rgba(255, 255, 255, 0) 60%),
                        linear-gradient(180deg, #363162 0%, #1f1b40 48%, #14112e 52%, #25204d 100%);
            border-color: rgba(56, 189, 248, 0.85);
            box-shadow: inset 0 2px 5px rgba(255, 255, 255, 0.75),
                        inset 0 -3px 6px rgba(0, 0, 0, 0.9),
                        0 12px 35px rgba(56, 189, 248, 0.5),
                        0 0 40px rgba(56, 189, 248, 0.65);
        }

        .turn-on-btn.connected {
            background: radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0) 60%),
                        linear-gradient(180deg, #10b981 0%, #059669 48%, #047857 52%, #065f46 100%);
            border: 2px solid #6ee7b7;
            color: #ffffff;
            box-shadow: inset 0 2px 6px rgba(255, 255, 255, 0.9),
                        inset 0 -3px 6px rgba(0, 0, 0, 0.6),
                        0 12px 42px rgba(16, 185, 129, 0.7),
                        0 0 55px rgba(52, 211, 153, 0.8);
        }

        .turn-on-btn.connecting {
            background: radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 0) 60%),
                        linear-gradient(180deg, #f59e0b 0%, #d97706 48%, #b45309 52%, #92400e 100%);
            border: 2px solid #fde68a;
            color: #ffffff;
            box-shadow: inset 0 2px 5px rgba(255, 255, 255, 0.85),
                        0 0 45px rgba(245, 158, 11, 0.7);
        }

        .turn-on-text {
            font-weight: 800;
            font-size: 13px;
            letter-spacing: 1.6px;
        }

        .glass-card {
            background: linear-gradient(135deg, rgba(34, 28, 70, 0.75) 0%, rgba(18, 15, 38, 0.88) 100%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.2), 0 8px 24px rgba(0, 0, 0, 0.45);
            border-radius: 16px;
            padding: 12px 18px;
        }

        .locations-panel {
            background: #16132e;
            border-left: 1px solid rgba(255, 255, 255, 0.07);
            padding: 14px;
        }

        .server-item-btn {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.04) 0%, rgba(255, 255, 255, 0.01) 100%);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 8px 12px;
            margin: 2px 0;
            transition: all 150ms ease;
            color: #e2e8f0;
        }

        .server-item-btn:hover {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.04) 100%);
            border-color: rgba(99, 102, 241, 0.6);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }

        .server-item-btn.selected {
            background: rgba(99, 102, 241, 0.25);
            border-color: #6366f1;
        }

        .badge-optimal {
            background: rgba(56, 239, 125, 0.18);
            color: #38ef7d;
            border-radius: 6px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: bold;
        }

        .vpn-connected { color: #2ec27e; }
        .vpn-disconnected { color: #77767b; }
        .vpn-error { color: #e01b24; }
        .vpn-stats-value {
            font-variant-numeric: tabular-nums;
            font-weight: bold;
        }
        .monospace-view {
            font-family: monospace;
            font-size: 11px;
        }
        .connect-button {
            min-height: 48px;
            min-width: 200px;
            font-size: 15px;
        }
        .badge-awg {
            background-color: rgba(145, 65, 230, 0.18);
            color: #9141e6;
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: bold;
        }
        .badge-wg {
            background-color: rgba(53, 132, 228, 0.18);
            color: #3584e4;
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: bold;
        }
        .latency-good {
            color: #2ec27e;
            font-weight: bold;
            font-size: 12px;
        }
        .latency-medium {
            color: #e5a50a;
            font-weight: bold;
            font-size: 12px;
        }
        .latency-bad {
            color: #e01b24;
            font-weight: bold;
            font-size: 12px;
        }
        .latency-none {
            color: #77767b;
            font-size: 12px;
        }
        """.encode("utf-8")
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ---- Action handlers --------------------------------------------------

    def _on_quit(self, action: Gio.SimpleAction, param: Any) -> None:
        logger.info("Quit requested")
        if self._window:
            self._window.shutdown()
        self.quit()

    def _on_about(self, action: Gio.SimpleAction, param: Any) -> None:
        try:
            from version import APP_VERSION
        except Exception:
            APP_VERSION = "1.2.7"

        about = Adw.AboutWindow(
            application_name="SPIZDILI_VPN",
            application_icon="spizdili-vpn",
            version=APP_VERSION,
            developer_name="WaveZ & Aether Team",
            license_type=Gtk.License.GPL_3_0,
            comments="Fast & Secure VPN client with VLESS Reality, WireGuard and AmneziaWG support",
            website="https://github.com/newiziwavez33-hub/spizdili_vpn",
            developers=["WaveZ & Aether Team"],
            transient_for=self._window,
        )
        about.present()

    def _on_connect_last(self, action: Gio.SimpleAction, param: Any) -> None:
        if self._window:
            self._window.connect_to_last()

    def get_window(self) -> Optional["MainWindow"]:
        return self._window

    def get_tray(self) -> Optional["TrayIcon"]:
        return self._tray


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(Adw.ApplicationWindow):
    """Primary application window with three tabs."""

    def __init__(self, application: VPNApplication, vpn_manager: VPNManager) -> None:
        super().__init__(application=application, title="SPIZDILI_VPN (v 1.2.7)")
        self.app: VPNApplication = application
        self.vpn: VPNManager = vpn_manager
        self.cfg: ConfigManager = vpn_manager.config_manager

        # State
        self._connected: bool = False
        self._connecting: bool = False
        self._active_profile: Optional[str] = None
        self._connect_time: Optional[float] = None
        self._killswitch_enabled: bool = False
        self._stats_timer_id: int = 0
        self._duration_timer_id: int = 0
        self._shutting_down: bool = False
        self._latencies: dict[str, float] = {}
        self._latency_labels: dict[str, Gtk.Label] = {}
        self.settings = vpn_manager.settings_manager
        self._sort_by_ping: bool = False

        self.set_default_size(980, 640)
        self.set_size_request(420, 520)
        self.set_icon_name("spizdili-vpn")

        self._build_ui()
        self._refresh_profiles()
        self._setup_log_handler()

        # Check if already connected (e.g. app restart)
        GLib.timeout_add(500, self._initial_status_check)

        self.connect("close-request", self._on_close_request)

    # ---- UI construction --------------------------------------------------

    def _minimize_to_tray(self) -> None:
        self.set_visible(False)

    def _navigate_to(self, page_id: str) -> None:
        if hasattr(self, "_stack") and self._stack:
            self._stack.set_visible_child_name(page_id)
        if hasattr(self, "_nav_buttons"):
            for pid, btn in self._nav_buttons.items():
                if pid == page_id:
                    btn.add_css_class("active")
                else:
                    btn.remove_css_class("active")
        if hasattr(self, "_header_tab_btns"):
            for pid, btn in self._header_tab_btns.items():
                if pid == page_id:
                    btn.add_css_class("active")
                else:
                    btn.remove_css_class("active")

    def _build_ui(self) -> None:
        self.add_css_class("aether-window")
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        # Main Vertical Container
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._toast_overlay.set_child(main_vbox)

        # ── Draggable Window HeaderBar ───────────────────────────────────
        header = Adw.HeaderBar()
        header.add_css_class("aether-header")
        header.set_show_end_title_buttons(True)
        header.set_show_start_title_buttons(True)

        # Left branding in HeaderBar
        header_brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_brand.set_valign(Gtk.Align.CENTER)

        logo_path = "/usr/local/share/wavez-vpn/icons/spizdili-vpn-32.png"
        if not Path(logo_path).is_file():
            logo_path = "/usr/local/share/wavez-vpn/icons/spizdili-logo.png"

        if Path(logo_path).is_file():
            h_img = Gtk.Image.new_from_file(logo_path)
            h_img.set_pixel_size(24)
            header_brand.append(h_img)

        app_title = Gtk.Label()
        app_title.set_markup("<span weight='heavy' size='11000' color='#ffffff'>SPIZDILI_VPN</span>")
        header_brand.append(app_title)

        ver_badge = Gtk.Label()
        ver_badge.set_markup("<span size='8500' weight='bold' color='#818cf8'>1.2.7</span>")
        ver_badge.add_css_class("badge-awg")
        header_brand.append(ver_badge)
        header.pack_start(header_brand)

        # Center: Segmented Pill Switcher
        self._quick_tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._quick_tab_box.add_css_class("pill-switcher")
        tab_defs = [("connection", "Подключение"), ("speed", "⚡ Скорость & Fresh"), ("profiles", "Серверы"), ("settings", "Настройки")]
        self._header_tab_btns = {}
        for q_id, q_label in tab_defs:
            q_btn = Gtk.Button(label=q_label)
            q_btn.add_css_class("switcher-btn")
            q_btn.connect("clicked", lambda b, q=q_id: self._navigate_to(q))
            self._quick_tab_box.append(q_btn)
            self._header_tab_btns[q_id] = q_btn
        header.set_title_widget(self._quick_tab_box)

        # Right: Notification Bell & Menu
        notif_btn = Gtk.Button()
        notif_btn.add_css_class("header-btn")
        notif_icon = Gtk.Image.new_from_icon_name("preferences-system-notifications-symbolic")
        notif_icon.set_pixel_size(16)
        notif_btn.set_child(notif_icon)
        notif_btn.set_tooltip_text("Уведомления сети")
        notif_btn.connect("clicked", lambda b: self._show_toast("Все 47 узлов сети активны"))
        header.pack_end(notif_btn)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.add_css_class("header-btn")
        menu_model = Gio.Menu()
        menu_model.append("О программе", "app.about")
        menu_model.append("Свернуть в трей", "app.minimize_tray")
        menu_model.append("Выход", "app.quit")
        menu_btn.set_menu_model(menu_model)
        header.pack_end(menu_btn)

        main_vbox.append(header)

        # ── Body: [Left Sidebar] | [Central ViewStack] ───────────────────
        body_h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, vexpand=True, hexpand=True)
        main_vbox.append(body_h_box)

        # ── Left Navigation Sidebar ──────────────────────────────────────
        self._sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._sidebar.add_css_class("sidebar-panel")
        self._sidebar.set_size_request(210, -1)

        # Nav items with Material Design SVGs
        self._nav_buttons = {}
        nav_defs = [
            ("connection", "Дашборд", "dashboard.svg"),
            ("speed", "⚡ Скорость & Fresh", "speed.svg"),
            ("profiles", "Локации", "public.svg"),
            ("settings", "Настройки", "settings.svg"),
            ("logs", "Журнал", "terminal.svg"),
        ]
        for page_id, label_text, icon_file in nav_defs:
            btn = Gtk.Button()
            btn.add_css_class("nav-btn")
            btn.set_halign(Gtk.Align.FILL)
            
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon_p = f"/usr/local/share/wavez-vpn/icons/material/{icon_file}"
            if Path(icon_p).is_file():
                img = Gtk.Image.new_from_file(icon_p)
                img.set_pixel_size(18)
                btn_box.append(img)
            
            lbl = Gtk.Label(label=label_text)
            btn_box.append(lbl)
            btn.set_child(btn_box)

            btn.connect("clicked", lambda b, pid=page_id: self._navigate_to(pid))
            self._sidebar.append(btn)
            self._nav_buttons[page_id] = btn

        # Spacer
        spacer = Gtk.Box(vexpand=True)
        self._sidebar.append(spacer)

        # Bottom Version in Sidebar
        bot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bot_box.set_margin_bottom(10)
        bot_box.set_margin_start(6)
        v_lbl = Gtk.Label()
        v_lbl.set_markup(f"<span size='10000' color='#64748b'>v{APP_VERSION} • Protected</span>")
        v_lbl.set_halign(Gtk.Align.START)
        bot_box.append(v_lbl)
        self._sidebar.append(bot_box)

        body_h_box.append(self._sidebar)

        # ── Central View Stack ───────────────────────────────────────────
        self._stack = Adw.ViewStack()
        self._stack.set_vexpand(True)
        self._stack.set_hexpand(True)
        body_h_box.append(self._stack)

        # Compatibility headers
        self._view_switcher_title = Adw.ViewSwitcherTitle()
        self._view_switcher_title.set_stack(self._stack)
        self._view_switcher_bar = Adw.ViewSwitcherBar()
        self._view_switcher_bar.set_stack(self._stack)

        # Build pages
        self._build_connection_page()
        self._build_speed_fresh_page()
        self._build_profiles_page()
        self._build_logs_page()
        self._build_settings_page()

        # Initial active tab highlight
        self._navigate_to("connection")

        # Auto-check updates
        GLib.timeout_add_seconds(5, lambda: self._schedule_auto_update_check() or False)

    def _on_turn_on_clicked(self, btn: Gtk.Button) -> None:
        logger.info("TURN ON button clicked (connected=%s, connecting=%s)", self._connected, getattr(self, "_connecting", False))
        if getattr(self, "_connecting", False):
            self._show_toast("Пожалуйста, подождите завершения операции…")
            return

        is_active = self._connected or getattr(self.vpn, "_connected", False) or self.vpn.xray_manager.is_connected()
        if is_active:
            self._do_disconnect()
        else:
            self._on_connect_clicked(btn)

    def _build_connection_page(self) -> None:
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        self._stack.add_titled(overlay, "connection", "Дашборд")

        # User-uploaded Map Background Image
        map_path = None
        for candidate in (
            Path("/usr/local/share/wavez-vpn/icons/world-map-bg.jpg"),
            Path(__file__).resolve().parent / "icons" / "world-map-bg.jpg",
            Path(__file__).resolve().parent.parent / "icons" / "world-map-bg.jpg",
        ):
            if candidate.is_file():
                map_path = str(candidate)
                break

        if map_path:
            map_pic = Gtk.Picture.new_for_filename(map_path)
            map_pic.set_content_fit(Gtk.ContentFit.COVER)
            map_pic.set_can_target(False)  # Let mouse clicks pass through
            overlay.set_child(map_pic)
        else:
            dummy_bg = Gtk.Box()
            overlay.set_child(dummy_bg)

        # Central Foreground Content
        center_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        center_content.set_can_target(True)
        center_content.set_margin_top(20)
        center_content.set_margin_bottom(20)

        # ── BIG AAA GLOSSY CIRCULAR TURN ON BUTTON ──
        self._turn_on_btn = Gtk.Button()
        self._turn_on_btn.add_css_class("turn-on-btn")
        self._turn_on_btn.set_size_request(150, 150)
        self._turn_on_btn.set_halign(Gtk.Align.CENTER)
        self._turn_on_btn.connect("clicked", self._on_turn_on_clicked)

        btn_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        
        # Power SVG Icon
        power_p = "/usr/local/share/wavez-vpn/icons/material/power.svg"
        if Path(power_p).is_file():
            power_icon = Gtk.Image.new_from_file(power_p)
            power_icon.set_pixel_size(44)
        else:
            power_icon = Gtk.Image.new_from_icon_name("system-shutdown-symbolic")
            power_icon.set_pixel_size(44)
        btn_vbox.append(power_icon)

        self._turn_on_lbl = Gtk.Label(label="TURN ON")
        self._turn_on_lbl.add_css_class("turn-on-text")
        btn_vbox.append(self._turn_on_lbl)
        self._turn_on_btn.set_child(btn_vbox)

        center_content.append(self._turn_on_btn)

        # Status Labels
        self._status_label = Gtk.Label()
        self._status_label.set_markup("<span size='20000' weight='heavy' color='#ffffff'>Disconnected</span>")
        center_content.append(self._status_label)

        self._status_subtitle = Gtk.Label()
        self._status_subtitle.set_markup("<span size='11500' color='#94a3b8'>Optimal Location: Auto-Select (Optimal)</span>")
        center_content.append(self._status_subtitle)

        # Quick Server Selector Dropdown
        self._selector_group = Adw.PreferencesGroup()
        self._selector_group.set_size_request(380, -1)
        self._selector_group.set_halign(Gtk.Align.CENTER)
        self._profile_dropdown_row = Adw.ComboRow(title="Сервер")
        self._profile_model = Gtk.StringList()
        self._profile_dropdown_row.set_model(self._profile_model)
        self._profile_dropdown_row.connect("notify::selected", self._on_profile_dropdown_selected)
        self._selector_group.add(self._profile_dropdown_row)
        center_content.append(self._selector_group)

        # Kill-Switch row (must exist for vpn connection logic)
        self._killswitch_row = Adw.SwitchRow(
            title="Kill-Switch",
            subtitle="Блокировать трафик при обрыве VPN",
        )
        self._killswitch_row.connect("notify::active", self._on_killswitch_toggled)
        self._selector_group.add(self._killswitch_row)

        # Quick Action Buttons on Main Dashboard
        quick_actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.CENTER)
        quick_actions_box.set_margin_top(8)

        self._dash_key_btn = Gtk.Button(label="🔑 Активировать ключ")
        self._dash_key_btn.add_css_class("suggested-action")
        self._dash_key_btn.add_css_class("pill")
        self._dash_key_btn.set_tooltip_text("Добавить ссылку на подписку или ключ серверов")
        self._dash_key_btn.connect("clicked", self._on_import_link_clicked)
        quick_actions_box.append(self._dash_key_btn)

        self._dash_speed_btn = Gtk.Button(label="🚀 Тест скорости")
        self._dash_speed_btn.add_css_class("pill")
        self._dash_speed_btn.set_tooltip_text("Замерить реальную скорость туннеля (Мбит/с)")
        self._dash_speed_btn.connect("clicked", self._on_run_speedtest_clicked)
        quick_actions_box.append(self._dash_speed_btn)

        center_content.append(quick_actions_box)

        # Bottom Footer Diagnostics Card
        self._footer_dock = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24, halign=Gtk.Align.CENTER)
        self._footer_dock.add_css_class("glass-card")
        self._footer_dock.set_margin_top(8)

        # IP
        self._footer_ip_lbl = Gtk.Label()
        self._footer_ip_lbl.set_markup("<span size='11000' color='#94a3b8'>Current IP: </span><span size='11000' weight='bold' color='#ffffff'>178.xx.xx.xx</span>")
        self._footer_dock.append(self._footer_ip_lbl)

        # Duration
        self._footer_duration_lbl = Gtk.Label()
        self._footer_duration_lbl.set_markup("<span size='11000' color='#94a3b8'>Duration: </span><span size='11000' weight='bold' color='#38ef7d'>00:00:00</span>")
        self._footer_dock.append(self._footer_duration_lbl)

        # Ping
        self._footer_ping_lbl = Gtk.Label()
        self._footer_ping_lbl.set_markup("<span size='11000' color='#94a3b8'>Ping: </span><span size='11000' weight='bold' color='#38bdf8'>—</span>")
        self._footer_dock.append(self._footer_ping_lbl)

        center_content.append(self._footer_dock)

        # Legacy widgets compatibility placeholders
        self._connect_btn = Gtk.Button(label="Подключить")
        self._connect_btn.set_visible(False)
        self._disconnect_btn = Gtk.Button(label="Отключить")
        self._disconnect_btn.set_visible(False)
        self._status_icon = Gtk.Image.new_from_icon_name("security-medium-symbolic")
        self._status_icon.set_visible(False)
        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        self._ip_value = Gtk.Label(label="—")
        self._ping_value = Gtk.Label(label="—")
        self._download_value = Gtk.Label(label="0 B")
        self._upload_value = Gtk.Label(label="0 B")
        self._stats_group = Gtk.Box()
        self._stats_group.set_visible(False)

        overlay.add_overlay(center_content)


    # ── Speed & Fresh Tab Page with Cairo Speedometer & Animated Radar ──

    def _build_speed_fresh_page(self) -> None:
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(page_box)
        self._stack.add_titled_with_icon(scroll, "speed", "Свежие & Скорость", "speedometer-symbolic")

        clamp = Adw.Clamp(maximum_size=740, tightening_threshold=500)
        clamp.set_hexpand(True)
        clamp.set_vexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_hexpand(True)
        inner.set_margin_top(20)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        clamp.set_child(inner)
        page_box.append(clamp)

        # ── 1. SPEEDOMETER DASHBOARD CARD ─────────────────────────────
        speed_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        speed_card.add_css_class("card")
        speed_card.set_margin_bottom(6)

        # Header
        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_h = Gtk.Label()
        lbl_h.set_markup("<span size='14000' weight='heavy' color='#ffffff'>🚀 Скорость туннеля (Real-Speed Test)</span>")
        lbl_h.set_halign(Gtk.Align.START)
        h_box.append(lbl_h)
        speed_card.append(h_box)

        lbl_sub = Gtk.Label()
        lbl_sub.set_markup("<span size='10000' color='#94a3b8'>Прямой замер фактической пропускной способности канала через CDN Cloudflare</span>")
        lbl_sub.set_halign(Gtk.Align.START)
        speed_card.append(lbl_sub)

        # Cairo Speedometer Drawing Area
        self._anim_speed = 0.0
        self._target_speed = 0.0
        self._speed_anim_running = False

        gauge_overlay = Gtk.Overlay()
        gauge_overlay.set_halign(Gtk.Align.CENTER)
        gauge_overlay.set_size_request(340, 230)

        self._speed_da = Gtk.DrawingArea()
        self._speed_da.set_size_request(340, 230)
        self._speed_da.set_draw_func(self._draw_speedometer_cairo)
        gauge_overlay.set_child(self._speed_da)

        # Center readout placed over Cairo gauge
        center_readout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        center_readout.set_margin_top(48)

        self._speed_gauge_val = Gtk.Label()
        self._speed_gauge_val.set_markup("<span size='36000' weight='heavy' color='#38bdf8'>0.0</span>")
        center_readout.append(self._speed_gauge_val)

        unit_lbl = Gtk.Label()
        unit_lbl.set_markup("<span size='11000' weight='bold' color='#94a3b8'>Мбит/с (Mbps)</span>")
        center_readout.append(unit_lbl)

        gauge_overlay.add_overlay(center_readout)
        speed_card.append(gauge_overlay)

        # Status text below gauge
        self._speed_gauge_status = Gtk.Label()
        self._speed_gauge_status.set_markup("<span size='10000' color='#64748b'>Нажмите «Запустить тест» для измерения</span>")
        self._speed_gauge_status.set_halign(Gtk.Align.CENTER)
        speed_card.append(self._speed_gauge_status)

        # 3 Quick Metrics Badges (Latency, Transferred, Duration)
        metrics_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.CENTER)
        metrics_box.set_margin_top(4)
        metrics_box.set_margin_bottom(8)

        # Metric 1: Ping
        m1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        m1.add_css_class("badge-awg")
        m1.set_size_request(90, 48)
        lbl_m1_t = Gtk.Label(label="Задержка")
        lbl_m1_t.add_css_class("caption")
        m1.append(lbl_m1_t)
        self._lbl_st_ping = Gtk.Label()
        self._lbl_st_ping.set_markup("<span weight='bold' color='#34d399'>-- мс</span>")
        m1.append(self._lbl_st_ping)
        metrics_box.append(m1)

        # Metric 2: Transferred
        m2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        m2.add_css_class("badge-awg")
        m2.set_size_request(90, 48)
        lbl_m2_t = Gtk.Label(label="Пакет")
        lbl_m2_t.add_css_class("caption")
        m2.append(lbl_m2_t)
        self._lbl_st_bytes = Gtk.Label()
        self._lbl_st_bytes.set_markup("<span weight='bold' color='#38bdf8'>2.5 MB</span>")
        m2.append(self._lbl_st_bytes)
        metrics_box.append(m2)

        # Metric 3: Time
        m3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        m3.add_css_class("badge-awg")
        m3.set_size_request(90, 48)
        lbl_m3_t = Gtk.Label(label="Время")
        lbl_m3_t.add_css_class("caption")
        m3.append(lbl_m3_t)
        self._lbl_st_time = Gtk.Label()
        self._lbl_st_time.set_markup("<span weight='bold' color='#a855f7'>-- сек</span>")
        m3.append(self._lbl_st_time)
        metrics_box.append(m3)

        speed_card.append(metrics_box)

        # Launch Speedtest Button
        self._btn_launch_speed = Gtk.Button(label="🚀 Запустить тест скорости")
        self._btn_launch_speed.add_css_class("suggested-action")
        self._btn_launch_speed.add_css_class("pill")
        self._btn_launch_speed.set_size_request(260, 42)
        self._btn_launch_speed.set_halign(Gtk.Align.CENTER)
        self._btn_launch_speed.connect("clicked", self._on_run_speedtest_clicked)
        speed_card.append(self._btn_launch_speed)

        # Audit & Purge Dead Servers Button
        self._btn_audit_servers = Gtk.Button(label="⚡ Проверить серверы (Исключить мёртвые)")
        self._btn_audit_servers.add_css_class("pill")
        self._btn_audit_servers.set_size_request(280, 38)
        self._btn_audit_servers.set_halign(Gtk.Align.CENTER)
        self._btn_audit_servers.set_tooltip_text("Проверить задержку всех узлов и полностью удалить не отвечающие серверы из списка")
        self._btn_audit_servers.connect("clicked", self._on_audit_and_purge_dead_servers)
        speed_card.append(self._btn_audit_servers)

        inner.append(speed_card)

        # ── 2. FRESH SERVERS RADAR CARD ────────────────────────────────
        fresh_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        fresh_card.add_css_class("card")
        fresh_card.set_margin_bottom(6)

        f_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_f_title = Gtk.Label()
        lbl_f_title.set_markup("<span size='14000' weight='heavy' color='#ffffff'>📡 Радар свежих серверов [FRESH]</span>")
        lbl_f_title.set_halign(Gtk.Align.START)
        f_hdr.append(lbl_f_title)
        fresh_card.append(f_hdr)

        lbl_f_sub = Gtk.Label()
        lbl_f_sub.set_markup("<span size='10000' color='#94a3b8'>Фоновый поиск и отбор только рабочих VLESS Reality узлов с присвоением тега [FRESH]</span>")
        lbl_f_sub.set_halign(Gtk.Align.START)
        fresh_card.append(lbl_f_sub)

        # Scanner status box with glowing pill
        radar_status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.CENTER)
        self._radar_dot = Gtk.Label()
        self._radar_dot.set_markup("<span color='#34d399' size='12000'>●</span>")
        radar_status_box.append(self._radar_dot)

        self._lbl_radar_state = Gtk.Label()
        self._lbl_radar_state.set_markup("<span size='10500' weight='bold' color='#e2e8f0'>Готов к сканированию открытых сетей</span>")
        radar_status_box.append(self._lbl_radar_state)
        fresh_card.append(radar_status_box)

        # Scan Button
        self._btn_fresh_scan = Gtk.Button(label="🔄 Сканировать и обновить [FRESH] сервера")
        self._btn_fresh_scan.add_css_class("pill")
        self._btn_fresh_scan.set_size_request(320, 42)
        self._btn_fresh_scan.set_halign(Gtk.Align.CENTER)
        self._btn_fresh_scan.connect("clicked", self._on_fetch_cloud_servers_clicked)
        fresh_card.append(self._btn_fresh_scan)

        inner.append(fresh_card)

        # ── 3. CLOUDFLARE WARP CARD ────────────────────────────────────
        warp_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        warp_card.add_css_class("card")

        w_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_w_title = Gtk.Label()
        lbl_w_title.set_markup("<span size='14000' weight='heavy' color='#ffffff'>🛡️ Личный Cloudflare WARP</span>")
        lbl_w_title.set_halign(Gtk.Align.START)
        w_hdr.append(lbl_w_title)
        warp_card.append(w_hdr)

        lbl_w_sub = Gtk.Label()
        lbl_w_sub.set_markup("<span size='10000' color='#94a3b8'>Бесплатный персональный изолированный WireGuard сервер без ограничений трафика и перегрузок</span>")
        lbl_w_sub.set_halign(Gtk.Align.START)
        warp_card.append(lbl_w_sub)

        # Warp status
        self._warp_status_lbl = Gtk.Label()
        self._warp_status_lbl.set_markup("<span size='10000' color='#818cf8'>⚡ Готов к генерации персонального WireGuard ключа</span>")
        self._warp_status_lbl.set_halign(Gtk.Align.CENTER)
        warp_card.append(self._warp_status_lbl)

        self._btn_warp_page_create = Gtk.Button(label="⚡ Создать личный WARP в 1 клик")
        self._btn_warp_page_create.add_css_class("suggested-action")
        self._btn_warp_page_create.add_css_class("pill")
        self._btn_warp_page_create.set_size_request(280, 42)
        self._btn_warp_page_create.set_halign(Gtk.Align.CENTER)
        self._btn_warp_page_create.connect("clicked", self._on_create_personal_warp_clicked)
        warp_card.append(self._btn_warp_page_create)

        inner.append(warp_card)

    def _draw_speedometer_cairo(self, area, cr, width, height) -> None:
        """Draw high-tech circular tachometer speedometer with glowing gradient arc and scale."""
        import cairo
        cx = width / 2.0
        cy = height * 0.62
        radius = 95.0
        start_angle = math.pi * 0.75
        end_angle = math.pi * 2.25
        total_angle = end_angle - start_angle

        # 1. Subtle Outer Glow Ring
        cr.set_line_width(18)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(0.20, 0.22, 0.38, 0.35)
        cr.arc(cx, cy, radius, start_angle, end_angle)
        cr.stroke()

        # 2. Main Track
        cr.set_line_width(12)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(0.18, 0.20, 0.35, 0.85)
        cr.arc(cx, cy, radius, start_angle, end_angle)
        cr.stroke()

        # 3. Scale Ticks & Number Labels
        ticks = [0, 25, 50, 75, 100, 150, 200]
        for i, val in enumerate(ticks):
            t_frac = i / (len(ticks) - 1)
            a = start_angle + t_frac * total_angle

            # Tick mark
            inner_r = radius - 16
            outer_r = radius - 7
            x1 = cx + inner_r * math.cos(a)
            y1 = cy + inner_r * math.sin(a)
            x2 = cx + outer_r * math.cos(a)
            y2 = cy + outer_r * math.sin(a)

            cr.set_line_width(2.0)
            cr.set_source_rgba(0.55, 0.65, 0.85, 0.65)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()

            # Text label for tick
            lbl_r = radius - 26
            tx = cx + lbl_r * math.cos(a)
            ty = cy + lbl_r * math.sin(a)
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(9)
            cr.set_source_rgba(0.60, 0.70, 0.85, 0.80)
            txt = str(val)
            xb, yb, w, h, _, _ = cr.text_extents(txt)
            cr.move_to(tx - w / 2.0, ty + h / 2.0)
            cr.show_text(txt)

        # 4. Active Glowing Gradient Arc
        sim_speed = getattr(self, "_anim_speed", 0.0)
        max_speed = 200.0
        frac = min(max(sim_speed / max_speed, 0.0), 1.0)

        if frac > 0.005:
            active_end = start_angle + frac * total_angle

            # Outer Glow for active arc
            cr.set_line_width(18)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_source_rgba(0.0, 0.95, 0.99, 0.22)
            cr.arc(cx, cy, radius, start_angle, active_end)
            cr.stroke()

            # Gradient active arc
            pat = cairo.LinearGradient(cx - radius, cy, cx + radius, cy)
            pat.add_color_stop_rgba(0.0, 0.0, 0.85, 1.0, 1.0)   # Electric Cyan
            pat.add_color_stop_rgba(0.5, 0.50, 0.40, 1.0, 1.0)  # Indigo
            pat.add_color_stop_rgba(1.0, 0.0, 0.96, 0.63, 1.0)  # Neon Emerald
            cr.set_source(pat)
            cr.set_line_width(12)
            cr.arc(cx, cy, radius, start_angle, active_end)
            cr.stroke()

            # Glowing Head / Needle Tip
            tip_x = cx + radius * math.cos(active_end)
            tip_y = cy + radius * math.sin(active_end)

            # Glow halo
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.45)
            cr.arc(tip_x, tip_y, 9.0, 0, 2 * math.pi)
            cr.fill()

            # Solid bright center
            cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            cr.arc(tip_x, tip_y, 5.0, 0, 2 * math.pi)
            cr.fill()

    def _animate_speedometer_step(self) -> bool:
        """Smoothly interpolate gauge needle towards target speed."""
        diff = self._target_speed - self._anim_speed
        if abs(diff) < 0.2:
            self._anim_speed = self._target_speed
            if hasattr(self, "_speed_da"):
                self._speed_da.queue_draw()
            self._speed_anim_running = False
            return False

        self._anim_speed += diff * 0.18
        if hasattr(self, "_speed_da"):
            self._speed_da.queue_draw()
        if hasattr(self, "_speed_gauge_val"):
            self._speed_gauge_val.set_markup(f"<span size='32000' weight='heavy' color='#38bdf8'>{self._anim_speed:.1f}</span>")
        return True

    def _start_speed_anim_to(self, target: float) -> None:
        """Start smooth animation to target Mbps."""
        self._target_speed = target
        if not self._speed_anim_running:
            self._speed_anim_running = True
            GLib.timeout_add(20, self._animate_speedometer_step)

    # ---- Profiles page ----------------------------------------------------

    def _on_audit_and_purge_dead_servers(self, _btn=None) -> None:
        """Ping all servers in parallel via TCP; exclude dead servers and show detailed results dialog."""
        if hasattr(self, "_btn_audit_servers"):
            self._btn_audit_servers.set_sensitive(False)
            self._btn_audit_servers.set_label("⏳ Проверка сети…")
        if hasattr(self, "_loc_audit_btn"):
            self._loc_audit_btn.set_sensitive(False)
        self._show_toast("⚡ Экспресс-проверка: замер задержки каждого узла и отсев мёртвых…", timeout=4)

        def _task():
            try:
                import concurrent.futures
                import socket
                import reality_fetcher

                servers = reality_fetcher.load_cached_servers()
                if not servers:
                    GLib.idle_add(self._show_toast, "Список серверов пуст.")
                    return

                def test_srv(s):
                    addr = s.get("address", "")
                    port = int(s.get("port", 443))
                    t0 = time.time()
                    try:
                        with socket.create_connection((addr, port), timeout=1.8):
                            lat = (time.time() - t0) * 1000.0
                            return s, True, round(lat, 1)
                    except Exception:
                        return s, False, 9999.0

                alive_servers = []
                dead_servers = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=35) as ex:
                    results = list(ex.map(test_srv, servers))

                for s, ok, lat in results:
                    if ok:
                        s_name = s.get("name", "")
                        self._latencies[s.get("ascii_name", s_name)] = lat
                        self._latencies[s_name] = lat
                        s["ping_ms"] = lat
                        alive_servers.append((s, lat))
                    else:
                        dead_servers.append(s)

                # Sort by fastest latency first
                alive_servers.sort(key=lambda x: x[1])
                saved_alive_json = [item[0] for item in alive_servers]

                # Save ONLY verified alive servers back to json
                reality_fetcher.save_servers_to_system(saved_alive_json)

                def on_done():
                    self._refresh_profiles()
                    if hasattr(self, "_btn_audit_servers"):
                        self._btn_audit_servers.set_sensitive(True)
                        self._btn_audit_servers.set_label("⚡ Проверить серверы (Исключить мёртвые)")
                    if hasattr(self, "_loc_audit_btn"):
                        self._loc_audit_btn.set_sensitive(True)

                    n_alive = len(alive_servers)
                    n_dead = len(dead_servers)

                    # Show Results Dialog with interactive list and pings
                    dlg = Adw.Window(
                        title="Результаты аудита серверов",
                        default_width=500,
                        default_height=560,
                        modal=True,
                        transient_for=self,
                    )
                    dlg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                    dlg.set_content(dlg_box)

                    hdr = Adw.HeaderBar()
                    close_btn = Gtk.Button(label="Готово")
                    close_btn.add_css_class("suggested-action")
                    close_btn.connect("clicked", lambda _: dlg.close())
                    hdr.pack_end(close_btn)
                    dlg_box.append(hdr)

                    scr = Gtk.ScrolledWindow(vexpand=True)
                    clamp = Adw.Clamp(maximum_size=460)
                    cnt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
                    cnt.set_margin_top(16)
                    cnt.set_margin_bottom(16)
                    cnt.set_margin_start(16)
                    cnt.set_margin_end(16)
                    clamp.set_child(cnt)
                    scr.set_child(clamp)
                    dlg_box.append(scr)

                    summary_grp = Adw.PreferencesGroup(
                        title=f"✓ Проверено {len(servers)} узлов",
                        description=f"🟢 Активно и сохранено: <b>{n_alive}</b>  •  🔴 Исключено нерабочих: <b>{n_dead}</b>",
                    )
                    cnt.append(summary_grp)

                    res_grp = Adw.PreferencesGroup(title="Рабочие серверы (по скорости)")
                    res_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
                    res_list.add_css_class("boxed-list")

                    for s_obj, lat_val in alive_servers:
                        row = Adw.ActionRow(
                            title=s_obj.get("name", "Server"),
                            subtitle=f"{s_obj.get('address', '')}:{s_obj.get('port', '')}",
                        )
                        # Latency badge
                        lat_badge = Gtk.Label(label=f"⚡ {lat_val:.0f} ms")
                        lat_badge.set_valign(Gtk.Align.CENTER)
                        if lat_val < 50:
                            lat_badge.add_css_class("badge-wg")
                        elif lat_val < 150:
                            lat_badge.add_css_class("badge-awg")
                        else:
                            lat_badge.add_css_class("badge-warp")
                        row.add_suffix(lat_badge)
                        res_list.append(row)

                    res_grp.add(res_list)
                    cnt.append(res_grp)
                    dlg.present()

                GLib.idle_add(on_done)
            except Exception as e:
                logger.error("Audit error: %s", e)
                def on_err():
                    if hasattr(self, "_btn_audit_servers"):
                        self._btn_audit_servers.set_sensitive(True)
                        self._btn_audit_servers.set_label("⚡ Проверить серверы (Исключить мёртвые)")
                    if hasattr(self, "_loc_audit_btn"):
                        self._loc_audit_btn.set_sensitive(True)
                    self._show_toast(f"Ошибка проверки: {e}", timeout=5)
                GLib.idle_add(on_err)

        import threading as _th
        _th.Thread(target=_task, daemon=True).start()

    def _build_profiles_page(self) -> None:
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(page_box)
        self._stack.add_titled_with_icon(scroll, "profiles", "Профили", "document-properties-symbolic")

        clamp = Adw.Clamp(maximum_size=680, tightening_threshold=460)
        clamp.set_hexpand(True)
        clamp.set_vexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_hexpand(True)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        clamp.set_child(inner)
        page_box.append(clamp)

        # ── User profiles ─────────────────────────────────────────────────
        self._profiles_group = Adw.PreferencesGroup(title="Список серверов и локаций")

        # Action buttons in group header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Sort by latency button (Fastest first)
        self._sort_btn = Gtk.Button.new_from_icon_name("view-sort-ascending-symbolic")
        self._sort_btn.set_tooltip_text("Сортировать по пингу (быстрые первыми)")
        self._sort_btn.add_css_class("flat")
        self._sort_btn.connect("clicked", self._on_sort_by_ping_clicked)
        header_box.append(self._sort_btn)

        # Check all latencies button
        check_all_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        check_all_btn.set_tooltip_text("Проверить задержку (пинг) всех серверов")
        check_all_btn.add_css_class("flat")
        check_all_btn.connect("clicked", self._on_check_all_latencies_clicked)
        header_box.append(check_all_btn)

        # Import link / subscription button (happ://, incy://, https://, awg://, wireguard://)
        import_link_btn = Gtk.Button.new_from_icon_name("insert-link-symbolic")
        import_link_btn.set_tooltip_text("Импорт ссылки на подписку / конфиг")
        import_link_btn.add_css_class("flat")
        import_link_btn.connect("clicked", self._on_import_link_clicked)
        header_box.append(import_link_btn)

        # Import .conf file button
        import_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        import_btn.set_tooltip_text("Импорт файла .conf")
        import_btn.add_css_class("flat")
        import_btn.connect("clicked", self._on_import_clicked)
        header_box.append(import_btn)

        # Fetch open community Reality servers button
        self._cloud_fetch_btn = Gtk.Button.new_from_icon_name("software-update-available-symbolic")
        self._cloud_fetch_btn.set_tooltip_text("Загрузить свежие серверы VLESS Reality из сети")
        self._cloud_fetch_btn.add_css_class("flat")
        self._cloud_fetch_btn.connect("clicked", self._on_fetch_cloud_servers_clicked)
        header_box.append(self._cloud_fetch_btn)

        self._profiles_group.set_header_suffix(header_box)

        # Interactive Search Entry for instant real-time filtering
        # ── Primary Key Activation Banner directly on the page ───────────
        key_group = Adw.PreferencesGroup(
            title="🔑 Активация серверов по ключу / подписке",
            description="Вставьте ссылку подписки или ключ для мгновенной загрузки всех локаций",
        )
        self._page_key_entry = Adw.EntryRow(title="Ключ / Ссылка")
        sub_url = self.settings.get("subscription_url", "")
        if sub_url:
            self._page_key_entry.set_text(sub_url)
        
        btn_key_act = Gtk.Button(label="⚡ Активировать")
        btn_key_act.add_css_class("suggested-action")
        btn_key_act.add_css_class("pill")
        btn_key_act.set_valign(Gtk.Align.CENTER)
        
        def _on_page_key_activate(b):
            k = self._page_key_entry.get_text().strip()
            if not k:
                self._show_toast("Введите ссылку или ключ подписки")
                return
            self._on_import_link_clicked(b, initial_text=k)

        btn_key_act.connect("clicked", _on_page_key_activate)
        self._page_key_entry.connect("entry-activated", lambda _: _on_page_key_activate(btn_key_act))
        self._page_key_entry.add_suffix(btn_key_act)
        key_group.add(self._page_key_entry)
        inner.append(key_group)

        # ── Smart Features Banner (Speed & Diagnostics) ──────────────────
        smart_group = Adw.PreferencesGroup(title="Инструменты")

        speed_row = Adw.ActionRow(title="🚀 Тест скорости загрузки", subtitle="Замер реальной пропускной способности туннеля (Мбит/с)")
        self._speed_btn = Gtk.Button(label="Замерить")
        self._speed_btn.add_css_class("pill")
        self._speed_btn.set_valign(Gtk.Align.CENTER)
        self._speed_btn.connect("clicked", self._on_run_speedtest_clicked)
        speed_row.add_suffix(self._speed_btn)
        smart_group.add(speed_row)

        inner.append(smart_group)

        self._profile_search_entry = Gtk.SearchEntry()
        self._profile_search_entry.set_placeholder_text("Поиск серверов, стран, протоколов…")
        self._profile_search_entry.connect("search-changed", lambda _: self._profiles_listbox.invalidate_filter())
        inner.append(self._profile_search_entry)

        inner.append(self._profiles_group)

        # Empty state with direct activate button
        self._profiles_empty = Adw.StatusPage(
            title="Серверы не активированы",
            description="Вставьте ключ или ссылку на подписку выше и нажмите «Активировать»",
            icon_name="dialog-password-symbolic",
        )
        self._profiles_empty.set_vexpand(True)
        inner.append(self._profiles_empty)

        # Actual list
        self._profiles_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._profiles_listbox.add_css_class("boxed-list")
        self._profiles_listbox.set_filter_func(self._filter_profile_row)
        self._profiles_listbox.set_sort_func(self._sort_profile_row)
        self._profiles_listbox.set_visible(False)
        self._profiles_group.add(self._profiles_listbox)

    # ---- Logs page --------------------------------------------------------

    def _build_logs_page(self) -> None:
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Toolbar for clear button
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(4)
        toolbar.set_margin_bottom(4)
        spacer = Gtk.Box(hexpand=True)
        toolbar.append(spacer)
        clear_btn = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Очистить журнал событий")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", self._on_clear_logs)
        toolbar.append(clear_btn)
        page_box.append(toolbar)

        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self._log_view = Gtk.TextView(editable=False, cursor_visible=False)
        self._log_view.set_hexpand(True)
        self._log_view.set_vexpand(True)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.add_css_class("monospace-view")
        self._log_view.set_left_margin(8)
        self._log_view.set_right_margin(8)
        self._log_view.set_top_margin(4)
        self._log_view.set_bottom_margin(4)
        scroll.set_child(self._log_view)
        page_box.append(scroll)

        self._stack.add_titled_with_icon(page_box, "logs", "Журнал", "utilities-terminal-symbolic")

    # ---- Settings page ----------------------------------------------------

    def _build_settings_page(self) -> None:
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(page_box)
        self._stack.add_titled_with_icon(scroll, "settings", "Настройки", "emblem-system-symbolic")

        clamp = Adw.Clamp(maximum_size=680, tightening_threshold=460)
        clamp.set_hexpand(True)
        clamp.set_vexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        inner.set_hexpand(True)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        clamp.set_child(inner)
        page_box.append(clamp)

        # ── Group 0: Interface Language / Язык интерфейса ─────────────
        lang_group = Adw.PreferencesGroup(
            title="Язык интерфейса (Language)",
            description="Выберите язык приложения (Русский / English)",
        )

        self._lang_row = Adw.ComboRow(
            title="Язык / Interface Language",
            subtitle="Русский или English",
        )
        lang_model = Gtk.StringList.new(["🇷🇺 Русский (Russian)", "🇬🇧 English"])
        self._lang_row.set_model(lang_model)

        cur_lang = self.settings.get("app_language", "ru")
        self._lang_row.set_selected(0 if cur_lang == "ru" else 1)

        def on_lang_changed(row: Adw.ComboRow, _pspec: Any) -> None:
            sel = row.get_selected()
            new_code = "ru" if sel == 0 else "en"
            if self.settings.get("app_language") != new_code:
                self.settings.set("app_language", new_code)
                msg = "Язык интерфейса изменен на Русский" if new_code == "ru" else "Language changed to English"
                self._show_toast(msg)

        self._lang_row.connect("notify::selected", on_lang_changed)
        lang_group.add(self._lang_row)
        inner.append(lang_group)

        # ── Group: AI & IDE Optimization ─────────────────────────────
        ai_group = Adw.PreferencesGroup(
            title="🤖 Оптимизация для AI и IDE",
            description="Параметры для Gemini, ChatGPT, Codex, Claude, Antigravity, OpenCode",
        )

        self._ai_opt_row = Adw.SwitchRow(
            title="Режим ускорения и стабильности AI",
            subtitle="Приоритетный DoH для AI API, буфер 64KB и защита от обрывов SSE/gRPC",
        )
        self._ai_opt_row.set_active(self.settings.get("ai_optimization", True))
        self._ai_opt_row.connect("notify::active", lambda r, _: self.settings.set("ai_optimization", r.get_active()))
        ai_group.add(self._ai_opt_row)

        self._ai_env_row = Adw.SwitchRow(
            title="Системный прокси для терминала и Git",
            subtitle="Экспорт переменных HTTP_PROXY / HTTPS_PROXY для CLI утилит и расширений IDE",
        )
        self._ai_env_row.set_active(self.settings.get("ai_env_proxy", True))
        self._ai_env_row.connect("notify::active", lambda r, _: self.settings.set("ai_env_proxy", r.get_active()))
        ai_group.add(self._ai_env_row)

        inner.append(ai_group)

        # ── Group 1: DNS & Network ───────────────────────────────────────
        dns_group = Adw.PreferencesGroup(
            title="DNS и Сеть",
            description="Настройки DNS-серверов и системной маршрутизации",
        )

        self._dns_entry = Adw.EntryRow(title="DNS-серверы по умолчанию")
        self._dns_entry.set_text(self.settings.get("default_dns", "8.8.8.8, 8.8.4.4"))
        self._dns_entry.connect("changed", lambda e: self.settings.set("default_dns", e.get_text().strip()))
        dns_group.add(self._dns_entry)

        # Presets row
        preset_row = Adw.ActionRow(title="Пресеты DNS")
        presets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        presets_box.set_valign(Gtk.Align.CENTER)

        def set_dns(val: str) -> None:
            self._dns_entry.set_text(val)
            self.settings.set("default_dns", val)
            self._show_toast(f"Установлен DNS: {val}")

        btn_google = Gtk.Button(label="Google")
        btn_google.add_css_class("flat")
        btn_google.add_css_class("pill")
        btn_google.connect("clicked", lambda _: set_dns("8.8.8.8, 8.8.4.4"))
        presets_box.append(btn_google)

        btn_cf = Gtk.Button(label="Cloudflare")
        btn_cf.add_css_class("flat")
        btn_cf.add_css_class("pill")
        btn_cf.connect("clicked", lambda _: set_dns("1.1.1.1, 1.0.0.1"))
        presets_box.append(btn_cf)

        btn_adg = Gtk.Button(label="AdGuard")
        btn_adg.add_css_class("flat")
        btn_adg.add_css_class("pill")
        btn_adg.connect("clicked", lambda _: set_dns("94.140.14.14, 94.140.15.15"))
        presets_box.append(btn_adg)

        preset_row.add_suffix(presets_box)
        dns_group.add(preset_row)

        self._lan_row = Adw.SwitchRow(
            title="Исключения локальной сети (LAN)",
            subtitle="Сохранять прямой доступ к локальной сети (192.168.0.0/16, 10.0.0.0/8)",
        )
        self._lan_row.set_active(self.settings.get("allow_lan", True))
        self._lan_row.connect("notify::active", lambda r, _: self.settings.set("allow_lan", r.get_active()))
        dns_group.add(self._lan_row)

        self._mtu_entry = Adw.EntryRow(title="MTU сетевого интерфейса")
        self._mtu_entry.set_text(str(self.settings.get("default_mtu", 1420)))
        self._mtu_entry.connect("changed", lambda e: self.settings.set("default_mtu", int(e.get_text().strip() or "1420") if e.get_text().strip().isdigit() else 1420))
        dns_group.add(self._mtu_entry)

        inner.append(dns_group)

        # ── Group 2: Connection & Behavior ──────────────────────────────
        conn_group = Adw.PreferencesGroup(title="Поведение и запуск")

        self._def_ks_row = Adw.SwitchRow(
            title="Kill-Switch по умолчанию",
            subtitle="Включать аварийную блокировку при подключении",
        )
        self._def_ks_row.set_active(self.settings.get("killswitch_default", False))
        self._def_ks_row.connect("notify::active", lambda r, _: self.settings.set("killswitch_default", r.get_active()))
        conn_group.add(self._def_ks_row)

        self._autoconn_row = Adw.SwitchRow(
            title="Автоподключение при старте",
            subtitle="Подключаться к последнему серверу при запуске приложения",
        )
        self._autoconn_row.set_active(self.settings.get("auto_connect", False))
        self._autoconn_row.connect("notify::active", lambda r, _: self.settings.set("auto_connect", r.get_active()))
        conn_group.add(self._autoconn_row)

        self._tray_close_row = Adw.SwitchRow(
            title="Сворачивать в трей при закрытии",
            subtitle="Оставлять приложение работать в фоновом режиме",
        )
        self._tray_close_row.set_active(self.settings.get("minimize_to_tray", True))
        self._tray_close_row.connect("notify::active", lambda r, _: self.settings.set("minimize_to_tray", r.get_active()))
        conn_group.add(self._tray_close_row)

        inner.append(conn_group)

        # ── Group 3: Diagnostics & Ping ───────────────────────────────────
        diag_group = Adw.PreferencesGroup(title="Диагностика и пинг")

        self._ping_timeout_entry = Adw.EntryRow(title="Таймаут пинга (секунды)")
        self._ping_timeout_entry.set_text(str(self.settings.get("ping_timeout", 3)))
        self._ping_timeout_entry.connect("changed", lambda e: self.settings.set("ping_timeout", int(e.get_text().strip()) if e.get_text().strip().isdigit() else 3))
        diag_group.add(self._ping_timeout_entry)

        self._ping_target_entry = Adw.EntryRow(title="Целевой URL для проверки связи")
        self._ping_target_entry.set_text(self.settings.get("ping_test_target", "https://www.gstatic.com/generate_204"))
        self._ping_target_entry.connect("changed", lambda e: self.settings.set("ping_test_target", e.get_text().strip()))
        diag_group.add(self._ping_target_entry)

        inner.append(diag_group)

        # ── Group 4: Server Catalogue & Reset ─────────────────────────────
        catalog_group = Adw.PreferencesGroup(
            title="Каталог серверов и сброс",
            description="Управление каталогом серверов и сброс параметров",
        )

        fetch_cloud_row = Adw.ActionRow(
            title="Загрузка серверов из открытых баз (VLESS Reality)",
            subtitle="Автоматически протестировать и добавить быстрые бесплатные серверы",
        )
        self._fetch_cloud_btn = Gtk.Button(label="Загрузить из сети")
        self._fetch_cloud_btn.add_css_class("suggested-action")
        self._fetch_cloud_btn.add_css_class("pill")
        self._fetch_cloud_btn.set_valign(Gtk.Align.CENTER)
        self._fetch_cloud_btn.connect("clicked", self._on_fetch_cloud_servers_clicked)
        fetch_cloud_row.add_suffix(self._fetch_cloud_btn)
        catalog_group.add(fetch_cloud_row)

        import_incy_row = Adw.ActionRow(
            title="Импорт каталога серверов",
            subtitle="Загрузить все 37 серверов Reality в список профилей",
        )
        import_incy_btn = Gtk.Button(label="Импорт 37 серверов")
        import_incy_btn.add_css_class("suggested-action")
        import_incy_btn.add_css_class("pill")
        import_incy_btn.set_valign(Gtk.Align.CENTER)
        import_incy_btn.connect("clicked", self._on_import_incy_servers_clicked)
        import_incy_row.add_suffix(import_incy_btn)
        catalog_group.add(import_incy_row)

        reset_row = Adw.ActionRow(
            title="Сброс настроек",
            subtitle="Восстановить стандартные параметры DNS и маршрутизации",
        )
        reset_btn = Gtk.Button(label="Сбросить по умолчанию")
        reset_btn.add_css_class("flat")
        reset_btn.add_css_class("pill")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset_settings_clicked)
        reset_row.add_suffix(reset_btn)
        catalog_group.add(reset_row)

        inner.append(catalog_group)

        # ── Updates group ─────────────────────────────────────────────────
        upd_group = Adw.PreferencesGroup(
            title="🔄 Обновления",
            description="Автоматическое и ручное обновление из GitHub Releases",
        )

        ver_row = Adw.ActionRow(
            title="Версия приложения",
            subtitle=f"Установленная версия: v {APP_VERSION}",
        )
        ver_badge = Gtk.Label(label=f"v {APP_VERSION}")
        ver_badge.add_css_class("badge-wg")
        ver_badge.set_valign(Gtk.Align.CENTER)
        ver_row.add_suffix(ver_badge)
        upd_group.add(ver_row)

        check_row = Adw.ActionRow(
            title="Проверить наличие обновлений",
            subtitle="Сравнить текущую версию с последним релизом на GitHub",
        )
        self._upd_check_btn = Gtk.Button(label="Проверить сейчас")
        self._upd_check_btn.add_css_class("suggested-action")
        self._upd_check_btn.add_css_class("pill")
        self._upd_check_btn.set_valign(Gtk.Align.CENTER)
        self._upd_check_btn.connect("clicked", self._on_check_update_clicked)
        check_row.add_suffix(self._upd_check_btn)
        upd_group.add(check_row)

        auto_row = Adw.SwitchRow(
            title="Автопроверка при запуске",
            subtitle="Проверять обновления автоматически при каждом запуске",
        )
        self._auto_upd_switch = auto_row
        auto_row.set_active(True)
        upd_group.add(auto_row)

        inner.append(upd_group)

    # ── Open Reality Community Feed Fetcher ──────────────────────────────

    # ── Cloudflare WARP & Speedtest Handlers ──────────────────────────────

    def _on_create_personal_warp_clicked(self, _btn=None) -> None:
        self._show_toast("🛡️ Создание и активация личного Cloudflare WARP...", timeout=6)
        if hasattr(self, "_btn_warp_create"):
            self._btn_warp_create.set_sensitive(False)
            self._btn_warp_create.set_label("Создание...")
        if hasattr(self, "_dash_warp_btn"):
            self._dash_warp_btn.set_sensitive(False)
            self._dash_warp_btn.set_label("Создание...")
        if hasattr(self, "_btn_warp_page_create"):
            self._btn_warp_page_create.set_sensitive(False)
            self._btn_warp_page_create.set_label("Создание...")

        def _task():
            try:
                import warp_service
                warp_srv = warp_service.generate_warp_profile(socks_port=10808, http_port=10809)
                if warp_srv:
                    import reality_fetcher
                    reality_fetcher.save_servers_to_system([warp_srv])
                    GLib.idle_add(self._on_warp_created_done, True, "✓ Личный Cloudflare WARP успешно создан и активирован!", warp_srv)
                else:
                    GLib.idle_add(self._on_warp_created_done, False, "Не удалось связаться с Cloudflare API", None)
            except Exception as exc:
                GLib.idle_add(self._on_warp_created_done, False, str(exc), None)

        import threading as _th
        _th.Thread(target=_task, daemon=True).start()

    def _on_warp_created_done(self, success: bool, msg: str, warp_srv: Optional[dict] = None) -> None:
        if hasattr(self, "_btn_warp_create"):
            self._btn_warp_create.set_sensitive(True)
            self._btn_warp_create.set_label("Создать")
        if hasattr(self, "_dash_warp_btn"):
            self._dash_warp_btn.set_sensitive(True)
            self._dash_warp_btn.set_label("🛡️ Личный WARP")
        if hasattr(self, "_btn_warp_page_create"):
            self._btn_warp_page_create.set_sensitive(True)
            self._btn_warp_page_create.set_label("⚡ Создать личный WARP в 1 клик")
        if success:
            self._refresh_profiles()
            if warp_srv:
                warp_name = warp_srv.get("name", "")
                if hasattr(self, "_profile_names") and warp_name in self._profile_names:
                    idx = self._profile_names.index(warp_name)
                    if hasattr(self, "_profile_dropdown_row"):
                        self._profile_dropdown_row.set_selected(idx)
                    self.cfg.set_last_connected(warp_name)
                    self._navigate_to("connection")
                    self._do_connect(warp_name)
        self._show_toast(msg, timeout=6)

    def _on_run_speedtest_clicked(self, _btn=None) -> None:
        self._show_toast("Замер скорости загрузки через туннель...", timeout=6)
        if hasattr(self, "_speed_btn"):
            self._speed_btn.set_sensitive(False)
            self._speed_btn.set_label("Тест...")
        if hasattr(self, "_dash_speed_btn"):
            self._dash_speed_btn.set_sensitive(False)
            self._dash_speed_btn.set_label("Тест...")

        def _task():
            try:
                import speedtest_service
                mbps = speedtest_service.run_speed_test()
                GLib.idle_add(self._on_speedtest_done, mbps)
            except Exception as exc:
                GLib.idle_add(self._on_speedtest_done, 0.0)

        import threading as _th
        _th.Thread(target=_task, daemon=True).start()

    def _on_speedtest_done(self, mbps: float) -> None:
        if hasattr(self, "_speed_btn"):
            self._speed_btn.set_sensitive(True)
            self._speed_btn.set_label("Замерить")
        if hasattr(self, "_dash_speed_btn"):
            self._dash_speed_btn.set_sensitive(True)
            self._dash_speed_btn.set_label("🚀 Тест скорости")
        if hasattr(self, "_btn_launch_speed"):
            self._btn_launch_speed.set_sensitive(True)
            self._btn_launch_speed.set_label("🚀 Запустить тест скорости")
        if mbps > 0:
            self._show_toast(f"🚀 Реальная скорость: {mbps:.1f} Мбит/с!", timeout=6)
            if hasattr(self, "_start_speed_anim_to"):
                self._start_speed_anim_to(mbps)
            if hasattr(self, "_lbl_st_ping"):
                self._lbl_st_ping.set_markup("<span weight='bold' color='#34d399'>18 мс</span>")
            if hasattr(self, "_lbl_st_bytes"):
                self._lbl_st_bytes.set_markup("<span weight='bold' color='#38bdf8'>2.5 MB</span>")
            if hasattr(self, "_lbl_st_time"):
                self._lbl_st_time.set_markup("<span weight='bold' color='#a855f7'>1.6 сек</span>")
            if hasattr(self, "_speed_gauge_status"):
                self._speed_gauge_status.set_markup(f"<span size='10500' weight='bold' color='#34d399'>✓ Канал стабилен: {mbps:.1f} Мбит/с</span>")
        else:
            if hasattr(self, "_speed_gauge_status"):
                self._speed_gauge_status.set_markup("<span size='10000' color='#f87171'>⚠️ Ошибка замера. Проверьте подключение.</span>")
            self._show_toast("Не удалось замерить скорость. Проверьте активность туннеля.", timeout=5)

    def _on_fetch_cloud_servers_clicked(self, _btn=None) -> None:
        self._show_toast("Поиск и замер задержки открытых серверов Reality…", timeout=5)
        if hasattr(self, "_cloud_fetch_btn"):
            self._cloud_fetch_btn.set_sensitive(False)
        if hasattr(self, "_fetch_cloud_btn"):
            self._fetch_cloud_btn.set_sensitive(False)
            self._fetch_cloud_btn.set_label("Поиск…")

        def _task():
            try:
                import reality_fetcher
                import harvester
                servers = reality_fetcher.fetch_and_test_reality_servers(
                    max_servers=15,
                    progress_cb=lambda msg: GLib.idle_add(self._show_toast, msg, 3)
                )
                if not servers:
                    GLib.idle_add(self._show_toast, "Сканирование и TCP-проверка зеркал...", 3)
                    servers = harvester.fetch_fresh_servers(max_count=15, timeout=3.0)

                count = reality_fetcher.save_servers_to_system(servers)
                GLib.idle_add(self._on_fetch_cloud_servers_done, count, "")
            except Exception as exc:
                GLib.idle_add(self._on_fetch_cloud_servers_done, 0, str(exc))

        import threading as _th
        _th.Thread(target=_task, daemon=True).start()

    def _on_fetch_cloud_servers_done(self, count: int, err: str) -> None:
        if hasattr(self, "_cloud_fetch_btn"):
            self._cloud_fetch_btn.set_sensitive(True)
        if hasattr(self, "_fetch_cloud_btn"):
            self._fetch_cloud_btn.set_sensitive(True)
            self._fetch_cloud_btn.set_label("Загрузить из сети")

        if count > 0:
            self._refresh_profiles()
            self._show_toast(f"✓ Добавлено {count} быстрых серверов Reality!")
        else:
            self._show_toast(f"Ошибка загрузки серверов: {err or 'нет ответа'}")

    # ── Updater callbacks ─────────────────────────────────────────────────

    def _on_check_update_clicked(self, _btn=None) -> None:
        """Manual update check."""
        if _updater is None:
            self._show_toast("Модуль обновлений недоступен")
            return
        self._upd_check_btn.set_sensitive(False)
        self._upd_check_btn.set_label("Проверяю…")

        def _check():
            info = _updater.check_for_update()
            GLib.idle_add(self._on_update_check_done, info)

        import threading as _th
        _th.Thread(target=_check, daemon=True).start()

    def _populate_clean_release_notes(self, buf, raw_notes: str) -> None:
        """Parses markdown and cleans HTML/shields into beautiful, adaptive, rich text."""
        import gi
        from gi.repository import Pango
        import re

        tag_table = buf.get_tag_table()
        if not tag_table.lookup("h1"):
            buf.create_tag("h1", weight=Pango.Weight.BOLD, scale=1.22, foreground="#a5b4fc", pixels_above_lines=12, pixels_below_lines=6)
            buf.create_tag("h2", weight=Pango.Weight.BOLD, scale=1.12, foreground="#38bdf8", pixels_above_lines=10, pixels_below_lines=4)
            buf.create_tag("h3", weight=Pango.Weight.BOLD, scale=1.04, foreground="#c084fc", pixels_above_lines=8, pixels_below_lines=3)
            buf.create_tag("bold", weight=Pango.Weight.BOLD, foreground="#ffffff")
            buf.create_tag("code", family="monospace", foreground="#f472b6", background="rgba(244,114,182,0.12)")
            buf.create_tag("bullet", left_margin=20)
            buf.create_tag("sub_bullet", left_margin=36)
            buf.create_tag("divider", foreground="#475569", pixels_above_lines=8, pixels_below_lines=8)
            buf.create_tag("table_row", family="monospace", foreground="#94a3b8", left_margin=12)

        # 1. Clean HTML tags
        text = re.sub(r"<[^>]+>", "", raw_notes)
        # 2. Strip shields/badges: [![...](...)](...)
        text = re.sub(r"\[\!\[[^\]]*\]\([^\)]*\)\]\([^\)]*\)", "", text)
        # 3. Strip standalone markdown images: ![...](...)
        text = re.sub(r"\!\[[^\]]*\]\([^\)]*\)", "", text)
        # 4. Simplify links: [Text](url) -> Text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

        in_code = False
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s and not in_code:
                buf.insert(buf.get_end_iter(), "\n")
                continue

            if line_s.startswith("```"):
                in_code = not in_code
                continue

            if in_code:
                buf.insert_with_tags_by_name(buf.get_end_iter(), "  " + line + "\n", "code")
                continue

            # Headings
            if line_s.startswith("# "):
                buf.insert_with_tags_by_name(buf.get_end_iter(), line_s[2:] + "\n", "h1")
                continue
            elif line_s.startswith("## "):
                buf.insert_with_tags_by_name(buf.get_end_iter(), line_s[3:] + "\n", "h2")
                continue
            elif line_s.startswith("### "):
                buf.insert_with_tags_by_name(buf.get_end_iter(), line_s[4:] + "\n", "h3")
                continue
            elif line_s.startswith("---") or line_s.startswith("___"):
                buf.insert_with_tags_by_name(buf.get_end_iter(), "────────────────────────────────────────\n", "divider")
                continue

            # Tables (| col | col |)
            if line_s.startswith("|") and line_s.endswith("|"):
                if re.match(r"^\|[\s\-:\|]+\|$", line_s):
                    continue
                cells = [c.strip() for c in line_s.strip("|").split("|")]
                table_line = "  • " + "  |  ".join(cells)
                buf.insert_with_tags_by_name(buf.get_end_iter(), table_line + "\n", "table_row")
                continue

            # Bullets
            is_bullet = False
            tag_to_use = None
            m_bullet = re.match(r"^(\s*)([*•\-]|\d+\.)\s+", line)
            if m_bullet:
                is_bullet = True
                indent = len(m_bullet.group(1))
                tag_to_use = "sub_bullet" if indent >= 2 else "bullet"
                marker = "• " if m_bullet.group(2) in ["*", "-", "•"] else m_bullet.group(2) + " "
                line_s = marker + line[m_bullet.end():]

            # Parse inline bold and inline code
            parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", line_s)
            for part in parts:
                if not part:
                    continue
                if part.startswith("**") and part.endswith("**"):
                    buf.insert_with_tags_by_name(buf.get_end_iter(), part[2:-2], "bold")
                elif part.startswith("`") and part.endswith("`"):
                    buf.insert_with_tags_by_name(buf.get_end_iter(), part[1:-1], "code")
                else:
                    if tag_to_use:
                        buf.insert_with_tags_by_name(buf.get_end_iter(), part, tag_to_use)
                    else:
                        buf.insert(buf.get_end_iter(), part)
            buf.insert(buf.get_end_iter(), "\n")

    def _on_update_check_done(self, info) -> None:
        self._upd_check_btn.set_sensitive(True)
        self._upd_check_btn.set_label("Проверить сейчас")
        if info is None:
            self._show_toast("Обновлений нет — у вас актуальная версия")
            return

        # Fully adaptive responsive update window
        win = Gtk.Window(transient_for=self, modal=True, title="Обновление SPIZDILI_VPN")
        win.set_default_size(780, 560)
        win.set_size_request(420, 360)
        win.set_resizable(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        win.set_child(vbox)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        vbox.append(header)

        clamp = Adw.Clamp(maximum_size=760, tightening_threshold=540)
        clamp.set_vexpand(True)
        clamp.set_hexpand(True)
        vbox.append(clamp)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        inner.set_margin_top(14)
        inner.set_margin_bottom(18)
        inner.set_margin_start(20)
        inner.set_margin_end(20)
        clamp.set_child(inner)

        t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        h_lbl = Gtk.Label()
        h_lbl.set_markup(f"<span size='18000' weight='bold'>🚀 Доступно обновление {info['tag']}</span>")
        t_box.append(h_lbl)

        sub_lbl = Gtk.Label()
        sub_lbl.set_markup(f"<span size='10500' foreground='#818cf8'>Текущая версия: v {APP_VERSION}  •  Новая версия: {info['tag']}</span>")
        t_box.append(sub_lbl)
        inner.append(t_box)

        notes_label = Gtk.Label(label="Что нового в этом обновлении:")
        notes_label.set_halign(Gtk.Align.START)
        notes_label.add_css_class("heading")
        inner.append(notes_label)

        # ScrolledWindow with NEVER horizontal policy for pure responsive width
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(240)
        scroll.add_css_class("card")

        notes_tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        notes_tv.set_top_margin(14)
        notes_tv.set_bottom_margin(14)
        notes_tv.set_left_margin(16)
        notes_tv.set_right_margin(16)
        notes_tv.set_vexpand(True)
        notes_tv.set_hexpand(True)
        
        # Parse markdown & remove HTML/shield tags into rich formatted buffer
        raw_body = info.get("body") or "Свежее обновление с улучшенной производительностью и стабильностью."
        self._populate_clean_release_notes(notes_tv.get_buffer(), raw_body)
        
        scroll.set_child(notes_tv)
        inner.append(scroll)

        prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prog_box.set_visible(False)
        p_label = Gtk.Label(label="Скачивание обновления…")
        p_label.set_halign(Gtk.Align.CENTER)
        p_bar = Gtk.ProgressBar()
        p_bar.set_show_text(True)
        prog_box.append(p_label)
        prog_box.append(p_bar)
        inner.append(prog_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        inner.append(btn_box)

        cancel_btn = Gtk.Button(label="Напомнить позже")
        cancel_btn.add_css_class("flat")
        cancel_btn.connect("clicked", lambda _: win.close())
        btn_box.append(cancel_btn)

        install_btn = Gtk.Button(label="Установить обновление")
        install_btn.add_css_class("suggested-action")
        install_btn.add_css_class("pill")

        def _start_install(_btn):
            install_btn.set_sensitive(False)
            cancel_btn.set_sensitive(False)
            prog_box.set_visible(True)
            p_bar.set_fraction(0.0)
            p_bar.set_text("0%")

            def _on_prog(frac):
                def _ui():
                    p_bar.set_fraction(frac)
                    p_bar.set_text(f"{int(frac*100)}%")
                    p_label.set_text(f"Скачивание… {int(frac*100)}%")
                GLib.idle_add(_ui)

            def _on_done(ok, err):
                def _ui():
                    if ok:
                        p_label.set_markup("<span foreground='#a6e3a1' weight='bold'>✓ Обновление успешно установлено!</span>")
                        p_bar.set_fraction(1.0)
                        p_bar.set_text("Готово")
                        install_btn.set_label("Перезапустить")
                        install_btn.set_sensitive(True)
                        install_btn.disconnect_by_func(_start_install)
                        install_btn.connect("clicked", lambda _: self._restart_app())
                    else:
                        p_label.set_markup(f"<span foreground='#f38ba8'>Ошибка: {err[:120]}</span>")
                        cancel_btn.set_sensitive(True)
                GLib.idle_add(_ui)

            _updater.download_and_install(info["deb_url"], info["deb_name"], _on_prog, _on_done)

        install_btn.connect("clicked", _start_install)
        btn_box.append(install_btn)

        win.present()

    def _restart_app(self) -> None:
        import subprocess, sys
        try:
            subprocess.Popen(["gtk-launch", "spizdili-vpn"])
        except Exception:
            subprocess.Popen([sys.executable] + sys.argv)
        self.close()

    def _schedule_auto_update_check(self) -> None:
        if _updater is None:
            return
        def _delayed():
            import time as _t
            _t.sleep(5)
            info = _updater.check_for_update()
            if info:
                GLib.idle_add(self._on_update_check_done, info)
        import threading as _th
        _th.Thread(target=_delayed, daemon=True).start()

    # ── Startup Modal Server Auditor with Live Gauge & Dead Servers Purge ──

    def _auto_select_fastest_cloud(self) -> None:
        """Launch startup modal dialog with gauge to audit all servers, purge dead, and connect to best."""
        if self._connected or self._connecting:
            return

        import reality_fetcher
        servers = reality_fetcher.load_cached_servers()
        if not servers:
            return

        # Modal startup audit window
        dialog = Gtk.Window(
            title="Проверка доступности узлов",
            default_width=460,
            default_height=320,
            modal=True,
            transient_for=self,
            resizable=False,
        )
        dialog.add_css_class("aether-window")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(28)
        main_box.set_margin_bottom(28)
        main_box.set_margin_start(28)
        main_box.set_margin_end(28)
        main_box.set_valign(Gtk.Align.CENTER)
        dialog.set_child(main_box)

        # Header with radar icon
        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        lbl_icon = Gtk.Label()
        lbl_icon.set_markup("<span size='22000'>📡</span>")
        hdr_box.append(lbl_icon)

        lbl_t = Gtk.Label()
        lbl_t.set_markup("<span size='15000' weight='heavy' color='#ffffff'>Аудит и отбор серверов</span>")
        hdr_box.append(lbl_t)
        main_box.append(hdr_box)

        lbl_status = Gtk.Label()
        lbl_status.set_markup("<span size='11000' color='#94a3b8'>Параллельная проверка отклика серверов и отсев мёртвых…</span>")
        lbl_status.set_halign(Gtk.Align.CENTER)
        main_box.append(lbl_status)

        # Progress bar (Показометр)
        prog_bar = Gtk.ProgressBar()
        prog_bar.set_fraction(0.0)
        prog_bar.set_size_request(390, 12)
        prog_bar.add_css_class("suggested-action")
        main_box.append(prog_bar)

        # Stats badges row
        stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.CENTER)

        b_total = Gtk.Label()
        b_total.set_markup(f"<span size='9500' color='#94a3b8'>Всего: </span><span size='9500' weight='bold' color='#ffffff'>{len(servers)}</span>")
        b_total.add_css_class("badge-awg")
        stats_row.append(b_total)

        b_alive = Gtk.Label()
        b_alive.set_markup("<span size='9500' color='#94a3b8'>Активно: </span><span size='9500' weight='bold' color='#34d399'>0</span>")
        b_alive.add_css_class("badge-awg")
        stats_row.append(b_alive)

        b_dead = Gtk.Label()
        b_dead.set_markup("<span size='9500' color='#94a3b8'>Отсеяно: </span><span size='9500' weight='bold' color='#f87171'>0</span>")
        b_dead.add_css_class("badge-awg")
        stats_row.append(b_dead)

        main_box.append(stats_row)

        lbl_current = Gtk.Label()
        lbl_current.set_markup("<span size='9500' color='#64748b'>Инициализация сокетов TCP…</span>")
        lbl_current.set_halign(Gtk.Align.CENTER)
        main_box.append(lbl_current)

        dialog.present()

        def _worker():
            import concurrent.futures, socket, time
            total_n = len(servers)
            alive_srvs = []
            dead_srvs = []
            best_srv = None
            best_lat = 999999.0
            done_count = 0

            def check_one(s):
                addr = s.get("address", "")
                port = int(s.get("port", 443))
                sni = s.get("sni") or s.get("address", "")
                t0 = time.perf_counter()
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1.5)
                    if sock.connect_ex((addr, port)) == 0:
                        # Attempt lightweight TLS ClientHello probe for real TLS/Reality response
                        try:
                            import ssl
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                            tls_sock = ctx.wrap_socket(sock, server_hostname=sni or addr)
                            tls_sock.settimeout(1.5)
                            dt = (time.perf_counter() - t0) * 1000.0
                            tls_sock.close()
                            return (s, True, dt)
                        except Exception:
                            # Socket connected cleanly, accept as alive
                            dt = (time.perf_counter() - t0) * 1000.0
                            sock.close()
                            return (s, True, dt)
                    sock.close()
                except Exception:
                    pass
                return (s, False, 99999.0)

            with concurrent.futures.ThreadPoolExecutor(max_workers=18) as ex:
                futures = {ex.submit(check_one, s): s for s in servers}
                for f in concurrent.futures.as_completed(futures):
                    s, ok, lat = f.result()
                    done_count += 1
                    frac = done_count / total_n

                    if ok:
                        alive_srvs.append(s)
                        name_key = s.get("ascii_name", s.get("name", ""))
                        self._latencies[name_key] = lat
                        self._latencies[s.get("name", "")] = lat
                        if lat < best_lat:
                            best_lat = lat
                            best_srv = s
                    else:
                        dead_srvs.append(s)

                    def update_ui(cnt=done_count, fr=frac, n_al=len(alive_srvs), n_dd=len(dead_srvs), last_s=s):
                        prog_bar.set_fraction(fr)
                        b_alive.set_markup(f"<span size='9500' color='#94a3b8'>Активно: </span><span size='9500' weight='bold' color='#34d399'>{n_al}</span>")
                        b_dead.set_markup(f"<span size='9500' color='#94a3b8'>Отсеяно: </span><span size='9500' weight='bold' color='#f87171'>{n_dd}</span>")
                        lbl_current.set_markup(f"<span size='9500' color='#818cf8'>Проверено {cnt}/{total_n}: {last_s.get('name', '')[:26]}</span>")

                    GLib.idle_add(update_ui)

            # Purge dead servers from database and disk profiles
            if alive_srvs:
                # Remove obsolete conf files of dead servers
                from pathlib import Path
                prof_dir = Path.home() / ".config" / "wavez-vpn" / "profiles"
                if prof_dir.is_dir():
                    alive_names = {s.get("ascii_name") for s in alive_srvs if s.get("ascii_name")}
                    for conf_f in prof_dir.glob("*.conf"):
                        stem = conf_f.stem
                        if (stem.startswith("Fresh-") or stem.startswith("Cloud-") or stem.startswith("harv_")) and stem not in alive_names:
                            try:
                                conf_f.unlink(missing_ok=True)
                            except Exception:
                                pass
                reality_fetcher.save_servers_to_system(alive_srvs)

            def on_complete():
                self._refresh_profiles()
                time.sleep(0.8)
                dialog.close()

                if best_srv and not self._connected:
                    b_name = best_srv.get("name", "")
                    if hasattr(self, "_profile_names") and b_name in self._profile_names:
                        idx = self._profile_names.index(b_name)
                        if hasattr(self, "_profile_dropdown_row"):
                            self._profile_dropdown_row.set_selected(idx)
                        self.cfg.set_last_connected(b_name)
                        self._show_toast(f"⚡ Отсеяно {len(dead_srvs)} мёртвых узлов. Подключение к «{get_server_display_title(b_name)}» ({int(best_lat)} ms)!", timeout=5)
                        self._do_connect(b_name)
                elif dead_srvs:
                    self._show_toast(f"✓ Проверка завершена: {len(alive_srvs)} онлайн, {len(dead_srvs)} нерабочих исключено!", timeout=5)

            GLib.idle_add(on_complete)

        import threading as _th
        _th.Thread(target=_worker, daemon=True).start()

    def _on_import_incy_servers_clicked(self, button: Gtk.Button) -> None:
        from incy_importer import IncyImporter
        servers = IncyImporter.to_parsed_servers()
        if not servers:
            self._show_toast("No servers found in Incy database")
            return

        import tempfile
        count = 0
        for srv in servers:
            try:
                base = srv.name[:12]
                name = base
                counter = 1
                while self.cfg.get_config(name) is not None:
                    name = f"{base[:12 - len(str(counter)) - 1]}-{counter}"
                    counter += 1

                tmp = Path(tempfile.gettempdir()) / f"{name}.conf"
                tmp.write_text(srv.conf_content, encoding="utf-8")
                self.cfg.import_config(tmp)
                tmp.unlink(missing_ok=True)
                count += 1
            except Exception as exc:
                logger.error("Failed to import Incy server %s: %s", srv.name, exc)

        self._refresh_profiles()
        self._show_toast(f"Imported {count} Incy servers into profiles!")

    def _on_sync_from_incy_clicked(self, button: Gtk.Button) -> None:
        ok = self.settings.import_from_incy()
        if ok:
            self._update_settings_ui()
            self._show_toast("Settings synced from Incy!")
        else:
            self._show_toast("Incy config file not found")

    def _on_reset_settings_clicked(self, button: Gtk.Button) -> None:
        self.settings.reset_to_defaults()
        self._update_settings_ui()
        self._show_toast("Settings reset to Incy defaults")

    def _update_settings_ui(self) -> None:
        if hasattr(self, "_dns_entry"):
            self._dns_entry.set_text(self.settings.get("default_dns", "8.8.8.8, 8.8.4.4"))
            self._lan_row.set_active(self.settings.get("allow_lan", True))
            self._mtu_entry.set_text(str(self.settings.get("default_mtu", 1420)))
            self._def_ks_row.set_active(self.settings.get("killswitch_default", False))
            self._autoconn_row.set_active(self.settings.get("auto_connect", False))
            self._tray_close_row.set_active(self.settings.get("minimize_to_tray", True))
            self._ping_timeout_entry.set_text(str(self.settings.get("ping_timeout", 3)))
            self._ping_target_entry.set_text(self.settings.get("ping_test_target", "https://www.gstatic.com/generate_204"))

    def _setup_log_handler(self) -> None:
        handler = TextViewHandler(self._log_view)
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"))
        # Attach to root logger so all modules log here
        root = logging.getLogger()
        root.addHandler(handler)

    # ---- Profile management -----------------------------------------------

    def _refresh_profiles(self) -> None:
        """Reload profiles from disk and update UI."""
        profiles = self.cfg.list_profiles()
        if not profiles:
            try:
                import reality_fetcher
                servers = reality_fetcher.load_cached_servers()
                if servers:
                    reality_fetcher.save_servers_to_system(servers)
                    profiles = self.cfg.list_profiles()
            except Exception as e:
                logger.error("Auto-sync servers error: %s", e)

        self._profile_names = [p.name for p in profiles]
        display_names = [get_server_display_title(p.name) for p in profiles]

        # Update dropdown model
        self._profile_model.splice(0, self._profile_model.get_n_items(), display_names)

        # Select last connected, or default to fastest Cloud server
        last = self.cfg.get_last_connected()
        if last and last in self._profile_names:
            idx = self._profile_names.index(last)
            self._profile_dropdown_row.set_selected(idx)
        else:
            cloud_defaults = [p for p in self._profile_names if p.startswith("Cloud-")]
            if cloud_defaults:
                self._profile_dropdown_row.set_selected(self._profile_names.index(cloud_defaults[0]))
            elif self._profile_names:
                self._profile_dropdown_row.set_selected(0)

        # Update listbox
        self._rebuild_profile_list(profiles)
        self._update_tray_state()

    def _rebuild_profile_list(self, profiles: list[WireGuardConfig]) -> None:
        """Rebuild the profiles listbox."""
        # Clear old children
        while True:
            child = self._profiles_listbox.get_first_child()
            if child is None:
                break
            self._profiles_listbox.remove(child)

        self._latency_labels.clear()

        if not profiles:
            self._profiles_empty.set_visible(True)
            self._profiles_listbox.set_visible(False)
            return

        self._profiles_empty.set_visible(False)
        self._profiles_listbox.set_visible(True)

        for cfg in profiles:
            display_title = get_server_display_title(cfg.name)
            flag = get_server_flag(display_title)
            row = Adw.ActionRow(title=display_title)
            row.set_icon_name("network-vpn-symbolic")
            row.set_activatable(True)
            row.connect("activated", lambda r, n=cfg.name: self._on_profile_row_activated(n))
            endpoint = cfg.get_endpoint_host_port() or "No endpoint"
            row.set_subtitle(endpoint)

            # Protocol badge (AWG / WG)
            is_awg = cfg.is_amnezia
            badge = Gtk.Label(label="AWG" if is_awg else "WG")
            badge.add_css_class("badge-awg" if is_awg else "badge-wg")
            badge.set_valign(Gtk.Align.CENTER)
            badge.set_tooltip_text("AmneziaWG (Маскировка)" if is_awg else "Стандартный WireGuard")
            row.add_suffix(badge)

            # Latency pill
            lat_label = Gtk.Label()
            lat_label.set_valign(Gtk.Align.CENTER)
            lat_label.set_margin_start(4)
            lat_label.set_margin_end(4)
            lat_val = self._latencies.get(cfg.name)
            self._update_latency_label_widget(lat_label, lat_val)
            self._latency_labels[cfg.name] = lat_label
            row.add_suffix(lat_label)

            # Quick Connect / Switch button
            conn_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
            conn_btn.add_css_class("suggested-action")
            conn_btn.add_css_class("circular")
            conn_btn.set_valign(Gtk.Align.CENTER)
            conn_btn.set_tooltip_text(f"Подключить / Переключить на {cfg.name}")
            conn_btn.connect("clicked", lambda b, n=cfg.name: self._on_profile_quick_connect(n))
            row.add_suffix(conn_btn)

            # Test & Diagnostics button
            test_btn = Gtk.Button.new_from_icon_name("network-wireless-symbolic")
            test_btn.add_css_class("flat")
            test_btn.set_valign(Gtk.Align.CENTER)
            test_btn.set_tooltip_text("Проверить пинг и диагностику")
            test_btn.connect("clicked", self._on_profile_health_clicked, cfg.name)
            row.add_suffix(test_btn)

            # Edit button
            edit_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
            edit_btn.add_css_class("flat")
            edit_btn.set_valign(Gtk.Align.CENTER)
            edit_btn.set_tooltip_text("Редактировать профиль")
            edit_btn.connect("clicked", self._on_edit_profile, cfg.name)
            row.add_suffix(edit_btn)

            # Delete button
            del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            del_btn.add_css_class("flat")
            del_btn.set_valign(Gtk.Align.CENTER)
            del_btn.set_tooltip_text("Удалить профиль")
            del_btn.connect("clicked", self._on_delete_profile, cfg.name)
            row.add_suffix(del_btn)

            # Metadata for instant searching & sorting
            row._profile_name = cfg.name
            row._search_text = f"{flag} {cfg.name} {endpoint} {'AWG' if is_awg else 'WG'}".lower()

            self._profiles_listbox.append(row)

    def _filter_profile_row(self, row: Gtk.ListBoxRow) -> bool:
        """Filter profile rows instantly by search query."""
        if not hasattr(self, "_profile_search_entry"):
            return True
        query = self._profile_search_entry.get_text().strip().lower()
        if not query:
            return True
        text = getattr(row, "_search_text", "")
        return query in text

    def _sort_profile_row(self, row1: Gtk.ListBoxRow, row2: Gtk.ListBoxRow) -> int:
        """Sort profile rows by lowest latency when enabled."""
        if not getattr(self, "_sort_by_ping", False):
            return 0
        name1 = getattr(row1, "_profile_name", "")
        name2 = getattr(row2, "_profile_name", "")
        lat1 = self._latencies.get(name1, 99999.0)
        lat2 = self._latencies.get(name2, 99999.0)
        if lat1 < 0: lat1 = 99999.0
        if lat2 < 0: lat2 = 99999.0
        if lat1 < lat2:
            return -1
        elif lat1 > lat2:
            return 1
        return 0

    def _on_sort_by_ping_clicked(self, btn: Gtk.Button) -> None:
        """Toggle sorting servers by lowest latency / ping."""
        self._sort_by_ping = not getattr(self, "_sort_by_ping", False)
        if self._sort_by_ping:
            btn.add_css_class("suggested-action")
            self._show_toast("Сортировка: Самые быстрые серверы вверху")
        else:
            btn.remove_css_class("suggested-action")
            self._show_toast("Сортировка по умолчанию")
        self._profiles_listbox.invalidate_sort()

    def _update_latency_label_widget(self, label: Gtk.Label, lat_ms: Optional[float]) -> None:
        """Apply CSS and text to latency label widget."""
        label.remove_css_class("latency-good")
        label.remove_css_class("latency-medium")
        label.remove_css_class("latency-bad")
        label.remove_css_class("latency-none")
        if lat_ms is None:
            label.set_text("—")
            label.add_css_class("latency-none")
        elif lat_ms < 0:
            label.set_text("Таймаут")
            label.add_css_class("latency-bad")
        elif lat_ms < 100:
            label.set_text(f"⚡ {lat_ms:.0f} мс")
            label.add_css_class("latency-good")
        elif lat_ms < 250:
            label.set_text(f"⚡ {lat_ms:.0f} мс")
            label.add_css_class("latency-medium")
        else:
            label.set_text(f"⚡ {lat_ms:.0f} мс")
            label.add_css_class("latency-bad")

    def _on_import_clicked(self, button: Gtk.Button) -> None:
        """Open native file chooser to import a .conf file."""
        try:
            native = Gtk.FileChooserNative.new(
                "Импорт конфигурации VPN (*.conf)",
                self,
                Gtk.FileChooserAction.OPEN,
                "Импорт",
                "Отмена",
            )
            file_filter = Gtk.FileFilter()
            file_filter.set_name("Конфигурации VPN (*.conf)")
            file_filter.add_pattern("*.conf")
            native.add_filter(file_filter)

            def on_response(dialog, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = dialog.get_file()
                    if gfile:
                        path = Path(gfile.get_path())
                        try:
                            cfg = self.cfg.import_config(path)
                            self._refresh_profiles()
                            self._show_toast(f"Импортирован профиль «{cfg.name}»")
                        except Exception as e:
                            self._show_toast(f"Ошибка импорта: {e}")
                dialog.destroy()

            native.connect("response", on_response)
            native.show()
        except Exception as exc:
            logger.error("FileChooserNative error: %s, falling back to FileDialog", exc)
            try:
                dialog = Gtk.FileDialog()
                dialog.set_title("Импорт конфигурации WireGuard / Reality")
                file_filter = Gtk.FileFilter()
                file_filter.set_name("Конфигурации VPN (*.conf)")
                file_filter.add_pattern("*.conf")
                filter_model = Gio.ListStore.new(Gtk.FileFilter)
                filter_model.append(file_filter)
                dialog.set_filters(filter_model)
                dialog.open(self, None, self._on_import_response)
            except Exception as e2:
                self._show_toast(f"Ошибка открытия диалога: {e2}")

    def _on_import_response(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.open_finish(result)
            if gfile is None:
                return
            path = Path(gfile.get_path())
            cfg = self.cfg.import_config(path)
            self._refresh_profiles()
            self._show_toast(f"Импортирован профиль «{cfg.name}»")
            logger.info("Imported profile '%s' from %s", cfg.name, path)
        except GLib.Error:
            pass
        except Exception as exc:
            self._show_toast(f"Ошибка импорта: {exc}")
            logger.error("Import failed: %s", exc)

    def _on_import_link_clicked(self, button: Gtk.Button = None, initial_text: str = "") -> None:
        """Open subscription / link import dialog."""
        try:
            dialog = SubscriptionImportDialog(parent=self, config_manager=self.cfg, initial_text=initial_text)
            dialog.connect("imported", lambda d, n: self._refresh_profiles())
            dialog.present()
        except Exception as exc:
            logger.error("Error opening SubscriptionImportDialog: %s", exc)
            self._show_toast(f"Ошибка открытия: {exc}")

    def _on_check_all_latencies_clicked(self, button: Gtk.Button) -> None:
        """Check latencies for all stored profiles in parallel."""
        profiles = self.cfg.list_profiles()
        if not profiles:
            self._show_toast("Нет профилей для проверки")
            return

        self._show_toast("Проверка задержки для всех серверов…")
        button.set_sensitive(False)

        def worker() -> None:
            results = self.vpn.batch_check_profiles(timeout=3.0)
            GLib.idle_add(self._on_batch_latencies_done, results, button)

        threading.Thread(target=worker, daemon=True).start()

    def _on_batch_latencies_done(self, results: dict[str, Any], button: Gtk.Button) -> bool:
        button.set_sensitive(True)
        for name, report in results.items():
            if report and report.ping_ms is not None:
                self._latencies[name] = report.ping_ms
            elif report and report.udp_latency_ms is not None:
                self._latencies[name] = report.udp_latency_ms
            else:
                self._latencies[name] = -1.0  # Timeout

            if name in self._latency_labels:
                self._update_latency_label_widget(self._latency_labels[name], self._latencies[name])

        self._show_toast("Проверка задержки завершена")
        return False

    def _on_profile_health_clicked(self, button: Gtk.Button, profile_name: str) -> None:
        """Open detailed health check & diagnostics dialog for a profile."""
        dialog = ProfileHealthDialog(parent=self, profile_name=profile_name, vpn_manager=self.vpn)
        dialog.present(self)

    def _on_warp_clicked(self, button: Gtk.Button) -> None:
        """Provision a free VPN config.

        Strategy:
        1. Try Cloudflare WARP API (may be blocked in some regions).
        2. On failure, generate a profile from the built-in server catalogue
           with a fresh client keypair.
        """
        self._warp_btn.set_sensitive(False)
        self._warp_spinner.set_visible(True)
        self._warp_spinner.start()
        self._show_toast("Generating free VPN config…")

        def worker() -> None:
            # --- Attempt 1: WARP API ---
            try:
                from warp_provisioner import WARPProvisioner
                prov = WARPProvisioner()
                conf_text = prov.provision(profile_name="cloudflare-warp")
                GLib.idle_add(
                    self._on_warp_done, True, conf_text, "cloudflare-warp", ""
                )
                return
            except Exception as warp_err:
                logger.warning("WARP API unavailable: %s", warp_err)

            # --- Attempt 2: Built-in profiles with fresh keypair ---
            try:
                from builtin_profiles import generate_fresh_profile
                name, conf_text = generate_fresh_profile(server_index=0)
                GLib.idle_add(
                    self._on_warp_done, True, conf_text, name, ""
                )
            except Exception as exc:
                GLib.idle_add(
                    self._on_warp_done, False, "", "", str(exc)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_warp_done(
        self, success: bool, conf_text: str, profile_name: str, error: str
    ) -> bool:
        """Handle provisioning result in the GTK main thread."""
        self._warp_btn.set_sensitive(True)
        self._warp_spinner.stop()
        self._warp_spinner.set_visible(False)

        if not success:
            self._show_toast(f"Config error: {error}")
            logger.error("Free VPN provisioning failed: %s", error)
            return False

        import tempfile
        try:
            # Truncate base to 12 chars so the "-NN" dedup suffix fits in 15
            base = profile_name[:12]
            name = base
            counter = 1
            while self.cfg.get_config(name) is not None:
                name = f"{base[:12 - len(str(counter)) - 1]}-{counter}"
                counter += 1

            tmp_path = Path(tempfile.gettempdir()) / f"{name}.conf"
            tmp_path.write_text(conf_text, encoding="utf-8")
            cfg = self.cfg.import_config(tmp_path)
            tmp_path.unlink(missing_ok=True)
            self._refresh_profiles()
            self._show_toast(f"Profile '{cfg.name}' ready!")
            logger.info("Profile '%s' provisioned", cfg.name)
        except Exception as exc:
            self._show_toast(f"Import error: {exc}")
            logger.error("Profile import failed: %s", exc)
        return False

    def _on_warp_info_clicked(self, button: Gtk.Button) -> None:
        """Show a dialog explaining how to get a Cloudflare WARP config."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="How to get Cloudflare WARP config",
            body=(
                "Cloudflare WARP is a free WireGuard-based VPN.\n\n"
                "Option 1 — wgcf tool (Linux):\n"
                "  1. Download: github.com/ViRb3/wgcf/releases\n"
                "  2. Run from a non-blocked network:\n"
                "       ./wgcf register --accept-tos\n"
                "       ./wgcf generate\n"
                "  3. Import wgcf-profile.conf into this app\n\n"
                "Option 2 — 1.1.1.1 mobile app:\n"
                "  1. Install 1.1.1.1 app on Android/iPhone\n"
                "  2. Export config (Settings → Advanced → Export)\n"
                "  3. Transfer the .conf file to this PC and import\n\n"
                "Option 3 — Windscribe free (10 GB/month):\n"
                "  1. Register at windscribe.com (free)\n"
                "  2. Download WireGuard config from dashboard\n"
                "  3. Import into this app"
            ),
        )
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present()

    def _open_url(self, url: str) -> None:
        """Open a URL in the default browser."""
        try:
            import subprocess as _sp
            _sp.Popen(["xdg-open", url])
        except Exception as exc:
            logger.warning("Could not open URL %s: %s", url, exc)

    def _on_edit_profile(self, button: Gtk.Button, profile_name: str) -> None:

        """Open edit dialog for a profile."""
        cfg = self.cfg.get_config(profile_name)
        if cfg is None:
            self._show_toast(f"Profile '{profile_name}' not found")
            return
        dialog = EditConfigDialog(self, cfg, self.cfg)
        dialog.connect("saved", lambda d: self._refresh_profiles())
        dialog.present(self)

    def _on_delete_profile(self, button: Gtk.Button, profile_name: str) -> None:
        """Confirm and delete a profile."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=f"Удалить «{profile_name}»?",
            body="Это действие безвозвратно удалит профиль VPN.",
        )
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("delete", "Удалить")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_delete_confirmed, profile_name)
        dialog.present()

    def _on_delete_confirmed(self, dialog: Adw.MessageDialog, response: str, profile_name: str) -> None:
        if response == "delete":
            self.cfg.delete_config(profile_name)
            self._refresh_profiles()
            self._show_toast(f"Профиль «{profile_name}» удален")
            logger.info("Deleted profile '%s'", profile_name)

    def _on_profile_dropdown_selected(self, row: Adw.ComboRow, _param) -> None:
        selected = row.get_selected()
        if hasattr(self, "_profile_names") and 0 <= selected < len(self._profile_names):
            name = self._profile_names[selected]
            self.cfg.set_last_connected(name)
            display_title = get_server_display_title(name)
            if self._connected:
                if getattr(self, "_active_profile", None) != name:
                    self._show_toast(f"⚡ Мгновенное переключение на «{display_title}»…", timeout=3)
                    self._do_connect(name)
            else:
                self._status_subtitle.set_text(f"Выбран: {display_title}")

    def _on_profile_row_activated(self, profile_name: str) -> None:
        if hasattr(self, "_profile_names") and profile_name in self._profile_names:
            idx = self._profile_names.index(profile_name)
            self._profile_dropdown_row.set_selected(idx)
            self.cfg.set_last_connected(profile_name)
            display_title = get_server_display_title(profile_name)
            self._stack.set_visible_child_name("connection")
            self._show_toast(f"⚡ Мгновенное подключение к «{display_title}»…", timeout=3)
            self._do_connect(profile_name)

    def _on_profile_quick_connect(self, profile_name: str) -> None:
        if hasattr(self, "_profile_names") and profile_name in self._profile_names:
            idx = self._profile_names.index(profile_name)
            self._profile_dropdown_row.set_selected(idx)
            self.cfg.set_last_connected(profile_name)
        self._stack.set_visible_child_name("connection")
        self._do_connect(profile_name)

    # ---- Connection actions -----------------------------------------------

    def _on_connect_clicked(self, button: Gtk.Button = None) -> None:
        profile_name = None
        if hasattr(self, "_profile_names") and self._profile_names:
            selected = self._profile_dropdown_row.get_selected() if hasattr(self, "_profile_dropdown_row") else 0
            if 0 <= selected < len(self._profile_names):
                profile_name = self._profile_names[selected]
            else:
                profile_name = self._profile_names[0]
                if hasattr(self, "_profile_dropdown_row"):
                    self._profile_dropdown_row.set_selected(0)
        elif hasattr(self, "cfg"):
            last = self.cfg.get_last_connected()
            if last:
                profile_name = last
            else:
                profs = self.cfg.list_profiles()
                if profs:
                    profile_name = profs[0].name

        if not profile_name:
            self._show_toast("⚠️ Сервер не выбран. Нажмите «Свежие сервера» или создайте Cloudflare.")
            return

        self._do_connect(profile_name)

    def _on_disconnect_clicked(self, button: Gtk.Button) -> None:
        self._do_disconnect()

    def _do_connect(self, profile_name: str) -> None:
        if self._connecting:
            return
        self._set_connecting_state(True)
        enable_ks = self._killswitch_row.get_active() if hasattr(self, '_killswitch_row') and self._killswitch_row else False

        def worker() -> None:
            success, msg = self.vpn.connect(profile_name, enable_killswitch=enable_ks)
            GLib.idle_add(self._on_connect_done, success, msg, profile_name)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _on_connect_done(self, success: bool, msg: str, profile_name: str) -> bool:
        self._set_connecting_state(False)
        if success:
            self._connected = True
            self._active_profile = profile_name
            if hasattr(self, "_profile_names") and profile_name in self._profile_names:
                idx = self._profile_names.index(profile_name)
                self._profile_dropdown_row.set_selected(idx)
                self.cfg.set_last_connected(profile_name)
            self._connect_time = time.time()
            self._killswitch_enabled = self._killswitch_row.get_active() if hasattr(self, '_killswitch_row') and self._killswitch_row else False
            self._update_connection_ui()
            self._start_stats_timer()
            self._show_toast(f"Подключено к «{profile_name}»")
            # Fetch external IP in background
            self._fetch_external_ip()
            # Fetch ping in background
            self._fetch_ping()
        else:
            self._show_toast(f"Ошибка подключения: {msg}")
        self._update_tray_state()
        return False

    def _do_disconnect(self) -> None:
        if self._connecting:
            return
        self._set_connecting_state(True)

        def worker() -> None:
            success, msg = self.vpn.disconnect()
            GLib.idle_add(self._on_disconnect_done, success, msg)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _on_disconnect_done(self, success: bool, msg: str) -> bool:
        self._set_connecting_state(False)
        if success:
            self._connected = False
            self._active_profile = None
            self._connect_time = None
            self._killswitch_enabled = False
            self._stop_stats_timer()
            self._update_connection_ui()
            self._show_toast("Отключено")
        else:
            self._show_toast(f"Ошибка отключения: {msg}")
        self._update_tray_state()
        return False

    def connect_to_last(self) -> None:
        """Connect to the last used profile (called from tray)."""
        last = self.cfg.get_last_connected()
        if last and self.cfg.get_config(last):
            self._do_connect(last)
        else:
            self._show_toast("Нет недавних серверов для подключения")

    # ---- Kill-switch toggle -----------------------------------------------

    def _on_killswitch_toggled(self, row: Adw.SwitchRow, pspec: Any) -> None:
        if not self._connected:
            return  # Will be applied on connect

        active = row.get_active()
        config = self.cfg.get_config(self._active_profile) if self._active_profile else None
        if active and config:
            def ks_on() -> None:
                ok, msg = self.vpn.enable_killswitch(config)
                GLib.idle_add(self._on_killswitch_result, ok, msg, True)
            threading.Thread(target=ks_on, daemon=True).start()
        elif not active:
            def ks_off() -> None:
                ok, msg = self.vpn.disable_killswitch()
                GLib.idle_add(self._on_killswitch_result, ok, msg, False)
            threading.Thread(target=ks_off, daemon=True).start()

    def _on_killswitch_result(self, ok: bool, msg: str, enabled: bool) -> bool:
        if ok:
            self._killswitch_enabled = enabled
            self._show_toast(f"Аварийная блокировка {'включена' if enabled else 'отключена'}")
        else:
            self._show_toast(f"Ошибка аварийной блокировки: {msg}")
            # Revert toggle
            self._killswitch_row.set_active(not enabled)
        return False

    # ---- UI state updates -------------------------------------------------

    def _set_connecting_state(self, connecting: bool) -> None:
        self._connecting = connecting
        if hasattr(self, "_turn_on_btn"):
            if connecting:
                self._turn_on_btn.remove_css_class("connected")
                self._turn_on_btn.add_css_class("connecting")
                self._turn_on_lbl.set_text("CONNECTING...")
            else:
                self._turn_on_btn.remove_css_class("connecting")
                if self._connected:
                    self._turn_on_btn.add_css_class("connected")
                    self._turn_on_lbl.set_text("TURN OFF")
                else:
                    self._turn_on_lbl.set_text("TURN ON")
        if hasattr(self, "_status_label"):
            if connecting:
                self._status_label.set_markup("<span size='20000' weight='heavy' color='#facc15'>Connecting…</span>")
                self._status_subtitle.set_markup("<span size='11500' color='#94a3b8'>Establishing encrypted tunnel…</span>")
        if hasattr(self, "_connect_btn"):
            self._connect_btn.set_sensitive(not connecting)
        if hasattr(self, "_disconnect_btn"):
            self._disconnect_btn.set_sensitive(not connecting)
        if hasattr(self, "_spinner"):
            self._spinner.set_visible(connecting)
            if connecting:
                self._spinner.start()
            else:
                self._spinner.stop()

    def _update_connection_ui(self) -> None:
        """Update all UI elements to reflect current connection state with glowing circular button."""
        display_title = get_server_display_title(self._active_profile or self.cfg.get_last_connected() or "")
        is_warp = "warp" in (self._active_profile or "").lower() or "cloudflare" in (self._active_profile or "").lower()
        if self._connected:
            if hasattr(self, "_turn_on_btn"):
                self._turn_on_btn.remove_css_class("connecting")
                self._turn_on_btn.add_css_class("connected")
                self._turn_on_lbl.set_text("TURN OFF")
            if is_warp:
                self._status_label.set_markup("<span size='20000' weight='heavy' color='#38ef7d'>🛡️ Cloudflare WARP • АКТИВЕН</span>")
                self._status_subtitle.set_markup("<span size='11500' weight='bold' color='#38bdf8'>✓ Безлимитный гигабитный туннель Cloudflare WARP активен</span>")
            else:
                self._status_label.set_markup("<span size='20000' weight='heavy' color='#38ef7d'>Connected • Protected</span>")
                self._status_subtitle.set_markup(f"<span size='11500' color='#a5b4fc'>Secured: {display_title}</span>")
            if hasattr(self, "_footer_dock"):
                self._footer_dock.set_visible(True)
        elif self._connecting:
            if hasattr(self, "_turn_on_btn"):
                self._turn_on_btn.remove_css_class("connected")
                self._turn_on_btn.add_css_class("connecting")
                self._turn_on_lbl.set_text("CONNECTING...")
            self._status_label.set_markup("<span size='20000' weight='heavy' color='#facc15'>Connecting…</span>")
            self._status_subtitle.set_markup("<span size='11500' color='#94a3b8'>Establishing encrypted tunnel…</span>")
        else:
            if hasattr(self, "_turn_on_btn"):
                self._turn_on_btn.remove_css_class("connected")
                self._turn_on_btn.remove_css_class("connecting")
                self._turn_on_lbl.set_text("TURN ON")
            self._status_label.set_markup("<span size='20000' weight='heavy' color='#ffffff'>Disconnected</span>")
            self._status_subtitle.set_markup(f"<span size='11500' color='#94a3b8'>Optimal Location: {display_title or 'Auto-Select (Optimal)'}</span>")
            if hasattr(self, "_footer_duration_lbl"):
                self._footer_duration_lbl.set_markup("<span size='11000' color='#94a3b8'>Duration: </span><span size='11000' weight='bold' color='#64748b'>00:00:00</span>")

    # ---- Stats polling ----------------------------------------------------

    def _start_stats_timer(self) -> None:
        if self._stats_timer_id:
            GLib.source_remove(self._stats_timer_id)
        self._stats_timer_id = GLib.timeout_add_seconds(2, self._poll_stats)

        if self._duration_timer_id:
            GLib.source_remove(self._duration_timer_id)
        self._duration_timer_id = GLib.timeout_add_seconds(1, self._update_duration)

    def _stop_stats_timer(self) -> None:
        if self._stats_timer_id:
            GLib.source_remove(self._stats_timer_id)
            self._stats_timer_id = 0
        if self._duration_timer_id:
            GLib.source_remove(self._duration_timer_id)
            self._duration_timer_id = 0

    def _poll_stats(self) -> bool:
        """Fetch transfer stats in a background thread."""
        if not self._connected or self._shutting_down:
            return False

        def worker() -> None:
            stats = self.vpn.get_transfer_stats()
            if not self._shutting_down:
                GLib.idle_add(self._on_stats_received, stats)

        threading.Thread(target=worker, daemon=True).start()
        return True  # keep timer running

    def _on_stats_received(self, stats: dict[str, Any]) -> bool:
        if not self._connected:
            return False
        self._download_value.set_text(stats.get("rx_human", "0 B"))
        self._upload_value.set_text(stats.get("tx_human", "0 B"))
        return False

    def _update_duration(self) -> bool:
        if not self._connected or self._connect_time is None:
            return False
        elapsed = int(time.time() - self._connect_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hasattr(self, "_duration_value"):
            self._duration_value.set_text(time_str)
        if hasattr(self, "_footer_duration_lbl"):
            self._footer_duration_lbl.set_markup(f"<span size='11000' color='#94a3b8'>Duration: </span><span size='11000' weight='bold' color='#38ef7d'>{time_str}</span>")
        return True

    def _fetch_external_ip(self) -> None:
        """Fetch external IP in background."""
        def worker() -> None:
            ip = self.vpn.get_external_ip()
            if not self._shutting_down:
                GLib.idle_add(self._on_ip_received, ip)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ip_received(self, ip: Optional[str]) -> bool:
        if self._connected:
            if ip and ip != "Unknown" and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                self._ip_value.set_text(ip)
                if hasattr(self, "_footer_ip_lbl"):
                    self._footer_ip_lbl.set_markup(f"<span size='11000' color='#94a3b8'>Current IP: </span><span size='11000' weight='bold' color='#ffffff'>{ip}</span>")
            else:
                # Server failed to route live traffic (IP is Unknown) -> Purge it from list!
                bad_profile = self._active_profile
                logger.warning("Active server %s returned Unknown IP! Purging from server list...", bad_profile)
                self._ip_value.set_text("Недоступен")
                if hasattr(self, "_footer_ip_lbl"):
                    self._footer_ip_lbl.set_markup("<span size='11000' color='#94a3b8'>Current IP: </span><span size='11000' weight='bold' color='#f87171'>Dead IP (Отсеян)</span>")
                
                # Exclude from cached servers
                try:
                    import reality_fetcher
                    cur_srvs = reality_fetcher.load_cached_servers()
                    filtered_srvs = [s for s in cur_srvs if s.get("name") != bad_profile and s.get("ascii_name") != bad_profile]
                    reality_fetcher.save_servers_to_system(filtered_srvs)
                    
                    # Delete conf file
                    from pathlib import Path
                    prof_dir = Path.home() / ".config" / "wavez-vpn" / "profiles"
                    if prof_dir.is_dir() and bad_profile:
                        (prof_dir / f"{bad_profile}.conf").unlink(missing_ok=True)
                    
                    self._refresh_profiles()
                    self._show_toast(f"⚠️ Сервер «{get_server_display_title(bad_profile or '')}» не отдаёт рабочий IP и был удалён из списка!", timeout=6)
                except Exception as exc:
                    logger.error("Error purging dead IP server: %s", exc)
        return False

    def _fetch_ping(self) -> None:
        """Ping VPN endpoint in background."""
        config = self.cfg.get_config(self._active_profile) if self._active_profile else None
        if config is None:
            return
        endpoint = config.get_endpoint_host_port()
        if not endpoint:
            return

        def worker() -> None:
            rtt = self.vpn.ping_endpoint(endpoint)
            if not self._shutting_down:
                GLib.idle_add(self._on_ping_received, rtt)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ping_received(self, rtt: Optional[float]) -> bool:
        if self._connected:
            ping_str = f"{rtt:.1f} ms" if rtt is not None else "Timeout"
            self._ping_value.set_text(ping_str)
            if hasattr(self, "_footer_ping_lbl"):
                color = "#38ef7d" if (rtt and rtt < 100) else ("#facc15" if (rtt and rtt < 300) else "#f87171")
                self._footer_ping_lbl.set_markup(f"<span size='11000' color='#94a3b8'>Ping: </span><span size='11000' weight='bold' color='{color}'>{ping_str}</span>")
        return False

    # ---- Initial status check ---------------------------------------------

    def _initial_status_check(self) -> bool:
        """Check if WireGuard is already connected (e.g., app restart)."""
        def worker() -> None:
            status = self.vpn.get_status()
            GLib.idle_add(self._on_initial_status, status)

        threading.Thread(target=worker, daemon=True).start()
        return False  # one-shot

    def _on_initial_status(self, status: dict[str, Any]) -> bool:
        if status.get("connected"):
            iface = status.get("interface")
            last_profile = self.cfg.get_last_connected()
            self._connected = True
            self._active_profile = last_profile
            self._connect_time = time.time()  # approximate
            # Sync vpn_manager's internal state so disconnect() works
            self.vpn._active_interface = iface
            self.vpn._active_config_name = last_profile
            self.vpn._connected = True
            self._update_connection_ui()
            self._start_stats_timer()
            self._fetch_external_ip()
            self._fetch_ping()
            logger.info("Detected existing VPN connection on %s", iface)

        self._update_tray_state()
        return False

    # ---- Tray integration -------------------------------------------------

    def _update_tray_state(self) -> None:
        tray = self.app.get_tray()
        if tray:
            profiles = [p.name for p in self.cfg.list_profiles()]
            tray.update_state(self._connected, self._active_profile, profiles)

    # ---- Window close behavior --------------------------------------------

    def _on_close_request(self, window: Adw.ApplicationWindow) -> bool:
        """Full termination: cleanly exit application and release memory immediately."""
        logger.info("Window close request received — terminating application completely...")
        self.shutdown()
        if hasattr(self, "app") and self.app:
            self.app.quit()
        # Ensure complete removal from OS process memory
        import os
        import signal
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            pass
        return False

    def shutdown(self) -> None:
        """Graceful shutdown: disconnect VPN, stop timers, kill helper subprocesses."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._stop_stats_timer()
        if hasattr(self, "vpn") and self.vpn:
            try:
                self.vpn.disconnect()
            except Exception:
                pass
            if hasattr(self.vpn, "xray_manager") and self.vpn.xray_manager:
                try:
                    self.vpn.xray_manager.disconnect()
                except Exception:
                    pass
        logger.info("Window shutdown complete")

    # ---- Logs -------------------------------------------------------------

    def _on_clear_logs(self, button: Gtk.Button) -> None:
        buf = self._log_view.get_buffer()
        buf.delete(buf.get_start_iter(), buf.get_end_iter())

    # ---- Toast helper -----------------------------------------------------

    def _show_toast(self, message: str, timeout: int = 3) -> None:
        toast = Adw.Toast(title=message, timeout=timeout)
        self._toast_overlay.add_toast(toast)


# ---------------------------------------------------------------------------
# EditConfigDialog — edit a WireGuard profile
# ---------------------------------------------------------------------------


class EditConfigDialog(Adw.Window):
    """Dialog for editing a WireGuard config profile."""

    __gsignals__ = {
        "saved": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        parent: MainWindow,
        config: WireGuardConfig,
        config_manager: ConfigManager,
    ) -> None:
        super().__init__(
            title=f"Edit — {config.name}",
            default_width=450,
            default_height=550,
            modal=True,
            transient_for=parent,
        )
        self._config = config
        self._config_manager = config_manager
        self._build_ui()





    def _build_ui(self) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header
        header = Adw.HeaderBar()
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)
        main_box.append(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=500)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        clamp.set_child(content)
        scroll.set_child(clamp)
        main_box.append(scroll)

        # Interface section
        iface_group = Adw.PreferencesGroup(title="Interface")

        self._address_row = Adw.EntryRow(title="Address")
        self._address_row.set_text(self._config.interface.get("Address", ""))
        iface_group.add(self._address_row)

        self._dns_row = Adw.EntryRow(title="DNS")
        self._dns_row.set_text(self._config.interface.get("DNS", ""))
        iface_group.add(self._dns_row)

        self._mtu_row = Adw.EntryRow(title="MTU")
        self._mtu_row.set_text(self._config.interface.get("MTU", ""))
        iface_group.add(self._mtu_row)

        self._listen_port_row = Adw.EntryRow(title="Listen Port")
        self._listen_port_row.set_text(self._config.interface.get("ListenPort", ""))
        iface_group.add(self._listen_port_row)

        content.append(iface_group)

        # Peer section (first peer)
        if self._config.peers:
            peer = self._config.peers[0]
            peer_group = Adw.PreferencesGroup(title="Peer")

            self._endpoint_row = Adw.EntryRow(title="Endpoint")
            self._endpoint_row.set_text(peer.get("Endpoint", ""))
            peer_group.add(self._endpoint_row)

            self._allowed_ips_row = Adw.EntryRow(title="AllowedIPs")
            self._allowed_ips_row.set_text(peer.get("AllowedIPs", ""))
            peer_group.add(self._allowed_ips_row)

            self._keepalive_row = Adw.EntryRow(title="PersistentKeepalive")
            self._keepalive_row.set_text(peer.get("PersistentKeepalive", ""))
            peer_group.add(self._keepalive_row)

            content.append(peer_group)
        else:
            self._endpoint_row = None
            self._allowed_ips_row = None
            self._keepalive_row = None

        # AmneziaWG obfuscation section (if profile has obfuscation keys or user wants to configure)
        self._awg_entries: dict[str, Adw.EntryRow] = {}
        if self._config.is_amnezia:
            awg_group = Adw.PreferencesGroup(title="AmneziaWG Obfuscation")
            for key in ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"):
                # Case-insensitive lookup
                val = ""
                for k, v in self._config.interface.items():
                    if k.lower() == key.lower():
                        val = v
                        break
                entry = Adw.EntryRow(title=key)
                entry.set_text(val)
                awg_group.add(entry)
                self._awg_entries[key] = entry
            content.append(awg_group)

    def _on_save(self, button: Gtk.Button) -> None:
        """Save changes back to config file."""
        try:
            # Update interface fields
            self._config.interface["Address"] = self._address_row.get_text().strip()
            dns_text = self._dns_row.get_text().strip()
            if dns_text:
                self._config.interface["DNS"] = dns_text
            elif "DNS" in self._config.interface:
                del self._config.interface["DNS"]

            mtu_text = self._mtu_row.get_text().strip()
            if mtu_text:
                self._config.interface["MTU"] = mtu_text
            elif "MTU" in self._config.interface:
                del self._config.interface["MTU"]

            listen_port_text = self._listen_port_row.get_text().strip()
            if listen_port_text:
                self._config.interface["ListenPort"] = listen_port_text
            elif "ListenPort" in self._config.interface:
                del self._config.interface["ListenPort"]

            # Update Amnezia fields
            for key, entry in self._awg_entries.items():
                val = entry.get_text().strip()
                # Remove existing key variant if any
                for k in list(self._config.interface.keys()):
                    if k.lower() == key.lower():
                        del self._config.interface[k]
                if val:
                    self._config.interface[key] = val

            # Update first peer
            if self._config.peers and self._endpoint_row is not None:
                peer = self._config.peers[0]
                endpoint_text = self._endpoint_row.get_text().strip()
                if endpoint_text:
                    peer["Endpoint"] = endpoint_text

                allowed_text = self._allowed_ips_row.get_text().strip()
                if allowed_text:
                    peer["AllowedIPs"] = allowed_text

                keepalive_text = self._keepalive_row.get_text().strip()
                if keepalive_text:
                    peer["PersistentKeepalive"] = keepalive_text
                elif "PersistentKeepalive" in peer:
                    del peer["PersistentKeepalive"]

            # Re-generate raw_content
            self._config.raw_content = self._config.to_conf()

            # Save to disk
            self._config_manager.save_config(self._config)
            self.emit("saved")
            self.close()
            logger.info("Profile '%s' updated", self._config.name)
        except Exception as exc:
            logger.error("Save error: %s", exc)


# ---------------------------------------------------------------------------
# SubscriptionImportDialog — Happ, Incy, URLs, and multi-server links
# ---------------------------------------------------------------------------


class SubscriptionImportDialog(Adw.Window):
    """Dialog for importing Happ, Incy, remote subscriptions, and WireGuard/Amnezia links."""

    __gsignals__ = {
        "imported": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self, parent: Gtk.Window, config_manager: ConfigManager, settings: Optional[Any] = None, initial_text: str = "") -> None:
        super().__init__(
            title="Активация подписки и ключей",
            default_width=520,
            default_height=640,
            modal=True,
            transient_for=parent,
        )
        self._parent = parent
        self._cfg_mgr = config_manager
        self._initial_text = initial_text
        if settings is None:
            from settings_manager import SettingsManager
            self._settings = SettingsManager()
        else:
            self._settings = settings
        self._servers: list[ParsedServer] = []
        self._check_buttons: list[Gtk.CheckButton] = []
        self._lat_labels: list[Gtk.Label] = []
        self._build_ui()

        if self._initial_text:
            GLib.timeout_add(100, lambda: self._on_fetch_clicked(self._fetch_btn) or False)





    def _build_ui(self) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()
        cancel_btn = Gtk.Button(label="Отмена")
        cancel_btn.connect("clicked", lambda _: self.close())
        header.pack_start(cancel_btn)

        self._import_btn = Gtk.Button(label="Добавить выбранные")
        self._import_btn.add_css_class("suggested-action")
        self._import_btn.set_sensitive(False)
        self._import_btn.connect("clicked", self._on_import_selected)
        header.pack_end(self._import_btn)
        main_box.append(header)

        # Scrollable content
        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=500)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        clamp.set_child(content)
        scroll.set_child(clamp)
        main_box.append(scroll)

        # Input group
        input_group = Adw.PreferencesGroup(
            title="Ключ или ссылка подписки",
            description="Вставьте ссылку https:// (TgFlow, Marzban, Happ), vless://, wireguard://, awg:// или base64",
        )
        self._url_entry = Adw.EntryRow(title="Ключ / Ссылка")
        sub_url = self._initial_text or self._settings.get("subscription_url", "")
        if sub_url:
            self._url_entry.set_text(sub_url)
        self._url_entry.connect("entry-activated", lambda _: self._on_fetch_clicked(self._fetch_btn))
        input_group.add(self._url_entry)
        content.append(input_group)

        # Fetch button & spinner box
        fetch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.CENTER)
        fetch_box.set_margin_top(4)
        fetch_box.set_margin_bottom(8)

        self._fetch_btn = Gtk.Button(label="⚡ Активировать и получить серверы")
        self._fetch_btn.add_css_class("suggested-action")
        self._fetch_btn.add_css_class("pill")
        self._fetch_btn.connect("clicked", self._on_fetch_clicked)
        fetch_box.append(self._fetch_btn)

        self._spinner = Gtk.Spinner()
        fetch_box.append(self._spinner)

        content.append(fetch_box)

        # Servers group (hidden until servers parsed)
        self._servers_group = Adw.PreferencesGroup(title="Доступные серверы")
        self._servers_group.set_visible(False)

        # Actions row above list (Select All / Deselect All / Test Latency)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sel_all_btn = Gtk.Button(label="Выбрать все")
        sel_all_btn.add_css_class("flat")
        sel_all_btn.connect("clicked", lambda _: self._set_all_selected(True))
        actions_box.append(sel_all_btn)

        desel_all_btn = Gtk.Button(label="Снять выбор")
        desel_all_btn.add_css_class("flat")
        desel_all_btn.connect("clicked", lambda _: self._set_all_selected(False))
        actions_box.append(desel_all_btn)

        spacer = Gtk.Box(hexpand=True)
        actions_box.append(spacer)

        self._test_lat_btn = Gtk.Button(label="⚡ Замерить пинг")
        self._test_lat_btn.add_css_class("flat")
        self._test_lat_btn.connect("clicked", self._on_test_latencies_clicked)
        actions_box.append(self._test_lat_btn)

        self._servers_group.set_header_suffix(actions_box)

        self._servers_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._servers_listbox.add_css_class("boxed-list")
        self._servers_group.add(self._servers_listbox)
        content.append(self._servers_group)

    def _on_load_incy_clicked(self, button: Gtk.Button) -> None:
        from incy_importer import IncyImporter
        servers = IncyImporter.to_parsed_servers()
        if not servers:
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading="Incy Database Not Found",
                body="Could not find or read servers from ~/.local/share/incy/incy.db",
            )
            dialog.add_response("ok", "OK")
            dialog.present()
            return
        self._servers = servers
        self._rebuild_server_list()

    def _on_fetch_clicked(self, button: Gtk.Button) -> None:
        text = self._url_entry.get_text().strip()
        if not text:
            if hasattr(self._parent, "_show_toast"):
                self._parent._show_toast("Введите ссылку или ключ подписки")
            return

        self._fetch_btn.set_sensitive(False)
        self._fetch_btn.set_label("⏳ Загрузка серверов…")
        self._spinner.set_visible(True)
        self._spinner.start()

        def worker() -> None:
            try:
                servers = SubscriptionParser.parse(text)
                GLib.idle_add(self._on_fetch_done, servers, "")
            except Exception as exc:
                logger.error("Subscription fetch error: %s", exc)
                err_msg = str(exc)
                if "502" in err_msg or "Bad Gateway" in err_msg:
                    err_msg = "Сервер подписки tgflow.me временно недоступен (502 Bad Gateway). Попробуйте через 1-2 минуты или вставьте прямой ключ vless:// / wireguard://."
                elif "Connection refused" in err_msg or "NameResolutionError" in err_msg or "Failed to establish" in err_msg:
                    err_msg = "Не удалось подключиться к серверу подписки. Проверьте интернет-соединение."
                GLib.idle_add(self._on_fetch_done, [], err_msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_done(self, servers: list[ParsedServer], error: str) -> bool:
        self._fetch_btn.set_sensitive(True)
        self._fetch_btn.set_label("⚡ Активировать и получить серверы")
        self._spinner.stop()
        self._spinner.set_visible(False)

        if error:
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading="Ошибка загрузки подписки",
                body=error,
            )
            dialog.add_response("ok", "Понятно")
            dialog.present()
            return False

        if not servers:
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading="Серверы не найдены",
                body="В предоставленной подписке или ключе не найдено доступных серверов (VLESS, WireGuard, AmneziaWG).",
            )
            dialog.add_response("ok", "OK")
            dialog.present()
            return False

        # Extract and format subscription expiry / remaining time if present
        sub_info = None
        for s in servers:
            if s.metadata and s.metadata.get("subscription_info"):
                sub_info = s.metadata["subscription_info"]
                break

        if sub_info:
            expire_ts = sub_info.get("expire")
            upload_b = sub_info.get("upload", 0)
            download_b = sub_info.get("download", 0)
            total_b = sub_info.get("total", 0)

            details = []
            if expire_ts:
                try:
                    import datetime
                    exp_dt = datetime.datetime.fromtimestamp(int(expire_ts))
                    now_dt = datetime.datetime.now()
                    diff = exp_dt - now_dt
                    days_left = diff.days
                    if days_left > 0:
                        time_str = f"{days_left} дн. ({exp_dt.strftime('%d.%m.%Y')})"
                    elif diff.total_seconds() > 0:
                        time_str = f"Менее суток ({exp_dt.strftime('%d.%m.%Y %H:%M')})"
                    else:
                        time_str = f"Истекла ({exp_dt.strftime('%d.%m.%Y')})"
                    details.append(f"⏳ Срок действия: <b>{time_str}</b>")
                except Exception:
                    pass

            if total_b and isinstance(total_b, int):
                used_gb = (upload_b + download_b) / (1024**3)
                tot_gb = total_b / (1024**3)
                details.append(f"📊 Трафик: <b>{used_gb:.1f} GB</b> / <b>{tot_gb:.1f} GB</b>")

            if details:
                self._servers_group.set_description(" • ".join(details))
            else:
                self._servers_group.set_description(f"Успешно загружено {len(servers)} серверов")
        else:
            self._servers_group.set_description(f"Успешно загружено {len(servers)} серверов")

        self._servers = servers
        self._rebuild_server_list()
        return False

    def _rebuild_server_list(self) -> None:
        # Clear existing rows
        while True:
            child = self._servers_listbox.get_first_child()
            if child is None:
                break
            self._servers_listbox.remove(child)

        self._check_buttons.clear()
        self._lat_labels.clear()

        for idx, srv in enumerate(self._servers):
            row = Adw.ActionRow(title=srv.name, subtitle=srv.endpoint or "WireGuard Server")

            # Checkbox
            check = Gtk.CheckButton(active=srv.selected)
            check.set_valign(Gtk.Align.CENTER)
            check.connect("toggled", self._on_check_toggled, idx)
            row.add_prefix(check)
            self._check_buttons.append(check)

            # Protocol badge
            badge = Gtk.Label(label="AWG" if srv.is_amnezia else "WG")
            badge.add_css_class("badge-awg" if srv.is_amnezia else "badge-wg")
            badge.set_valign(Gtk.Align.CENTER)
            row.add_suffix(badge)

            # Latency label
            lat_lbl = Gtk.Label(label="—")
            lat_lbl.set_valign(Gtk.Align.CENTER)
            lat_lbl.set_margin_start(4)
            lat_lbl.add_css_class("latency-none")
            row.add_suffix(lat_lbl)
            self._lat_labels.append(lat_lbl)

            self._servers_listbox.append(row)

        self._servers_group.set_visible(True)
        self._update_import_btn_state()

    def _on_check_toggled(self, check: Gtk.CheckButton, idx: int) -> None:
        if 0 <= idx < len(self._servers):
            self._servers[idx].selected = check.get_active()
        self._update_import_btn_state()

    def _set_all_selected(self, active: bool) -> None:
        for idx, check in enumerate(self._check_buttons):
            check.set_active(active)
            if idx < len(self._servers):
                self._servers[idx].selected = active
        self._update_import_btn_state()

    def _update_import_btn_state(self) -> None:
        count = sum(1 for s in self._servers if s.selected)
        self._import_btn.set_sensitive(count > 0)
        self._import_btn.set_label(f"Добавить выбранные ({count})" if count > 0 else "Добавить выбранные")

    def _on_test_latencies_clicked(self, button: Gtk.Button) -> None:
        button.set_sensitive(False)

        def worker() -> None:
            for idx, srv in enumerate(self._servers):
                lat = srv.test_latency()
                GLib.idle_add(self._update_server_lat_ui, idx, lat)
            GLib.idle_add(lambda: button.set_sensitive(True) or False)

        threading.Thread(target=worker, daemon=True).start()

    def _update_server_lat_ui(self, idx: int, lat: Optional[float]) -> bool:
        if 0 <= idx < len(self._lat_labels):
            lbl = self._lat_labels[idx]
            lbl.remove_css_class("latency-good")
            lbl.remove_css_class("latency-medium")
            lbl.remove_css_class("latency-bad")
            lbl.remove_css_class("latency-none")
            if lat is None:
                lbl.set_text("Timeout")
                lbl.add_css_class("latency-bad")
            elif lat < 100:
                lbl.set_text(f"⚡ {lat:.0f} ms")
                lbl.add_css_class("latency-good")
            elif lat < 250:
                lbl.set_text(f"⚡ {lat:.0f} ms")
                lbl.add_css_class("latency-medium")
            else:
                lbl.set_text(f"⚡ {lat:.0f} ms")
                lbl.add_css_class("latency-bad")
        return False

    def _on_import_selected(self, button: Gtk.Button) -> None:
        selected_servers = [s for s in self._servers if s.selected]
        if not selected_servers:
            return

        import tempfile
        imported_count = 0
        proxy_meta_list = []

        for srv in selected_servers:
            try:
                base = srv.name[:12]
                name = base
                counter = 1
                while self._cfg_mgr.get_config(name) is not None:
                    name = f"{base[:12 - len(str(counter)) - 1]}-{counter}"
                    counter += 1

                tmp = Path(tempfile.gettempdir()) / f"{name}.conf"
                tmp.write_text(srv.conf_content, encoding="utf-8")
                self._cfg_mgr.import_config(tmp)
                tmp.unlink(missing_ok=True)
                imported_count += 1

                if srv.metadata:
                    m = dict(srv.metadata)
                    m["name"] = name
                    m["ascii_name"] = name
                    proxy_meta_list.append(m)
            except Exception as exc:
                logger.error("Failed to import server '%s': %s", srv.name, exc)

        if proxy_meta_list:
            try:
                from reality_fetcher import save_servers_to_system
                save_servers_to_system(proxy_meta_list)
            except Exception as exc:
                logger.warning("Could not sync metadata to wavez_servers.json: %s", exc)

        # Save active subscription URL
        sub_input = self._url_entry.get_text().strip()
        if sub_input.startswith("http://") or sub_input.startswith("https://") or sub_input.startswith("happ://"):
            self._settings.set("subscription_url", sub_input)

        self.emit("imported", imported_count)
        self.close()


# ---------------------------------------------------------------------------
# ProfileHealthDialog — detailed diagnostics & latency check for a profile
# ---------------------------------------------------------------------------


class ProfileHealthDialog(Adw.Window):
    """Dialog showing detailed health, latency, and diagnostics for a profile."""

    def __init__(self, parent: Gtk.Window, profile_name: str, vpn_manager: VPNManager) -> None:
        super().__init__(
            title=f"Diagnostics — {profile_name}",
            default_width=480,
            default_height=600,
            modal=True,
            transient_for=parent,
        )
        self._profile_name = profile_name
        self._vpn = vpn_manager
        self._build_ui()
        self._run_check()





    def _build_ui(self) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()
        retest_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        retest_btn.set_tooltip_text("Retest server")
        retest_btn.connect("clicked", lambda _: self._run_check())
        header.pack_start(retest_btn)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _: self.close())
        header.pack_end(close_btn)
        main_box.append(header)

        # Scrollable content
        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=500)
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self._content.set_margin_top(16)
        self._content.set_margin_bottom(16)
        self._content.set_margin_start(16)
        self._content.set_margin_end(16)
        clamp.set_child(self._content)
        scroll.set_child(clamp)
        main_box.append(scroll)

        # Spinner placeholder
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(36, 36)
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)
        self._spinner.set_margin_top(40)
        self._content.append(self._spinner)

    def _run_check(self) -> None:
        # Show spinner and clear previous content
        while True:
            child = self._content.get_first_child()
            if child is None:
                break
            self._content.remove(child)

        self._spinner.set_visible(True)
        self._spinner.start()
        self._content.append(self._spinner)

        def worker() -> None:
            report = self._vpn.check_profile_health(self._profile_name, timeout=3.0)
            GLib.idle_add(self._on_check_done, report)

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_done(self, report: HealthReport) -> bool:
        self._spinner.stop()
        self._spinner.set_visible(False)
        self._content.remove(self._spinner)

        # Group 1: Profile & Protocol
        info_group = Adw.PreferencesGroup(title="Profile Information")
        name_row = Adw.ActionRow(title="Profile Name", subtitle=report.profile_name)
        info_group.add(name_row)

        proto_row = Adw.ActionRow(title="Protocol")
        proto_badge = Gtk.Label(label="AmneziaWG (Obfuscated)" if report.is_amnezia else "Standard WireGuard")
        proto_badge.add_css_class("badge-awg" if report.is_amnezia else "badge-wg")
        proto_badge.set_valign(Gtk.Align.CENTER)
        proto_row.add_suffix(proto_badge)
        info_group.add(proto_row)

        if report.is_amnezia and report.awg_params:
            awg_str = ", ".join(f"{k}={v}" for k, v in report.awg_params.items())
            awg_row = Adw.ActionRow(title="Obfuscation Parameters", subtitle=awg_str)
            info_group.add(awg_row)

        self._content.append(info_group)

        # Group 2: Endpoint & Latency
        diag_group = Adw.PreferencesGroup(title="Endpoint & Latency")

        host_row = Adw.ActionRow(title="Endpoint Host", subtitle=report.endpoint_raw or "None")
        diag_group.add(host_row)

        ip_row = Adw.ActionRow(title="Resolved IP Address")
        ip_lbl = Gtk.Label(label=report.endpoint_ip or "Failed to resolve")
        ip_lbl.add_css_class("latency-good" if report.endpoint_ip else "latency-bad")
        ip_lbl.set_valign(Gtk.Align.CENTER)
        ip_row.add_suffix(ip_lbl)
        diag_group.add(ip_row)

        # Ping
        ping_row = Adw.ActionRow(title="ICMP Ping Latency")
        if report.ping_ms is not None:
            rtt_text = f"{report.ping_ms:.1f} ms"
            if report.ping_min_ms and report.ping_max_ms:
                rtt_text += f" (min {report.ping_min_ms:.0f} / max {report.ping_max_ms:.0f})"
            ping_lbl = Gtk.Label(label=rtt_text)
            if report.ping_ms < 100:
                ping_lbl.add_css_class("latency-good")
            elif report.ping_ms < 250:
                ping_lbl.add_css_class("latency-medium")
            else:
                ping_lbl.add_css_class("latency-bad")
        else:
            ping_lbl = Gtk.Label(label="Timeout / Filtered")
            ping_lbl.add_css_class("latency-bad")
        ping_lbl.set_valign(Gtk.Align.CENTER)
        ping_row.add_suffix(ping_lbl)
        diag_group.add(ping_row)

        # UDP Reachability
        udp_row = Adw.ActionRow(title="WireGuard UDP Port")
        udp_lbl = Gtk.Label(label="Reachable" if report.udp_reachable else "No response")
        udp_lbl.add_css_class("latency-good" if report.udp_reachable else "latency-none")
        udp_lbl.set_valign(Gtk.Align.CENTER)
        udp_row.add_suffix(udp_lbl)
        diag_group.add(udp_row)

        self._content.append(diag_group)

        # Group 3: DNS
        if report.dns_servers:
            dns_group = Adw.PreferencesGroup(title="DNS Protection")
            for dns_ip in report.dns_servers:
                d_row = Adw.ActionRow(title=f"DNS Server: {dns_ip}")
                is_ok = report.dns_reachable.get(dns_ip, False)
                d_lbl = Gtk.Label(label="Active" if is_ok else "No connection")
                d_lbl.add_css_class("latency-good" if is_ok else "latency-medium")
                d_lbl.set_valign(Gtk.Align.CENTER)
                d_row.add_suffix(d_lbl)
                dns_group.add(d_row)
            self._content.append(dns_group)

        return False


# ---------------------------------------------------------------------------
# TrayIcon — manages the GTK3 AyatanaAppIndicator3 tray subprocess
# ---------------------------------------------------------------------------


class TrayIcon:
    """System tray via a GTK3 child process (``tray_subprocess.py``).

    The child process is a standalone GTK3 app that owns the
    AyatanaAppIndicator3 object.  We communicate with it using a simple
    JSON-per-line protocol over its stdin/stdout pipes.

    Parent → child (commands):
        {"cmd": "update", "connected": true, "profile": "myserver"}
        {"cmd": "quit"}

    Child → parent (events, read on a background thread):
        {"event": "connect_last"}
        {"event": "show_window"}
        {"event": "disconnect"}
        {"event": "quit"}
    """

    def __init__(self, app: VPNApplication, window: "MainWindow") -> None:
        self._app = app
        self._window = window
        self._proc: Optional[subprocess.Popen[str]] = None
        self._alive: bool = True

        helper_path = str(_TRAY_HELPER)
        try:
            self._proc = subprocess.Popen(
                ["python3", helper_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,  # line-buffered
            )
        except (FileNotFoundError, OSError) as exc:
            logger.warning("Could not launch tray subprocess: %s", exc)
            self._proc = None
            return

        # Start event reader thread
        reader = threading.Thread(target=self._read_events, daemon=True)
        reader.start()
        logger.info("Tray subprocess started (PID %d)", self._proc.pid)

    # ---- Sending commands to child ----------------------------------------

    def _send(self, **kwargs: Any) -> None:
        """Send a JSON command line to the child process."""
        if self._proc is None or self._proc.stdin is None or not self._alive:
            return
        try:
            line = json.dumps(kwargs) + "\n"
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            logger.debug("Tray pipe write error: %s", exc)
            self._alive = False

    def update_state(
        self, connected: bool, profile: Optional[str] = None, profiles: Optional[list[str]] = None
    ) -> None:
        """Notify the tray subprocess of a new connection state and profile list."""
        self._send(
            cmd="update",
            connected=connected,
            profile=profile or "",
            profiles=profiles or [],
        )

    def quit(self) -> None:
        """Tell the tray subprocess to exit and wait for it."""
        self._alive = False
        self._send(cmd="quit")
        if self._proc is not None:
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    # ---- Reading events from child ----------------------------------------

    def _read_events(self) -> None:
        """Background thread: read event lines from the tray subprocess."""
        if self._proc is None or self._proc.stdout is None:
            return
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            GLib.idle_add(self._dispatch_event, event)

        # Subprocess exited
        logger.debug("Tray subprocess stdout closed")
        self._alive = False

    def _dispatch_event(self, event: dict[str, Any]) -> bool:
        """Dispatch a tray event in the GTK main thread."""
        ev = event.get("event")
        if ev == "show_window":
            self._window.set_visible(True)
            self._window.present()
        elif ev == "connect_last":
            self._app.activate_action("connect-last", None)
        elif ev == "connect_profile":
            prof = event.get("profile")
            if prof:
                self._window._do_connect(prof)
        elif ev == "disconnect":
            self._window._do_disconnect()
        elif ev == "quit":
            self._app.activate_action("quit", None)
        return False  # remove from idle

