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
5. Full game loop
6. Adaptive AI
7. Polish and share

## Play it

Windows: download `BitMiner-WeaponGallery-windows.zip` from the
[weapon-gallery release](https://github.com/claygriffderr/BitMiner/releases/tag/weapon-gallery), unzip it
and run `BitMiner.exe`. Each push to a sprint branch rebuilds it. (The sprint 2 build stays on the
[flight-test release](https://github.com/claygriffderr/BitMiner/releases/tag/flight-test).)

From source (Python 3.13):

```
pip install -r requirements.txt
python -m bitminer                       # the menu
python -m bitminer --mode gallery        # straight into the weapon gallery
```

The menu leads to the flight test and the weapon gallery; Esc goes back to it.

- Flight test: W main booster, S retro, A and D strafe, mouse to aim, R puts the ship back.
- Weapon gallery: Left and Right pick a weapon or enemy attack, Up and Down the target or defense,
  Space replays, F switches between the auto pilot and free-fly (WASD, mouse, click to fire, 1 to 4
  picks the weapon).
- Everywhere: Tab shows the tuning panel, C toggles the CRT filter, F11 is full screen. Slider
  changes save to `flight_tuning.json`.

Starting values for the sliders live in `bitminer/data/tuning.json`, and every weapon, enemy and
defense number in `bitminer/data/weapons.json`, so none of them are fixed in code.

## Tech

Python with the [Arcade](https://api.arcade.academy/) library, rendered at 640×360 and scaled up
with pixel-perfect integer scaling.

- `bitminer/flight.py`: the ship's flight model (mass, boosters, turning, damper, soft speed cap)
- `bitminer/field.py`: the wrap-around asteroid field and its collisions
- `bitminer/graphics/`: the renderer (outline after rotation, bloom, parallax backdrop, CRT filter)
- `bitminer/combat/`: the combat simulation (shots, missiles, beams, hits, shields, explosions)
- `bitminer/gallery/`: the weapon gallery's scenes and the director that plays them
- `bitminer/views/`: the menu, flight test and gallery screens
- `bitminer/ui/`: the tuning panel and HUDs, in the pixel font
- `bitminer/settings.py`: the tuning sliders and where your settings are saved

```
pip install -r requirements-dev.txt
python -m pytest                         # unit tests (BITMINER_GL_TESTS=1 also drives the window)
python -m bitminer --selftest            # quick check with no window
python packaging/build.py                # BitMiner.exe and its zip, in dist/
python packaging/render_check.py dist/BitMiner shots --no-mesa   # run the built game, print what it drew
python -m bitminer --record gifs/ --size 1280x720                 # a GIF of every gallery scene
```

## Art

Every sprite, effect and HUD piece is drawn in code, so a color or shape change is a quick edit
followed by a rebuild.

```
pip install -r requirements.txt
python -m art.build                       # sprites into assets/sprites, mock screens into assets/mockups
python -m art.build --review review/      # also the boards and GIFs for the art review page
python -m art.review_page review/         # the review page itself, review/index.html
```

- `art/palette.py`: every color and what it means
- `art/sprites.py`: ships, enemies, shots, effects and world pieces
- `art/hud.py`: the ship console, radar and top bar
- `art/mockups.py`: the two mock fight screens
- `art/pix.py`: the pixel toolkit (outlines, shading, rotation, glow and the CRT filter)
