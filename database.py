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

    try:
        cursor.execute("ALTER TABLE penguins ADD COLUMN last_active INTEGER DEFAULT 0")
    except:
        pass

    conn.commit()
    conn.close()
   
def get_db():
    conn = sqlite3.connect("village.db")
    conn.row_factory = sqlite3.Row
    return conn