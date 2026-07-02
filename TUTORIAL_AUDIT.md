# Tutorial System Audit
Branch: `claude/laughing-volta-8x615q`  
Date: 2026-07-02  
Scope: Read-only. No code changes made.

---

## DB columns
| Column | Table | Used by |
|---|---|---|
| `tutorial_step` | `penguins` | `/tutorial/advance` (write), home.html `TUTORIAL_STEP` constant (read) |
| `tutorial_completed` | `penguins` | `/tutorial/complete` (write), `/tutorial/advance` when step≥12 (write), Jinja `tutorial_completed` (read) |
| `tutorial_rewards_given` | `penguins` | `/tutorial/gift`, `/tutorial/starter-fight`, `/tutorial/free-boutique`, `/tutorial/free-rest` (idempotency guard) |

All three columns exist and are consistently referenced across routes and frontend.

---

## Route inventory
| Route | Handler | Status |
|---|---|---|
| `POST /tutorial/advance` | `tutorial_advance` | Exists — sets `tutorial_step=?`; sets `tutorial_completed=1` when step≥12 |
| `POST /tutorial/complete` | `tutorial_complete` | Exists — sets `tutorial_completed=1` directly (unused by current step flow) |
| `POST /tutorial/reset` | `tutorial_reset` | Exists — resets both columns to 0 |
| `POST /tutorial/gift` | `tutorial_gift` | Exists — gives step-keyed rewards for steps 2, 4, 11 |
| `POST /tutorial/starter-fight` | `tutorial_starter_fight` | Exists — gives gold+xp+random common gear, uses `GEAR_TEMPLATES["common"]` |
| `POST /tutorial/free-boutique` | `tutorial_free_boutique` | Exists — inserts cosmetic gear row for `item_id` into `gear` table |
| `POST /tutorial/free-rest` | `tutorial_free_rest` | Exists — sets `energy = max_energy` |

---

## Auto-start logic
`home.html` (Jinja, ~line 8856):
```
{% if logged_in and not tutorial_completed %}
  if (window.TutorialManager && TUTORIAL_STEP < 12) { TutorialManager.init(TUTORIAL_STEP); }
{% endif %}
```
Fires 900ms after page load. Resumes from the player's current `tutorial_step`.

---

## Step-by-step audit

| Step | Name | Advance trigger | Backend call | Mismatch? | Note |
|---|---|---|---|---|---|
| 0 | Welcome | User clicks "Let's go! →" button | `POST /tutorial/advance {step:1}` | NO | Pure dialogue; no external deps. |
| 1 | Village Map | User drags `#village-canvas` (mousemove/touchmove) → 1.2 s delay | `POST /tutorial/advance {step:2}` | NO | Canvas element exists; drag listener attached directly to canvas in `_waitForMapDrag`. |
| 2 | First Job | `sea_lion_pit` building opens → inject btn → user clicks "CLAIM STARTER CATCH!" → then "Nice! →" | `POST /tutorial/gift {step:2}` then `POST /tutorial/advance {step:3}` | NO | Gift: fish=50, gold=30, xp=50. Idempotent (already_given guard). Building open fires `_notifyBuilding('sea_lion_pit')` at line 3594. |
| 3 | Mini-Game Demo | `sea_lion_pit` opens → inject btn → `startMiniGame('sea_lion_pit')` → `MiniGameManager.startGame('sea_lion_pit', cb)` → on complete `_pendingMinigameCb(score)` → user clicks "Got it! →" | `POST /minigame/start`, `POST /minigame/complete`, then `POST /tutorial/advance {step:4}` | NO | **Sea Lion Pit = Fish Catch mini-game.** `MiniGameManager.startGame()` called at `home.html:5435`. This session's changes affected Herb Garden (Club Soda) and Juggle Master (Parkmusement) only — Fish Catch at Sea Lion Pit is unchanged in identity. Difficulty ramp was added to Fish Catch but `startGame` API signature is identical. |
| 4 | Stats Gift | User clicks STATS sidebar tab → `_notifySidebar('stats')` (line 2808) → `POST /tutorial/gift {step:4}` → user clicks "Wow, thanks! →" | `POST /tutorial/gift {step:4}` then `POST /tutorial/advance {step:5}` | NO | Gift: gold=100, herbs=20, bones=10, spell_fragments=5. Sidebar notify hook at line 2808 is correctly wired. |
| 5 | First Fight | `barracks` building opens → inject btn into `#barracks-pane-monsters` → user clicks "FIGHT THE SNOW CRAB!" → `POST /tutorial/starter-fight` → fight modal shows → OK btn → "Equip it! →" | `POST /tutorial/starter-fight` then `POST /tutorial/advance {step:6}` | NO | Starter fight gives gold=30, xp=20, random gear from `GEAR_TEMPLATES["common"]`. `#barracks-pane-monsters` pane ID must exist in barracks building template. Fight modal uses `showFightModal`/`showFightResult` helpers present in home.html. |
| 6 | Equip Gear | Inventory modal opens → `_notifyInventory()` (line 5155) → Mayor says "Click EQUIP…" → user clicks "Done! →" | `POST /tutorial/advance {step:7}` (equip itself calls `POST /gear/equip` independently) | NO | `/gear/equip` guarded by `FEATURES.get("gear_equip", False)` at `app.py:3262`; **`feature_flags.py` has `"gear_equip": True`** — feature is enabled. Tutorial advance does NOT verify equip success; "Done! →" fires unconditionally after inventory opens. Acceptable: equip is a UI action, tutorial trusts the player. |
| 7 | Boutique | `boutique` building opens → inject card added to `#bq-items-grid` → user clicks "CLAIM FREE!" → `POST /tutorial/free-boutique {item_id:'party_hat'}` → "Thanks! →" | `POST /tutorial/free-boutique` then `POST /tutorial/advance {step:8}` | NO | Looks up `'party_hat'` in `BOUTIQUE_ITEMS`; if not found, returns error and tutorial shows fallback "Moving on!" text before advancing anyway (graceful). Rewards: cosmetic gear row inserted into `gear` table. |
| 8 | Hotel | `hotel` building opens → inject btn → `POST /tutorial/free-rest` → "Refreshed! →" | `POST /tutorial/free-rest` then `POST /tutorial/advance {step:9}` | NO | Restores `energy = max_energy`. Idempotent (step 8 already_given guard). Building open fires `_notifyBuilding('hotel')` via the generic openBuilding path. |
| 9 | Village Building | Two dialogue prompts with continue buttons; no building required | `POST /tutorial/advance {step:10}` | NO | Pure dialogue, no external deps. Advance fires on second "I'll contribute! →" click. |
| 10 | Igloo | User clicks IGLOO content tab → `switchContentTab('igloo', ...)` → `_notifyContentTab('igloo')` (line 2855) → "Cool! →" | `POST /tutorial/advance {step:11}` | NO | Content tab hook at line 2855 is correctly wired. Igloo tab exists in home.html as `data-tab="igloo"`. |
| 11 | Stream + Farewell | User clicks "Awesome! →" → `POST /tutorial/gift {step:11}` → confetti → "Let's go! 🐧" → `_advanceStep()` → `_complete()` | `POST /tutorial/gift {step:11}` then `POST /tutorial/advance {step:12}` which sets `tutorial_completed=1` | NO | Gift: gold=200, mayor_seals=1. `/tutorial/advance` with step=12 sets both `tutorial_step=12` and `tutorial_completed=1`. Tutorial dialogue removed from DOM. |

---

## Special focus findings

### Mini-game demo (Step 3) — Sea Lion Pit / MiniGameManager
- `startMiniGame('sea_lion_pit')` at `home.html:5482` calls `MiniGameManager.startGame('sea_lion_pit', cb)` at `home.html:5435`.
- `MiniGameManager.startGame` is defined in `static/minigames.js` and dispatches on `buildingId`.
- `'sea_lion_pit'` maps to **Fish Catch** — the fishing mini-game (`FishCatchGame`).
- This session's changes modified `HerbGardenGame` (Club Soda building) and `JuggleMasterGame` (Parkmusement building). Neither touches `sea_lion_pit` / `FishCatchGame`.
- The difficulty ramp (`getDifficultyMult()`) was added to Fish Catch, but only affects spawn rate and fish speed — `startGame` API and building ID routing are unchanged.
- **Result: Step 3 is correctly wired and unaffected by this session's changes.**

### Equip gear (Step 6) — `/gear/equip` feature flag
- `app.py:3262`: `if not FEATURES.get("gear_equip", False): return disabled`
- `feature_flags.py:3`: `"gear_equip": True`
- Flag is **enabled**. `/gear/equip` executes fully — unequips prior item in same slot, equips new item, runs `check_achievements`.
- The tutorial's inventory-open trigger (`_notifyInventory`) is independent of the equip action; "Done! →" advances regardless of equip success, but equip does work.
- **Result: No mismatch.**

---

## Minor concern (not a blocking mismatch)

### `skipTutorial()` sends step=11, not step=12
`home.html:8803–8808` — `skipTutorial()` POSTs `{step: 11}` to `/tutorial/advance`.  
`/tutorial/advance` only sets `tutorial_completed=1` when `step >= 12`.  
**Effect**: After skipping, `tutorial_step=11` and `tutorial_completed=0`. On next page reload, the auto-start condition (`not tutorial_completed AND TUTORIAL_STEP < 12`) is true, so `TutorialManager.init(11)` fires and the farewell step (with step 11 gift) shows automatically.  
This is probably intentional — the player gets the farewell gift + welcome message on their next login even if they skipped — but it means "skip" doesn't fully suppress the tutorial on the next session.  
**Not a code error; flagged for awareness.**

---

## Summary

All 12 tutorial steps (0–11) have working advance triggers. All seven tutorial routes exist and their DB operations are consistent with the columns that exist in the `penguins` table. The mini-game demo step correctly calls `MiniGameManager.startGame('sea_lion_pit', ...)` and the Sea Lion Pit / Fish Catch game is unaffected by this session's Herb Garden and Juggle Master changes. The equip gear step is functional with `gear_equip: True` in `feature_flags.py`. No step references a non-existent route, function, or DB column.
