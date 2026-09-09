# Faucet / Sink Audit — Penguin Village RPG

Source-grepped constants only. Every formula below is quoted from `app.py` /
`level_config.py` / `raid_settings.py` as they exist on this branch today.
Where the task brief assumed a value that code contradicts, the code value is
used and the discrepancy is flagged.

---

## 1. Passive jobs (`BUILDINGS[*]["produces"]`, `app.py:5800` `/work/collect`)

```
amount = floor(rate_per_hour * stream_mult * (1 + gathering_bonus + building_bonus) * hours_worked * res_mult)
gold   = floor(rate_per_hour * stream_mult * (1 + gathering_bonus + building_bonus) * hours_worked * gold_mult)
xp     = floor(rate_per_hour * stream_mult * (1 + building_bonus)                   * hours_worked * xp_mult)   # no gathering_bonus on xp
```

- **Job cap: `JOB_CAP_HOURS = 12.0`** (`app.py:845`) — brief assumed 8hr; actual is 12hr. Used below.
- `gathering_bonus` = `get_total_gathering_bonus(level)/100` — cumulative +5%/level from `level_config.LEVEL_DATA`, 0% at level 1. Level 1 = 0%, Level 15 = 70%, Level 30 = 145% (verified by execution).
- `building_bonus` = `BUILDING_BONUS_RATES = {1: 0.0, 2: 0.15, 3: 0.30}` (`app.py:636`).
- `stream_mult` = `STREAM_RATES = {0:1.0, 1:1.25, 2:1.50, 3:1.75}` (offline=1.0, used as baseline below).
- No mayor buffs active (`xp_mult=resource_mult=gold_mult=1.0` baseline).

**Totals per full 12h job cycle** (not per hour — floor applied once against `rate*hours`):

| Building (job) | Resource | Lvl1/Bld1 | Lvl1/Bld2 | Lvl1/Bld3 | Lvl15/Bld1 | Lvl15/Bld2 | Lvl15/Bld3 | Lvl30/Bld1 | Lvl30/Bld2 | Lvl30/Bld3 |
|---|---|---|---|---|---|---|---|---|---|---|
| sea_lion_pit | fish | 150 | 172 | 195 | 255 | 277 | 300 | 367 | 390 | 412 |
| sea_lion_pit | gold | 60 | 69 | 78 | 102 | 111 | 120 | 147 | 156 | 165 |
| parkmusement | gold | 180 | 207 | 234 | 306 | 332 | 360 | 441 | 468 | 495 |
| cursed_temple | spell_fragments | 150 | 172 | 195 | 255 | 277 | 300 | 367 | 390 | 412 |
| cursed_temple | gold | 96 | 110 | 124 | 163 | 177 | 192 | 235 | 249 | 264 |
| club_soda | herbs | 150 | 172 | 195 | 255 | 277 | 300 | 367 | 390 | 412 |
| club_soda | gold | 60 | 69 | 78 | 102 | 111 | 120 | 147 | 156 | 165 |
| guillotine | blood_gems | 60 | 69 | 78 | 102 | 111 | 120 | 147 | 156 | 165 |
| guillotine | bones | 60 | 69 | 78 | 102 | 111 | 120 | 147 | 156 | 165 |
| guillotine | gold | 60 | 69 | 78 | 102 | 111 | 120 | 147 | 156 | 165 |

All 5 jobs also produce xp (2.0/hr base, cursed_temple 4.0/hr) — not a sink-relevant resource, omitted.

A player can only run **one job at a time**; a full 12h cycle must be manually collected before the next starts (no auto-restart found), so realistic throughput is ~1 cycle/day for an active player, up to 2/day for one who collects at exactly the 12h mark twice.

---

## 2. Combat (`MONSTER_TYPES`, `app.py:1056`; fight resolution `app.py:6315`)

- **Energy cost: flat 15 per fight, every tier** (no tier scaling found).
- **Daily ceiling: not energy-count-capped — capped at 1 kill per specific `monster_id` per calendar day** (`monster_kills` uniqueness check, `app.py:6342`). Practical ceiling = `floor(current_energy / 15)`, further bounded by how many distinct monsters are unlocked at the player's level (see below).
- Reward only pays out on victory; on loss, consolation xp only (`max(1, tier_xp_lo//4)`), no gold/resources.
- **First-kill bonus:** first-ever kill of a given monster+variant pays **2x** gold/xp/resources (`multiplier = 2 if is_first_kill_eligible else 1`, `app.py:6375`) — one-time per monster, not a repeatable faucet.
- Win chance: `calculate_win_chance(player_cp, monster_cp, tier) = clamp(5, 95, round(50 + K*(player_cp - monster_cp)))`, `K` from `WIN_CHANCE_TIER_STEEPNESS = {1:1.61, 2:0.92, 3:1.35, 4:0.94, 5:3.73}`. Actual player_cp isn't a fixed constant (depends on gear RNG), so no exact win% can be derived from code alone — design-comment target curve (`app.py:1005-1027`) states **~30% win at a bracket's entry level rising to ~90% by its exit level**. **Assumption flagged:** 65% blended win rate used in §9 (midpoint of that stated range).

**Per-tier averages** (steady-state, multiplier=1, midpoint of each monster's gold/xp/resource range, averaged across the tier's monster count):

| Tier | Monsters | Min level | Energy | Avg gold/kill | Avg xp/kill | Avg resource units/kill | Gear drop chance |
|---|---|---|---|---|---|---|---|
| 1 | 7 | 1 | 15 | 31.1 | 50.6 | 31.4 | 0.18–0.25 |
| 2 | 7 | 5 | 15 | 76.4 | 120.2 | 42.1 | 0.18–0.22 |
| 3 | 7 | 10 | 15 | 123.6 | 163.3 | 77.9 | 0.14–0.16 |
| 4 | 6 | 15 | 15 | 186.1 | 237.0 | 115.0 | 0.12–0.14 |
| 5 | 4 | 25 | 15 | 328.1 | 395.6 | 215.0 | 0.08–0.10 |

At level 15, tiers 1–4 are all simultaneously unlocked (27 distinct fightable monsters), so a player is not restricted to only tier 4 — see §9 for the assumption used.

---

## 3. Mini-games (`calculate_minigame_rewards`, `app.py:12398`; `MINIGAME_BUILDING_IDS`, `app.py:12383`)

**Found 6 mini-games, not 5** (task brief assumed 5) — `sea_lion_pit`, `club_soda`, `parkmusement`, `cursed_temple`, `guillotine`, plus `grand_piano` (igloo furniture, not a village building).

```
reward_score = min(100, score)
multiplier   = clamp(0.2, 2.0, reward_score / 50.0)     # score 0 -> 0.2x, score 50 -> 1.0x, score >=100 -> 2.0x
gather_bonus = 1 + player_level * 0.05                   # NOT gathering_bonus from level_config — separate flat formula
reward[res]  = max(1, int(base[res] * multiplier))                 if res == "xp"
reward[res]  = max(1, int(base[res] * multiplier * gather_bonus))  otherwise
```

| Building | Base rewards (per play, multiplier=1, gather_bonus=1) |
|---|---|
| sea_lion_pit ("🎣 Fish Catch") | fish 15, gold 5, xp 10 |
| club_soda ("🌿 Herb Garden") | herbs 15, gold 5, xp 10 |
| parkmusement ("🎪 Juggle Master") | gold 20, xp 10 |
| cursed_temple ("🔮 Rune Memory") | spell_fragments 12, gold 5, xp 10 |
| guillotine ("💀 Whack-a-Target") | blood_gems 6, bones 6, gold 5, xp 10 |
| grand_piano ("🎹 Piano Recital") | gold 20, xp 10 |

- **Energy cost: 10** per play (`app.py:12797`), except free during tutorial.
- **Daily ceiling:** none of the 5 building minigames are limited (comment at `app.py:12760` explicitly: "the other 5 building minigames are unlimited"). `grand_piano` is capped at **once per day per host's piano** (`piano_scores` unique constraint).
- **Hard gate:** cannot play any minigame while a job is active (`app.py:12793-12796`, "Collect your passive job first!").
- Score is client-side (fish caught, combo points, etc.) — **the actual score distribution players achieve is not in the codebase**; multiplier is flagged as an assumption in §9 (multiplier=1.0, i.e. "average" play, used below).

---

## 4. Ice Blocks / Build! roll (`calculateIceBlockReward`, `app.py:12426`; `_perform_build_roll`, `app.py:12431`)

```python
def calculateIceBlockReward(roll):
    return roll   # 1:1, no scaling at all
```

- Roll: `random.randint(1, 20)` → **ice_blocks earned = roll** (avg 10.5/roll, range 1–20).
- **Energy cost: 5 per roll** (`energy_cost = 5`, `app.py:12457`).
- **Crit (nat 20):** grants **5 free re-rolls** (`build_free_rolls = 5`) that don't cost energy and re-trigger the crit chain if another 20 lands (`app.py:12468-12476`). No separate crit payout multiplier — reward is still just `roll` (=20) on the crit itself.
- No daily cap found on rolls beyond energy availability.

---

## 5. N00Tboxes (`open_lootbox`, `app.py:2068`; `grant_lootbox`, `app.py:2116`)

All N00Tbox sources funnel through the **same** `open_lootbox()` — one universal payout table regardless of source (daily login, streak, raid, minigame weekly, build leaderboard, tutorial, mayor gift):

```
gear:     1 item, rarity-rolled, tier = player's current gear tier at OPEN time
gold:     random.randint(*raid_settings.gold_range)      -> default [50, 100], avg 75
resource: 1 of RESOURCE_TYPES (6 types: fish, herbs, blood_gems, bones, spell_fragments, ice_blocks), amount random.randint(*resource_range) -> default [1, 50], avg 25.5
```

→ **Average value per box: 75 gold + 25.5 units of one random resource type** (expected 4.25 units/box per specific resource type, since 1-in-6 chance each).

**Sources and rates found:**

| Source | Rate | Notes |
|---|---|---|
| `daily_login` | 1 box, first login each calendar day | `app.py:3673` |
| `login_streak` (`LOGIN_STREAK_LOOTBOX_SCHEDULE`, `app.py:1656`) | 40 boxes / 30-day cycle = avg **1.33/day** | escalates at day 7(2)/14(3)/21(2)/28(3)/30(5), else 1/day |
| `daily_monsters_complete` | 1 box, once/day, only if every monster in the player's *current tier* is killed that day | `app.py:6461` — achievable at lvl15 with the tier-4 fight budget used in §9 |
| `raid_reward` (weekly boss raid) | podium ranks 1–3 get 3/2/1 boxes; ranks 4+ get a resource roll instead (no box) | `resolve_raid`, `app.py:2178`, podium size 3 |
| `minigame_weekly_<game>` | 1 box/week **to the #1 player only**, per each of the 6 games (up to 6 boxes/week community-wide) | `resolve_weekly_minigame_leaderboard`, `app.py:13079` |
| `build_leaderboard_reward` | weekly; rank 1 = 3 boxes, rank 2 = 2, rank 3 = 1, rank 4+ = 0 boxes (resource roll only) | `_calculate_build_leaderboard_reward`, `app.py:12583` |
| `tutorial` | one-time, not recurring | `app.py:9557` |
| `mayor_gift` | admin-manual, not a formula-driven organic source | `app.py:10936` |

**Guaranteed personal boxes/day** (daily_login + streak-average + achievable daily_monsters_complete) = `1 + 1.33 + 1 = 3.33/day/player`. The weekly winner-only sources (raid, minigame weekly, build leaderboard) are **not** per-player-guaranteed (only 1–3 of 5.5 players benefit each week) — treated separately in §9/§10 rather than folded into the per-player daily rate, to avoid double counting.

---

## 6. Other passive income

- **Passive seals** (`PASSIVE_SEALS_AMOUNT = 1` every `PASSIVE_SEALS_INTERVAL_MINUTES = 10`, `app.py:765-766`): mints `mayor_seals`, a **premium currency explicitly excluded from `RESOURCE_TYPES`** (`lootbox_config.py:8`) — not part of this resource economy.
- **Igloo visits** (`IGLOO_VISIT_REWARDS`, `app.py:961`): player-initiated (visiting another penguin's igloo), once per visitor→host pair per day. Gold 5–35 and 1–7 resource units scaled by relationship tier. Small and bounded by how many other players exist to visit (≤4–5 in a 5.5-player community) — **excluded from §9 calc as a minor, discretionary, non-automatic source**; flagged here for completeness.
- **Group events** (`run_autonomous_actions`, hourly tick, `GROUP_EVENT_CHANCE_PER_TICK = 0.05`): confirmed **no gold/resource grant** — `moment_scenarios.py` events are flavor-text/relationship-only (grepped for `gold`/`resource`, only found inside narrative strings, no reward code).
- **Achievement rewards**: gold + gear_tier only (e.g. `first_kill` → 100 gold, `kill_50` → 400 gold) — one-time per achievement, not recurring; not modeled as daily income.

---

## 7 & 8. Building donation sinks (`BUILDING_UPGRADES`, `app.py:535`)

**Only 5 of the 11 `BUILDINGS` entries are donation-upgradeable at all.** Confirmed explicitly in code comment at `app.py:13338-13344`: *"Only 5 of the 11 BUILDINGS ids (BUILDING_UPGRADES' keys) actually carry a building_upgrades row in practice — the other 6 (hotel, horny_jail, boutique, award_hall, barracks, bank) aren't donation-upgradeable."* `max_level` defaults to 3 (`database.py:194`).

| Building | Resource | Cost lvl1→2 | Cost lvl2→3 | Total lvl1→3 |
|---|---|---|---|---|
| sea_lion_pit | fish | 2,500 | 12,500 | 15,000 |
| sea_lion_pit | gold | 1,250 | 6,250 | 7,500 |
| sea_lion_pit | ice_blocks | 5,000 | 10,000 | 15,000 |
| club_soda | herbs | 2,500 | 12,500 | 15,000 |
| club_soda | gold | 1,250 | 6,250 | 7,500 |
| club_soda | ice_blocks | 5,000 | 10,000 | 15,000 |
| parkmusement | gold | 3,750 | 18,750 | 22,500 |
| parkmusement | ice_blocks | 5,000 | 10,000 | 15,000 |
| cursed_temple | spell_fragments | 2,000 | 10,000 | 12,000 |
| cursed_temple | gold | 1,250 | 6,250 | 7,500 |
| cursed_temple | ice_blocks | 5,000 | 10,000 | 15,000 |
| guillotine | blood_gems | 500 | 2,500 | 3,000 |
| guillotine | bones | 500 | 2,500 | 3,000 |
| guillotine | gold | 1,250 | 6,250 | 7,500 |
| guillotine | ice_blocks | 5,000 | 10,000 | 15,000 |

**hotel, horny_jail, boutique, award_hall, barracks, bank: no donation cost found — flagged as "not found at grep for BUILDING_UPGRADES / donation_cost / max_level across app.py, database.py"** — these 6 are `type: "rest"/"placeholder"/"shop"/"achievements"/"combat"` and have no upgrade-cost dict at all.

**Total resources required to take all 5 upgradeable buildings from lvl1→lvl3:**

| Resource | Total sink |
|---|---|
| fish | 15,000 |
| herbs | 15,000 |
| spell_fragments | 12,000 |
| blood_gems | 3,000 |
| bones | 3,000 |
| gold | 52,500 |
| ice_blocks | 75,000 |

---

## 9–11. Calculation

### Assumptions (all flagged explicitly — none are code constants)

- Level 15, building level 1 (unupgraded — a conservative/floor baseline; real building bonuses of +15–30% would only make the oversupply findings below worse, not better).
- Job: 1×12h cycle/day at the matching job for each resource type (gold uses the average gold output across the 5 jobs = 155/day, since gold isn't resource-specific and a player only works one job).
- Combat: `max_energy` at level 15 = 100 base + 20 (level-10 milestone, `level_config.py:11`) = **120**. "Full energy on combat" → `floor(120/15) = 8` fights/day. Modeled as: the 6 unique tier-4 monsters fought once each (best reward/energy ratio available at this level) using 6 of the 8 slots; remaining 2 slots not further modeled. **Win rate assumed 65%** (midpoint of the design-commented 30%→90% per-bracket target curve — no exact figure derivable from code).
- Mini-games: "full energy on minigames" → `floor(120/10) = 12` plays/day, spread 2 plays/game across the 5 building minigames (`grand_piano` excluded — requires owning/visiting specific furniture). **Score multiplier assumed 1.0** (score=50, "average" play — code supports 0.2x–2.0x depending on player skill, not derivable from code).
- Ice blocks: "all ice_block rolls" → `floor(120/5) = 24` rolls/day × avg 10.5/roll (nat-20 free-reroll chain not modeled, adds ~2.5% EV).
- N00Tbox: guaranteed personal rate only (3.33 boxes/day/player from §5) — weekly winner-only sources (raid podium, 6× minigame weekly, build leaderboard) are **not** included in the per-player-×5.5 model since they inherently go to only 1–3 of 5.5 players; they're a community-level addition, separately flagged below rather than estimated (would require simulating who wins each week).
- Community size: 5.5 players (per brief). Period: 30 days.
- **This is a per-resource independent model**, not one single player doing everything at once for every resource simultaneously — e.g. the "fish" row assumes that day's representative player worked the fishing job, the "herbs" row assumes a (different) representative player worked club_soda, etc. This matches "5 job buildings, ~5.5 players" being roughly one-job-per-player in practice.

### One player's max resources/day (level 15, building lvl1)

| Resource | Job (matched) | Combat (×0.65 win) | Minigames | N00Tbox (personal) | Ice rolls | **Total/day** |
|---|---|---|---|---|---|---|
| fish | 255 | 74.8 | 52 | 14.2 | — | **395.9** |
| herbs | 255 | 45.5 | 52 | 14.2 | — | **366.7** |
| spell_fragments | 255 | 130.0 | 42 | 14.2 | — | **441.2** |
| blood_gems | 102 | 91.0 | 20 | 14.2 | — | **227.2** |
| bones | 102 | 107.3 | 20 | 14.2 | — | **243.4** |
| ice_blocks | 0 | 0 | 0 | 14.2 | 252.0 | **266.2** |
| gold | 155 (avg job) | 725.7 | 134 | 250.0 | — | **1,264.7** |

### Community 30-day total income (× 5.5 players × 30 days)

| Resource | 30-day community income |
|---|---|
| fish | 65,326 |
| herbs | 60,500 |
| spell_fragments | 72,793 |
| blood_gems | 37,482 |
| bones | 40,164 |
| ice_blocks | 43,918 |
| gold | 208,680 |

*(Excludes weekly winner-only N00Tbox windfalls — raid podium up to 3 boxes/week, minigame weekly up to 6 boxes/week, build leaderboard up to 3 boxes/week community-wide — which would add roughly another 12 boxes/week × ~4.3 weeks × [75 gold + 4.25/resource-type] ≈ 3,900 gold + ~220 per resource type over 30 days on top of the table above. Small relative to the totals below; doesn't change the ranking.)*

### Ratio: 30-day community income ÷ total sink (lvl1→3, all 5 upgradeable buildings)

| Resource | Community income | Total sink | **Ratio** | Flag |
|---|---|---|---|---|
| fish | 65,326 | 15,000 | **4.36x** | oversupplied |
| herbs | 60,500 | 15,000 | **4.03x** | oversupplied |
| gold | 208,680 | 52,500 | **3.97x** | oversupplied |
| spell_fragments | 72,793 | 12,000 | **6.07x** | oversupplied |
| blood_gems | 37,482 | 3,000 | **12.49x** | 🚩 most oversupplied |
| bones | 40,164 | 3,000 | **13.39x** | 🚩 most oversupplied |
| ice_blocks | 43,918 | 75,000 | **0.59x** | under target (bottleneck, not oversupplied) |

**Reading:** every resource lands well above the brief's expected ~1.0–1.5x except `ice_blocks`, which comes in *under* 1x. That's structurally consistent: `ice_blocks` is the one resource every one of the 5 buildings demands (15,000 each × 5 = 75,000 total), while every other resource is a single-building sink (3,000–22,500). `ice_blocks`'s ratio near/under 1x is plausibly why the observed ~30-day full-clear pace happened at all — it's the actual pacing bottleneck. Meanwhile `blood_gems` and `bones` (guillotine's two resources, sink capped at just 3,000 each) are supplied ~12–13x over what's needed, because both drop from a wide spread of tier-2-through-5 monsters and from every guillotine job/minigame session, but their building sink was never scaled up to match. **`blood_gems`/`bones` are the clearest candidates for the steepest new cost curve**, with `spell_fragments` a distant second; `ice_blocks`'s curve is already roughly correctly paced and should not be steepened without also steepening the resource-specific costs, or ice_blocks becomes the sole late-game gate while everything else sits as dead surplus.

---

## Caveats

- Win rate (65%) and minigame score multiplier (1.0) are the two largest unverifiable assumptions — both are genuinely player-skill/gear-dependent and not fixed constants in code. Sensitivity: raising win rate to 90% (top of the design target curve) increases combat-driven rows (spell_fragments, blood_gems, bones, gold) by roughly 35%, which would push blood_gems/bones ratios to ~16-17x — directionally the same conclusion, more extreme.
- "5.5 players" and "30 days" are brief-supplied, not code constants.
- Building level assumed 1 (unupgraded) for the job-income baseline in §9; real mid-game building levels would raise faucet income further (+15–30%), so all ratios above are conservative lower bounds.
