"""
Windows System Proxy & Networking Configuration Manager
Supports: Windows 7, Windows 8, Windows 10, Windows 11
Uses native WinINet API & Registry to enable/disable system-wide proxy instantly without reboot.
"""

import sys
import ctypes
if sys.platform == "win32":
    import winreg
else:
    winreg = None
import subprocess
import logging

logger = logging.getLogger("win_proxy")

# WinINet Constants
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37


class WindowsProxyManager:
    """Manages Windows System Internet Proxy settings."""

    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

    @classmethod
    def enable_proxy(cls, host: str = "127.0.0.1", http_port: int = 20809, socks_port: int = 20808) -> bool:
        """Enable Windows system-wide HTTP/HTTPS and SOCKS proxy."""
        if sys.platform != "win32":
            logger.info("Non-windows platform, skipping WinINet proxy configuration")
            return True

        proxy_server = f"http={host}:{http_port};https={host}:{http_port};socks={host}:{socks_port}"
        override = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;<local>"

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, override)
                try:
                    winreg.DeleteValue(key, "AutoConfigURL")
                except FileNotFoundError:
                    pass

            cls._refresh_wininet()
            logger.info("Windows system proxy enabled -> %s", proxy_server)
            return True
        except Exception as exc:
            logger.error("Failed to enable Windows system proxy: %s", exc)
            return False

    @classmethod
    def disable_proxy(cls) -> bool:
        """Disable Windows system-wide proxy and restore direct connection."""
        if sys.platform != "win32":
            return True

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)

            cls._refresh_wininet()
            logger.info("Windows system proxy disabled (Direct connection restored)")
            return True
        except Exception as exc:
            logger.error("Failed to disable Windows system proxy: %s", exc)
            return False

    @classmethod
    def _refresh_wininet(cls) -> None:
        """Notify Windows system that internet settings have changed."""
        try:
            wininet = ctypes.windll.wininet
            wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception as exc:
            logger.debug("WinINet refresh notice: %s", exc)
