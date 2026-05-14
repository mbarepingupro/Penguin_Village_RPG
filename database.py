import sqlite3

def init_db():
    conn = sqlite3.connect("village.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS penguins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            level INTEGER DEFAULT 1,
            energy INTEGER DEFAULT 100,
            coins INTEGER DEFAULT 0,
            job TEXT DEFAULT NULL,
            job_started INTEGER DEFAULT 0,
            last_active INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS igloo_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            item_key TEXT NOT NULL,
            x INTEGER NOT NULL DEFAULT 0,
            y INTEGER NOT NULL DEFAULT 0
        )
    """)

    try:
        cursor.execute("ALTER TABLE penguins ADD COLUMN last_active INTEGER DEFAULT 0")
    except:
        pass

    # XP column on penguins
    try:
        cursor.execute("ALTER TABLE penguins ADD COLUMN xp INTEGER DEFAULT 0")
    except:
        pass

    # Resources per player (everything except coins)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            username TEXT PRIMARY KEY,
            fish INTEGER DEFAULT 0,
            herbs INTEGER DEFAULT 0,
            blood_gems INTEGER DEFAULT 0,
            bones INTEGER DEFAULT 0,
            spell_fragments INTEGER DEFAULT 0
        )
    """)

    # Gear owned by player
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gear (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            item_id TEXT,
            name TEXT,
            type TEXT,
            slot TEXT,
            attack_bonus INTEGER DEFAULT 0,
            defense_bonus INTEGER DEFAULT 0,
            equipped INTEGER DEFAULT 0
        )
    """)

    # Daily monster kill tracker (per day, resets with date)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monster_kills (
            username TEXT,
            monster_id TEXT,
            date TEXT,
            PRIMARY KEY (username, monster_id, date)
        )
    """)

    # Achievements
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            username TEXT,
            achievement_id TEXT,
            unlocked_at INTEGER,
            PRIMARY KEY (username, achievement_id)
        )
    """)

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect("village.db")
    conn.row_factory = sqlite3.Row
    return conn
