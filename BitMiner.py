"""Entry point for the Windows build (PyInstaller) and for double-click launching."""

import sys

from bitminer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
