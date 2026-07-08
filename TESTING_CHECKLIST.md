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

---

## Ice Blocks Feature (`claude/ice-blocks-feature`)

### Normal Roll
- [ ] Click Build! on map tab → POST to `/build/roll` succeeds
- [ ] `count-ice_blocks` increments by the roll value (1-19)
- [ ] Toast shows "🧊 ×N ice blocks! (roll R)"
- [ ] Energy decreases by 5
- [ ] Button returns to enabled state after response

### Energy Gate
- [ ] With energy < 5 and no free rolls: clicking Build! shows "Need 5 energy to build! Rest at the hotel."
- [ ] Energy is NOT consumed when the gate fires (player stays at current energy)
- [ ] Build! button re-enables after the error toast

### Crit (Roll 20)
- [ ] Rolling a natural 20 grants 20 ice blocks
- [ ] Toast includes "CRITICAL! 5 free rolls!"
- [ ] Button turns red and shows "Build!\n(5 free)"
- [ ] `penguins.build_free_rolls` persists to 5 in the DB (survives page reload)
- [ ] `ice_crit` sound fires exactly once

### Free Roll Consumption
- [ ] With free rolls > 0: clicking Build! costs 0 energy
- [ ] `build_free_rolls` decrements by 1 per click
- [ ] Button label updates to "(N free)" after each click
- [ ] On last free roll (`normal_return: true`): toast appends "Free rolls used up."
- [ ] `ice_normal_return` sound fires on normal_return
- [ ] Button reverts to blue after free rolls are exhausted
- [ ] After exhausting free rolls: next click costs 5 energy again

### Sound Regression
- [ ] No double-sound firing on Build! click (only `ice_roll`/`ice_crit`/`ice_normal_return` — not also `uiClick`)
- [ ] No MutationObserver, fetch-interceptor, or delegated-click-listener triggers a second sound

### Map Layout Stability
- [ ] Build! button appears on the map tab without causing any layout reflow or resize of the `.map-area` container
- [ ] World map and other map-tab elements are unaffected
- [ ] Toggling between tabs (map → village → map) leaves button in correct state

### Resource Bar
- [ ] 🧊 ice_blocks item appears in the resource bar
- [ ] `updateResourceBar()` fetches and populates `count-ice_blocks`
- [ ] Hovering 🧊 icon shows correct tooltip text

---

## Feature Batch: Building Donations (Ice Blocks), XP on Roll, Block-Collection Animation, PNG Button Sprites

### XP on Every Roll (normal and free)
- [ ] After clicking Build!, `penguins.xp` increases by exactly the roll value (e.g. a roll of 14 → +14 XP)
- [ ] This applies on both normal rolls (energy-consuming) and free rolls (no energy cost)
- [ ] Verify via: `SELECT xp FROM penguins WHERE username='<test_user>';` before and after roll
- [ ] XP matches the `roll` value in the toast, not a fixed amount
- [ ] Level-up triggers correctly if XP crosses a threshold (check level field too)

### Block-Collection Animation
- [ ] After the d20 overlay closes (settle), 🧊 emoji particles burst from the Build! button and fly toward the ice_blocks HUD counter
- [ ] Particle count scales with the amount earned (roll 1 → 1 emoji, roll 20 → 20 emojis, capped at 20)
- [ ] ⭐ XP emoji particles also fly toward the XP bar after the same settle event
- [ ] Animations do not begin during the d20 tumble or hold phase — only after `onSettle` fires (2360 ms)
- [ ] Animations do not collide visually with d20 overlay (overlay is already hidden when animations start)
- [ ] HUD counter `count-ice_blocks` flashes `.updated` both immediately (counter text update) and again when emojis land (~800 ms later) — two flashes is correct
- [ ] On a free roll, both 🧊 and ⭐ animations still fire correctly

### PNG Button Sprites
- [ ] Build! button visually shows the blue PNG (`build_button_blue.png`) instead of the flat ice-blue circle
- [ ] Button text ("Build!" / "Build!\n(N free)") is legible on top of the PNG
- [ ] Clicking Build! when free rolls are active: button turns red and shows the red PNG (`build_button_red.png`)
- [ ] Reverting from crit (free rolls exhausted): button returns to blue PNG
- [ ] PNG scales cleanly within the 80×80 px button (no stretching/distortion) — `background-size: contain`
- [ ] At mobile breakpoint (≤600 px), button shrinks to 64×64 and PNG scales down proportionally
- [ ] Button bounding box / absolute position is unchanged from before (no map reflow)
- [ ] If the PNG files are swapped with custom art of a different aspect ratio, the button does not distort (contain preserves proportions)
- [ ] Fallback: if PNG fails to load (e.g. 404), button falls back to the flat ice-blue / red background color

### Building Ice Block Donations (pending threshold numbers)
- [ ] *(Blocked — awaiting ice_block donation threshold numbers per building/level from owner)*
- [ ] Once thresholds are set: donating ice_blocks to a supported building deducts from `resources.ice_blocks`
- [ ] Partial donation is tracked in `building_upgrades.ice_blocks_donated`
- [ ] Progress bar / donated counter in the building UI reflects partial donations
- [ ] Donating enough ice_blocks triggers automatic level-up (same as existing resources)
- [ ] `ice_blocks_donated` counter resets to 0 after level-up
- [ ] Donating when at max level returns an error: "Building is already max level."
- [ ] Donating ice_blocks to a building that doesn't require them returns an error

### Global Chat (claude/global-chat)

**Rate limit**: 5 seconds between messages per player (`_CHAT_RATE_LIMIT_SECONDS = 5`)
**Profanity filter**: hardcoded `frozenset` wordlist (word-boundary split on `\w+`; expand the set in `_CHAT_BLOCKED_WORDS` in `app.py` to add terms)
**24h cleanup**: query-time filter on `/chat/messages` + DELETE piggyback in `run_autonomous_actions` (runs every 30 min)

#### Sending a message
- [ ] Typing a message and clicking SEND (or pressing Enter) posts the message to `/chat/send`
- [ ] The new message appears in the chat panel immediately after send (re-poll fires on success)
- [ ] Messages from other players appear on the next poll cycle (≤4 s lag)
- [ ] Sender name displays as the logged-in `username`, styled in purple (#A86EFF)
- [ ] Message text wraps correctly inside the 260 px panel without horizontal overflow
- [ ] Relative timestamps update on each poll ("just now" → "Xs ago" → "Xm ago" → "Xh ago")

#### Rate-limit rejection
- [ ] Sending a second message within 5 s of the first shows the status line: "Please wait Xs before sending again."
- [ ] Waiting 5 s and re-sending succeeds
- [ ] Rate limit is per-user (different users are not blocked by each other)

#### Profanity filter rejection
- [ ] Sending a message containing a blocked word shows the status line: "⚠ Message not allowed."
- [ ] The blocked message is NOT stored in the database
- [ ] Sending a clean message immediately after works normally

#### Cross-session message visibility
- [ ] Simulate two sessions (two browsers / incognito tabs): message sent in session A appears in session B within ≤4 s
- [ ] Messages persist across page refreshes

#### 24h expiry
- [ ] Insert a test row with `created_at` set to `now - 90000` (>24 h ago) via SQLite CLI
- [ ] `/chat/messages` does NOT return the expired row
- [ ] After `run_autonomous_actions` fires, the expired row is deleted from the table

#### No map resize/reflow regression
- [ ] Opening chat panel does not change the size or position of `#map-area` or `#village-canvas`
- [ ] Build! button, world-map-btn, and d20 overlay remain at correct positions while chat panel is open
- [ ] Closing the chat panel leaves all map elements unchanged

#### Chat toggle button
- [ ] 💬 button appears top-right of the map area (z-index 62, above canvas, below d20 overlay)
- [ ] Clicking 💬 opens the panel; clicking ✕ or 💬 again closes it
- [ ] On mobile (≤768 px) the 💬 button and chat panel are hidden (map is too cramped)

#### Polling behavior
- [ ] Poll runs every 4 s when the chat panel is open AND the map tab is active
- [ ] Switching to a non-map tab pauses polling; switching back to MAP resumes it
- [ ] Polling does not fire when the panel is closed

---

## Weekly Challenge → Raid Feature (`claude/raid-join-window-ui-sgwlai`, Phases 1–5)

Run this end-to-end before flipping `weekly_raid` to `True` in production (flag is already `True` as of Phase 5 — treat this as the regression pass covering that flip). Where a real week-long cycle isn't practical to wait for, manually adjust DB timestamps / call scheduler functions directly to force each phase transition.

### Phase 1 — Challenge lifecycle & scheduling
- [ ] Monday 00:00 job creates a new `weekly_challenges` row with a valid metric_type
- [ ] Metric type does NOT repeat the previous week's metric
- [ ] `record_challenge_progress()` actually increments `current_progress` when gold is earned
- [ ] ...when resources are gathered
- [ ] ...when a monster is killed
- [ ] Progress does NOT increment for metrics that don't match the active challenge
- [ ] Friday 09:00 job: threshold met → challenge marked `succeeded`, `raid_state` row created with status `join_window`
- [ ] Friday 09:00 job: threshold NOT met → challenge marked `failed`, no `raid_state` row created, no raid icon appears
- [ ] Verify no crash/duplicate rows if the scheduler is restarted mid-week (Railway redeploy scenario)

### Phase 2 — Join window
- [ ] Join icon appears on map overlay only when raid status = `join_window`
- [ ] Icon does NOT appear when there's no active raid or challenge failed
- [ ] Map canvas does not resize/reflow when icon appears or popup opens
- [ ] Popup shows correct boss name, live participant count, reward preview text
- [ ] Joining increments participant count immediately (own client + poll-refreshed on a second browser/session)
- [ ] Duplicate join attempts (same player, double-click) do not create duplicate `raid_participants` rows
- [ ] Joining after the window closes (past Sat 00:00) is rejected
- [ ] Player who does NOT join cannot Attack once raid goes active (Phase 3 check)
- [ ] 30s poll doesn't cause noticeable performance issues with many players on map tab

### Phase 3 — Attack mechanic
- [ ] Saturday 00:00 job sets boss_max_hp correctly = participants × BOSS_HP_PER_PARTICIPANT
- [ ] Raid with 0 joiners doesn't divide/crash (min-1 floor applied)
- [ ] Build! button is replaced by Attack! exactly when raid goes active — no flicker/both-visible state
- [ ] Attack button reverts to Build! correctly once raid resolves (Phase 5)
- [ ] Non-participant attempting POST /raid/attack gets 403
- [ ] Attack while raid not active gets 409
- [ ] Energy is deducted correctly per attack (same cost as Build roll)
- [ ] Attacking with insufficient energy is blocked, same as Build
- [ ] d20 tumble animation, pop/hold/reveal, and sound all fire correctly on Attack
- [ ] Nat 20 crit triggers 5 free attacks (not free Builds) and confetti
- [ ] Boss HP bar updates in real time after each attack, both for the attacker and other players polling
- [ ] Boss HP bar never goes negative / visually clamps at 0
- [ ] XP is awarded on every roll, normal and free
- [ ] calculate_attack_damage() at roll=1 and roll=20 produce sane, non-trivial values relative to boss HP

### Phase 4 — Lootboxes (test standalone, then via Phase 5)
- [ ] grant_lootbox() creates correct number of unopened rows
- [ ] Lootboxes appear in inventory panel, unopened state visually distinct from opened
- [ ] Open action rejected for non-owner
- [ ] Open action rejected for already-opened lootbox
- [ ] Drop rates roughly match configured curve over a large sample (e.g. script-open 200 test lootboxes, tally rarity distribution)
- [ ] Gold awarded is within 50–100 range
- [ ] Resource awarded is within 1–50 range, resource type is valid
- [ ] Gear awarded actually gets added to player inventory/gear table correctly
- [ ] Open animation (gift emoji pop/explode) plays, then reveals all 3 rewards
- [ ] Opening from inventory later (not immediately after grant) works identically

### Phase 5 — Raid resolution
- [ ] Boss defeated mid-attack: resolve_raid() fires synchronously in the same request, no need to wait for next poll
- [ ] Timeout path: Monday 00:00 job correctly resolves any still-active raid as "failed"/timeout
- [ ] Leaderboard ranks participants correctly by total_damage_dealt DESC
- [ ] Ties in damage are handled without crashing (define/verify tiebreak behavior — e.g. join order)
- [ ] Rank 1/2/3 receive exactly 3/2/1 lootboxes respectively
- [ ] Ranks 4+ receive resources scaled by exact rank position (spot-check a few ranks against calculate_rank_reward())
- [ ] Reward distribution total doesn't silently fail for large participant counts (test with 20+ simulated participants)
- [ ] Chat system posts the system message announcing outcome, correct boss name, correct top 3
- [ ] GET /raid/results/{raid_id} works for a player who was NOT actively attacking when it ended
- [ ] GET /raid/results/{raid_id} is publicly viewable (not owner-restricted) by another logged-in player
- [ ] Results modal displays correctly, own row highlighted if player participated
- [ ] Results modal does NOT appear/error for players who never joined this raid
- [ ] After resolution, Attack button and boss HP bar disappear; map overlay reverts to Build! (if new challenge active) or nothing
- [ ] Next Monday's new challenge starts cleanly with no leftover state from the resolved raid

### Cross-cutting
- [ ] Full cycle test: force through all 4 timestamps in sequence (Mon start → Fri succeed → Sat start → boss defeated OR Mon timeout) without manual DB poking mid-flow, to catch any transition gaps
- [ ] Mobile: join popup, Attack button, boss HP bar, and results modal all render correctly on mobile layout (fullscreen overlay conventions)
- [ ] Sound: Attack button and lootbox-open both route through GameSounds interceptor correctly, no duplicate/missing sounds
- [ ] `weekly_raid` feature flag OFF: confirm zero visible UI changes anywhere (icon, button, bar all hidden) before go-live
- [ ] Balance-pass flags still open: BOSS_HP_PER_PARTICIPANT, weekly challenge thresholds, LOOTBOX_DROP_RATES, calculate_rank_reward() curve — note these are placeholder values, not bugs, if flagged during testing
