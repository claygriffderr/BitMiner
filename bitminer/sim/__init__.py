"""The balance simulator: a bot plays whole games of Secure the Base with no graphics and reports
whether the pacing targets are met. Run it with `python -m bitminer.sim`; its settings are in
`data/sim.json`."""

from __future__ import annotations

import json

from ..combat.specs import SHOP_FILE

SIM_FILE = SHOP_FILE.with_name("sim.json")


def load_spec() -> dict:
    """`data/sim.json`: the shopping list, the player presets, the bot's habits and the pass marks."""
    return json.loads(SIM_FILE.read_text(encoding="utf-8"))
