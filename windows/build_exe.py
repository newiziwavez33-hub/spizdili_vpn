"""
Automated PyInstaller Standalone Windows Executable Builder
Produces: dist/SPIZDILI_VPN.exe
"""
import os
import sys
import shutil
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = BASE_DIR / "bin"
BIN_DIR.mkdir(exist_ok=True)

XRAY_WIN_URL = "https://github.com/XTLS/Xray-core/releases/download/v1.8.24/Xray-windows-64.zip"


def download_xray_windows() -> None:
    xray_exe = BIN_DIR / "xray.exe"
    if xray_exe.is_file():
        print(f"✓ Found existing Windows xray.exe at {xray_exe}")
        return

    print("→ Downloading official Xray Windows amd64 core...")
    zip_path = BIN_DIR / "xray_win.zip"
    try:
        urllib.request.urlretrieve(XRAY_WIN_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extract("xray.exe", BIN_DIR)
            try:
                z.extract("geoip.dat", BIN_DIR)
                z.extract("geosite.dat", BIN_DIR)
            except Exception:
                pass
        zip_path.unlink(missing_ok=True)
        print("✓ Successfully extracted xray.exe for Windows")
    except Exception as e:
        print(f"⚠ Could not auto-download Xray: {e}")


def build() -> None:
    download_xray_windows()

    print("→ Building standalone SPIZDILI_VPN.exe with PyInstaller...")
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",  # fast startup, clean packaging
        "--windowed",
        "--name=SPIZDILI_VPN",
        f"--icon={BASE_DIR / 'icons' / 'spizdili-vpn.ico'}",
        f"--paths={BASE_DIR}",
        f"--paths={BASE_DIR / 'windows'}",
        f"--add-data={BASE_DIR / 'icons'}{os.pathsep}icons",
        f"--add-data={BASE_DIR / 'wavez_servers.json'}{os.pathsep}.",
        f"--add-data={BIN_DIR / 'xray.exe'}{os.pathsep}bin",
        str(BASE_DIR / "windows" / "main_win.py"),
    ]
    if (BIN_DIR / "geoip.dat").is_file():
        cmd.insert(-1, f"--add-data={BIN_DIR / 'geoip.dat'}{os.pathsep}bin")
    if (BIN_DIR / "geosite.dat").is_file():
        cmd.insert(-1, f"--add-data={BIN_DIR / 'geosite.dat'}{os.pathsep}bin")

    import subprocess
    subprocess.run(cmd, check=True)
    print("✓ Build complete! Standalone executable located in dist/SPIZDILI_VPN/")


if __name__ == "__main__":
    build()
