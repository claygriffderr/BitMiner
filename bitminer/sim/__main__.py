"""`python -m bitminer.sim`: play simulated games and print the balance report.

    python -m bitminer.sim --preset motivated --seeds 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import load_spec
from .report import render, summarise
from .run import play, run_batch


def parse(argv=None) -> argparse.Namespace:
    spec = load_spec()
    p = argparse.ArgumentParser(prog="bitminer.sim", description="BitMiner balance simulator")
    p.add_argument("--preset", choices=list(spec["presets"]), default="motivated", help="the kind of player")
    p.add_argument("--seeds", type=int, default=10, help="how many games to play (maps 1 to this number)")
    p.add_argument("--first-seed", type=int, default=1, help="the first map's number")
    p.add_argument("--minutes", type=float, help=f"how long each game lasts (default {spec['minutes']})")
    p.add_argument("--jobs", type=int, help="games to play at once (default: one per processor)")
    p.add_argument("--out", help="also write the report to this file")
    p.add_argument("--json", help="also write every game's numbers to this file")
    p.add_argument("--trace", action="store_true", help="play one game and list what the bot did, job by job")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse(argv)
    spec = load_spec()
    if args.trace:
        game = play(seed=args.first_seed, preset=args.preset, minutes=args.minutes, trace=True)
        for t, job in game["trace"]:
            print(f"{t / 60.0:6.2f}  {job}")
        print(json.dumps(game["marks"], indent=2))
        return 0
    seeds = list(range(args.first_seed, args.first_seed + max(1, args.seeds)))

    def note(game: dict) -> None:
        print(f"  map {game['seed']}: {game['marks']['earned']:,} credits, {game['marks']['waves']} waves, "
              f"{game['marks']['deaths']} deaths ({game['wall_seconds']:.0f} s)", file=sys.stderr, flush=True)

    print(f"Playing {len(seeds)} games as the {args.preset} player...", file=sys.stderr, flush=True)
    games = run_batch(seeds, args.preset, args.minutes, args.jobs, note)
    summary = summarise(games, spec)
    text = render(summary)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "games": games}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
