#!/usr/bin/env python3
"""Ubuntu VPN Client — Settings Manager.

Loads, saves, and synchronizes application settings with Incy defaults.
Stored in ~/.config/ubuntu-vpn/settings.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("settings_manager")

SETTINGS_DIR = Path.home() / ".config" / "wavez-vpn"
LEGACY_SETTINGS_DIR = Path.home() / ".config" / "ubuntu-vpn"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
INCY_PREFERENCES_FILE = Path.home() / ".config" / "incy" / "preferences.json"

# Default excluded subnets matching Incy
INCY_DEFAULT_EXCLUDED_ROUTES = [
    "10.0.0.0/8",
    "100.64.0.0/10",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "224.0.0.0/4",
    "255.255.255.255/32",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8",
]

# Defaults mirroring Incy config
INCY_DEFAULTS: dict[str, Any] = {
    "default_dns": "8.8.8.8, 8.8.4.4",
    "remote_doh_dns": "https://1.1.1.1/dns-query",
    "allow_lan": True,
    "bypass_private_ips": True,
    "excluded_routes": INCY_DEFAULT_EXCLUDED_ROUTES,
    "killswitch_default": False,
    "auto_connect": False,
    "minimize_to_tray": True,
    "start_minimized": False,
    "auto_reconnect_unlock": False,
    "ping_timeout": 3,
    "ping_test_target": "https://www.gstatic.com/generate_204",
    "preferred_ip_type": "auto",  # auto, ipv4, ipv6
    "default_mtu": 1420,
    "subscription_url": "",
    "app_theme": "system",
    "app_language": "ru",
    "ai_optimization": True,
    "ai_env_proxy": True,
    "auto_check_updates": True,
}


class SettingsManager:
    """Manages application settings with JSON persistence."""

    def __init__(self, settings_path: Optional[Path] = None) -> None:
        self.settings_path = settings_path or SETTINGS_FILE
        self._data: dict[str, Any] = dict(INCY_DEFAULTS)
        self._load()

    def _load(self) -> None:
        """Load settings from JSON, initializing with Incy config if present."""
        if not self.settings_path.is_file() and (LEGACY_SETTINGS_DIR / "settings.json").is_file():
            try:
                legacy_data = (LEGACY_SETTINGS_DIR / "settings.json").read_text(encoding="utf-8")
                self.settings_path.parent.mkdir(parents=True, exist_ok=True)
                self.settings_path.write_text(legacy_data, encoding="utf-8")
                logger.info("Migrated legacy settings to %s", self.settings_path)
            except Exception:
                pass

        if self.settings_path.is_file():
            try:
                loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data.update(loaded)
                    return
            except Exception as exc:
                logger.warning("Could not read settings file: %s", exc)

        # If settings.json doesn't exist yet, try to import live from Incy preferences
        if INCY_PREFERENCES_FILE.is_file():
            self.import_from_incy()
        else:
            self.save()

    def save(self) -> None:
        """Write settings to ~/.config/ubuntu-vpn/settings.json."""
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            logger.info("Saved settings to %s", self.settings_path)
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value."""
        return self._data.get(key, default if default is not None else INCY_DEFAULTS.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Set setting value and optionally save."""
        self._data[key] = value
        if auto_save:
            self.save()

    def reset_to_defaults(self) -> None:
        """Reset all settings to Incy defaults."""
        self._data = dict(INCY_DEFAULTS)
        self.save()

    def import_from_incy(self) -> bool:
        """Import preferences directly from ~/.config/incy/preferences.json."""
        if not INCY_PREFERENCES_FILE.is_file():
            return False
        try:
            raw = json.loads(INCY_PREFERENCES_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return False

            if "vpnDns" in raw and raw["vpnDns"]:
                self._data["default_dns"] = raw["vpnDns"].replace(",", ", ")
            if "remoteDNS" in raw and raw["remoteDNS"]:
                self._data["remote_doh_dns"] = raw["remoteDNS"]
            if "allowLanConnections" in raw:
                self._data["allow_lan"] = bool(raw["allowLanConnections"])
            if "bypassPrivateIPs" in raw:
                self._data["bypass_private_ips"] = bool(raw["bypassPrivateIPs"])
            if "killSwitch" in raw:
                self._data["killswitch_default"] = bool(raw["killSwitch"])
            if "autoConnect" in raw:
                self._data["auto_connect"] = bool(raw["autoConnect"])
            if "minimizeToTray" in raw:
                self._data["minimize_to_tray"] = bool(raw["minimizeToTray"])
            if "startMinimized" in raw:
                self._data["start_minimized"] = bool(raw["startMinimized"])
            if "pingTimeout" in raw:
                self._data["ping_timeout"] = int(raw["pingTimeout"])
            if "pingTestURL" in raw and raw["pingTestURL"]:
                self._data["ping_test_target"] = raw["pingTestURL"]
            if "preferredIPType" in raw:
                self._data["preferred_ip_type"] = raw["preferredIPType"]
            if "tunMtu" in raw and raw["tunMtu"]:
                self._data["default_mtu"] = int(raw["tunMtu"])
            if "excludedRoutes" in raw and raw["excludedRoutes"]:
                lines = [line.strip() for line in raw["excludedRoutes"].splitlines() if line.strip()]
                if lines:
                    self._data["excluded_routes"] = lines

            self.save()
            logger.info("Successfully imported settings from Incy config")
            return True
        except Exception as exc:
            logger.error("Failed to import Incy preferences: %s", exc)
            return False
