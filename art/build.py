"""Build every art asset.

    python -m art.build                # sprites and mockups into assets/
    python -m art.build --review DIR   # also the images for the art review page
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from . import hud, mockups, pix, pixfont, sprites as S
from .palette import PALETTE, ROLES, hexcode, rgba

ROOT = Path(__file__).resolve().parent.parent


def strip(frames: list[Image.Image]) -> Image.Image:
    w = max(f.width for f in frames)
    h = max(f.height for f in frames)
    out = Image.new("RGBA", (w * len(frames), h), pix.CLEAR)
    for i, f in enumerate(frames):
        out.alpha_composite(f, (i * w + (w - f.width) // 2, (h - f.height) // 2))
    return out


def sprite_catalog() -> dict[str, Image.Image]:
    """Every sprite as the game will load it (1x, transparent). Animations are horizontal strips."""
    c: dict[str, Image.Image] = {}
    c["player_ship"] = S.tight(S.player_ship())
    body, _ = S.player_parts()
    c["player_ship_body"] = body
    for key in ("W", "S", "A", "D"):
        c[f"player_flame_{key}"] = strip([S.player_flames((key,), f) for f in range(2)])
    c["sentry"] = S.tight(S.sentry())
    c["drill"] = strip([S.drill(f) for f in range(2)])
    c["home_base"] = strip([S.home_base(f) for f in range(2)])
    c["shot_auto"] = S.shot_auto()
    c["shot_sniper"] = S.shot_sniper()
    c["missile_player"] = strip([S.missile_player(f) for f in range(2)])
    c["laser_player"] = strip([S.laser_player(120, f) for f in range(2)])
    c["infantry"] = strip([S.infantry(f) for f in range(2)])
    c["guard"] = strip([S.guard(f) for f in range(2)])
    c["guard_charging"] = strip([S.guard(f, charging=True) for f in range(2)])
    c["rapid_assault"] = strip([S.rapid_assault(f) for f in range(2)])
    c["tank"] = strip([S.tank(f) for f in range(2)])
    c["mothership"] = strip([S.mothership(f) for f in range(2)])
    c["mothership_laser_charge"] = strip([S.mothership(0, laser_charge=q / 4) for q in range(1, 5)])
    c["shot_infantry"] = strip([S.shot_infantry(f) for f in range(2)])
    c["shot_rapid"] = S.shot_rapid()
    c["missile_enemy"] = strip([S.missile_enemy(f) for f in range(2)])
    for kind in ("shield", "repair", "damage", "speed"):
        c[f"powerup_{kind}"] = strip([S.powerup(kind, f) for f in range(2)])
    c["safe_zone"] = strip([S.safe_zone(44, f) for f in range(0, 8, 2)])
    for d, seed in ((10, 101), (14, 102), (18, 103), (24, 104), (32, 105), (48, 106), (64, 107), (96, 108)):
        c[f"asteroid_{d}"] = S.asteroid(d, seed, ore=0)
        c[f"asteroid_{d}_ore"] = S.asteroid(d, seed + 50, ore=max(1, d // 5))
    for pal in ("enemy", "danger", "player"):
        c[f"explosion_{pal}"] = strip([S.explosion(f, pal) for f in range(6)])
    c["shield_hit"] = strip([S.shield_hit(f) for f in range(4)])
    c["armor_hit"] = strip([S.armor_hit(f) for f in range(3)])
    c["ram_warning"] = strip([S.ram_warning(80, f) for f in range(2)])
    c["laser_warning"] = strip([S.laser_warning(120, f) for f in range(2)])
    c["laser_beam"] = strip([S.laser_beam(120, f) for f in range(2)])
    for kind in hud.WEAPON_ICONS:
        c[f"hud_weapon_{kind}"] = hud.weapon_icon(kind)
    return c


def build_assets() -> None:
    out = ROOT / "assets" / "sprites"
    out.mkdir(parents=True, exist_ok=True)
    for name, img in sprite_catalog().items():
        img.save(out / f"{name}.png")
    mk = ROOT / "assets" / "mockups"
    mk.mkdir(parents=True, exist_ok=True)
    for name, fn in (("defend_the_drill", mockups.defend_the_drill), ("mothership_assault", mockups.mothership_assault)):
        scene = fn()
        scene.render().save(mk / f"{name}.png", optimize=True)
        scene.render(crt=True).save(mk / f"{name}_crt.png", optimize=True)
    print(f"wrote {len(list(out.glob('*.png')))} sprite files and mockups")


# ---------------------------------------------------------------- review page images

def _stage(w: int, h: int, k: int) -> pix.Scene:
    return pix.Scene(w, h, k)


def _gif(frames: list[Image.Image], path: Path, ms: int | list[int]) -> None:
    pal = [f.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=ms, loop=0, disposal=1, optimize=False)


def _label(scene: pix.Scene, text: str, x: int, y: int, color: str = "hud_dim") -> None:
    scene.blit(pixfont.render(text, color), x, y, center=False, glow=0)


def review_images(dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "img").mkdir(exist_ok=True)
    (dest / "anim").mkdir(exist_ok=True)
    (dest / "mock").mkdir(exist_ok=True)
    meta: dict = {"sprites": {}, "anims": {}, "palette": []}

    # Boards: rows of sprites rendered with glow, the way they look in the game.
    def board(name: str, items: list[tuple[str | None, Image.Image]], k: int, gap: int = 10, pad: int = 8,
              hud_piece: bool = False) -> None:
        labels = [pixfont.render(lbl, "hud_dim") if lbl else None for lbl, _ in items]
        label_h = 11 if any(labels) else 0
        slots = [max(img.width, t.width if t else 0) for (_, img), t in zip(items, labels)]
        w = sum(slots) + gap * (len(items) - 1) + pad * 2
        h = max(img.height for _, img in items) + pad * 2 + label_h
        sc = _stage(w, h, k)
        x = pad
        inner_h = h - pad * 2 - label_h
        for (_, img), t, slot in zip(items, labels, slots):
            sc.blit(img, x + (slot - img.width) // 2, pad + (inner_h - img.height) // 2, center=False, hud=hud_piece)
            if t:
                sc.blit(t, x + (slot - t.width) // 2, h - pad - 7, center=False, glow=0, hud=True)
            x += slot + gap
        sc.render().save(dest / "img" / f"{name}.png", optimize=True)
        meta["sprites"][name] = [w * k, h * k]

    board("player", [("SHIP", S.tight(S.player_ship())), ("SENTRY", S.tight(S.sentry())), ("DRILL", S.drill(0))], 6, gap=8)
    board("home_base", [(None, S.home_base(0))], 4)
    board("shots_player", [("AUTO", S.shot_auto()), ("SNIPER", S.shot_sniper()), ("MISSILE", S.missile_player(0))], 6, gap=8)
    board("weapon_icons", [(k_.upper(), hud.weapon_icon(k_)) for k_ in hud.WEAPON_ICONS], 4, gap=10)
    board("enemies", [("INFANTRY", S.infantry(0)), ("GUARD", S.guard(0)), ("RAMMING", S.guard(0, charging=True)),
                      ("RAPID", S.rapid_assault(0))], 5, gap=8)
    board("tank", [(None, S.tank(0))], 6)
    board("mothership", [(None, S.mothership(0))], 3)
    board("shots_enemy", [("ORB", S.shot_infantry(0)), ("NEEDLE", S.shot_rapid()), ("MISSILE", S.missile_enemy(0))], 6, gap=8)
    board("asteroids", [("14", S.asteroid(14, 102)), ("24", S.asteroid(24, 104, ore=2)),
                        ("48", S.asteroid(48, 106, ore=6)), ("96", S.asteroid(96, 4242, ore=16))], 3, gap=12)
    board("powerups", [(k_.upper(), S.powerup(k_)) for k_ in ("shield", "repair", "damage", "speed")], 4, gap=8)
    board("hud_console", [(None, hud.ship_console(shield=0.45, hull=0.82, armor_level=2))], 3, hud_piece=True)
    board("hud_console_low", [(None, hud.ship_console(shield=0.12, hull=0.34, armor_level=4, weapon="sniper", ammo=0.55,
                                                      others=("auto", "explosive", "laser"), low_hull=True))], 3, hud_piece=True)
    board("hud_radar", [(None, hud.radar([(14, -18, "enemy"), (17, -19, "enemy"), (20, -16, "enemy"), (24, 2, "enemy"),
                                          (30, -26, "boss"), (-30, 24, "base"), (-15, 4, "drill"), (-34, -8, "drill"),
                                          (-14, -9, "danger")]))], 3, hud_piece=True)
    top = Image.new("RGBA", (640, 40), pix.CLEAR)
    for img, x, y in hud.top_bar(alert="LASER CHARGING - CLEAR THE LANE"):
        top.alpha_composite(img, (x, y - 2))
    board("hud_top", [(None, top.crop(top.getbbox()))], 2, hud_piece=True)

    k = 4
    # Booster demo: each key in turn.
    frames = []
    for keys, label in ((("W",), "W  MAIN"), (("S",), "S  RETRO"), (("A",), "A  STRAFE LEFT"),
                        (("D",), "D  STRAFE RIGHT"), (("W", "A"), "W+A")):
        for f in range(6):
            sc = _stage(96, 56, k)
            body, flames = S.player_parts(keys, f)
            sc.blit(S._finish(body, "hull_outline", 0, flames), 48, 24)
            _label(sc, label, 48 - pixfont.text_width(label) // 2, 46)
            frames.append(sc.render())
    _gif(frames, dest / "anim" / "boosters.gif", 110)
    meta["anims"]["boosters"] = [96 * k, 56 * k]

    # Turning: crisp angles versus smooth rotation.
    crisp, smooth = [], []
    for i in range(48):
        ang = i * 7.5
        sc = _stage(48, 48, k)
        sc.blit(S.player_ship(ang, ("W",), i), 24, 24)
        crisp.append(sc.render())
        sc = _stage(48, 48, k)
        body, flames = S.player_parts(("W",), i)
        sc.blit_smooth(body, 24, 24, angle=ang, outline="hull_outline", overlay=flames)
        smooth.append(sc.render())
    _gif(crisp, dest / "anim" / "turn_crisp.gif", 70)
    _gif(smooth, dest / "anim" / "turn_smooth.gif", 70)
    meta["anims"]["turn_crisp"] = meta["anims"]["turn_smooth"] = [48 * k, 48 * k]

    # Enemies snapping between directions with hard turns (diagonals still to be hand-drawn).
    frames = []
    for i in range(16):
        ang = (i // 4) * 90
        sc = _stage(120, 48, k)
        for x, maker in ((20, S.infantry), (60, S.rapid_assault), (100, S.guard)):
            # Diagonals are machine-rotated stand-ins for now; final ones will be hand-drawn.
            sc.blit(maker(i % 2, angle=ang), x, 24)
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "enemy_turns.gif", 260)
    meta["anims"]["enemy_turns"] = [120 * k, 48 * k]

    # Explosions in the three owner colours.
    frames = []
    for f in list(range(6)) + [6, 6, 6]:
        sc = _stage(108, 40, k)
        for x, pal in ((18, "enemy"), (54, "danger"), (90, "player")):
            if f < 6:
                sc.blit(S.explosion(f, pal), x, 18)
        _label(sc, "ENEMY", 18 - pixfont.text_width("ENEMY") // 2, 32)
        _label(sc, "DANGER", 54 - pixfont.text_width("DANGER") // 2, 32)
        _label(sc, "YOURS", 90 - pixfont.text_width("YOURS") // 2, 32)
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "explosions.gif", [90] * 6 + [300, 120, 120])
    meta["anims"]["explosions"] = [108 * k, 40 * k]

    # Hits on the player: shield first, then armor.
    frames = []
    for f in range(10):
        sc = _stage(56, 48, k)
        sc.blit(S.player_ship(), 28, 26)
        if f < 4:
            sc.blit(S.shield_hit(f), 28, 26)
        elif 5 <= f < 8:
            sc.blit(S.armor_hit(f - 5), 32, 22)
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "hits.gif", [120] * 4 + [300] + [110] * 3 + [400, 200])
    meta["anims"]["hits"] = [56 * k, 48 * k]

    # Guard ram: warning lane, then the dash.
    frames = []
    for f in range(12):
        sc = _stage(48, 96, k)
        sc.blit(S.player_ship(), 24, 84)
        if f < 8:
            sc.blit(S.ram_warning(56, f), 24, 44)
            sc.blit(S.guard(f, charging=True, angle=180), 24, 10)
        else:
            y = 10 + (f - 7) * 16
            sc.blit(S.guard(f, charging=True, angle=180), 24, min(y, 66))
            if f == 11:
                sc.blit(S.armor_hit(0), 24, 76)
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "guard_ram.gif", [150] * 8 + [70, 70, 70, 600])
    meta["anims"]["guard_ram"] = [48 * k, 96 * k]

    # Mothership laser: charge, telegraph, fire.
    frames = []
    k2 = 3
    for f in range(14):
        sc = _stage(240, 300, k2)
        charge = min(1.0, f / 7) if f < 9 else 1.0
        ms = S.mothership(f, laser_charge=charge if f > 0 else 0.0)
        sc.blit(ms, 120, 82)
        ey = 82 - ms.height // 2 + 1 + 160 - 24
        if 0 < f < 9:
            lane = S.laser_warning(300 - ey - 12, f)
            sc.blit(lane, 120, ey + 12 + lane.height / 2, glow=0.6)
        elif f >= 9 and f < 13:
            beam = S.laser_beam(300 - ey - 6, f)
            sc.blit(beam, 120, ey + 6 + beam.height / 2)
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "mothership_laser.gif", [500] + [220] * 8 + [90] * 4 + [700])
    meta["anims"]["mothership_laser"] = [240 * k2, 300 * k2]

    # Friendly faction: powerups blinking and the safe zone edge crawling.
    frames = []
    for f in range(8):
        sc = _stage(150, 100, k)
        sc.blit(S.safe_zone(40, f), 44, 50, glow=0.5)
        for i, kind in enumerate(("shield", "repair", "damage", "speed")):
            sc.blit(S.powerup(kind, f + i), 104 + (i % 2) * 22, 34 + (i // 2) * 24 + (1 if (f + i) % 4 < 2 else 0))
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "friendly.gif", 160)
    meta["anims"]["friendly"] = [150 * k, 100 * k]

    # Mining: drill blinking on a rock.
    frames = []
    rock = S.asteroid(48, 106, ore=6)
    for f in range(4):
        sc = _stage(72, 64, k)
        sc.blit(rock, 36, 40)
        top_y = mockups.surface_y(rock, rock.width // 2)
        d = S.drill(f)
        sc.blit(d, 36, 40 - rock.height // 2 + top_y - d.height // 2 + 3)
        frames.append(sc.render())
    _gif(frames, dest / "anim" / "drill.gif", 400)
    meta["anims"]["drill"] = [72 * k, 64 * k]

    # Mock screenshots.
    for name, fn in (("defend_the_drill", mockups.defend_the_drill), ("mothership_assault", mockups.mothership_assault)):
        scene = fn()
        scene.render().save(dest / "mock" / f"{name}.png", optimize=True)
        scene.render(crt=True).save(dest / "mock" / f"{name}_crt.png", optimize=True)

    for group, blurb, names in ROLES:
        meta["palette"].append({"group": group, "blurb": blurb,
                                "colors": [{"name": n, "hex": hexcode(n)} for n in names]})
    (dest / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", type=Path)
    args = ap.parse_args()
    build_assets()
    if args.review:
        review_images(args.review)
        print("review images in", args.review)
