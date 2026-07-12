import random
import sqlite3
import os

import raid_settings

DATABASE = os.environ.get('DATABASE_PATH', 'village.db')

# ── WEEKLY METRIC TYPES ───────────────────────────────────────────────────────
# id (matches the metric_type stored in weekly_challenges) + label (human-readable)
# are fixed here; the per-metric threshold is a live value — see
# raid_settings.DEFAULTS["weekly_metric_thresholds"], editable from the Mayor's
# Raid Debug panel without a redeploy.

WEEKLY_METRIC_TYPES = [
    {"id": "gold_earned",        "label": "Gold Earned"},
    {"id": "resources_gathered", "label": "Resources Gathered"},
    {"id": "monsters_killed",    "label": "Monsters Defeated"},
]

# Placeholder boss names — one is chosen randomly when a raid is created
BOSS_NAMES = [
    "Frostfang",
    "The Blizzard King",
    "Glacial Colossus",
    "Snowmaw the Devourer",
    "Permafrost Tyrant",
    "The Frozen Sovereign",
]


def pick_weekly_metric(db=None):
    """Return a metric dict ({id, label, threshold}) excluding last week's metric.

    Queries the most recent weekly_challenges row to avoid back-to-back repeats.
    If all metrics would repeat (only one metric exists), skips the exclusion.
    threshold is the live value from raid_settings, not a hardcoded constant.

    Pass the caller's own already-open `db` connection when calling mid-
    transaction (see raid_settings.get_setting's docstring for why) -- both
    the weekly_challenges lookup and the raid_settings read below then run on
    that connection instead of opening one (or two) more. Omit `db` only for
    a genuine top-level caller with nothing open yet.
    """
    # `conn` is the connection actually used for the SELECT below (either the
    # caller's own `db`, or a temporary one this function owns and closes).
    # `db` itself is left untouched so it can be passed straight through to
    # get_setting() afterward -- None if this was a top-level call, or the
    # caller's still-open connection to reuse, never a connection we've
    # already closed.
    owns_conn = db is None
    conn = db
    if owns_conn:
        conn = sqlite3.connect(DATABASE, timeout=30)
        conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT metric_type FROM weekly_challenges ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_metric = row["metric_type"] if row else None
    finally:
        if owns_conn:
            conn.close()

    candidates = [m for m in WEEKLY_METRIC_TYPES if m["id"] != last_metric]
    if not candidates:
        candidates = WEEKLY_METRIC_TYPES  # fallback: all metrics if list is tiny
    metric = dict(random.choice(candidates))
    thresholds = raid_settings.get_setting("weekly_metric_thresholds", db=db)
    metric["threshold"] = thresholds.get(metric["id"], 0)
    return metric


def pick_boss_name(db=None):
    """Return a random boss name from the live-editable raid_settings.boss_names pool.

    BOSS_NAMES above only seeds that pool's default and serves as a fallback
    if the pool is ever left completely empty -- the Mayor Raid Debug panel
    edits raid_settings.boss_names directly, not this module-level constant.

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why.
    """
    names = raid_settings.get_setting("boss_names", db=db)
    if not names:
        names = BOSS_NAMES
    return random.choice(names)


def calculate_attack_damage(roll):
    """Return boss damage for a given 1-20 attack roll. Isolated for future multipliers.

    Same linear shape as calculate_ice_blocks_reward (build_roll's calculateIceBlockReward) —
    a nat 20 free-roll chain here is still bounded by boss_max_hp = participant_count *
    boss_hp_per_participant (raid_settings), so it's nowhere near trivial and doesn't
    need a different curve.
    """
    return roll


CP_DAMAGE_BONUS_DIVISOR = 10  # tune during balance-pass -- only used as a fallback if
                               # raid_settings.cp_damage_bonus_divisor is ever missing/invalid;
                               # the Mayor Raid Debug panel edits that live value directly.


def cp_damage_bonus(player_cp, db=None):
    """Flat additive raid-attack damage bonus from the player's current total CP
    (NOT a multiplier): floor(player_cp / cp_damage_bonus_divisor).

    Added on top of calculate_attack_damage()'s roll-based base damage in
    POST /raid/attack, identically for both normal rolls and free-roll/crit
    rolls -- there's no separate curve for either path. Raid attacks only;
    does not apply to Build!/ice-blocks rolls (calculate_ice_blocks_reward).

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why.
    """
    divisor = raid_settings.get_setting("cp_damage_bonus_divisor", db=db) or CP_DAMAGE_BONUS_DIVISOR
    return player_cp // divisor
