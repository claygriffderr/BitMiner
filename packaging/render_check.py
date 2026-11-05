"""Render check for the built game: fly the scripted route, play a gallery scene, and report what it drew.

GitHub's Windows build machines have no graphics card, and Windows alone only offers OpenGL 1.1
there, so this borrows Mesa's software OpenGL (llvmpipe) from the mesa-dist-win project and puts
it next to a copy of the game. Then it runs each scripted check (the flight test's --smoke route,
then the mothership laser scene in the weapon gallery) and prints everything needed to judge the
result from the build log alone: the game's progress notes, any crash log, and for each
screenshot a grid of average colours, plus a small thumbnail of the last one in base64.

    python packaging/render_check.py dist/BitMiner shots
    python packaging/render_check.py dist/BitMiner shots --no-mesa    # use this machine's OpenGL
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

MESA_REPO = "pal1000/mesa-dist-win"
MESA_PATTERN = "mesa3d-*-release-msvc.7z"
MESA_TRIES = 4      # newest releases to try, in case the newest is packed differently
RUNS = {
    "flight": ["--mode", "flight", "--smoke", "4", "--shots", "1.5,3.5", "--size", "1280x720"],
    "gallery": ["--mode", "gallery", "--scene", "mothership_laser-shield_breaks", "--smoke", "5",
                "--shots", "3.5,4.5", "--size", "1280x720"],
}
TIMEOUT = 180       # seconds; the route takes well under a minute with software OpenGL
GRID = (16, 9)      # average colours printed for each screenshot
THUMB = (320, 180)
CHUNK = 4000        # base64 characters per log line


def say(*parts) -> None:
    print(*parts, flush=True)


def find_gl(root: Path) -> Path | None:
    """The folder that holds Mesa's 64-bit opengl32.dll, if this unpacked release has one."""
    for dll in sorted(root.rglob("*.dll")):
        parts = [p.lower() for p in dll.relative_to(root).parts]
        if parts[-1] == "opengl32.dll" and "x64" in parts:
            return dll.parent
    return None


def mesa_tags() -> list[str]:
    jq = ".[] | select(.prerelease or .draft | not) | .tag_name"
    out = subprocess.run(["gh", "api", f"repos/{MESA_REPO}/releases?per_page=20", "--jq", jq],
                         check=True, capture_output=True, text=True).stdout
    return out.split()[:MESA_TRIES]


def fetch_mesa(work: Path) -> Path:
    """Download mesa-dist-win releases, newest first, until one has a 64-bit opengl32.dll."""
    for tag in mesa_tags():
        folder = work / tag
        got = subprocess.run(["gh", "release", "download", tag, "--repo", MESA_REPO,
                              "--pattern", MESA_PATTERN, "--dir", str(folder)])
        archives = sorted(folder.glob("*.7z"))
        if got.returncode or not archives:
            say(f"Mesa {tag}: nothing matching {MESA_PATTERN}")
            continue
        unpacked = folder / "x"
        subprocess.run(["7z", "x", str(archives[0]), f"-o{unpacked}", "-y"], check=True,
                       stdout=subprocess.DEVNULL)
        gl = find_gl(unpacked)
        if gl:
            say(f"Mesa {tag}: using {gl.relative_to(unpacked).as_posix()}/ "
                f"({', '.join(sorted(p.name for p in gl.glob('*.dll')))})")
            return gl
        dlls = sorted(p.relative_to(unpacked).as_posix() for p in unpacked.rglob("*.dll"))
        say(f"Mesa {tag}: no 64-bit opengl32.dll. Its DLLs are: {', '.join(dlls) or 'none'}")
        shutil.rmtree(folder, ignore_errors=True)
    raise SystemExit("Render check failed: no recent Mesa release has a 64-bit opengl32.dll")


def grab_desktop(path: Path) -> None:
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
    except Exception as e:  # noqa: BLE001 - a missing picture shouldn't hide the real problem
        say(f"Could not take a picture of the desktop: {e}")


def run_game(game: Path, shots: Path, script: list[str]) -> int | None:
    """Run one scripted check. Returns the exit code, or None if the game never finished."""
    exe = game / ("BitMiner.exe" if os.name == "nt" else "BitMiner")
    cmd = [str(exe), *script, "--shot-dir", str(shots), "--settings", str(shots / "tuning.json")]
    say("Running:", " ".join(cmd))
    start = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=game)
    try:
        code = proc.wait(TIMEOUT)
    except subprocess.TimeoutExpired:
        say(f"The game was still running after {TIMEOUT} s, so here is the desktop it was stuck on.")
        grab_desktop(shots / "desktop.png")
        proc.kill()
        proc.wait()
        return None
    say(f"The game exited with code {code} after {time.monotonic() - start:.1f} s")
    return code


def describe(path: Path, thumbnail: bool, tag: str = "") -> None:
    """Print a picture as text: its size, colour count, a grid of average colours, a thumbnail."""
    img = Image.open(path).convert("RGB")
    colours = img.getcolors(img.width * img.height) or []
    say(f"{path.name}: {img.width}x{img.height}, {len(colours)} colours")
    cells = img.resize(GRID, Image.Resampling.BOX)
    for y in range(GRID[1]):
        say("  GRID " + " ".join("%02x%02x%02x" % cells.getpixel((x, y)) for x in range(GRID[0])))
    if not thumbnail:
        return
    thumb = img.resize(THUMB, Image.Resampling.BOX).quantize(64)
    buf = io.BytesIO()
    thumb.save(buf, "PNG", optimize=True)
    text = base64.b64encode(buf.getvalue()).decode()
    n = -(-len(text) // CHUNK)
    for i in range(n):
        say(f"  THUMB {tag}{'_' if tag else ''}{path.stem} {i + 1}/{n} {text[i * CHUNK:(i + 1) * CHUNK]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game", type=Path, help="the built game folder, like dist/BitMiner")
    ap.add_argument("shots", type=Path, help="where the screenshots and notes go")
    ap.add_argument("--no-mesa", action="store_true", help="use this machine's own OpenGL")
    args = ap.parse_args(argv)

    shots = args.shots.resolve()
    if shots.exists():
        shutil.rmtree(shots)
    shots.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="render-check-"))
    game = work / "BitMiner"
    shutil.copytree(args.game, game)
    if not args.no_mesa:
        for dll in fetch_mesa(work / "mesa").glob("*.dll"):
            shutil.copy2(dll, game)
        os.environ.setdefault("GALLIUM_DRIVER", "llvmpipe")

    failed = []
    total = 0
    for name, script in RUNS.items():
        say(f"--- {name} ---")
        out = shots / name
        out.mkdir()
        code = run_game(game, out, script)
        progress = out / "progress.txt"
        if progress.exists():
            say("Game notes:\n" + progress.read_text().rstrip())
        crash = game / "bitminer_error.log"
        if crash.exists():
            say("Crash log:\n" + crash.read_text().rstrip())
            crash.unlink()
        pictures = sorted(out.glob("shot_*.png"))
        for path in pictures:
            describe(path, thumbnail=path == pictures[-1], tag=name)
        for path in out.glob("desktop.png"):
            describe(path, thumbnail=True, tag=name)
        total += len(pictures)
        if code is None:
            failed.append(f"{name}: the game timed out")
        elif code != 0:
            failed.append(f"{name}: the game exited with code {code}")
        elif not pictures:
            failed.append(f"{name}: no screenshots")

    if failed:
        say("Render check failed: " + "; ".join(failed))
        return 1
    say(f"Render check passed: {total} screenshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
