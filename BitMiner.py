"""Entry point for the Windows build (PyInstaller) and for double-click launching."""

import os
import sys

# A windowed program has no console. Give stray prints somewhere harmless to go.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from bitminer.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
