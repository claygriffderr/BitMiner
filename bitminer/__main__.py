"""Start the flight test: `python -m bitminer` (or BitMiner.exe in the Windows build)."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def _size(text: str) -> tuple[int, int]:
    w, h = text.lower().split("x")
    return int(w), int(h)


def parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="bitminer", description="BitMiner flight test")
    p.add_argument("--selftest", action="store_true", help="check the game without opening a window")
    p.add_argument("--size", type=_size, help="window size, like 1280x720")
    p.add_argument("--crt", action="store_true", help="start with the CRT filter on")
    p.add_argument("--no-panel", action="store_true", help="start with the tuning panel hidden")
    p.add_argument("--seed", type=int, default=7, help="asteroid field layout")
    p.add_argument("--settings", help="settings file to use instead of flight_tuning.json")
    p.add_argument("--smoke", type=float, help="fly a scripted route for this many seconds, then quit")
    p.add_argument("--shots", type=lambda s: [float(v) for v in s.split(",")],
                   help="with --smoke: take screenshots at these times, like 1,2.5,4")
    p.add_argument("--shot-dir", help="where screenshots go")
    return p.parse_args(argv)


def _report_crash(dialog: bool = True) -> None:
    """A windowed program has no console, so write the error down and say where it is.

    Scripted runs (`--smoke`, `--selftest`) skip the dialog so a build machine never waits on a click.
    """
    text = traceback.format_exc()
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    log = base / "bitminer_error.log"
    try:
        log.write_text(text)
    except OSError:
        log = None
    if sys.stderr:
        print(text, file=sys.stderr)
    if dialog and sys.platform == "win32":
        import ctypes
        hint = ""
        if any(word in text for word in ("OpenGL", "GL context", "ContextException", "GLException")):
            hint = "\n\nThis usually means the graphics driver is missing OpenGL 3.3. Updating it often fixes this."
        where = f"\n\nDetails were saved to:\n{log}" if log else ""
        msg = f"BitMiner hit a problem and has to close.{hint}{where}"
        ctypes.windll.user32.MessageBoxW(None, msg, "BitMiner", 0x10)


def main(argv=None) -> int:
    args = parse(argv)
    if args.selftest:
        from .selftest import run as selftest
        try:
            return selftest()
        except Exception:
            _report_crash(dialog=False)
            return 1
    try:
        import pyglet
        pyglet.options.debug_gl = False        # checking every GL call costs frame time
        pyglet.options.audio = ("silent",)     # no sound until a later sprint
        from .app import run
        run(args)
    except Exception:
        _report_crash(dialog=not args.smoke)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
