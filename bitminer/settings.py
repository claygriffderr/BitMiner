"""Flight tuning (every number the on-screen sliders change), display options, and where they are saved.

No tuning number lives in the code. `data/tuning.json` holds each slider's starting value and
range, and the player's own changes save to flight_tuning.json next to the program.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

FILE_NAME = "flight_tuning.json"
DATA_FILE = Path(__file__).resolve().parent / "data" / "tuning.json"

_SPECS = json.loads(DATA_FILE.read_text(encoding="utf-8"))["flight"]
DEFAULTS: dict[str, float] = {item["key"]: float(item["value"]) for item in _SPECS}


def _start(key: str):
    """A field whose starting value comes from the data file."""
    return field(default_factory=lambda: DEFAULTS[key])


@dataclass
class Tuning:
    thrust_main: float = _start("thrust_main")    # W, forward booster. Game pixels per second squared at mass 1.
    thrust_side: float = _start("thrust_side")    # A and D, strafe boosters.
    thrust_retro: float = _start("thrust_retro")  # S, retro boosters on the front of the pods.
    turn_rate: float = _start("turn_rate")        # How fast the ship turns toward the mouse, degrees per second.
    damper: float = _start("damper")              # Drift damper: how fast speed bleeds off, per second. 0 is off.
    top_speed: float = _start("top_speed")        # Soft cap. Faster than this, speed is pulled back quickly.
    mass: float = _start("mass")                  # Heavier: slower to speed up, hits harder, knocked around less.
    bounce: float = _start("bounce")              # How springy hits against asteroids are, 0 to 1.
    camera_lead: float = _start("camera_lead")    # How far the camera looks ahead of the ship, 0 to 1.
    camera_aim: float = _start("camera_aim")      # In a fight, how far the view leans toward the mouse.
    shake: float = _start("shake")                # Screen shake strength on impacts.
    map_size: float = _start("map_size")          # Secure the Base map, times the sandbox each way. Used on a new game.

    def clamped(self) -> "Tuning":
        values = {}
        for spec in SLIDERS:
            v = getattr(self, spec.key)
            values[spec.key] = min(spec.hi, max(spec.lo, float(v)))
        return Tuning(**values)


@dataclass
class Display:
    crt: bool = False         # The optional CRT filter: scanlines, colour fringing and a vignette.
    fullscreen: bool = False


@dataclass
class Settings:
    tuning: Tuning = field(default_factory=Tuning)
    display: Display = field(default_factory=Display)


@dataclass(frozen=True)
class SliderSpec:
    key: str
    label: str
    lo: float
    hi: float
    step: float

    def snap(self, value: float) -> float:
        steps = round((value - self.lo) / self.step)
        return round(min(self.hi, max(self.lo, self.lo + steps * self.step)), 4)

    def fraction(self, value: float) -> float:
        return (value - self.lo) / (self.hi - self.lo)

    def text(self, value: float) -> str:
        if self.key == "damper" and value == 0:
            return "OFF"
        if self.key == "map_size":
            return f"{value:.0f}X"
        if self.step >= 1:
            return f"{value:.0f}"
        if self.step >= 0.1 - 1e-9:
            return f"{value:.1f}"
        return f"{value:.2f}"


# The order here (the data file's order) is the order on screen.
SLIDERS: tuple[SliderSpec, ...] = tuple(
    SliderSpec(item["key"], item["label"], float(item["min"]), float(item["max"]), float(item["step"]))
    for item in _SPECS)

assert {s.key for s in SLIDERS} == {f.name for f in fields(Tuning)}


def settings_path() -> Path:
    """Next to the program, so it's easy to find and send back. Falls back to the user's folder."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    if os.access(base, os.W_OK):
        return base / FILE_NAME
    return fallback_path()


def fallback_path() -> Path:
    """Somewhere always writable, for when the program sits in a protected folder."""
    return Path(os.environ.get("APPDATA") or Path.home()) / "BitMiner" / FILE_NAME


def load(path: Path | None = None) -> Settings:
    """Read saved settings. Missing, unknown or broken values fall back to the defaults."""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    numbers = {f.name for f in fields(Tuning)}
    tuning = {k: v for k, v in data.items()
              if k in numbers and isinstance(v, (int, float)) and not isinstance(v, bool) and v == v}
    flags = {f.name for f in fields(Display)}
    display = {k: v for k, v in data.items() if k in flags and isinstance(v, bool)}
    return Settings(Tuning(**tuning).clamped(), Display(**display))


def save(settings: Settings, path: Path | None = None) -> Path:
    """Write one flat, readable JSON file: the tuning numbers first, then the display options."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {**asdict(settings.tuning), **asdict(settings.display)}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)
    return path
