"""
Automated PyInstaller Standalone Windows Executable Builder
Produces: dist/SPIZDILI_VPN.exe and dist/SPIZDILI_VPN_v1.0.3_Windows_x64.zip
"""
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = BASE_DIR / "bin"
BIN_DIR.mkdir(exist_ok=True)
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"


def build() -> None:
    xray_exe = BIN_DIR / "xray.exe"
    if not xray_exe.is_file():
        print(f"⚠ Warning: {xray_exe} not found!")

    print("→ Building standalone SPIZDILI_VPN.exe with PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=SPIZDILI_VPN",
        f"--icon={str(BASE_DIR / 'icons' / 'spizdili-vpn.ico')}",
        f"--paths={str(BASE_DIR)}",
        f"--paths={str(BASE_DIR / 'windows')}",
        f"--add-data={str(BASE_DIR / 'icons')}{os.pathsep}icons",
        f"--add-data={str(BASE_DIR / 'wavez_servers.json')}{os.pathsep}.",
        f"--add-data={str(BIN_DIR / 'xray.exe')}{os.pathsep}bin",
        str(BASE_DIR / "windows" / "main_win.py"),
    ]
    if (BIN_DIR / "geoip.dat").is_file():
        cmd.insert(-1, f"--add-data={str(BIN_DIR / 'geoip.dat')}{os.pathsep}bin")
    if (BIN_DIR / "geosite.dat").is_file():
        cmd.insert(-1, f"--add-data={str(BIN_DIR / 'geosite.dat')}{os.pathsep}bin")

    subprocess.run(cmd, cwd=str(BASE_DIR), check=True)

    exe_path = DIST_DIR / "SPIZDILI_VPN.exe"
    if exe_path.is_file():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"✓ Standalone single-file executable built: {exe_path} ({size_mb:.1f} MB)")
        zip_path = DIST_DIR / "SPIZDILI_VPN_v1.0.3_Windows_x64.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(exe_path, arcname="SPIZDILI_VPN.exe")
        print(f"✓ Created portable zip archive: {zip_path}")


if __name__ == "__main__":
    build()
