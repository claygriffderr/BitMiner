"""One whole game played by the bot, and what it measured.

`play` returns plain numbers and lists (so a run can be saved as JSON and sent between processes):
credits earned each minute split into mining and combat, when each thing was bought, how much of each
wave was killed, when the ship went down, how many enemies were out, what each step cost, and the
pacing marks worked out from those.
"""

from __future__ import annotations

import time as clock

from ..combat.campaign import Campaign
from ..selftest import Quiet
from ..settings import Tuning
from . import load_spec
from .bot import Bot

MASSIVE_FROM = 30         # the first massive wave (the pacing guide's deaths mark counts up to it)


def play(seed: int = 1, preset: str = "motivated", minutes: float | None = None, spec: dict | None = None,
         trace: bool = False, scale: float | None = None) -> dict:
    """Play one game for `minutes` game minutes and return its numbers."""
    spec = spec or load_spec()
    minutes = float(spec["minutes"] if minutes is None else minutes)
    rate = int(spec["step_rate"])
    dt = 1.0 / rate
    game = Campaign(Quiet(), Quiet(), Tuning(), scale=scale, seed=seed)
    bot = Bot(game, spec["presets"][preset], spec["plan"], spec["bot"], seed=seed)
    if trace:
        bot.trace = []
    st = game.stage
    slots = max(1, int(minutes + 0.999))
    mining = [0.0] * slots
    combat = [0.0] * slots
    out = [0] * slots               # the most enemies out at once in each minute
    balance = [0] * slots           # credits in hand at the end of each minute
    purchases: list[dict] = []
    waves: list[dict] = []
    deaths: list[float] = []
    kills: dict[str, int] = {}
    members: dict[int, tuple] = {}  # enemy uid -> (enemy, wave record)
    seen: set[int] = {game.mothership.uid}
    current: dict | None = None
    events: list = []
    steps = int(round(minutes * 60 * rate))
    worst = 0.0                     # the slowest second of play, in ms a step
    most = 0                        # the most enemies out at once
    most_ms = 0.0                   # what a step cost during that second
    sec_cost = 0.0
    sec_most = 0
    began = clock.perf_counter()
    for n in range(steps):
        t0 = clock.perf_counter()
        act = bot.act(dt, events)
        events = game.step(dt, act.controls, act.trigger, act.cursor, set_drill=act.set_drill, boost=act.boost,
                           lay_mines=act.lay_mines, place_sentry=act.place_sentry, lasso=act.lasso,
                           ring_key=act.ring_key)
        sec_cost += clock.perf_counter() - t0
        m = min(slots - 1, int(game.time / 60.0))
        for ev in events:
            kind = ev[0]
            if kind == "unload":
                mining[m] += ev[2]
            elif kind == "ring_sale":
                mining[m] += ev[1]
            elif kind == "bounty":
                combat[m] += ev[2]
                kills[ev[1]] = kills.get(ev[1], 0) + 1
            elif kind == "bought":
                p = {"t": round(game.time, 1), "key": ev[1], "price": ev[2]}
                if len(ev) > 3 and ev[3] is not None:
                    p["step"] = ev[3]           # an upgrade's new level, or a sentry's tier
                purchases.append(p)
            elif kind == "wave":
                current = {"n": ev[1], "name": ev[2], "t": round(game.time, 1), "size": 0, "killed": 0,
                           "home": 0, "cleared": None}
                waves.append(current)
            elif kind == "down":
                deaths.append(round(game.time, 1))
        # Who is out, and which wave each came with.
        alive = 0
        for e in st.enemies:
            if e.uid not in seen:
                seen.add(e.uid)
                if current is not None:
                    current["size"] += 1
                    members[e.uid] = (e, current)
            if e.alive and e.dying < 0 and e.kind != "mothership":
                alive += 1
        if members and (n % 6 == 0 or n == steps - 1):
            for uid in [u for u, (e, _) in members.items() if not e.alive or e.dying >= 0]:
                e, w = members.pop(uid)
                if e.health <= 0 or e.dying >= 0:
                    w["killed"] += 1
                else:
                    w["home"] += 1              # flew back to the mothership
                if w["killed"] + w["home"] >= w["size"]:
                    w["cleared"] = round(game.time - w["t"], 1)
        out[m] = max(out[m], alive)
        sec_most = max(sec_most, alive)
        if (n + 1) % rate == 0:
            ms = sec_cost / rate * 1000.0
            worst = max(worst, ms)
            if sec_most > most:
                most, most_ms = sec_most, ms
            sec_cost, sec_most = 0.0, 0
        if (n + 1) % (60 * rate) == 0 or n == steps - 1:
            balance[m] = game.credits
    wall = clock.perf_counter() - began

    bought = {}
    for p in purchases:
        name = p["key"] if "step" not in p else f"{p['key']} {p['step']}"
        k = 1
        while (name if k == 1 else f"{name} #{k}") in bought:
            k += 1
        bought[name if k == 1 else f"{name} #{k}"] = round(p["t"] / 60.0, 2)
    result = {
        "seed": seed, "preset": preset, "minutes": minutes, "step_rate": rate,
        "mining": [round(v) for v in mining], "combat": [round(v) for v in combat],
        "out": out, "balance": balance,
        "purchases": purchases, "bought": bought,
        "waves": waves, "deaths": deaths, "kills": kills,
        "skipped": list(bot.skipped),
        "list_left": [key if tier is None else f"{key}:{tier}" for _, key, tier in bot.plan[bot.at:]],
        "time_in": {k: round(v, 1) for k, v in sorted(bot.time_in.items(), key=lambda kv: -kv[1])},
        "drills_out": len(game.drills), "ring": game.haul.has_ring(),
        "ring_rocks": game.haul.ring.held if game.haul.has_ring() else 0,
        "step_ms": {"mean": round(wall / max(1, steps) * 1000.0, 3), "worst_second": round(worst, 3),
                    "most_out": most, "at_most_out": round(most_ms, 3)},
        "wall_seconds": round(wall, 1),
    }
    result["marks"] = marks(result, bot.done_at, spec)
    if trace:
        result["trace"] = bot.trace
    return result


def crossover(mining: list, combat: list, window: int) -> float | None:
    """The minute combat income passes mining income for good: the end of the first `window`-minute
    stretch in which kills paid more than ore, with every later stretch the same."""
    n = len(mining)
    at = None
    for m in range(window, n + 1):
        ahead = sum(combat[m - window:m]) > sum(mining[m - window:m])
        if ahead and at is None:
            at = float(m)
        elif not ahead:
            at = None
    return at


def marks(result: dict, done_at: dict, spec: dict) -> dict:
    """The pacing guide's marks for one game, in minutes (None where the game never got there)."""
    def minute(t):
        return None if t is None else round(t / 60.0, 2)

    third = [p["t"] for p in result["purchases"] if p["key"] == "sentry_missile" and p.get("step") == 3]
    wave_30 = next((w["t"] for w in result["waves"] if w["n"] >= MASSIVE_FROM), None)
    deaths = result["deaths"]
    return {
        "early_done": minute(done_at.get("early")),
        "mid_done": minute(done_at.get("mid")),
        "late_done": minute(done_at.get("late")),
        "crossover": crossover(result["mining"], result["combat"], int(spec["window"])),
        "two_missile_t3": minute(third[1]) if len(third) >= 2 else None,
        "deaths_before_wave_30": len([t for t in deaths if wave_30 is None or t < wave_30]),
        "wave_30": minute(wave_30),
        "waves": len(result["waves"]),
        "deaths": len(deaths),
        "earned": sum(result["mining"]) + sum(result["combat"]),
    }
