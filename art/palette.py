"""BitMiner's color palette.

Every color has one job, so a glance at the screen tells you what is what:

- Green and purple: enemy ships
- Hot pink and red: anything that can hurt you
- Orange: the friendly faction (powerups, safe zones)
- Pale white-cyan: the player's shots, engines and HUD
- Drab grey with a light outline: the player's ship, base, drills and sentries
- Gold: resources
- Dark, muted violet-greys: space and asteroids

`GLOW` lists the colors that emit light and how strongly they bloom.
Brighter glow means more threat.
"""

def _hex(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255)


PALETTE: dict[str, tuple[int, int, int, int]] = {
    "clear": (0, 0, 0, 0),
    # Space
    "void": _hex("#06050d"),
    "space": _hex("#0b0a1a"),
    "nebula_violet": _hex("#140c29"),
    "nebula_violet_hi": _hex("#1d113c"),
    "nebula_teal": _hex("#0a1a1e"),
    "nebula_teal_hi": _hex("#0e262a"),
    "star_dim": _hex("#34345a"),
    "star_mid": _hex("#7a7aa8"),
    "star_bright": _hex("#e4e2ff"),
    # Asteroids
    "rock_shadow": _hex("#18131d"),
    "rock_dark": _hex("#2a2230"),
    "rock_mid": _hex("#3e3446"),
    "rock_light": _hex("#5a4e62"),
    "rock_rim": _hex("#7c6f84"),
    # Resources
    "ore_dark": _hex("#8a6a0e"),
    "ore": _hex("#f0c235"),
    "ore_hi": _hex("#fff09a"),
    # Player ship, base, drills and sentries
    "hull_black": _hex("#141619"),
    "hull_dark": _hex("#2c3037"),
    "hull_mid": _hex("#4b525c"),
    "hull_light": _hex("#737c87"),
    "hull_hi": _hex("#a3acb6"),
    "hull_outline": _hex("#d4e2ea"),
    "canopy": _hex("#3fb6d6"),
    "canopy_hi": _hex("#b9f6ff"),
    # Player light: shots, engines, HUD
    "ion_dark": _hex("#1f7fa8"),
    "ion": _hex("#4fd8ff"),
    "ion_hi": _hex("#aef3ff"),
    "ion_white": _hex("#f0ffff"),
    # Enemy ships
    "alien_green_dark": _hex("#0b4a30"),
    "alien_green": _hex("#17a34f"),
    "alien_green_hi": _hex("#59f58a"),
    "alien_eye": _hex("#b6ffcf"),
    "alien_purple_black": _hex("#1c0b33"),
    "alien_purple_dark": _hex("#371260"),
    "alien_purple": _hex("#6526b5"),
    "alien_purple_hi": _hex("#9d5cff"),
    # Danger
    "danger_dark": _hex("#7a0b2a"),
    "danger_red": _hex("#ff2448"),
    "danger_pink": _hex("#ff2f9a"),
    "danger_pink_hi": _hex("#ff86c8"),
    "danger_white": _hex("#ffe3f1"),
    # Friendly faction
    "friend_dark": _hex("#7c3300"),
    "friend": _hex("#ff7a1a"),
    "friend_hi": _hex("#ffb45e"),
    "friend_white": _hex("#ffe2bd"),
    # Console (HUD frames)
    "console_black": _hex("#0d0f14"),
    "console_dark": _hex("#1a1e26"),
    "console_mid": _hex("#2b313c"),
    "console_edge": _hex("#4a5262"),
    "console_hi": _hex("#6c7586"),
    "hud_text": _hex("#c6f2ff"),
    "hud_dim": _hex("#59707e"),
}

# Glow strength per emissive color, from 0 (none) to 1 (strongest).
GLOW: dict[str, float] = {
    "star_bright": 0.25,
    "ore": 0.35,
    "ore_hi": 0.5,
    "canopy_hi": 0.25,
    "ion": 0.45,
    "ion_hi": 0.55,
    "ion_white": 0.6,
    "alien_green_hi": 0.35,
    "alien_eye": 0.6,
    "alien_purple_hi": 0.25,
    "danger_red": 0.9,
    "danger_pink": 0.9,
    "danger_pink_hi": 1.0,
    "danger_white": 1.0,
    "friend": 0.6,
    "friend_hi": 0.7,
    "friend_white": 0.8,
    "hud_text": 0.15,
}

# Roles shown on the art review page.
ROLES: list[tuple[str, str, list[str]]] = [
    ("Space", "The backdrop stays dark so everything else reads.",
     ["void", "space", "nebula_violet", "nebula_violet_hi", "nebula_teal", "nebula_teal_hi",
      "star_dim", "star_mid", "star_bright"]),
    ("Asteroids", "Dark and muted, with a lit rim so their edges are clear.",
     ["rock_shadow", "rock_dark", "rock_mid", "rock_light", "rock_rim"]),
    ("Resources", "Gold flecks mark ore worth mining.",
     ["ore_dark", "ore", "ore_hi"]),
    ("Player hardware", "Drab grey with a light outline: your ship, base, drills and sentries.",
     ["hull_black", "hull_dark", "hull_mid", "hull_light", "hull_hi", "hull_outline",
      "canopy", "canopy_hi"]),
    ("Player light", "Your shots, engines and HUD.",
     ["ion_dark", "ion", "ion_hi", "ion_white"]),
    ("Enemy ships", "Hacker green and purple.",
     ["alien_green_dark", "alien_green", "alien_green_hi", "alien_eye",
      "alien_purple_black", "alien_purple_dark", "alien_purple", "alien_purple_hi"]),
    ("Danger", "Anything that can hurt you, from shots to warnings.",
     ["danger_dark", "danger_red", "danger_pink", "danger_pink_hi", "danger_white"]),
    ("Friendly faction", "Powerups and safe zones.",
     ["friend_dark", "friend", "friend_hi", "friend_white"]),
    ("Console", "HUD frames and text.",
     ["console_black", "console_dark", "console_mid", "console_edge", "console_hi",
      "hud_text", "hud_dim"]),
]


def rgba(name: str) -> tuple[int, int, int, int]:
    return PALETTE[name]


def hexcode(name: str) -> str:
    r, g, b, _ = PALETTE[name]
    return f"#{r:02x}{g:02x}{b:02x}"
