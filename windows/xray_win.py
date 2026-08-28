"""
Windows Xray VLESS Reality Engine Controller
Supports: Windows 7, Windows 8, Windows 10, Windows 11
Handles embedded xray.exe lifecycle, config generation, and traffic stats.
"""

import sys
import os
import json
import time
import subprocess
import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("xray_win")

HTTP_PORT = 20809
SOCKS_PORT = 20808


class WindowsXrayManager:
    """Manages the Xray core subprocess on Windows."""

    def __init__(self, app_dir: Optional[Path] = None) -> None:
        if getattr(sys, "frozen", False):
            self.base_dir = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
        else:
            self.base_dir = app_dir or Path(__file__).resolve().parent.parent

        self.user_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "SPIZDILI_VPN"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.user_dir / "xray_active.json"

        self._proc: Optional[subprocess.Popen] = None
        self._active_profile: Optional[str] = None
        self._start_time: Optional[float] = None
        self._active_server: Optional[dict[str, Any]] = None

    def find_xray_binary(self) -> Optional[Path]:
        """Locate bundled or system xray.exe."""
        candidates = [
            self.base_dir / "bin" / "xray.exe",
            self.base_dir / "xray.exe",
            Path(sys.executable).parent / "xray.exe",
            Path(sys.executable).parent / "bin" / "xray.exe",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Xray" / "xray.exe",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def generate_config(self, server: dict[str, Any]) -> dict[str, Any]:
        """Generate high-stability Xray config for Windows with AI IDE streaming optimizations."""
        full_json = server.get("full_config_json")
        cfg = {}
        if full_json:
            try:
                cfg = json.loads(full_json)
            except Exception:
                pass

        if not cfg:
            # Fallback direct VLESS template
            cfg = {
                "log": {"loglevel": "warning"},
                "outbounds": [{
                    "protocol": "vless",
                    "tag": "proxy",
                    "settings": {
                        "vnext": [{
                            "address": server.get("address", ""),
                            "port": server.get("port", 443),
                            "users": [{
                                "id": server.get("uuid", ""),
                                "encryption": "none",
                                "flow": server.get("flow", "xtls-rprx-vision")
                            }]
                        }]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "serverName": server.get("sni", "storage.yandex.net"),
                            "publicKey": server.get("public_key", ""),
                            "shortId": server.get("short_id", ""),
                            "fingerprint": server.get("fingerprint", "firefox")
                        }
                    }
                }, {"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
            }

        # Windows local Inbounds
        cfg["inbounds"] = [
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

        # AI IDE streaming policy (Google Antigravity, OpenAI, Claude, OpenCode)
        cfg["policy"] = {
            "levels": {
                "0": {
                    "handshake": 10,
                    "connIdle": 900,
                    "uplinkOnly": 15,
                    "downlinkOnly": 30,
                    "statsUserUplink": True,
                    "statsUserDownlink": True,
                    "bufferSize": 65536
                }
            },
            "system": {
                "statsOutboundUplink": True,
                "statsOutboundDownlink": True
            }
        }

        # Prioritized DNS for AI endpoints
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

        # Enable TCP keep-alive on outbounds
        for ob in cfg.get("outbounds", []):
            if ob.get("tag") == "proxy" or ob.get("protocol") in ("vless", "vmess", "shadowsocks", "trojan"):
                stream = ob.setdefault("streamSettings", {})
                sockopt = stream.setdefault("sockopt", {})
                sockopt["tcpKeepAliveInterval"] = 15
                sockopt["tcpKeepAliveIdle"] = 30
                sockopt["tcpUserTimeout"] = 30000
                sockopt["tcpNoDelay"] = True

        return cfg

    def start(self, server: dict[str, Any]) -> tuple[bool, str]:
        """Start Xray for the selected server."""
        self.stop()

        xray_bin = self.find_xray_binary()
        if not xray_bin:
            return False, "xray.exe binary not found. Please ensure it is present in the application folder."

        cfg = self.generate_config(server)
        try:
            self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to write Windows Xray config: {exc}"

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = 0x08000000  # CREATE_NO_WINDOW

        try:
            self._proc = subprocess.Popen(
                [str(xray_bin), "run", "-c", str(self.config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            self._active_profile = server.get("name", "Unknown Server")
            self._active_server = server
            self._start_time = time.time()
            time.sleep(0.5)

            if self._proc.poll() is not None:
                return False, "xray.exe exited immediately on launch."

            logger.info("Xray engine started successfully on Windows (PID %d)", self._proc.pid)
            return True, "Connected"
        except Exception as exc:
            return False, f"Failed to start xray.exe: {exc}"

    def stop(self) -> bool:
        """Stop running Xray engine."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "xray.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        self._active_profile = None
        self._active_server = None
        self._start_time = None
        return True

    def is_connected(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
