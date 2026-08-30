#!/usr/bin/env python3
"""Xray Engine Manager for VLESS Reality & Hysteria2 Proxies.

Manages Xray Core lifecycle, config generation, system proxy routing (via GNOME gsettings),
and live telemetry for Incy and VLESS servers without requiring external subscription keys.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("xray_manager")

XRAY_CANDIDATE_PATHS = [
    Path("/usr/local/bin/xray-core"),
    Path("/usr/local/bin/xray"),
    Path("/usr/bin/xray"),
    Path("/usr/local/lib/wavez-vpn/bin/xray"),
    Path(__file__).resolve().parent / "bin" / "xray",
    Path("/opt/incy/lib/app/resources/bin/xray"),
]

SERVER_JSON_CANDIDATES = [
    Path.home() / ".config" / "wavez-vpn" / "wavez_servers.json",
    Path.home() / ".config" / "wavez-vpn" / "incy_servers.json",
    Path.home() / ".config" / "ubuntu-vpn" / "incy_servers.json",
    Path("/usr/local/share/wavez-vpn/wavez_servers.json"),
    Path(__file__).resolve().parent / "wavez_servers.json",
]
RUN_DIR = Path.home() / ".config" / "wavez-vpn" / "run"

SOCKS_PORT = 20808
HTTP_PORT = 20809


class XrayManager:
    """Manages the Xray core subprocess and system proxy settings."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen[str]] = None
        self._active_profile: Optional[str] = None
        self._active_server_data: Optional[dict[str, Any]] = None
        self._connected: bool = False
        self._start_time: Optional[float] = None
        self._xray_bin = self._find_xray_binary()
        RUN_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _find_xray_binary(cls) -> Optional[Path]:
        """Locate Xray binary on the system."""
        for p in XRAY_CANDIDATE_PATHS:
            if p.is_file() and os.access(p, os.X_OK):
                return p
        which = shutil.which("xray-core") or shutil.which("xray")
        if which:
            return Path(which)
        return None

    def is_available(self) -> bool:
        """Check if Xray core binary is present and executable."""
        self._xray_bin = self._find_xray_binary()
        return self._xray_bin is not None

    def is_connected(self) -> bool:
        """Return True if Xray proxy is active."""
        if self._proc is not None:
            if self._proc.poll() is None:
                return True
            # Process terminated unexpectedly
            self._connected = False
            self._proc = None
        return False

    def get_active_profile(self) -> Optional[str]:
        return self._active_profile

    def get_server_data(self, profile_name: str) -> Optional[dict[str, Any]]:
        """Find server metadata by profile name with high-precision matching."""
        # 1. Check if profile .conf has explicit header metadata
        user_conf = Path.home() / ".config" / "wavez-vpn" / "profiles" / f"{profile_name}.conf"
        target_endpoint = None
        target_uuid = None
        target_name = None
        if user_conf.is_file():
            try:
                for line in user_conf.read_text(encoding="utf-8").splitlines():
                    if line.startswith("# Incy Profile:"):
                        target_name = line.split(":", 1)[1].strip()
                    elif line.startswith("# Endpoint:"):
                        target_endpoint = line.split(":", 1)[1].strip()
                    elif line.startswith("# UUID:"):
                        target_uuid = line.split(":", 1)[1].strip()
            except Exception:
                pass

        # 2. If .conf contains direct VLESS metadata, construct server_data directly!
        if target_uuid and target_endpoint:
            addr, _, port_str = target_endpoint.partition(":")
            port = int(port_str) if port_str.isdigit() else 443
            conf_lines = user_conf.read_text(encoding="utf-8").splitlines() if user_conf.is_file() else []
            sni = addr
            pbk = ""
            sid = ""
            flow = "xtls-rprx-vision"
            fp = "firefox"
            proto = "VLESS"
            uri = ""
            for l in conf_lines:
                if l.startswith("# SNI:"):
                    sni = l.split(":", 1)[1].strip()
                elif l.startswith("# Reality PublicKey:"):
                    pbk = l.split(":", 1)[1].strip()
                elif l.startswith("# ShortID:"):
                    sid = l.split(":", 1)[1].strip()
                elif l.startswith("# Flow:"):
                    flow = l.split(":", 1)[1].strip()
                elif l.startswith("# Fingerprint:"):
                    fp = l.split(":", 1)[1].strip()
                elif l.startswith("# Protocol:"):
                    proto = l.split(":", 1)[1].strip()
                elif l.startswith("# URI:"):
                    uri = l.split(":", 1)[1].strip()

            return {
                "name": target_name or profile_name,
                "ascii_name": profile_name,
                "protocol": proto,
                "address": addr,
                "port": port,
                "uuid": target_uuid,
                "public_key": pbk,
                "sni": sni,
                "short_id": sid,
                "flow": flow,
                "fingerprint": fp,
                "security": "reality",
                "network": "tcp",
                "uri": uri,
            }

        # 3. Search candidate JSON databases
        for target_path in SERVER_JSON_CANDIDATES:
            if not target_path.is_file():
                continue
            try:
                data = json.loads(target_path.read_text(encoding="utf-8"))
                servers = data.get("servers", [])
                
                # Priority 1: Exact match by target_uuid / target_endpoint from .conf
                if target_uuid:
                    for s in servers:
                        if s.get("uuid") == target_uuid and target_endpoint and f"{s.get('address')}:{s.get('port')}" == target_endpoint:
                            return s
                if target_name:
                    for s in servers:
                        if s.get("name") == target_name:
                            return s

                # Priority 2: Exact match on ascii_name
                for s in servers:
                    if s.get("ascii_name") == profile_name:
                        return s

                # Priority 3: Exact match on full name
                for s in servers:
                    if s.get("name") == profile_name:
                        return s

                # Priority 4: Case-insensitive exact match
                prof_lower = profile_name.lower()
                for s in servers:
                    if s.get("ascii_name", "").lower() == prof_lower or s.get("name", "").lower() == prof_lower:
                        return s

                # Priority 5: Exact endpoint match
                for s in servers:
                    if f"{s.get('address')}:{s.get('port')}" == profile_name:
                        return s

                # Priority 6: Prefix or substring match as fallback
                for s in servers:
                    if prof_lower in s.get("name", "").lower() or prof_lower in s.get("ascii_name", "").lower():
                        return s
            except Exception:
                continue

        return None

    def connect(self, profile_name: str, server_data: Optional[dict[str, Any]] = None) -> tuple[bool, str]:
        """Start Xray proxy with the specified server configuration."""
        if self._xray_bin is None:
            return False, "Xray core binary not found (/opt/incy/lib/app/resources/bin/xray)"

        # Always cleanly disconnect and wait for ports to be completely free
        self.disconnect()

        s_data = server_data or self.get_server_data(profile_name)
        if not s_data:
            return False, f"Server parameters for '{profile_name}' not found"

        full_json_str = s_data.get("full_config_json")
        cfg = None
        if full_json_str:
            try:
                cfg = json.loads(full_json_str)
            except Exception as exc:
                logger.warning("Invalid full_config_json, rebuilding dynamically: %s", exc)

        if not cfg:
            proto = s_data.get("protocol", "vless").lower()
            if proto == "wireguard":
                # Pure user-space WireGuard in Xray Core (No root or /etc/wireguard required)
                secret_key = s_data.get("secret_key", "")
                public_key = s_data.get("public_key", "")
                addr = s_data.get("address", "162.159.193.1")
                port = int(s_data.get("port", 2408))
                local_addrs = s_data.get("local_address", ["172.16.0.2/32"])
                if isinstance(local_addrs, str):
                    local_addrs = [local_addrs]
                local_addrs = [a if "/" in a else f"{a}/32" for a in local_addrs]

                cfg = {
                    "log": {"loglevel": "warning"},
                    "outbounds": [
                        {
                            "tag": "proxy",
                            "protocol": "wireguard",
                            "settings": {
                                "secretKey": secret_key,
                                "address": local_addrs,
                                "peers": [
                                    {
                                        "publicKey": public_key,
                                        "endpoint": f"{addr}:{port}",
                                        "keepAlive": 25
                                    }
                                ]
                            }
                        },
                        {"tag": "direct", "protocol": "freedom"}
                    ]
                }
            else:
                # VLESS Reality or WebSocket CDN
                sec = s_data.get("security", "reality")
                net = s_data.get("network", "tcp")
                stream_settings = {
                    "network": net,
                    "security": sec,
                }
                if sec == "reality":
                    stream_settings["realitySettings"] = {
                        "serverName": s_data.get("sni", s_data.get("address", "")),
                        "publicKey": s_data.get("public_key") or s_data.get("pbk", ""),
                        "shortId": s_data.get("short_id") or s_data.get("sid", ""),
                        "fingerprint": s_data.get("fingerprint", "chrome")
                    }
                elif sec == "tls":
                    stream_settings["tlsSettings"] = {
                        "serverName": s_data.get("sni", s_data.get("address", "")),
                        "allowInsecure": False
                    }
                if net == "ws":
                    stream_settings["wsSettings"] = {
                        "path": s_data.get("ws_path", "/"),
                        "headers": {"Host": s_data.get("ws_host", s_data.get("sni", ""))}
                    }

                cfg = {
                    "log": {"loglevel": "warning"},
                    "outbounds": [
                        {
                            "tag": "proxy",
                            "protocol": "vless",
                            "settings": {
                                "vnext": [
                                    {
                                        "address": s_data.get("address", ""),
                                        "port": int(s_data.get("port", 443)),
                                        "users": [
                                            {
                                                "id": s_data.get("uuid", ""),
                                                "encryption": "none",
                                                "flow": s_data.get("flow", "xtls-rprx-vision")
                                            }
                                        ]
                                    }
                                ]
                            },
                            "streamSettings": stream_settings
                        },
                        {"tag": "direct", "protocol": "freedom"}
                    ]
                }

        # Configure inbounds: Kernel-level TUN interface (for ALL apps/system traffic) + SOCKS + HTTP
        inbounds = [
            {
                "protocol": "tun",
                "tag": "tun-in",
                "settings": {
                    "name": "tun_wavez",
                    "gateway": ["198.18.0.1/16"],
                    "dns": ["1.1.1.1", "8.8.8.8"],
                    "mtu": 1400,
                    "autoOutboundsInterface": "auto",
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"],
                }
            },
            {
                "tag": "socks",
                "port": SOCKS_PORT,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
            },
            {
                "tag": "http",
                "port": HTTP_PORT,
                "listen": "127.0.0.1",
                "protocol": "http",
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
            }
        ]
        cfg["inbounds"] = inbounds

        # High-stability policy for Google AI / Antigravity streaming & long-lived connections
        cfg["policy"] = {
            "levels": {
                "0": {
                    "handshake": 10,
                    "connIdle": 900,
                    "uplinkOnly": 15,
                    "downlinkOnly": 30,
                    "statsUserUplink": True,
                    "statsUserDownlink": True,
                    "bufferSize": 262144
                }
            },
            "system": {
                "statsOutboundUplink": True,
                "statsOutboundDownlink": True
            }
        }

        # DNS configuration: DoH + Google DNS with strict IPv4 and AI IDE priority routing
        cfg["dns"] = {
            "servers": [
                {
                    "address": "https://1.1.1.1/dns-query",
                    "domains": [
                        "domain:openai.com", "domain:chatgpt.com", "domain:oaistatic.com", "domain:oaiusercontent.com",
                        "domain:anthropic.com", "domain:claude.ai",
                        "domain:googleapis.com", "domain:google.com", "domain:gstatic.com", "domain:googlevideo.com",
                        "domain:github.com", "domain:githubusercontent.com",
                        "domain:opencode.ai", "domain:huggingface.co", "domain:openrouter.ai"
                    ]
                },
                "https://8.8.8.8/dns-query",
                "8.8.8.8",
                "1.1.1.1"
            ],
            "queryStrategy": "UseIPv4"
        }

        # Clean routing rules with YouTube & Google Video 4K Acceleration
        cfg["routing"] = {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "ip": [
                        "10.0.0.0/8", "100.64.0.0/10", "172.16.0.0/12", "192.168.0.0/16",
                        "169.254.0.0/16", "224.0.0.0/4", "255.255.255.255", "::1/128",
                        "fc00::/7", "fe80::/10", "ff00::/8", "127.0.0.0/8"
                    ],
                    "outboundTag": "direct"
                },
                # Block UDP:443 (QUIC) so YouTube immediately uses lightning-fast TCP HTTP/2 without buffering
                {
                    "type": "field",
                    "port": "443",
                    "network": "udp",
                    "outboundTag": "block"
                },
                # Prioritize YouTube & Google Video domains to proxy
                {
                    "type": "field",
                    "domain": [
                        "domain:youtube.com", "domain:googlevideo.com", "domain:ytimg.com",
                        "domain:ggpht.com", "domain:gvt1.com", "domain:youtube-nocookie.com",
                        "domain:youtu.be", "domain:yt.be", "domain:googleusercontent.com"
                    ],
                    "outboundTag": "proxy"
                },
                {
                    "type": "field",
                    "network": "tcp,udp",
                    "outboundTag": "proxy"
                }
            ]
        }

        # Mark outbound packets & configure TCP Keep-Alive for continuous Antigravity streams
        for ob in cfg.get("outbounds", []):
            if ob.get("tag") == "proxy" or ob.get("protocol") in ("vless", "vmess", "shadowsocks", "trojan", "hysteria2", "freedom"):
                stream = ob.setdefault("streamSettings", {})
                sockopt = stream.setdefault("sockopt", {})
                sockopt["mark"] = 51820
                sockopt["tcpKeepAliveInterval"] = 15
                sockopt["tcpKeepAliveIdle"] = 30
                sockopt["tcpUserTimeout"] = 30000
                sockopt["tcpNoDelay"] = True

        # Write config to run directory
        config_path = RUN_DIR / "xray_active.json"
        try:
            config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except OSError as exc:
            return False, f"Failed to write Xray runtime config: {exc}"

        logger.info("Starting Xray backend for server: %s (%s:%s)", profile_name, s_data.get("address"), s_data.get("port"))

        # Asset directory for geoip.dat / geosite.dat
        env = dict(os.environ)
        asset_candidates = [
            "/usr/local/share/wavez-vpn",
            "/usr/local/share/xray",
            "/opt/incy/lib/app/resources/bin",
            str(Path(__file__).resolve().parent / "bin"),
        ]
        for ac in asset_candidates:
            if Path(ac).is_dir():
                env["XRAY_LOCATION_ASSET"] = ac
                break

        try:
            self._proc = subprocess.Popen(
                [str(self._xray_bin), "run", "-c", str(config_path)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            logger.error("Failed to start Xray process: %s", exc)
            return False, f"Failed to start Xray: {exc}"

        # Wait for Xray to bind ports (20808 / 20809)
        started = False
        for _ in range(30):  # up to 3 seconds
            time.sleep(0.1)
            if self._proc.poll() is not None:
                _, err = self._proc.communicate()
                return False, f"Xray process failed: {err.strip() if err else 'exited unexpectedly'}"
            if self._check_port(SOCKS_PORT) or self._check_port(HTTP_PORT):
                started = True
                break

        if not started:
            self.disconnect()
            return False, f"Xray did not open proxy inbound ports ({SOCKS_PORT}/{HTTP_PORT})"

        # Enable system proxy in GNOME / Ubuntu Desktop & environment
        self._enable_system_proxy()

        # Enable kernel-level default routing & DNS for tun_wavez
        self._enable_kernel_routing()

        self._connected = True
        self._active_profile = profile_name
        self._active_server_data = s_data
        self._start_time = time.time()
        logger.info("Successfully connected to '%s' via Xray Reality", profile_name)
        return True, f"Connected to {profile_name}"

    def disconnect(self) -> tuple[bool, str]:
        """Stop Xray process, reset system proxy, and ensure ports are fully freed."""
        logger.info("Disconnecting Xray backend...")

        # 1. Reset kernel routing & system proxy
        self._disable_kernel_routing()
        self._disable_system_proxy()

        # 2. Terminate managed process
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
            self._proc = None

        # 3. Kill any stray xray-core processes to avoid port bind conflicts
        try:
            subprocess.run(["killall", "-9", "xray-core"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        # 4. Wait for ports to be completely released
        for _ in range(15):
            if not self._check_port(SOCKS_PORT) and not self._check_port(HTTP_PORT):
                break
            time.sleep(0.05)

        self._connected = False
        self._active_profile = None
        self._active_server_data = None
        self._start_time = None
        logger.info("Xray backend disconnected and ports freed")
        return True, "Disconnected"

    @classmethod
    def _enable_kernel_routing(cls) -> None:
        """Call privileged helper to route all system traffic into tun_wavez."""
        helper_path = "/usr/local/lib/wavez-vpn/vpn-helper"
        if os.path.isfile(helper_path):
            try:
                subprocess.run(
                    ["pkexec", helper_path, "setup-xray-routes", "tun_wavez", "51820", "51820"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                logger.debug("Configured kernel default routing for tun_wavez")
            except Exception as exc:
                logger.warning("Could not setup kernel routes: %s", exc)

    @classmethod
    def _disable_kernel_routing(cls) -> None:
        """Tear down kernel default routing and restore DNS."""
        helper_path = "/usr/local/lib/wavez-vpn/vpn-helper"
        if os.path.isfile(helper_path):
            try:
                subprocess.run(
                    ["pkexec", helper_path, "cleanup-xray-routes", "tun_wavez", "51820", "51820"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                logger.debug("Restored kernel routing")
            except Exception as exc:
                logger.warning("Could not cleanup kernel routes: %s", exc)

    @classmethod
    def _enable_tun_mode(cls) -> None:
        """Start hev-socks5-tunnel and kernel routing so 100% of all apps/browsers use the VPN."""
        helper_path = "/usr/local/lib/wavez-vpn/vpn-helper"
        if os.path.isfile(helper_path):
            try:
                subprocess.run(
                    ["pkexec", helper_path, "start-tun", str(SOCKS_PORT), "tun_wavez", "51820", "51820"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                logger.debug("Activated TUN kernel routing for tun_wavez")
            except Exception as exc:
                logger.warning("Could not activate TUN mode: %s", exc)

    @classmethod
    def _disable_tun_mode(cls) -> None:
        """Tear down hev-socks5-tunnel and kernel routing."""
        helper_path = "/usr/local/lib/wavez-vpn/vpn-helper"
        if os.path.isfile(helper_path):
            try:
                subprocess.run(
                    ["pkexec", helper_path, "stop-tun", "tun_wavez", "51820", "51820"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                logger.debug("Deactivated TUN kernel routing")
            except Exception as exc:
                logger.warning("Could not deactivate TUN mode: %s", exc)

    @classmethod
    def _check_port(cls, port: int, host: str = "127.0.0.1") -> bool:
        """Check if a local TCP port is open and accepting connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                return s.connect_ex((host, port)) == 0
        except OSError:
            return False

    @classmethod
    def _enable_system_proxy(cls) -> None:
        """Set GNOME system proxy and environment to route desktop apps through local Xray."""
        try:
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "mode", "manual"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.http", "enabled", "true"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.http", "host", "127.0.0.1"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.http", "port", str(HTTP_PORT)], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.https", "host", "127.0.0.1"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.https", "port", str(HTTP_PORT)], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.socks", "host", "127.0.0.1"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.socks", "port", str(SOCKS_PORT)], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "use-same-proxy", "true"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "ignore-hosts", "['localhost', '127.0.0.0/8', '::1']"], check=False)
            logger.debug("GNOME system proxy set to manual (127.0.0.1:%d/%d)", SOCKS_PORT, HTTP_PORT)
        except Exception as exc:
            logger.warning("Could not set GNOME system proxy: %s", exc)

        # Set environment variables for child processes & tools
        os.environ["http_proxy"] = f"http://127.0.0.1:{HTTP_PORT}"
        os.environ["https_proxy"] = f"http://127.0.0.1:{HTTP_PORT}"
        os.environ["all_proxy"] = f"socks5h://127.0.0.1:{SOCKS_PORT}"
        os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{HTTP_PORT}"
        os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{HTTP_PORT}"
        os.environ["ALL_PROXY"] = f"socks5h://127.0.0.1:{SOCKS_PORT}"

    @classmethod
    def _disable_system_proxy(cls) -> None:
        """Reset GNOME system proxy back to direct connection."""
        try:
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "mode", "none"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy.http", "enabled", "false"], check=False)
            logger.debug("GNOME system proxy reset to none")
        except Exception as exc:
            logger.warning("Could not reset GNOME system proxy: %s", exc)

        for var in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            os.environ.pop(var, None)

    def get_status(self) -> dict[str, Any]:
        """Return status dict compatible with VPNManager status."""
        if not self.is_connected():
            return {"connected": False}

        rx_bytes = 0
        tx_bytes = 0
        for iface in ("tun_wavez", "tun0", "tun_xray"):
            rx_p = Path(f"/sys/class/net/{iface}/statistics/rx_bytes")
            tx_p = Path(f"/sys/class/net/{iface}/statistics/tx_bytes")
            if rx_p.is_file() and tx_p.is_file():
                try:
                    rx_bytes = int(rx_p.read_text().strip())
                    tx_bytes = int(tx_p.read_text().strip())
                    break
                except Exception:
                    pass

        return {
            "connected": True,
            "profile": self._active_profile,
            "engine": "xray",
            "protocol": self._active_server_data.get("protocol", "VLESS") if self._active_server_data else "VLESS",
            "endpoint": f"{self._active_server_data.get('address', '')}:{self._active_server_data.get('port', '')}" if self._active_server_data else "",
            "uptime": int(time.time() - self._start_time) if self._start_time else 0,
            "transfer_rx": rx_bytes,
            "transfer_tx": tx_bytes,
        }
