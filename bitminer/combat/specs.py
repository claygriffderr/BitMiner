"""Weapon, enemy and defense numbers, read from `data/weapons.json` so none of them live in code."""

from __future__ import annotations

import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "weapons.json"

_DATA = json.loads(DATA_FILE.read_text(encoding="utf-8"))

WEAPONS: dict[str, dict] = _DATA["player_weapons"]
ENEMIES: dict[str, dict] = _DATA["enemies"]
ENEMY_WEAPONS: dict[str, dict] = _DATA["enemy_weapons"]
DEFENSE: dict[str, float] = _DATA["player_defense"]
GALLERY: dict[str, dict] = _DATA["gallery"]

WEAPON_ORDER = list(WEAPONS)          # auto, sniper, missile, laser
ENEMY_ORDER = list(ENEMIES)           # infantry, guard, rapid, tank, mothership
