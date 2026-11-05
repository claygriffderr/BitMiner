"""Write the art review page (index.html) next to the images made by `python -m art.build --review DIR`.

    python -m art.review_page DIR
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

CSS = """
:root {
  /* Layout: a single column of console panels on deep space, like the game's own HUD. */
  --space: #0b0a1a;
  --void: #07060f;
  --panel: #151821;
  --panel-hi: #2b313c;
  --panel-edge: #4a5262;
  --ink: #d4e2ea;
  --ink-dim: #8796a3;
  --ion: #4fd8ff;
  --ion-dim: #1f7fa8;
  --danger: #ff2f9a;
  --friend: #ff7a1a;
  --ore: #f0c235;
  --alien: #59f58a;
  --font-display: "Silkscreen", "Courier New", monospace;
  --font-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
  color-scheme: dark;
}
* { box-sizing: border-box; }
figure { margin: 0; }
body {
  background: var(--space);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.6;
}
.wrap {
  max-width: 1120px;
  margin: 0 auto;
  padding-block: 40px 80px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid;
  gap: 56px;
}
header { display: grid; gap: 14px; }
.eyebrow {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ion);
}
h1, h2, h3 { margin: 0; text-wrap: balance; font-weight: 400; }
h1 { font-family: var(--font-display); font-size: clamp(30px, 6vw, 52px); line-height: 1.05; letter-spacing: 0.02em; }
h2 { font-family: var(--font-display); font-size: clamp(20px, 3.4vw, 28px); letter-spacing: 0.03em; }
h3 { font-size: 16px; font-weight: 600; }
p { margin: 0; max-width: 68ch; }
.lead { font-size: 17px; color: var(--ink); }
.muted { color: var(--ink-dim); }
a { color: var(--ion); }
a:focus-visible, button:focus-visible { outline: 2px solid var(--ion); outline-offset: 3px; }
nav.jump { display: flex; flex-wrap: wrap; gap: 8px 18px; font-family: var(--font-mono); font-size: 13px; }
nav.jump a { text-decoration: none; border-bottom: 1px solid var(--ion-dim); }
section { display: grid; gap: 20px; }
.section-head { display: grid; gap: 8px; }
.panel {
  background: var(--panel);
  border: 1px solid var(--panel-hi);
  border-top-color: var(--panel-edge);
  border-left-color: var(--panel-edge);
  position: relative;
  min-width: 0;
}
.panel::after {
  content: "";
  position: absolute;
  top: 4px; left: 4px; width: 3px; height: 3px;
  background: var(--panel-edge);
}
.grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); }
.tile { display: grid; grid-template-rows: auto 1fr; }
.stage {
  background: var(--space);
  display: flex; align-items: center; justify-content: center;
  padding: 12px;
  border-bottom: 1px solid var(--panel-hi);
  overflow: hidden;
}
.stage img { display: block; max-width: 100%; height: auto; image-rendering: pixelated; }
.cap { padding: 14px 16px 16px; display: grid; gap: 6px; align-content: start; }
.cap .size { font-family: var(--font-mono); font-size: 12px; color: var(--ink-dim); }
.wide { grid-column: 1 / -1; }
.span2 { grid-column: 1 / -1; }
@media (min-width: 1040px) { .span2 { grid-column: span 2; } }
.mock { display: grid; gap: 10px; }
.mock .stage { padding: 0; }
.mock img { width: 100%; image-rendering: auto; }
.toggle { display: flex; gap: 6px; flex-wrap: wrap; }
.toggle button {
  font: 13px var(--font-mono);
  color: var(--ink-dim);
  background: var(--void);
  border: 1px solid var(--panel-hi);
  padding: 6px 12px;
  cursor: pointer;
}
.toggle button[aria-pressed="true"] { color: var(--ink); border-color: var(--ion); background: #0f2430; }
.decisions { display: grid; gap: 16px; }
.decision { padding: 20px; display: grid; gap: 14px; }
.decision .q { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.decision .num {
  font-family: var(--font-display);
  color: var(--danger);
  font-size: 18px;
}
.options { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); }
.option { border: 1px solid var(--panel-hi); background: var(--void); padding: 14px; display: grid; gap: 8px; align-content: start; min-width: 0; }
.option.rec { border-color: var(--ion-dim); }
.chip {
  justify-self: start;
  font: 11px var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--space);
  background: var(--ion);
  padding: 2px 7px;
}
.option img { image-rendering: pixelated; max-width: 100%; height: auto; justify-self: center; }
.swatches { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr)); }
.group { padding: 16px; display: grid; gap: 10px; align-content: start; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.sw { display: grid; grid-template-columns: 22px auto; gap: 6px; align-items: center; font: 11.5px var(--font-mono); color: var(--ink-dim); }
.sw i { width: 22px; height: 22px; display: block; border: 1px solid #ffffff22; }
ul.plain { margin: 0; padding-left: 18px; display: grid; gap: 6px; max-width: 72ch; }
.next { padding: 20px; display: grid; gap: 10px; align-content: start; }
code { font-family: var(--font-mono); font-size: 13px; color: var(--ink); background: var(--void); padding: 1px 5px; }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto; } }
"""

JS = """
document.querySelectorAll('[data-mock]').forEach(function (box) {
  var img = box.querySelector('img');
  box.querySelectorAll('button').forEach(function (btn) {
    btn.addEventListener('click', function () {
      img.src = btn.getAttribute('data-src');
      img.alt = btn.getAttribute('data-alt');
      box.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', String(b === btn)); });
    });
  });
});
"""


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def img_tag(meta: dict, kind: str, name: str, alt: str) -> str:
    folder = "img" if kind == "sprites" else "anim"
    ext = "png" if kind == "sprites" else "gif"
    w, h = meta[kind][name]
    return f'<img src="{folder}/{name}.{ext}" width="{w}" height="{h}" alt="{esc(alt)}">'


def tile(meta: dict, kind: str, name: str, title: str, size: str, text: str, wide: bool = False, alt: str | None = None,
         span2: bool = False) -> str:
    cls = " wide" if wide else (" span2" if span2 else "")
    return f"""
<figure class="panel tile{cls}" id="art-{name}">
  <div class="stage">{img_tag(meta, kind, name, alt or title)}</div>
  <figcaption class="cap"><h3>{esc(title)}</h3><span class="size">{esc(size)}</span><p class="muted">{text}</p></figcaption>
</figure>"""


def build(dest: Path) -> Path:
    meta = json.loads((dest / "meta.json").read_text())

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

    palette_html = []
    for g in meta["palette"]:
        chips = "".join(f'<span class="sw"><i style="background:{c["hex"]}"></i>{c["hex"]}</span>' for c in g["colors"])
        palette_html.append(f"""
<div class="panel group"><h3>{esc(g['group'])}</h3><p class="muted">{esc(g['blurb'])}</p><div class="chips">{chips}</div></div>""")

    page = f"""<title>BitMiner Art Review</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&family=Silkscreen&display=swap">
<style>{CSS}</style>
<div class="wrap">

<header>
  <span class="eyebrow">Sprint 1 · Art direction · Round 2</span>
  <h1>BitMiner art review</h1>
  <p class="lead">Every sprite, effect and HUD piece for the first playable version, drawn on the game's 640×360 pixel grid and shown together in two mock fights. This round adds the changes from your notes, shown first. Leave a comment on anything you want changed.</p>
  <nav class="jump" aria-label="Sections">
    <a href="#changes">What changed</a><a href="#fights">Mock fights</a><a href="#decisions">Your decisions</a><a href="#palette">Palette</a>
    <a href="#yours">Your side</a><a href="#enemies">Enemies</a><a href="#world">World</a>
    <a href="#effects">Effects</a><a href="#hud">HUD</a><a href="#next">What's next</a>
  </nav>
</header>

<section id="changes">
  <div class="section-head">
    <h2>What changed</h2>
    <p class="muted">Your four notes from round 1, plus one fix that came out of them. Both mock fights below are updated to match.</p>
  </div>
  <div class="grid">
    {tile(meta, "anims", "guard_ram", "Guard ram: steel scoop", "Folds out, glints, then the dash", "The red outline is gone. Before a ram, the guard folds out a steel scoop like a bulldozer blade: the wings swing out, then the blade pushes forward on two arms and glints as it locks. The red lane still marks the dash, and the visor still turns pink.")}
    {tile(meta, "sprites", "guard_scoop", "The scoop, step by step", "Shown 4× larger", "Idle guard, then the three steps of the scoop folding out. The steel is brighter and shinier than your ship's drab grey and keeps the enemies' dark outline, so it still reads as theirs.", span2=True)}
    {tile(meta, "anims", "mothership_laser", "Mothership aims, then locks", "Tracks you, freezes, fires", "While the laser charges, the mothership turns to follow you, slowly enough that a hard strafe pulls the lane off you. When it locks, it freezes, the lane goes solid and flashes, and the HUD says LASER LOCKED. Then you have a moment to get out before it fires.", wide=True, alt="Mothership turning to track the player, locking, and firing after the player dodges")}
    {tile(meta, "sprites", "hud_boss", "Mothership health bar", "Bottom centre, only when you're close", "Appears when you get within range of the mothership and fades when you leave. Health just knocked off by your hits flashes in your pale cyan before it drains.", wide=True)}
    {tile(meta, "anims", "enemy_turns", "Enemy diagonals (fix)", "Eight directions", "To make the scoop face the player on a diagonal, enemies now turn the same way your ship does, with square pixels. They still snap between eight directions with hard turns, and the diagonals no longer need hand-drawn frames.", wide=True)}
  </div>
</section>

<section id="fights">
  <div class="section-head">
    <h2>Mock fights</h2>
    <p class="muted">Each mock is a full 1080p frame: the 640×360 game screen scaled up three times, with glow on anything that gives off light. Switch on the CRT filter to compare the optional scanline look.</p>
  </div>
  {mock("defend_the_drill", "Defending the drill", "Mid-game. You strafe left while firing at an infantry formation. The middle guard has turned to face you and folded out its steel scoop to ram (red lane), a sentry shoots down a tank missile, and the friendly faction has dropped a shield powerup and a safe zone. Off-screen arrows point to more enemies and to your base.")}
  {mock("mothership_assault", "Attacking the mothership", "Late game. The mothership has turned to track you and its laser has locked, so the lane is solid red and the HUD tells you to clear it. You're close, so its health bar shows at the bottom. Infantry pour out of the hangar bays while turrets and missile racks fire. Your hull is low, so its bar turns red.")}
</section>

<section id="decisions">
  <div class="section-head">
    <h2>Your decisions</h2>
    <p class="muted">Locked in from round 1. These carry through every sprint from here on.</p>
  </div>
  <div class="panel next">
    <ul class="plain">
      <li><strong>Ship turning:</strong> smooth, so your ship always points exactly at your mouse.</li>
      <li><strong>Explosions:</strong> in the owner's colors. Enemies burst green and purple, enemy weapons pink and red, and yours cyan.</li>
      <li><strong>Resources:</strong> gold.</li>
      <li><strong>HUD:</strong> keep the shield bar, wave countdown, credits and ore, lives and the BASE pointer, and add a mothership health bar.</li>
    </ul>
  </div>
</section>

<section id="palette">
  <div class="section-head">
    <h2>Palette</h2>
    <p class="muted">Each color does one job. Brighter glow means more danger: enemy shots and warnings glow hardest, your shots glow softly, and the backdrop never glows.</p>
  </div>
  <div class="swatches">{''.join(palette_html)}</div>
</section>

<section id="yours">
  <div class="section-head"><h2>Your side</h2><p class="muted">Drab gunmetal with a light outline, so your hardware never blends in with enemies.</p></div>
  <div class="grid">
    {tile(meta, "sprites", "player", "Ship, sentry and drill", "17×17, 9×11 and 13×13 px", "The ship's pods hold the side and retro thrusters, and its canopy is the only bright spot. Sentries turn to aim. The drill sits on an asteroid and shows its ore in a gold hopper.")}
    {tile(meta, "anims", "turn_smooth", "Turning", "Smooth, any angle", "Your ship turns to any angle so it always points exactly at your mouse, and its pixels turn as crisp squares.")}
    {tile(meta, "anims", "boosters", "Boosters", "Four ion flames", "W fires the main engine, S fires the retro thrusters on the front of the pods, and A and D fire the side thrusters. Several can burn at once.")}
    {tile(meta, "anims", "drill", "Drill at work", "Blinks while mining", "The status light blinks while the drill collects ore.")}
    {tile(meta, "sprites", "home_base", "Home base", "82×66 px", "Docking ring with four landing pads, a lit hub, and solar wings. This is where you trade ore for credits and buy upgrades.")}
    {tile(meta, "sprites", "shots_player", "Your shots", "1×5, 3×12 and 3×9 px", "Automatic bolts, sniper streaks and homing missiles. All of them are pale cyan, so they never read as danger.")}
    {tile(meta, "sprites", "weapon_icons", "Weapon icons", "13×13 px each", "Used in the HUD's weapon slots. The laser icon shows the beam's sweep point.")}
  </div>
</section>

<section id="enemies">
  <div class="section-head"><h2>Enemies</h2><p class="muted">Hacker green and purple, with glowing green eyes. Each class has its own silhouette, so you can read a swarm at a glance.</p></div>
  <div class="grid">
    {tile(meta, "sprites", "enemies", "Infantry, guard and rapid assault", "11×10, 15×12 and 9×12 px", "Infantry are small and simple so they read in swarms. Guards are wide, flat shield-walls that fold out a steel scoop before a ram. Rapid assault ships are thin darts that read as fast.", wide=True)}
    {tile(meta, "sprites", "tank", "Tank (first boss)", "29×29 px", "A front plow, a big green core and two missile pods. The pink tips show the pods are loaded.")}
    {tile(meta, "sprites", "shots_enemy", "Enemy shots", "5×5, 1×6 and 5×9 px", "Infantry fire slow pink orbs, rapid assault ships fire fast red needles, and tanks fire homing missiles that you can shoot down.")}
    <div class="panel next"><h3>Ram, turns and the mothership</h3><p class="muted">The guard's ram, the eight-direction turns and the mothership with its laser are shown in <a href="#changes">What changed</a> at the top of the page.</p></div>
  </div>
</section>

<section id="world">
  <div class="section-head"><h2>World</h2><p class="muted">Asteroids stay dark and muted with a lit rim so their edges read. Everything from the friendly faction is orange.</p></div>
  <div class="grid">
    {tile(meta, "sprites", "asteroids", "Asteroids", "14 to 96 px across", "Lit from the top left, with craters. Gold flecks mark ore worth mining. Larger rocks hold more ore.", wide=True)}
  </div>
  <div class="grid">
    {tile(meta, "sprites", "powerups", "Powerups", "15×15 px", "Shield, repair, damage boost and speed boost capsules. Their edges blink so they stand out.")}
    {tile(meta, "anims", "friendly", "Safe zone and powerups", "Edge crawls slowly", "The friendly faction's safe zone is a dashed orange ring with a faint fill.")}
  </div>
</section>

<section id="effects">
  <div class="section-head"><h2>Effects</h2><p class="muted">Sprint 3 animates every weapon against every enemy. These are the base pieces.</p></div>
  <div class="grid">
    {tile(meta, "anims", "explosions", "Explosions", "Six frames each", "Flash, fireball, bloom, break-up, smoke and embers.")}
    {tile(meta, "anims", "hits", "Hits on your ship", "Shield, then armor", "A cyan arc flashes where your shield takes a hit. Once the shield is down, grey sparks show hits landing on armor.")}
  </div>
</section>

<section id="hud">
  <div class="section-head"><h2>HUD</h2><p class="muted">An arcade ship console laid out the way you described, in the game's own pixel font. The new mothership health bar is in <a href="#changes">What changed</a>.</p></div>
  <div class="grid">
    {tile(meta, "sprites", "hud_console", "Ship console", "Lower right", "The current weapon sits on top in a large slot that fills with its ammo or reload state. Your other weapons sit beside it, smaller and grey. Below that are shield, hull and armor, then lives and the ship icon.")}
    {tile(meta, "sprites", "hud_console_low", "Console in trouble", "Low hull, sniper reloading", "When hull is low its bar turns red. Here the sniper is selected and about half reloaded.")}
    {tile(meta, "sprites", "hud_radar", "Radar (upgrade)", "Lower left", "Green dots are enemies, the purple bar is the mothership, the cyan square is your base, gold marks are drills, and pink dots are incoming missiles.")}
    {tile(meta, "sprites", "hud_top", "Top bar", "Top of the screen", "Credits and ore on the left and the wave countdown in the middle. Alerts such as LASER LOCKED appear under the countdown.", wide=True)}
  </div>
</section>

<section id="next">
  <div class="panel next">
    <h2>What's next</h2>
    <p>Once you've signed off on the look, sprint 2 is the flight test: a Windows build you can download and run, where you fly among asteroids and tune thrust, turn rate, drift and mass with on-screen sliders.</p>
    <p class="muted">Everything here is generated from code in the repo, so changes are quick. The source lives in <code>art/</code> and the game-ready sprites in <code>assets/sprites/</code>.</p>
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
