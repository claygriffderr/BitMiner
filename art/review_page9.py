"""Write the sprint 9 review page (index.html) next to the images made by `art.review9`.

    python -m art.review9 DIR     # builds the images, then this page
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .review_page import CSS, JS, esc, img_tag, tile
from .review_page6 import EXTRA_CSS


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

    picks = [("lasso", "Lasso"), ("ring", "Collector ring")]
    buttons = "".join(
        f'<button type="button" aria-pressed="{"true" if i == 0 else "false"}" data-src="mock/station_{p}.png" '
        f'data-alt="Station screen, Tools page, {lbl} selected">{lbl}</button>' for i, (p, lbl) in enumerate(picks))
    station_mock = f"""
<figure class="panel mock" data-mock id="mock-station">
  <div class="stage"><img src="mock/station_lasso.png" width="1920" height="1080" alt="Station screen, Tools page, Lasso selected"></div>
  <figcaption class="cap">
    <div class="toggle" role="group" aria-label="Selected row">{buttons}</div>
    <h3>In the shop</h3>
    <p class="muted">Both go at the bottom of the Tools page. The lasso works like the other upgrades: 3 levels bought in order, and each step card shows the biggest rock that level can tow. Here you own level 1, and level 2 is next. The ring is a single buy with no levels. Prices: lasso 500, 700 and 900 (your numbers, kept low so lots of small rocks pay off early), ring 4,000.</p>
  </figcaption>
</figure>"""

    def option(rec: bool, title: str, media: str, text: str) -> str:
        chip = '<span class="chip">Your pick</span>' if rec else ""
        return f"""<div class="option{' rec' if rec else ''}">{chip}<h3>{esc(title)}</h3><div class="imgs">{media}</div><p class="muted">{text}</p></div>"""

    beam_q = f"""
<div class="panel decision" id="q-beam">
  <div class="q"><span class="num">1</span><h3>Which look for the tow beam?</h3></div>
  <p class="muted">Both are in your cyan, both get thicker at each level, and both show the grip ring locked round the rock. The animation is the same tow in each look.</p>
  <div class="options">
    {option(True, "A. Steady beam", img_tag(meta, "anims", "tow_a", "Towing a rock with a steady cyan beam") + img_tag(meta, "sprites", "beam_a", "Steady beam at levels 1 to 3"), "A solid bar of light with bright pulses running toward your ship, so it reads as pulling. It matches your words, a fixed-length force beam, and stays clear at speed and in a busy fight.")}
    {option(False, "B. Energy chain", img_tag(meta, "anims", "tow_b", "Towing a rock with a chain of energy links") + img_tag(meta, "sprites", "beam_b", "Energy chain at levels 1 to 3"), "Separate glowing links, like a rope made of light. It has more character, but the links flicker as they move, and at level 1 the chain is thin enough to lose against the stars.")}
  </div>
</div>"""

    place_q = f"""
<div class="panel decision" id="q-place">
  <div class="q"><span class="num">2</span><h3>Where does the collector ring go?</h3></div>
  <p class="muted">The ring is big, about two thirds of the screen's height, so it needs open space.</p>
  <div class="options">
    {option(True, "A. Wherever you place it", img_tag(meta, "sprites", "placing", "Placing the ring: room to place it, and rocks in the way"), "After you buy it, press T to place it where your ship is. An outline shows where it will go: cyan when there's room, pink when rocks are in the way. You can set it up next to a rich field, but a ring far from home is harder to defend. It stays put once placed.")}
    {option(False, "B. Always beside home base", "", "The ring appears next to home base when you buy it. Simpler and easier to defend, but every rock has to be towed home, so the trips stay long on a big map.")}
  </div>
</div>"""

    keys = [("Q", "Grab the rock nearest you with the lasso"), ("Q again", "Let go. The rock keeps its speed"),
            ("T", "Place the collector ring where you are"), ("R inside the ring", "Mount a sentry on the next free mount"),
            ("R elsewhere", "Place a sentry where you are, as now"), ("E at the station", "Open the station screen")]
    keys_html = "".join(f"<li><kbd>{esc(k)}</kbd><span class=\"muted\">{esc(v)}</span></li>" for k, v in keys)

    page = f"""<title>BitMiner Hauling Art</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&family=Silkscreen&display=swap">
<style>{CSS}{EXTRA_CSS}
.decision .imgs img + img {{ margin-top: 6px; }}
</style>
<div class="wrap">

<header>
  <span class="eyebrow">Sprint 9 · Lasso and collector ring · Round 1</span>
  <h1>Hauling art</h1>
  <p class="lead">Everything new for the lasso and the collector ring, drawn on the game's 640×360 grid before any of it goes into the game: the tow beam, throwing rocks, the ring holding rocks and selling their gold, sentries mounted on it, and the ring breaking. You've approved it and picked the steady beam and placing the ring anywhere. Since then, drills float free when their rock crumbles, and the lasso is cheaper.</p>
  <nav class="jump" aria-label="Sections">
    <a href="#field">In the field</a><a href="#decisions">Your decisions</a><a href="#lasso">Lasso</a>
    <a href="#ring">Collector ring</a><a href="#station">Shop</a><a href="#keys">Keys</a><a href="#next">What's next</a>
  </nav>
</header>

<section id="field">
  <div class="section-head">
    <h2>In the field</h2>
    <p class="muted">A mid-game moment with the ring set up. Switch on the CRT filter to compare the optional scanline look.</p>
  </div>
  {mock("in_game", "Running a ring", "The ring holds three rocks, each with a drill. A drill on the bottom-right rock has just filled and sold itself: the nearest collector node glows gold and +40 CR pops up. Three sentries are mounted on the ring (sniper right, auto cannon bottom, missile left) and fire at a raid coming from the bottom right. The top mount is still empty. The ring's health bar sits above it, at 80% after earlier raids, and a few broken panels show the damage. You're boosting in from the right with a fourth rock on a level 3 beam, its drill still digging.")}
</section>

<section id="decisions">
  <div class="section-head">
    <h2>Your decisions</h2>
    <p class="muted">You picked A for both, so that's what goes into the game.</p>
  </div>
  <div class="decisions">{beam_q}{place_q}</div>
</section>

<section id="lasso">
  <div class="section-head">
    <h2>Lasso</h2>
    <p class="muted">A beam of fixed length from the back of your ship. The rock can never reach you, and it keeps its momentum when you let go.</p>
  </div>
  <div class="grid">
    {t("sprites", "targeting", "Picking a rock", "Brackets on the nearest rock", "Bright brackets show the rock Q would grab. If it's too heavy for your lasso level, the brackets go grey and say which level you need.")}
    {t("sprites", "throw_speed", "Fast rocks hurt", "Speed lines", "A thrown rock trails pale speed lines only while it's moving fast enough to do damage. Without them it just bumps things, so you can tell at a glance.")}
    {t("anims", "throw", "Throwing", "Swing, let go, hit", "Swing the rock round and let go at the right moment. It flies on in a straight line, knocks out the first enemy it hits, and comes off that hit slowed down, so one throw usually takes out one or two enemies.", wide=True)}
  </div>
</section>

<section id="ring">
  <div class="section-head">
    <h2>Collector ring</h2>
    <p class="muted">A big hoop in home base's grey with cyan lights. Four collector nodes sit on the inside and four sentry mounts on the outside. A faint dashed field just inside the hoop holds the rocks in place.</p>
  </div>
  <div class="grid">
    {t("sprites", "ring_states", "Empty, full and damaged", "About 330 px across", "Empty, holding four rocks (there's room for four of the largest), and badly damaged. As its health drops, panels break and go dark and its health bar turns pink.", wide=True)}
    {t("anims", "ring_fill", "Filling it", "Tow in, let go", "Tow a rock inside and let go. The field catches it and eases it into a free spot. When a drill inside fills, its gold flies to the nearest node and turns straight into credits.", wide=True)}
    {t("sprites", "mounts", "Sentry mounts", "Four per ring", "Mounted sentries are just the turret on the ring's mount, with no platform and no health bar of their own. They're part of the ring.", span2=True)}
    {t("anims", "ring_break", "When the ring breaks", "Its sentries go with it", "Press R inside the ring and the sentry mounts on the next free mount. Enemy hits on the ring or on its turrets wear down the ring's health. At zero it breaks apart and its mounted sentries are lost. The rocks and their drills stay where they were, unprotected.")}
    {t("sprites", "shop_icons", "Shop icons", "13 px", "The lasso is your ship's tail with a beam to a rock. The ring shows the hoop with rocks inside.")}
    {t("anims", "loose_drill", "Drills float free", "New: nothing is used up", "When a worked-out rock crumbles, its drill pops off and drifts away slowly, blinking cyan. Fly over it to put it back in your hold, then set it on a fresh rock. That makes lots of drills on small rocks worth it.", wide=True)}
  </div>
</section>

<section id="station">
  <div class="section-head">
    <h2>Shop</h2>
    <p class="muted">Switch the selected row with the buttons under the screen.</p>
  </div>
  {station_mock}
</section>

<section id="keys">
  <div class="panel next">
    <h2>Keys</h2>
    <p class="muted">Proposed keys. Q and T aren't used yet, and R is the sentry key you already know.</p>
    <ul class="keys">{keys_html}</ul>
  </div>
</section>

<section id="next">
  <div class="panel next">
    <h2>What's next</h2>
    <p>Sprint 10 builds the lasso, the collector ring and loose drills into the game. Every number (beam length, the rock size each level can tow, throw damage and the speed it needs, ring health, prices) goes in the data files and the in-game tuning menu. The full loop and balancing come after that.</p>
    <p class="muted">Everything here is drawn by code in the repo, so changes are quick. The source is in <code>art/haul.py</code>.</p>
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
