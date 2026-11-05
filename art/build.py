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
    c["guard_ram_deploy"] = strip([S.guard(0, ram=r) for r in (1, 2, 3)])
    c["guard_ram"] = strip([S.guard(f, ram=3) for f in range(2)])
    c["glint"] = strip([S.glint(f) for f in range(2)])
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
    c["laser_warning_locked"] = strip([S.laser_warning(120, f, locked=True) for f in range(2)])
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
    board("enemies", [("INFANTRY", S.infantry(0)), ("GUARD", S.guard(0)), ("RAMMING", S.tight(S.guard(0, ram=3))),
                      ("RAPID", S.rapid_assault(0))], 5, gap=8)
    board("guard_scoop", [("IDLE", S.guard(0)), ("FOLD", S.tight(S.guard(0, ram=1))),
                          ("SWING", S.tight(S.guard(0, ram=2))), ("RAM", S.tight(S.guard(0, ram=3)))], 4, gap=8)
    board("tank", [(None, S.tank(0))], 6)
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
    board("hud_boss", [(None, hud.boss_bar(health=0.58, recent=0.05))], 3, hud_piece=True)
    for img, x, y in hud.top_bar(alert="LASER LOCKED - CLEAR THE LANE"):
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

    # Turning: smooth rotation, so the ship points exactly at the mouse.
    smooth = []
    for i in range(48):
        ang = i * 7.5
        sc = _stage(48, 48, k)
        body, flames = S.player_parts(("W",), i)
        sc.blit_smooth(body, 24, 24, angle=ang, outline="hull_outline", overlay=flames)
        smooth.append(sc.render())
    _gif(smooth, dest / "anim" / "turn_smooth.gif", 70)
    meta["anims"]["turn_smooth"] = [48 * k, 48 * k]

    # Enemies snapping between eight directions. Diagonals are turned like the player's ship.
    frames = []
    for i in range(16):
        ang = (i // 2) * 45
        sc = _stage(120, 48, k)
        for x, maker in ((20, S.infantry_interior), (60, S.rapid_assault_interior), (100, S.guard_interior)):
            sc.blit_smooth(maker(i % 2), x, 24, angle=ang, outline=S.ENEMY_OUTLINE)
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

    # Guard ram: the steel scoop slides out, the lane flashes, then the dash.
    frames, times = [], []
    gx, gy, player_y = 24, 16, 92
    reach = S.scoop_reach()
    hit_y = player_y - 9

    def ram_frame(ram: int, f: int, y: float, lane: bool = False, sparkle: int | None = None, hit: bool = False):
        sc = _stage(48, 104, k)
        sc.blit(S.player_ship(), gx, player_y)
        if lane:
            mockups.ram_lane(sc, (gx, y + reach), (gx, hit_y), frame=f)
        sc.blit(S.guard(f, ram=ram, angle=180), gx, y)
        if sparkle is not None:
            sc.blit(S.glint(sparkle), gx - 8, y + reach - 1, glow=0)
        if hit:
            sc.blit(S.armor_hit(0), gx, hit_y + 2)
        return sc.render()

    for f in range(2):
        frames.append(ram_frame(0, f, gy)); times.append(260)
    for r in (1, 2):
        frames.append(ram_frame(r, 0, gy)); times.append(110)
    frames.append(ram_frame(3, 0, gy, sparkle=0)); times.append(110)
    frames.append(ram_frame(3, 1, gy, sparkle=1)); times.append(110)
    for f in range(6):
        frames.append(ram_frame(3, f, gy, lane=True)); times.append(140)
    for j in (1, 2, 3):
        y = min(gy + 18 * j, hit_y - reach)
        frames.append(ram_frame(3, j, y, hit=(j == 3))); times.append(70 if j < 3 else 600)
    _gif(frames, dest / "anim" / "guard_ram.gif", times)
    meta["anims"]["guard_ram"] = [48 * k, 104 * k]

    # Mothership laser: it turns to track you while charging, freezes once locked, then fires.
    frames, times = [], []
    k2, W2, H2 = 2, 320, 320
    center, py = (160, 92), 292
    turn_rate = 2.6

    def ease(t: float) -> float:
        return t * t * (3 - 2 * t)

    def laser_frame(f: int, ang: float, px: float, keys: tuple[str, ...], charge: float, state: str | None):
        sc = _stage(W2, H2, k2)
        sc.blit_smooth(S.mothership(f, laser_charge=charge, outlined=False), *center, angle=ang,
                       outline=S.ENEMY_OUTLINE)
        if state in ("tracking", "locked"):
            mockups.laser_lane(sc, center, ang, 300, f, locked=(state == "locked"))
        elif state == "firing":
            mockups.laser_lane(sc, center, ang, 300, f, firing=True)
        body, flames = S.player_parts(keys, f)
        sc.blit_smooth(body, px, py, angle=mockups.heading((px, py), center), outline="hull_outline", overlay=flames)
        if state:
            label = {"tracking": "TRACKING YOU", "locked": "LOCKED - MOVE", "firing": "FIRING"}[state]
            _label(sc, label, 6, H2 - 11, "hud_dim" if state == "tracking" else "danger_pink_hi")
        return sc.render()

    def follow(ang: float, px: float) -> float:
        want = mockups.aim_mothership(center, (px, py), ang)
        return ang + max(-turn_rate, min(turn_rate, want - ang))

    px = 92.0
    ang = mockups.aim_mothership(center, (px, py))
    for f in range(2):
        frames.append(laser_frame(f, ang, px, (), 0.0, None)); times.append(300)
    for i in range(16):
        px = 92 + 120 * ease(min(1.0, i / 12))
        ang = follow(ang, px)
        keys = ("D",) if i < 9 else (("A",) if i < 12 else ())
        frames.append(laser_frame(i, ang, px, keys, (i + 1) / 16, "tracking")); times.append(110)
    for j in range(8):
        if j >= 2:
            px = 212 - 56 * ease((j - 2) / 5)
        keys = ("A",) if 2 <= j < 6 else (("D",) if j >= 6 else ())
        frames.append(laser_frame(j, ang, px, keys, 1.0, "locked")); times.append(100)
    for j in range(5):
        px -= 1.5
        frames.append(laser_frame(j, ang, px, (), 1.0, "firing")); times.append(80)
    for j in range(3):
        ang = follow(ang, px)
        frames.append(laser_frame(j, ang, px, (), 0.0, None)); times.append(150 if j < 2 else 700)
    _gif(frames, dest / "anim" / "mothership_laser.gif", times)
    meta["anims"]["mothership_laser"] = [W2 * k2, H2 * k2]

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
