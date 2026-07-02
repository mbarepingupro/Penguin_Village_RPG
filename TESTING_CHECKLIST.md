# Alpha Smoke-Test Checklist

Estimated time: ~10 minutes with a running local server and one test account.
All DB paths assume SQLite file at `penguin_village.db` in the project root.

---

## Pre-flight

- [ ] Server is running (`flask run` or `python app.py`)
- [ ] At least two test accounts exist (create a second via a different Twitch login or via DB insert)
- [ ] SQLite browser / `sqlite3` CLI available for streak and debug steps

---

## Flow 1 — Twitch OAuth Login + Character Creation

- [ ] **1a. OAuth redirect** — Click "Login with Twitch"; confirm redirect to `https://id.twitch.tv/oauth2/authorize` and return to `/auth/callback` without a 500 error.
  > How to verify: After redirect, you should land on the character-creation screen (new user) or the home map (returning user). A 500 here indicates a Twitch API call failure.

- [ ] **1b. Character creation saves correctly** — Submit name (letters/digits/underscores only, ≤16 chars), a color from the palette, a shape (normal/tall), and one trait from each of Social / Interest / Quirk.
  > How to verify: `SELECT penguin_name, penguin_color, penguin_shape, trait_social, trait_interest, trait_quirk, character_created FROM penguins WHERE username='<test_user>';` — all six columns should be non-NULL and `character_created=1`.

- [ ] **1c. Resources row exists** — After creation, resources table has a row for the user.
  > How to verify: `SELECT * FROM resources WHERE username='<test_user>';` — row should exist with all resource columns.

---

## Flow 2 — Start a Job + Collect Resources

- [ ] **2a. Start job** — Open any building that has a job (e.g. Fish Market / Sea Lion Pit), click the work button.
  > How to verify: `SELECT job, job_started FROM penguins WHERE username='<test_user>';` — `job` should be set to the building ID and `job_started` to a recent Unix timestamp.

- [ ] **2b. Collect after wait (or time-skip)** — Wait at least 1 minute, then collect. Alternatively, set `job_started` to `strftime('%s','now') - 3600` in the DB to simulate 1 hour worked, then collect.
  > How to verify: Confirm gold/resource numbers in the UI increase. Cross-check: `SELECT gold, fish, herbs FROM resources WHERE username='<test_user>';` before and after collect. Also confirm `job` resets to NULL: `SELECT job FROM penguins WHERE username='<test_user>';`

- [ ] **2c. 12-hour cap** — Set `job_started` to 15 hours ago in the DB; collect; confirm rewards are capped at 12 hours' production, not 15.
  > How to verify: The endpoint uses `min(elapsed_secs / 3600.0, 12.0)` — reward should be exactly 12 × per-hour rate for that building.

---

## Flow 3 — Play a Mini-game

- [ ] **3a. Energy deducted on start** — Open a building with a mini-game (e.g. Sea Lion Pit → Rune Memory), start the game.
  > How to verify: `SELECT energy FROM penguins WHERE username='<test_user>';` before and after clicking play — should decrease by 10.

- [ ] **3b. Score submission grants rewards** — Complete the mini-game (or let it time out).
  > How to verify: Check that gold and/or resources in the UI increase after the result screen. `SELECT gold FROM resources WHERE username='<test_user>';` before and after.

- [ ] **3c. Blocked while job running** — Start a passive job, then try to start a mini-game.
  > How to verify: Server should return an error ("you're already working") and energy should NOT decrease.

---

## Flow 4 — Fight a Monster

- [ ] **4a. Win resolves without error** — Open combat tab, fight the lowest-level monster available.
  > How to verify: Fight result modal appears with VICTORY or DEFEAT (no blank screen / JS error in console). Network tab shows `POST /combat/fight` returns `200` with `{"status": "success", "victory": true/false}`.

- [ ] **4b. Win writes gold + XP** — On a victory, confirm gold and XP increase.
  > How to verify: `SELECT gold FROM resources WHERE username='<test_user>';` and `SELECT xp, level FROM penguins WHERE username='<test_user>';` before and after.

- [ ] **4c. Energy deducted regardless of outcome** — Win or lose, energy should decrease by the monster's `energy_cost`.
  > How to verify: `SELECT energy FROM penguins WHERE username='<test_user>';` — should be lower after the fight.

- [ ] **4d. Loss gives consolation XP only** — On a loss (force by fighting a high-CP monster with 1 CP), confirm only XP increases, not gold or resources.
  > How to verify: `SELECT gold FROM resources WHERE username='<test_user>';` should be unchanged; `xp` in penguins should increase slightly.

---

## Flow 5 — Equip Combat Item + Wear Cosmetic (Live Update Check)

- [ ] **5a. Equip a combat item** — Open Inventory → gear tab → click EQUIP on a combat item.
  > How to verify: `SELECT equipped FROM gear WHERE username='<test_user>' AND id=<gear_id>;` should be `1`. Sidebar CP number should update without a page refresh. Map avatar should reflect the change.

- [ ] **5b. Equip is slot-exclusive** — Equip a second item in the same slot (e.g. two helmets).
  > How to verify: Only one item per slot should show `equipped=1`. The previously equipped item should auto-unequip: `SELECT id, slot, equipped FROM gear WHERE username='<test_user>' AND slot='helmet';`

- [ ] **5c. Wear a cosmetic item independently** — Click WEAR on a cosmetic item (outfit, hat, etc.). Confirm the penguin avatar on the map and in the inventory preview updates without a page refresh.
  > How to verify: `SELECT worn FROM gear WHERE username='<test_user>' AND id=<cosmetic_id>;` should be `1`. Previous cosmetic in the same visual area should be `worn=0`.

- [ ] **5d. Equip and Wear are independent** — A worn cosmetic does not affect the equipped combat item and vice versa.
  > How to verify: Both `equipped=1` and `worn=1` can coexist on the same item if it's dual-purpose, or separately on different items with no interference.

---

## Flow 6 — Donate to a Building + Upgrade Trigger

- [ ] **6a. Donation deducts resource** — Open a building, donate 10 fish (or any resource in the next-level requirement).
  > How to verify: `SELECT fish FROM resources WHERE username='<test_user>';` decreases by the donated amount. `SELECT fish_donated FROM building_upgrades WHERE building_id='<building_id>';` increases.

- [ ] **6b. Progress bar updates in UI** — After donating, the progress bar in the building modal should reflect the new donation total without a full page reload.
  > How to verify: Visually confirm. Also: `SELECT fish_donated FROM building_upgrades WHERE building_id='<building_id>';` matches what the UI shows.

- [ ] **6c. Upgrade fires at threshold** — Fill a building's donation bar to 100% by setting `building_upgrades` columns to just under the threshold in the DB, then donate the remainder.
  > How to verify: `SELECT level FROM building_upgrades WHERE building_id='<building_id>';` increments. All donation columns reset to 0. A level-up toast appears in the UI.

---

## Flow 7 — Visit Another Player's Igloo

- [ ] **7a. Visit increments relationship count** — Log in as user A, visit user B's igloo.
  > How to verify: `SELECT interaction_count, relationship_level FROM relationships WHERE (username1='<A>' AND username2='<B>') OR (username1='<B>' AND username2='<A>');` — `interaction_count` should increase by 1.

- [ ] **7b. Visitor receives gold reward** — After visiting, user A's gold increases.
  > How to verify: `SELECT gold FROM resources WHERE username='<A>';` before and after.

- [ ] **7c. Daily cap enforced** — Try visiting the same igloo 6 times in one day.
  > How to verify: The 6th visit (same host, same day) should return an error. Cap is 5 unique visits per day total (any hosts); a second visit to the same host in the same day is also blocked regardless of total count.

---

## Flow 8 — Login Streak: Day 1 and Day 7

**Setup for day-7 test (DB manipulation required — no debug route exists):**

```sql
-- Set streak to 6 and yesterday's date so the next home-page load advances to 7
UPDATE login_streaks
   SET current_streak = 6,
       last_login_date = date('now', '-1 day')
 WHERE username = '<test_user>';
```

Then load `GET /` (the home page) while logged in as `<test_user>`.

- [ ] **8a. Day-1 streak** — First login of the day (new user or streak reset). Confirm streak counter shows 1.
  > How to verify: `SELECT current_streak, last_login_date FROM login_streaks WHERE username='<test_user>';`

- [ ] **8b. Day-7 milestone fires** — After the DB manipulation above, load the home page and confirm the streak milestone modal appears showing 300 gold + fish + herbs reward.
  > How to verify: `SELECT current_streak FROM login_streaks WHERE username='<test_user>';` should be 7. `SELECT gold FROM resources WHERE username='<test_user>';` should be 300 higher. A new gear item should appear: `SELECT * FROM gear WHERE username='<test_user>' ORDER BY obtained_at DESC LIMIT 1;`

- [ ] **8c. Day-7 streak achievement unlocks** — The `streak_7` achievement should be awarded.
  > How to verify: `SELECT * FROM achievements WHERE username='<test_user>' AND achievement_id='streak_7';` — row should exist. An additional 200 gold should be credited (achievement reward on top of milestone reward).

---

## Found Issues

The following bugs were identified while building this checklist. **Do not fix in this pass — log only.**

### HIGH

**[BUG-1] Streak milestone skipped when triggered via `/welcome-back` route**
- File: `app.py:4244`
- If a player's first page load of the day is `/welcome-back/<username>` (rather than `/`), `update_login_streak` runs and advances the counter, but `award_streak_milestone` is never called. The next load of `/` will see `is_new_day=False` and skip it too. Day-7 gear + gold + resources are silently lost.
- Impact: Any player landing on the welcome-back screen on their 7th (or 14th, 21st, 28th) day loses the milestone reward entirely.

**[BUG-2] `/minigame/complete` has no proof-of-start guard**
- File: `app.py:6758`
- A client can POST directly to `/minigame/complete` without calling `/minigame/start`, bypassing the 10-energy deduction. No session nonce or start-token links the two calls.
- Impact: Free mini-game rewards without spending energy.

### MEDIUM

**[BUG-3] Multiple routes accept `username` from request body with no session verification**
- Files: `app.py:2448, 2485, 2876, 3258, 3299, 4529`
- Routes `/work/start`, `/work/collect`, `/combat/fight`, `/gear/equip`, `/gear/wear`, `/building/donate` all trust `username` from the JSON body. Any authenticated user can perform these actions as any other user.
- Impact: Authenticated users can steal resources, fight for others, or equip gear on other accounts.

**[BUG-4] `/gear/equip` has no feature-flag guard; `/gear/unequip` does**
- Files: `app.py:3255, 3280`
- When `FEATURES["gear_equip"] = False`, equipping works but unequipping returns "coming soon". Players can equip items but are then stuck — they can never unequip.

### LOW

**[BUG-5] `/auth/callback` will 500 on Twitch API error**
- File: `app.py:1950`
- `user_resp.json()["data"][0]["login"]` is not wrapped in try/except. If Twitch returns an error response or empty `data` array (rate limit, bad token, service outage), the server returns an unhandled 500 with a full traceback visible to the user.

**[BUG-6] `/minigame/complete` will 500 on non-integer `score` string**
- File: `app.py:6763`
- `int(data.get("score", 0))` raises `ValueError` if `score` is a non-numeric or float string (e.g. `"99.5"`). No try/except around this conversion.

**[BUG-7] `igloo/visit` gold reward bypasses `add_gold()` (inconsistent pattern)**
- File: `app.py:3505`
- Gold is written via `UPDATE resources SET gold=gold+? ...` rather than `add_gold()`. Functionally correct (ensure_resources is called first), but `total_gold_collected` is updated separately, creating two code paths for gold that must be kept in sync manually.
