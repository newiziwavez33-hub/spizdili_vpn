#!/usr/bin/env python3
"""Ubuntu VPN Client — System Tray Subprocess (GTK3 / AyatanaAppIndicator3).

Runs in a separate GTK3 process to avoid in-process conflict with GTK4.
Handles tray icon rendering and rich interactive click menu with profile switching.

Protocol (JSON lines over stdin/stdout):
  Parent → Child:
    {"cmd": "update", "connected": true, "profile": "Netherlands", "profiles": ["Netherlands", "Germany"]}
    {"cmd": "quit"}

  Child → Parent:
    {"event": "connect_last"}
    {"event": "connect_profile", "profile": "Netherlands"}
    {"event": "disconnect"}
    {"event": "show_window"}
    {"event": "quit"}
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3, GLib, Gtk  # noqa: E402

_ICON_DIRS = [
    Path("/usr/local/share/wavez-vpn/icons"),
    Path("/usr/local/share/ubuntu-vpn/icons"),
    Path(__file__).resolve().parent / "icons",
    Path("/usr/local/share/icons/hicolor/scalable/apps"),
    Path("/usr/share/icons/hicolor/scalable/apps"),
]

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
)


def get_server_flag(name: str) -> str:
    """Return national flag emoji for a given server name."""
    if not name:
        return "🌐"
    lower = name.lower()
    for key, flag in _COUNTRY_FLAGS:
        if key in lower:
            return flag
    return "🌐"


def _find_icon(name: str) -> str:
    """Locate an SVG icon by name, return absolute path or fallback name."""
    for d in _ICON_DIRS:
        p = d / f"{name}.svg"
        if p.is_file():
            return str(p)
    return "network-vpn-symbolic"


class TrayApp:
    """Manages the system tray indicator and its interactive popup menu."""

    def __init__(self) -> None:
        self._connected: bool = False
        self._profile: Optional[str] = None
        self._profiles: list[str] = []

        self._build_indicator()
        self._build_menu()

        # Start reading commands from parent process on stdin
        self._reader_thread = threading.Thread(target=self._read_commands, daemon=True)
        self._reader_thread.start()

    def _build_indicator(self) -> None:
        icon_path = _find_icon("vpn-disconnected")
        icon_dir = str(Path(icon_path).parent)
        icon_name = Path(icon_path).stem

        self._indicator = AyatanaAppIndicator3.Indicator.new(
            "wavez-vpn-client",
            icon_name,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        if Path(icon_dir).is_dir():
            self._indicator.set_icon_theme_path(icon_dir)
        self._indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_title("WaveZ VPN Client")

    def _build_menu(self) -> None:
        self._menu = Gtk.Menu()

        # 1. Header / Status
        self._status_item = Gtk.MenuItem(label="⚪ Статус: Отключено")
        self._status_item.set_sensitive(False)
        self._menu.append(self._status_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        # 2. Connect / Disconnect quick actions
        self._connect_item = Gtk.MenuItem(label="⚡ Подключить последний")
        self._connect_item.connect("activate", lambda _: self._emit("connect_last"))
        self._menu.append(self._connect_item)

        # 3. Profiles submenu
        self._profiles_root_item = Gtk.MenuItem(label="📁 Выбрать сервер")
        self._profiles_menu = Gtk.Menu()
        self._profiles_root_item.set_submenu(self._profiles_menu)
        self._menu.append(self._profiles_root_item)

        self._disconnect_item = Gtk.MenuItem(label="🔴 Отключить VPN")
        self._disconnect_item.connect("activate", lambda _: self._emit("disconnect"))
        self._disconnect_item.set_sensitive(False)
        self._menu.append(self._disconnect_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        # 4. Open application window
        self._show_item = Gtk.MenuItem(label="🖥️ Открыть WaveZ VPN Client")
        self._show_item.connect("activate", lambda _: self._emit("show_window"))
        self._menu.append(self._show_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        # 5. Quit
        quit_item = Gtk.MenuItem(label="🚪 Выход")
        quit_item.connect("activate", lambda _: self._emit("quit"))
        self._menu.append(quit_item)

        self._menu.show_all()
        self._indicator.set_menu(self._menu)
        self._indicator.set_secondary_activate_target(self._show_item)

    def _emit(self, event: str, **kwargs: Any) -> None:
        """Send an event line to the parent process via stdout."""
        try:
            data = {"event": event}
            data.update(kwargs)
            payload = json.dumps(data)
            sys.stdout.write(payload + "\n")
            sys.stdout.flush()
        except (OSError, BrokenPipeError):
            Gtk.main_quit()

    def _read_commands(self) -> None:
        """Read JSON commands from stdin."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
            except json.JSONDecodeError:
                continue
            GLib.idle_add(self._process_command, cmd)

        GLib.idle_add(Gtk.main_quit)

    def _process_command(self, cmd: dict[str, Any]) -> bool:
        """Process incoming command from parent."""
        action = cmd.get("cmd")
        if action == "update":
            connected = bool(cmd.get("connected", False))
            profile = cmd.get("profile")
            profiles = cmd.get("profiles", [])
            self._update_state(connected, profile, profiles)
        elif action == "quit":
            Gtk.main_quit()
        return False

    def _update_state(
        self, connected: bool, profile: Optional[str], profiles: Optional[list[str]] = None
    ) -> None:
        """Update indicator icon, status, and profile menu."""
        self._connected = connected
        self._profile = profile
        if profiles is not None:
            self._profiles = profiles

        if connected:
            icon_name = "vpn-connected"
            flag = get_server_flag(profile or "")
            status_text = f"Подключено: {flag} {profile}" if profile else "Подключено"
            self._status_item.set_label(f"🟢 {status_text}")
        else:
            icon_name = "vpn-disconnected"
            status_text = "Отключено"
            self._status_item.set_label("⚪ Статус: Отключено")

        icon_path = _find_icon(icon_name)
        icon_dir = str(Path(icon_path).parent)
        if Path(icon_dir).is_dir():
            self._indicator.set_icon_theme_path(icon_dir)
        self._indicator.set_icon_full(Path(icon_path).stem, status_text)

        self._connect_item.set_sensitive(not connected)
        self._disconnect_item.set_sensitive(connected)

        # Rebuild profiles submenu
        for child in self._profiles_menu.get_children():
            self._profiles_menu.remove(child)

        if self._profiles:
            self._profiles_root_item.set_visible(True)
            for p in self._profiles:
                flag = get_server_flag(p)
                item_label = f"✓ {flag} {p}" if connected and p == profile else f"  {flag} {p}"
                p_item = Gtk.MenuItem(label=item_label)
                p_name = p
                p_item.connect(
                    "activate",
                    lambda _, name=p_name: self._emit("connect_profile", profile=name),
                )
                self._profiles_menu.append(p_item)
            self._profiles_menu.show_all()
        else:
            empty_item = Gtk.MenuItem(label="Нет доступных серверов")
            empty_item.set_sensitive(False)
            self._profiles_menu.append(empty_item)
            self._profiles_menu.show_all()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    app = TrayApp()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
