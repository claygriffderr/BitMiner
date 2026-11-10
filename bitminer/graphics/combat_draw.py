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
from art import haul as HL
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
RING_FRAMES = 6          # the collector ring's running lights chase round in this many pictures
RING_FPS = 2
RING_HEALTH_STEPS = 7    # its battle damage shows in this many steps
RING_BAR = 64            # width of its health bar, which sits over its top mount
RING_BAR_UP = HL.PAD_R + HL.PAD_HALF + 8
PULSE_TONES = ("ore_hi", "ore", "ore", "ore_dark", "ore_dark")
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

    def drop(self, keep) -> None:
        """Let go of cached pictures whose key fails `keep(key)` (big ones no longer shown)."""
        for key in [k for k in self._tex if not keep(k)]:
            del self._tex[key]

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
        self._ring_key = None                    # (ring, damage step) the ring's pictures are kept for

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

    def _line(self, pool: Pool, x0, y0, x1, y1, color: str, alpha: float, glow: float, width: float = 1.0) -> None:
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 0.5:
            return
        angle = -math.degrees(math.atan2(dy, dx))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        c = rgba(color)
        pool.add(self.pixel, cx, cy, angle, alpha, c[:3], (length, width))
        if glow > 0:
            self.light.add(self.pixel, cx, cy, angle, alpha, tuple(int(v * glow) for v in c[:3]), (length, width))

    def _dot(self, pool: Pool, x: float, y: float, color: str, size: float = 1.0, glow: float = 0.0,
             alpha: float = 1.0) -> None:
        c = rgba(color)[:3]
        px, py = math.floor(x) + 0.5 * size, math.floor(y) + 0.5 * size
        pool.add(self.pixel, px, py, 0.0, alpha, c, (size, size))
        if glow > 0:
            self.light.add(self.pixel, px, py, 0.0, alpha, tuple(int(v * glow) for v in c), (size, size))

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

        # The lasso's beam, the ring's field, thrown rocks and loose drills, under the structures.
        haul = getattr(stage, "haul", None)
        if haul is not None:
            self._haul_under(stage, haul, t)

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
            elif st_.kind == "ring":
                self._ring(st_)

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

        if haul is not None:
            self._haul_over(stage, haul, t)
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
        """A sentry: its platform, the turret turned toward its target, and its health bar. A sentry
        mounted on the collector ring is just its turret: the ring is its platform and its health."""
        A = self.art
        mounted = s.host is not None
        frame = int(s.clock * 2) % 2
        base_key = ("sbase", s.tier, frame)
        base_build = lambda t=s.tier, f=frame: I.sentry_base(t, f)
        if not mounted:
            self._put(self.under, A.get(base_key, base_build), s.x, s.y)
        step = int(round(s.angle / 360 * TURRET_STEPS)) % TURRET_STEPS
        firing = s.fired < 0.08
        loaded = s.loaded if s.gun == "missile" else 4
        key = ("turret", s.gun, step, firing, loaded)
        build = lambda g=s.gun, a=step * 360 / TURRET_STEPS, f=firing, n=loaded: \
            S._finish(I.turret_interior(g, f, n), I.OUTLINE, a)
        self._put(self.under, A.get(key, build), s.x, s.y)
        if s.flash > 0.02:
            if not mounted:
                self.under.add(A.plain(base_key + ("flash",), lambda b=base_build: silhouette(b())), s.x, s.y, 0.0,
                               s.flash * 0.8)
            self.under.add(A.plain(key + ("flash",), lambda b=build: silhouette(b())), s.x, s.y, 0.0, s.flash * 0.8)
        if mounted:
            return
        w = I.SENTRY_HEALTH_BAR[s.tier]
        hk = int(round(s.health / max(1.0, s.max_health) * (w - 2)))
        bar = A.get(("sbar", w, hk), lambda w=w, hk=hk: I.struct_bar(w, hk / (w - 2)))
        self._put(self.over, bar, s.x, s.y + SENTRY_BAR_UP, light_alpha=0.3)

    # ------------------------------------------------------------ hauling: the lasso and the ring

    def _ring(self, ring) -> None:
        """The collector ring: its hoop with the running lights, battle damage as it wears down,
        collector nodes that light gold as drills sell, gold flying in, and its health bar."""
        A = self.art
        frame = int(ring.clock * RING_FPS) % RING_FRAMES
        hstep = int(math.ceil(ring.health / max(1.0, ring.max_health) * RING_HEALTH_STEPS - 1e-6))
        key = ("ringb", ring.uid, hstep, frame)
        if self._ring_key != (ring.uid, hstep):
            # Only the pictures for how hurt it is now are kept: each is a big texture.
            self._ring_key = (ring.uid, hstep)
            A.drop(lambda k: k[0] != "ringb" or k[1:3] == (ring.uid, hstep))
        build = lambda f=frame, h=hstep / RING_HEALTH_STEPS, u=ring.uid: HL.collector_ring(f, h, (), seed=u % 7 + 3)
        self._put(self.under, A.get(key, build), ring.x, ring.y)
        for n, lit in enumerate(ring.lit):
            if lit > 0:
                nx, ny = ring.node_point(n)
                self._dot(self.under, nx - 1, ny - 1, "ore_hi", 3.0, 1.0, min(1.0, lit * 3))
        for dx, dy, n, tt, _ in ring.pulses:
            x0, y0 = ring.x + dx, ring.y + dy
            x1, y1 = ring.node_point(n)
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + 10        # a slight arc, so it reads as flying
            for j, tone in enumerate(PULSE_TONES):
                u = tt - j * 0.04
                if 0 <= u <= 1:
                    x = (1 - u) ** 2 * x0 + 2 * (1 - u) * u * mx + u ** 2 * x1
                    y = (1 - u) ** 2 * y0 + 2 * (1 - u) * u * my + u ** 2 * y1
                    self._dot(self.over, x, y, tone, 1.0, 1.0 if j == 0 else 0.6)
        health = ring.health / max(1.0, ring.max_health)
        hk = int(round(health * (RING_BAR - 2)))
        bar = A.get(("rbar", hk), lambda: I.struct_bar(RING_BAR, hk / (RING_BAR - 2)))
        self._put(self.over, bar, ring.x, ring.y + RING_BAR_UP, light_alpha=0.3)

    def _haul_under(self, stage, haul, t: float) -> None:
        A = self.art
        f = stage.field
        ring = haul.ring if haul.has_ring() else None
        if ring is not None:
            frame = int(t * 6) % 8
            self._put(self.under, A.get(("ringf", frame), lambda fr=frame: HL.ring_field(fr)), ring.x, ring.y,
                      light_alpha=0.6)
            hold_f = int(t * 8) % 15
            for i in ring.slots:
                if i < 0 or f.gone[i]:
                    continue
                size = int(f.size[i])
                x, y = haul.rock_pos(i)
                self._put(self.under, A.get(("rhold", size, hold_f), lambda s=size, fr=hold_f: HL.rock_hold(s, fr)),
                          x, y, light_alpha=0.5)
        # Speed lines behind asteroids fast enough to hurt.
        for i, strength in haul.fast_rocks():
            x, y = haul.rock_pos(i)
            vx, vy = float(f.vx[i]), float(f.vy[i])
            sp = math.hypot(vx, vy)
            ux, uy = vx / sp, vy / sp
            nx, ny = -uy, ux
            rad = float(f.size[i]) / 2
            length = 6 + 14 * strength
            for off, tone in ((-0.55, "rock_rim"), (0.0, "star_mid"), (0.55, "rock_rim")):
                sx = x - ux * (rad + 1) + nx * off * rad
                sy = y - uy * (rad + 1) + ny * off * rad
                ln = length * (1.0 if off == 0 else 0.7)
                self._line(self.under, sx, sy, sx - ux * ln, sy - uy * ln, tone, 0.9, 0.0)
        # The tow beam and the grip round the rock it holds.
        if haul.rock >= 0 and not f.gone[haul.rock] and stage.ship_visible:
            i = haul.rock
            size = int(f.size[i])
            x0, y0 = haul.tail()
            rx, ry = haul.rock_pos(i)
            d = math.hypot(rx - x0, ry - y0)
            if d > size / 2 + 1:
                ux, uy = (rx - x0) / d, (ry - y0) / d
                x1, y1 = rx - ux * (size / 2 + 1), ry - uy * (size / 2 + 1)
                self._beam(x0, y0, x1, y1, max(1, haul.level), t)
            closing = round(haul.latch * 4) / 4
            gf = int(t * 12) % 6
            pair = A.get(("grip", size, closing, gf), lambda s=size, fr=gf, c=closing: HL.grip(s, fr, c))
            self._put(self.under, pair, rx, ry, light_alpha=0.8)
        # The ring's outline while you hold T: cyan where it fits, pink where it doesn't.
        if haul.placing and stage.ship_visible:
            frame = int(t * 10) % 8
            ok = not haul.room
            pair = A.get(("ghost", ok, frame), lambda o=ok, fr=frame: HL.placement_ghost(o, fr))
            self._put(self.under, pair, stage.ship.x, stage.ship.y, light_alpha=0.7)
        # Drills floating free: they turn slowly and blink so you can find them.
        for ld in stage.loose:
            step = int(round(ld.angle / 360 * TURRET_STEPS)) % TURRET_STEPS
            key = ("loose", step)
            build = lambda a=step * 360 / TURRET_STEPS: S._finish(I.drill_interior(0.0, 1), I.OUTLINE, a)
            self._put(self.under, A.get(key, build), ld.x, ld.y)
            if int(ld.clock * 3) % 2 == 0:
                self._dot(self.over, ld.x - 1, ld.y - 1, "ion_hi", 2.0, 1.0)

    def _beam(self, x0: float, y0: float, x1: float, y1: float, level: int, t: float) -> None:
        """The steady tow beam: a dark cyan sheath, a bright core, and pulses running down it
        toward the ship. Thicker at each level."""
        w = HL.BEAM_LEVEL_WIDTH.get(level, 1)
        self._line(self.under, x0, y0, x1, y1, "ion_dark", 1.0, 0.5, width=w + 1.0)
        if w >= 2:
            self._line(self.under, x0, y0, x1, y1, "ion", 1.0, 0.8, width=w - 0.5)
        self._line(self.under, x0, y0, x1, y1, "ion_hi", 1.0, 1.0, width=1.0)
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 2:
            return
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        gap = 14.0
        shift = (t * 60.0) % gap
        k = 0.0
        while k * gap + shift <= length:
            along = length - (k * gap + shift)           # running from the rock toward the ship
            self._dot(self.under, x0 + ux * along, y0 + uy * along, "ion_white", 1.0 if w < 2 else 2.0, 1.0)
            k += 1
        self._dot(self.under, x0, y0, "ion_white", 1.0, 1.0)

    def _haul_over(self, stage, haul, t: float) -> None:
        """Brackets round the asteroid Q would grab: bright if your lasso can tow it, grey if not."""
        if not stage.ship_visible:
            return
        target = haul.target()
        if target is None:
            return
        i, ok = target
        size = int(stage.field.size[i])
        x, y = haul.rock_pos(i)
        frame = int(t * 3) % 2
        pair = self.art.get(("brk", size, ok, frame), lambda s=size, o=ok, fr=frame: HL.target_brackets(s, o, fr))
        self._put(self.over, pair, x, y, light_alpha=0.6 if ok else 0.0)

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

