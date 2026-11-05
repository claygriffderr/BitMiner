"""Record a GIF of weapon gallery scenes: `python -m bitminer --record DIR --size 1280x720`.

Each scene plays one loop on the auto pilot at a steady 25 frames a second (two game steps per
frame, whatever speed the computer manages), cropped to the scene's framing. Attack scenes show
your shield and hull in the corner, missile scenes your missile rack, and mothership scenes its
health bar, so the GIFs read on their own. Also writes `scenes.json` listing every GIF with its title and notes, for the review page.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from PIL import Image

from .gallery import scenes as SC
from .graphics.renderer import VIEW
from .ui import gallery_hud as GH

FPS = 25
STEPS = 2                  # game steps per GIF frame
LIMIT = 20.0               # seconds; no scene loop should run longer


def to_palette(frames: list[Image.Image]) -> list[Image.Image]:
    """One shared 255-colour palette for the whole clip, so still parts of the picture stay the
    same from frame to frame and the GIF only stores what moved."""
    step = max(1, len(frames) // 24)
    sample = frames[::step]
    w, h = sample[0].size
    sheet = Image.new("RGB", (w, h * len(sample)))
    for i, f in enumerate(sample):
        sheet.paste(f, (0, h * i))
    palette = sheet.quantize(255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    return [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]


class Recorder:
    def __init__(self, view, out_dir: str, only: str | None = None):
        self.view = view
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        keys = [k.strip() for k in only.split(",")] if only else [s.key for s in SC.SCENES]
        self.queue = [SC.BY_KEY[k] for k in keys]
        self.frames: list[Image.Image] = []
        self.index = -1
        self.started = time.perf_counter()
        self.made: list[dict] = []
        view.director.auto = True
        self._next()

    def _next(self) -> None:
        self.index += 1
        if self.index >= len(self.queue):
            self._finish()
            return
        scene = self.queue[self.index]
        v = self.view
        col = SC.COLUMNS.index(scene.column)
        v.column = col
        v.row = SC.rows_of(scene.column).index(scene.row)
        v.play(scene)
        v.camera.reset()
        self.frames = []
        self.t = 0.0

    def frame(self) -> None:
        """Called from the gallery's on_draw: step, draw, capture."""
        v = self.view
        w = v.window
        if self.index >= len(self.queue):
            return
        d = v.director
        before = d.finished
        for _ in range(STEPS):
            v.advance(1 / (FPS * STEPS))
            w.clock += 1 / (FPS * STEPS)
            self.t += 1 / (FPS * STEPS)
        done = d.finished > before or self.t >= LIMIT
        w.renderer.draw(v.frame(), self.draw_ui)
        if not done:
            self.frames.append(self._crop(w.renderer.screenshot()))
        else:
            self._save()
            self._next()

    def crop_rect(self) -> tuple[int, int, int, int]:
        """The scene's framing in game pixels: left, bottom, width, height."""
        cw, ch = self.queue[self.index].crop
        return (VIEW[0] - cw) // 2, (VIEW[1] - ch) // 2, cw, ch

    def _crop(self, img: Image.Image) -> Image.Image:
        k = self.view.window.renderer.k
        left, bottom, cw, ch = self.crop_rect()
        top = VIEW[1] - bottom - ch
        return img.crop((left * k, top * k, (left + cw) * k, (top + ch) * k))

    def draw_ui(self) -> None:
        """Only the readouts the scene needs, moved into the corners of the crop."""
        v = self.view
        hud = v.hud
        cam = v.window.renderer.ui_cam
        left, bottom, cw, ch = self.crop_rect()
        home = cam.position
        scene = self.queue[self.index]
        if scene.column not in SC.WEAPONS:
            # Shield and hull console into the crop's bottom-right corner.
            dx = (left + cw - 4) - (GH.CONSOLE_X + GH.CONSOLE_W)
            dy = (bottom + 4) - GH.CONSOLE_Y
            cam.position = (home[0] - dx, home[1] - dy)
            cam.use()
            hud.console.draw()
        if hud.missiles is not None and scene.column == "missile":
            # The missile rack into the same corner, so the reload shows.
            dx = (left + cw - 4) - (GH.CONSOLE_X + GH.CONSOLE_W)
            dy = (bottom + 4) - GH.AMMO_Y
            cam.position = (home[0] - dx, home[1] - dy)
            cam.use()
            hud.ammo.draw()
        if hud.boss_health is not None:
            dx = 0
            dy = (bottom + 4) - GH.BOSS_Y
            cam.position = (home[0] - dx, home[1] - dy)
            cam.use()
            hud.boss.draw()
        cam.position = home
        cam.use()

    def _save(self) -> None:
        scene = self.queue[self.index]
        frames = self.frames
        if not frames:
            return
        name = f"{scene.key}.gif"
        pal = to_palette(frames)
        pal[0].save(self.out / name, save_all=True, append_images=pal[1:], duration=1000 // FPS, loop=0,
                    disposal=1, optimize=False)
        size = (self.out / name).stat().st_size
        self.made.append({"key": scene.key, "file": name, "title": scene.title, "about": scene.about,
                          "column": scene.column, "row": scene.row, "label": SC.column_label(scene.column),
                          "row_label": SC.row_label(scene.row), "seconds": round(len(frames) / FPS, 2),
                          "size": [frames[0].width, frames[0].height], "bytes": size})
        print(f"{name}: {len(frames)} frames, {size / 1e6:.2f} MB", flush=True)

    def _finish(self) -> None:
        index = self.out / "scenes.json"
        old = json.loads(index.read_text()) if index.exists() else []
        keep = {m["key"]: m for m in old}
        for m in self.made:
            keep[m["key"]] = m
        order = [s.key for s in SC.SCENES]
        index.write_text(json.dumps([keep[k] for k in order if k in keep], indent=1))
        print(f"Recorded {len(self.made)} scenes in {time.perf_counter() - self.started:.0f} s", flush=True)
        self.view.window.close()
