"""Write the weapon gallery review page (index.html) next to the GIFs made by `--record DIR`.

    python -m bitminer --record DIR --size 1280x720
    python -m bitminer.gallery.review_page DIR

Uses the same look as the art review page from sprint 1.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from art.review_page import CSS as ART_CSS

from ..combat.specs import DEFENSE, ENEMIES, ENEMY_WEAPONS, WEAPONS
from . import scenes as SC

DOWNLOAD = "https://github.com/claygriffderr/BitMiner/releases/tag/weapon-gallery"

CSS = ART_CSS + """
.weapon { display: grid; gap: 14px; }
.weapon-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 16px; }
.weapon-head h3 { font-family: var(--font-display); font-size: 18px; font-weight: 400; letter-spacing: 0.03em; }
.stats { font: 12px var(--font-mono); color: var(--ink-dim); }
.gifs { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
.gifs .big { grid-column: 1 / -1; }
@media (min-width: 900px) { .gifs .big { grid-column: span 2; } }
.gifs .stage { padding: 0; }
.gifs img { width: 100%; height: auto; image-rendering: pixelated; }
.cap .tag { font: 11px var(--font-mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--ion); }
.cap .tag.hurt { color: var(--danger); }
.keys { display: grid; gap: 8px; grid-template-columns: max-content 1fr; align-items: baseline; max-width: 72ch; }
.keys kbd { font: 12px var(--font-mono); color: var(--ink); background: var(--void); border: 1px solid var(--panel-hi);
  border-bottom-width: 2px; padding: 1px 7px; white-space: nowrap; justify-self: start; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; font: 13px var(--font-mono); min-width: 560px; width: 100%; }
th, td { text-align: left; padding: 7px 12px; border-bottom: 1px solid var(--panel-hi); white-space: nowrap; }
th { color: var(--ink-dim); font-weight: 400; }
td.num { font-variant-numeric: tabular-nums; }
.download { display: inline-block; font: 14px var(--font-mono); color: var(--space); background: var(--ion);
  padding: 8px 14px; text-decoration: none; justify-self: start; }
"""

DEFENSE_TEXT = {
    "shield": ("Shield up", "Every hit lands on the bubble: a cyan arc where it struck, and the shield bar drops."),
    "shield_breaks": ("Shield breaks", "The shield starts nearly empty, so it shatters partway through and the rest of the hits land on the armor."),
    "armor": ("Armor", "No shield, so every hit lands on the armor: grey sparks, a white flash on the ship, and the hull bar drops."),
}

ATTACK_STATS = {
    "infantry_lasers": lambda: _stats(ENEMY_WEAPONS["infantry_laser"], speed="px/s", damage="dmg", fire_every="s apart"),
    "rapid_assault": lambda: _stats(ENEMY_WEAPONS["rapid_laser"], speed="px/s", damage="dmg", burst="shots"),
    "guard_ram": lambda: _stats(ENEMIES["guard"], ram_speed="px/s", ram_damage="dmg", warn_time="s warning"),
    "tank_missiles": lambda: _stats(ENEMY_WEAPONS["tank_missile"], max_speed="px/s", turn_rate="°/s", damage="dmg"),
    "shoot_down": lambda: _stats(ENEMY_WEAPONS["tank_missile"], health="health"),
    "mothership_laser": lambda: _stats(ENEMY_WEAPONS["mothership_laser"], track_time="s tracking",
                                       lock_time="s locked", fire_time="s firing", dps="dmg/s"),
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def _num(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def _stats(spec: dict, **units) -> str:
    return " · ".join(f"{_num(spec[k])} {u}" for k, u in units.items())


def sentence(text: str) -> str:
    """The HUD's capitals, as an ordinary sentence."""
    out = []
    for part in text.lower().split(". "):
        part = part.strip()
        if part:
            out.append(part[0].upper() + part[1:])
    s = ". ".join(out)
    return s if s.endswith(".") else s + "."


def tile(meta: dict, title: str, tag: str, text: str, hurt: bool = False) -> str:
    w, h = meta["size"]
    big = " big" if w > 800 else ""
    return f"""
<figure class="panel tile{big}" id="{esc(meta['key'])}">
  <div class="stage"><img src="gif/{esc(meta['file'])}" width="{w}" height="{h}" loading="lazy" alt="{esc(meta['title'].title())}"></div>
  <figcaption class="cap"><span class="tag{' hurt' if hurt else ''}">{esc(tag)}</span><h3>{esc(title)}</h3><p class="muted">{esc(text)}</p></figcaption>
</figure>"""


def build(dest: Path) -> Path:
    made = {m["key"]: m for m in json.loads((dest / "scenes.json").read_text())}

    weapons_html = []
    for w in WEAPONS:
        spec = WEAPONS[w]
        about = sentence(SC._fmt(SC.WEAPON_ABOUT[w], spec))
        stats = {
            "auto": _stats(spec, fire_rate="shots/s", damage="dmg", speed="px/s"),
            "sniper": _stats(spec, damage="dmg", pierce="hulls", fire_rate="shots/s"),
            "missile": _stats(spec, damage="dmg", blast_radius="px blast", max_speed="px/s"),
            "laser": _stats(spec, dps="dmg/s", duration="s beam", length="px long"),
        }[w]
        tiles = []
        for target in ENEMIES:
            m = made.get(f"{w}-{target}")
            if m:
                tiles.append(tile(m, f"vs {ENEMIES[target]['label'].title()}", spec["label"],
                                  sentence(SC.DEATH_ABOUT[target])))
        weapons_html.append(f"""
<div class="weapon" id="w-{w}">
  <div class="weapon-head"><h3>{esc(spec['label'].title())}</h3><span class="stats">{esc(stats)}</span></div>
  <p class="muted">{esc(about)}</p>
  <div class="gifs">{''.join(tiles)}</div>
</div>""")

    attacks_html = []
    for attack, (label, about) in SC.ATTACKS.items():
        spec = {"infantry_lasers": ENEMY_WEAPONS["infantry_laser"],
                "rapid_assault": ENEMY_WEAPONS["rapid_laser"]}.get(attack, {})
        tiles = []
        for row, (dlabel, dtext) in DEFENSE_TEXT.items():
            m = made.get(f"{attack}-{row}")
            if m:
                tiles.append(tile(m, dlabel, label, dtext, hurt=True))
        attacks_html.append(f"""
<div class="weapon" id="a-{attack}">
  <div class="weapon-head"><h3>{esc(label.title())}</h3><span class="stats">{esc(ATTACK_STATS[attack]())}</span></div>
  <p class="muted">{esc(sentence(SC._fmt(about, spec)))}</p>
  <div class="gifs">{''.join(tiles)}</div>
</div>""")

    numbers = []
    for k, e in ENEMIES.items():
        numbers.append(f"<tr><td>{esc(e['label'].title())}</td><td class='num'>{_num(e['health'])}</td>"
                       f"<td class='num'>{_num(e['mass'])}</td><td class='num'>{_num(e.get('speed', '-'))}</td></tr>")

    jump = "".join(f'<a href="#w-{w}">{esc(WEAPONS[w]["label"].title())}</a>' for w in WEAPONS)
    jump += "".join(f'<a href="#a-{a}">{esc(lab.title())}</a>' for a, (lab, _) in SC.ATTACKS.items())

    page = f"""<title>BitMiner Weapon Gallery</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&family=Silkscreen&display=swap">
<style>{CSS}</style>
<div class="wrap">

<header>
  <span class="eyebrow">Sprint 3 · Weapon effects gallery</span>
  <h1>BitMiner weapon gallery</h1>
  <p class="lead">Every weapon against every enemy, and every enemy attack against your shield and armor, recorded straight from the game. Each clip is one loop of the gallery's auto pilot, so it starts with the enemies warping in and ends when they are destroyed. Leave a comment on any clip you want changed.</p>
  <a class="download" href="{DOWNLOAD}">Download for Windows</a>
  <nav class="jump" aria-label="Sections">
    <a href="#weapons">Your weapons</a>{jump}<a href="#try">Try it yourself</a><a href="#numbers">Numbers</a><a href="#next">What's next</a>
  </nav>
</header>

<section id="weapons">
  <div class="section-head">
    <h2>Your weapons</h2>
    <p class="muted">Each enemy in these clips has just enough health to fall to one showing of the weapon, so you see the whole destruction every time. Real fights in sprint 4 use the full health in the table further down.</p>
  </div>
  {''.join(weapons_html)}
</section>

<section id="attacks">
  <div class="section-head">
    <h2>Enemy attacks</h2>
    <p class="muted">Each attack three ways: with your shield up, with the shield breaking partway through, and straight onto the armor. Everything that can hurt you is pink and red, and the shield and hull readout sits in the corner.</p>
  </div>
  {''.join(attacks_html)}
</section>

<section id="try">
  <div class="section-head">
    <h2>Try it yourself</h2>
    <p class="muted">The download opens on a new start menu with the flight test and the weapon gallery. In the gallery, switch to free-fly to fly in among the targets and fire each weapon yourself.</p>
  </div>
  <div class="panel next">
    <div class="keys">
      <kbd>← →</kbd><span>Pick a weapon or an enemy attack</span>
      <kbd>↑ ↓</kbd><span>Pick the target, or your defense</span>
      <kbd>Space</kbd><span>Replay the scene</span>
      <kbd>F</kbd><span>Switch between the auto pilot and free-fly</span>
      <kbd>WASD</kbd><span>Fly (free-fly), with the mouse to aim and a click to fire</span>
      <kbd>1 2 3 4</kbd><span>Auto cannon, sniper, missiles, laser (free-fly)</span>
      <kbd>Tab</kbd><span>Flight tuning sliders, starting from the values you sent</span>
      <kbd>Esc</kbd><span>Back to the menu</span>
    </div>
    <a class="download" href="{DOWNLOAD}">Download for Windows</a>
  </div>
</section>

<section id="numbers">
  <div class="section-head">
    <h2>Numbers</h2>
    <p class="muted">Starting guesses, all kept in one settings file (<code>bitminer/data/weapons.json</code>) so they can change without touching code. Your shield and hull are {_num(DEFENSE['shield'])} each. Combat in sprint 4 is where these get tuned.</p>
  </div>
  <div class="panel table-wrap">
    <table>
      <thead><tr><th>Enemy</th><th>Health</th><th>Mass</th><th>Speed px/s</th></tr></thead>
      <tbody>{''.join(numbers)}</tbody>
    </table>
  </div>
</section>

<section id="next">
  <div class="panel next">
    <h2>What's next</h2>
    <p>Sprint 4 is combat: these weapons and enemies in the asteroid field with real health, ammo and reloads, your ship console, enemy movement, and waves to fight.</p>
    <p class="muted">Your flight tuning from sprint 2 is now the starting point for every new install, kept in a settings file, and still adjustable from the Tab panel in both the flight test and the gallery.</p>
  </div>
</section>

</div>
"""
    out = dest / "index.html"
    out.write_text(page)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
