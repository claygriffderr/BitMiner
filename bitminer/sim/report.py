"""Turns a batch of simulated games into one report: the median of each number over the games, and
each pacing mark judged against its target from `data/sim.json`."""

from __future__ import annotations

from statistics import mean, median

JOBS = {
    "haul": "Loading and selling ore by hand",
    "tow": "Towing asteroids to the ring",
    "fight": "Fighting",
    "drill": "Setting drills",
    "shop": "At the station",
    "idle": "Waiting",
    "loose": "Picking up loose drills",
    "clear": "Clearing useless rocks out of the ring",
    "defend": "Flying to something under attack",
    "pause": "Pauses between jobs",
    "sentry": "Setting sentries",
    "ring": "Setting the ring",
    "down": "Destroyed, waiting to respawn",
    "drop": "Letting go of the lasso",
}


def _mid(values):
    values = [v for v in values if v is not None]
    return median(values) if values else None


def judge(mark: dict, games: list[dict]) -> dict:
    """One pass mark over all the games: the median of the games that got there, and a verdict."""
    key, low, high = mark["key"], float(mark["low"]), float(mark["high"])
    got = [g["marks"].get(key) for g in games]
    reached = [v for v in got if v is not None]
    out = {"key": key, "label": mark["label"], "low": low, "high": high, "unit": mark["unit"],
           "reached": len(reached), "games": len(games), "value": None, "least": None, "most": None}
    if len(reached) * 2 < len(games) or not reached:
        out["verdict"] = "NOT REACHED"
        return out
    value = median(reached)
    out.update(value=round(value, 1), least=round(min(reached), 1), most=round(max(reached), 1))
    if value < low:
        out["verdict"] = "TOO EARLY" if mark["unit"] == "min" else "PASS"
    elif value > high:
        out["verdict"] = "TOO LATE" if mark["unit"] == "min" else "TOO MANY"
    else:
        out["verdict"] = "PASS"
    return out


def summarise(games: list[dict], spec: dict) -> dict:
    """The whole batch boiled down."""
    first = games[0]
    minutes = int(len(first["mining"]))
    block = 5
    income = []
    for start in range(0, minutes, block):
        end = min(minutes, start + block)
        span = end - start
        mining = median(sum(g["mining"][start:end]) / span for g in games)
        combat = median(sum(g["combat"][start:end]) / span for g in games)
        income.append({"from": start, "to": end, "mining": round(mining), "combat": round(combat),
                       "combat_share": round(combat / (mining + combat), 3) if mining + combat > 0 else 0.0,
                       "most_out": round(median(max(g["out"][start:end]) for g in games)),
                       "balance": round(median(g["balance"][end - 1] for g in games))})
    names: dict[str, list[float]] = {}
    for g in games:
        for name, minute in g["bought"].items():
            names.setdefault(name, []).append(minute)
    bought = sorted(({"item": name, "minute": round(median(v), 1), "games": len(v)} for name, v in names.items()),
                    key=lambda row: row["minute"])
    waves = []
    most_waves = max(len(g["waves"]) for g in games)
    for k in range(most_waves):
        rows = [g["waves"][k] for g in games if len(g["waves"]) > k]
        if len(rows) * 2 < len(games):
            break
        size = sum(w["size"] for w in rows)
        cleared = [w["cleared"] for w in rows if w["cleared"] is not None]
        waves.append({"n": rows[0]["n"], "name": rows[0]["name"], "minute": round(median(w["t"] for w in rows) / 60.0, 1),
                      "ships": round(median(w["size"] for w in rows)),
                      "killed": round(sum(w["killed"] for w in rows) / size, 3) if size else 0.0,
                      "went_home": round(sum(w["home"] for w in rows) / size, 3) if size else 0.0,
                      "clear_seconds": round(median(cleared)) if len(cleared) * 2 >= len(rows) and cleared else None,
                      "games": len(rows)})
    total_time = sum(sum(g["time_in"].values()) for g in games) or 1.0
    jobs: dict[str, float] = {}
    for g in games:
        for name, seconds in g["time_in"].items():
            jobs[name] = jobs.get(name, 0.0) + seconds
    time_in = [{"job": name, "label": JOBS.get(name, name), "share": round(seconds / total_time, 3)}
               for name, seconds in sorted(jobs.items(), key=lambda kv: -kv[1])]
    skipped = sorted({key for g in games for key in g["skipped"]})
    left: dict[str, int] = {}
    for g in games:
        for key in dict.fromkeys(g["list_left"]):
            left[key] = left.get(key, 0) + 1
    earned = [g["marks"]["earned"] for g in games]
    return {
        "preset": first["preset"], "games": len(games), "minutes": first["minutes"],
        "seeds": [g["seed"] for g in games],
        "marks": [judge(m, games) for m in spec["marks"]],
        "earned": {"median": round(median(earned)), "least": min(earned), "most": max(earned),
                   "mining": round(median(sum(g["mining"]) for g in games)),
                   "combat": round(median(sum(g["combat"]) for g in games))},
        "income": income, "bought": bought, "waves": waves,
        "waves_launched": round(median(len(g["waves"]) for g in games)),
        "deaths": {"median": median(len(g["deaths"]) for g in games), "most": max(len(g["deaths"]) for g in games),
                   "minutes": sorted(round(t / 60.0, 1) for g in games for t in g["deaths"])},
        "kills": round(median(sum(g["kills"].values()) for g in games)),
        "time_in": time_in, "skipped": skipped,
        "list_left": [{"item": key, "games": n} for key, n in left.items()],
        "step_ms": {"mean": round(mean(g["step_ms"]["mean"] for g in games), 2),
                    "worst_second": round(max(g["step_ms"]["worst_second"] for g in games), 1),
                    "most_out": max(g["step_ms"]["most_out"] for g in games)},
    }


def _table(head: list[str], rows: list[list]) -> list[str]:
    rows = [[str(c) for c in row] for row in rows]
    wide = [max(len(head[i]), *(len(r[i]) for r in rows)) if rows else len(head[i]) for i in range(len(head))]
    line = lambda cells: "| " + " | ".join(c.ljust(w) for c, w in zip(cells, wide)) + " |"
    return [line(head), "|" + "|".join("-" * (w + 2) for w in wide) + "|", *(line(r) for r in rows)]


def _num(v, unit: str = "") -> str:
    if v is None:
        return "-"
    text = f"{v:,.1f}" if isinstance(v, float) and v != int(v) else f"{int(v):,}"
    return text + unit


def render(s: dict) -> str:
    """The report as text (Markdown tables, which also read fine in a terminal)."""
    out = [f"# BitMiner balance report: {s['preset']} player",
           "",
           f"{s['games']} simulated games of {_num(s['minutes'])} minutes each (seeds "
           f"{', '.join(str(v) for v in s['seeds'])}). Every number is the median over the games unless it says otherwise.",
           "", "## Pass marks", ""]
    rows = []
    for m in s["marks"]:
        unit = " min" if m["unit"] == "min" else ""
        target = f"{_num(m['low'])} to {_num(m['high'])}{unit}"
        if m["value"] is None:
            got, spread = "never" if m["reached"] == 0 else "rarely", f"{m['reached']} of {m['games']} games"
        else:
            got = _num(float(m["value"]), unit)
            spread = f"{_num(float(m['least']))} to {_num(float(m['most']))}"
            if m["reached"] < m["games"]:
                spread += f" ({m['reached']} of {m['games']} games)"
        rows.append([m["label"], target, got, spread, m["verdict"]])
    out += _table(["Mark", "Target", "Result", "Range", "Verdict"], rows)
    e = s["earned"]
    out += ["", "## Income", "",
            f"Earned over the whole game: {_num(e['median'])} credits ({_num(e['least'])} to {_num(e['most'])}), "
            f"{_num(e['mining'])} from ore and {_num(e['combat'])} from kills.", ""]
    out += _table(["Minutes", "Ore / min", "Kills / min", "Kills share", "Most enemies out", "Credits in hand"],
                  [[f"{r['from']} to {r['to']}", _num(r["mining"]), _num(r["combat"]), f"{r['combat_share']:.0%}",
                    r["most_out"], _num(r["balance"])] for r in s["income"]])
    out += ["", "## When things were bought", ""]
    out += _table(["Item", "Minute", "Games"], [[r["item"], _num(float(r["minute"])), f"{r['games']} of {s['games']}"]
                                                for r in s["bought"]])
    if s["list_left"]:
        out += ["", "Still on the shopping list at the end: " +
                ", ".join(f"{r['item']} ({r['games']} of {s['games']} games)" for r in s["list_left"]) + "."]
    if s["skipped"]:
        out += ["", "Not in the shop yet, so skipped: " + ", ".join(s["skipped"]) + "."]
    out += ["", "## Waves", "",
            f"{s['waves_launched']} waves launched and {_num(s['kills'])} enemies destroyed in a game.", ""]
    out += _table(["Wave", "Name", "Launched (min)", "Ships", "Killed", "Flew home", "Cleared in (s)"],
                  [[w["n"], w["name"], _num(float(w["minute"])), w["ships"], f"{w['killed']:.0%}", f"{w['went_home']:.0%}",
                    _num(w["clear_seconds"])] for w in s["waves"]])
    d = s["deaths"]
    when = ", ".join(_num(float(t)) for t in d["minutes"]) if d["minutes"] else "none"
    out += ["", "## Deaths", "",
            f"{_num(d['median'])} in a game (the most in any game: {d['most']}). Minutes they happened, all games: {when}.",
            "", "## Where the time went", ""]
    out += _table(["Doing what", "Share of the game"], [[r["label"], f"{r['share']:.0%}"] for r in s["time_in"]
                                                         if r["share"] >= 0.005])
    c = s["step_ms"]
    out += ["", "## Cost of a step", "",
            f"{c['mean']} ms on average, {c['worst_second']} ms in the slowest second, with at most {c['most_out']} "
            "enemies out at once (a 60 Hz frame has 16.7 ms).", ""]
    return "\n".join(out)
