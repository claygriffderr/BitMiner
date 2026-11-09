"""Write the sprint 6 review page (index.html) next to the images made by `art.review6`.

    python -m art.review6 DIR     # builds the images, then this page
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .review_page import CSS, JS, esc, img_tag, tile

EXTRA_CSS = """
.decision .imgs { display: grid; gap: 10px; justify-items: center; background: var(--space); padding: 10px; }
.keys { display: grid; gap: 8px 18px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); margin: 0; padding: 0; list-style: none; }
.keys li { display: flex; gap: 10px; align-items: baseline; }
kbd { font: 12px var(--font-mono); color: var(--ink); background: var(--void); border: 1px solid var(--panel-edge); padding: 1px 6px; white-space: nowrap; }
"""


def build(dest: Path) -> Path:
    meta = json.loads((dest / "meta.json").read_text())

    def t(kind, name, title, size, text, **kw):
        return tile(meta, kind, name, title, size, text, **kw)

    def mock(name: str, title: str, text: str) -> str:
        return f"""
<figure class="panel mock" data-mock id="mock-{name}">
  <div class="stage"><img src="mock/{name}.png" width="1920" height="1080" alt="{esc(title)}, clean"></div>
  <figcaption class="cap">
    <div class="toggle" role="group" aria-label="Screen filter for {esc(title)}">
      <button type="button" aria-pressed="true" data-src="mock/{name}.png" data-alt="{esc(title)}, clean">Clean</button>
      <button type="button" aria-pressed="false" data-src="mock/{name}_crt.png" data-alt="{esc(title)}, CRT filter">CRT filter</button>
    </div>
    <h3>{esc(title)}</h3>
    <p class="muted">{text}</p>
  </figcaption>
</figure>"""

    pages = [("ship", "Ship"), ("weapons", "Weapons"), ("tools", "Tools")]
    buttons = "".join(
        f'<button type="button" aria-pressed="{"true" if i == 0 else "false"}" data-src="mock/station_{p}.png" '
        f'data-alt="Station screen, {label} page">{label}</button>' for i, (p, label) in enumerate(pages))
    station_mock = f"""
<figure class="panel mock" data-mock id="mock-station">
  <div class="stage"><img src="mock/station_ship.png" width="1920" height="1080" alt="Station screen, Ship page"></div>
  <figcaption class="cap">
    <div class="toggle" role="group" aria-label="Station page">{buttons}</div>
    <h3>The station screen</h3>
    <p class="muted">Fly up to the station and press E, and this opens on the right, so your ship, the station and anything heading your way stay in view (the game keeps running). Each page lists what you can buy on the left. The selected row opens on the right with its 3 levels as steps, what the next level changes, and the buy button. Prices in gold are ones you can afford; grey ones you can't yet. On the Tools page, enemies have turned up, so a warning flashes at the top.</p>
  </figcaption>
</figure>"""

    def option(rec: bool, title: str, media: str, text: str) -> str:
        chip = '<span class="chip">Your pick</span>' if rec else ""
        return f"""<div class="option{' rec' if rec else ''}">{chip}<h3>{esc(title)}</h3><div class="imgs">{media}</div><p class="muted">{text}</p></div>"""

    sentry_q = f"""
<div class="panel decision" id="q-sentry-shots">
  <div class="q"><span class="num">1</span><h3>How should sentry shots differ from yours?</h3></div>
  <p class="muted">You asked for sentry shots that look a little different so you can always tell them apart. Each pair below is your shot, then the sentry's.</p>
  <div class="options">
    {option(True, "A. Same cyan, new shapes", img_tag(meta, "sprites", "shots_shape", "Your shots beside sentry shots with new shapes"), "Sentries fire short diamond pellets, ring-headed dashed sniper rounds and darker missiles with cyan noses. Cyan keeps meaning \"your side\", and the shapes tell you who fired.")}
    {option(False, "B. Your shapes, deeper blue", img_tag(meta, "sprites", "shots_blue", "Your shots beside the same shapes in deeper blue"), "Sentries fire exactly what you fire, tinted a deeper blue. Easy to spot side by side, but it adds a new color to learn, and at speed the two blues are close.")}
  </div>
</div>"""

    laser_q = f"""
<div class="panel decision" id="q-laser">
  <div class="q"><span class="num">2</span><h3>What comes out after the 2 second charge?</h3></div>
  <p class="muted">Your notes say the laser keeps its current limits and releases everything in a single burst. That could mean either of these. Both use one charge, and both play the same charge-up.</p>
  <div class="options">
    {option(True, "A. Today's beam, starting with a burst", img_tag(meta, "anims", "laser_a", "Laser charging, then a beam you sweep across a line of enemies"), "The beam opens with a flash and a shockwave, then lasts as long as it does now (1.5 s), and you can sweep it across a group. The laser stays your swarm clearer.")}
    {option(False, "B. One short, heavy blast", img_tag(meta, "anims", "laser_b", "Laser charging, then one short blast straight ahead"), "All the damage goes out in a quarter of a second, straight ahead. It's a precise heavy shot: line it up, because you can't sweep it.")}
  </div>
</div>"""

    keys = [("Shift (hold)", "Boost, once you've bought it"), ("F", "Set a drill on the asteroid you're next to"),
            ("G (hold)", "Lay mines one after another"), ("R", "Place a sentry where you are"),
            ("E at the station", "Open the station screen"), ("1, 2, 3", "Station pages"),
            ("W / S and Enter", "Pick a row and buy (or click)"), ("E again", "Leave the station")]
    keys_html = "".join(f"<li><kbd>{esc(k)}</kbd><span class=\"muted\">{esc(v)}</span></li>" for k, v in keys)

    page = f"""<title>BitMiner Station Art</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&family=Silkscreen&display=swap">
<style>{CSS}{EXTRA_CSS}</style>
<div class="wrap">

<header>
  <span class="eyebrow">Sprint 6 · Station and item art · Round 1</span>
  <h1>Station and item art</h1>
  <p class="lead">Every new visual from your Secure the Base notes, drawn on the game's 640×360 grid before any of it goes into the game: the station screen, drills that fill with gold, asteroids that crack and crumble, sentries, mines, and your ship's new laser charge-up, boost, shield levels and missile count. Two choices are marked for you. Leave a comment on anything you want changed.</p>
  <nav class="jump" aria-label="Sections">
    <a href="#field">In the field</a><a href="#decisions">Your decisions</a><a href="#station">Station</a>
    <a href="#drills">Drills and asteroids</a><a href="#sentries">Sentries</a><a href="#mines">Mines</a>
    <a href="#ship">Your ship</a><a href="#hud">HUD</a><a href="#keys">Keys</a><a href="#next">What's next</a>
  </nav>
</header>

<section id="field">
  <div class="section-head">
    <h2>In the field</h2>
    <p class="muted">A mid-game moment with everything new on screen at once. Switch on the CRT filter to compare the optional scanline look.</p>
  </div>
  {mock("in_game", "Holding the belt", "Two drills share the big asteroid. Its cracks show about half its ore is gone, and the top drill is full: its bar is solid gold and its tip light has turned gold, so it has stopped until you unload it. On the left, a worked-out asteroid is crumbling away and taking its drill with it. Three sentries (auto cannon tier 1, sniper tier 2, missile tier 3) fire their own shots at a raid coming from the top right, and a raider has just set off the end of your mine line. You're boosting back at level 2 with three missiles left on the pods. The console now shows only the weapons you own, your shield and boost levels, and the drills, mines and sentries you carry. Bottom left, a drill off screen is under attack.")}
</section>

<section id="decisions">
  <div class="section-head">
    <h2>Your decisions</h2>
    <p class="muted">You picked A for both, so that's what goes into the game.</p>
  </div>
  <div class="decisions">{sentry_q}{laser_q}</div>
</section>

<section id="station">
  <div class="section-head">
    <h2>Space station</h2>
    <p class="muted">Three pages, Ship, Weapons and Tools, in the same console style as the HUD. Switch pages with the buttons under the screen.</p>
  </div>
  {station_mock}
  <div class="grid">
    {t("sprites", "upgrade_pane", "Upgrade panel", "Every upgrade has 3 levels", "Each level is a step card. Levels you own are lit, the next one has a bright edge with its price below, and later ones are dim. Under the cards, the stats show what the next level changes. Here, boost is at level 1, and level 2 is +40% for 750 credits.")}
    {t("sprites", "item_icons", "Shop icons", "13 to 17 px", "One icon per item and upgrade, used in the station's rows and on the console. The three sentries use their tier 1 look.", span2=True)}
  </div>
</section>

<section id="drills">
  <div class="section-head">
    <h2>Drills and asteroids</h2>
    <p class="muted">How full a drill is shows on the drill itself, and how much ore an asteroid has left shows in its cracks.</p>
  </div>
  <div class="grid">
    {t("sprites", "drill_fill", "Drill with its gold bar", "13×17 px, filling in 8 steps", "The bar down its middle lights up gold from the bottom as the hold fills. While it works, the tip light blinks cyan. When it's full, it stops: the tip light turns solid gold and the bar pulses, so a full drill is easy to spot.", span2=True)}
    {t("sprites", "drill_health", "Drill health", "Always shown above it", "A thin health bar sits above each drill and turns pink when it's nearly destroyed.")}
    {t("anims", "drill_working", "Filling and unloading", "Drill, stop, unload", "The drill fills, stops when full, and empties into your hold as you fly by, then starts again.")}
    {t("anims", "asteroid_life", "Crumbling away", "Worked out, then gone", "When the last ore is gone, the asteroid splits along its cracks and crumbles into dust, and its drills go with it.")}
    {t("sprites", "drill_markers", "Drill arrows", "At the screen edge", "The dim arrow for each off-screen drill carries a tiny copy of its gold bar and its health. It flashes pink while the drill is under attack.")}
    {t("sprites", "rock_stages", "Asteroids cracking", "Full, then 3 stages of cracks", "Cracks start at each drill and spread as the ore runs out. Gold flecks fade with them. Two drills share this one, so it cracks from both sides.", wide=True)}
  </div>
</section>

<section id="sentries">
  <div class="section-head">
    <h2>Sentries</h2>
    <p class="muted">A fixed platform with a turret that turns to aim. The platform grows heavier at each tier and carries one light per tier, and its health bar gets longer.</p>
  </div>
  <div class="grid">
    {t("sprites", "sentries", "Three kinds, three tiers", "Platforms 15 to 19 px", "The auto cannon has twin short barrels, the sniper one long barrel, and the missile sentry two launcher pods. The turret is lighter than its platform so you can read which way it's aiming.", span2=True)}
    {t("anims", "sentries_firing", "Tracking and firing", "Their own shots", "Each turret follows its target and fires sentry shots (option A from your decisions). The auto cannon tier 1 has taken a hit.")}
  </div>
</section>

<section id="mines">
  <div class="section-head">
    <h2>Explosive mines</h2>
    <p class="muted">Small spiked mines in your grey, with a cyan light.</p>
  </div>
  <div class="grid">
    {t("sprites", "mine_states", "Mine", "13×13 px", "Dark for a moment after you lay it, then armed with a slow cyan blink. It flashes white when an enemy is right over it.")}
    {t("sprites", "mine_blast", "The blast", "Large, fading to the edge", "The full blast is white in the middle and fades evenly to dark blue at its edge, the way the damage falls off. It's your color, so it never reads as a threat to you.")}
    {t("anims", "mines", "Laying and setting off", "Hold to lay", "Hold the mine key while flying for a line, or hold still for a pile. An enemy that flies right over one sets it off.", wide=True)}
  </div>
</section>

<section id="ship">
  <div class="section-head">
    <h2>Your ship</h2>
    <p class="muted">The laser charge-up, the boost flame and shield at each level, and missiles you can see on the pods. The laser's two release options are in <a href="#decisions">Your decisions</a>.</p>
  </div>
  <div class="grid">
    {t("anims", "laser_cancel", "Laser charge-up", "2 seconds, then release", "Energy streaks in from all around the ship and gathers in a growing orb at the nose, while a ring fills like a clock so you know when it's ready. You can turn but not move. Letting go early scatters the energy and keeps your charge.")}
    {t("sprites", "boost_levels", "Boost flame", "3 levels", "The main engine flame grows longer and hotter with each level. Level 3 also trails speed lines from the pods.")}
    {t("anims", "boost", "Boost and its meter", "Hold, pause, recharge", "Hold Shift and the meter drains. Let go, and after a short pause it refills.")}
    {t("sprites", "shield_levels", "Shield levels", "Shown when hit", "None to start. Level 1 is a thin, broken ring that looks fragile, level 2 is today's dashed ring, and level 3 is a solid double ring.")}
    {t("anims", "shields", "Same hits, three shields", "Level 1 breaks fast", "The same stream of hits on each level. Level 1 shatters after two, level 2 after four, and level 3 holds.")}
    {t("sprites", "missile_pods", "Missiles on the pods", "Up to 6 showing", "Each loaded missile shows as a cyan nose at the front of a pod, three a side. They launch left, right, left, so the pods empty evenly.")}
    {t("anims", "missiles", "Missile count", "On the ship and the console", "One click fires one missile. The console slot counts down, and the number turns pink at zero. Buying a salvo at the station adds 6.")}
  </div>
</section>

<section id="hud">
  <div class="section-head">
    <h2>HUD</h2>
    <p class="muted">The lower-right console, updated for the shop.</p>
  </div>
  <div class="grid">
    {t("sprites", "console_early", "Console at the start", "Auto cannon only", "You start with the auto cannon, starting armor and no shield, so the console is short: the shield reads NONE, there's no boost meter yet, and you carry one drill.")}
    {t("sprites", "console_mid", "Console mid-game", "Everything owned", "Only weapons you own appear. Missiles are selected here and show 4 left. Shield and boost show their level as pips, armor fills in 3 steps, and the tools row counts drills, mines (out of 5) and sentries you carry.")}
  </div>
</section>

<section id="keys">
  <div class="panel next">
    <h2>Keys</h2>
    <p class="muted">These are the keys you approved. The station only opens when you press E, never just by flying into it.</p>
    <ul class="keys">{keys_html}</ul>
  </div>
</section>

<section id="next">
  <div class="panel next">
    <h2>What's next</h2>
    <p>You've signed off on these, so sprint 7 now builds drills and the station shop into the game: start with one drill and the auto cannon, mine and sell, then buy drills, the sniper, missiles, the laser and health. Sprint 8 adds the upgrades, sentries and mines.</p>
    <p class="muted">Everything here is drawn by code in the repo, so changes are quick. The source is in <code>art/items.py</code>, <code>art/station.py</code> and <code>art/hud.py</code>.</p>
  </div>
</section>

</div>
<script>{JS}</script>
"""
    out = dest / "index.html"
    out.write_text(page)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
