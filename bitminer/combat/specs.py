"""Weapon, enemy and defense numbers from `data/weapons.json`, and how enemies fight and waves arrive
from `data/combat.json`, so none of them live in code."""

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

COMBAT_FILE = DATA_FILE.parent / "combat.json"
_COMBAT = json.loads(COMBAT_FILE.read_text(encoding="utf-8"))

AI: dict[str, dict] = _COMBAT["ai"]
WAVES: dict = _COMBAT["waves"]
SANDBOX: dict = _COMBAT["sandbox"]
HUNT: dict = _COMBAT["hunt"]
FLEET: dict = _COMBAT["fleet"]
MINES: dict = _COMBAT["mines"]
PLAYDATA: dict = _COMBAT["playdata"]
