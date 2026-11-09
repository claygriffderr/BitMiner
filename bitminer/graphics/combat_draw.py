"""Draws a combat stage: enemy hulls, shots, missiles, beams, warnings, explosions and their glow.

Every picture comes from the approved art code (`art/sprites.py` and `art/effects.py`) and is
turned into a texture the first time it is needed, with its emissive twin for the light layer.

Each frame the stage is copied into four sprite layers the renderer draws in order:
- under: warning lanes on the ground, below everything
- hulls: enemy interiors, drawn into their own layer and outlined after rotating (like the ship)
- over: shots, missiles, beams, explosions, flares, debris, the shield bubble, health bars
- light: the glowing twin of all of it, at game resolution, for bloom
"""

from __future__ import annotations

import math

import arcade

from art import effects as E
from art import items as I
from art import sprites as S
from art.palette import rgba

from ..combat.stage import Stage
from ..combat import shapes
from ..flight import forward_vector
from .images import CANCEL_STEPS, CHARGE_STEPS, crumble_frames, laser_charge, light_twin, silhouette
from .textures import tex

LANE_STEP = 4            # lane and beam lengths are rounded to this many pixels, to share textures
ENEMY_FPS = 4            # blinking eyes and vents
MOTHERSHIP_FPS = 6
CHARGE_LEVELS = 4        # mothership laser charge picture steps
BAR_WIDTH = {"infantry": 14, "rapid": 12, "guard": 18, "tank": 26}
BAR_SHOW = 2.5           # seconds a health bar stays after a hit
DRILL_BAR = 13           # width of a drill's health bar
DRILL_STEPS = 8          # its gold bar fills in this many steps
DRILL_BAR_UP = 14        # the health bar sits this far above the drill's centre
TURRET_STEPS = 32        # a sentry turret's picture turns in this many steps
SENTRY_BAR_UP = 13       # its health bar sits this far above its centre
# How white a full hit flash turns each hull. Big hulls flash less, or steady fire would bleach them.
FLASH = {"tank": 0.6, "mothership": 0.2}


class Art:
    """Texture cache: each key builds a picture once, with its light twin (or None)."""

    def __init__(self) -> None:
        self._tex: dict = {}

    def get(self, key: tuple, build) -> tuple[arcade.Texture, arcade.Texture | None]:
        hit = self._tex.get(key)
        if hit is None:
            img = build()
            name = "c:" + "_".join(str(k) for k in key)
            glow = light_twin(img)
            hit = (tex(img, name), tex(glow, name + "_l") if glow is not None else None)
            self._tex[key] = hit
        return hit

    def plain(self, key: tuple, build) -> arcade.Texture:
        """A texture without a light twin (white silhouettes for the hit flash)."""
        hit = self._tex.get(key)
        if hit is None:
            hit = tex(build(), "c:" + "_".join(str(k) for k in key))
            self._tex[key] = hit
        return hit

    # ------------------------------------------------------------ hulls

    def hull(self, e, time: float):
        kind = e.kind
        if kind == "mothership":
            frame = int(e.clock * MOTHERSHIP_FPS) % 6
            level = int(round(e.charge * CHARGE_LEVELS))
            key = ("ms", frame, level)
            build = lambda: S.mothership(frame, level / CHARGE_LEVELS, outlined=False)
        else:
            frame = int(e.clock * ENEMY_FPS) % 2
            if kind == "infantry":
                key, build = ("inf", frame), lambda: S.infantry_interior(frame)
            elif kind == "rapid":
                key, build = ("rap", frame), lambda: S.rapid_assault_interior(frame)
            elif kind == "guard":
                key, build = ("grd", frame, e.ram), lambda: S.guard_interior(frame, e.ram)
            else:
                key, build = ("tnk", frame, e.pods_loaded), lambda: S.tank_interior(frame, e.pods_loaded)
        body, glow = self.get(key, build)
        flash = self.plain(key + ("flash",), lambda: silhouette(build()))
        return body, glow, flash


def snap(v: float, size: float, k: int) -> float:
    """Centre of a sprite `size` game pixels wide whose edge sits on a whole screen pixel."""
    return math.floor((v - size / 2) * k + 0.5) / k + size / 2


def snap_light(v: float, size: float) -> float:
    return math.floor(v - size / 2 + 0.5) + size / 2


class Pool:
    """A sprite list reused every frame: `begin`, then `add` what is visible, then `end`."""

    def __init__(self) -> None:
        self.list = arcade.SpriteList()
        self._sprites: list[arcade.Sprite] = []
        self._n = 0

    def begin(self) -> None:
        self._n = 0

    def add(self, texture: arcade.Texture, x: float, y: float, angle: float = 0.0, alpha: float = 1.0,
            color: tuple[int, int, int] = (255, 255, 255), size: tuple[float, float] | None = None) -> None:
        if self._n == len(self._sprites):
            s = arcade.Sprite(texture)
            self.list.append(s)
            self._sprites.append(s)
        s = self._sprites[self._n]
        self._n += 1
        if s.texture is not texture:
            s.texture = texture
        if size is None:
            s.size = (texture.width, texture.height)
        else:
            s.size = size
        s.position = (x, y)
        s.angle = angle
        s.color = (color[0], color[1], color[2], int(max(0.0, min(1.0, alpha)) * 255))
        s.visible = True

    def end(self) -> None:
        for s in self._sprites[self._n:]:
            if s.visible:
                s.visible = False

    def draw(self) -> None:
        self.list.draw(pixelated=True)


class StageDrawer:
    def __init__(self, pixel: arcade.Texture) -> None:
        self.art = Art()
        self.pixel = pixel
        self.under = Pool()
        self.hulls = Pool()
        self.over = Pool()
        self.light = Pool()
        self.bounds: tuple[float, float, float, float] | None = None   # hulls' world box
        self.k = 1
        self._crumbles: dict[int, list] = {}     # pictures of asteroids crumbling right now
        self._crumble_n = 0
        self._charges: dict[tuple, tuple] = {}   # the laser charge-up, built as it's first needed

    # ------------------------------------------------------------ placing sprites

    def _put(self, pool: Pool, pair, x: float, y: float, angle: float = 0.0, alpha: float = 1.0,
             light_alpha: float | None = None) -> None:
        body, glow = pair
        k = self.k
        w, h = body.width, body.height
        straight = angle % 90 == 0
        px = snap(x, w, k) if straight else x
        py = snap(y, h, k) if straight else y
        pool.add(body, px, py, angle, alpha)
        if glow is not None:
            la = alpha if light_alpha is None else light_alpha
            if la > 0:
                lx = snap_light(x, w) if straight else x
                ly = snap_light(y, h) if straight else y
                self.light.add(glow, lx, ly, angle, la)

    def _line(self, pool: Pool, x0, y0, x1, y1, color: str, alpha: float, glow: float) -> None:
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 0.5:
            return
        angle = -math.degrees(math.atan2(dy, dx))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        c = rgba(color)
        pool.add(self.pixel, cx, cy, angle, alpha, c[:3], (length, 1.0))
        if glow > 0:
            self.light.add(self.pixel, cx, cy, angle, alpha, tuple(int(v * glow) for v in c[:3]), (length, 1.0))

    # ------------------------------------------------------------ the frame

    def sync(self, stage: Stage, k: int, arena=None, arena_glow: float = 0.0) -> None:
        """`arena` is (left, bottom, right, top): a fence to draw as a dashed line, lit up by
        `arena_glow` (0 to 1) when something bumps it."""
        self.k = k
        t = stage.time
        A = self.art
        for pool in (self.under, self.hulls, self.over, self.light):
            pool.begin()
        flick = int(t * 30) % 2
        if arena is not None:
            self._fence(arena, arena_glow)

        # Warning lanes on the ground.
        for lane in stage.lanes:
            L = max(LANE_STEP, int(round(lane.length / LANE_STEP)) * LANE_STEP)
            fx, fy = forward_vector(lane.heading)
            cx, cy = lane.x + fx * L / 2, lane.y + fy * L / 2
            if lane.kind == "ram":
                frame = int(t * (24 if lane.locked else 10)) % 2     # flashes fast once it locks
                pair = A.get(("ramlane", L, frame), lambda: S.ram_warning(L, frame))
                self._put(self.under, pair, cx, cy, lane.heading)
            else:
                frame = int(t * (12 if lane.locked else 6)) % 2
                pair = A.get(("mslane", L, frame, lane.locked), lambda: S.laser_warning(L, frame, lane.locked))
                self._put(self.under, pair, cx, cy, lane.heading + 180)

        # Your base and mine rigs, on the ground under everything that flies.
        for st_ in stage.structures:
            if not st_.alive:
                continue
            if st_.kind == "base":
                frame = int(st_.clock * 2) % 2
                self._put(self.under, A.get(("base", frame), lambda f=frame: S.home_base(f)), st_.x, st_.y)
            elif st_.kind == "drill":
                self._drill(st_)
            elif st_.kind == "sentry":
                self._sentry(st_)

        # Your mines.
        for m in stage.mines:
            if m.state == "triggered":
                frame = int(m.clock * 20) % 2
            else:
                frame = int(m.clock * 4) % 4
            pair = A.get(("mine", m.state, frame), lambda s=m.state, f=frame: I.mine(f, s))
            self._put(self.under, pair, m.x, m.y)

        # Enemy hulls, with the hit flash, laser heat and warp-in on top.
        box = None
        for e in stage.enemies:
            if not e.alive:
                continue
            body, glow, flash = A.hull(e, t)
            angle = e.sprite_angle
            warp = e.fade_in < 1.0
            if warp and int(e.fade_in * 8) % 2 == 1:
                self.hulls.add(flash, e.x, e.y, angle, 1.0)
            else:
                self._put(self.hulls, (body, glow), e.x, e.y, angle, 1.0, light_alpha=1.0)
                white = max(e.flash * FLASH.get(e.kind, 0.85), 1.0 - e.fade_in if warp else 0.0)
                if white > 0.02:
                    self.hulls.add(flash, e.x, e.y, angle, white)
                if e.heat > 0.02 and e.kind != "mothership":
                    c = rgba("ion_hi")
                    self.hulls.add(flash, e.x, e.y, angle, e.heat * (0.18 + 0.12 * flick), c[:3])
            r = math.hypot(body.width, body.height) / 2 + 2
            b = (e.x - r, e.y - r, e.x + r, e.y + r)
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        self.bounds = box

        # Debris, rings, missiles, shots.
        for c in stage.chunks:
            fade = 1.0 - max(0.0, (c.t - c.life * 0.6) / (c.life * 0.4))
            pair = A.get(("chunk", c.kind, c.variant), lambda c=c: E.debris(c.kind, c.variant))
            self._put(self.over, pair, c.x, c.y, c.angle, fade)
        for r in stage.rings:
            rad = max(2, r.radius)
            tone = int(r.age * 5)
            pair = A.get(("ring", rad, r.owner, tone), lambda r=r, rad=rad, tone=tone: E.shockwave(rad, r.owner, tone / 5))
            self._put(self.over, pair, r.x, r.y)
        for m in stage.missiles:
            frame = int(m.clock * 20) % 2
            if m.style == "sentry":
                pair = A.get(("msls", frame), lambda f=frame: I.sentry_shot("missile", f))
            elif m.owner == "player":
                pair = A.get(("mslp", frame), lambda f=frame: S.missile_player(f))
            else:
                pair = A.get(("msle", frame), lambda f=frame: S.missile_enemy(f))
            self._put(self.over, pair, m.x, m.y, m.heading)
        for s in stage.shots:
            frame = int(s.clock * 16) % 2
            if s.kind == "auto":
                pair = A.get(("shot_auto",), S.shot_auto)
            elif s.kind == "sniper":
                pair = A.get(("shot_sniper",), S.shot_sniper)
            elif s.kind in ("sentry_auto", "sentry_sniper"):
                gun = s.kind[7:]
                pair = A.get(("shot_s", gun), lambda g=gun: I.sentry_shot(g))
            elif s.kind == "infantry":
                pair = A.get(("shot_inf", frame), lambda f=frame: S.shot_infantry(f))
            else:
                pair = A.get(("shot_rapid",), S.shot_rapid)
            self._put(self.over, pair, s.x, s.y, s.heading)
        for st_ in stage.streaks:
            a = 1.0 - st_.t / st_.life
            self._line(self.over, st_.x0, st_.y0, st_.x1, st_.y1, "ion_white" if a > 0.5 else "ion_hi", a, 0.8)

        # Beams.
        for b in stage.beams:
            fx, fy = forward_vector(b.heading)
            if b.owner == "player":
                # Cut short where a rock stops it.
                L = int(round(b.length)) if b.reach >= b.length else max(2 * LANE_STEP, int(round(b.reach / LANE_STEP)) * LANE_STEP)
                frame = int(t * 30) % 2
                pair = A.get(("lsr", L, frame), lambda L=L, f=frame: S.laser_player(L, f))
                if b.burst > 0 and b.t - b.warmup < b.burst:
                    # The charged laser opens extra wide, then settles to its usual width.
                    bf = 0 if b.t - b.warmup < b.burst / 2 else 1
                    pair = A.get(("lsrb", L, bf), lambda L=L, f=bf: I.laser_burst(L, f))
                cx, cy = b.x + fx * L / 2, b.y + fy * L / 2
                if b.firing:
                    self._put(self.over, pair, cx, cy, b.heading)
                    for (x, y) in b.contacts.values():
                        self._put(self.over, A.get(("bc", "player", frame), lambda f=frame: E.beam_contact("player", f)), x, y)
                elif b.t < b.warmup:
                    charge = b.t / max(0.01, b.warmup)
                    self._put(self.over, pair, cx, cy, b.heading, alpha=(0.15 + 0.3 * charge) * (0.6 + 0.4 * flick))
                    pip = A.get(("muz", "sniper", 1), lambda: E.muzzle_flash("sniper", 1))
                    self._put(self.over, pip, b.x, b.y, b.heading)
            else:
                L = max(LANE_STEP, int(round(math.hypot(b.end[0] - b.x, b.end[1] - b.y) / LANE_STEP)) * LANE_STEP)
                frame = int(t * 30) % 2
                pair = A.get(("msbeam", L, frame), lambda L=L, f=frame: S.laser_beam(L, f))
                self._put(self.over, pair, b.x + fx * L / 2, b.y + fy * L / 2, b.heading + 180)
                for (x, y) in b.contacts.values():
                    self._put(self.over, A.get(("bc", "danger", frame), lambda f=frame: E.beam_contact("danger", f)), x, y)

        # Frame animations: explosions, flares, muzzle flashes, shield and armor hits.
        for a in stage.anims:
            if not a.started:
                continue
            f = a.frame
            name = a.name
            angle = 0.0
            if name == "explosion":
                pal, size, seed = a.params
                pair = A.get(("exp", pal, size, seed, f), lambda: S.explosion(f, pal, size, seed))
            elif name == "flare":
                owner = a.params[0]
                pair = A.get(("flare", owner, f % 2), lambda: E.flare(owner, f % 2))
            elif name == "muzzle":
                kind = a.params[0]
                pair = A.get(("muz", kind, f % 2), lambda: E.muzzle_flash(kind, f % 2))
                angle = a.angle
            elif name == "shield_hit":
                pair = A.get(("shit", f), lambda: S.shield_hit(f))
                angle = a.angle
            elif name == "shield_break":
                rad = int(stage.shield_radius)
                pair = A.get(("sbrk", rad, f), lambda: E.shield_break(rad, f))
            elif name == "armor_hit":
                pair = A.get(("ahit", f), lambda: S.armor_hit(f))
            elif name == "mine_blast":
                rad = a.params[0]
                pair = A.get(("mblast", rad, f), lambda: I.mine_blast(f, rad))
            elif name == "glint":
                pair = A.get(("glint", f % 2), lambda: S.glint(f % 2))
            elif name == "crumble":
                pair = self._crumble(a, f)
                if pair is None:
                    continue
                self._put(self.under, pair, a.x, a.y)
                continue
            else:
                continue
            self._put(self.over, pair, a.x, a.y, angle)

        # The shield bubble, for a moment after each hit.
        ship = stage.ship
        if stage.ship_visible and stage.shield > 0 and stage.shield_show > 0:
            rad = int(stage.shield_radius)
            frame = int(t * 14) % 5
            lv = stage.shield_level
            pair = A.get(("bubble", lv, rad, frame), lambda: I.shield_bubble(lv, rad, frame))
            self._put(self.over, pair, ship.x, ship.y, alpha=min(1.0, stage.shield_show * 3))

        # Health bars over damaged enemies (the mothership's is in the HUD).
        for e in stage.enemies:
            if e.kind == "mothership" or not e.targetable or e.health >= e.max_health or e.since_hit > BAR_SHOW:
                continue
            w = BAR_WIDTH[e.kind]
            fill = int(round((w - 2) * e.health / e.max_health))
            pair = A.get(("hbar", w, fill), lambda w=w, fill=fill: E.health_bar(w, fill / (w - 2)))
            top = shapes.radius_of(e.mask) * 0.75 + 4
            fade = min(1.0, (BAR_SHOW - e.since_hit) / 0.4)
            self._put(self.over, pair, e.x, e.y + top, alpha=fade)

        self._charge(stage)
        live = {id(a) for a in stage.anims if a.name == "crumble"}
        for key in [k for k in self._crumbles if k not in live]:
            del self._crumbles[key]         # let its pictures go once it has played
        for pool in (self.under, self.hulls, self.over, self.light):
            pool.end()

    # ------------------------------------------------------------ your drills and asteroids

    def _drill(self, d) -> None:
        """A drill standing on its asteroid, its gold bar showing how full its hold is, and its health
        bar above it."""
        A = self.art
        fill = d.hold / max(1.0, d.hold_max)
        steps = 0 if fill <= 0 else max(1, int(round(fill * DRILL_STEPS)))
        full = steps >= DRILL_STEPS and fill >= 0.999
        frame = int(d.clock * (2.5 if full else 3)) % 2 if (d.working or full) else 1
        share = 1.0 if full else steps / DRILL_STEPS
        if not full and share >= 1.0:
            share = (DRILL_STEPS - 0.6) / DRILL_STEPS    # nearly full still looks like it's digging
        key = ("drill", steps, full, frame)
        build = lambda s=share, f=frame: I.drill(s, f)
        self._put(self.under, A.get(key, build), d.x, d.y, d.side)
        if d.flash > 0.02:
            white = A.plain(key + ("flash",), lambda b=build: silhouette(b()))
            self.under.add(white, d.x, d.y, d.side, d.flash * 0.8)
        health = d.health / max(1.0, d.max_health)
        hk = int(round(health * (DRILL_BAR - 2)))
        bar = A.get(("dbar", hk), lambda: I.struct_bar(DRILL_BAR, hk / (DRILL_BAR - 2)))
        self._put(self.over, bar, d.x, d.y + DRILL_BAR_UP, light_alpha=0.3)

    def _sentry(self, s) -> None:
        """A sentry: its platform, the turret turned toward its target, and its health bar."""
        A = self.art
        frame = int(s.clock * 2) % 2
        base_key = ("sbase", s.tier, frame)
        base_build = lambda t=s.tier, f=frame: I.sentry_base(t, f)
        self._put(self.under, A.get(base_key, base_build), s.x, s.y)
        step = int(round(s.angle / 360 * TURRET_STEPS)) % TURRET_STEPS
        firing = s.fired < 0.08
        loaded = s.loaded if s.gun == "missile" else 4
        key = ("turret", s.gun, step, firing, loaded)
        build = lambda g=s.gun, a=step * 360 / TURRET_STEPS, f=firing, n=loaded: \
            S._finish(I.turret_interior(g, f, n), I.OUTLINE, a)
        self._put(self.under, A.get(key, build), s.x, s.y)
        if s.flash > 0.02:
            self.under.add(A.plain(base_key + ("flash",), lambda b=base_build: silhouette(b())), s.x, s.y, 0.0,
                           s.flash * 0.8)
            self.under.add(A.plain(key + ("flash",), lambda b=build: silhouette(b())), s.x, s.y, 0.0, s.flash * 0.8)
        w = I.SENTRY_HEALTH_BAR[s.tier]
        hk = int(round(s.health / max(1.0, s.max_health) * (w - 2)))
        bar = A.get(("sbar", w, hk), lambda w=w, hk=hk: I.struct_bar(w, hk / (w - 2)))
        self._put(self.over, bar, s.x, s.y + SENTRY_BAR_UP, light_alpha=0.3)

    def _crumble(self, a, f: int):
        """The frames of an asteroid crumbling away, built when it starts."""
        frames = self._crumbles.get(id(a))
        if frames is None:
            size, variant, ore, wear, sites, seed = a.params
            pics = crumble_frames(size, variant, ore, wear, sites, seed, a.frames)
            self._crumble_n += 1
            frames = []
            for j, img in enumerate(pics):
                name = f"crumble{self._crumble_n}_{j}"
                glow = light_twin(img)
                frames.append((tex(img, name), tex(glow, name + "_l") if glow is not None else None))
            self._crumbles[id(a)] = frames
        return frames[min(f, len(frames) - 1)] if frames else None

    # ------------------------------------------------------------ the laser charge-up

    def _charge(self, stage: Stage) -> None:
        """Energy drawn in to the ship's nose while the laser charges, or scattering when you let go."""
        if not stage.ship_visible:
            return
        if stage.charging >= 0:
            step = min(CHARGE_STEPS - 1, int(stage.charging * CHARGE_STEPS))
            key = ("charge", step)
            build = lambda s=step: laser_charge(s)
        elif stage.charge_cancel > 0:
            step = min(CANCEL_STEPS - 1, int((1.0 - stage.charge_cancel) * CANCEL_STEPS))
            key = ("charge_x", step)
            build = lambda s=step: laser_charge(0, cancel=s)
        else:
            return
        pair = self._charges.get(key)
        if pair is None:
            img, glow = build()
            name = "c:" + "_".join(str(k) for k in key)
            pair = self._charges[key] = (tex(img, name), tex(glow, name + "_l") if glow is not None else None)
        ship = stage.ship
        self._put(self.over, pair, ship.x, ship.y, ship.angle)

    def _fence(self, arena, glow: float) -> None:
        """A dashed line round the edge of the gallery's free-fly space, one game pixel wide."""
        left, bottom, right, top = (int(round(v)) for v in arena)
        lit = glow > 0.02
        c = rgba("ion_hi" if lit else "console_edge")[:3]
        alpha = 0.35 + 0.65 * glow if lit else 0.35
        dash, gap = 6, 6

        def put(cx: float, cy: float, size: tuple[float, float]) -> None:
            self.under.add(self.pixel, cx, cy, 0.0, alpha, c, size)
            if lit:
                self.light.add(self.pixel, cx, cy, 0.0, glow, c, size)
        for x in range(left, right, dash + gap):
            n = min(dash, right - x)
            put(x + n / 2, bottom + 0.5, (n, 1.0))
            put(x + n / 2, top + 0.5, (n, 1.0))
        for y in range(bottom, top, dash + gap):
            n = min(dash, top - y)
            put(left + 0.5, y + n / 2, (1.0, n))
            put(right + 0.5, y + n / 2, (1.0, n))

    def hull_rect(self, cam_x: float, cam_y: float, k: int, size: tuple[int, int]):
        """The hulls' box on the scene texture, in screen pixels, or None."""
        if self.bounds is None:
            return None
        W, H = size
        x0, y0, x1, y1 = self.bounds
        left = max(0, int(math.floor((x0 - cam_x) * k + W / 2)) - k - 1)
        bottom = max(0, int(math.floor((y0 - cam_y) * k + H / 2)) - k - 1)
        right = min(W, int(math.ceil((x1 - cam_x) * k + W / 2)) + k + 1)
        top = min(H, int(math.ceil((y1 - cam_y) * k + H / 2)) + k + 1)
        if right <= left or top <= bottom:
            return None
        return left, bottom, right - left, top - bottom

