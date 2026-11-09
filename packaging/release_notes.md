Sprint 8: **upgrades, sentries and mines**. Build up a defended base and try every item and upgrade. The combat sandbox, flight test and weapon gallery are still in the menu.

**Download:** `BitMiner-UpgradesAndDefenses-windows.zip` below. Unzip it anywhere (Desktop or Downloads is fine), open the `BitMiner` folder and double-click `BitMiner.exe`.

If Windows shows *"Windows protected your PC"*, click **More info**, then **Run anyway**. The game isn't signed with a publisher certificate yet, so Windows doesn't recognise it.

**Menu:** Secure the Base is picked to start with. Use the mouse or the arrow keys and Enter. Esc goes back to the menu from anywhere.

**New in Secure the Base:**
- **Test credits:** press **=** (or keypad **+**) for 1,000 credits, so you can try everything without the grind. It works with the station open too. (`test_credits` in `shop.json`; set it to 0 to turn it off.)
- **Upgrades, 3 levels each, bought in order** on the station's Ship and Weapons pages. The pips on each row show the level you own, and the panel shows what the next level changes.
  - **Shield** (300 / 900 / 2,700): soaks up 40 / 100 / 180 before your hull takes hits. Stronger shields wait a little longer before they recharge, and recharge a little more slowly. The bubble round your ship looks different at each level.
  - **Armor** (300 / 900 / 2,700): your hull blocks 40% / 60% / 80% of each hit (16% to start), but the ship gets heavier.
  - **Boost** (250 / 750 / 2,250): hold **Shift** while flying for 20% / 40% / 80% more thrust and top speed. A full meter lasts 2 seconds and refills after a 2 second pause. The BST bar on the console drains as you use it.
  - **Auto cannon** (200 / 600 / 1,800) and **sniper** (300 / 900 / 2,700): x1.2 / x1.44 / x1.73 damage. Sniper rounds also go through 3 / 5 / 7 enemies.
- **Explosive mines** (40 each, carry up to 5, Tools page): hold **G** to lay them just behind your ship, one after another. Hold still for a pile, or keep flying for a line. Each arms after a moment and goes off when an enemy flies right over it. The blast is big and hurts every enemy in it, most at the middle, and never hurts you, your drills or your sentries.
- **Sentries** (Tools page): auto 800 / 1,200 / 1,800, sniper 1,600 / 2,400 / 3,600 and missile 3,200 / 4,800 / 7,200. Pick the tier with **A** and **D** (or click its card); a higher tier has more health. Press **R** to set down the next sentry you carry where your ship is (not on an asteroid or crowding the station, a drill or another sentry; you can have 16 out). It never moves, turns to the nearest enemy it can see in range and fires its own cyan shots: diamond pellets, ring-headed sniper rounds or salvos of four missiles. Enemies can damage and destroy it, and they raid sentries they come across, just like drills. Sentry kills pay credits too, and don't give away where you are.
- **Kills pay:** infantry 3, rapid assault 4, guard 5, tank 50, straight into your credits with a gold "+3" where it died. There's no free drill when you run out: kills are how you buy one back.
- The console shows your shield and boost levels, the armor bar, and how many mines and sentries you carry. The help line along the bottom lists the new keys.

**Keys in Secure the Base:** WASD fly, mouse aims, click fires, 1 to 4 pick the weapon, **Shift** boost, **F** drill, **G** mines (hold), **R** sentry, **E** station, **=** test credits, N next wave, P pause, Backspace new game, Esc menu.

**At the station:** 1, 2 and 3 pick the Ship, Weapons and Tools pages, W and S pick a row, A and D pick a sentry's tier, Enter buys, E or Esc closes it. The mouse works too.

**Not yet:** balance is sprint 9, so sentries are strong for now and the economy is slow without test credits. The mothership still doesn't fight back and home base can't be destroyed.

**Everywhere:** Tab shows or hides the tuning panel, C toggles the CRT filter, F11 is full screen. Your tuning saves to `flight_tuning.json` next to `BitMiner.exe`. Each game is written to a `playdata` folder next to it, for the adaptive AI in a later sprint.

Every price, upgrade level, starting item and kill reward is in `bitminer/data/shop.json`, and the mine and sentry numbers are in the `mines` and `sentries` blocks of `bitminer/data/combat.json`.

This build is made automatically from the latest code.
