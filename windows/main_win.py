"""
SPIZDILI_VPN v1.0.3 — Windows Launcher
"""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from windows.app_win_ui import main

if __name__ == "__main__":
    main()
