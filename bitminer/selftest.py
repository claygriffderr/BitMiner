"""A quick check that needs no window: build every picture, fly the ship, play some gallery
scenes, fight in the combat sandbox, play Secure the Base, save and load settings.

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

    # Secure the Base: the big map builds, and 40 seconds on auto pilot looks round the station,
    # sets a drill and digs ore while the first wave launches.
    from .combat.campaign import Campaign, autopilot as campaign_pilot

    game = Campaign(Quiet(), Quiet(), settings.Tuning())
    assert len(game.world.field) > 5000, "the big map came out nearly empty"
    opened = False
    with tempfile.TemporaryDirectory() as d:
        log = PlayLog(Path(d), {"mode": "selftest-campaign"})
        t = 0.0
        for _ in range(60 * 40):
            controls, trigger, cursor, set_drill = campaign_pilot(game, t)
            events = game.step(1 / 60, controls, trigger, cursor, set_drill)
            opened = opened or ("station", "open") in events
            log.record(1 / 60, events, game)
            t += 1 / 60
        log.close(game)
    assert opened, "the station never opened"
    assert game.drills, "no drill was set"
    assert game.cargo > 0 or game.credits > 0, "no ore was collected"
    assert game.fleet.number >= 1, "the first wave never launched"

    # The station screen, the console and the sprint 7 pictures build.
    from art import hud, station as ST
    from .combat.shop import PAGE_ITEMS, PAGES
    from .graphics.images import crumble_frames, laser_charge, worn_rock
    from .ui.station_screen import page_content

    for page in PAGES:
        for sel in range(len(PAGE_ITEMS[page])):
            rows, det = page_content(game, page, sel)
            assert ST.station_panel(page, rows, sel, det, game.credits).size == (ST.PANEL_W, ST.PANEL_H)
    spots = {}
    hud.campaign_console(weapons=("auto",), current="auto", shield_level=0, boost_level=0, blank=True, spots=spots)
    assert {"ammo", "hull", "downs"} <= set(spots)
    assert worn_rock(64, 1, True, 3, (90.0,), 5).size == (68, 68)
    assert len(crumble_frames(32, 0, True, 3, (0.0,), 5, 9)) == 9
    assert laser_charge(20)[1] is not None

    # Sprint 8: the upgrade, sentry and mine pictures build, an upgrade takes effect, a sentry
    # shoots and a mine goes off.
    from art import items as I

    for tier in (1, 2, 3):
        assert I.sentry_base(tier).size[0] > 0
        assert I.shield_bubble(tier, 14).size[0] > 0
        assert I.boost_flame(tier).size[0] > 0
    for gun in ("auto", "sniper", "missile"):
        assert I.turret_interior(gun).size[0] > 0
        assert I.sentry_shot(gun).size[0] > 0
    assert I.mine(0, "armed").size[0] > 0 and I.mine_blast(3, 64).size[0] > 0

    game = Campaign(Quiet(), Quiet(), settings.Tuning())
    st = game.stage
    st.enemies.clear()
    game.gear.raise_level("shield")
    assert st.shield_max > 0 and st.shield == st.shield_max
    x, y = game.base.x + 400, game.base.y
    while game.defenses.sentry_room(x, y):
        x += 30
    st.ship.x, st.ship.y = x, y
    still = Controls(aim=0.0)
    game.defenses.mines_carried = 1
    game.step(1 / 60, still, False, (x, y), lay_mines=True)
    assert len(st.mines) == 1, "the mine was not laid"
    mine = st.mines[0]
    game.battle.add("infantry", x + 120, y, warp=False)
    blasted = False
    for _ in range(60 * 4):
        if mine.state == "armed" and st.enemies:
            st.enemies[0].x, st.enemies[0].y = mine.x, mine.y
        blasted = blasted or any(ev[0] == "mine_blast" for ev in game.step(1 / 60, still, False, (x, y)))
        if blasted:
            break
    assert blasted, "the mine never went off"
    st.enemies.clear()
    game.defenses.carried.append(("auto", 1))
    game.step(1 / 60, still, False, (x, y), place_sentry=True)
    assert len(game.defenses.sentries) == 1, "the sentry was not placed"
    game.battle.add("guard", x + 150, y + 40, warp=False)
    fired = False
    for _ in range(60 * 4):
        fired = fired or ("fire", "sentry_auto") in game.step(1 / 60, still, False, (x, y))
        if fired:
            break
    assert fired, "the sentry never fired"

    # Settings.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / settings.FILE_NAME
        s = settings.Settings()
        s.tuning.mass = 2.0
        settings.save(s, path)
        assert settings.load(path).tuning.mass == 2.0
    return 0
