"""
SPIZDILI_VPN v1.2.6 — Windows Launcher
"""
import sys
import os
from pathlib import Path

# Add directory paths to sys.path
base_dir = Path(__file__).resolve().parent
root_dir = base_dir.parent
for p in (str(base_dir), str(root_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from windows.app_win_ui import main
except ImportError:
    from app_win_ui import main

if __name__ == "__main__":
    main()
