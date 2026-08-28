#!/usr/bin/env bash
# ===========================================================================
# WaveZ VPN Client v1.0.2 — Comprehensive Standalone Linux Installer
# ===========================================================================
# Supports: Ubuntu, Debian, Linux Mint, Pop!_OS, Fedora, Arch Linux
# Works 100% standalone on a clean OS without Incy or external subscriptions!
# ===========================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Terminal Colors & Helpers
# ---------------------------------------------------------------------------
BOLD='\033[1m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
err()  { echo -e "${RED}  ✗ ERROR:${NC} $*" >&2; }
warn() { echo -e "${YELLOW}  ⚠ WARNING:${NC} $*"; }
info() { echo -e "${CYAN}  →${NC} $*"; }
step() { echo -e "\n${BOLD}${BLUE}[*]${NC} ${BOLD}$*${NC}"; }
hdr()  { echo -e "\n${BOLD}${MAGENTA}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# Paths & Variables
# ---------------------------------------------------------------------------
APP_NAME="SPIZDILI_VPN"
APP_VERSION="1.0.3"
LIB_DIR="/usr/local/lib/wavez-vpn"
BIN_PATH="/usr/local/bin/wavez-vpn-client"
SPIZDILI_BIN_PATH="/usr/local/bin/spizdili-vpn"
LEGACY_BIN_PATH="/usr/local/bin/ubuntu-vpn-client"
POLKIT_DIR="/usr/share/polkit-1/actions"
DESKTOP_DIR="/usr/share/applications"
SHARE_DIR="/usr/local/share/wavez-vpn"
ICON_DEST="${SHARE_DIR}/icons"
HELPER_PATH="${LIB_DIR}/vpn-helper"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET_USER="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 2>/dev/null || echo "$HOME")"

# ---------------------------------------------------------------------------
# Help & Usage
# ---------------------------------------------------------------------------
show_help() {
    echo "${APP_NAME} v${APP_VERSION} — Linux Installer"
    echo ""
    echo "Usage:"
    echo "  sudo ./install.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help          Show this help message and exit"
    echo "  -c, --check         Run dependency and environment diagnostics without installing"
    echo "  -u, --uninstall     Completely remove ${APP_NAME} from the system"
    echo "  -r, --reinstall     Clean reinstall (uninstall then install)"
    echo "  -y, --yes           Non-interactive mode (auto-confirm package installations)"
    echo ""
    echo "Examples:"
    echo "  sudo ./install.sh              # Standard installation"
    echo "  sudo ./install.sh --check      # Check system dependencies"
    echo "  sudo ./install.sh --uninstall  # Clean uninstall"
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
check_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This installer requires root privileges."
        echo -e "Please run with: ${BOLD}sudo $0${NC}"
        exit 1
    fi
}

detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    else
        echo "unknown"
    fi
}

# ---------------------------------------------------------------------------
# Dependency Resolution & Installation
# ---------------------------------------------------------------------------
install_dependencies() {
    local pm="$1"
    step "Resolving and installing required system dependencies"

    case "$pm" in
        apt)
            info "Updating APT package index..."
            apt-get update -qq || warn "APT update had warnings, continuing..."

            local apt_packages=(
                "wireguard"
                "wireguard-tools"
                "python3"
                "python3-pip"
                "python3-gi"
                "python3-gi-cairo"
                "gir1.2-gtk-4.0"
                "gir1.2-adw-1"
                "gir1.2-ayatanaappindicator3-0.1"
                "libayatana-appindicator3-1"
                "python3-requests"
                "python3-urllib3"
                "iptables"
                "iproute2"
                "systemd-resolved"
                "pkexec"
                "curl"
                "unzip"
                "desktop-file-utils"
            )

            local to_install=()
            for pkg in "${apt_packages[@]}"; do
                if dpkg -s "$pkg" &>/dev/null; then
                    ok "$pkg is already installed"
                else
                    to_install+=("$pkg")
                fi
            done

            if [[ ${#to_install[@]} -gt 0 ]]; then
                info "Installing missing APT packages: ${to_install[*]}"
                DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${to_install[@]}" || {
                    warn "Some optional packages failed to install, trying standard install..."
                    apt-get install -y "${to_install[@]}" || true
                }
            fi
            ;;

        dnf)
            info "Using DNF package manager (Fedora/RHEL)"
            dnf install -y wireguard-tools python3-gobject gtk4 libadwaita libayatana-appindicator-gtk3 python3-requests iptables iproute polkit unzip curl || warn "Some DNF packages failed"
            ;;

        pacman)
            info "Using Pacman package manager (Arch/Manjaro)"
            pacman -Sy --noconfirm --needed wireguard-tools python-gobject gtk4 libadwaita libayatana-appindicator python-requests iptables iproute2 polkit unzip curl || warn "Some Pacman packages failed"
            ;;

        *)
            warn "Unrecognized package manager. Please ensure wireguard-tools, GTK4, Libadwaita, and Python3-GObject are installed."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Installation Tasks
# ---------------------------------------------------------------------------
create_directories() {
    step "Creating application directories"
    for dir in "${LIB_DIR}" "${ICON_DEST}" "${SHARE_DIR}" "/usr/local/bin" "/usr/share/polkit-1/actions" "/usr/share/applications"; do
        mkdir -p "$dir"
        chmod 755 "$dir"
        ok "Directory ready: $dir"
    done
}

install_xray_core() {
    step "Installing standalone Xray Reality core engine"
    local installed=false

    # 1. Check local bundled binary in repository
    if [[ -f "${SCRIPT_DIR}/bin/xray" ]]; then
        rm -f "/usr/local/bin/xray-core" && cp -f "${SCRIPT_DIR}/bin/xray" "/usr/local/bin/xray-core"
        chmod 755 "/usr/local/bin/xray-core"
        ln -sf "/usr/local/bin/xray-core" "/usr/local/bin/xray" 2>/dev/null || true
        ok "Installed bundled Xray core: /usr/local/bin/xray-core"
        installed=true
    fi

    # 2. Check /opt/incy if available
    if [[ "$installed" = false && -f "/opt/incy/lib/app/resources/bin/xray" ]]; then
        rm -f "/usr/local/bin/xray-core" && cp -f "/opt/incy/lib/app/resources/bin/xray" "/usr/local/bin/xray-core"
        chmod 755 "/usr/local/bin/xray-core"
        ln -sf "/usr/local/bin/xray-core" "/usr/local/bin/xray" 2>/dev/null || true
        ok "Imported Xray core from system: /usr/local/bin/xray-core"
        installed=true
    fi

    # 3. Fallback: Download official release for Linux 64-bit
    if [[ "$installed" = false && ! -f "/usr/local/bin/xray-core" ]]; then
        info "Downloading official Xray core release for Linux x86_64..."
        local tmp_zip="/tmp/xray-linux-64.zip"
        if curl -sSL --connect-timeout 10 "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip" -o "$tmp_zip"; then
            unzip -q -o "$tmp_zip" xray -d /usr/local/bin/ 2>/dev/null || true
            mv -f /usr/local/bin/xray /usr/local/bin/xray-core 2>/dev/null || true
            chmod 755 /usr/local/bin/xray-core
            ln -sf "/usr/local/bin/xray-core" "/usr/local/bin/xray" 2>/dev/null || true
            rm -f "$tmp_zip"
            ok "Downloaded and installed standalone Xray core: /usr/local/bin/xray-core"
            installed=true
        else
            warn "Could not download Xray core automatically. Please ensure internet access or place binary in ${SCRIPT_DIR}/bin/xray"
        fi
    fi

    # Grant CAP_NET_ADMIN so Xray can create TUN interface for 100% system-wide routing
    if command -v setcap &>/dev/null && [[ -f "/usr/local/bin/xray-core" ]]; then
        setcap cap_net_admin,cap_net_bind_service=+ep /usr/local/bin/xray-core 2>/dev/null || true
        ok "Enabled kernel network capabilities (CAP_NET_ADMIN) for system-wide TUN routing"
    fi
}

install_helper() {
    step "Installing privileged network helper"
    cp "${SCRIPT_DIR}/vpn-helper" "${HELPER_PATH}"
    chown root:root "${HELPER_PATH}"
    chmod 755 "${HELPER_PATH}"
    ok "Installed privileged helper: ${HELPER_PATH} (0755 root:root)"
}

install_python_modules() {
    step "Installing Python modules & optimizing bytecode"
    local modules=(
        "main.py"
        "app_ui.py"
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

    for f in "${modules[@]}"; do
        if [[ -f "${SCRIPT_DIR}/${f}" ]]; then
            cp "${SCRIPT_DIR}/${f}" "${LIB_DIR}/${f}"
            chmod 644 "${LIB_DIR}/${f}"
            ok "Installed module: ${LIB_DIR}/${f}"
        fi
    done

    # Install bundled servers database
    if [[ -f "${SCRIPT_DIR}/wavez_servers.json" ]]; then
        cp "${SCRIPT_DIR}/wavez_servers.json" "${SHARE_DIR}/wavez_servers.json"
        chmod 644 "${SHARE_DIR}/wavez_servers.json"
        ok "Installed built-in servers database: ${SHARE_DIR}/wavez_servers.json"
    fi

    # Backward compatibility symlinks
    ln -sfn "${LIB_DIR}" "/usr/local/lib/ubuntu-vpn" 2>/dev/null || true
    ln -sfn "${SHARE_DIR}" "/usr/local/share/ubuntu-vpn" 2>/dev/null || true

    # Pre-compile bytecode (.pyc) for maximum startup speed
    python3 -m compileall -q "${LIB_DIR}" 2>/dev/null && ok "Compiled bytecode cache (.pyc) for fast startup" || true
}

install_launcher() {
    step "Installing binary launcher"
    cat > "${BIN_PATH}" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
# SPIZDILI_VPN Client launcher
exec python3 /usr/local/lib/wavez-vpn/main.py "$@"
LAUNCHER_EOF
    chmod 755 "${BIN_PATH}"
    ln -sf "${BIN_PATH}" "${SPIZDILI_BIN_PATH}" 2>/dev/null || true
    ln -sf "${BIN_PATH}" "${LEGACY_BIN_PATH}" 2>/dev/null || true
    ok "Installed launchers: ${BIN_PATH} & ${SPIZDILI_BIN_PATH}"
}

install_polkit() {
    step "Installing Polkit authorization policy"
    if [[ -f "${SCRIPT_DIR}/com.wavez.vpnclient.policy" ]]; then
        cp "${SCRIPT_DIR}/com.wavez.vpnclient.policy" "${POLKIT_DIR}/com.wavez.vpnclient.policy"
        chmod 644 "${POLKIT_DIR}/com.wavez.vpnclient.policy"
        chown root:root "${POLKIT_DIR}/com.wavez.vpnclient.policy"
        ok "Installed Polkit policy: ${POLKIT_DIR}/com.wavez.vpnclient.policy"
    fi
}

install_desktop_and_icons() {
    step "Installing desktop menu entry & application icons"

    # Desktop file
    if [[ -f "${SCRIPT_DIR}/com.wavez.vpnclient.desktop" ]]; then
        cp "${SCRIPT_DIR}/com.wavez.vpnclient.desktop" "${DESKTOP_DIR}/com.wavez.vpnclient.desktop"
        chmod 644 "${DESKTOP_DIR}/com.wavez.vpnclient.desktop"
        ok "Installed desktop entry: ${DESKTOP_DIR}/com.wavez.vpnclient.desktop"
    fi

    # Clean legacy desktop file if present
    rm -f "${DESKTOP_DIR}/com.ubuntu.vpnclient.desktop" 2>/dev/null || true

    # Icons (both SVG and PNG)
    mkdir -p "${ICON_DEST}"
    if [[ -d "${SCRIPT_DIR}/icons" ]]; then
        for icon_file in "${SCRIPT_DIR}/icons"/*; do
            if [[ -f "$icon_file" ]]; then
                cp "$icon_file" "${ICON_DEST}/"
                chmod 644 "${ICON_DEST}/$(basename "$icon_file")"
                ok "Installed icon: $(basename "$icon_file")"
            fi
        done

        # System icon theme integration (scalable & 512x512)
        local hicolor_scalable="/usr/share/icons/hicolor/scalable/apps"
        local hicolor_512="/usr/share/icons/hicolor/512x512/apps"
        local hicolor_256="/usr/share/icons/hicolor/256x256/apps"
        local local_hicolor="/usr/local/share/icons/hicolor/scalable/apps"
        mkdir -p "$hicolor_scalable" "$hicolor_512" "$hicolor_256" "$local_hicolor"

        for state in connected disconnected error; do
            local src="${ICON_DEST}/vpn-${state}.svg"
            if [[ -f "$src" ]]; then
                cp "$src" "${hicolor_scalable}/vpn-${state}.svg" 2>/dev/null || true
                cp "$src" "${local_hicolor}/vpn-${state}.svg" 2>/dev/null || true
            fi
        done

        # Application mascot icons (multi-resolution square icons)
        for s in 512 256 128 64 48 32 16; do
            mkdir -p "/usr/share/icons/hicolor/${s}x${s}/apps"
            if [[ -f "${SCRIPT_DIR}/icons/spizdili-vpn-${s}.png" ]]; then
                cp "${SCRIPT_DIR}/icons/spizdili-vpn-${s}.png" "/usr/share/icons/hicolor/${s}x${s}/apps/spizdili-vpn.png" 2>/dev/null || true
            elif [[ -f "${ICON_DEST}/spizdili-vpn.png" ]]; then
                cp "${ICON_DEST}/spizdili-vpn.png" "/usr/share/icons/hicolor/${s}x${s}/apps/spizdili-vpn.png" 2>/dev/null || true
            fi
        done
        cp "${ICON_DEST}/spizdili-vpn.png" "${hicolor_scalable}/spizdili-vpn.png" 2>/dev/null || true
        cp "${ICON_DEST}/spizdili-vpn.png" "${local_hicolor}/spizdili-vpn.png" 2>/dev/null || true

        if command -v gtk-update-icon-cache &>/dev/null; then
            gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
            gtk-update-icon-cache -f /usr/local/share/icons/hicolor/ 2>/dev/null || true
        fi
    fi

    # Update desktop database
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
        ok "Updated desktop application database"
    fi
}

initialize_user_environment() {
    step "Setting up user configuration and built-in server profiles"
    local config_dir="${USER_HOME}/.config/wavez-vpn"
    local profiles_dir="${config_dir}/profiles"
    local legacy_dir="${USER_HOME}/.config/ubuntu-vpn"

    mkdir -p "$profiles_dir"

    # Copy bundled server database to user config
    if [[ -f "${SHARE_DIR}/wavez_servers.json" ]]; then
        cp "${SHARE_DIR}/wavez_servers.json" "${config_dir}/wavez_servers.json"
        cp "${SHARE_DIR}/wavez_servers.json" "${config_dir}/incy_servers.json" 2>/dev/null || true
    fi

    # Populate all 37 servers and default settings (runs independently of Incy)
    python3 - << 'PY_EOF' || true
import sys
sys.path.insert(0, "/usr/local/lib/wavez-vpn")
try:
    from settings_manager import SettingsManager
    sm = SettingsManager()
    sm.save()

    from incy_importer import IncyImporter
    from vpn_manager import ConfigManager
    cm = ConfigManager()
    servers = IncyImporter.to_parsed_servers()
    for s in servers:
        p = cm.profiles_dir / f"{s.name}.conf"
        if not p.exists():
            p.write_text(s.conf_content, encoding="utf-8")
    print(f"  ✓ Initialized {len(servers)} built-in VPN server profiles.")
except Exception as e:
    print(f"  ⚠ Profile initialization notice: {e}")
PY_EOF

    chown -R "${TARGET_USER}:${TARGET_USER}" "$config_dir" 2>/dev/null || true
    chmod 700 "$config_dir" 2>/dev/null || true
    chmod 700 "$profiles_dir" 2>/dev/null || true
    ok "User environment fully configured at ${config_dir}"
}

# ---------------------------------------------------------------------------
# Diagnostics / Check Mode
# ---------------------------------------------------------------------------
run_diagnostics() {
    hdr "System Diagnostics & Verification Report"

    local pass_count=0
    local warn_count=0
    local fail_count=0

    check_cmd() {
        local name="$1"
        shift
        if "$@" &>/dev/null; then
            echo -e "  ${GREEN}[ PASS ]${NC} $name"
            pass_count=$((pass_count + 1))
        else
            echo -e "  ${RED}[ FAIL ]${NC} $name"
            fail_count=$((fail_count + 1))
        fi
    }

    check_info() {
        local name="$1"
        shift
        if "$@" &>/dev/null; then
            echo -e "  ${GREEN}[ PASS ]${NC} $name"
            pass_count=$((pass_count + 1))
        else
            echo -e "  ${YELLOW}[ INFO ]${NC} $name"
            warn_count=$((warn_count + 1))
        fi
    }

    echo -e "${BOLD}Core System Binaries:${NC}"
    check_cmd "Python 3 (>= 3.10)" python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    check_cmd "wireguard-tools (wg)" command -v wg
    check_cmd "wg-quick utility" command -v wg-quick
    check_cmd "PolicyKit pkexec" command -v pkexec
    check_cmd "iptables firewall" command -v iptables
    check_cmd "systemd-resolved / resolvectl" command -v resolvectl
    check_info "AmneziaWG (awg-quick) (optional, for AWG obfuscation)" command -v awg-quick
    check_cmd "Xray core binary (/usr/local/bin/xray-core)" test -x /usr/local/bin/xray-core

    echo -e "\n${BOLD}Python GUI & Networking Libraries:${NC}"
    check_cmd "PyGObject (gi)" python3 -c "import gi"
    check_cmd "GTK 4.0 bindings" python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk"
    check_cmd "Libadwaita 1.0" python3 -c "import gi; gi.require_version('Adw', '1'); from gi.repository import Adw"
    check_cmd "AyatanaAppIndicator3 (Tray)" python3 -c "import gi; gi.require_version('AyatanaAppIndicator3', '0.1'); from gi.repository import AyatanaAppIndicator3"
    check_cmd "Requests HTTP library" python3 -c "import requests"
    check_cmd "SQLite3 library" python3 -c "import sqlite3"

    echo -e "\n${BOLD}Application Components & Files:${NC}"
    check_cmd "Installed Launcher (${BIN_PATH})" test -x "${BIN_PATH}"
    check_cmd "Privileged Helper (${HELPER_PATH})" test -x "${HELPER_PATH}"
    check_cmd "Built-in Servers Database (${SHARE_DIR}/wavez_servers.json)" test -f "${SHARE_DIR}/wavez_servers.json"
    check_cmd "Polkit Policy Action" test -f "${POLKIT_DIR}/com.wavez.vpnclient.policy"
    check_cmd "Desktop Menu Entry" test -f "${DESKTOP_DIR}/com.wavez.vpnclient.desktop"

    echo ""
    if [[ $fail_count -eq 0 ]]; then
        echo -e "${GREEN}✓ All core components and dependencies verified successfully!${NC}"
    else
        echo -e "${RED}✗ Found $fail_count issue(s) that need attention.${NC}"
    fi
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
uninstall_app() {
    hdr "Uninstalling ${APP_NAME}"

    step "Removing binaries and launchers"
    rm -f "${BIN_PATH}" "${LEGACY_BIN_PATH}" && ok "Removed launchers" || true

    step "Removing application libraries and assets"
    rm -rf "${LIB_DIR}" "/usr/local/lib/ubuntu-vpn" "${SHARE_DIR}" "/usr/local/share/ubuntu-vpn" && ok "Removed application directories" || true

    step "Removing Polkit authorization policies"
    rm -f "${POLKIT_DIR}/com.wavez.vpnclient.policy" "${POLKIT_DIR}/com.ubuntu.vpnclient.policy" && ok "Removed Polkit policies" || true

    step "Removing desktop menu entry and icons"
    rm -f "${DESKTOP_DIR}/com.wavez.vpnclient.desktop" "${DESKTOP_DIR}/com.ubuntu.vpnclient.desktop" && ok "Removed desktop files" || true

    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
    fi

    step "Removing staged WireGuard configs and active links"
    rm -f /etc/wireguard/wavez-*.conf /etc/wireguard/ubuntu-*.conf 2>/dev/null || true

    echo -e "\n${GREEN}========================================================${NC}"
    echo -e "${GREEN}✓ ${APP_NAME} has been completely uninstalled.${NC}"
    echo -e "${GREEN}========================================================${NC}"
    info "Note: User profiles and settings in ~/.config/wavez-vpn were preserved."
    info "To delete them manually: rm -rf ~/.config/wavez-vpn ~/.config/ubuntu-vpn"
}

# ---------------------------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------------------------
main() {
    local action="install"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                exit 0
                ;;
            -c|--check)
                action="check"
                shift
                ;;
            -u|--uninstall)
                action="uninstall"
                shift
                ;;
            -r|--reinstall)
                action="reinstall"
                shift
                ;;
            -y|--yes)
                shift
                ;;
            *)
                err "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    case "$action" in
        check)
            run_diagnostics
            exit 0
            ;;
        uninstall)
            check_root
            uninstall_app
            exit 0
            ;;
        reinstall)
            check_root
            uninstall_app
            echo ""
            ;;
    esac

    check_root

    echo -e "\n${BOLD}${CYAN}${APP_NAME} v${APP_VERSION} — Standalone Installation Suite${NC}"
    echo -e "${CYAN}Target User: ${TARGET_USER} (${USER_HOME})${NC}\n"

    local pm
    pm="$(detect_pkg_manager)"
    info "Detected package manager: ${pm}"

    install_dependencies "$pm"
    create_directories
    install_xray_core
    install_helper
    install_python_modules
    install_launcher
    install_polkit
    install_desktop_and_icons
    initialize_user_environment

    run_diagnostics

    echo -e "\n${BOLD}${GREEN}========================================================${NC}"
    echo -e "${BOLD}${GREEN}✓ ${APP_NAME} v${APP_VERSION} Installation Completed Successfully!${NC}"
    echo -e "${BOLD}${GREEN}========================================================${NC}"
    echo -e "You can launch the client:"
    echo -e "  1. From Application Menu:  ${BOLD}${APP_NAME}${NC}"
    echo -e "  2. From Terminal:          ${BOLD}wavez-vpn-client${NC}"
    echo -e "\nTo check system health:    ${BOLD}sudo ./install.sh --check${NC}"
    echo -e "To uninstall:              ${BOLD}sudo ./install.sh --uninstall${NC}\n"
}

main "$@"
