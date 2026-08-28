#!/usr/bin/env python3
"""Ubuntu VPN Client — Network Engine.

Low-level WireGuard management: config parsing, profile CRUD,
privileged helper invocation via pkexec, kill-switch and DNS control.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

from xray_manager import XrayManager

__all__ = [
    "WireGuardConfig",
    "ConfigManager",
    "VPNManager",
    "SystemDependencyChecker",
]

logger = logging.getLogger("vpn_manager")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HELPER_PATHS = [
    "/usr/local/lib/wavez-vpn/vpn-helper",
    "/usr/local/lib/ubuntu-vpn/vpn-helper",
]
HELPER_PATH = "/usr/local/lib/wavez-vpn/vpn-helper"
HELPER_DEV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vpn-helper")
CONFIG_DIR = Path.home() / ".config" / "wavez-vpn"
LEGACY_CONFIG_DIR = Path.home() / ".config" / "ubuntu-vpn"
PROFILES_DIR = CONFIG_DIR / "profiles"
STATE_FILE = CONFIG_DIR / "state.json"
PKEXEC_DISMISSED_CODES = {126, 127}
SUBPROCESS_TIMEOUT = 60
IFACE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,15}$")
IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


# ---------------------------------------------------------------------------
# WireGuardConfig — dataclass + parser
# ---------------------------------------------------------------------------


@dataclass
class WireGuardConfig:
    """Parsed WireGuard configuration file."""

    name: str
    interface: dict[str, str] = field(default_factory=dict)
    peers: list[dict[str, str]] = field(default_factory=list)
    raw_content: str = ""

    # ---- Factories --------------------------------------------------------

    @classmethod
    def from_file(cls, path: Path) -> "WireGuardConfig":
        """Parse a .conf file from *path*.

        Raises ``ValueError`` on malformed content.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
        content = path.read_text(encoding="utf-8")
        name = path.stem
        return cls.from_string(content, name)

    @classmethod
    def from_string(cls, content: str, name: str) -> "WireGuardConfig":
        """Parse WireGuard config from a raw string."""
        interface: dict[str, str] = {}
        peers: list[dict[str, str]] = []
        current_section: Optional[str] = None
        current_peer: dict[str, str] = {}

        for raw_line in content.splitlines():
            line = raw_line.strip()
            # skip empty lines & comments
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            # section headers
            lower = line.lower()
            if lower == "[interface]":
                current_section = "interface"
                continue
            if lower == "[peer]":
                if current_section == "peer" and current_peer:
                    peers.append(current_peer)
                current_section = "peer"
                current_peer = {}
                continue

            # key = value
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if current_section == "interface":
                interface[key] = value
            elif current_section == "peer":
                current_peer[key] = value

        # flush last peer
        if current_section == "peer" and current_peer:
            peers.append(current_peer)

        # basic validation
        if not interface.get("PrivateKey"):
            raise ValueError(
                f"Config '{name}': [Interface] section must contain PrivateKey"
            )
        if not interface.get("Address"):
            raise ValueError(
                f"Config '{name}': [Interface] section must contain Address"
            )
        if not peers:
            raise ValueError(f"Config '{name}': at least one [Peer] section is required")
        for idx, peer in enumerate(peers):
            if not peer.get("PublicKey"):
                raise ValueError(
                    f"Config '{name}': [Peer] #{idx + 1} must contain PublicKey"
                )

        return cls(
            name=name,
            interface=interface,
            peers=peers,
            raw_content=content,
        )

    # ---- Protocol & Obfuscation -------------------------------------------

    @property
    def is_amnezia(self) -> bool:
        """Return True if this configuration contains AmneziaWG obfuscation parameters."""
        awg_keys = {"jc", "jmin", "jmax", "s1", "s2", "h1", "h2", "h3", "h4"}
        return any(k.lower() in awg_keys for k in self.interface)

    @property
    def protocol_name(self) -> str:
        """Return human-readable protocol name ('AmneziaWG' or 'WireGuard')."""
        return "AmneziaWG" if self.is_amnezia else "WireGuard"

    # ---- Serialization ----------------------------------------------------

    def to_conf(self) -> str:
        """Serialize back to WireGuard / AmneziaWG .conf format."""
        lines: list[str] = ["[Interface]"]
        # Canonical key ordering including AmneziaWG keys
        iface_order = [
            "PrivateKey", "Address", "DNS", "ListenPort", "MTU",
            "Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4",
            "Table", "PreUp", "PostUp", "PreDown", "PostDown",
        ]
        written_keys: set[str] = set()
        # Case-insensitive map of interface keys
        key_map = {k.lower(): (k, v) for k, v in self.interface.items()}
        for order_key in iface_order:
            lower_k = order_key.lower()
            if lower_k in key_map:
                orig_k, val = key_map[lower_k]
                lines.append(f"{order_key} = {val}")
                written_keys.add(lower_k)
        for k, v in self.interface.items():
            if k.lower() not in written_keys:
                lines.append(f"{k} = {v}")
        lines.append("")

        peer_order = [
            "PublicKey", "PresharedKey", "AllowedIPs", "Endpoint",
            "PersistentKeepalive",
        ]
        for peer in self.peers:
            lines.append("[Peer]")
            written_keys = set()
            p_map = {pk.lower(): (pk, pv) for pk, pv in peer.items()}
            for order_key in peer_order:
                lower_k = order_key.lower()
                if lower_k in p_map:
                    orig_k, val = p_map[lower_k]
                    lines.append(f"{order_key} = {val}")
                    written_keys.add(lower_k)
            for pk, pv in peer.items():
                if pk.lower() not in written_keys:
                    lines.append(f"{pk} = {pv}")
            lines.append("")

        return "\n".join(lines)

    # ---- Accessors --------------------------------------------------------

    def get_endpoint_ip(self) -> Optional[str]:
        """Return the IP address of the first peer endpoint, or *None*."""
        if not self.peers:
            return None
        endpoint = self.peers[0].get("Endpoint", "")
        if not endpoint:
            return None
        # endpoint is host:port
        host = endpoint.rsplit(":", 1)[0]
        # strip brackets from IPv6
        host = host.strip("[]")
        if IPV4_RE.match(host):
            return host
        # try to resolve hostname
        try:
            info = socket.getaddrinfo(host, None, socket.AF_INET)
            if info:
                return info[0][4][0]
        except (socket.gaierror, OSError):
            pass
        return host  # return as-is if resolution fails

    def get_endpoint_host_port(self) -> Optional[str]:
        """Return full endpoint string (host:port) of first peer."""
        if not self.peers:
            return None
        return self.peers[0].get("Endpoint")

    def get_dns_servers(self) -> list[str]:
        """Return list of DNS server addresses from Interface/DNS."""
        dns_raw = self.interface.get("DNS", "")
        if not dns_raw:
            return []
        servers = [s.strip() for s in dns_raw.split(",") if s.strip()]
        return servers


# ---------------------------------------------------------------------------
# ConfigManager — profile CRUD
# ---------------------------------------------------------------------------


class ConfigManager:
    """Manages WireGuard profiles in ``~/.config/ubuntu-vpn/profiles/``."""

    def __init__(self) -> None:
        self.config_dir: Path = CONFIG_DIR
        self.profiles_dir: Path = PROFILES_DIR
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # Migrate profiles from legacy dir if new dir is empty
        legacy_profiles = LEGACY_CONFIG_DIR / "profiles"
        if legacy_profiles.is_dir() and not any(self.profiles_dir.glob("*.conf")):
            for f in legacy_profiles.glob("*.conf"):
                try:
                    shutil.copy2(f, self.profiles_dir / f.name)
                except Exception:
                    pass
            logger.info("Migrated existing profiles from %s", legacy_profiles)

        # Restrict permissions to owner only
        try:
            os.chmod(self.config_dir, 0o700)
            os.chmod(self.profiles_dir, 0o700)
        except OSError as exc:
            logger.warning("Could not set restrictive permissions: %s", exc)

    def list_profiles(self) -> list[WireGuardConfig]:
        """Return all parsed profiles sorted by name."""
        profiles: list[WireGuardConfig] = []
        for conf_file in sorted(self.profiles_dir.glob("*.conf")):
            try:
                cfg = WireGuardConfig.from_file(conf_file)
                profiles.append(cfg)
            except (ValueError, OSError) as exc:
                logger.warning("Skipping invalid config %s: %s", conf_file.name, exc)
        return profiles

    def import_config(self, source_path: Path) -> WireGuardConfig:
        """Import a .conf file into profiles directory.

        Handles duplicate names by appending ``_1``, ``_2``, etc.
        """
        source_path = Path(source_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source config not found: {source_path}")

        # Validate content first
        cfg = WireGuardConfig.from_file(source_path)

        # Determine unique destination name
        base_name = source_path.stem
        dest_name = base_name
        counter = 1
        while (self.profiles_dir / f"{dest_name}.conf").exists():
            dest_name = f"{base_name}_{counter}"
            counter += 1

        dest_path = self.profiles_dir / f"{dest_name}.conf"
        shutil.copy2(source_path, dest_path)
        os.chmod(dest_path, 0o600)

        # Re-parse with new name
        cfg = WireGuardConfig.from_file(dest_path)
        logger.info("Imported profile '%s' from %s", cfg.name, source_path)
        return cfg

    def save_config(self, config: WireGuardConfig) -> Path:
        """Write *config* to the profiles directory (overwrite if exists)."""
        dest_path = self.profiles_dir / f"{config.name}.conf"
        content = config.to_conf()
        dest_path.write_text(content, encoding="utf-8")
        os.chmod(dest_path, 0o600)
        logger.info("Saved profile '%s'", config.name)
        return dest_path

    def delete_config(self, name: str) -> bool:
        """Delete the named profile. Returns *True* if deleted."""
        conf_path = self.profiles_dir / f"{name}.conf"
        if conf_path.is_file():
            conf_path.unlink()
            logger.info("Deleted profile '%s'", name)
            return True
        logger.warning("Profile '%s' not found for deletion", name)
        return False

    def get_config(self, name: str) -> Optional[WireGuardConfig]:
        """Return parsed config by name, or *None*."""
        conf_path = self.profiles_dir / f"{name}.conf"
        if not conf_path.is_file():
            return None
        try:
            return WireGuardConfig.from_file(conf_path)
        except (ValueError, OSError) as exc:
            logger.error("Error loading profile '%s': %s", name, exc)
            return None

    def get_config_path(self, name: str) -> Path:
        """Return full path for a named profile."""
        return self.profiles_dir / f"{name}.conf"

    def get_last_connected(self) -> Optional[str]:
        """Read last connected profile name from state file."""
        if not STATE_FILE.is_file():
            return None
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data.get("last_connected")
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not read state file: %s", exc)
            return None

    def set_last_connected(self, name: str) -> None:
        """Persist last connected profile name."""
        data: dict[str, Any] = {}
        if STATE_FILE.is_file():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        data["last_connected"] = name
        try:
            STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write state file: %s", exc)


# ---------------------------------------------------------------------------
# VPNManager — connection lifecycle
# ---------------------------------------------------------------------------


class VPNManager:
    """Manages VPN connections by invoking the privileged helper via *pkexec*."""

    def __init__(self, config_manager: ConfigManager, settings_manager: Optional[Any] = None) -> None:
        self.config_manager: ConfigManager = config_manager
        if settings_manager is None:
            from settings_manager import SettingsManager
            self.settings_manager = SettingsManager()
        else:
            self.settings_manager = settings_manager
        self._active_config_name: Optional[str] = None
        self._active_interface: Optional[str] = None
        self._killswitch_active: bool = False
        self._connected: bool = False
        self.xray_manager = XrayManager()

    # ---- Public API -------------------------------------------------------

    def connect(
        self, config_name: str, enable_killswitch: bool = False
    ) -> tuple[bool, str]:
        """Bring up a tunnel (Xray Reality or WireGuard) for *config_name*.

        Returns ``(success, message)``.
        """
        # 1. Try Xray Reality backend first for Incy / VLESS servers
        server_data = self.xray_manager.get_server_data(config_name)
        if server_data and self.xray_manager.is_available():
            logger.info("Connecting to Xray Reality profile '%s'...", config_name)
            ok, msg = self.xray_manager.connect(config_name, server_data)
            if ok:
                self._active_config_name = config_name
                self._active_interface = "xray-proxy"
                self._connected = True
                self.config_manager.set_last_connected(config_name)
                logger.info("Connected to '%s' via Xray Reality engine", config_name)
                return True, f"Connected to {config_name} (Xray Reality)"
            else:
                logger.warning("Xray connect returned: %s, falling back to WireGuard", msg)

        # 2. WireGuard / AmneziaWG backend
        config = self.config_manager.get_config(config_name)
        if config is None:
            return False, f"Profile '{config_name}' not found"

        config_path = self.config_manager.get_config_path(config_name)
        if not config_path.is_file():
            return False, f"Config file missing: {config_path}"

        logger.info("Connecting to profile '%s' via WireGuard...", config_name)

        result = self._run_helper("up", str(config_path))
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error during connect")
            logger.error("Connect failed: %s", error_msg)
            return False, error_msg

        interface = result.get("interface", config_name)
        self._active_config_name = config_name
        self._active_interface = interface
        self._connected = True

        # DNS protection: use config DNS or fallback to settings default DNS (Google/Incy default)
        dns_servers = config.get_dns_servers()
        if not dns_servers:
            def_dns = self.settings_manager.get("default_dns", "8.8.8.8, 8.8.4.4")
            if def_dns:
                dns_servers = [s.strip() for s in def_dns.split(",") if s.strip()]

        if dns_servers:
            args = ["dns-set", interface] + dns_servers
            dns_res = self._run_helper(*args)
            if not dns_res.get("success"):
                logger.warning("DNS setup warning: %s", dns_res.get("error"))

        # Kill-switch
        if enable_killswitch:
            ks_ok, ks_msg = self.enable_killswitch(config)
            if not ks_ok:
                logger.warning("Kill-switch warning: %s", ks_msg)

        self.config_manager.set_last_connected(config_name)
        logger.info("Connected to '%s' via interface '%s'", config_name, interface)
        return True, f"Connected to {config_name}"

    def disconnect(self) -> tuple[bool, str]:
        """Tear down the active tunnel. Returns ``(success, message)``."""
        if not self._connected and not self.xray_manager.is_connected() and not self._active_interface:
            return False, "No active connection"

        # 1. Disconnect Xray if running
        if self.xray_manager.is_connected():
            self.xray_manager.disconnect()
            self._active_config_name = None
            self._active_interface = None
            self._connected = False
            logger.info("Disconnected from Xray backend")
            return True, "Disconnected"

        interface = self._active_interface
        if not interface:
            self._connected = False
            return True, "Disconnected"

        logger.info("Disconnecting interface '%s'...", interface)

        # Disable kill-switch first so traffic can flow normally after disconnect
        if self._killswitch_active:
            ks_ok, ks_msg = self.disable_killswitch()
            if not ks_ok:
                logger.warning("Kill-switch disable warning: %s", ks_msg)

        # Restore DNS
        self.restore_dns(interface)

        result = self._run_helper("down", interface)
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error during disconnect")
            logger.error("Disconnect failed: %s", error_msg)
            return False, error_msg

        self._active_config_name = None
        self._active_interface = None
        self._connected = False
        logger.info("Disconnected from interface '%s'", interface)
        return True, "Disconnected"

    def get_status(self) -> dict[str, Any]:
        """Query current VPN / proxy interface status."""
        if self.xray_manager.is_connected():
            self._connected = True
            return self.xray_manager.get_status()

        if not self._active_interface:
            # Try to detect any active WireGuard interface
            result = self._run_helper("status")
            if result.get("success") and result.get("connected"):
                self._connected = True
                self._active_interface = result.get("interface")
                return result
            self._connected = False
            return {"connected": False}

        result = self._run_helper("status", self._active_interface)
        if not result.get("success"):
            self._connected = False
            return {"connected": False, "error": result.get("error", "")}

        self._connected = result.get("connected", False)
        if not self._connected:
            self._active_interface = None
            self._active_config_name = None
        return result

    def get_transfer_stats(self) -> dict[str, Any]:
        """Return transfer statistics for the active connection."""
        status = self.get_status()
        if not status.get("connected"):
            return {
                "rx_bytes": 0,
                "tx_bytes": 0,
                "rx_human": "0 B",
                "tx_human": "0 B",
            }
        rx = status.get("transfer_rx", 0)
        tx = status.get("transfer_tx", 0)

        # Fallback to direct kernel interface counters
        if rx == 0 and tx == 0:
            for iface in ("tun_wavez", self._active_interface or "", "tun0", "wg0"):
                if not iface:
                    continue
                rx_p = Path(f"/sys/class/net/{iface}/statistics/rx_bytes")
                tx_p = Path(f"/sys/class/net/{iface}/statistics/tx_bytes")
                if rx_p.is_file() and tx_p.is_file():
                    try:
                        rx = int(rx_p.read_text().strip())
                        tx = int(tx_p.read_text().strip())
                        break
                    except Exception:
                        pass

        return {
            "rx_bytes": rx,
            "tx_bytes": tx,
            "rx_human": self._format_bytes(rx),
            "tx_human": self._format_bytes(tx),
        }

    def get_external_ip(self) -> Optional[str]:
        """Fetch the external (public) IP address."""
        proxies = None
        if self.xray_manager.is_connected():
            proxies = {"http": "http://127.0.0.1:20809", "https": "http://127.0.0.1:20809"}

        urls = [
            "https://api.ipify.org?format=text",
            "https://ifconfig.me/ip",
            "https://icanhazip.com",
            "https://checkip.amazonaws.com",
            "https://ipinfo.io/ip",
            "https://api4.ipify.org",
        ]
        for url in urls:
            try:
                resp = requests.get(url, proxies=proxies, headers={"User-Agent": "curl/7.88.1"}, timeout=4)
                if resp.status_code == 200:
                    ip = resp.text.strip()
                    if ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                        return ip
            except Exception:
                continue

        # Fallback via urllib
        if proxies:
            try:
                import urllib.request
                ph = urllib.request.ProxyHandler({"http": "http://127.0.0.1:20809", "https": "http://127.0.0.1:20809"})
                opener = urllib.request.build_opener(ph)
                req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "curl/7.88.1"})
                with opener.open(req, timeout=4) as r:
                    ip = r.read().decode("utf-8").strip()
                    if ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                        return ip
            except Exception:
                pass

        logger.warning("Could not determine external IP")
        return None

    def ping_endpoint(self, endpoint: str) -> Optional[float]:
        """Ping *endpoint* (IP or host:port). Returns RTT in ms, or *None*."""
        # Strip port if present
        host = endpoint.rsplit(":", 1)[0].strip("[]")
        try:
            result = subprocess.run(
                ["ping", "-c", "3", "-W", "3", host],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                # Parse average RTT from "min/avg/max/mdev = ..."
                match = re.search(
                    r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms",
                    result.stdout,
                )
                if match:
                    return float(match.group(1))
                # Alternative format: "round-trip min/avg/max ..."
                match = re.search(
                    r"round-trip min/avg/max(?:/\w+)? = [\d.]+/([\d.]+)/",
                    result.stdout,
                )
                if match:
                    return float(match.group(1))
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("Ping to %s failed: %s", host, exc)
        return None

    def is_connected(self) -> bool:
        """Quick check of connection state (cached, does not query helper)."""
        return self._connected

    def get_active_config_name(self) -> Optional[str]:
        """Return name of the currently active profile, or *None*."""
        return self._active_config_name

    def get_active_interface(self) -> Optional[str]:
        """Return name of the active WireGuard interface, or *None*."""
        return self._active_interface

    def is_killswitch_active(self) -> bool:
        """Return whether the kill-switch is currently enabled."""
        return self._killswitch_active

    def is_awg_installed(self) -> bool:
        """Return True if awg-quick (AmneziaWG) binary is installed."""
        return shutil.which("awg-quick") is not None or shutil.which("awg") is not None

    def check_profile_health(self, config_name: str, timeout: float = 3.0) -> Any:
        """Run full health check on the specified profile."""
        from health_checker import ConfigHealthChecker
        cfg = self.config_manager.get_config(config_name)
        if cfg is None:
            from health_checker import HealthReport
            return HealthReport(profile_name=config_name, endpoint_raw="", error=f"Profile '{config_name}' not found")
        return ConfigHealthChecker.check_config(config_name, cfg, timeout=timeout)

    def batch_check_profiles(self, timeout: float = 3.0) -> dict[str, Any]:
        """Run concurrent health checks on all stored profiles."""
        from health_checker import ConfigHealthChecker
        profiles = [(cfg.name, cfg) for cfg in self.config_manager.list_profiles()]
        return ConfigHealthChecker.batch_check(profiles, timeout=timeout)

    # ---- Kill-switch & DNS ------------------------------------------------

    def enable_killswitch(self, config: WireGuardConfig) -> tuple[bool, str]:
        """Enable traffic kill-switch via iptables."""
        endpoint_ip = config.get_endpoint_ip()
        if not endpoint_ip:
            return False, "Cannot determine endpoint IP for kill-switch"
        interface = self._active_interface
        if not interface:
            return False, "No active interface for kill-switch"

        result = self._run_helper("killswitch-on", endpoint_ip, interface)
        if result.get("success"):
            self._killswitch_active = True
            logger.info("Kill-switch enabled")
            return True, "Kill-switch enabled"
        error = result.get("error", "Unknown error")
        logger.error("Kill-switch enable failed: %s", error)
        return False, error

    def disable_killswitch(self) -> tuple[bool, str]:
        """Disable traffic kill-switch."""
        result = self._run_helper("killswitch-off")
        if result.get("success"):
            self._killswitch_active = False
            logger.info("Kill-switch disabled")
            return True, "Kill-switch disabled"
        error = result.get("error", "Unknown error")
        logger.error("Kill-switch disable failed: %s", error)
        return False, error

    def set_dns(
        self, config: WireGuardConfig, interface: str
    ) -> tuple[bool, str]:
        """Set DNS servers from *config* on *interface*."""
        dns_servers = config.get_dns_servers()
        if not dns_servers:
            return True, "No DNS servers in config"

        args = ["dns-set", interface] + dns_servers
        result = self._run_helper(*args)
        if result.get("success"):
            logger.info("DNS set to %s on %s", dns_servers, interface)
            return True, "DNS configured"
        error = result.get("error", "Unknown error")
        logger.warning("DNS set failed: %s", error)
        return False, error

    def restore_dns(self, interface: str) -> tuple[bool, str]:
        """Restore DNS settings for *interface*."""
        result = self._run_helper("dns-restore", interface)
        if result.get("success"):
            logger.info("DNS restored on %s", interface)
            return True, "DNS restored"
        error = result.get("error", "Unknown error")
        logger.debug("DNS restore note: %s", error)
        return False, error

    # ---- Internal helpers -------------------------------------------------

    def _resolve_helper_path(self) -> str:
        """Return the path to the vpn-helper script."""
        for p in HELPER_PATHS:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        if os.path.isfile(HELPER_DEV_PATH) and os.access(HELPER_DEV_PATH, os.X_OK):
            logger.debug("Using development helper path: %s", HELPER_DEV_PATH)
            return HELPER_DEV_PATH
        return HELPER_PATH

    def _run_helper(self, *args: str) -> dict[str, Any]:
        """Execute ``pkexec vpn-helper <args>`` and parse JSON response.

        Handles:
        * pkexec dismissed by user (exit 126/127)
        * helper not found
        * timeout
        * malformed JSON
        """
        helper = self._resolve_helper_path()
        cmd = ["pkexec", helper, *args]
        logger.debug("Running: %s", " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except FileNotFoundError:
            logger.error("pkexec not found on this system")
            return {
                "success": False,
                "error": "pkexec is not installed. Install policykit-1.",
            }
        except subprocess.TimeoutExpired:
            logger.error("Helper command timed out after %ds", SUBPROCESS_TIMEOUT)
            return {"success": False, "error": "Operation timed out"}

        if proc.returncode in PKEXEC_DISMISSED_CODES:
            logger.info("Authentication dismissed by user")
            return {"success": False, "error": "Authentication dismissed by user"}

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if stderr:
            logger.debug("Helper stderr: %s", stderr)

        if not stdout:
            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": f"Helper exited with code {proc.returncode}. {stderr}",
                }
            return {"success": False, "error": "Helper returned empty response"}

        try:
            data = json.loads(stdout)
            return data
        except json.JSONDecodeError as exc:
            logger.error("Malformed JSON from helper: %s (%s)", stdout[:200], exc)
            return {
                "success": False,
                "error": f"Malformed response from helper: {stdout[:100]}",
            }

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Format bytes into human-readable string (KiB, MiB, GiB)."""
        if num_bytes < 0:
            num_bytes = 0
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if abs(num_bytes) < 1024.0:
                if unit == "B":
                    return f"{num_bytes} {unit}"
                return f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024.0  # type: ignore[assignment]
        return f"{num_bytes:.1f} PiB"


# ---------------------------------------------------------------------------
# SystemDependencyChecker
# ---------------------------------------------------------------------------


class SystemDependencyChecker:
    """Checks for required system utilities."""

    REQUIRED_BINARIES = {
        "wg": "wireguard-tools",
        "wg-quick": "wireguard-tools",
        "pkexec": "policykit-1",
        "iptables": "iptables",
    }

    @staticmethod
    def check_all() -> dict[str, bool]:
        """Check availability of each required binary.

        Returns a mapping ``{binary_name: is_available}``.
        """
        result: dict[str, bool] = {}
        for binary in SystemDependencyChecker.REQUIRED_BINARIES:
            result[binary] = shutil.which(binary) is not None
        return result

    @staticmethod
    def get_missing() -> list[str]:
        """Return list of missing binary names."""
        return [
            name
            for name, available in SystemDependencyChecker.check_all().items()
            if not available
        ]

    @staticmethod
    def get_missing_packages() -> list[str]:
        """Return apt package names for missing binaries."""
        packages: list[str] = []
        seen: set[str] = set()
        for binary, package in SystemDependencyChecker.REQUIRED_BINARIES.items():
            if shutil.which(binary) is None and package not in seen:
                packages.append(package)
                seen.add(package)
        return packages

    @staticmethod
    def check_wireguard_module() -> bool:
        """Check if the WireGuard kernel module is available."""
        # Check /sys/module first (loaded)
        if Path("/sys/module/wireguard").is_dir():
            return True
        # Try modprobe dry run
        try:
            result = subprocess.run(
                ["modprobe", "-n", "wireguard"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # On kernels 5.6+ wireguard is built-in, check /proc/modules
        try:
            modules = Path("/proc/modules").read_text()
            if "wireguard" in modules:
                return True
        except OSError:
            pass
        # If wg binary exists, assume module is available
        return shutil.which("wg") is not None

    @staticmethod
    def check_awg_installed() -> bool:
        """Check if AmneziaWG (awg / awg-quick) tools are installed."""
        return shutil.which("awg-quick") is not None or shutil.which("awg") is not None
