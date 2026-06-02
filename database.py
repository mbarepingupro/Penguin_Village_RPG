import sqlite3


def _add_col(cursor, table, col_def):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception:
        pass  # column already exists


def init_db():
    conn = sqlite3.connect("village.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS penguins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 100,
            max_energy INTEGER DEFAULT 100,
            coins INTEGER DEFAULT 0,
            prestige INTEGER DEFAULT 0,
            breed TEXT DEFAULT 'classic_black',
            job TEXT DEFAULT NULL,
            job_duration INTEGER DEFAULT 0,
            job_started INTEGER DEFAULT 0,
            last_active INTEGER DEFAULT 0,
            login_streak INTEGER DEFAULT 0,
            last_login_date TEXT DEFAULT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            mission_key TEXT NOT NULL,
            date TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            UNIQUE(username, mission_key, date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS igloo_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            item_key TEXT NOT NULL,
            x INTEGER NOT NULL DEFAULT 0,
            y INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            username TEXT PRIMARY KEY,
            gold INTEGER DEFAULT 0,
            fish INTEGER DEFAULT 0,
            herbs INTEGER DEFAULT 0,
            blood_gems INTEGER DEFAULT 0,
            bones INTEGER DEFAULT 0,
            spell_fragments INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS gear (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            item_id TEXT,
            name TEXT NOT NULL,
            set_name TEXT DEFAULT NULL,
            type TEXT NOT NULL,
            slot TEXT NOT NULL,
            rarity TEXT DEFAULT 'common',
            attack_bonus INTEGER DEFAULT 0,
            defense_bonus INTEGER DEFAULT 0,
            speed_bonus INTEGER DEFAULT 0,
            hp_bonus INTEGER DEFAULT 0,
            equipped INTEGER DEFAULT 0,
            obtained_at INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS monster_kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            monster_id TEXT NOT NULL,
            killed_date TEXT NOT NULL,
            loot_summary TEXT DEFAULT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            username TEXT,
            achievement_id TEXT,
            unlocked_at INTEGER,
            PRIMARY KEY (username, achievement_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            username TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS login_streaks (
            username TEXT PRIMARY KEY,
            current_streak INTEGER DEFAULT 1,
            longest_streak INTEGER DEFAULT 1,
            last_login_date TEXT DEFAULT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS building_upgrades (
            building_id TEXT PRIMARY KEY,
            current_level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 3,
            fish_donated INTEGER DEFAULT 0,
            herbs_donated INTEGER DEFAULT 0,
            gold_donated INTEGER DEFAULT 0,
            blood_gems_donated INTEGER DEFAULT 0,
            bones_donated INTEGER DEFAULT 0,
            spell_fragments_donated INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS building_donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id TEXT NOT NULL,
            username TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            donated_at INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS active_buffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buff_type TEXT NOT NULL,
            multiplier REAL DEFAULT 2.0,
            activated_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            activated_by TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS community_boss (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            max_hp INTEGER NOT NULL,
            current_hp INTEGER NOT NULL,
            spawned_at INTEGER NOT NULL,
            defeated_at INTEGER DEFAULT NULL,
            spawned_by TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS boss_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            damage_dealt INTEGER DEFAULT 0,
            hits INTEGER DEFAULT 0,
            last_hit_at INTEGER DEFAULT 0,
            UNIQUE(boss_id, username)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS first_kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            monster_type TEXT NOT NULL,
            variant_name TEXT NOT NULL,
            killed_at INTEGER NOT NULL,
            UNIQUE(username, monster_type, variant_name)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username1 TEXT NOT NULL,
            username2 TEXT NOT NULL,
            interaction_count INTEGER DEFAULT 0,
            relationship_level TEXT DEFAULT 'stranger',
            last_interaction INTEGER DEFAULT 0,
            UNIQUE(username1, username2)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS igloo_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor TEXT NOT NULL,
            host TEXT NOT NULL,
            visited_date TEXT NOT NULL,
            reward_gold INTEGER DEFAULT 0,
            reward_resource_type TEXT DEFAULT NULL,
            reward_resource_amount INTEGER DEFAULT 0,
            UNIQUE(visitor, host, visited_date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS building_contributions_tracker (
            username TEXT NOT NULL,
            building_id TEXT NOT NULL,
            total_contributed INTEGER DEFAULT 0,
            background_unlocked INTEGER DEFAULT 0,
            PRIMARY KEY (username, building_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS discovered_sets (
            username TEXT NOT NULL,
            set_name TEXT NOT NULL,
            discovered_at INTEGER NOT NULL,
            PRIMARY KEY (username, set_name)
        )
    """)

    # Safe migrations for existing databases
    _add_col(c, "penguins", "xp INTEGER DEFAULT 0")
    _add_col(c, "penguins", "max_energy INTEGER DEFAULT 100")
    _add_col(c, "penguins", "prestige INTEGER DEFAULT 0")
    _add_col(c, "penguins", "breed TEXT DEFAULT 'classic_black'")
    _add_col(c, "penguins", "job_duration INTEGER DEFAULT 0")
    _add_col(c, "penguins", "login_streak INTEGER DEFAULT 0")
    _add_col(c, "penguins", "last_login_date TEXT DEFAULT NULL")
    _add_col(c, "penguins", "last_active INTEGER DEFAULT 0")
    _add_col(c, "resources", "gold INTEGER DEFAULT 0")
    _add_col(c, "gear", "rarity TEXT DEFAULT 'common'")
    _add_col(c, "gear", "set_name TEXT DEFAULT NULL")
    _add_col(c, "gear", "speed_bonus INTEGER DEFAULT 0")
    _add_col(c, "gear", "hp_bonus INTEGER DEFAULT 0")
    _add_col(c, "gear", "obtained_at INTEGER DEFAULT 0")
    _add_col(c, "gear", "combat_power INTEGER DEFAULT 0")
    _add_col(c, "login_streaks", "last_login_date TEXT DEFAULT NULL")
    _add_col(c, "login_streaks", "daily_reward_claimed TEXT DEFAULT NULL")
    _add_col(c, "monster_kills", "killed_date TEXT DEFAULT ''")
    _add_col(c, "monster_kills", "loot_summary TEXT DEFAULT NULL")
    _add_col(c, "penguins", "title TEXT DEFAULT NULL")
    _add_col(c, "resources", "mayor_seals INTEGER DEFAULT 0")
    _add_col(c, "penguins", "stream_tier INTEGER DEFAULT 0")
    _add_col(c, "penguins", "last_chatted INTEGER DEFAULT 0")
    _add_col(c, "penguins", "active_title TEXT DEFAULT NULL")
    _add_col(c, "penguins", "fishing_hours REAL DEFAULT 0")
    _add_col(c, "penguins", "herbalism_hours REAL DEFAULT 0")
    _add_col(c, "penguins", "circus_hours REAL DEFAULT 0")
    _add_col(c, "penguins", "monk_hours REAL DEFAULT 0")
    _add_col(c, "penguins", "executioner_hours REAL DEFAULT 0")
    _add_col(c, "penguins", "ceremonial_titles TEXT DEFAULT NULL")
    _add_col(c, "penguins", "last_energy_update INTEGER DEFAULT 0")
    _add_col(c, "penguins", "hotel_uses_today INTEGER DEFAULT 0")
    _add_col(c, "penguins", "last_hotel_date TEXT DEFAULT NULL")
    _add_col(c, "penguins", "total_contributions INTEGER DEFAULT 0")
    _add_col(c, "penguins", "tutorial_completed INTEGER DEFAULT 0")
    _add_col(c, "penguins", "character_created INTEGER DEFAULT 0")
    _add_col(c, "penguins", "penguin_color TEXT DEFAULT 'classic_black'")
    _add_col(c, "penguins", "penguin_name TEXT DEFAULT NULL")
    _add_col(c, "penguins", "social_mode TEXT DEFAULT 'social'")
    _add_col(c, "penguins", "social_target TEXT DEFAULT NULL")
    _add_col(c, "penguins", "total_visits_given INTEGER DEFAULT 0")
    _add_col(c, "penguins", "total_visits_received INTEGER DEFAULT 0")
    _add_col(c, "penguins", "trait_social TEXT DEFAULT NULL")
    _add_col(c, "penguins", "trait_interest TEXT DEFAULT NULL")
    _add_col(c, "penguins", "trait_quirk TEXT DEFAULT NULL")

    # Existing players (level > 1) skip character creation — they can reshape at the Cursed Temple
    try:
        c.execute("UPDATE penguins SET character_created = 1 WHERE character_created = 0 AND level > 1")
    except Exception:
        pass

    # Migrate building levels from 5-level to 3-level system
    try:
        c.execute(
            "UPDATE building_upgrades SET max_level=3 "
            "WHERE building_id IN ('sea_lion_pit','club_soda','parkmusement','cursed_temple','guillotine') "
            "AND max_level=5"
        )
        # Clamp any current_level > 3 down to 3
        c.execute(
            "UPDATE building_upgrades SET current_level=3 "
            "WHERE building_id IN ('sea_lion_pit','club_soda','parkmusement','cursed_temple','guillotine') "
            "AND current_level > 3"
        )
    except Exception:
        pass

    # Migrate gear slot names to standardized names
    try:
        c.execute("UPDATE gear SET slot = 'armor' WHERE slot IN ('arm', 'chest', 'cape') AND type = 'combat'")
        c.execute("UPDATE gear SET slot = 'helmet' WHERE slot = 'head' AND type = 'combat'")
        c.execute("UPDATE gear SET slot = 'outfit' WHERE slot IN ('cape', 'back') AND type = 'cosmetic'")
        c.execute("UPDATE gear SET slot = 'hat' WHERE slot = 'head' AND type = 'cosmetic'")
    except Exception:
        pass

    # Backfill combat_power from old stat columns for existing gear
    try:
        c.execute("""
            UPDATE gear SET combat_power = attack_bonus + defense_bonus + speed_bonus + (hp_bonus / 5)
            WHERE type = 'combat' AND combat_power = 0
              AND (attack_bonus > 0 OR defense_bonus > 0 OR speed_bonus > 0 OR hp_bonus > 0)
        """)
    except Exception:
        pass

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect("village.db")
    conn.row_factory = sqlite3.Row
    return conn


def backfill_cosmetics(LEVEL_DATA, COSMETIC_SLOTS):
    import time as _time
    conn = sqlite3.connect("village.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        players = c.execute("SELECT username, level FROM penguins").fetchall()
    except Exception:
        conn.close()
        return
    now = int(_time.time())
    for player in players:
        username = player["username"]
        player_level = player["level"] or 1
        for lvl, data in LEVEL_DATA.items():
            if lvl > player_level:
                continue
            reward = data.get("reward") or {}
            for cosmetic in reward.get("cosmetics", []):
                item_id = cosmetic.lower().replace(" ", "_").replace("'", "")
                cosm_slot = COSMETIC_SLOTS.get(cosmetic, "accessory")
                existing = c.execute(
                    "SELECT COUNT(*) as cnt FROM gear WHERE username=? AND item_id=? AND type='cosmetic'",
                    (username, item_id)
                ).fetchone()
                if not existing or existing["cnt"] == 0:
                    c.execute(
                        "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
                        "VALUES (?,?,?,'cosmetic',?,'milestone',0,?)",
                        (username, item_id, cosmetic, cosm_slot, now)
                    )
    conn.commit()
    conn.close()
