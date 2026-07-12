"""Live-editable raid balance knobs, backed by the raid_settings table.

Replaces what used to be hardcoded constants in raid_config.py / lootbox_config.py
so the Mayor's Raid Debug panel can tune them without a redeploy. Each key is
JSON-encoded in a single-row-per-key table; DEFAULTS seeds/back-fills any key
that hasn't been explicitly set yet, so behavior is unchanged until an admin
actually edits something.
"""
import json
import sqlite3
import os

DATABASE = os.environ.get('DATABASE_PATH', 'village.db')

DEFAULTS = {
    "weekly_metric_thresholds": {
        "gold_earned":         50000,
        "resources_gathered":  500,
        "monsters_killed":     100,
    },
    "boss_hp_per_participant": 200,  # kept for reference — no longer read by boss spawn logic,
                                      # which now always uses boss_hp_flat (see
                                      # start_raid_if_unlocked in app.py). Restore manually if this
                                      # scaling is ever wanted again.
    "boss_hp_flat": 5000,
    # Live-editable pool raid_config.pick_boss_name() draws from -- seeded from
    # what used to be the hardcoded raid_config.BOSS_NAMES placeholder list.
    # That module-level list is kept as a fallback (used only if this pool is
    # ever left completely empty), not as the source of truth anymore.
    "boss_names": [
        "Frostfang",
        "The Blizzard King",
        "Glacial Colossus",
        "Snowmaw the Devourer",
        "Permafrost Tyrant",
        "The Frozen Sovereign",
    ],
    "lootbox_drop_rates": {
        "legendary": 5,
        "rare":      10,
        "epic":      7,
        "uncommon":  28,
        "common":    50,
    },
    "gold_range":     [50, 100],
    "resource_range": [1, 50],
    # Ranks 1..N get lootboxes (N, N-1, ..., 1); ranks N+1 and below scale
    # via calculate_rank_reward(). Default N=3 matches the original 3/2/1 tiers.
    "rank_reward_podium_size": 3,
}


def _get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key):
    """Return the live value for `key`, seeding its default on first read."""
    if key not in DEFAULTS:
        raise ValueError(f"Unknown raid setting: {key}")
    db = _get_db()
    row = db.execute("SELECT value FROM raid_settings WHERE key=?", (key,)).fetchone()
    if row:
        db.close()
        return json.loads(row["value"])
    default = DEFAULTS[key]
    db.execute("INSERT OR IGNORE INTO raid_settings (key, value) VALUES (?, ?)", (key, json.dumps(default)))
    db.commit()
    db.close()
    return default


def set_setting(key, value):
    """Validate and persist a new value for `key`. Caller validates shape/ranges first."""
    if key not in DEFAULTS:
        raise ValueError(f"Unknown raid setting: {key}")
    db = _get_db()
    db.execute(
        "INSERT INTO raid_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value))
    )
    db.commit()
    db.close()


def get_all_settings():
    return {k: get_setting(k) for k in DEFAULTS}
