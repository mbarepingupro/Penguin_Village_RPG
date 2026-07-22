import sqlite3
import os
DATABASE = os.environ.get('DATABASE_PATH', 'village.db')

def _add_col(cursor, table, col_def):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception:
        pass  # column already exists


def init_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
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
            item_id TEXT NOT NULL,
            obtained_at INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS igloos (
            username TEXT PRIMARY KEY,
            room_level INTEGER DEFAULT 1,
            floor_type TEXT DEFAULT 'ice',
            wall_type TEXT DEFAULT 'snow'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS igloo_furniture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            item_id TEXT NOT NULL,
            grid_x INTEGER NOT NULL,
            grid_y INTEGER NOT NULL,
            rotation INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS help_dismissed (
            username TEXT NOT NULL,
            help_key TEXT NOT NULL,
            PRIMARY KEY (username, help_key)
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
        CREATE TABLE IF NOT EXISTS player_lootboxes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    NOT NULL,
            source     TEXT    NOT NULL,
            opened     INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
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
            created_at INTEGER NOT NULL,
            participants TEXT DEFAULT NULL
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

    # One row per minigame attempt (raw score, not normalized -- see
    # app.py's minigame_complete()). This single per-attempt ledger is the
    # minimal schema that serves both the Award Hall's all-time records
    # (MAX(score) per building_id) and the weekly combined leaderboard
    # (MAX(score) per username+building_id within the week's time range) --
    # no separate per-week rollup table needed.
    c.execute("""
        CREATE TABLE IF NOT EXISTS minigame_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            building_id TEXT NOT NULL,
            score INTEGER NOT NULL,
            played_at INTEGER NOT NULL
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS bank_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_username TEXT NOT NULL,
            listing_type TEXT NOT NULL,
            offer_gear_id INTEGER DEFAULT NULL,
            offer_resource TEXT DEFAULT NULL,
            offer_amount INTEGER DEFAULT 0,
            ask_resource TEXT NOT NULL,
            ask_amount INTEGER NOT NULL,
            status TEXT DEFAULT 'open',
            created_at INTEGER DEFAULT 0,
            completed_at INTEGER DEFAULT 0,
            buyer_username TEXT DEFAULT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    NOT NULL,
            message    TEXT    NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_created_at ON chat_messages(created_at)"
    )

    c.execute("""
        CREATE TABLE IF NOT EXISTS penguin_interests (
            username     TEXT NOT NULL,
            interest_key TEXT NOT NULL,
            PRIMARY KEY (username, interest_key)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS topic_suggestions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT    NOT NULL,
            suggestion TEXT    NOT NULL,
            created_at INTEGER NOT NULL,
            status     TEXT    NOT NULL DEFAULT 'pending'
        )
    """)

    # Mayor-approved topics (accepted suggestions + directly-added ones), merged
    # with the hardcoded INTEREST_TOPICS at read time in app.py's get_all_topics().
    c.execute("""
        CREATE TABLE IF NOT EXISTS custom_topics (
            key        TEXT PRIMARY KEY,
            label      TEXT NOT NULL,
            emoji      TEXT NOT NULL DEFAULT '🏷️',
            created_at INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_challenges (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_type      TEXT    NOT NULL,
            threshold        INTEGER NOT NULL,
            current_progress INTEGER NOT NULL DEFAULT 0,
            week_start       TEXT    NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'active',
            created_at       INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS raid_state (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id      INTEGER NOT NULL REFERENCES weekly_challenges(id),
            boss_name         TEXT    NOT NULL,
            boss_max_hp       INTEGER NOT NULL DEFAULT 0,
            boss_current_hp   INTEGER NOT NULL DEFAULT 0,
            status            TEXT    NOT NULL DEFAULT 'inactive',
            join_window_start INTEGER DEFAULT NULL,
            raid_start        INTEGER DEFAULT NULL,
            raid_end          INTEGER DEFAULT NULL,
            created_at        INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS raid_participants (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            raid_id            INTEGER NOT NULL REFERENCES raid_state(id),
            username           TEXT    NOT NULL,
            joined_at          INTEGER NOT NULL,
            total_damage_dealt INTEGER NOT NULL DEFAULT 0,
            UNIQUE(raid_id, username)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS raid_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Weekly building leaderboard -- tracks cumulative ice_blocks earned (not
    # currently held) per player over a rotating week, independent cadence
    # from the raid Mon/Fri/Sat/Mon schedule above. Same three-table split as
    # the raid system: a live table for the in-progress week, an archive of
    # resolved standings (Phase 3c reads this for reward distribution), and a
    # single-row state table tracking the current week_id (a plain
    # incrementing counter, not date-derived, so an inactive/empty week still
    # advances correctly on reset instead of stalling on MAX(week_id)).
    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_build_leaderboard (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            username         TEXT    NOT NULL UNIQUE,
            ice_blocks_total INTEGER NOT NULL DEFAULT 0,
            week_id          INTEGER NOT NULL,
            updated_at       INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_build_leaderboard_archive (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id             INTEGER NOT NULL,
            rank                INTEGER NOT NULL,
            username            TEXT    NOT NULL,
            ice_blocks_total    INTEGER NOT NULL,
            archived_at         INTEGER NOT NULL,
            reward_lootboxes    INTEGER NOT NULL DEFAULT 0,
            reward_lootbox_ids  TEXT    NOT NULL DEFAULT '[]',
            reward_resources    TEXT    NOT NULL DEFAULT '{}',
            notified            INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Added after the table's initial rollout -- _add_col back-fills any DB
    # created before rewards existed (see resolve_weekly_build_leaderboard()
    # in app.py, Phase 3b) with the same defaults as a fresh CREATE above.
    _add_col(c, "weekly_build_leaderboard_archive", "reward_lootboxes INTEGER NOT NULL DEFAULT 0")
    _add_col(c, "weekly_build_leaderboard_archive", "reward_lootbox_ids TEXT NOT NULL DEFAULT '[]'")
    _add_col(c, "weekly_build_leaderboard_archive", "reward_resources TEXT NOT NULL DEFAULT '{}'")
    _add_col(c, "weekly_build_leaderboard_archive", "notified INTEGER NOT NULL DEFAULT 0")

    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_build_leaderboard_state (
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            week_id INTEGER NOT NULL DEFAULT 1
        )
    """)
    c.execute("INSERT OR IGNORE INTO weekly_build_leaderboard_state (id, week_id) VALUES (1, 1)")

    # One-shot cross-session notification queue: /stream/build_command (a
    # StreamerBot-triggered Build! roll, no browser fetch involved) writes a
    # row here so the player's own open tab -- polling GET
    # /stream/pending_animations -- can still play the normal resource-collect
    # animation for a reward it never made the /build/roll request for. Same
    # "DB row as the delivery marker" idea as weekly_build_leaderboard_archive's
    # notified column above, just per-event instead of per-week.
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_animations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL,
            resource_type TEXT    NOT NULL,
            amount        INTEGER NOT NULL,
            crit          INTEGER NOT NULL DEFAULT 0,
            consumed      INTEGER NOT NULL DEFAULT 0,
            created_at    INTEGER NOT NULL
        )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_pending_animations_username "
        "ON pending_animations(username, consumed)"
    )

    # Short-lived one-time codes for manually linking a Twitch Extension
    # viewer (identified only by an opaque per-extension id, no shared real
    # identity) to their existing account. /extension/link/start (called from
    # the extension panel, once it exists) mints a row here; the player pastes
    # the code into the site's own logged-in UI, which redeems it via
    # /extension/link/redeem. `code` doubles as the primary key since it's
    # already required to be unique.
    c.execute("""
        CREATE TABLE IF NOT EXISTS extension_link_codes (
            code           TEXT    PRIMARY KEY,
            opaque_user_id TEXT    NOT NULL,
            created_at     INTEGER NOT NULL,
            expires_at     INTEGER NOT NULL,
            used           INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Catalog tables -- DB-backed mirrors of what are still (as of this pass)
    # the source-of-truth dict literals in app.py (BARRACKS_SHOP,
    # BOUTIQUE_ITEMS, GEAR_TEMPLATES, SET_BONUSES). Seeded once by
    # migrate_catalog_tables.py; no route reads from these tables yet -- that
    # switchover is a separate, later pass. cost is JSON-encoded (resource ->
    # int), same convention as raid_settings' value column.
    c.execute("""
        CREATE TABLE IF NOT EXISTS barracks_shop (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            slot            TEXT NOT NULL,
            rarity          TEXT NOT NULL,
            combat_power    INTEGER NOT NULL,
            cost            TEXT NOT NULL,
            event_exclusive INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS boutique_items (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            category        TEXT NOT NULL,
            slot            TEXT NOT NULL,
            price           INTEGER NOT NULL,
            tier            TEXT NOT NULL,
            event_exclusive INTEGER NOT NULL DEFAULT 0
        )
    """)

    # id is synthetic -- GEAR_TEMPLATES entries have no stable id in app.py
    # (a fresh item_id is generated per drop instead); migrate_catalog_tables.py
    # derives one as slugify(name)_slot_rarity so each row has a stable PK.
    c.execute("""
        CREATE TABLE IF NOT EXISTS gear_templates (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            slot         TEXT NOT NULL,
            rarity       TEXT NOT NULL,
            set_name     TEXT DEFAULT NULL,
            combat_power INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS set_bonuses (
            set_name                TEXT PRIMARY KEY,
            pieces_needed            INTEGER NOT NULL,
            bonus_2pc_cp             INTEGER NOT NULL,
            bonus_2pc_desc           TEXT NOT NULL,
            bonus_3pc_cp             INTEGER NOT NULL,
            bonus_3pc_desc           TEXT NOT NULL,
            secret_cosmetic_required TEXT DEFAULT NULL,
            secret_cp                INTEGER NOT NULL,
            secret_desc              TEXT NOT NULL
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
    _add_col(c, "penguins", "tutorial_step INTEGER DEFAULT 0")
    _add_col(c, "penguins", "tutorial_rewards_given TEXT DEFAULT '[]'")
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
    # Session 8: combat gear level tiers -- minimum player level to /gear/equip
    # (not /gear/wear -- cosmetic slots stay ungated). barracks_shop mirrors
    # the same gate for its forged items (see catalog.py's
    # _BARRACKS_REQUIRED_LEVEL), gear_templates carries the real per-set
    # values (see catalog.DEFAULT_GEAR_TEMPLATES).
    _add_col(c, "gear_templates", "required_level INTEGER DEFAULT 1")
    _add_col(c, "barracks_shop", "required_level INTEGER DEFAULT 1")
    _add_col(c, "gear", "worn INTEGER DEFAULT 0")
    _add_col(c, "gear", "listed INTEGER DEFAULT 0")
    _add_col(c, "gear", "bank_sell_price INTEGER DEFAULT 0")
    _add_col(c, "gear", "bank_listed_at INTEGER DEFAULT 0")
    # Who sold this item to the bank, if it's currently a bank listing (or
    # was one previously) -- purely informational, never read by any pricing,
    # ownership, or expiry logic. NULL for items that never went through
    # bank_sell_to_bank().
    _add_col(c, "gear", "original_owner TEXT DEFAULT NULL")
    _add_col(c, "penguins", "total_monsters_defeated INTEGER DEFAULT 0")
    _add_col(c, "penguins", "total_resources_collected INTEGER DEFAULT 0")
    _add_col(c, "penguins", "total_gold_collected INTEGER DEFAULT 0")
    _add_col(c, "penguins", "penguin_shape TEXT DEFAULT 'normal'")
    _add_col(c, "penguins", "auth_provider TEXT DEFAULT 'twitch'")
    _add_col(c, "penguins", "discord_id TEXT DEFAULT NULL")
    # Twitch's stable numeric user id (distinct from `username`, which is the
    # Twitch login name and can change) -- for future Twitch Extension
    # identity linking. See the Twitch OAuth callback in app.py.
    _add_col(c, "penguins", "twitch_user_id TEXT DEFAULT NULL")
    # Opaque per-extension viewer id from the Twitch Extension Helper JWT,
    # linked via the code-based flow in app.py's /extension/link/* routes.
    # Deliberately separate from twitch_user_id above -- an opaque id is only
    # meaningful within this one extension (and isn't stable Twitch identity),
    # so it must never be treated as interchangeable with the real Twitch id.
    _add_col(c, "penguins", "extension_opaque_id TEXT DEFAULT NULL")
    _add_col(c, "resources", "ice_blocks INTEGER DEFAULT 0")
    _add_col(c, "penguins", "build_free_rolls INTEGER DEFAULT 0")
    _add_col(c, "building_upgrades", "ice_blocks_donated INTEGER DEFAULT 0")
    _add_col(c, "raid_participants", "reward_summary TEXT DEFAULT NULL")
    _add_col(c, "topic_suggestions", "status TEXT DEFAULT 'pending'")
    # JSON array of usernames for group events (see personality_config.GROUP_EVENT_TEMPLATES);
    # NULL for every other event_log row. Lets welcome-back find events a given player took part in.
    _add_col(c, "event_log", "participants TEXT DEFAULT NULL")
    # JSON array of exactly 12 slots -- each either null (rest) or an int
    # 0-7 indexing into the fixed one-octave note set (see app.py's
    # DOORBELL_NOTE_FREQS). NULL means no custom doorbell tune set.
    _add_col(c, "penguins", "doorbell_tune TEXT DEFAULT NULL")
    # Per-player "last delivered" markers for the weekly-challenge/raid
    # lifecycle popups -- store the weekly_challenges/raid_state row id the
    # notice was already shown for, so /lifecycle-notices only ever surfaces
    # each transition to a given player once, no matter how often they poll.
    _add_col(c, "penguins", "notice_challenge_start_id INTEGER DEFAULT 0")
    _add_col(c, "penguins", "notice_challenge_result_id INTEGER DEFAULT 0")
    _add_col(c, "penguins", "notice_raid_start_id INTEGER DEFAULT 0")
    _add_col(c, "penguins", "notice_raid_result_id INTEGER DEFAULT 0")

    # Backfill total_monsters_defeated from existing monster_kills rows
    try:
        c.execute("""
            UPDATE penguins SET total_monsters_defeated = (
                SELECT COUNT(*) FROM monster_kills WHERE monster_kills.username = penguins.username
            ) WHERE total_monsters_defeated = 0
        """)
    except Exception:
        pass

    # Backfill penguin_shape for existing players
    try:
        c.execute("UPDATE penguins SET penguin_shape = 'normal' WHERE penguin_shape IS NULL")
    except Exception:
        pass

    # Convert palette key colors to hex for existing players
    _PALETTE_HEX = {
        "classic_black":  "#1a1a1a",
        "midnight_blue":  "#1a1a4e",
        "forest_green":   "#1a3a1a",
        "deep_red":       "#4a1a1a",
        "warm_brown":     "#3a2a1a",
        "steel_gray":     "#3a3a3a",
        "arctic_white":   "#e8e8e8",
        "royal_blue":     "#1a3a8a",
        "golden_emperor": "#8a6a1a",
        "shadow_purple":  "#3a1a4a",
        "frost_crystal":  "#88c8e8",
        "neon_pink":      "#cc3a7a",
    }
    try:
        for key, hex_val in _PALETTE_HEX.items():
            c.execute("UPDATE penguins SET penguin_color = ? WHERE penguin_color = ?", (hex_val, key))
        # NULL → classic black
        c.execute("UPDATE penguins SET penguin_color = '#1a1a1a' WHERE penguin_color IS NULL OR penguin_color = ''")
    except Exception:
        pass

    # Migrate: cosmetics that were equipped should also be worn (they were shown visually)
    try:
        c.execute("UPDATE gear SET worn=1 WHERE equipped=1 AND type='cosmetic' AND worn=0")
    except Exception:
        pass

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

    # Cosmetic items must never have combat stats
    try:
        c.execute(
            "UPDATE gear SET combat_power=0, attack_bonus=0, defense_bonus=0, speed_bonus=0, hp_bonus=0 "
            "WHERE type='cosmetic'"
        )
    except Exception:
        pass

    # Rebalance CP on existing gear to match updated GEAR_TEMPLATES and BARRACKS_SHOP values
    try:
        # Common monster drops
        c.execute("UPDATE gear SET combat_power=3  WHERE name='Rusty Sword'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=2  WHERE name='Leather Cap'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=2  WHERE name='Worn Boots'           AND type='combat'")
        c.execute("UPDATE gear SET combat_power=3  WHERE name='Padded Vest'          AND type='combat'")
        # Uncommon monster drops (Frost Guardian set)
        c.execute("UPDATE gear SET combat_power=7  WHERE name='Frost Blade'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=5  WHERE name='Frost Helm'           AND type='combat'")
        c.execute("UPDATE gear SET combat_power=5  WHERE name='Frost Greaves'        AND type='combat'")
        c.execute("UPDATE gear SET combat_power=7  WHERE name='Frost Mail'           AND type='combat'")
        # Rare monster drops (Blood Reaper set)
        c.execute("UPDATE gear SET combat_power=15 WHERE name='Blood Reaper'         AND type='combat'")
        c.execute("UPDATE gear SET combat_power=12 WHERE name='Blood Crown'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=11 WHERE name='Blood Stompers'       AND type='combat'")
        c.execute("UPDATE gear SET combat_power=14 WHERE name='Blood Plate'          AND type='combat'")
        # Epic monster drops (Temple Mystic set)
        c.execute("UPDATE gear SET combat_power=28 WHERE name='Temple Mystic Staff'  AND type='combat'")
        c.execute("UPDATE gear SET combat_power=22 WHERE name='Temple Mystic Hood'   AND type='combat'")
        c.execute("UPDATE gear SET combat_power=20 WHERE name='Temple Mystic Sandals'AND type='combat'")
        c.execute("UPDATE gear SET combat_power=25 WHERE name='Temple Mystic Robes'  AND type='combat'")
        # Legendary monster drops (Penguin Emperor set) -- Session 8 bumped
        # these from 45/35/32/42 (total 154, the shared legendary split) to
        # 56/43/39/52 (total 190), scaled proportionally to that same split,
        # since Penguin Emperor kept its piece names but is now a standalone
        # set stronger than the 5-tier ladder's legendary stage.
        c.execute("UPDATE gear SET combat_power=56 WHERE name=\"Emperor's Scepter\"  AND type='combat'")
        c.execute("UPDATE gear SET combat_power=43 WHERE name=\"Emperor's Diadem\"   AND type='combat'")
        c.execute("UPDATE gear SET combat_power=39 WHERE name=\"Emperor's Sabatons\" AND type='combat'")
        c.execute("UPDATE gear SET combat_power=52 WHERE name=\"Emperor's Regalia\"  AND type='combat'")
        # Barracks forged — common
        c.execute("UPDATE gear SET combat_power=4  WHERE name='Iron Sword'           AND type='combat'")
        c.execute("UPDATE gear SET combat_power=3  WHERE name='Iron Helmet'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=3  WHERE name='Iron Boots'           AND type='combat'")
        c.execute("UPDATE gear SET combat_power=4  WHERE name='Iron Plate'           AND type='combat'")
        # Barracks forged — uncommon
        c.execute("UPDATE gear SET combat_power=9  WHERE name='Steel Sword'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=7  WHERE name='Steel Helmet'         AND type='combat'")
        c.execute("UPDATE gear SET combat_power=6  WHERE name='Steel Boots'          AND type='combat'")
        c.execute("UPDATE gear SET combat_power=9  WHERE name='Steel Plate'          AND type='combat'")
        # Barracks forged — rare
        c.execute("UPDATE gear SET combat_power=19 WHERE name='Crystal Blade'        AND type='combat'")
        c.execute("UPDATE gear SET combat_power=15 WHERE name='Crystal Crown'        AND type='combat'")
        c.execute("UPDATE gear SET combat_power=14 WHERE name='Crystal Greaves'      AND type='combat'")
        c.execute("UPDATE gear SET combat_power=18 WHERE name='Crystal Armor'        AND type='combat'")
        # Catch-all: reset any remaining inflated starter/misc items
        c.execute("UPDATE gear SET combat_power=2  WHERE name LIKE 'Worn%'  AND type='combat' AND combat_power > 2")
        c.execute("UPDATE gear SET combat_power=2  WHERE name LIKE 'Fish%'  AND type='combat' AND combat_power > 2")
        c.execute("UPDATE gear SET combat_power=1  WHERE name LIKE 'Basic%' AND type='combat' AND combat_power > 1")
        # Safety: cosmetics always 0 CP
        c.execute("UPDATE gear SET combat_power=0  WHERE type='cosmetic'")
    except Exception:
        pass

    # Migrate igloo_items to new schema (replaces old x/y placement system)
    try:
        c.execute("SELECT obtained_at FROM igloo_items LIMIT 1")
    except Exception:
        c.execute("DROP TABLE IF EXISTS igloo_items")
        c.execute("""CREATE TABLE igloo_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at INTEGER NOT NULL,
            placed INTEGER DEFAULT 0,
            UNIQUE(username, item_id)
        )""")

    # Migrate igloo_items again: drop UNIQUE(username, item_id) and the
    # `placed` column so a player can own multiple units of the same
    # furniture item, each independently placeable. Ownership/placed counts
    # are now derived (COUNT igloo_items rows / COUNT igloo_furniture rows
    # per item_id) rather than tracked on the ownership row itself.
    try:
        row = c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='igloo_items'"
        ).fetchone()
        if row and row[0] and "UNIQUE" in row[0]:
            c.execute("ALTER TABLE igloo_items RENAME TO igloo_items_old")
            c.execute("""CREATE TABLE igloo_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                item_id TEXT NOT NULL,
                obtained_at INTEGER NOT NULL
            )""")
            c.execute("""
                INSERT INTO igloo_items (id, username, item_id, obtained_at)
                SELECT id, username, item_id, obtained_at FROM igloo_items_old
            """)
            c.execute("DROP TABLE igloo_items_old")
    except Exception:
        pass

    _add_col(c, "igloos", "unlocked_floors TEXT DEFAULT 'ice'")
    _add_col(c, "igloos", "unlocked_walls TEXT DEFAULT 'snow'")
    _add_col(c, "igloos", "floor_cells TEXT DEFAULT '{}'")
    _add_col(c, "igloos", "wall_cells TEXT DEFAULT '{}'")

    # Initialize igloo rows for all existing penguins
    try:
        c.execute("INSERT OR IGNORE INTO igloos (username) SELECT username FROM penguins")
    except Exception:
        pass

    # Backfill: players who already use a non-default floor/wall get it unlocked for free
    try:
        c.execute("""
            UPDATE igloos SET unlocked_floors =
              CASE WHEN floor_type != 'ice' AND instr(COALESCE(unlocked_floors,'ice'), floor_type) = 0
                   THEN COALESCE(unlocked_floors,'ice') || ',' || floor_type
                   ELSE COALESCE(unlocked_floors,'ice')
              END
        """)
        c.execute("""
            UPDATE igloos SET unlocked_walls =
              CASE WHEN wall_type != 'snow' AND instr(COALESCE(unlocked_walls,'snow'), wall_type) = 0
                   THEN COALESCE(unlocked_walls,'snow') || ',' || wall_type
                   ELSE COALESCE(unlocked_walls,'snow')
              END
        """)
    except Exception:
        pass

    # Seed the catalog tables (barracks_shop/boutique_items/gear_templates/
    # set_bonuses) the first time they're empty -- e.g. a genuinely fresh
    # database. Must happen here, once, on init_db()'s own single connection
    # before any request handling starts: catalog.py's load_*() functions
    # are read-only and may run on a borrowed, already-mid-transaction `db`
    # from a caller (see raid_settings.get_setting's docstring on why that
    # matters) -- a lazy seed-on-read there previously caused a real
    # "database is locked" error when a second connection (e.g.
    # get_combat_power()'s own) tried to write into a table while another
    # connection held an uncommitted transaction on it.
    import catalog
    catalog._seed_barracks_shop_if_empty(c, owns_conn=False)
    catalog._seed_boutique_items_if_empty(c, owns_conn=False)
    catalog._seed_gear_templates_if_empty(c, owns_conn=False)
    catalog._seed_set_bonuses_if_empty(c, owns_conn=False)

    # Session 9: keep barracks_shop.required_level in sync with catalog.py's
    # live _BARRACKS_REQUIRED_LEVEL every startup, not just once at seed time
    # (_seed_barracks_shop_if_empty above only runs on a genuinely empty
    # table, so a database seeded before this tier spread existed would
    # otherwise keep its stale values forever). This is what the standalone
    # migrate_barracks_tier_levels.py script used to require someone to
    # remember to run by hand against the live database -- a step that, in
    # practice, never happened. Cheap (5 UPDATEs, no-ops once in sync), so
    # it's safe to run unconditionally on every boot instead.
    try:
        for rarity, required_level in catalog._BARRACKS_REQUIRED_LEVEL.items():
            c.execute(
                "UPDATE barracks_shop SET required_level=? WHERE rarity=? AND required_level!=?",
                (required_level, rarity, required_level)
            )
    except Exception:
        pass

    # Session 9: retroactively unequip any currently-EQUIPPED combat gear a
    # player's level no longer (or never did) qualify for. /gear/equip's
    # required_level check (app.py's _gear_required_level) only fires on the
    # ACT of equipping -- gear equipped before required_level existed, or
    # before required_level was populated correctly (see barracks_shop sync
    # just above), stayed equipped forever with no re-check. Mirrors
    # _gear_required_level's own lookup order (barracks_shop by item_id
    # first, else gear_templates by name+slot+rarity, else no gate) as a
    # bulk SQL pass -- database.py can't import app.py (app.py imports this
    # module, not the reverse), so this can't just call that helper.
    try:
        c.execute("""
            UPDATE gear
            SET equipped = 0
            WHERE equipped = 1
              AND type = 'combat'
              AND COALESCE(
                    (SELECT bs.required_level FROM barracks_shop bs WHERE bs.id = gear.item_id),
                    (SELECT gt.required_level FROM gear_templates gt
                     WHERE UPPER(gt.name) = UPPER(gear.name)
                       AND gt.slot = gear.slot AND gt.rarity = gear.rarity
                     LIMIT 1),
                    1
                  ) > COALESCE(
                    (SELECT p.level FROM penguins p WHERE p.username = gear.username),
                    1
                  )
        """)
    except Exception:
        pass

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def record_challenge_progress(db, metric_type, amount):
    """Increment current_progress on the active weekly_challenges row if metric matches.

    Executes on the caller's own db connection instead of opening a separate
    one — a second connection here would contend for the write lock against
    whatever transaction the caller already has open (add_gold, combat fight,
    job collect, etc. all call this mid-transaction), blocking for the full
    busy-timeout and then silently failing to record anything. That was
    exactly the cause of a ~10s delay on every monster fight (and every
    gold/resource gain) while a matching weekly challenge was active, with
    progress never actually incrementing.

    Safe to call from any reward-granting code path — silently no-ops when
    there is no active challenge, or when the active challenge has a
    different metric_type. Caller owns the transaction/commit.
    """
    if amount <= 0:
        return
    try:
        db.execute(
            "UPDATE weekly_challenges SET current_progress = current_progress + ? "
            "WHERE status = 'active' AND metric_type = ?",
            (amount, metric_type),
        )
    except Exception:
        pass  # never raise from an instrumentation helper


def record_build_leaderboard_progress(db, username, amount):
    """Increment username's cumulative ice_blocks_total for the current week.

    Executes on the caller's own db connection -- same fix as
    record_challenge_progress() above (see the Session 6 SQLite-locking
    audit): opening a second connection here would contend for the write
    lock against /build/roll's already-open transaction on this same
    connection. Caller owns the transaction/commit.

    Tracks blocks EARNED, not blocks currently held -- donating ice_blocks
    to a building only ever decrements resources.ice_blocks, never this
    table, so no adjustment is needed anywhere else for donations to stay
    out of this total.
    """
    if amount <= 0:
        return
    try:
        import time as _time
        row     = db.execute("SELECT week_id FROM weekly_build_leaderboard_state WHERE id=1").fetchone()
        week_id = row["week_id"] if row else 1
        now     = int(_time.time())
        db.execute(
            "INSERT INTO weekly_build_leaderboard (username, ice_blocks_total, week_id, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET "
            "ice_blocks_total = ice_blocks_total + excluded.ice_blocks_total, "
            "week_id = excluded.week_id, updated_at = excluded.updated_at",
            (username, amount, week_id, now),
        )
    except Exception:
        pass  # never raise from an instrumentation helper


def backfill_cosmetics(LEVEL_DATA, COSMETIC_SLOTS):
    import time as _time
    conn = sqlite3.connect(DATABASE, timeout=30)
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
