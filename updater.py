"""Auto-updater for SPIZDILI_VPN — checks GitHub Releases and installs .deb."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
import urllib.request
from typing import Callable, Optional

from version import APP_VERSION, GITHUB_API_URL, GITHUB_REPO

logger = logging.getLogger("updater")


def _parse_version(v: str) -> tuple[int, ...]:
    v = v.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def check_for_update() -> Optional[dict]:
    """Return release dict if a newer version exists on GitHub, else None."""
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"User-Agent": f"SPIZDILI_VPN/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode())
        remote_tag = data.get("tag_name", "")
        if _parse_version(remote_tag) > _parse_version(APP_VERSION):
            # Find .deb asset
            deb_asset = None
            for asset in data.get("assets", []):
                if asset["name"].endswith(".deb"):
                    deb_asset = asset
                    break
            return {
                "tag": remote_tag,
                "body": data.get("body", ""),
                "deb_url": deb_asset["browser_download_url"] if deb_asset else None,
                "deb_name": deb_asset["name"] if deb_asset else None,
            }
    except Exception as e:
        logger.warning("Update check failed: %s", e)
    return None


def download_and_install(
    deb_url: str,
    deb_name: str,
    progress_cb: Optional[Callable[[float], None]] = None,
    done_cb: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """Download .deb and install it via pkexec dpkg -i (runs in background thread)."""

    def _run():
        try:
            tmp_path = os.path.join(tempfile.gettempdir(), deb_name)
            req = urllib.request.Request(
                deb_url, headers={"User-Agent": f"SPIZDILI_VPN/{APP_VERSION}"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 65536
                with open(tmp_path, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if progress_cb and total:
                            progress_cb(downloaded / total)

            result = subprocess.run(
                ["pkexec", "dpkg", "-i", tmp_path],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                if done_cb:
                    done_cb(True, "")
            else:
                if done_cb:
                    done_cb(False, result.stderr or result.stdout)
        except Exception as exc:
            if done_cb:
                done_cb(False, str(exc))

    threading.Thread(target=_run, daemon=True).start()
