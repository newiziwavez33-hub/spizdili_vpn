#!/usr/bin/env bash
set -euo pipefail

PKG_NAME="spizdili-vpn"
PKG_VER="1.0.3"
PKG_ARCH="amd64"
BUILD_ROOT="/tmp/spizdili_deb_build"

echo "=== Building ${PKG_NAME}_${PKG_VER}_${PKG_ARCH}.deb ==="

rm -rf "${BUILD_ROOT}"
mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/usr/local/bin"
mkdir -p "${BUILD_ROOT}/usr/local/lib/spizdili-vpn"
mkdir -p "${BUILD_ROOT}/usr/local/share/spizdili-vpn/icons"
mkdir -p "${BUILD_ROOT}/usr/share/applications"
mkdir -p "${BUILD_ROOT}/usr/share/polkit-1/actions"

# 1. DEBIAN/control
cat > "${BUILD_ROOT}/DEBIAN/control" << CONTROL_EOF
Package: ${PKG_NAME}
Version: ${PKG_VER}
Section: net
Priority: optional
Architecture: ${PKG_ARCH}
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-ayatanaappindicator3-0.1, libayatana-appindicator3-1, python3-requests, python3-pil, iptables, iproute2, wireguard, wireguard-tools, pkexec, systemd-resolved, desktop-file-utils
Maintainer: SPIZDILI VPN Team <dev@spizdili-vpn.local>
Description: SPIZDILI_VPN Client - Autonomous Linux & Windows VPN Client
 Fast and secure VPN client with VLESS Reality, WireGuard and AmneziaWG.
 100% standalone with 37 built-in servers and AI IDE streaming optimization.
CONTROL_EOF

# 2. DEBIAN/postinst
cat > "${BUILD_ROOT}/DEBIAN/postinst" << 'POSTINST_EOF'
#!/usr/bin/env bash
set -e

# Set permissions
chown root:root /usr/local/lib/spizdili-vpn/vpn-helper
chmod 0755 /usr/local/lib/spizdili-vpn/vpn-helper

if [ -f /usr/local/bin/xray-core ]; then
    chmod 0755 /usr/local/bin/xray-core
    setcap cap_net_admin,cap_net_bind_service=+ep /usr/local/bin/xray-core 2>/dev/null || true
fi

# Pre-compile Python bytecode
python3 -m compileall -q /usr/local/lib/spizdili-vpn/ 2>/dev/null || true

# Update desktop & icon caches
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
update-desktop-database /usr/share/applications 2>/dev/null || true

# Setup user profiles for existing normal users
for udir in /home/*; do
    if [ -d "$udir" ]; then
        uname=$(basename "$udir")
        cfg_dir="${udir}/.config/spizdili-vpn"
        prof_dir="${cfg_dir}/profiles"
        mkdir -p "$prof_dir"
        if [ -f /usr/local/share/spizdili-vpn/wavez_servers.json ]; then
            cp -n /usr/local/share/spizdili-vpn/wavez_servers.json "${cfg_dir}/wavez_servers.json" 2>/dev/null || true
        fi
        chown -R "${uname}:${uname}" "$cfg_dir" 2>/dev/null || true
    fi
done

echo "✓ SPIZDILI_VPN v1.0.3 installed successfully!"
exit 0
POSTINST_EOF

chmod 0755 "${BUILD_ROOT}/DEBIAN/postinst"

# 3. Payload copying
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODULES=(
    "main.py"
    "app_ui.py"
    "version.py"
    "updater.py"
    "vpn_manager.py"
    "xray_manager.py"
    "settings_manager.py"
    "incy_importer.py"
    "subscription_parser.py"
    "health_checker.py"
    "builtin_profiles.py"
    "tray_subprocess.py"
    "warp_provisioner.py"
)

for m in "${MODULES[@]}"; do
    if [ -f "${SCRIPT_DIR}/${m}" ]; then
        cp "${SCRIPT_DIR}/${m}" "${BUILD_ROOT}/usr/local/lib/spizdili-vpn/"
        chmod 0644 "${BUILD_ROOT}/usr/local/lib/spizdili-vpn/${m}"
    fi
done

# Privileged helper
cp "${SCRIPT_DIR}/vpn-helper" "${BUILD_ROOT}/usr/local/lib/spizdili-vpn/vpn-helper"
chmod 0755 "${BUILD_ROOT}/usr/local/lib/spizdili-vpn/vpn-helper"

# Assets & Icons
if [ -d "${SCRIPT_DIR}/icons" ]; then
    cp -r "${SCRIPT_DIR}/icons/"* "${BUILD_ROOT}/usr/local/share/spizdili-vpn/icons/"
    # Install icons into system theme
    for sz in 16 24 32 48 64 128 256; do
        mkdir -p "${BUILD_ROOT}/usr/share/icons/hicolor/${sz}x${sz}/apps"
        if [ -f "${SCRIPT_DIR}/icons/spizdili-vpn.png" ]; then
            cp "${SCRIPT_DIR}/icons/spizdili-vpn.png" "${BUILD_ROOT}/usr/share/icons/hicolor/${sz}x${sz}/apps/spizdili-vpn.png"
        fi
    done
fi

if [ -f "${SCRIPT_DIR}/wavez_servers.json" ]; then
    cp "${SCRIPT_DIR}/wavez_servers.json" "${BUILD_ROOT}/usr/local/share/spizdili-vpn/wavez_servers.json"
fi

# Xray binary bundle
if [ -f "${SCRIPT_DIR}/bin/xray" ]; then
    cp "${SCRIPT_DIR}/bin/xray" "${BUILD_ROOT}/usr/local/bin/xray-core"
    chmod 0755 "${BUILD_ROOT}/usr/local/bin/xray-core"
fi

# Executable launcher script
cat > "${BUILD_ROOT}/usr/local/bin/spizdili-vpn" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/local/lib/spizdili-vpn:${PYTHONPATH:-}"
exec python3 /usr/local/lib/spizdili-vpn/main.py "$@"
LAUNCHER_EOF
chmod 0755 "${BUILD_ROOT}/usr/local/bin/spizdili-vpn"

# PolicyKit action
if [ -f "${SCRIPT_DIR}/com.wavez.vpnclient.policy" ]; then
    cp "${SCRIPT_DIR}/com.wavez.vpnclient.policy" "${BUILD_ROOT}/usr/share/polkit-1/actions/com.spizdili.vpnclient.policy"
fi

# Desktop launcher entry
cat > "${BUILD_ROOT}/usr/share/applications/spizdili-vpn.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Name=SPIZDILI_VPN
Comment=Autonomous VPN Client with VLESS Reality, WireGuard and AI IDE optimization
Exec=/usr/local/bin/spizdili-vpn
Icon=spizdili-vpn
Terminal=false
Type=Application
Categories=Network;Security;VPN;
StartupWMClass=spizdili-vpn
Keywords=vpn;wireguard;vless;reality;proxy;
DESKTOP_EOF
chmod 0644 "${BUILD_ROOT}/usr/share/applications/spizdili-vpn.desktop"

# 4. Build deb package
dpkg-deb --build "${BUILD_ROOT}" "${SCRIPT_DIR}/${PKG_NAME}_${PKG_VER}_${PKG_ARCH}.deb"
rm -rf "${BUILD_ROOT}"

echo "✓ Created Debian package: ${PKG_NAME}_${PKG_VER}_${PKG_ARCH}.deb ($(du -h "${SCRIPT_DIR}/${PKG_NAME}_${PKG_VER}_${PKG_ARCH}.deb" | cut -f1))"
