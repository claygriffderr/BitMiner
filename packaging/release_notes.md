Sprint 10: **the lasso and the collector ring**. Tow asteroids around, throw them at enemies, and set up a ring that sells your drills' ore by itself. The combat sandbox, flight test and weapon gallery are still in the menu.

**Download:** `BitMiner-LassoAndRing-windows.zip` below. Unzip it anywhere (Desktop or Downloads is fine), open the `BitMiner` folder and double-click `BitMiner.exe`.

If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**. The game isn't signed with a publisher certificate yet, so Windows doesn't recognise it.

**Menu:** Secure the Base is picked to start with. Use the mouse or the arrow keys and Enter. Esc goes back to the menu from anywhere.

**New in Secure the Base:**
- **Lasso** (Tools page, 3 levels: 500 / 700 / 900). Fly near an asteroid and brackets show the one you'd grab: bright if your lasso can tow it, grey (with the level you need) if it's too big. Level 1 tows small rocks, level 2 medium, level 3 the largest. Press **Q** to grab it: a steady cyan beam holds it at a fixed distance behind your ship, so it can never hit you. Big rocks are heavy and slow you down. Press **Q** again to let go: the rock keeps its speed. A rock moving fast trails pale speed lines, and while it has them it hurts any enemy it hits (more for heavier, faster rocks) and comes off the hit slower, so one throw usually takes out one or two. Kills with rocks pay credits like any other.
- **Collector ring** (Tools page, 4,000, one at a time). Hold **T** to see where it would go, centred on your ship: cyan when there's room, pink when asteroids are in the way. Let go of **T** to place it. Tow up to 4 asteroids inside and let go: the ring catches each one and holds it still. When a drill on a held rock fills up, its ore sells by itself: a gold spark flies to the nearest collector node and the credits pop up. You never have to fly the ore home.
- **Sentries on the ring:** press **R** inside the ring and the next sentry you carry goes on its next free mount (top, right, bottom, left). Mounted sentries have no health of their own: hits on them hurt the ring, and they break when the ring breaks. With all 4 mounts full, R places sentries the usual way.
- **Enemies raid the ring** like drills and sentries, and their shots hit its band. It has a health bar over its top mount. Repair it from its row at the station (300 for half its health). If it's destroyed, its sentries go with it, the asteroids and drills stay where they were, and you can buy a new one.
- **Drills aren't used up any more.** When a worked-out asteroid crumbles, its drills pop off and float away slowly, blinking cyan. Fly over one to put it back in your hold. A cyan arrow at the screen edge points to each one.
- **Two new sliders** in the tuning panel (Tab): **TOW WEIGHT** (how heavy a towed rock feels; lower tows big rocks more easily) and **THROW POWER** (how hard thrown rocks hit; 0 makes them harmless).

**Keys in Secure the Base:** WASD fly, mouse aims, click fires, 1 to 4 pick the weapon, **Q** lasso (grab / let go), **T** collector ring (hold, then let go to place), **Shift** boost, **F** drill, **G** mines (hold), **R** sentry, **E** station, **=** test credits, N next wave, P pause, Backspace new game, Esc menu. Q and T aren't on the help line (it's full); the prompt at the bottom of the screen shows them when they apply.

**At the station:** 1, 2 and 3 pick the Ship, Weapons and Tools pages, W and S pick a row, A and D pick a sentry's tier, Enter buys, E or Esc closes it. The mouse works too.

**Not yet:** balance is the next sprint (the full loop), so the economy is slow without test credits (press **=**). The mothership still doesn't fight back and home base can't be destroyed.

**Everywhere:** Tab shows or hides the tuning panel, C toggles the CRT filter, F11 is full screen. Your tuning saves to `flight_tuning.json` next to `BitMiner.exe`. Each game is written to a `playdata` folder next to it, for the adaptive AI in a later sprint.

Every price and upgrade level (the lasso's levels and the ring's price and repair) is in `bitminer/data/shop.json`. How the lasso and ring behave (beam length, grab reach, throw damage and the speed it needs, ring health, how fast it pulls rocks in) is in the `haul` block of `bitminer/data/combat.json`, and how loose drills drift is in its `drills` block.

This build is made automatically from the latest code.
