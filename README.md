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

## Tech

Python with the [Arcade](https://api.arcade.academy/) library, rendered at 640×360 and scaled up
with pixel-perfect integer scaling.

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
