#!/usr/bin/env python3
"""Ubuntu VPN Client — Entry Point.

Initialises logging, checks system dependencies, wires together
VPNManager + ConfigManager + VPNApplication, and handles OS signals
for graceful shutdown.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

# Ensure our own directory is on the path when run in-place
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gio  # noqa: E402

from vpn_manager import ConfigManager, SystemDependencyChecker, VPNManager  # noqa: E402
from app_ui import VPNApplication  # noqa: E402

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _configure_logging() -> None:
    """Configure root logger: console + level from env."""
    level_name = os.environ.get("UBUNTU_VPN_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Dependency check dialog
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------


_vpn_manager_ref: Optional[VPNManager] = None
_application_ref: Optional[VPNApplication] = None


def _on_unix_signal(signum: int) -> bool:
    """Handle SIGINT / SIGTERM: disconnect VPN then quit."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s, shutting down gracefully…", sig_name)

    if _vpn_manager_ref is not None and _vpn_manager_ref.is_connected():
        logger.info("Disconnecting VPN before exit…")
        try:
            ok, msg = _vpn_manager_ref.disconnect()
            if not ok:
                logger.warning("Disconnect on exit: %s", msg)
        except Exception as exc:
            logger.error("Error during shutdown disconnect: %s", exc)

    if _application_ref is not None:
        try:
            window = _application_ref.get_window()
            if window:
                window.shutdown()
            _application_ref.quit()
        except Exception as exc:
            logger.error("Error quitting application: %s", exc)

    return GLib.SOURCE_REMOVE


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Application entry point. Returns exit code."""
    _configure_logging()
    try:
        from version import APP_VERSION
    except ImportError:
        APP_VERSION = "1.0.5"
    logger.info("SPIZDILI_VPN v%s starting…", APP_VERSION)

    # --- Dependency check ---
    missing = SystemDependencyChecker.get_missing()
    if missing:
        logger.error("Missing system dependencies: %s", ", ".join(missing))
        # Try to show GTK error dialog; if GTK itself is not available, print to stderr
        try:
            # Build a minimal error dialog
            _show_dependency_dialog_and_exit(missing)
        except Exception:
            print(
                f"ERROR: Missing system dependencies: {', '.join(missing)}\n"
                f"Run: sudo apt install wireguard-tools policykit-1 iptables",
                file=sys.stderr,
            )
        return 1

    # Check WireGuard kernel module
    if not SystemDependencyChecker.check_wireguard_module():
        logger.warning(
            "WireGuard kernel module may not be available. "
            "Try: sudo modprobe wireguard"
        )

    # --- Initialize managers ---
    config_manager = ConfigManager()
    vpn_manager = VPNManager(config_manager)

    global _vpn_manager_ref
    _vpn_manager_ref = vpn_manager

    # --- Create application ---
    application = VPNApplication(vpn_manager=vpn_manager)

    global _application_ref
    _application_ref = application

    # --- Register GLib UNIX signal handlers ---
    try:
        from gi.repository import GLibUnix
        GLibUnix.signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, _on_unix_signal, signal.SIGINT)
        GLibUnix.signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, _on_unix_signal, signal.SIGTERM)
    except Exception:
        try:
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, _on_unix_signal, signal.SIGINT)
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, _on_unix_signal, signal.SIGTERM)
        except Exception:
            pass

    # --- Run ---
    logger.info("Starting GTK main loop")
    exit_code = application.run(sys.argv)
    logger.info("Application exited with code %d", exit_code)
    return exit_code


def _show_dependency_dialog_and_exit(missing: list[str]) -> None:
    """Display a GTK4/Adwaita error dialog listing missing tools."""
    packages = SystemDependencyChecker.get_missing_packages()
    apt_cmd = "sudo apt install " + " ".join(packages) if packages else "see install.sh"
    missing_list = "\n".join(f"  • {m}" for m in missing)
    body = (
        f"The following required utilities are not installed:\n\n"
        f"{missing_list}\n\n"
        f"To install them, run:\n{apt_cmd}"
    )

    # Use a temporary Adw.Application just to show the dialog
    err_app = Adw.Application(application_id="com.wavez.vpnclient.depcheck")

    def on_activate(app: Adw.Application) -> None:
        # We need a transient parent; create a hidden window
        win = Adw.ApplicationWindow(application=app, visible=False)

        dialog = Adw.MessageDialog(
            heading="Missing System Dependencies",
            body=body,
            transient_for=win,
        )
        dialog.add_response("quit", "Quit")
        dialog.set_default_response("quit")
        dialog.connect("response", lambda d, r: app.quit())
        dialog.present()

    err_app.connect("activate", on_activate)
    err_app.run([])


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
