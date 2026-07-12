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


def pick_weekly_metric():
    """Return a metric dict ({id, label, threshold}) excluding last week's metric.

    Queries the most recent weekly_challenges row to avoid back-to-back repeats.
    If all metrics would repeat (only one metric exists), skips the exclusion.
    threshold is the live value from raid_settings, not a hardcoded constant.
    """
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT metric_type FROM weekly_challenges ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_metric = row["metric_type"] if row else None
    finally:
        conn.close()

    candidates = [m for m in WEEKLY_METRIC_TYPES if m["id"] != last_metric]
    if not candidates:
        candidates = WEEKLY_METRIC_TYPES  # fallback: all metrics if list is tiny
    metric = dict(random.choice(candidates))
    thresholds = raid_settings.get_setting("weekly_metric_thresholds")
    metric["threshold"] = thresholds.get(metric["id"], 0)
    return metric


def pick_boss_name():
    """Return a random boss name from the live-editable raid_settings.boss_names pool.

    BOSS_NAMES above only seeds that pool's default and serves as a fallback
    if the pool is ever left completely empty -- the Mayor Raid Debug panel
    edits raid_settings.boss_names directly, not this module-level constant.
    """
    names = raid_settings.get_setting("boss_names")
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
