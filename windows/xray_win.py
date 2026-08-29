"""
Windows Xray VLESS Reality Engine Controller
Supports: Windows 7, Windows 8, Windows 10, Windows 11
Handles embedded xray.exe lifecycle, dynamic port allocation, and config generation.
"""

import sys
import os
import json
import time
import socket
import subprocess
import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("xray_win")


def find_free_port(preferred: int) -> int:
    """Find the next available TCP port on 127.0.0.1."""
    for port in range(preferred, preferred + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


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
        self.current_http_port: int = 20809
        self.current_socks_port: int = 20808

    def find_xray_binary(self) -> Optional[Path]:
        """Locate bundled or system xray.exe."""
        candidates = [
            self.base_dir / "bin" / "xray.exe",
            self.base_dir / "xray.exe",
            Path(sys.executable).parent / "xray.exe",
            Path(sys.executable).parent / "bin" / "xray.exe",
            Path(os.environ.get("ProgramFiles", "C:\Program Files")) / "Xray" / "xray.exe",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def generate_config(self, server: dict[str, Any]) -> dict[str, Any]:
        """Generate high-stability Xray config for Windows with dynamic ports."""
        full_json = server.get("full_config_json")
        cfg = {}
        if full_json:
            try:
                cfg = json.loads(full_json)
            except Exception:
                pass

        if not cfg:
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
                            "fingerprint": server.get("fingerprint", "chrome")
                        }
                    }
                }, {"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
            }

        # Allocate guaranteed free ports
        self.current_socks_port = find_free_port(20810)
        self.current_http_port = find_free_port(self.current_socks_port + 1)

        cfg["inbounds"] = [
            {
                "tag": "socks",
                "port": self.current_socks_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
            },
            {
                "tag": "http",
                "port": self.current_http_port,
                "listen": "127.0.0.1",
                "protocol": "http",
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
            }
        ]

        # Policy
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
            }
        }

        return cfg

    def start(self, server: dict[str, Any]) -> tuple[bool, str]:
        """Start Xray for the selected server."""
        self.stop()

        xray_bin = self.find_xray_binary()
        if not xray_bin:
            return False, "xray.exe binary not found in application directory."

        cfg = self.generate_config(server)
        try:
            self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception as exc:
            return False, f"Failed to write Windows Xray config: {exc}"

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = 0x08000000  # CREATE_NO_WINDOW

        # Set cwd to bin directory so geoip.dat / geosite.dat are loaded
        work_dir = xray_bin.parent

        try:
            self._proc = subprocess.Popen(
                [str(xray_bin), "run", "-c", str(self.config_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(work_dir),
                creationflags=creation_flags
            )
            self._active_profile = server.get("name", "Unknown Server")
            self._active_server = server
            self._start_time = time.time()
            time.sleep(0.7)

            if self._proc.poll() is not None:
                err_out = ""
                try:
                    _, err = self._proc.communicate(timeout=1)
                    err_out = err.strip()
                except Exception:
                    pass
                return False, f"xray.exe stopped: {err_out or 'check config'}"

            logger.info("Xray engine started successfully on Windows (PID %d, HTTP %d, SOCKS %d)",
                        self._proc.pid, self.current_http_port, self.current_socks_port)
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
            try:
                subprocess.run(["taskkill", "/F", "/IM", "xray.exe"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except Exception:
                pass

        self._active_profile = None
        self._active_server = None
        self._start_time = None
        return True

    def is_connected(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
