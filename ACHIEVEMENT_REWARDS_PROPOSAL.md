# Achievement Rewards Proposal

## Scaling anchors (from app.py)

| Reference point | Gold |
|---|---|
| Daily mission (login/work) | 25–30 |
| Daily mission (hard worker / fight) | 40–80 |
| Streak day 3 | 100 |
| Streak day 7 + gear tier 1 | 300 |
| Streak day 14 | 500 |
| Streak day 30 | 1 000 |
| Streak day 60 | 2 000 |
| LB top-20 | 100 |
| LB top-10 | 200 |
| LB top-3 (lb_top3, lb_first) | 0 (no gold — prestige only, already special) |

Gear tiers (from `_GEAR_DROP_RARITY_WEIGHTS`):
- Tier 1 — mostly common/uncommon (easy/early)
- Tier 2 — common/uncommon/rare (mid)
- Tier 3 — uncommon/rare/epic (hard)
- Tier 4 — rare/epic/legendary (late-game)

---

## Proposed rewards per achievement

| Key | Title | Difficulty | Gold | Gear tier | Notes |
|---|---|---|---|---|---|
| `first_login` | WELCOME HOME | Trivial (day 1) | 50 | — | Matches daily login mission |
| `first_job` | CLOCK IN | Easy | 50 | — | Matches daily work mission |
| `first_fight` | BRAVE (OR DUMB) | Easy | 75 | — | Slightly above fighting mission (40) |
| `first_kill` | MONSTER SLAYER | Easy | 100 | 1 | First kill is a milestone; tier 1 gear appropriate |
| `level_5` | RISING STAR | Early-game | 150 | — | Small milestone; below streak-3 anchor (100) no, raise slightly |
| `level_10` | VILLAGE LEGEND | Mid-game | 300 | 1 | Matches streak-7 gold; tier 1 gear |
| `level_20` | SEASONED VETERAN | Late-game | 750 | 2 | Between streak-14 (500) and streak-30 (1 000); tier 2 for better loot |
| `gold_500` | GETTING PAID | Easy | 100 | — | Early collection milestone |
| `gold_5000` | MONEY PENGUIN | Mid-game | 300 | — | Gold-focused: gear reward would be odd; pure gold bonus |
| `fish_50` | FISHER PENGUIN | Easy | 100 | — | Resource collection start |
| `fish_500` | MASTER FISHER | Mid-game | 250 | — | Sustained grinding; no gear (resource theme) |
| `kill_10` | HUNTER | Easy-mid | 150 | 1 | Combat milestone, tier 1 gear fits |
| `kill_50` | VETERAN HUNTER | Mid-game | 400 | 2 | Significant grind; tier 2 gear |
| `igloo_5` | HOME SWEET IGLOO | Easy | 100 | — | Decoration activity; gold-only |
| `streak_7` | DEDICATED | Mid-game | 200 | — | streak milestone already grants gear + 300 gold via `award_streak_milestone`; gold top-up only here to avoid double gear |
| `streak_30` | COMMITTED | Hard | 500 | 2 | Very committed player; tier 2 gear, below streak-30 milestone (1 000) since that fires separately |
| `prestige_1` | REBORN | Very hard (end-game) | 1 000 | 3 | Prestige is the hardest milestone; tier 3 gear |
| `first_igloo_visit` | WARM WELCOME | Trivial | 50 | — | One social visit |
| `social_butterfly` | SOCIAL BUTTERFLY | Significant effort | 250 | — | 50 igloo visits |
| `best_friends_forever` | BFF | High effort (social) | 300 | — | Relationship grind; gold reward |
| `popular_penguin` | POPULAR PENGUIN | Passive/social | 200 | — | Requires others to visit you |
| `village_socialite` | THE SOCIALITE | High effort (social) | 400 | — | 10 Friend+ relationships |
| `lb_top20` | RISING STAR | Competitive | 100 | — | Already awarded via `_check_lb_achievements`; no change needed |
| `lb_top10` | CONTENDER | Competitive | 200 | — | Already awarded via `_check_lb_achievements`; no change needed |
| `lb_top3` | CHAMPION | Very competitive | 500 | — | Currently no reward; add gold |
| `lb_first` | VILLAGE LEGEND | Elite | 1 000 | — | Currently no reward; add gold |

---

## Notes

- `streak_7` and `streak_30` achievements are checked in `check_achievements` but the heavy reward (gear + gold) already fires from `award_streak_milestone`. The achievement reward here is a smaller supplemental gold bonus to avoid duplicating the gear drop.
- `lb_top20` and `lb_top10` already grant gold via `_check_lb_achievements`'s `lb_unlock(aid, gold_reward)` — those entries above are **no-change** (listed for completeness). `lb_top3` and `lb_first` currently pass `gold_reward=0`; propose adding gold there.
- All gear drops use `generate_gear_drop(tier)` and the standard gear insert pattern added in the streak fix.

---

## Summary: achievements that need gear drops

| Key | Gear tier |
|---|---|
| `first_kill` | 1 |
| `level_10` | 1 |
| `level_20` | 2 |
| `kill_10` | 1 |
| `kill_50` | 2 |
| `streak_30` | 2 |
| `prestige_1` | 3 |
