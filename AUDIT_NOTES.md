# Audit Notes — Reward System Bugs

## 1. Login Streak — 7-Day Gear Reward Never Fires

**File:Line:** `app.py:1221–1237` (`award_streak_milestone`), `app.py:1208–1213` (`_MILESTONE_TIERS`)

**Root cause:** `award_streak_milestone` grants gold and resources but never calls `generate_gear_drop()` and never inserts into the `gear` table. `_MILESTONE_TIERS` has no `gear` key. The streak modal HTML (`home.html` ~line 2709) has rarity CSS classes already defined, confirming gear display was designed into the UI but the backend half was never implemented.

**Suggested fix:**
- In `award_streak_milestone` (after line 1232, before `log_event`): map cycle (7/14/21/28) to a gear tier (1–4), call `gear = generate_gear_drop(tier)`, insert into `gear` table using the same pattern as `app.py:2918–2925` (monster combat drop), and add `"gear_drop": {name, rarity, slot}` to the return dict.
- In `home.html` JS (~line 8067): read `sr.gear_drop` from the response and populate `sm-item-name` / `.sm-rarity` with the existing CSS classes.

---

## 2. Daily Mission XP Bypasses Level-Up Check

**File:Line:** `app.py:1288` (inside `advance_mission`)

**Root cause:** Mission completion XP is written with a raw `UPDATE penguins SET xp=xp+?` instead of `award_xp()`. `award_xp` (lines 1519–1542) is the only function that detects level-ups and calls `apply_level_rewards`. Players who level up entirely via mission XP never receive level-up cosmetics or other level-up rewards.

**Suggested fix:** Replace line 1288:
```python
# before
db.execute("UPDATE penguins SET xp=xp+? WHERE username=?", (defn["xp"], username))
# after
award_xp(db, username, defn["xp"])
```

---

## 3. Achievement Unlock Grants No Rewards + Silently Swallows Errors

**File:Line:** `app.py:1586–1596` (`unlock` inner function inside `check_achievements`), `app.py:979–1006` (`ACHIEVEMENT_DEFS`)

**Root cause (rewards):** `unlock(aid)` inserts into the `achievements` table and logs the event but never reads a `reward` field from `ACHIEVEMENT_DEFS`. No gear, gold, or resources are granted on any of the 24 achievement unlocks. Note: `_check_lb_achievements` (lines 1655–1698) correctly calls `add_gold` for leaderboard achievements — the pattern exists but is not applied to `check_achievements`.

**Root cause (silent errors):** `except Exception: pass` at line 1596 swallows all exceptions, making it impossible to distinguish an expected UNIQUE constraint (already-unlocked skip) from a genuine DB failure.

**Suggested fix:**
- Add a `"reward"` key to relevant `ACHIEVEMENT_DEFS` entries (e.g. `"streak_7": {..., "reward": {"gear_tier": 1}}`).
- In `unlock(aid)`, after the INSERT succeeds, read `defn.get("reward")` and dispatch to `generate_gear_drop` / `add_gold` as appropriate.
- Narrow the exception catch to `sqlite3.IntegrityError` so real failures surface.

---

## Summary

| System | File:Line | Root Cause |
|--------|-----------|------------|
| Streak 7-day gear | `app.py:1221–1237` | `generate_gear_drop()` never called; no gear insert; `_MILESTONE_TIERS` has no gear key |
| Mission XP level-up | `app.py:1288` | Raw SQL bypasses `award_xp()`, so `apply_level_rewards` never fires |
| Achievement rewards | `app.py:1586–1596` | `unlock()` never reads a reward field; `except: pass` hides real errors |
