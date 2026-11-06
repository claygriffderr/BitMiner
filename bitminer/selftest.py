"""A quick check that needs no window: build every picture, fly the ship, play some gallery
scenes, fight in the combat sandbox, save and load settings.

The Windows build runs this on the build machine (`BitMiner.exe --selftest`) to prove that
everything it needs made it into the package.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path


def run() -> int:
    from art import pixfont, sprites as S

    from . import settings
    from .field import SIZES, VARIANTS
    from .flight import Controls
    from .graphics.images import light_twin, nebula_tile, rock_image, tile_noise
    from .world import FlightWorld

    # Pictures.
    for size in SIZES:
        for v in range(VARIANTS):
            for ore in (False, True):
                img = rock_image(size, v, ore)
                assert img.width == size + 4
                assert (light_twin(img) is not None) == ore
    body, flames = S.player_parts(("W", "S", "A", "D"))
    assert body.size == flames.size == (27, 27)
    assert tile_noise(240, 24, 1).shape == (240, 240)
    assert nebula_tile().size == (960, 960)
    assert pixfont.text_width("FLIGHT_TUNING.JSON") > 0

    # Flight: a minute of scripted flying through the field.
    world = FlightWorld()
    tuning = settings.Tuning()
    hits = 0
    for i in range(60 * 60):
        t = i / 60
        c = Controls(forward=(i // 80) % 3 != 2, right=(i // 150) % 2 == 0, back=(i // 400) % 5 == 4,
                     aim=(t * 55) % 360 - 180)
        hits += len(world.step(c, tuning, 1 / 60))
        s = world.ship
        assert math.isfinite(s.x) and math.isfinite(s.vx)
        assert 0 <= s.x < world.width and 0 <= s.y < world.height
    assert hits > 0, "the scripted flight never hit a rock"

    # Combat: the weapon numbers load, the effect pictures build, and a few gallery scenes play through.
    from art import effects as E
    from .combat.specs import WEAPONS
    from .combat.stage import Stage
    from .gallery import scenes as SC
    from .gallery.director import Director

    assert set(WEAPONS) == {"auto", "sniper", "missile", "laser"}
    for owner in E.TONES:
        assert E.flare(owner, 0).size == (5, 5)
    assert E.shield_bubble(14).size == (31, 31)
    assert S.explosion(2, "enemy", 33, 1).size == (33, 33)

    class Quiet:
        def burst(self, *a, **k):
            pass

        def emit(self, *a, **k):
            pass

    for key in ("missile-tank", "guard_ram-shield_breaks", "mothership_laser-armor"):
        stage = Stage(Quiet(), Quiet())
        director = Director(stage, settings.Tuning(), (1600.0, 1000.0))
        director.start(SC.BY_KEY[key])
        for _ in range(60 * 16):
            director.step(1 / 60)
            if director.finished:
                break
        assert director.finished, f"gallery scene {key} never finished"

    # The combat sandbox: half a minute of fighting on auto pilot, with a play log.
    from .combat.sandbox import Sandbox, autopilot
    from .playdata import PlayLog

    sb = Sandbox(Quiet(), Quiet(), settings.Tuning())
    with tempfile.TemporaryDirectory() as d:
        log = PlayLog(Path(d), {"mode": "selftest"})
        t = 0.0
        for _ in range(60 * 30):
            controls, trigger, cursor = autopilot(sb, t)
            log.record(1 / 60, sb.step(1 / 60, controls, trigger, cursor), sb)
            t += 1 / 60
        log.close(sb)
        assert log.path.exists() and log.path.stat().st_size > 0, "the play log was not written"
    assert sb.waves.number >= 1, "no wave arrived"
    assert sb.stage.enemies or sb.kills, "the wave never showed up"

    # Settings.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / settings.FILE_NAME
        s = settings.Settings()
        s.tuning.mass = 2.0
        settings.save(s, path)
        assert settings.load(path).tuning.mass == 2.0
    return 0
