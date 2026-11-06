Sprint 5: **Secure the Base**, the first build of the real game mode. A much bigger map, mines you set on asteroids, and enemies that have to find you. The combat sandbox, flight test and weapon gallery are still in the menu.

**Download:** `BitMiner-SecureTheBase-windows.zip` below. Unzip it anywhere (Desktop or Downloads is fine), open the `BitMiner` folder and double-click `BitMiner.exe`.

If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**. The game isn't signed with a publisher certificate yet, so Windows doesn't recognise it.

**Menu:** Secure the Base is picked to start with. Use the mouse or the arrow keys and Enter. Esc goes back to the menu from anywhere.

**Secure the Base:**
- **The map** is 10 times wider and taller than the sandbox, and wraps at every edge. It has asteroid belts, clusters, big landmark rocks and loose rocks everywhere. You start next to home base; the mothership sits on the far side of the map. A dim arrow at the screen edge always points home.
- **Mines:** fly up to an asteroid that glints with ore (24 px or bigger) and press **F** to set a mine on it. You can run 4 at once. A mine digs ore into its hold until its asteroid runs dry (bigger asteroids last much longer), or until enemies destroy it (it has a lot of health). Fly over a mine to load its ore, and fly to home base to sell it for credits. Each mine shows a health bar and an ore bar, and gets its own dim arrow at the screen edge with the same two bars beside it. The arrow turns pink while the mine is under attack.
- **Enemies have to find you.** The top bar says HIDDEN or SPOTTED. When any enemy sees you (or you hit one), they all know where you are. Get out of sight for a few seconds and they lose you: they fly to where you were last seen, search around it, and eventually give up and fly home to the mothership. Waves that launch while you are hidden head for where you were last seen. Enemies that fly past one of your mines remember it and come back to raid it.
- **Waves:** the first leaves the mothership after 30 seconds. Each next wave launches once only a few enemies of the last are still out, with a warning but no countdown. It's a long flight from the mothership, so the early game is quiet: time to set mines. **N** still calls the next wave straight away.
- Going down costs the ore you were carrying, and you start again at home base. Credits don't buy anything yet: the shop, defenses and a mothership you can destroy come in sprint 6.
- **MAP SIZE** is a new slider at the bottom of the tuning panel (Tab), from 3x to 16x. It takes effect when you start a new game with **Backspace**.

**Combat sandbox, flight test and weapon gallery:** unchanged from sprint 4.

**Everywhere:** Tab shows or hides the tuning panel, C toggles the CRT filter, F11 is full screen. Your tuning saves to `flight_tuning.json` next to `BitMiner.exe`. Each game is written to a `playdata` folder next to it, for the adaptive AI in a later sprint.

Every number for the map is in `bitminer/data/map.json`, and for mines, waves and how enemies search in the `mines`, `fleet` and `hunt` blocks of `bitminer/data/combat.json`.

This build is made automatically from the latest code.
