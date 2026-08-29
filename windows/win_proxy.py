"""
Windows System Proxy & Networking Configuration Manager
Supports: Windows 7, Windows 8, Windows 10, Windows 11
Uses native WinINet API & Registry to enable/disable system-wide proxy instantly without reboot.
"""

import sys
import ctypes
import logging
from typing import Optional

logger = logging.getLogger("win_proxy")

# WinINet Constants
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
CONN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings\Connections"


class WindowsProxyManager:
    """Manages Windows System Internet Proxy settings for all browsers and apps."""

    @classmethod
    def enable_proxy(cls, host: str = "127.0.0.1", http_port: int = 20809, socks_port: Optional[int] = None) -> bool:
        """Enable Windows system-wide HTTP/HTTPS proxy via WinINet and Registry."""
        if sys.platform != "win32":
            logger.info("Non-windows platform, skipping WinINet proxy configuration")
            return True

        import winreg

        # Universal Windows proxy server string: host:port routes all HTTP and HTTPS traffic
        proxy_server = f"{host}:{http_port}"
        override = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;<local>"

        try:
            # 1. Update Internet Settings key
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, override)
                try:
                    winreg.DeleteValue(key, "AutoConfigURL")
                except FileNotFoundError:
                    pass

            # 2. Update DefaultConnectionSettings binary blob for Windows 10/11
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CONN_PATH, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                    try:
                        blob, reg_type = winreg.QueryValueEx(key, "DefaultConnectionSettings")
                        blob_bytes = bytearray(blob)
                        if len(blob_bytes) > 8:
                            blob_bytes[8] = 0x03  # 0x03 = proxy enabled
                            winreg.SetValueEx(key, "DefaultConnectionSettings", 0, reg_type, bytes(blob_bytes))
                    except FileNotFoundError:
                        pass
                    try:
                        blob_saved, reg_type = winreg.QueryValueEx(key, "SavedLegacySettings")
                        blob_saved_bytes = bytearray(blob_saved)
                        if len(blob_saved_bytes) > 8:
                            blob_saved_bytes[8] = 0x03
                            winreg.SetValueEx(key, "SavedLegacySettings", 0, reg_type, bytes(blob_saved_bytes))
                    except FileNotFoundError:
                        pass
            except Exception as e:
                logger.debug("Could not modify connection blob: %s", e)

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

        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)

            # Update DefaultConnectionSettings binary blob
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CONN_PATH, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                    try:
                        blob, reg_type = winreg.QueryValueEx(key, "DefaultConnectionSettings")
                        blob_bytes = bytearray(blob)
                        if len(blob_bytes) > 8:
                            blob_bytes[8] = 0x01  # 0x01 = direct connection
                            winreg.SetValueEx(key, "DefaultConnectionSettings", 0, reg_type, bytes(blob_bytes))
                    except FileNotFoundError:
                        pass
                    try:
                        blob_saved, reg_type = winreg.QueryValueEx(key, "SavedLegacySettings")
                        blob_saved_bytes = bytearray(blob_saved)
                        if len(blob_saved_bytes) > 8:
                            blob_saved_bytes[8] = 0x01
                            winreg.SetValueEx(key, "SavedLegacySettings", 0, reg_type, bytes(blob_saved_bytes))
                    except FileNotFoundError:
                        pass
            except Exception as e:
                logger.debug("Could not restore connection blob: %s", e)

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
