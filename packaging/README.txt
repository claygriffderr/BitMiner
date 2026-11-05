BitMiner - Flight Test
======================

Double-click BitMiner.exe to fly.

If Windows shows "Windows protected your PC", click "More info", then "Run anyway".
The game isn't signed with a publisher certificate yet, so Windows doesn't recognise it.

Controls
--------
W            Main booster (forward)
S            Retro boosters (brake / reverse)
A / D        Side boosters (strafe left / right)
Mouse        Aim. The ship turns toward the cursor.
Tab          Show or hide the tuning panel
C            CRT filter on or off
R            Put the ship back at the start
F11          Full screen
Esc          Quit

Tuning
------
Drag a slider (or scroll the mouse wheel over it) while you fly. Changes take effect
straight away and are saved to flight_tuning.json in this folder. When the ship feels
right, send that file back so its numbers become the game's defaults.

Each slider has a small tick showing where its default sits. Reset puts them all back.

- Main / side / retro thrust: how hard each booster pushes.
- Turn rate: how fast the ship swings toward the mouse.
- Drift damper: how quickly speed bleeds off on its own. 0 means pure drift.
- Top speed: above this, speed is pulled back quickly (a soft cap, not a wall).
- Mass: heavier ships speed up more slowly, hit rocks harder and get knocked around less.
- Bounce: how springy hits against asteroids are.
- Camera lead: how far the camera looks ahead in the direction you're drifting.
- Screen shake: how hard the screen shakes on impacts.

If something goes wrong, the game writes bitminer_error.log next to BitMiner.exe.
