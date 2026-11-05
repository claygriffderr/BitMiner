"""Flight tuning (every number the on-screen sliders change), display options, and where they are saved."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

FILE_NAME = "flight_tuning.json"


@dataclass
class Tuning:
    thrust_main: float = 260.0   # W, forward booster. Game pixels per second squared at mass 1.
    thrust_side: float = 160.0   # A and D, strafe boosters.
    thrust_retro: float = 140.0  # S, retro boosters on the front of the pods.
    turn_rate: float = 300.0     # How fast the ship turns toward the mouse, degrees per second.
    damper: float = 0.25         # Drift damper: how fast speed bleeds off, per second. 0 is off.
    top_speed: float = 240.0     # Soft cap. Faster than this, speed is pulled back quickly.
    mass: float = 1.0            # Heavier: slower to speed up, hits harder, knocked around less.
    bounce: float = 0.4          # How springy hits against asteroids are, 0 to 1.
    camera_lead: float = 0.5     # How far the camera looks ahead of the ship, 0 to 1.
    shake: float = 1.0           # Screen shake strength on impacts.

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
        if self.step >= 1:
            return f"{value:.0f}"
        if self.step >= 0.1 - 1e-9:
            return f"{value:.1f}"
        return f"{value:.2f}"


# The order here is the order on screen.
SLIDERS: tuple[SliderSpec, ...] = (
    SliderSpec("thrust_main", "MAIN THRUST", 60, 700, 10),
    SliderSpec("thrust_side", "SIDE THRUST", 30, 500, 10),
    SliderSpec("thrust_retro", "RETRO THRUST", 30, 500, 10),
    SliderSpec("turn_rate", "TURN RATE", 60, 900, 10),
    SliderSpec("damper", "DRIFT DAMPER", 0, 2, 0.05),
    SliderSpec("top_speed", "TOP SPEED", 80, 700, 10),
    SliderSpec("mass", "MASS", 0.4, 4, 0.1),
    SliderSpec("bounce", "BOUNCE", 0, 1, 0.05),
    SliderSpec("camera_lead", "CAMERA LEAD", 0, 1, 0.05),
    SliderSpec("shake", "SCREEN SHAKE", 0, 2, 0.1),
)

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
