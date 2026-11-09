# BitMiner

A retro 8-bit space shooter for Windows where the enemy learns how you play.

You fly a mining ship across a huge wrap-around asteroid field, set drills on asteroids, haul
what they collect back to base, and spend it on weapons, armor and sentries. Every wave launches
from an enemy mothership whose commander studies your habits and builds each attack to beat
you. Destroy the mothership to win.

## Status

Early development, built in short sprints with a playable or reviewable demo at the end of each:

1. Art direction
2. Flight test
3. Weapon effects gallery
4. Combat
5. Map, mines and the hunt
6. Station and item art (design review)
7. Drills and the station shop
8. Upgrades, sentries and mines
9. The full loop
10. Adaptive AI
11. Polish and share

## Play it

Windows: download `BitMiner-DrillsAndShop-windows.zip` from the
[drills-and-shop release](https://github.com/claygriffderr/BitMiner/releases/tag/drills-and-shop), unzip it
and run `BitMiner.exe`. Each push to a sprint branch rebuilds it. (Earlier sprints stay on the
[secure-the-base](https://github.com/claygriffderr/BitMiner/releases/tag/secure-the-base),
[combat-sandbox](https://github.com/claygriffderr/BitMiner/releases/tag/combat-sandbox),
[weapon-gallery](https://github.com/claygriffderr/BitMiner/releases/tag/weapon-gallery) and
[flight-test](https://github.com/claygriffderr/BitMiner/releases/tag/flight-test) releases.)

From source (Python 3.13):

```
pip install -r requirements.txt
python -m bitminer                       # the menu
python -m bitminer --mode campaign       # straight into Secure the Base
python -m bitminer --mode sandbox        # straight into the combat sandbox
python -m bitminer --mode gallery        # straight into the weapon gallery
```

The menu leads to Secure the Base, the flight test, the combat sandbox and the weapon gallery; Esc
goes back to it.

- Secure the Base: the game itself, so far. A wrap-around map ten times the sandbox each way (the
  MAP SIZE slider changes it on a new game), home base and its space station where you start, and
  the mothership across the map. You start with one drill, the auto cannon and no shield. F sets a
  drill on an ore asteroid next to you (several can share one); a drill fills its gold bar and
  waits for you to fly past and load it, and you sell the ore at home base. Asteroids crack as they
  empty, then crumble away and take their drills with them. Press E at the station to open its
  shop (the game keeps running): more drills, the sniper, missiles six at a time, the laser and
  hull repairs. Every enemy you destroy pays credits on the spot, more for the dangerous ones. The laser charges for 2 seconds while you hold fire. Enemies only know where you
  are while one of them can see you: then they all do, and when they lose you they search where you
  were last seen, then go home. They raid drills they come across. Each wave launches once only a
  few of the last are still out. Dim arrows at the screen edge point at home base and each drill,
  with the drill's gold bar and health beside it.
- Combat sandbox: wave after wave of infantry squads, guards and rapid assault ships in the asteroid
  field. WASD flies, the mouse aims, click fires, 1 to 4 (or the mouse wheel, Q and E) picks the
  weapon, N calls the next wave early, P pauses, Backspace starts a fresh fight. Going down costs
  nothing: you are back a moment later, blinking.
- Flight test: W main booster, S retro, A and D strafe, mouse to aim, R puts the ship back.
- Weapon gallery: Left and Right pick a weapon or enemy attack, Up and Down the target or defense,
  Space replays, F switches between the auto pilot and free-fly (WASD, mouse, click to fire, 1 to 4
  picks the weapon).
- Everywhere: Tab shows the tuning panel, C toggles the CRT filter, F11 is full screen. Slider
  changes save to `flight_tuning.json`.

Starting values for the sliders live in `bitminer/data/tuning.json`, every weapon, enemy and
defense number in `bitminer/data/weapons.json`, and how enemies fight and when waves arrive in
`bitminer/data/combat.json` (with drills, the mothership's waves and how enemies search in its `drills`,
`fleet` and `hunt` blocks), the station shop's prices, your starting kit and what each kill pays in `bitminer/data/shop.json`,
and the big map in `bitminer/data/map.json`, so none of them are fixed in code. Each game or sandbox fight is also written
to a `playdata` folder next to the settings file, for the adaptive AI to learn from later.

## Tech

Python with the [Arcade](https://api.arcade.academy/) library, rendered at 640×360 and scaled up
with pixel-perfect integer scaling.

- `bitminer/flight.py`: the ship's flight model (mass, boosters, turning, damper, soft speed cap)
- `bitminer/field.py`: the wrap-around asteroid field, its collisions and a grid for quick lookups
- `bitminer/sector.py`: the big map's layout and the belts, clusters and rocks that fill it
- `bitminer/graphics/`: the renderer (outline after rotation, bloom, parallax backdrop, CRT filter)
- `bitminer/combat/`: the combat simulation (shots, missiles, beams, hits, shields, explosions,
  bumping), the enemy brains and waves (`ai.py`), what the enemy knows and the mothership's waves
  (`hunt.py`), your weapons (`arsenal.py`), the station shop (`shop.py`), and the sandbox and
  Secure the Base without graphics (`sandbox.py`, `campaign.py`)
- `bitminer/playdata.py`: the play log
- `bitminer/gallery/`: the weapon gallery's scenes and the director that plays them
- `bitminer/views/`: the menu, Secure the Base, flight test, combat sandbox and gallery screens
- `bitminer/ui/`: the tuning panel, HUDs, Secure the Base's console and the station screen, in the pixel font
- `bitminer/settings.py`: the tuning sliders and where your settings are saved

```
pip install -r requirements-dev.txt
python -m pytest                         # unit tests (BITMINER_GL_TESTS=1 also drives the window)
python -m bitminer --selftest            # quick check with no window
python packaging/build.py                # BitMiner.exe and its zip, in dist/
python packaging/render_check.py dist/BitMiner shots --no-mesa   # run the built game, print what it drew
python -m bitminer --record gifs/ --size 1280x720                 # a GIF of every gallery scene
python -m bitminer.gallery.review_page gifs/                      # and the review page, gifs/index.html
```

## Art

Every sprite, effect and HUD piece is drawn in code, so a color or shape change is a quick edit
followed by a rebuild.

```
pip install -r requirements.txt
python -m art.build                       # sprites into assets/sprites, mock screens into assets/mockups
python -m art.build --review review/      # also the boards and GIFs for the art review page
python -m art.review_page review/         # the review page itself, review/index.html
python -m art.review6 review6/            # the sprint 6 station and item review page, review6/index.html
```

- `art/palette.py`: every color and what it means
- `art/sprites.py`: ships, enemies, shots, effects and world pieces
- `art/hud.py`: the ship console, radar, top bar, shop icons and drill arrows
- `art/items.py`: drills and their gold bar, cracking asteroids, sentries, mines, and the ship's
  boost, shield levels, loaded missiles and laser charge-up
- `art/station.py`: the space station screen and its upgrade panels
- `art/mockups.py`: the two mock fight screens
- `art/pix.py`: the pixel toolkit (outlines, shading, rotation, glow and the CRT filter)
