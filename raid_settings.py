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
    # Flat additive raid-attack damage bonus = floor(player_cp / this) -- see
    # raid_config.cp_damage_bonus(). Raid attacks only, not Build!/ice-blocks rolls.
    "cp_damage_bonus_divisor": 10,
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


def get_setting(key, db=None):
    """Return the live value for `key`, seeding its default on first read.

    Pass the caller's own already-open `db` connection when calling from
    inside another function's transaction (any scheduler job or request
    handler mid-write) -- opening a second connection there would contend
    for the write lock against that transaction, exactly the class of bug
    already hit three times in this raid system (record_challenge_progress,
    then re-introduced via pick_boss_name and cp_damage_bonus, each fixed by
    manually reordering the call site instead of eliminating the second
    connection). Passing `db` here eliminates it at the source instead:
    when provided, this executes on that connection and the caller owns
    commit/close, same convention as record_challenge_progress. Omit `db`
    only for genuine top-level callers with no connection open yet (this
    still opens/commits/closes its own, unchanged from before).
    """
    if key not in DEFAULTS:
        raise ValueError(f"Unknown raid setting: {key}")
    owns_conn = db is None
    if owns_conn:
        db = _get_db()
    row = db.execute("SELECT value FROM raid_settings WHERE key=?", (key,)).fetchone()
    if row:
        if owns_conn:
            db.close()
        return json.loads(row["value"])
    default = DEFAULTS[key]
    db.execute("INSERT OR IGNORE INTO raid_settings (key, value) VALUES (?, ?)", (key, json.dumps(default)))
    if owns_conn:
        db.commit()
        db.close()
    return default


def set_setting(key, value, db=None):
    """Validate and persist a new value for `key`. Caller validates shape/ranges first.

    Same optional-`db` convention as get_setting() -- pass the caller's
    connection when called mid-transaction, omit it for top-level callers.
    """
    if key not in DEFAULTS:
        raise ValueError(f"Unknown raid setting: {key}")
    owns_conn = db is None
    if owns_conn:
        db = _get_db()
    db.execute(
        "INSERT INTO raid_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value))
    )
    if owns_conn:
        db.commit()
        db.close()


def get_all_settings():
    return {k: get_setting(k) for k in DEFAULTS}
