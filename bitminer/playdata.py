"""A record of how you fight, for the adaptive enemy AI to learn from in a later sprint.

Each sandbox fight writes one JSON-lines file in a `playdata` folder next to the settings file:
- a `start` line with the date and the game's settings,
- one line for each thing that matters as it happens: kills, hits you take, bumps, rams, waves,
  going down and coming back,
- a `sample` line every `sample_every` seconds: where you are and how you are flying, what you
  hold, your shield and hull, the enemies near you, and how many shots each side fired since the
  last sample,
- an `end` line with totals when you leave the fight.

Writing never gets in the way of the game: if the folder can't be written, logging just stops.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path

from .combat.specs import PLAYDATA

VERSION = 1
COUNTED = {"fire", "enemy_fire", "hit", "rock"}     # too many to log one by one: counted per sample
FLUSH_EVERY = 5.0


def _round(v):
    if isinstance(v, float):
        return round(v, 2) if math.isfinite(v) else None
    return v


class PlayLog:
    def __init__(self, folder: Path, meta: dict | None = None, spec: dict | None = None):
        self.spec = spec or PLAYDATA
        self.folder = Path(folder)
        self.path = self.folder / time.strftime("fight-%Y%m%d-%H%M%S.jsonl")
        self.ok = True
        self.lines: list[str] = []
        self.counts: Counter = Counter()
        self.totals: Counter = Counter()
        self.sample_in = 0.0
        self.flush_in = FLUSH_EVERY
        self.t = 0.0
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            n = 1
            while self.path.exists():
                n += 1
                self.path = self.folder / time.strftime(f"fight-%Y%m%d-%H%M%S-{n}.jsonl")
            self._prune()
        except OSError:
            self.ok = False
        self._line({"type": "start", "version": VERSION, "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    **(meta or {})})

    def _prune(self) -> None:
        keep = int(self.spec.get("keep", 40))
        old = sorted(self.folder.glob("fight-*.jsonl"))
        for f in old[: max(0, len(old) - (keep - 1))]:
            try:
                f.unlink()
            except OSError:
                pass

    def _line(self, data: dict) -> None:
        if self.ok:
            self.lines.append(json.dumps(data, separators=(",", ":")))

    def record(self, dt: float, events: list, sb) -> None:
        """Note this step's events, and take a sample when one is due."""
        if not self.ok:
            return
        self.t += dt
        t = round(self.t, 2)
        for ev in events:
            kind = ev[0]
            if kind in COUNTED:
                # fire_auto, enemy_fire_infantry, hit_sniper, rock_player ...
                self.counts[f"{kind}_{ev[1]}"] += 1
                if kind == "hit":
                    self.counts["damage_dealt"] = round(self.counts["damage_dealt"] + ev[3], 1)
                continue
            self.totals[kind] += 1
            self._line({"t": t, "type": kind, "data": [_round(v) for v in ev[1:]]})
        self.sample_in -= dt
        if self.sample_in <= 0:
            self.sample_in += float(self.spec.get("sample_every", 0.5))
            self._sample(t, sb)
        self.flush_in -= dt
        if self.flush_in <= 0:
            self.flush()

    def _sample(self, t: float, sb) -> None:
        st = sb.stage
        ship = st.ship
        W, H = st.world or (1.0, 1.0)
        near = Counter()
        nearest = None
        for e in st.enemies:
            if not e.alive or e.dying >= 0 or e.kind == "mothership":
                continue
            d = math.hypot(e.x - ship.x, e.y - ship.y)
            if d < 400:
                near[e.kind] += 1
            nearest = d if nearest is None else min(nearest, d)
        extra = sb.log_extra() if hasattr(sb, "log_extra") else {}
        self._line({
            "t": t, "type": "sample",
            "x": round(ship.x % W, 1), "y": round(ship.y % H, 1),
            "vx": round(ship.vx, 1), "vy": round(ship.vy, 1), "angle": round(ship.angle, 1),
            "shield": round(st.shield, 1), "hull": round(st.hull, 1), "down": st.ship_down,
            "weapon": sb.arsenal.weapon, "wave": sb.waves.number,
            "near": dict(near), "nearest": None if nearest is None else round(nearest, 1),
            "counts": dict(self.counts), **extra,
        })
        self.counts.clear()

    def flush(self) -> None:
        self.flush_in = FLUSH_EVERY
        if not self.ok or not self.lines:
            self.lines = []
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("\n".join(self.lines) + "\n")
        except OSError:
            self.ok = False
        self.lines = []

    def close(self, sb) -> None:
        self._line({"t": round(self.t, 2), "type": "end", "kills": sb.kills, "downs": sb.downs,
                    "waves": sb.waves.number, "totals": dict(self.totals)})
        self.flush()
