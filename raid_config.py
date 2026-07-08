import random
import sqlite3
import os

DATABASE = os.environ.get('DATABASE_PATH', 'village.db')

# ── WEEKLY METRIC TYPES ───────────────────────────────────────────────────────
# Each metric has: id (matches the metric_type stored in weekly_challenges),
# label (human-readable), threshold (tune during balance-pass).

WEEKLY_METRIC_TYPES = [
    {
        "id":        "gold_earned",
        "label":     "Gold Earned",
        "threshold": 50000,   # tune during balance-pass
    },
    {
        "id":        "resources_gathered",
        "label":     "Resources Gathered",
        "threshold": 500,     # tune during balance-pass
    },
    {
        "id":        "monsters_killed",
        "label":     "Monsters Defeated",
        "threshold": 100,     # tune during balance-pass
    },
]

# Boss HP per participant — boss_max_hp = participant_count * BOSS_HP_PER_PARTICIPANT
BOSS_HP_PER_PARTICIPANT = 200   # tune during balance-pass

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
    """Return a metric dict from WEEKLY_METRIC_TYPES, excluding last week's metric.

    Queries the most recent weekly_challenges row to avoid back-to-back repeats.
    If all metrics would repeat (only one metric exists), skips the exclusion.
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
    return random.choice(candidates)


def pick_boss_name():
    """Return a random boss name from BOSS_NAMES."""
    return random.choice(BOSS_NAMES)
