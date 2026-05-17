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
    _add_col(c, "login_streaks", "daily_reward_claimed TEXT DEFAULT NULL")
    _add_col(c, "monster_kills", "killed_date TEXT DEFAULT ''")
    _add_col(c, "monster_kills", "loot_summary TEXT DEFAULT NULL")
    _add_col(c, "penguins", "title TEXT DEFAULT NULL")
    _add_col(c, "resources", "mayor_seals INTEGER DEFAULT 0")
    _add_col(c, "penguins", "stream_tier INTEGER DEFAULT 0")
    _add_col(c, "penguins", "last_chatted INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect("village.db")
    conn.row_factory = sqlite3.Row
    return conn
