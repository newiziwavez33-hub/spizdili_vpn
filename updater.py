"""
SPIZDILI_VPN — Cross-Platform GitHub Auto-Updater.

Handles checking the GitHub Releases API, parsing semantic versions,
downloading platform-specific release assets (.deb for Linux, .exe/.zip for Windows),
and automated silent/elevated package installation and application relaunch.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from version import (
        __version__ as CURRENT_VERSION,
        APP_NAME,
        GITHUB_OWNER,
        GITHUB_REPO,
        GITHUB_REPO_URL,
        GITHUB_RELEASES_API,
    )
except ImportError:
    try:
        from .version import (
            __version__ as CURRENT_VERSION,
            APP_NAME,
            GITHUB_OWNER,
            GITHUB_REPO,
            GITHUB_REPO_URL,
            GITHUB_RELEASES_API,
        )
    except Exception:
        CURRENT_VERSION = "1.0.6.1"
        APP_NAME = "SPIZDILI_VPN"
        GITHUB_OWNER = "newiziwavez33-hub"
        GITHUB_REPO = "spizdili_vpn"
        GITHUB_REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
        GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

logger = logging.getLogger("updater")


def parse_semver(v: str) -> tuple[int, ...]:
    """Parse a version string like 'v1.0.3' or '1.0.4.1' into a tuple of ints."""
    clean = re.sub(r"^[^\d]*", "", v.strip())
    parts = re.split(r"[.\-_]", clean)
    nums = []
    for p in parts:
        digits = re.findall(r"^\d+", p)
        if digits:
            nums.append(int(digits[0]))
        else:
            break
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def is_newer_version(latest_str: str, current_str: str = CURRENT_VERSION) -> bool:
    """Return True if latest_str is strictly newer than current_str."""
    try:
        return parse_semver(latest_str) > parse_semver(current_str)
    except Exception:
        return False


@dataclass
class UpdateInfo:
    """Detailed metadata for an available release."""
    current_version: str
    latest_version: str
    has_update: bool
    title: str = ""
    release_notes: str = ""
    release_url: str = ""
    published_at: str = ""
    deb_asset_url: Optional[str] = None
    deb_asset_name: Optional[str] = None
    deb_asset_size: int = 0
    exe_asset_url: Optional[str] = None
    exe_asset_name: Optional[str] = None
    exe_asset_size: int = 0
    zip_asset_url: Optional[str] = None
    zip_asset_name: Optional[str] = None
    zip_asset_size: int = 0
    all_assets: list[dict[str, Any]] = field(default_factory=list)


class AppUpdater:
    """Cross-platform updater client communicating with GitHub Releases API."""

    def __init__(
        self,
        current_version: str = CURRENT_VERSION,
        api_url: str = GITHUB_RELEASES_API,
        repo_url: str = GITHUB_REPO_URL,
    ) -> None:
        self.current_version = current_version
        self.api_url = api_url
        self.repo_url = repo_url

    def check_for_updates(self, timeout: float = 8.0) -> Optional[UpdateInfo]:
        """Fetch latest release metadata from GitHub API and check for updates."""
        headers = {
            "User-Agent": f"SPIZDILI-VPN-Updater/{self.current_version} ({platform.system()}; {platform.machine()})",
            "Accept": "application/vnd.github.v3+json",
        }
        req = urllib.request.Request(self.api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning("GitHub API returned HTTP %s", resp.status)
                    return None
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.info("No releases found on repository.")
            else:
                logger.warning("GitHub API HTTPError %s: %s", exc.code, exc.reason)
            return None
        except Exception as exc:
            logger.warning("Failed to check for updates: %s", exc)
            return None

        tag_name = str(data.get("tag_name") or "").strip()
        latest_clean = tag_name.lstrip("v")
        has_update = is_newer_version(latest_clean, self.current_version)

        info = UpdateInfo(
            current_version=self.current_version,
            latest_version=latest_clean or tag_name,
            has_update=has_update,
            title=str(data.get("name") or f"Release {tag_name}"),
            release_notes=str(data.get("body") or "").strip(),
            release_url=str(data.get("html_url") or f"{self.repo_url}/releases/latest"),
            published_at=str(data.get("published_at") or ""),
            all_assets=data.get("assets", []) or [],
        )

        for asset in info.all_assets:
            name = asset.get("name", "")
            download_url = asset.get("browser_download_url", "")
            size = asset.get("size", 0)

            name_lower = name.lower()
            if name_lower.endswith(".deb"):
                info.deb_asset_url = download_url
                info.deb_asset_name = name
                info.deb_asset_size = size
            elif name_lower.endswith(".exe"):
                info.exe_asset_url = download_url
                info.exe_asset_name = name
                info.exe_asset_size = size
            elif name_lower.endswith(".zip") and ("win" in name_lower or "x64" in name_lower or "spizdili" in name_lower):
                info.zip_asset_url = download_url
                info.zip_asset_name = name
                info.zip_asset_size = size

        logger.info(
            "Update check result: current=%s, latest=%s, has_update=%s",
            self.current_version,
            info.latest_version,
            info.has_update,
        )
        return info

    @staticmethod
    def download_file(
        url: str,
        dest_path: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        chunk_size: int = 64 * 1024,
    ) -> bool:
        """Download remote URL to dest_path with progress callback (downloaded_bytes, total_bytes)."""
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "SPIZDILI-VPN-Updater"},
            )
            with urllib.request.urlopen(req) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                temp_file = dest_path.with_suffix(dest_path.suffix + ".part")
                with open(temp_file, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total_size)
                if dest_path.is_file():
                    dest_path.unlink()
                temp_file.rename(dest_path)
            return True
        except Exception as exc:
            logger.error("Download failed from %s: %s", url, exc)
            return False

    @staticmethod
    def install_linux_deb(deb_path: Path) -> tuple[bool, str]:
        """Install downloaded .deb file via pkexec (PolicyKit elevation)."""
        if not deb_path.is_file():
            return False, f"Файл пакета не найден: {deb_path}"

        logger.info("Installing Debian package: %s", deb_path)

        cmd_apt = ["pkexec", "apt-get", "install", "-y", "--reinstall", str(deb_path.resolve())]
        try:
            proc = subprocess.run(
                cmd_apt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
            )
            if proc.returncode == 0:
                logger.info("APT package installation succeeded.")
                return True, "Пакет успешно установлен через APT."
            logger.warning("APT install returned code %d: %s", proc.returncode, proc.stderr)
        except Exception as exc:
            logger.warning("Error running apt install: %s", exc)

        cmd_dpkg = ["pkexec", "dpkg", "-i", str(deb_path.resolve())]
        try:
            proc = subprocess.run(
                cmd_dpkg,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0:
                logger.info("dpkg installation succeeded.")
                return True, "Пакет успешно установлен через dpkg."
            return False, f"Ошибка установки dpkg: {proc.stderr.strip() or proc.stdout.strip()}"
        except Exception as exc:
            return False, f"Сбой запуска установщика: {exc}"

    @staticmethod
    def apply_windows_update(new_file_path: Path) -> tuple[bool, str]:
        """Apply Windows standalone executable or zip update."""
        if not new_file_path.is_file():
            return False, f"Файл обновления не найден: {new_file_path}"

        target_exe = Path(sys.executable)
        if getattr(sys, "frozen", False):
            target_path = target_exe.resolve()
        else:
            target_path = Path(__file__).resolve().parent / "dist" / "SPIZDILI_VPN.exe"

        bat_script = Path(tempfile.gettempdir()) / "spizdili_updater.bat"
        
        bat_content = f"""@echo off
title SPIZDILI VPN Updater
echo Waiting for SPIZDILI VPN to close...
timeout /t 2 /nobreak > nul
taskkill /f /im SPIZDILI_VPN.exe > nul 2>&1
timeout /t 1 /nobreak > nul

echo Applying update...
copy /y "{new_file_path.resolve()}" "{target_path}"
if %errorlevel% neq 0 (
    echo Update failed!
    pause
    exit /b 1
)

echo Starting updated application...
start "" "{target_path}"
del "{bat_script}" > nul 2>&1
exit
"""
        try:
            bat_script.write_text(bat_content, encoding="cp866", errors="ignore")
            subprocess.Popen(
                ["cmd.exe", "/c", str(bat_script)],
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200),
                close_fds=True,
            )
            return True, "Обновление готово к установке. Перезапуск приложения..."
        except Exception as exc:
            return False, f"Ошибка запуска установщика Windows: {exc}"

    @staticmethod
    def update_from_git() -> tuple[bool, str]:
        """Update working directory from git remote origin if running from source clone."""
        git_dir = Path(__file__).resolve().parent / ".git"
        if not git_dir.is_dir():
            return False, "Текущая копия не является git-репозиторием."

        try:
            proc = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(git_dir.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                return True, f"Репозиторий успешно обновлен: {proc.stdout.strip()}"
            return False, f"Ошибка git pull: {proc.stderr.strip()}"
        except Exception as exc:
            return False, f"Сбой git: {exc}"


# Global default instance
default_updater = AppUpdater()

# ---------------------------------------------------------------------------
# Backward Compatibility Wrappers for Linux app_ui
# ---------------------------------------------------------------------------

def check_for_update() -> Optional[dict]:
    """Compatibility helper for app_ui."""
    info = default_updater.check_for_updates()
    if info and info.has_update:
        return {
            "tag": info.latest_version,
            "body": info.release_notes,
            "deb_url": info.deb_asset_url,
            "deb_name": info.deb_asset_name,
        }
    return None


def download_and_install(
    deb_url: str,
    deb_name: str,
    progress_cb: Optional[Callable[[float], None]] = None,
    done_cb: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """Compatibility helper for app_ui."""
    def _run():
        try:
            tmp_path = Path(tempfile.gettempdir()) / deb_name
            def _wrap_prog(down: int, tot: int):
                if progress_cb and tot > 0:
                    progress_cb(down / tot)
            ok = default_updater.download_file(deb_url, tmp_path, progress_cb=_wrap_prog)
            if not ok:
                if done_cb:
                    done_cb(False, "Ошибка скачивания файла обновления")
                return
            ok_inst, msg = default_updater.install_linux_deb(tmp_path)
            if done_cb:
                done_cb(ok_inst, msg)
        except Exception as exc:
            if done_cb:
                done_cb(False, str(exc))

    import threading
    threading.Thread(target=_run, daemon=True).start()
