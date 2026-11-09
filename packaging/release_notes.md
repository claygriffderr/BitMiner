Sprint 7: **drills and the station shop**. Mine, sell and buy your way up from the auto cannon. The combat sandbox, flight test and weapon gallery are still in the menu.

**Download:** `BitMiner-DrillsAndShop-windows.zip` below. Unzip it anywhere (Desktop or Downloads is fine), open the `BitMiner` folder and double-click `BitMiner.exe`.

If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**. The game isn't signed with a publisher certificate yet, so Windows doesn't recognise it.

**Menu:** Secure the Base is picked to start with. Use the mouse or the arrow keys and Enter. Esc goes back to the menu from anywhere.

**Secure the Base:**
- **You start small:** one drill, the auto cannon, starting armor and no shield. The console in the lower right only shows what you own.
- **Drills:** fly up to an asteroid that glints with ore (24 px or bigger) and press **F** to set a drill on the side facing you. Several drills can share an asteroid, and they all dig from the same ore. A drill's gold bar fills as it digs; when it's full the bar pulses, its tip light turns gold and it waits for you. Fly over it to load the ore, and fly to home base to sell it.
- **Asteroids wear out:** as one empties, cracks spread from its drills and its gold flecks fade. Once it's empty and you've picked up the last ore, it crumbles away and takes its drills with it. Enemies can also destroy drills. Each drill's health bar is always shown above it.
- **The space station** is at home base. Fly up to it and press **E** to open its shop (it never opens just because you fly into it). The game keeps running, so clear the area first: it warns you when enemies are near. **1**, **2** and **3** pick the Ship, Weapons and Tools pages, **W** and **S** pick a row, **Enter** buys, and **E** or **Esc** closes it. The mouse works too.
- **On sale:** drills (150), the sniper (200), missiles (60 for 6, up to 18), the laser (1,500) and health (100, patches half your hull). Shield, armor, boost, weapon upgrades, mines and sentries show as coming soon: they arrive in sprint 8.
- **Kills pay:** every enemy you destroy drops credits straight into your account the moment it goes down, more for the dangerous ones: infantry 3, rapid assault 4, guard 5, tank 50. A gold "+3" rises where it died. That's how you buy a drill back if you lose them all.
- **Missiles** show on your ship's pods as they load. A click fires one; hold to keep firing. The pods reload from the missiles you carry.
- **The laser charges first:** hold fire for 2 seconds. Your ship stops and can only turn while energy gathers at its nose. Let go early and it cancels without using a charge. Then the beam opens with a burst and lasts as long as before, so you can sweep it across a group. (The combat sandbox's laser charges the same way.)
- Dim arrows at the screen edge point home and at each drill, with a tiny copy of the drill's gold bar and health beside it. A drill's arrow turns pink while it is under attack.
- Enemies still have to find you, and the first wave leaves the mothership after 30 seconds. **N** calls the next wave straight away. Going down costs the ore you were carrying, and you start again at home base.

**Combat sandbox, flight test and weapon gallery:** unchanged, apart from the laser's charge-up in the sandbox.

**Everywhere:** Tab shows or hides the tuning panel, C toggles the CRT filter, F11 is full screen. Your tuning saves to `flight_tuning.json` next to `BitMiner.exe`. Each game is written to a `playdata` folder next to it, for the adaptive AI in a later sprint.

Every price, starting item and kill reward is in `bitminer/data/shop.json`, drill numbers in the `drills` block of `bitminer/data/combat.json`, and the laser's charge-up in `bitminer/data/weapons.json`.

This build is made automatically from the latest code.
