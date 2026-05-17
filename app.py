from dotenv import load_dotenv
import os
import datetime
import random
from flask import Flask, jsonify, redirect, request, session, url_for, render_template
from database import init_db, get_db
from feature_flags import FEATURES
from level_config import LEVEL_DATA, get_total_gathering_bonus, get_next_milestone, COSMETIC_SLOTS
import time
import requests as http_requests

load_dotenv()

TWITCH_CLIENT_ID    = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
SECRET_KEY          = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── JOB TITLES ───────────────────────────────────────────────────────────────
JOB_TITLES = {
    "fishing": [
        {"hours": 5,   "title": "Apprentice Fisher"},
        {"hours": 20,  "title": "Fisher of the Northern Bay"},
        {"hours": 50,  "title": "Sea Lion Whisperer"},
        {"hours": 100, "title": "Master Fisher"},
        {"hours": 200, "title": "Admiral of the Frozen Seas"},
    ],
    "herbalism": [
        {"hours": 5,   "title": "Herb Picker"},
        {"hours": 20,  "title": "Club Soda Botanist"},
        {"hours": 50,  "title": "Potion Apprentice"},
        {"hours": 100, "title": "Master Herbalist"},
        {"hours": 200, "title": "Keeper of the Green"},
    ],
    "circus": [
        {"hours": 5,   "title": "Juggling Novice"},
        {"hours": 20,  "title": "Crowd Pleaser"},
        {"hours": 50,  "title": "Star Performer"},
        {"hours": 100, "title": "Ringmaster"},
        {"hours": 200, "title": "Legend of the Parkmusement"},
    ],
    "monk": [
        {"hours": 5,   "title": "Temple Initiate"},
        {"hours": 20,  "title": "Cursed Acolyte"},
        {"hours": 50,  "title": "Spell Weaver"},
        {"hours": 100, "title": "High Priest"},
        {"hours": 200, "title": "Enlightened One"},
    ],
    "executioner": [
        {"hours": 5,   "title": "Blood Apprentice"},
        {"hours": 20,  "title": "Bone Collector"},
        {"hours": 50,  "title": "Gil's Right Hand"},
        {"hours": 100, "title": "Master Executioner"},
        {"hours": 200, "title": "The Guillotine's Shadow"},
    ],
}

JOB_HOUR_COL = {
    "sea_lion_pit":   ("fishing",     "fishing_hours"),
    "club_soda":      ("herbalism",   "herbalism_hours"),
    "parkmusement":   ("circus",      "circus_hours"),
    "cursed_temple":  ("monk",        "monk_hours"),
    "guillotine":     ("executioner", "executioner_hours"),
}

LEVEL_TITLES = {3:"Newcomer", 7:"Settler", 10:"Villager", 14:"Explorer",
                19:"Pathfinder", 20:"Veteran", 24:"Sage", 29:"Elder", 30:"Legend"}


def get_earned_job_title(category, hours):
    """Return highest unlocked title string for a category given hours."""
    earned = None
    for tier in JOB_TITLES.get(category, []):
        if hours >= tier["hours"]:
            earned = tier["title"]
    return earned


def get_all_earned_titles(db, username):
    """Return a list of dicts for all titles the player has earned."""
    p = db.execute(
        "SELECT level, fishing_hours, herbalism_hours, circus_hours, monk_hours, "
        "executioner_hours, ceremonial_titles FROM penguins WHERE username=?",
        (username,)
    ).fetchone()
    if not p:
        return []
    titles = []
    level = p["level"] or 1
    for lvl, name in LEVEL_TITLES.items():
        if level >= lvl:
            titles.append({"title": name, "source": f"Level {lvl} Milestone", "category": "level"})
    hour_cols = [
        ("fishing",     p["fishing_hours"]     or 0),
        ("herbalism",   p["herbalism_hours"]   or 0),
        ("circus",      p["circus_hours"]      or 0),
        ("monk",        p["monk_hours"]        or 0),
        ("executioner", p["executioner_hours"] or 0),
    ]
    for cat, hrs in hour_cols:
        for tier in JOB_TITLES.get(cat, []):
            if hrs >= tier["hours"]:
                titles.append({
                    "title": tier["title"],
                    "source": f"{cat.capitalize()} — {tier['hours']} hours",
                    "category": cat,
                })
    try:
        cer = json.loads(p["ceremonial_titles"] or "[]")
        for t in cer:
            titles.append({"title": t, "source": "Granted by Mayor", "category": "ceremonial"})
    except Exception:
        pass
    return titles


# ── STREAM MULTIPLIERS ────────────────────────────────────────────────────────
# Tier 0 = offline, 1 = stream live, 2 = present in chat, 3 = has chatted
STREAM_RATES      = {0: 1.0, 1: 1.25, 2: 1.50, 3: 1.75}
_stream_was_live  = None  # tracks previous live state to detect transitions

# ── VILLAGE BUILDING UPGRADES ────────────────────────────────────────────────
BUILDING_UPGRADES = {
    "sea_lion_pit": {
        "name": "Ash's Sea Lion Pit",
        "levels": {
            2: {"fish": 500,   "gold": 200,  "benefit": "+10% fish rate for everyone"},
            3: {"fish": 1500,  "gold": 600,  "benefit": "+25% fish rate for everyone"},
            4: {"fish": 4000,  "gold": 1500, "benefit": "+50% fish rate for everyone"},
            5: {"fish": 10000, "gold": 4000, "benefit": "+100% fish rate for everyone, unlocks rare fish events"},
        },
    },
    "club_soda": {
        "name": "Club Soda",
        "levels": {
            2: {"herbs": 500,   "gold": 200,  "benefit": "+10% herb rate for everyone"},
            3: {"herbs": 1500,  "gold": 600,  "benefit": "+25% herb rate for everyone"},
            4: {"herbs": 4000,  "gold": 1500, "benefit": "+50% herb rate for everyone"},
            5: {"herbs": 10000, "gold": 4000, "benefit": "+100% herb rate for everyone, unlocks potion crafting"},
        },
    },
    "parkmusement": {
        "name": "Ash's Parkmusement",
        "levels": {
            2: {"gold": 500,   "benefit": "+10% gold rate for everyone"},
            3: {"gold": 1500,  "benefit": "+25% gold rate for everyone"},
            4: {"gold": 4000,  "benefit": "+50% gold rate for everyone"},
            5: {"gold": 10000, "benefit": "+100% gold rate for everyone, unlocks special performances"},
        },
    },
    "cursed_temple": {
        "name": "Cursed Temple",
        "levels": {
            2: {"spell_fragments": 300,  "gold": 300,  "benefit": "+10% XP rate for everyone"},
            3: {"spell_fragments": 800,  "gold": 800,  "benefit": "+25% XP rate for everyone"},
            4: {"spell_fragments": 2000, "gold": 2000, "benefit": "+50% XP rate for everyone"},
            5: {"spell_fragments": 5000, "gold": 5000, "benefit": "+100% XP rate for everyone, unlocks advanced spells"},
        },
    },
    "guillotine": {
        "name": "Gil the Guillotine",
        "levels": {
            2: {"blood_gems": 200,  "bones": 200,  "gold": 200,  "benefit": "+10% blood gem and bone rate for everyone"},
            3: {"blood_gems": 600,  "bones": 600,  "gold": 600,  "benefit": "+25% rate for everyone"},
            4: {"blood_gems": 1500, "bones": 1500, "gold": 1500, "benefit": "+50% rate for everyone"},
            5: {"blood_gems": 4000, "bones": 4000, "gold": 4000, "benefit": "+100% rate for everyone, unlocks dark rituals"},
        },
    },
    "hotel": {
        "name": "Penguin Hotel",
        "levels": {
            2: {"gold": 500,   "fish": 200,  "benefit": "Rest costs reduced by 20%"},
            3: {"gold": 1500,  "fish": 600,  "benefit": "Rest costs reduced by 40%"},
            4: {"gold": 4000,  "fish": 1500, "benefit": "Rest costs reduced by 60%"},
            5: {"gold": 10000, "fish": 4000, "benefit": "Rest is FREE for everyone"},
        },
    },
}

BUILDING_BONUS_RATES = {1: 0.0, 2: 0.10, 3: 0.25, 4: 0.50, 5: 1.00}

# resource column name in building_upgrades table
_RES_COL = {
    "fish": "fish_donated", "herbs": "herbs_donated", "gold": "gold_donated",
    "blood_gems": "blood_gems_donated", "bones": "bones_donated",
    "spell_fragments": "spell_fragments_donated",
}


def get_building_level(db, building_id):
    row = db.execute(
        "SELECT current_level FROM building_upgrades WHERE building_id=?", (building_id,)
    ).fetchone()
    return row["current_level"] if row else 1


def ensure_building_row(db, building_id):
    db.execute(
        "INSERT OR IGNORE INTO building_upgrades (building_id) VALUES (?)", (building_id,)
    )


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

# ── SEAL SHOP ─────────────────────────────────────────────────────────────────
SEAL_SHOP = [
    {"id": "royal_crown",         "name": "Royal Crown",          "cost": 50,  "slot": "hat",         "description": "A crown fit for stream royalty."},
    {"id": "stream_cape",         "name": "Streamer's Cape",       "cost": 80,  "slot": "back",        "description": "Flows with the energy of live content."},
    {"id": "neon_scarf",          "name": "Neon Scarf",            "cost": 30,  "slot": "accessory",   "description": "Glows in the dark. Like your dedication."},
    {"id": "aurora_boots",        "name": "Aurora Sliders",        "cost": 40,  "slot": "footwear",    "description": "Leave sparkly trails. Fancy."},
    {"id": "penguin_pet",         "name": "Mini Penguin Pet",      "cost": 100, "slot": "accessory",   "description": "A tiny penguin follows you around. Adorable."},
    {"id": "golden_frame",        "name": "Golden Card Frame",     "cost": 60,  "slot": "card_frame",  "description": "Makes your Penguin Card shine."},
    {"id": "animated_sparkle",    "name": "Sparkle Effect",        "cost": 120, "slot": "card_effect", "description": "Animated sparkles on your Penguin Card."},
    {"id": "mayor_council_badge", "name": "Mayor's Council Badge", "cost": 150, "slot": "accessory",   "description": "You have the Mayor's ear. Use it wisely."},
]

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
        item_id     = cosmetic.lower().replace(" ", "_").replace("'", "")
        cosm_slot   = COSMETIC_SLOTS.get(cosmetic, "accessory")
        try:
            db.execute(
                "INSERT INTO gear (username, item_id, name, type, slot, rarity, obtained_at) "
                "VALUES (?,?,?,'cosmetic',?,'milestone',?)",
                (username, item_id, cosmetic, cosm_slot, now)
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
# Seed building_upgrades rows for each upgradeable building
_seed_db = get_db()
for _bid in BUILDING_UPGRADES:
    _seed_db.execute("INSERT OR IGNORE INTO building_upgrades (building_id) VALUES (?)", (_bid,))
_seed_db.commit()
_seed_db.close()


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
            "mayor_seals":     (r["mayor_seals"] if r and r["mayor_seals"] is not None else 0),
            "stream_tier":     (p["stream_tier"] if p["stream_tier"] is not None else 0),
            "active_title":    (p["active_title"] if p["active_title"] is not None else None),
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
        "SELECT p.username, p.level, p.xp, p.prestige, p.job, p.active_title, r.gold "
        "FROM penguins p LEFT JOIN resources r ON p.username=r.username "
        "ORDER BY p.level DESC, p.xp DESC LIMIT 20"
    ).fetchall()
    db.close()
    return jsonify({"penguins": [dict(r) for r in rows]})


@app.route("/islive")
def islive():
    global _stream_was_live
    try:
        res  = http_requests.get(
            "https://api.twitch.tv/helix/streams?user_login=mbarepingu",
            headers={"Client-Id": TWITCH_CLIENT_ID,
                     "Authorization": f"Bearer {os.getenv('TWITCH_APP_TOKEN', '')}"}
        )
        live = len(res.json().get("data", [])) > 0
    except Exception:
        live = False

    db = get_db()
    if live and _stream_was_live is False:
        # Stream just came online — bump all players to at least tier 1
        db.execute("UPDATE penguins SET stream_tier=1 WHERE stream_tier=0")
    elif not live and _stream_was_live is True:
        # Stream just ended — reset all tiers
        db.execute("UPDATE penguins SET stream_tier=0, last_chatted=0")
    _stream_was_live = live
    db.commit()
    db.close()
    return jsonify({"live": live})


def _stream_is_live():
    try:
        res = http_requests.get(
            "https://api.twitch.tv/helix/streams?user_login=mbarepingu",
            headers={"Client-Id": TWITCH_CLIENT_ID,
                     "Authorization": f"Bearer {os.getenv('TWITCH_APP_TOKEN', '')}"},
            timeout=3
        )
        return len(res.json().get("data", [])) > 0
    except Exception:
        return False


# ── MAYOR'S SEALS ─────────────────────────────────────────────────────────────

@app.route("/seals/award", methods=["POST"])
def seals_award():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"status": "error", "message": "username required"})
    if not _stream_is_live():
        return jsonify({"status": "skip", "reason": "stream offline"})
    db = get_db()
    p  = db.execute("SELECT id FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "skip"})
    ensure_resources(db, username)
    db.execute("UPDATE resources SET mayor_seals=mayor_seals+1 WHERE username=?", (username,))
    db.commit()
    row = db.execute("SELECT mayor_seals FROM resources WHERE username=?", (username,)).fetchone()
    total = row["mayor_seals"] if row else 1
    db.close()
    return jsonify({"status": "success", "seals_awarded": 1, "total_seals": total})


@app.route("/seals/shop")
def seals_shop():
    return jsonify({"items": SEAL_SHOP})


@app.route("/seals/buy", methods=["POST"])
def seals_buy():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    item_id  = data.get("item_id", "").strip()
    shop_item = next((i for i in SEAL_SHOP if i["id"] == item_id), None)
    if not shop_item:
        return jsonify({"status": "error", "message": "Item not found."})
    db = get_db()
    p  = db.execute("SELECT id FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    ensure_resources(db, username)
    r = db.execute("SELECT mayor_seals FROM resources WHERE username=?", (username,)).fetchone()
    seals = r["mayor_seals"] if r else 0
    if seals < shop_item["cost"]:
        db.close()
        return jsonify({"status": "error", "message": f"Not enough Mayor's Seals. Need {shop_item['cost']}, have {seals}."})
    already = db.execute(
        "SELECT id FROM gear WHERE username=? AND item_id=?", (username, item_id)
    ).fetchone()
    if already:
        db.close()
        return jsonify({"status": "error", "message": "You already own this item."})
    db.execute("UPDATE resources SET mayor_seals=mayor_seals-? WHERE username=?", (shop_item["cost"], username))
    db.execute(
        "INSERT INTO gear (username, item_id, name, type, slot, rarity, obtained_at) VALUES (?,?,?,?,?,?,?)",
        (username, item_id, shop_item["name"], "cosmetic", shop_item["slot"], "exclusive", int(time.time()))
    )
    log_event(db, "seal_shop", f"{username} purchased {shop_item['name']} from the Seal Shop!", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "item": shop_item})


# ── STREAM PRESENCE ──────────────────────────────────────────────────────────

@app.route("/stream/presence", methods=["POST"])
def stream_presence():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"status": "skip"})
    db = get_db()
    p  = db.execute("SELECT id, stream_tier FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "skip"})
    if (p["stream_tier"] or 0) < 2:
        db.execute("UPDATE penguins SET stream_tier=2 WHERE username=?", (username,))
        db.commit()
    db.close()
    return jsonify({"status": "ok"})


@app.route("/stream/chatted", methods=["POST"])
def stream_chatted():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"status": "skip"})
    db = get_db()
    p  = db.execute("SELECT id FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "skip"})
    db.execute("UPDATE penguins SET stream_tier=3, last_chatted=? WHERE username=?", (int(time.time()), username))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


# ── BUILDING INFO ────────────────────────────────────────────────────────────

@app.route("/building/<building_id>")
def building_info(building_id):
    username = request.args.get("username", "")
    b = BUILDINGS.get(building_id)
    if not b:
        return jsonify({"status": "error", "message": "Building not found."})
    db = get_db()
    p  = db.execute("SELECT job, job_started, job_duration, energy, max_energy FROM penguins WHERE username=?", (username,)).fetchone()
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
        "rest_cost":        b.get("rest_cost", 0),
        "player_job":       p["job"],
        "player_energy":    p["energy"] or 0,
        "player_max_energy": p["max_energy"] or 100,
        "player_gold":      gold,
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
    stream_mult     = STREAM_RATES.get(p["stream_tier"] or 0, 1.0)
    ensure_building_row(db, p["job"])
    building_bonus  = BUILDING_BONUS_RATES.get(get_building_level(db, p["job"]), 0.0)

    earned    = {}
    level_ups = []
    ensure_resources(db, username)

    for resource, rate_per_hour in b.get("produces", {}).items():
        if resource == "xp":
            amount = int(rate_per_hour * stream_mult * (1 + building_bonus) * hours_worked)
        else:
            amount = int(rate_per_hour * stream_mult * (1 + gathering_bonus + building_bonus) * hours_worked)
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

    # Track job hours and check for new titles
    new_title = None
    if p["job"] in JOB_HOUR_COL:
        cat, col = JOB_HOUR_COL[p["job"]]
        old_hours = p[col] or 0
        new_hours = old_hours + hours_worked
        db.execute(f"UPDATE penguins SET {col}=? WHERE username=?", (new_hours, username))
        old_earned = get_earned_job_title(cat, old_hours)
        new_earned  = get_earned_job_title(cat, new_hours)
        if new_earned and new_earned != old_earned:
            new_title = new_earned
            log_event(db, "title", f"{username} earned the title: {new_earned}!", username)

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
        "stream_tier":      p["stream_tier"] or 0,
        "stream_mult":      stream_mult,
        "building_bonus":   building_bonus,
        "new_title":        new_title,
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

@app.route("/hotel/rest/<username>", methods=["POST"])
def hotel_rest(username):
    db = get_db()
    p  = db.execute("SELECT energy, max_energy, job FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    max_e  = p["max_energy"] or 100
    energy = p["energy"] or 0
    if energy >= max_e:
        db.close()
        return jsonify({"status": "error", "message": "Your penguin is already fully rested!"})
    if p["job"]:
        db.close()
        return jsonify({"status": "error", "message": "Your penguin needs to finish working first! Collect your job earnings before resting."})
    to_restore = max_e - energy
    cost = to_restore * 2
    ensure_resources(db, username)
    gold = get_gold(db, username)
    if gold < cost:
        db.close()
        return jsonify({"status": "error", "message": f"Not enough gold! Need {cost} gold ({to_restore} energy × 2).", "need": cost, "have": gold})
    add_gold(db, username, -cost)
    db.execute("UPDATE penguins SET energy=? WHERE username=?", (max_e, username))
    log_event(db, "village", f"{username} rested at the Penguin Hotel (+{to_restore} energy for {cost} gold)", username)
    db.commit()
    db.close()
    return jsonify({
        "status":          "success",
        "message":         "Fully rested!",
        "energy_restored": to_restore,
        "gold_spent":      cost,
        "new_energy":      max_e,
    })


# ── COSMETICS ────────────────────────────────────────────────────────────────

@app.route("/gear/cosmetics/<username>")
def gear_cosmetics(username):
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM gear WHERE username=? AND type='cosmetic' ORDER BY obtained_at",
        (username,)
    ).fetchall()
    db.close()
    return jsonify({"cosmetics": [dict(g) for g in rows]})


@app.route("/gear/cosmetics/equip", methods=["POST"])
def gear_cosmetics_equip():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    gear_id  = data.get("gear_id")
    action   = data.get("action", "equip")
    db = get_db()
    item = db.execute(
        "SELECT * FROM gear WHERE id=? AND username=? AND type='cosmetic'",
        (gear_id, username)
    ).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    if action == "unequip":
        db.execute("UPDATE gear SET equipped=0 WHERE id=?", (gear_id,))
    else:
        db.execute(
            "UPDATE gear SET equipped=0 WHERE username=? AND type='cosmetic' AND slot=?",
            (username, item["slot"])
        )
        db.execute("UPDATE gear SET equipped=1 WHERE id=?", (gear_id,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


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


# ── TITLES ────────────────────────────────────────────────────────────────────

@app.route("/titles/<username>")
def titles_list(username):
    db = get_db()
    p  = db.execute(
        "SELECT level, active_title, fishing_hours, herbalism_hours, circus_hours, "
        "monk_hours, executioner_hours FROM penguins WHERE username=?", (username,)
    ).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Not found."})
    earned = get_all_earned_titles(db, username)
    db.close()

    level = p["level"] or 1
    # Progress toward next title in each category
    progress = {}
    hour_map = {
        "fishing":     p["fishing_hours"]     or 0,
        "herbalism":   p["herbalism_hours"]   or 0,
        "circus":      p["circus_hours"]      or 0,
        "monk":        p["monk_hours"]        or 0,
        "executioner": p["executioner_hours"] or 0,
    }
    for cat, hrs in hour_map.items():
        tiers  = JOB_TITLES.get(cat, [])
        earned_t = get_earned_job_title(cat, hrs)
        next_t   = next((t for t in tiers if hrs < t["hours"]), None)
        progress[cat] = {
            "current_hours": round(hrs, 2),
            "current_title": earned_t,
            "next_title":    next_t["title"] if next_t else None,
            "hours_needed":  next_t["hours"] if next_t else None,
            "progress_pct":  min(100, round((hrs / next_t["hours"]) * 100)) if next_t else 100,
        }

    return jsonify({
        "status":       "success",
        "active_title": p["active_title"],
        "earned":       earned,
        "progress":     progress,
    })


@app.route("/titles/equip", methods=["POST"])
def titles_equip():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    title    = data.get("title", "").strip()
    db = get_db()
    earned = [t["title"] for t in get_all_earned_titles(db, username)]
    if title not in earned:
        db.close()
        return jsonify({"status": "error", "message": "Title not earned."})
    db.execute("UPDATE penguins SET active_title=? WHERE username=?", (title, username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "active_title": title})


@app.route("/titles/unequip", methods=["POST"])
def titles_unequip():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    db = get_db()
    db.execute("UPDATE penguins SET active_title=NULL WHERE username=?", (username,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/titles/grant", methods=["POST"])
def titles_grant():
    # Localhost-only or secret-key protected
    secret = os.getenv("ADMIN_SECRET", "")
    provided = request.headers.get("X-Admin-Secret", "") or (request.get_json(silent=True) or {}).get("secret", "")
    remote   = request.remote_addr
    if remote not in ("127.0.0.1", "::1") and (not secret or provided != secret):
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    title    = data.get("title", "").strip()
    if not username or not title:
        return jsonify({"status": "error", "message": "username and title required."})
    db = get_db()
    p  = db.execute("SELECT id, ceremonial_titles FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    try:
        existing = json.loads(p["ceremonial_titles"] or "[]")
    except Exception:
        existing = []
    if title not in existing:
        existing.append(title)
        db.execute("UPDATE penguins SET ceremonial_titles=? WHERE username=?",
                   (json.dumps(existing), username))
    log_event(db, "title", f"The Mayor granted {username} the title: {title}!", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "title": title, "username": username})


# ── VILLAGE BUILDING UPGRADE ENDPOINTS ───────────────────────────────────────

def _building_upgrade_info(db, building_id):
    """Return full upgrade state for a building (dict, or None if unknown)."""
    cfg = BUILDING_UPGRADES.get(building_id)
    if not cfg:
        return None
    ensure_building_row(db, building_id)
    row = db.execute(
        "SELECT * FROM building_upgrades WHERE building_id=?", (building_id,)
    ).fetchone()
    current_level = row["current_level"] if row else 1
    max_level     = row["max_level"]     if row else 5
    levels_cfg    = cfg["levels"]
    next_level    = current_level + 1 if current_level < max_level else None
    next_req      = levels_cfg.get(next_level, {}) if next_level else {}
    donated       = {
        "fish":            row["fish_donated"]            if row else 0,
        "herbs":           row["herbs_donated"]           if row else 0,
        "gold":            row["gold_donated"]            if row else 0,
        "blood_gems":      row["blood_gems_donated"]      if row else 0,
        "bones":           row["bones_donated"]           if row else 0,
        "spell_fragments": row["spell_fragments_donated"] if row else 0,
    }
    progress = {}
    for res, need in next_req.items():
        if res == "benefit":
            continue
        have = donated.get(res, 0)
        progress[res] = {
            "needed": need, "donated": have,
            "pct": min(100, round(have / need * 100)) if need else 100,
        }
    # current benefit
    cur_benefit  = levels_cfg.get(current_level, {}).get("benefit", "Base level") if current_level > 1 else "Base level"
    next_benefit = next_req.get("benefit") if next_req else None
    return {
        "building_id":    building_id,
        "name":           cfg["name"],
        "current_level":  current_level,
        "max_level":      max_level,
        "current_benefit": cur_benefit,
        "next_level":     next_level,
        "next_req":       {k: v for k, v in next_req.items() if k != "benefit"},
        "next_benefit":   next_benefit,
        "progress":       progress,
    }


@app.route("/building/upgrade/<building_id>")
def building_upgrade_info(building_id):
    username = request.args.get("username", "")
    db       = get_db()
    info     = _building_upgrade_info(db, building_id)
    if not info:
        db.close()
        return jsonify({"status": "error", "message": "Not upgradeable."})
    # Top contributors
    rows = db.execute(
        "SELECT username, SUM(amount) AS total FROM building_donations "
        "WHERE building_id=? GROUP BY username ORDER BY total DESC LIMIT 5",
        (building_id,)
    ).fetchall()
    contributors = [{"rank": i+1, "username": r["username"], "total": r["total"]}
                    for i, r in enumerate(rows)]
    # Player resources for donation UI
    player_resources = {}
    if username:
        ensure_resources(db, username)
        r = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
        if r:
            player_resources = {
                "fish": r["fish"] or 0, "herbs": r["herbs"] or 0,
                "gold": r["gold"] or 0, "blood_gems": r["blood_gems"] or 0,
                "bones": r["bones"] or 0, "spell_fragments": r["spell_fragments"] or 0,
            }
        g = get_gold(db, username)
        player_resources["gold"] = g
    db.close()
    return jsonify({"status": "success", **info,
                    "contributors": contributors,
                    "player_resources": player_resources})


@app.route("/building/donate", methods=["POST"])
def building_donate():
    data          = request.get_json(silent=True) or {}
    username      = data.get("username", "").strip()
    building_id   = data.get("building_id", "").strip()
    resource_type = data.get("resource_type", "").strip()
    amount        = int(data.get("amount", 0))

    if amount <= 0:
        return jsonify({"status": "error", "message": "Amount must be positive."})
    cfg = BUILDING_UPGRADES.get(building_id)
    if not cfg:
        return jsonify({"status": "error", "message": "Not upgradeable."})
    if resource_type not in _RES_COL:
        return jsonify({"status": "error", "message": "Invalid resource."})

    db = get_db()
    ensure_building_row(db, building_id)
    row = db.execute(
        "SELECT * FROM building_upgrades WHERE building_id=?", (building_id,)
    ).fetchone()
    current_level = row["current_level"] if row else 1
    max_level     = row["max_level"]     if row else 5

    if current_level >= max_level:
        db.close()
        return jsonify({"status": "error", "message": "Building is already max level."})

    next_level = current_level + 1
    next_req   = {k: v for k, v in cfg["levels"][next_level].items() if k != "benefit"}
    if resource_type not in next_req:
        db.close()
        return jsonify({"status": "error", "message": f"{resource_type} is not needed for the next upgrade."})

    # Check player has enough
    ensure_resources(db, username)
    if resource_type == "gold":
        player_have = get_gold(db, username)
    else:
        r = db.execute(f"SELECT {resource_type} FROM resources WHERE username=?", (username,)).fetchone()
        player_have = (r[resource_type] if r else 0) or 0

    if player_have < amount:
        db.close()
        return jsonify({"status": "error", "message": f"Not enough {resource_type}. Have {player_have}, need {amount}."})

    # Deduct resource
    if resource_type == "gold":
        db.execute("UPDATE resources SET gold=gold-? WHERE username=?", (amount, username))
    else:
        db.execute(f"UPDATE resources SET {resource_type}={resource_type}-? WHERE username=?", (amount, username))

    # Add to building total
    col = _RES_COL[resource_type]
    db.execute(f"UPDATE building_upgrades SET {col}={col}+? WHERE building_id=?", (amount, building_id))

    # Record donation
    db.execute(
        "INSERT INTO building_donations (building_id, username, resource_type, amount, donated_at) VALUES (?,?,?,?,?)",
        (building_id, username, resource_type, amount, int(time.time()))
    )

    log_event(db, "village",
              f"{username} donated {amount} {resource_type} to {cfg['name']}",
              username)

    # Refresh row and check for level-up
    row = db.execute("SELECT * FROM building_upgrades WHERE building_id=?", (building_id,)).fetchone()
    leveled_up = False
    new_level  = current_level
    all_met = all(
        (row[_RES_COL[res]] or 0) >= need
        for res, need in next_req.items()
        if res in _RES_COL
    )
    if all_met:
        new_level = next_level
        # Reset donated counters
        db.execute(
            "UPDATE building_upgrades SET current_level=?, fish_donated=0, herbs_donated=0, "
            "gold_donated=0, blood_gems_donated=0, bones_donated=0, spell_fragments_donated=0 "
            "WHERE building_id=?",
            (new_level, building_id)
        )
        benefit = cfg["levels"][new_level].get("benefit", "")
        log_event(db, "village",
                  f"🏗️ {cfg['name']} has been upgraded to Level {new_level}! {benefit} Thanks to the village!",
                  None)
        leveled_up = True

    db.commit()
    db.close()
    return jsonify({
        "status":          "success",
        "donated":         amount,
        "resource":        resource_type,
        "building_level":  new_level,
        "level_up":        leveled_up,
    })


@app.route("/building/contributors/<building_id>")
def building_contributors(building_id):
    db   = get_db()
    rows = db.execute(
        "SELECT username, SUM(amount) AS total FROM building_donations "
        "WHERE building_id=? GROUP BY username ORDER BY total DESC LIMIT 10",
        (building_id,)
    ).fetchall()
    db.close()
    return jsonify({
        "status":       "success",
        "contributors": [{"rank": i+1, "username": r["username"], "total": r["total"]}
                         for i, r in enumerate(rows)]
    })


@app.route("/building/all_levels")
def building_all_levels():
    """Lightweight endpoint returning current level for every upgradeable building."""
    db  = get_db()
    rows = db.execute("SELECT building_id, current_level FROM building_upgrades").fetchall()
    db.close()
    levels = {r["building_id"]: r["current_level"] for r in rows}
    # Fill defaults for any not yet in DB
    for bid in BUILDING_UPGRADES:
        levels.setdefault(bid, 1)
    return jsonify(levels)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
