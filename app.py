from dotenv import load_dotenv
import os
import datetime
import random
from flask import Flask, jsonify, redirect, request, session, url_for, render_template
from database import init_db, get_db
from feature_flags import FEATURES
from level_config import LEVEL_DATA, get_total_gathering_bonus, get_next_milestone
import time
import requests as http_requests

load_dotenv()

TWITCH_CLIENT_ID    = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
SECRET_KEY          = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── BUILDINGS ─────────────────────────────────────────────────────────────────
# produces = per-hour rates. Jobs cap at JOB_CAP_HOURS; earned = floor(rate * hours).
JOB_CAP_HOURS = 8.0

BUILDINGS = {
    "hotel": {
        "name": "Penguin Hotel", "icon": "🏨",
        "desc": "Rest those flippers. You've earned it.",
        "type": "rest", "rest_cost": 50,
        "pos": {"x": 12, "y": 62},
    },
    "horny_jail": {
        "name": "Horny Jail", "icon": "🔒",
        "desc": "You know what you did.",
        "type": "placeholder",
        "pos": {"x": 24, "y": 63},
    },
    "award_hall": {
        "name": "Award Hall", "icon": "🏆",
        "desc": "Your ego, immortalised in pixel form.",
        "type": "achievements",
        "pos": {"x": 30, "y": 48},
    },
    "sea_lion_pit": {
        "name": "Ash's Sea Lion Pit", "icon": "🦭",
        "desc": "Fish don't catch themselves. Actually here they do.",
        "type": "job", "job_label": "FISHING",
        "produces": {"fish": 0.2, "gold": 1.0, "xp": 2.0},
        "pos": {"x": 36, "y": 62},
    },
    "parkmusement": {
        "name": "Ash's Parkmusement", "icon": "🎪",
        "desc": "Step right up! Juggle fish for coins! No refunds.",
        "type": "job", "job_label": "CIRCUS",
        "produces": {"gold": 3.0, "xp": 2.0},
        "pos": {"x": 47, "y": 48},
    },
    "cursed_temple": {
        "name": "Cursed Temple", "icon": "⛩️",
        "desc": "Dark rituals. Ancient power. No refunds.",
        "type": "job", "job_label": "MONK",
        "produces": {"blood_gems": 0.2, "xp": 4.0},
        "pos": {"x": 9, "y": 30},
    },
    "club_soda": {
        "name": "Club Soda", "icon": "🌿",
        "desc": "Where the herbs are fresh and the beats are questionable.",
        "type": "job", "job_label": "HERBALISM",
        "produces": {"herbs": 0.2, "gold": 1.0, "xp": 2.0},
        "pos": {"x": 67, "y": 58},
    },
    "barracks": {
        "name": "Penguin Barracks", "icon": "⚔️",
        "desc": "Gear up. Fight stuff. Try not to die.",
        "type": "combat",
        "pos": {"x": 79, "y": 57},
    },
    "guillotine": {
        "name": "Gil the Guillotine", "icon": "💀",
        "desc": "A hard day's work. Blood gems don't collect themselves.",
        "type": "job", "job_label": "EXECUTIONER",
        "produces": {"blood_gems": 0.1, "bones": 0.1, "gold": 1.0, "xp": 2.0},
        "pos": {"x": 84, "y": 58},
    },
}

# ── MONSTERS ──────────────────────────────────────────────────────────────────
MONSTERS = {
    "snow_crab":      {"name":"Snow Crab",      "tier":1,"min_level":1, "hp":30,  "attack":5,  "defense":3,  "rewards":{"fish":5,  "gold":8,  "xp":15}, "drop_name":"Ice Shard",      "drop_chance":0.30,"icon":"🦀"},
    "ice_bat":        {"name":"Ice Bat",         "tier":1,"min_level":1, "hp":20,  "attack":8,  "defense":2,  "rewards":{"herbs":3, "gold":6,  "xp":12}, "drop_name":"Bat Wing",       "drop_chance":0.40,"icon":"🦇"},
    "frost_rat":      {"name":"Frost Rat",       "tier":1,"min_level":1, "hp":15,  "attack":6,  "defense":1,  "rewards":{"bones":3, "gold":5,  "xp":10}, "drop_name":"Rat Tail",       "drop_chance":0.50,"icon":"🐀"},
    "blizzard_wolf":  {"name":"Blizzard Wolf",   "tier":2,"min_level":6, "hp":60,  "attack":15, "defense":8,  "rewards":{"blood_gems":3,"gold":20,"xp":30},"drop_name":"Wolf Fang",    "drop_chance":0.30,"icon":"🐺"},
    "cursed_snowman": {"name":"Cursed Snowman",  "tier":2,"min_level":6, "hp":50,  "attack":12, "defense":10, "rewards":{"spell_fragments":3,"gold":18,"xp":28},"drop_name":"Cursed Carrot","drop_chance":0.25,"icon":"☃️"},
    "shadow_penguin": {"name":"Shadow Penguin",  "tier":2,"min_level":6, "hp":55,  "attack":14, "defense":7,  "rewards":{"bones":5, "gold":22, "xp":35}, "drop_name":"Shadow Feather", "drop_chance":0.20,"icon":"🐧"},
    "stone_golem":    {"name":"Stone Golem",     "tier":3,"min_level":16,"hp":120, "attack":25, "defense":20, "rewards":{"blood_gems":8,"gold":40,"xp":60},"drop_name":"Stone Core",   "drop_chance":0.20,"icon":"🗿"},
    "sea_serpent":    {"name":"Sea Serpent",     "tier":3,"min_level":16,"hp":100, "attack":22, "defense":15, "rewards":{"fish":15, "gold":35, "xp":55}, "drop_name":"Serpent Scale",  "drop_chance":0.15,"icon":"🐍"},
    "dark_druid":     {"name":"Dark Druid",      "tier":3,"min_level":16,"hp":110, "attack":28, "defense":12, "rewards":{"spell_fragments":8,"herbs":5,"gold":45,"xp":70},"drop_name":"Druid Staff","drop_chance":0.10,"icon":"🧙"},
}

# ── GEAR CATALOG ──────────────────────────────────────────────────────────────
# cost keys: 'gold' + resource names (never gold alone)
GEAR_CATALOG = {
    # Weapons
    "fish_club":   {"name":"FISH CLUB",       "set_name":None,            "type":"combat",  "slot":"weapon","rarity":"common",   "attack_bonus":5,  "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":50}},
    "bone_dagger": {"name":"BONE DAGGER",     "set_name":"Blood Reaper",  "type":"combat",  "slot":"weapon","rarity":"uncommon", "attack_bonus":10, "defense_bonus":0, "speed_bonus":2,"hp_bonus":0, "cost":{"gold":80,  "bones":10}},
    "ice_sword":   {"name":"ICE SWORD",       "set_name":"Frost Guardian","type":"combat",  "slot":"weapon","rarity":"rare",     "attack_bonus":18, "defense_bonus":2, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":200, "fish":30}},
    "blood_axe":   {"name":"BLOOD AXE",       "set_name":"Blood Reaper",  "type":"combat",  "slot":"weapon","rarity":"epic",     "attack_bonus":30, "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":500, "blood_gems":15}},
    # Chest armor
    "fish_vest":   {"name":"FISH SCALE VEST", "set_name":"Frost Guardian","type":"combat",  "slot":"chest", "rarity":"common",   "attack_bonus":0,  "defense_bonus":8, "speed_bonus":0,"hp_bonus":10,"cost":{"gold":60,  "fish":15}},
    "bone_plate":  {"name":"BONE PLATE",      "set_name":"Blood Reaper",  "type":"combat",  "slot":"chest", "rarity":"uncommon", "attack_bonus":0,  "defense_bonus":12,"speed_bonus":0,"hp_bonus":15,"cost":{"gold":120, "bones":20}},
    "ice_plate":   {"name":"ICE PLATE",       "set_name":"Frost Guardian","type":"combat",  "slot":"chest", "rarity":"rare",     "attack_bonus":0,  "defense_bonus":22,"speed_bonus":0,"hp_bonus":25,"cost":{"gold":300, "fish":40,"herbs":10}},
    # Boots
    "leather_boots":{"name":"LEATHER BOOTS",  "set_name":None,            "type":"combat",  "slot":"boots", "rarity":"common",   "attack_bonus":0,  "defense_bonus":3, "speed_bonus":5,"hp_bonus":0, "cost":{"gold":40}},
    "bone_boots":  {"name":"BONE BOOTS",      "set_name":"Blood Reaper",  "type":"combat",  "slot":"boots", "rarity":"uncommon", "attack_bonus":2,  "defense_bonus":5, "speed_bonus":8,"hp_bonus":0, "cost":{"gold":100, "bones":15}},
    "frost_boots": {"name":"FROST BOOTS",     "set_name":"Frost Guardian","type":"combat",  "slot":"boots", "rarity":"rare",     "attack_bonus":0,  "defense_bonus":8, "speed_bonus":12,"hp_bonus":5,"cost":{"gold":250, "fish":20,"spell_fragments":5}},
    # Cosmetics
    "tophat":      {"name":"TOP HAT",         "set_name":None,            "type":"cosmetic","slot":"hat",   "rarity":"common",   "attack_bonus":0,  "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":25}},
    "party_hat":   {"name":"PARTY HAT",       "set_name":None,            "type":"cosmetic","slot":"hat",   "rarity":"common",   "attack_bonus":0,  "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":15}},
    "crown":       {"name":"CROWN",           "set_name":None,            "type":"cosmetic","slot":"hat",   "rarity":"rare",     "attack_bonus":0,  "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":200}},
    "red_cape":    {"name":"RED CAPE",        "set_name":None,            "type":"cosmetic","slot":"cape",  "rarity":"common",   "attack_bonus":0,  "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":20}},
    "star_cape":   {"name":"STAR CAPE",       "set_name":None,            "type":"cosmetic","slot":"cape",  "rarity":"uncommon", "attack_bonus":0,  "defense_bonus":0, "speed_bonus":0,"hp_bonus":0, "cost":{"gold":80,  "herbs":10}},
}

# ── ACHIEVEMENT DEFINITIONS ───────────────────────────────────────────────────
ACHIEVEMENT_DEFS = {
    "first_login":    {"title":"WELCOME HOME",      "desc":"Log in for the first time",         "icon":"🐧", "category":"village"},
    "first_job":      {"title":"CLOCK IN",          "desc":"Complete your first job",           "icon":"⚒️", "category":"jobs"},
    "first_fight":    {"title":"BRAVE (OR DUMB)",   "desc":"Fight your first monster",          "icon":"⚔️", "category":"combat"},
    "first_kill":     {"title":"MONSTER SLAYER",    "desc":"Defeat your first monster",         "icon":"💀", "category":"combat"},
    "level_5":        {"title":"RISING STAR",       "desc":"Reach level 5",                     "icon":"⭐", "category":"village"},
    "level_10":       {"title":"VILLAGE LEGEND",    "desc":"Reach level 10",                    "icon":"🌟", "category":"village"},
    "level_20":       {"title":"SEASONED VETERAN",  "desc":"Reach level 20",                    "icon":"💫", "category":"village"},
    "gold_500":       {"title":"GETTING PAID",      "desc":"Accumulate 500 gold",               "icon":"💰", "category":"collection"},
    "gold_5000":      {"title":"MONEY PENGUIN",     "desc":"Accumulate 5000 gold total",        "icon":"🤑", "category":"collection"},
    "fish_50":        {"title":"FISHER PENGUIN",    "desc":"Collect 50 fish",                   "icon":"🎣", "category":"jobs"},
    "fish_500":       {"title":"MASTER FISHER",     "desc":"Collect 500 fish",                  "icon":"🐟", "category":"jobs"},
    "kill_10":        {"title":"HUNTER",            "desc":"Defeat 10 monsters",                "icon":"🏹", "category":"combat"},
    "kill_50":        {"title":"VETERAN HUNTER",    "desc":"Defeat 50 monsters",                "icon":"🗡️", "category":"combat"},
    "igloo_5":        {"title":"HOME SWEET IGLOO",  "desc":"Place 5 items in your igloo",       "icon":"🏠", "category":"village"},
    "streak_7":       {"title":"DEDICATED",         "desc":"Log in 7 days in a row",            "icon":"🔥", "category":"village"},
    "streak_30":      {"title":"COMMITTED",         "desc":"Log in 30 days in a row",           "icon":"🔥", "category":"village"},
    "prestige_1":     {"title":"REBORN",            "desc":"Prestige for the first time",       "icon":"♻️", "category":"prestige"},
}

# ── FURNITURE CATALOG ─────────────────────────────────────────────────────────
FURNITURE_CATALOG = {
    "rug":      {"name":"COSY RUG",    "cost":8,  "icon":"🟥"},
    "lamp":     {"name":"ICE LAMP",    "cost":8,  "icon":"🕯️"},
    "chair":    {"name":"ICE CHAIR",   "cost":15, "icon":"🪑"},
    "plant":    {"name":"SNOW PLANT",  "cost":12, "icon":"🌿"},
    "table":    {"name":"FISH TABLE",  "cost":20, "icon":"🍽️"},
    "tv":       {"name":"STREAM TV",   "cost":25, "icon":"📺"},
    "bed":      {"name":"SNOW BED",    "cost":30, "icon":"🛏️"},
    "fishtank": {"name":"FISH TANK",   "cost":35, "icon":"🐠"},
    "penguin":  {"name":"PET PENGUIN", "cost":40, "icon":"🐧"},
    "trophy":   {"name":"TROPHY",      "cost":50, "icon":"🏆"},
}
IGLOO_COLS = 11
IGLOO_ROWS = 8

# ── MISSION DEFINITIONS ───────────────────────────────────────────────────────
MISSION_DEFS = {
    "login_today":  {"title":"SHOW UP",      "desc":"Log in to the village today",       "gold":25,  "target":1, "stream":False, "icon":"🐧"},
    "work_today":   {"title":"CLOCK IN",     "desc":"Send your penguin to work",         "gold":25,  "target":1, "stream":False, "icon":"⚒️"},
    "collect_1":    {"title":"FIRST HAUL",   "desc":"Collect your earnings once",        "gold":30,  "target":1, "stream":False, "icon":"💰"},
    "collect_3":    {"title":"HARD WORKER",  "desc":"Collect earnings 3 times today",    "gold":80,  "target":3, "stream":False, "icon":"⛏️"},
    "fight_1":      {"title":"BRAWLER",      "desc":"Fight a monster today",             "gold":40,  "target":1, "stream":False, "icon":"⚔️"},
    "watch_stream": {"title":"LOYAL VIEWER", "desc":"Watch the stream for 30 minutes",  "gold":100, "target":1, "stream":True,  "icon":"📺"},
    "chat_stream":  {"title":"CHATTERBOX",   "desc":"Send a message during the stream",  "gold":60,  "target":1, "stream":True,  "icon":"💬"},
}
DAILY_MISSIONS = list(MISSION_DEFS.keys())


# ── LEVEL / XP SYSTEM ────────────────────────────────────────────────────────
# XP required to level up from level k: int(80 * k^2.2)
# This gives ~1 week to level 5, level 30 is a long-term prestige target.
def _xp_to_levelup(level):
    return int(80 * (level ** 2.2))

def calc_level(total_xp):
    """Return level 1-30 based on total XP (exponential scaling)."""
    level = 1
    remaining = total_xp
    while level < 30:
        needed = _xp_to_levelup(level)
        if remaining < needed:
            break
        remaining -= needed
        level += 1
    return level

def xp_progress(total_xp):
    """Return (current_level, xp_into_level, xp_needed_for_next) tuple."""
    level = 1
    remaining = total_xp
    while level < 30:
        needed = _xp_to_levelup(level)
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1
    return 30, 0, _xp_to_levelup(30)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_today():
    return datetime.date.today().isoformat()


def ensure_resources(db, username):
    """Create resources row if missing; migrate legacy penguins.coins to gold."""
    db.execute("INSERT OR IGNORE INTO resources (username) VALUES (?)", (username,))
    try:
        p = db.execute("SELECT coins FROM penguins WHERE username=?", (username,)).fetchone()
        if p and p["coins"] and p["coins"] > 0:
            db.execute("UPDATE resources SET gold=gold+? WHERE username=?", (p["coins"], username))
            db.execute("UPDATE penguins SET coins=0 WHERE username=?", (username,))
    except Exception:
        pass


def get_gold(db, username):
    ensure_resources(db, username)
    r = db.execute("SELECT gold FROM resources WHERE username=?", (username,)).fetchone()
    return r["gold"] if r else 0


def add_gold(db, username, amount):
    ensure_resources(db, username)
    db.execute("UPDATE resources SET gold=gold+? WHERE username=?", (amount, username))


def log_event(db, event_type, message, username=None):
    db.execute(
        "INSERT INTO event_log (event_type, message, username, created_at) VALUES (?,?,?,?)",
        (event_type, message, username, int(time.time()))
    )


import json
from pathlib import Path

DAILY_RESOURCE_OPTIONS = [
    ("fish",           "🐟"),
    ("herbs",          "🌿"),
    ("bones",          "🦴"),
    ("blood_gems",     "💎"),
    ("spell_fragments","✨"),
]

STREAK_MILESTONES = {
    3:  {"label": "100 gold",                      "gold": 100},
    7:  {"label": "Resource haul + 300 gold",      "gold": 300},
    14: {"label": "Resource haul + 500 gold",      "gold": 500},
    30: {"label": "Mega haul + 1000 gold",         "gold": 1000},
    60: {"label": "Legendary haul + 2000 gold",    "gold": 2000},
}

# Resources awarded per milestone tier (every 7 days)
_MILESTONE_TIERS = {
    7:  {"gold": 300, "resources": [("fish", 20), ("herbs", 15)]},
    14: {"gold": 500, "resources": [("fish", 30), ("herbs", 20), ("bones", 15)]},
    21: {"gold": 500, "resources": [("blood_gems", 10), ("bones", 25), ("fish", 20)]},
    28: {"gold": 750, "resources": [("blood_gems", 15), ("spell_fragments", 10), ("herbs", 25)]},
}

def compute_daily_reward():
    res_name, res_icon = random.choice(DAILY_RESOURCE_OPTIONS)
    amount = random.randint(2, 5)
    return {"gold": 50, "resource": res_name, "resource_amount": amount, "resource_icon": res_icon}


def award_streak_milestone(db, username, streak):
    """On every 7th login day, award a big resource haul + gold."""
    if streak <= 0 or streak % 7 != 0:
        return None
    cycle = streak % 28 or 28
    tier = _MILESTONE_TIERS.get(cycle, _MILESTONE_TIERS[7])
    gold = tier["gold"]
    resources = tier["resources"]
    add_gold(db, username, gold)
    ensure_resources(db, username)
    for res_key, amount in resources:
        db.execute(f"UPDATE resources SET {res_key}={res_key}+? WHERE username=?", (amount, username))
    res_summary = ", ".join(f"+{amt} {key}" for key, amt in resources)
    log_event(db, "achievement",
              f"{username} hit a {streak}-day streak! Haul: +{gold} gold, {res_summary} 🔥",
              username)
    return {"gold": gold, "resources": resources, "streak": streak}


def update_login_streak(db, username, today):
    db.execute(
        "INSERT OR IGNORE INTO login_streaks (username, current_streak, longest_streak, last_login_date) VALUES (?,1,1,?)",
        (username, today)
    )
    row = db.execute("SELECT * FROM login_streaks WHERE username=?", (username,)).fetchone()
    if row["last_login_date"] == today:
        return row["current_streak"]
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if row["last_login_date"] == yesterday:
        new_streak = row["current_streak"] + 1
    else:
        new_streak = 1
    new_longest = max(row["longest_streak"], new_streak)
    db.execute(
        "UPDATE login_streaks SET current_streak=?, longest_streak=?, last_login_date=? WHERE username=?",
        (new_streak, new_longest, today, username)
    )
    db.execute(
        "UPDATE penguins SET login_streak=? WHERE username=?",
        (new_streak, username)
    )
    return new_streak


def advance_mission(db, username, key, today, amount=1):
    defn = MISSION_DEFS.get(key)
    if not defn:
        return False
    db.execute(
        "INSERT OR IGNORE INTO daily_missions (username, mission_key, date) VALUES (?,?,?)",
        (username, key, today)
    )
    row = db.execute(
        "SELECT progress, completed FROM daily_missions WHERE username=? AND mission_key=? AND date=?",
        (username, key, today)
    ).fetchone()
    if not row or row["completed"]:
        return False
    new_prog = min(row["progress"] + amount, defn["target"])
    done = new_prog >= defn["target"]
    db.execute(
        "UPDATE daily_missions SET progress=?, completed=? WHERE username=? AND mission_key=? AND date=?",
        (new_prog, 1 if done else 0, username, key, today)
    )
    if done:
        add_gold(db, username, defn["gold"])
    return done


def get_player_stats(db, username):
    p = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
    level = p["level"] if p else 1
    attack  = level * 4 + 3
    defense = level * 3
    speed   = level * 2
    hp      = level * 30 + 20
    equipped = db.execute(
        "SELECT attack_bonus, defense_bonus, speed_bonus, hp_bonus FROM gear WHERE username=? AND equipped=1",
        (username,)
    ).fetchall()
    for g in equipped:
        attack  += g["attack_bonus"]
        defense += g["defense_bonus"]
        speed   += g["speed_bonus"]
        hp      += g["hp_bonus"]
    return {"attack": attack, "defense": defense, "speed": speed, "hp": hp, "level": level}


def apply_level_rewards(db, username, reward):
    now = int(time.time())
    if reward.get("gold"):
        add_gold(db, username, reward["gold"])
    if reward.get("max_energy"):
        db.execute("UPDATE penguins SET max_energy=max_energy+? WHERE username=?",
                   (reward["max_energy"], username))
    if reward.get("title"):
        db.execute("UPDATE penguins SET title=? WHERE username=?", (reward["title"], username))
    for cosmetic in reward.get("cosmetics", []):
        item_id = cosmetic.lower().replace(" ", "_").replace("'", "")
        try:
            db.execute(
                "INSERT INTO gear (username, item_id, name, type, slot, rarity, obtained_at) "
                "VALUES (?,?,?,'cosmetic','cosmetic','milestone',?)",
                (username, item_id, cosmetic, now)
            )
        except Exception:
            pass


def award_xp(db, username, amount):
    p = db.execute("SELECT xp, level FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        return False, []
    old_xp    = p["xp"] or 0
    old_level = p["level"] or 1
    new_xp    = old_xp + amount
    new_level = calc_level(new_xp)
    leveled   = new_level > old_level
    db.execute("UPDATE penguins SET xp=?, level=? WHERE username=?", (new_xp, new_level, username))
    rewards_list = []
    if leveled:
        log_event(db, "village", f"{username} reached level {new_level}! 🎉", username)
        for lvl in range(old_level + 1, new_level + 1):
            lv_data = LEVEL_DATA.get(lvl, {})
            reward  = lv_data.get("reward")
            if reward:
                apply_level_rewards(db, username, reward)
            rewards_list.append({
                "level":        lvl,
                "reward":       reward,
                "big_milestone": lv_data.get("big_milestone", False),
            })
    return leveled, rewards_list


def simulate_combat(player_stats, monster):
    php  = player_stats["hp"]
    mhp  = monster["hp"]
    patk = player_stats["attack"]
    pdef = player_stats["defense"]
    matk = monster["attack"]
    mdef = monster["defense"]
    for _ in range(300):
        if php <= 0 or mhp <= 0:
            break
        mhp -= max(1, patk - mdef // 2)
        php -= max(1, matk - pdef // 2)
    return php > 0


def check_achievements(db, username):
    now   = int(time.time())
    p     = db.execute("SELECT level, xp FROM penguins WHERE username=?", (username,)).fetchone()
    r     = db.execute("SELECT gold, fish FROM resources WHERE username=?", (username,)).fetchone()
    kills = db.execute("SELECT COUNT(*) as c FROM monster_kills WHERE username=?", (username,)).fetchone()
    igloo = db.execute("SELECT COUNT(*) as c FROM igloo_items WHERE username=?", (username,)).fetchone()
    streak = db.execute("SELECT current_streak FROM login_streaks WHERE username=?", (username,)).fetchone()
    prest  = db.execute("SELECT prestige FROM penguins WHERE username=?", (username,)).fetchone()

    new_ach = []
    def unlock(aid):
        try:
            db.execute(
                "INSERT INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
                (username, aid, now)
            )
            new_ach.append(aid)
            defn = ACHIEVEMENT_DEFS.get(aid, {})
            log_event(db, "achievement", f"{username} unlocked '{defn.get('title','?')}'! {defn.get('icon','')}", username)
        except Exception:
            pass

    if p:
        if p["level"] >= 5:  unlock("level_5")
        if p["level"] >= 10: unlock("level_10")
        if p["level"] >= 20: unlock("level_20")
    if r:
        if r["gold"] >= 500:  unlock("gold_500")
        if r["gold"] >= 5000: unlock("gold_5000")
        if r["fish"] >= 50:   unlock("fish_50")
        if r["fish"] >= 500:  unlock("fish_500")
    if kills:
        if kills["c"] >= 1:  unlock("first_kill")
        if kills["c"] >= 10: unlock("kill_10")
        if kills["c"] >= 50: unlock("kill_50")
    if igloo and igloo["c"] >= 5:
        unlock("igloo_5")
    if streak:
        if streak["current_streak"] >= 7:  unlock("streak_7")
        if streak["current_streak"] >= 30: unlock("streak_30")
    if prest and prest["prestige"] >= 1:
        unlock("prestige_1")
    return new_ach


# ── APP INIT ──────────────────────────────────────────────────────────────────
init_db()


# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    username = session.get("username")
    if not username:
        return render_template("home.html", logged_in=False, features=FEATURES)
    db = get_db()
    penguin = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not penguin:
        session.clear()
        db.close()
        return render_template("home.html", logged_in=False, features=FEATURES)
    ensure_resources(db, username)
    db.commit()
    resources     = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    streak_row    = db.execute("SELECT current_streak FROM login_streaks WHERE username=?", (username,)).fetchone()
    db.close()
    streak_reward = session.pop("streak_reward", None)
    daily_reward  = session.pop("daily_reward",  None)
    return render_template(
        "home.html",
        logged_in=True,
        penguin=penguin,
        resources=resources,
        streak=streak_row["current_streak"] if streak_row else 1,
        streak_reward=streak_reward,
        daily_reward=daily_reward,
        features=FEATURES,
        level_data=LEVEL_DATA,
    )


@app.route("/login")
def login():
    return redirect(
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={TWITCH_CLIENT_ID}"
        f"&redirect_uri={TWITCH_REDIRECT_URI}"
        "&response_type=code&scope=user:read:email"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    token_resp = http_requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TWITCH_REDIRECT_URI,
    })
    access_token = token_resp.json().get("access_token")
    user_resp = http_requests.get(
        "https://api.twitch.tv/helix/users",
        headers={"Authorization": f"Bearer {access_token}", "Client-Id": TWITCH_CLIENT_ID}
    )
    username = user_resp.json()["data"][0]["login"]
    session["username"] = username

    db = get_db()
    try:
        db.execute("INSERT INTO penguins (username) VALUES (?)", (username,))
        session["new_user"] = True
        log_event(db, "village", f"{username} joined the village! 🐧", username)
    except Exception:
        session["new_user"] = False

    today = get_today()
    ensure_resources(db, username)
    streak_row_pre = db.execute("SELECT last_login_date FROM login_streaks WHERE username=?", (username,)).fetchone()
    is_new_day = not streak_row_pre or streak_row_pre["last_login_date"] != today
    streak = update_login_streak(db, username, today)
    if is_new_day:
        session["daily_reward"] = compute_daily_reward()
    streak_reward = award_streak_milestone(db, username, streak)
    if streak_reward:
        session["streak_reward"] = streak_reward
    advance_mission(db, username, "login_today", today)
    try:
        db.execute(
            "INSERT OR IGNORE INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
            (username, "first_login", int(time.time()))
        )
    except Exception:
        pass
    check_achievements(db, username)
    db.commit()
    db.close()
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/profile/<username>")
def profile(username):
    db = get_db()
    p = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Not found"})
    ensure_resources(db, username)
    r      = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    streak = db.execute("SELECT current_streak, longest_streak FROM login_streaks WHERE username=?", (username,)).fetchone()
    db.close()
    xp_val = p["xp"] or 0
    level, xp_into, xp_needed = xp_progress(xp_val)
    gathering_bonus = get_total_gathering_bonus(level)
    next_lvl, next_data = get_next_milestone(level)
    next_unlock = None
    if next_lvl:
        nr = next_data.get("reward", {}) or {}
        next_unlock = {
            "level":        next_lvl,
            "cosmetics":    nr.get("cosmetics", []),
            "gold":         nr.get("gold", 0),
            "title":        nr.get("title"),
            "max_energy":   nr.get("max_energy", 0),
            "big_milestone": next_data.get("big_milestone", False),
        }
    try:
        title = p["title"]
    except (IndexError, KeyError):
        title = None
    return jsonify({
        "status": "success",
        "penguin": {
            "username":        p["username"],
            "level":           level,
            "xp":              xp_val,
            "xp_into":         xp_into,
            "xp_needed":       xp_needed,
            "energy":          p["energy"],
            "max_energy":      p["max_energy"] or 100,
            "gold":            r["gold"] if r else 0,
            "prestige":        p["prestige"] or 0,
            "breed":           p["breed"] or "classic_black",
            "job":             p["job"],
            "job_duration":    p["job_duration"] or 0,
            "job_started":     p["job_started"] or 0,
            "login_streak":    streak["current_streak"] if streak else 1,
            "gathering_bonus": gathering_bonus,
            "next_unlock":     next_unlock,
            "title":           title,
        },
        "resources": dict(r) if r else {},
    })


@app.route("/resources/<username>")
def get_resources(username):
    db = get_db()
    ensure_resources(db, username)
    db.commit()
    r = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    db.close()
    return jsonify(dict(r) if r else {})


@app.route("/streak/claim/<username>", methods=["POST"])
def streak_claim(username):
    today = get_today()
    db    = get_db()
    row   = db.execute("SELECT current_streak, daily_reward_claimed FROM login_streaks WHERE username=?", (username,)).fetchone()
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "No streak found."})
    if row["daily_reward_claimed"] == today:
        db.close()
        return jsonify({"status": "error", "message": "Already claimed today!"})
    reward = compute_daily_reward()
    ensure_resources(db, username)
    add_gold(db, username, reward["gold"])
    db.execute(
        f"UPDATE resources SET {reward['resource']}={reward['resource']}+? WHERE username=?",
        (reward["resource_amount"], username)
    )
    db.execute("UPDATE login_streaks SET daily_reward_claimed=? WHERE username=?", (today, username))
    log_event(db, "village",
              f"{username} claimed day {row['current_streak']} streak reward: +{reward['gold']} gold + {reward['resource_amount']} {reward['resource']} {reward['resource_icon']}",
              username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "earned": reward})


BUILDINGS_CONFIG_PATH = Path("building_config.json")

@app.route("/buildings/config")
def get_building_config():
    if BUILDINGS_CONFIG_PATH.exists():
        return jsonify(json.loads(BUILDINGS_CONFIG_PATH.read_text()))
    return jsonify({})

@app.route("/buildings/positions", methods=["POST"])
def save_building_positions():
    data = request.get_json(silent=True) or {}
    BUILDINGS_CONFIG_PATH.write_text(json.dumps(data, indent=2))
    return jsonify({"status": "success"})


@app.route("/streak/<username>")
def get_streak(username):
    db  = get_db()
    row = db.execute(
        "SELECT current_streak, longest_streak FROM login_streaks WHERE username=?", (username,)
    ).fetchone()
    db.close()
    cur = row["current_streak"] if row else 1
    week_day       = (cur % 7) or 7   # 1-7, where 7 = reward day
    days_to_reward = 7 - week_day
    return jsonify({
        "current":        cur,
        "longest":        row["longest_streak"] if row else 1,
        "week_day":       week_day,
        "days_to_reward": days_to_reward,
    })


@app.route("/leaderboard")
def leaderboard():
    db = get_db()
    rows = db.execute(
        "SELECT p.username, p.level, p.xp, p.prestige, r.gold "
        "FROM penguins p LEFT JOIN resources r ON p.username=r.username "
        "ORDER BY p.level DESC, p.xp DESC LIMIT 20"
    ).fetchall()
    db.close()
    return jsonify({"penguins": [dict(r) for r in rows]})


@app.route("/islive")
def islive():
    try:
        res  = http_requests.get(
            "https://api.twitch.tv/helix/streams?user_login=mbarepingu",
            headers={"Client-Id": TWITCH_CLIENT_ID,
                     "Authorization": f"Bearer {os.getenv('TWITCH_APP_TOKEN', '')}"}
        )
        live = len(res.json().get("data", [])) > 0
        return jsonify({"live": live})
    except Exception:
        return jsonify({"live": False})


# ── BUILDING INFO ────────────────────────────────────────────────────────────

@app.route("/building/<building_id>")
def building_info(building_id):
    username = request.args.get("username", "")
    b = BUILDINGS.get(building_id)
    if not b:
        return jsonify({"status": "error", "message": "Building not found."})
    db = get_db()
    p  = db.execute("SELECT job, job_started, job_duration, energy FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    ensure_resources(db, username)
    gold = get_gold(db, username)
    db.close()

    working_here     = p["job"] == building_id
    job_started_ts   = 0
    hours_worked     = 0.0
    preview_earnings = {}
    if working_here:
        job_started_ts = p["job_started"] or 0
        elapsed_secs   = int(time.time()) - job_started_ts
        hours_worked   = min(elapsed_secs / 3600.0, JOB_CAP_HOURS)
        for res, rate in b.get("produces", {}).items():
            preview_earnings[res] = int(rate * hours_worked)

    return jsonify({
        "status":          "success",
        "building_id":     building_id,
        "icon":            b["icon"],
        "name":            b["name"],
        "desc":            b.get("desc", ""),
        "type":            b["type"],
        "job_label":       b.get("job_label", "WORK"),
        "produces":        b.get("produces", {}),
        "rest_cost":       b.get("rest_cost", 0),
        "player_job":      p["job"],
        "player_energy":   p["energy"] or 0,
        "player_gold":     gold,
        "working_here":    working_here,
        "hours_worked":    round(hours_worked, 2),
        "job_started_ts":  job_started_ts,
        "job_cap_ts":      job_started_ts + int(JOB_CAP_HOURS * 3600) if job_started_ts else 0,
        "complete":        hours_worked >= JOB_CAP_HOURS,
        "preview_earnings":preview_earnings,
    })


# ── JOBS ─────────────────────────────────────────────────────────────────────

@app.route("/work/start", methods=["POST"])
def work_start():
    data        = request.get_json(silent=True) or {}
    username    = data.get("username", "")
    building_id = data.get("building_id", "")

    b = BUILDINGS.get(building_id)
    if not b or b.get("type") != "job":
        return jsonify({"status": "error", "message": "Not a job building."})

    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    if p["job"]:
        db.close()
        return jsonify({"status": "error", "message": "Already working! Collect first."})

    now = int(time.time())
    db.execute(
        "UPDATE penguins SET job=?, job_started=?, job_duration=0 WHERE username=?",
        (building_id, now, username)
    )
    today = get_today()
    advance_mission(db, username, "work_today", today)
    log_event(db, "job", f"{username} started {b['job_label']} at {b['name']}", username)
    db.commit()
    db.close()
    return jsonify({
        "status":      "success",
        "message":     f"Started {b['job_label']}!",
        "building_id": building_id,
        "job_cap_ts":  now + int(JOB_CAP_HOURS * 3600),
    })


@app.route("/work/collect", methods=["POST"])
def work_collect():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p or not p["job"]:
        db.close()
        return jsonify({"status": "error", "message": "Not working."})

    b = BUILDINGS.get(p["job"])
    if not b:
        db.execute("UPDATE penguins SET job=NULL, job_started=0, job_duration=0 WHERE username=?", (username,))
        db.commit()
        db.close()
        return jsonify({"status": "error", "message": "Invalid job state cleared."})

    elapsed_secs  = int(time.time()) - (p["job_started"] or 0)
    hours_worked  = min(elapsed_secs / 3600.0, JOB_CAP_HOURS)

    player_level    = p["level"] or 1
    gathering_bonus = get_total_gathering_bonus(player_level) / 100.0

    earned    = {}
    level_ups = []
    ensure_resources(db, username)

    for resource, rate_per_hour in b.get("produces", {}).items():
        if resource == "xp":
            amount = int(rate_per_hour * hours_worked)
        else:
            amount = int(rate_per_hour * (1 + gathering_bonus) * hours_worked)
        if amount <= 0:
            continue
        earned[resource] = amount
        if resource == "gold":
            add_gold(db, username, amount)
        elif resource == "xp":
            _, rewards = award_xp(db, username, amount)
            level_ups.extend(rewards)
        else:
            db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))

    db.execute("UPDATE penguins SET job=NULL, job_started=0, job_duration=0 WHERE username=?", (username,))
    today = get_today()
    advance_mission(db, username, "collect_1", today)
    advance_mission(db, username, "collect_3", today)
    new_ach = check_achievements(db, username)

    earned_parts = [f"+{v} {k}" for k, v in earned.items() if v > 0]
    log_event(db, "job",
              f"{username} collected from {b['name']}: {', '.join(earned_parts) or 'nothing yet'}",
              username)
    db.commit()
    db.close()
    return jsonify({
        "status":           "success",
        "earned":           earned,
        "hours_worked":     round(hours_worked, 2),
        "leveled_up":       bool(level_ups),
        "level_ups":        level_ups,
        "new_achievements": new_ach,
        "building":         b["name"],
    })


@app.route("/work/status")
def work_status():
    username = request.args.get("username", "")
    db = get_db()
    p  = db.execute("SELECT job, job_started FROM penguins WHERE username=?", (username,)).fetchone()
    if not p or not p["job"]:
        db.close()
        return jsonify({"working": False})
    b             = BUILDINGS.get(p["job"], {})
    job_started   = p["job_started"] or 0
    elapsed_secs  = int(time.time()) - job_started
    hours_worked  = min(elapsed_secs / 3600.0, JOB_CAP_HOURS)
    hours_remaining = max(0.0, JOB_CAP_HOURS - hours_worked)
    complete      = hours_worked >= JOB_CAP_HOURS
    preview       = {
        res: int(rate * hours_worked)
        for res, rate in b.get("produces", {}).items()
    }
    db.close()
    return jsonify({
        "working":          True,
        "building_id":      p["job"],
        "building_name":    b.get("name", p["job"]),
        "job_label":        b.get("job_label", "WORK"),
        "hours_worked":     round(hours_worked, 2),
        "hours_remaining":  round(hours_remaining, 2),
        "complete":         complete,
        "preview":          preview,
        "produces":         b.get("produces", {}),
        "job_started_ts":   job_started,
        "job_cap_ts":       job_started + int(JOB_CAP_HOURS * 3600),
    })


# ── REST ─────────────────────────────────────────────────────────────────────

@app.route("/rest", methods=["POST"])
def rest():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    db = get_db()
    p  = db.execute("SELECT energy, max_energy FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    max_e = p["max_energy"] or 100
    if (p["energy"] or 0) >= max_e:
        db.close()
        return jsonify({"status": "error", "message": "Already at full energy!"})
    cost = BUILDINGS["hotel"]["rest_cost"]
    ensure_resources(db, username)
    gold = get_gold(db, username)
    if gold < cost:
        db.close()
        return jsonify({"status": "error", "message": f"Need {cost} gold to rest."})
    add_gold(db, username, -cost)
    db.execute("UPDATE penguins SET energy=? WHERE username=?", (max_e, username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": f"Fully rested! Energy restored.", "energy": max_e})


# ── COMBAT ───────────────────────────────────────────────────────────────────

@app.route("/combat/monsters")
def combat_monsters():
    if not FEATURES.get("combat", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!", "monsters": []})
    username = request.args.get("username", "")
    today    = get_today()
    try:
        db = get_db()
        p  = db.execute("SELECT level, energy FROM penguins WHERE username=?", (username,)).fetchone()
        player_level = p["level"] if p else 1
        killed_today = {
            row["monster_id"] for row in
            db.execute("SELECT monster_id FROM monster_kills WHERE username=? AND killed_date=?", (username, today))
        }
        db.close()
        result = [
            {**m, "id": mid,
             "can_fight":    player_level >= m["min_level"],
             "killed_today": mid in killed_today}
            for mid, m in MONSTERS.items()
        ]
        return jsonify({"monsters": result, "player_level": player_level, "player_energy": p["energy"] if p else 100})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "monsters": []})


@app.route("/combat/fight", methods=["POST"])
def combat_fight():
    if not FEATURES.get("combat", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    db = None
    try:
        data       = request.get_json(silent=True) or {}
        username   = data.get("username", "")
        monster_id = data.get("monster_id", "")
        print(f"[COMBAT] fight request: username={username!r} monster_id={monster_id!r}")

        m = MONSTERS.get(monster_id)
        if not m:
            print(f"[COMBAT] unknown monster_id: {monster_id!r}")
            return jsonify({"status": "error", "message": "Unknown monster."})

        today = get_today()
        db    = get_db()
        p     = db.execute("SELECT level, energy FROM penguins WHERE username=?", (username,)).fetchone()
        print(f"[COMBAT] penguin row: {dict(p) if p else None}")
        if not p:
            return jsonify({"status": "error", "message": "Penguin not found."})
        if p["level"] < m["min_level"]:
            return jsonify({"status": "error", "message": f"Need level {m['min_level']}."})

        energy_cost = 20 + (m["tier"] - 1) * 10
        if (p["energy"] or 0) < energy_cost:
            return jsonify({"status": "error", "message": f"Need {energy_cost} energy to fight."})

        if db.execute(
            "SELECT 1 FROM monster_kills WHERE username=? AND monster_id=? AND killed_date=?",
            (username, monster_id, today)
        ).fetchone():
            return jsonify({"status": "error", "message": "Already fought this today."})

        stats = get_player_stats(db, username)
        print(f"[COMBAT] player stats: {stats}")
        won   = simulate_combat(stats, m)
        drop  = None
        new_ach = []
        ensure_resources(db, username)

        advance_mission(db, username, "fight_1", today)
        db.execute("UPDATE penguins SET energy=MAX(0,energy-?) WHERE username=?", (energy_cost, username))

        loot_summary = ""
        if won:
            for resource, amount in m["rewards"].items():
                if resource == "xp":
                    award_xp(db, username, amount)
                elif resource == "gold":
                    add_gold(db, username, amount)
                else:
                    db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
            if random.random() < m["drop_chance"]:
                drop = m["drop_name"]
            loot_summary = ", ".join(f"+{v} {k}" for k, v in m["rewards"].items())
            if drop:
                loot_summary += f" + {drop}"
            log_event(db, "combat",
                      f"{username} defeated {m['name']}! {loot_summary} 🎉",
                      username)
            advance_mission(db, username, "first_fight", today)
            new_ach = check_achievements(db, username)
        else:
            award_xp(db, username, max(2, m["rewards"].get("xp", 10) // 5))
            log_event(db, "combat", f"{username} was defeated by {m['name']}...", username)

        db.execute(
            "INSERT INTO monster_kills (username, monster_id, killed_date, loot_summary) VALUES (?,?,?,?)",
            (username, monster_id, today, loot_summary if won else "defeat")
        )
        db.commit()
        print(f"[COMBAT] done: won={won} drop={drop} loot={loot_summary!r}")
        return jsonify({
            "status":           "success",
            "won":              won,
            "drop":             drop,
            "rewards":          m["rewards"] if won else {},
            "new_achievements": new_ach,
            "energy_cost":      energy_cost,
        })
    except Exception as e:
        import traceback
        print(f"[COMBAT] ERROR: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if db:
            db.close()


# ── GEAR ─────────────────────────────────────────────────────────────────────

@app.route("/gear/inventory")
def gear_inventory():
    if not FEATURES.get("gear_equip", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!", "gear": []})
    username = request.args.get("username", "")
    db = get_db()
    ensure_resources(db, username)
    rows    = db.execute("SELECT * FROM gear WHERE username=? ORDER BY id", (username,)).fetchall()
    gold    = get_gold(db, username)
    r       = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    db.close()
    return jsonify({
        "gear":    [dict(g) for g in rows],
        "catalog": GEAR_CATALOG,
        "gold":    gold,
        "resources": dict(r) if r else {},
    })


@app.route("/gear/buy", methods=["POST"])
def gear_buy():
    if not FEATURES.get("gear_crafting", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    item_id  = data.get("item_id", "")
    defn = GEAR_CATALOG.get(item_id)
    if not defn:
        return jsonify({"status": "error", "message": "Unknown item."})

    db = get_db()
    ensure_resources(db, username)
    r = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    if not r:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    # Check affordability
    for resource, amount in defn["cost"].items():
        have = r["gold"] if resource == "gold" else (r[resource] if resource in r.keys() else 0)
        if have < amount:
            db.close()
            return jsonify({"status": "error", "message": f"Need {amount} {resource}."})

    # Deduct
    for resource, amount in defn["cost"].items():
        if resource == "gold":
            add_gold(db, username, -amount)
        else:
            db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))

    db.execute(
        "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, attack_bonus, defense_bonus, speed_bonus, hp_bonus, obtained_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (username, item_id, defn["name"], defn.get("set_name"), defn["type"], defn["slot"],
         defn.get("rarity","common"), defn["attack_bonus"], defn["defense_bonus"],
         defn["speed_bonus"], defn["hp_bonus"], int(time.time()))
    )
    new_ach = check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": f"{defn['name']} purchased!", "new_achievements": new_ach})


@app.route("/gear/equip", methods=["POST"])
def gear_equip():
    if not FEATURES.get("gear_equip", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    gear_id  = int(data.get("gear_id", 0))
    db = get_db()
    item = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    if item["equipped"]:
        db.execute("UPDATE gear SET equipped=0 WHERE id=?", (gear_id,))
        db.commit()
        db.close()
        return jsonify({"status": "success", "equipped": False, "message": f"{item['name']} unequipped."})
    db.execute("UPDATE gear SET equipped=0 WHERE username=? AND slot=?", (username, item["slot"]))
    db.execute("UPDATE gear SET equipped=1 WHERE id=?", (gear_id,))
    new_ach = check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "equipped": True, "message": f"{item['name']} equipped.", "new_achievements": new_ach})


# ── MISSIONS ─────────────────────────────────────────────────────────────────

@app.route("/missions/<username>")
def get_missions(username):
    today = get_today()
    db    = get_db()
    for key in DAILY_MISSIONS:
        db.execute(
            "INSERT OR IGNORE INTO daily_missions (username, mission_key, date) VALUES (?,?,?)",
            (username, key, today)
        )
    db.commit()
    rows = db.execute(
        "SELECT mission_key, progress, completed FROM daily_missions WHERE username=? AND date=?",
        (username, today)
    ).fetchall()
    db.close()
    key_order = {k: i for i, k in enumerate(DAILY_MISSIONS)}
    missions  = sorted([
        {
            "key":       r["mission_key"],
            "title":     MISSION_DEFS[r["mission_key"]]["title"],
            "desc":      MISSION_DEFS[r["mission_key"]]["desc"],
            "gold":      MISSION_DEFS[r["mission_key"]]["gold"],
            "target":    MISSION_DEFS[r["mission_key"]]["target"],
            "stream":    MISSION_DEFS[r["mission_key"]]["stream"],
            "icon":      MISSION_DEFS[r["mission_key"]]["icon"],
            "progress":  r["progress"],
            "completed": bool(r["completed"]),
        }
        for r in rows if r["mission_key"] in MISSION_DEFS
    ], key=lambda m: key_order.get(m["key"], 99))
    return jsonify({"missions": missions, "date": today})


@app.route("/missions/<username>/claim/<key>", methods=["POST"])
def claim_stream_mission(username, key):
    defn = MISSION_DEFS.get(key)
    if not defn or not defn.get("stream"):
        return jsonify({"status": "error", "message": "Not a claimable stream mission."})
    today = get_today()
    db    = get_db()
    done  = advance_mission(db, username, key, today)
    db.commit()
    db.close()
    if done:
        return jsonify({"status": "success", "message": f"Mission complete! +{defn['gold']} gold", "gold": defn["gold"]})
    return jsonify({"status": "error", "message": "Already completed or not available."})


# ── ACHIEVEMENTS ─────────────────────────────────────────────────────────────

@app.route("/achievements/<username>")
def get_achievements(username):
    db  = get_db()
    ensure_resources(db, username)
    check_achievements(db, username)
    db.commit()
    rows    = db.execute("SELECT achievement_id, unlocked_at FROM achievements WHERE username=?", (username,)).fetchall()
    db.close()
    unlocked = {r["achievement_id"]: r["unlocked_at"] for r in rows}
    result   = [
        {**defn, "id": aid, "unlocked": aid in unlocked, "unlocked_at": unlocked.get(aid)}
        for aid, defn in ACHIEVEMENT_DEFS.items()
    ]
    return jsonify({"achievements": result})


# ── EVENT LOG ─────────────────────────────────────────────────────────────────

@app.route("/events")
def get_events():
    cutoff = int(time.time()) - 86400  # last 24 hours
    db     = get_db()
    rows   = db.execute(
        "SELECT * FROM event_log WHERE created_at > ? ORDER BY created_at DESC LIMIT 100",
        (cutoff,)
    ).fetchall()
    db.close()
    return jsonify({"events": [dict(r) for r in rows]})


# ── IGLOO ─────────────────────────────────────────────────────────────────────

@app.route("/igloo/<username>")
def get_igloo(username):
    db    = get_db()
    items = db.execute("SELECT id, item_key, x, y FROM igloo_items WHERE username=? ORDER BY id", (username,)).fetchall()
    ensure_resources(db, username)
    gold = get_gold(db, username)
    db.close()
    return jsonify({"items": [dict(r) for r in items], "coins": gold, "catalog": FURNITURE_CATALOG})


@app.route("/igloo/<username>/place", methods=["POST"])
def igloo_place(username):
    data     = request.get_json(silent=True) or {}
    item_key = data.get("item_key")
    x        = int(data.get("x", -1))
    y        = int(data.get("y", -1))
    if item_key not in FURNITURE_CATALOG:
        return jsonify({"status": "error", "message": "Unknown item."})
    if not (0 <= x < IGLOO_COLS and 0 <= y < IGLOO_ROWS):
        return jsonify({"status": "error", "message": "Out of bounds."})
    cost = FURNITURE_CATALOG[item_key]["cost"]
    db   = get_db()
    ensure_resources(db, username)
    gold = get_gold(db, username)
    if gold < cost:
        db.close()
        return jsonify({"status": "error", "message": f"Need {cost}G!"})
    if db.execute("SELECT id FROM igloo_items WHERE username=? AND x=? AND y=?", (username, x, y)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": "That spot is taken!"})
    add_gold(db, username, -cost)
    cur    = db.execute("INSERT INTO igloo_items (username, item_key, x, y) VALUES (?,?,?,?)", (username, item_key, x, y))
    new_id = cur.lastrowid
    new_gold = get_gold(db, username)
    check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "item": {"id": new_id, "item_key": item_key, "x": x, "y": y}, "coins": new_gold})


@app.route("/igloo/<username>/move/<int:item_id>", methods=["POST"])
def igloo_move(username, item_id):
    data = request.get_json(silent=True) or {}
    x    = int(data.get("x", -1))
    y    = int(data.get("y", -1))
    if not (0 <= x < IGLOO_COLS and 0 <= y < IGLOO_ROWS):
        return jsonify({"status": "error", "message": "Out of bounds."})
    db   = get_db()
    item = db.execute("SELECT id FROM igloo_items WHERE id=? AND username=?", (item_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    if db.execute("SELECT id FROM igloo_items WHERE username=? AND x=? AND y=? AND id!=?", (username, x, y, item_id)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": "That spot is taken!"})
    db.execute("UPDATE igloo_items SET x=?, y=? WHERE id=?", (x, y, item_id))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/igloo/<username>/remove/<int:item_id>", methods=["POST"])
def igloo_remove(username, item_id):
    db   = get_db()
    item = db.execute("SELECT item_key FROM igloo_items WHERE id=? AND username=?", (item_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    refund = FURNITURE_CATALOG.get(item["item_key"], {}).get("cost", 0) // 2
    db.execute("DELETE FROM igloo_items WHERE id=?", (item_id,))
    ensure_resources(db, username)
    add_gold(db, username, refund)
    new_gold = get_gold(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "refund": refund, "coins": new_gold})


# ── WELCOME BACK / OFFLINE PROGRESS ──────────────────────────────────────────

RESOURCE_ICONS = {
    "fish":            "🐟",
    "herbs":           "🌿",
    "blood_gems":      "💎",
    "bones":           "🦴",
    "spell_fragments": "✨",
    "gold":            "🪙",
    "xp":              "⭐",
}

@app.route("/welcome-back/<username>")
def welcome_back(username):
    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"show": False})

    now         = int(time.time())
    last_active = p["last_active"] or 0

    # Brand-new account — just set last_active, no popup
    if last_active == 0:
        db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
        db.commit()
        db.close()
        return jsonify({"show": False})

    hours_away = min((now - last_active) / 3600.0, 12.0)

    # Under 30 minutes — refresh silently
    if hours_away < 0.5:
        db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
        db.commit()
        db.close()
        return jsonify({"show": False})

    ensure_resources(db, username)
    job_earnings = None

    # Auto-collect any active job
    if p["job"]:
        b = BUILDINGS.get(p["job"])
        if b and b.get("type") == "job":
            job_started  = p["job_started"] or 0
            elapsed_secs = now - job_started
            hours_worked = min(elapsed_secs / 3600.0, JOB_CAP_HOURS)
            wb_bonus = get_total_gathering_bonus(p["level"] or 1) / 100.0
            earned   = {}
            leveled  = False
            for resource, rate in b.get("produces", {}).items():
                if resource == "xp":
                    amount = int(rate * hours_worked)
                else:
                    amount = int(rate * (1 + wb_bonus) * hours_worked)
                if amount <= 0:
                    continue
                earned[resource] = amount
                if resource == "gold":
                    add_gold(db, username, amount)
                elif resource == "xp":
                    lv, _ = award_xp(db, username, amount)
                    if lv:
                        leveled = True
                else:
                    db.execute(
                        f"UPDATE resources SET {resource}={resource}+? WHERE username=?",
                        (amount, username)
                    )
            db.execute(
                "UPDATE penguins SET job=NULL, job_started=0, job_duration=0 WHERE username=?",
                (username,)
            )
            today = get_today()
            advance_mission(db, username, "collect_1", today)
            advance_mission(db, username, "collect_3", today)
            parts = [f"+{v} {k}" for k, v in earned.items() if v > 0]
            log_event(db, "job",
                      f"{username} (offline) collected from {b['name']}: {', '.join(parts) or 'nothing'}",
                      username)
            job_earnings = {
                "building_name": b["name"],
                "building_icon": b.get("icon", "🏢"),
                "earned":        earned,
                "hours_worked":  round(hours_worked, 2),
                "leveled_up":    leveled,
            }

    # Passive offline earnings
    passive_gold = int(hours_away * 0.8)
    passive_xp   = int(hours_away * 1.5)
    leveled_passive = False
    if passive_gold > 0:
        add_gold(db, username, passive_gold)
    if passive_xp > 0:
        lv, _ = award_xp(db, username, passive_xp)
        if lv:
            leveled_passive = True

    log_event(db, "village",
              f"{username} returned after {round(hours_away, 1)}h — {passive_gold} gold + {passive_xp} XP offline",
              username)
    db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
    db.commit()
    db.close()

    return jsonify({
        "show":             True,
        "hours_away":       round(hours_away, 1),
        "job_earnings":     job_earnings,
        "passive_earnings": {
            "gold":       passive_gold,
            "xp":         passive_xp,
            "leveled_up": leveled_passive,
        },
    })


# ── ACTIVE PING ───────────────────────────────────────────────────────────────

@app.route("/active/<username>")
def active(username):
    db = get_db()
    p  = db.execute("SELECT energy, max_energy, last_active FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "skip"})
    now     = int(time.time())
    max_e   = p["max_energy"] or 100
    if p["last_active"] and p["last_active"] > 0:
        mins_away  = (now - p["last_active"]) // 60
        recovered  = mins_away * 2
        new_energy = min(max_e, (p["energy"] or 0) + recovered)
    else:
        new_energy = p["energy"] or max_e
    db.execute("UPDATE penguins SET last_active=?, energy=? WHERE username=?", (now, new_energy, username))
    db.commit()
    db.close()
    return jsonify({"status": "ok", "energy": new_energy})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
