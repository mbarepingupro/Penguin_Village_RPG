from dotenv import load_dotenv
import hashlib
import os
import datetime
import random
from flask import Flask, jsonify, redirect, request, session, url_for, render_template
from database import init_db, get_db, backfill_cosmetics
from feature_flags import FEATURES
from level_config import LEVEL_DATA, get_total_gathering_bonus, get_next_milestone, COSMETIC_SLOTS
import time
import requests as http_requests

load_dotenv()

TWITCH_CLIENT_ID    = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
SECRET_KEY          = os.getenv("SECRET_KEY")
MAYOR_KEY           = os.getenv("MAYOR_KEY", "")
MAYOR_USERNAME      = "mbarepingu"

BUFF_NAMES = {
    "double_resources": "2x Resources",
    "double_xp":        "2x XP",
    "double_gold":      "2x Gold",
    "half_energy":      "Half Energy Costs",
    "festival":         "Festival (2x XP + 2x Gold)",
}

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Reverse lookup: cosmetic name → level that awards it
_COSMETIC_LEVEL_MAP = {}
for _lvl, _ldata in LEVEL_DATA.items():
    for _c in (_ldata.get("reward") or {}).get("cosmetics", []):
        _COSMETIC_LEVEL_MAP[_c] = _lvl

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
            2: {"fish": 1000, "gold": 500,  "benefit": "+15% fish rate for everyone"},
            3: {"fish": 5000, "gold": 2500, "benefit": "+30% fish rate for everyone"},
        },
    },
    "club_soda": {
        "name": "Club Soda",
        "levels": {
            2: {"herbs": 1000, "gold": 500,  "benefit": "+15% herb rate for everyone"},
            3: {"herbs": 5000, "gold": 2500, "benefit": "+30% herb rate for everyone"},
        },
    },
    "parkmusement": {
        "name": "Ash's Parkmusement",
        "levels": {
            2: {"gold": 1500, "benefit": "+15% gold rate for everyone"},
            3: {"gold": 7500, "benefit": "+30% gold rate for everyone"},
        },
    },
    "cursed_temple": {
        "name": "Cursed Temple",
        "levels": {
            2: {"spell_fragments": 800,  "gold": 500,  "benefit": "+15% XP rate for everyone"},
            3: {"spell_fragments": 4000, "gold": 2500, "benefit": "+30% XP rate for everyone"},
        },
    },
    "guillotine": {
        "name": "Gil the Guillotine",
        "levels": {
            2: {"blood_gems": 200,  "bones": 200,  "gold": 500,  "benefit": "+15% blood gem and bone rate for everyone"},
            3: {"blood_gems": 1000, "bones": 1000, "gold": 2500, "benefit": "+30% rate for everyone"},
        },
    },
}

CONTRIBUTION_MILESTONES = {
    100:  {"name": "Contributor's Frame",      "description": "A warm glow for those who give back."},
    500:  {"name": "Builder's Canvas",          "description": "The village remembers your generosity."},
    1000: {"name": "Architect's Backdrop",      "description": "You shaped this village with your own flippers."},
    5000: {"name": "Legendary Founder's Frame", "description": "A living legend of Penguin Village."},
}

BUILDING_BONUS_RATES = {1: 0.0, 2: 0.15, 3: 0.30}

BOUTIQUE_ITEMS = {
    "hats": [
        {"id": "baseball_cap",  "name": "Baseball Cap",  "slot": "hat", "price": 200,  "tier": "cheap"},
        {"id": "beanie",        "name": "Beanie",         "slot": "hat", "price": 350,  "tier": "cheap"},
        {"id": "party_hat",     "name": "Party Hat",      "slot": "hat", "price": 400,  "tier": "mid"},
        {"id": "beret",         "name": "Beret",          "slot": "hat", "price": 450,  "tier": "mid"},
        {"id": "chefs_hat",     "name": "Chef's Hat",     "slot": "hat", "price": 500,  "tier": "mid"},
        {"id": "cowboy_hat",    "name": "Cowboy Hat",     "slot": "hat", "price": 600,  "tier": "mid"},
        {"id": "viking_helmet", "name": "Viking Helmet",  "slot": "hat", "price": 800,  "tier": "mid"},
        {"id": "top_hat",       "name": "Top Hat",        "slot": "hat", "price": 800,  "tier": "mid"},
        {"id": "pirate_hat",    "name": "Pirate Hat",     "slot": "hat", "price": 1000, "tier": "expensive"},
    ],
    "outfits": [
        {"id": "plain_tshirt",    "name": "Plain T-Shirt",    "slot": "cape", "price": 200,  "tier": "cheap"},
        {"id": "hawaiian_shirt",  "name": "Hawaiian Shirt",   "slot": "cape", "price": 350,  "tier": "cheap"},
        {"id": "hoodie",          "name": "Hoodie",           "slot": "cape", "price": 400,  "tier": "mid"},
        {"id": "bra",             "name": "Bra",              "slot": "cape", "price": 500,  "tier": "mid"},
        {"id": "lab_coat",        "name": "Lab Coat",         "slot": "cape", "price": 600,  "tier": "mid"},
        {"id": "leather_jacket",  "name": "Leather Jacket",   "slot": "cape", "price": 800,  "tier": "mid"},
        {"id": "tuxedo_vest",     "name": "Tuxedo Vest",      "slot": "cape", "price": 1200, "tier": "expensive"},
        {"id": "superhero_cape",  "name": "Superhero Cape",   "slot": "cape", "price": 1500, "tier": "expensive"},
        {"id": "tuxedo",          "name": "Full Tuxedo",      "slot": "cape", "price": 2500, "tier": "expensive"},
    ],
    "footwear": [
        {"id": "sandals",       "name": "Sandals",       "slot": "footwear", "price": 150, "tier": "cheap"},
        {"id": "sneakers",      "name": "Sneakers",      "slot": "footwear", "price": 200, "tier": "cheap"},
        {"id": "fuzzy_slippers","name": "Fuzzy Slippers","slot": "footwear", "price": 250, "tier": "cheap"},
        {"id": "rain_boots",    "name": "Rain Boots",    "slot": "footwear", "price": 300, "tier": "cheap"},
        {"id": "roller_skates", "name": "Roller Skates", "slot": "footwear", "price": 500, "tier": "mid"},
        {"id": "cowboy_boots",  "name": "Cowboy Boots",  "slot": "footwear", "price": 700, "tier": "mid"},
    ],
    "accessories": [
        {"id": "lollipop",    "name": "Lollipop",    "slot": "accessory", "price": 150,  "tier": "cheap"},
        {"id": "scarf_shop",  "name": "Scarf",        "slot": "accessory", "price": 200,  "tier": "cheap"},
        {"id": "sunglasses",  "name": "Sunglasses",   "slot": "accessory", "price": 300,  "tier": "cheap"},
        {"id": "bow_tie",     "name": "Bow Tie",       "slot": "accessory", "price": 350,  "tier": "mid"},
        {"id": "backpack",    "name": "Backpack",      "slot": "accessory", "price": 400,  "tier": "mid"},
        {"id": "monocle",     "name": "Monocle",       "slot": "accessory", "price": 500,  "tier": "mid"},
        {"id": "bubble_pipe", "name": "Bubble Pipe",   "slot": "accessory", "price": 600,  "tier": "mid"},
        {"id": "gold_chain",  "name": "Gold Chain",    "slot": "accessory", "price": 1000, "tier": "expensive"},
        {"id": "dragon_wings","name": "Dragon Wings",  "slot": "accessory", "price": 3000, "tier": "expensive"},
    ],
}

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
    "boutique": {
        "name": "The Penguin Boutique", "icon": "🛍️",
        "desc": "The finest penguin fashion this side of the ice shelf. No refunds. All sales are final. You'll look fabulous.",
        "type": "shop",
        "pos": {"x": 0, "y": 0},
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
        "produces": {"fish": 12.5, "gold": 5.0, "xp": 2.0},
        "pos": {"x": 36, "y": 62},
    },
    "parkmusement": {
        "name": "Ash's Parkmusement", "icon": "🎪",
        "desc": "Step right up! Juggle fish for coins! No refunds.",
        "type": "job", "job_label": "CIRCUS",
        "produces": {"gold": 15.0, "xp": 2.0},
        "pos": {"x": 47, "y": 48},
    },
    "cursed_temple": {
        "name": "Cursed Temple", "icon": "⛩️",
        "desc": "Dark rituals. Ancient power. No refunds.",
        "type": "job", "job_label": "MONK",
        "produces": {"spell_fragments": 12.5, "gold": 8.0, "xp": 4.0},
        "pos": {"x": 9, "y": 30},
    },
    "club_soda": {
        "name": "Club Soda", "icon": "🌿",
        "desc": "Where the herbs are fresh and the beats are questionable.",
        "type": "job", "job_label": "HERBALISM",
        "produces": {"herbs": 12.5, "gold": 5.0, "xp": 2.0},
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
        "produces": {"blood_gems": 5.0, "bones": 5.0, "gold": 5.0, "xp": 2.0},
        "pos": {"x": 84, "y": 58},
    },
}

# ── MONSTERS ──────────────────────────────────────────────────────────────────
_MONSTER_ICONS = {
    "crab":               "🦀",
    "bat":                "🦇",
    "rat":                "🐀",
    "shell_lurker":       "🐚",
    "ice_squid":          "🦑",
    "frost_beetle":       "🪲",
    "pufferfish":         "🐡",
    "wolf":               "🐺",
    "snowman":            "☃️",
    "shadow_penguin":     "🐧",
    "ice_hawk":           "🦅",
    "frost_scorpion":     "🦂",
    "snow_bear":          "🐻",
    "frost_wraith":       "👻",
    "ice_spider":         "🕷️",
    "frost_shark":        "🦈",
    "tundra_boar":        "🐗",
    "living_iceblock":    "🧊",
    "cursed_owl":         "🦉",
    "glacier_croc":       "🐊",
    "night_stalker":      "🌑",
    "golem":              "🗿",
    "serpent":            "🐍",
    "druid":              "🧙",
    "ice_drake":          "🐉",
    "fallen_knight":      "⚔️",
    "blizzard_elemental": "🌪️",
    "elite_frostbear":    "🐻",
    "frost_demon":        "😈",
    "ancient_wyrm":       "🐲",
    "deaths_herald":      "💀",
}

MONSTER_TYPES = {
    # ── TIER 1 — NEWCOMER GROUNDS (level 1) ──────────────────────────────────
    "crab": {
        "tier": 1, "min_level": 1, "combat_power": 15,
        "variants": ["Snow Crab", "Hermit Crab", "Giant Crab"],
        "energy_cost": 25,
        "rewards": {"gold": [50, 100], "xp": [45, 75], "resources": {"fish": [20, 50]}, "gear_drop_chance": 0.25},
    },
    "bat": {
        "tier": 1, "min_level": 1, "combat_power": 18,
        "variants": ["Ice Bat", "Cave Bat", "Frost Wing"],
        "energy_cost": 25,
        "rewards": {"gold": [40, 90], "xp": [36, 66], "resources": {"herbs": [20, 40]}, "gear_drop_chance": 0.25},
    },
    "rat": {
        "tier": 1, "min_level": 1, "combat_power": 12,
        "variants": ["Frost Rat", "Sewer Rat", "Snow Mouse"],
        "energy_cost": 25,
        "rewards": {"gold": [25, 75], "xp": [30, 60], "resources": {"bones": [10, 30]}, "gear_drop_chance": 0.20},
    },
    "shell_lurker": {
        "tier": 1, "min_level": 1, "combat_power": 14,
        "variants": ["Tide Shell", "Giant Conch", "Lurking Shell"],
        "energy_cost": 25,
        "rewards": {"gold": [40, 90], "xp": [36, 66], "resources": {"fish": [10, 40]}, "gear_drop_chance": 0.20},
    },
    "ice_squid": {
        "tier": 1, "min_level": 1, "combat_power": 16,
        "variants": ["Baby Squid", "Frost Squid", "Ink Specter"],
        "energy_cost": 25,
        "rewards": {"gold": [50, 90], "xp": [36, 66], "resources": {"fish": [20, 40], "herbs": [10, 20]}, "gear_drop_chance": 0.20},
    },
    "frost_beetle": {
        "tier": 1, "min_level": 1, "combat_power": 13,
        "variants": ["Tunnel Bug", "Ice Crawler", "Crystal Grub"],
        "energy_cost": 25,
        "rewards": {"gold": [30, 70], "xp": [30, 60], "resources": {"bones": [10, 20]}, "gear_drop_chance": 0.20},
    },
    "pufferfish": {
        "tier": 1, "min_level": 1, "combat_power": 17,
        "variants": ["Toxic Puffer", "Spiky Fish", "Blowfish"],
        "energy_cost": 25,
        "rewards": {"gold": [40, 80], "xp": [36, 66], "resources": {"fish": [20, 50], "herbs": [10, 20]}, "gear_drop_chance": 0.25},
    },
    # ── TIER 2 — FROZEN FRONTIER (level 6) ───────────────────────────────────
    "wolf": {
        "tier": 2, "min_level": 6, "combat_power": 35,
        "variants": ["Blizzard Wolf", "Shadow Wolf", "Arctic Dire Wolf"],
        "energy_cost": 25,
        "rewards": {"gold": [100, 200], "xp": [90, 150], "resources": {"bones": [30, 60], "blood_gems": [10, 20]}, "gear_drop_chance": 0.20},
    },
    "snowman": {
        "tier": 2, "min_level": 6, "combat_power": 40,
        "variants": ["Cursed Snowman", "Frost Golem", "Ice Construct"],
        "energy_cost": 25,
        "rewards": {"gold": [110, 210], "xp": [96, 156], "resources": {"spell_fragments": [20, 40]}, "gear_drop_chance": 0.18},
    },
    "shadow_penguin": {
        "tier": 2, "min_level": 6, "combat_power": 38,
        "variants": ["Shadow Penguin", "Dark Penguin", "Void Waddle"],
        "energy_cost": 25,
        "rewards": {"gold": [110, 190], "xp": [84, 144], "resources": {"blood_gems": [20, 40]}, "gear_drop_chance": 0.22},
    },
    "ice_hawk": {
        "tier": 2, "min_level": 6, "combat_power": 33,
        "variants": ["Storm Hawk", "Tundra Raptor", "Frozen Eagle"],
        "energy_cost": 25,
        "rewards": {"gold": [90, 180], "xp": [84, 135], "resources": {"herbs": [30, 60]}, "gear_drop_chance": 0.20},
    },
    "frost_scorpion": {
        "tier": 2, "min_level": 6, "combat_power": 37,
        "variants": ["Ice Stinger", "Polar Pincer", "Frost Venom"],
        "energy_cost": 25,
        "rewards": {"gold": [100, 190], "xp": [90, 144], "resources": {"blood_gems": [10, 30], "bones": [20, 40]}, "gear_drop_chance": 0.18},
    },
    "snow_bear": {
        "tier": 2, "min_level": 6, "combat_power": 42,
        "variants": ["Snowfield Cub", "Frost Grizzly", "Avalanche Bear"],
        "energy_cost": 25,
        "rewards": {"gold": [125, 225], "xp": [105, 165], "resources": {"bones": [40, 80]}, "gear_drop_chance": 0.18},
    },
    "frost_wraith": {
        "tier": 2, "min_level": 6, "combat_power": 36,
        "variants": ["Ice Spirit", "Chilling Specter", "Pale Phantom"],
        "energy_cost": 25,
        "rewards": {"gold": [110, 200], "xp": [90, 150], "resources": {"spell_fragments": [10, 30]}, "gear_drop_chance": 0.22},
    },
    # ── TIER 3 — SHADOW TERRITORY (level 11) ─────────────────────────────────
    "ice_spider": {
        "tier": 3, "min_level": 11, "combat_power": 58,
        "variants": ["Web Creeper", "Frost Widow", "Icy Spinner"],
        "energy_cost": 25,
        "rewards": {"gold": [175, 300], "xp": [120, 195], "resources": {"herbs": [40, 80], "bones": [30, 50]}, "gear_drop_chance": 0.15},
    },
    "frost_shark": {
        "tier": 3, "min_level": 11, "combat_power": 62,
        "variants": ["Glacier Fin", "Deep Frostbite", "Ice Jaw"],
        "energy_cost": 25,
        "rewards": {"gold": [190, 310], "xp": [126, 204], "resources": {"fish": [60, 120]}, "gear_drop_chance": 0.15},
    },
    "tundra_boar": {
        "tier": 3, "min_level": 11, "combat_power": 57,
        "variants": ["Frozen Tusker", "Blizzard Hog", "Snow Crusher"],
        "energy_cost": 25,
        "rewards": {"gold": [165, 290], "xp": [114, 186], "resources": {"bones": [50, 90]}, "gear_drop_chance": 0.15},
    },
    "living_iceblock": {
        "tier": 3, "min_level": 11, "combat_power": 65,
        "variants": ["Frostcube", "Crystalline Mass", "Cryo Entity"],
        "energy_cost": 25,
        "rewards": {"gold": [200, 325], "xp": [135, 210], "resources": {"spell_fragments": [30, 50]}, "gear_drop_chance": 0.14},
    },
    "cursed_owl": {
        "tier": 3, "min_level": 11, "combat_power": 60,
        "variants": ["Night Eye", "Shadow Talon", "Hexed Feather"],
        "energy_cost": 25,
        "rewards": {"gold": [175, 300], "xp": [126, 195], "resources": {"spell_fragments": [20, 50], "herbs": [30, 60]}, "gear_drop_chance": 0.16},
    },
    "glacier_croc": {
        "tier": 3, "min_level": 11, "combat_power": 63,
        "variants": ["Tundra Jaws", "Frost Maw", "Ice Scale"],
        "energy_cost": 25,
        "rewards": {"gold": [190, 315], "xp": [129, 201], "resources": {"fish": [50, 100], "bones": [30, 60]}, "gear_drop_chance": 0.14},
    },
    "night_stalker": {
        "tier": 3, "min_level": 11, "combat_power": 68,
        "variants": ["Shadow Creeper", "Dusk Hunter", "Void Walker"],
        "energy_cost": 25,
        "rewards": {"gold": [200, 325], "xp": [135, 210], "resources": {"blood_gems": [30, 60]}, "gear_drop_chance": 0.15},
    },
    # ── TIER 4 — CURSED DEPTHS (level 16) ────────────────────────────────────
    "golem": {
        "tier": 4, "min_level": 16, "combat_power": 85,
        "variants": ["Stone Golem", "Crystal Golem", "Ancient Guardian"],
        "energy_cost": 25,
        "rewards": {"gold": [275, 425], "xp": [180, 270], "resources": {"bones": [60, 120], "blood_gems": [30, 60]}, "gear_drop_chance": 0.12},
    },
    "serpent": {
        "tier": 4, "min_level": 16, "combat_power": 90,
        "variants": ["Sea Serpent", "Ice Wyrm", "Frost Leviathan"],
        "energy_cost": 25,
        "rewards": {"gold": [290, 450], "xp": [186, 285], "resources": {"fish": [80, 150], "spell_fragments": [30, 50]}, "gear_drop_chance": 0.12},
    },
    "druid": {
        "tier": 4, "min_level": 16, "combat_power": 82,
        "variants": ["Dark Druid", "Cursed Shaman", "Shadow Priest"],
        "energy_cost": 25,
        "rewards": {"gold": [275, 425], "xp": [186, 276], "resources": {"spell_fragments": [50, 90], "herbs": [50, 90]}, "gear_drop_chance": 0.14},
    },
    "ice_drake": {
        "tier": 4, "min_level": 16, "combat_power": 95,
        "variants": ["Frost Whelp", "Arctic Drake", "Glacial Serpent"],
        "energy_cost": 25,
        "rewards": {"gold": [300, 475], "xp": [195, 300], "resources": {"blood_gems": [40, 80], "spell_fragments": [20, 40]}, "gear_drop_chance": 0.12},
    },
    "fallen_knight": {
        "tier": 4, "min_level": 16, "combat_power": 88,
        "variants": ["Lost Paladin", "Cursed Champion", "Hollow Warden"],
        "energy_cost": 25,
        "rewards": {"gold": [290, 460], "xp": [186, 285], "resources": {"bones": [50, 100], "blood_gems": [20, 50]}, "gear_drop_chance": 0.12},
    },
    "blizzard_elemental": {
        "tier": 4, "min_level": 16, "combat_power": 100,
        "variants": ["Storm Core", "Blizzard Wraith", "Polar Force"],
        "energy_cost": 25,
        "rewards": {"gold": [310, 490], "xp": [195, 300], "resources": {"spell_fragments": [40, 80]}, "gear_drop_chance": 0.12},
    },
    # ── TIER 5 — THE ABYSS (level 26) ────────────────────────────────────────
    "elite_frostbear": {
        "tier": 5, "min_level": 26, "combat_power": 125,
        "variants": ["Frostbear Alpha", "Glacial Ursine", "Permafrost Beast"],
        "energy_cost": 25,
        "rewards": {"gold": [450, 700], "xp": [270, 420], "resources": {"blood_gems": [60, 120], "bones": [80, 150]}, "gear_drop_chance": 0.10},
    },
    "frost_demon": {
        "tier": 5, "min_level": 26, "combat_power": 140,
        "variants": ["Frost Wraith Lord", "Infernal Ice", "Arctic Demon"],
        "energy_cost": 25,
        "rewards": {"gold": [500, 750], "xp": [300, 450], "resources": {"blood_gems": [80, 140], "spell_fragments": [50, 100]}, "gear_drop_chance": 0.10},
    },
    "ancient_wyrm": {
        "tier": 5, "min_level": 26, "combat_power": 155,
        "variants": ["Void Dragon", "Ancient Serpent", "Deep Abyss"],
        "energy_cost": 25,
        "rewards": {"gold": [550, 800], "xp": [330, 495], "resources": {"spell_fragments": [80, 150], "blood_gems": [50, 100]}, "gear_drop_chance": 0.08},
    },
    "deaths_herald": {
        "tier": 5, "min_level": 26, "combat_power": 160,
        "variants": ["Death Knight", "The Reaper", "End Bringer"],
        "energy_cost": 25,
        "rewards": {"gold": [600, 900], "xp": [360, 540], "resources": {"blood_gems": [100, 180], "bones": [100, 180]}, "gear_drop_chance": 0.08},
    },
}

COMMUNITY_BOSS = {
    "name":        "The Blizzard King",
    "icon":        "👑",
    "desc":        "An ancient ice titan. His wrath freezes the entire village.",
    "max_hp":      10000,
    "hit_rewards": {"xp": 50, "gold": 25},
    "kill_rewards": {"xp": 500, "gold": 300, "blood_gems": 15, "spell_fragments": 10},
    "energy_cost": 25,
    "speed":       20,
    "attack":      50,
    "defense":     20,
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

# ── GEAR DROP TEMPLATES ───────────────────────────────────────────────────────
GEAR_TEMPLATES = {
    "common": {
        "weapon": {"attack_bonus":(3,8),   "defense_bonus":(0,2),  "speed_bonus":(0,2),  "hp_bonus":(0,5)},
        "chest":  {"attack_bonus":(0,2),   "defense_bonus":(5,12), "speed_bonus":(0,2),  "hp_bonus":(5,15)},
        "boots":  {"attack_bonus":(0,2),   "defense_bonus":(2,6),  "speed_bonus":(3,8),  "hp_bonus":(0,5)},
        "helm":   {"attack_bonus":(0,2),   "defense_bonus":(3,8),  "speed_bonus":(0,2),  "hp_bonus":(5,10)},
    },
    "uncommon": {
        "weapon": {"attack_bonus":(8,15),  "defense_bonus":(0,3),  "speed_bonus":(2,5),  "hp_bonus":(0,8)},
        "chest":  {"attack_bonus":(0,3),   "defense_bonus":(12,22),"speed_bonus":(0,3),  "hp_bonus":(15,25)},
        "boots":  {"attack_bonus":(2,5),   "defense_bonus":(5,10), "speed_bonus":(8,14), "hp_bonus":(0,8)},
        "helm":   {"attack_bonus":(0,3),   "defense_bonus":(8,15), "speed_bonus":(2,5),  "hp_bonus":(10,18)},
    },
    "rare": {
        "weapon": {"attack_bonus":(15,25), "defense_bonus":(2,5),  "speed_bonus":(3,8),  "hp_bonus":(5,15)},
        "chest":  {"attack_bonus":(2,5),   "defense_bonus":(22,35),"speed_bonus":(2,5),  "hp_bonus":(25,40)},
        "boots":  {"attack_bonus":(3,8),   "defense_bonus":(8,16), "speed_bonus":(12,20),"hp_bonus":(5,12)},
        "helm":   {"attack_bonus":(2,5),   "defense_bonus":(15,25),"speed_bonus":(3,8),  "hp_bonus":(18,30)},
    },
    "epic": {
        "weapon": {"attack_bonus":(25,40), "defense_bonus":(3,8),  "speed_bonus":(5,12), "hp_bonus":(10,20)},
        "chest":  {"attack_bonus":(3,8),   "defense_bonus":(35,50),"speed_bonus":(3,8),  "hp_bonus":(40,60)},
        "boots":  {"attack_bonus":(5,12),  "defense_bonus":(14,24),"speed_bonus":(18,28),"hp_bonus":(8,18)},
        "helm":   {"attack_bonus":(3,8),   "defense_bonus":(24,38),"speed_bonus":(5,12), "hp_bonus":(28,45)},
    },
    "legendary": {
        "weapon": {"attack_bonus":(40,60), "defense_bonus":(5,12), "speed_bonus":(8,18), "hp_bonus":(15,30)},
        "chest":  {"attack_bonus":(5,12),  "defense_bonus":(50,70),"speed_bonus":(5,12), "hp_bonus":(60,90)},
        "boots":  {"attack_bonus":(8,18),  "defense_bonus":(22,36),"speed_bonus":(26,40),"hp_bonus":(12,25)},
        "helm":   {"attack_bonus":(5,12),  "defense_bonus":(36,55),"speed_bonus":(8,18), "hp_bonus":(42,65)},
    },
}

_GEAR_DROP_RARITY_WEIGHTS = {
    1: {"common": 70, "uncommon": 25, "rare": 5,  "epic": 0,  "legendary": 0},
    2: {"common": 40, "uncommon": 40, "rare": 15, "epic": 5,  "legendary": 0},
    3: {"common": 15, "uncommon": 35, "rare": 35, "epic": 14, "legendary": 1},
    4: {"common": 5,  "uncommon": 20, "rare": 40, "epic": 30, "legendary": 5},
    5: {"common": 0,  "uncommon": 10, "rare": 25, "epic": 40, "legendary": 25},
}

_GEAR_DROP_NAMES = {
    "weapon": {"common":"Worn Blade",    "uncommon":"Sturdy Blade",  "rare":"Ice Blade",    "epic":"Cursed Blade",   "legendary":"Divine Blade"},
    "chest":  {"common":"Worn Plate",    "uncommon":"Sturdy Plate",  "rare":"Ice Plate",    "epic":"Cursed Plate",   "legendary":"Divine Plate"},
    "boots":  {"common":"Worn Boots",    "uncommon":"Sturdy Boots",  "rare":"Ice Boots",    "epic":"Cursed Boots",   "legendary":"Divine Boots"},
    "helm":   {"common":"Worn Helm",     "uncommon":"Sturdy Helm",   "rare":"Ice Helm",     "epic":"Cursed Helm",    "legendary":"Divine Helm"},
}

# ── SET BONUSES ───────────────────────────────────────────────────────────────
SET_BONUSES = {
    "Frost Guardian": {
        2: {"defense_bonus": 10, "hp_bonus": 20},
        3: {"defense_bonus": 20, "hp_bonus": 40, "speed_bonus": 5},
    },
    "Blood Reaper": {
        2: {"attack_bonus": 12, "speed_bonus": 5},
        3: {"attack_bonus": 25, "speed_bonus": 10, "defense_bonus": 5},
    },
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


def get_active_buffs(db):
    now = int(time.time())
    rows = db.execute(
        "SELECT * FROM active_buffs WHERE expires_at > ? ORDER BY activated_at",
        (now,)
    ).fetchall()
    return [dict(r) for r in rows]


def _is_mayor_authed():
    if session.get("username") == MAYOR_USERNAME:
        return True
    key = request.args.get("key", "") or (request.get_json(silent=True) or {}).get("key", "")
    return bool(MAYOR_KEY and key == MAYOR_KEY)


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


def get_daily_variant(monster_type_id):
    """Return the daily flavor variant for a monster type, consistent within a UTC day."""
    mtype = MONSTER_TYPES[monster_type_id]
    today = get_today()
    h = hashlib.md5(f"{monster_type_id}:{today}".encode()).hexdigest()
    idx = int(h[:4], 16) % len(mtype["variants"])
    result = {k: v for k, v in mtype.items() if k != "variants"}
    result["name"] = mtype["variants"][idx]
    result["icon"] = _MONSTER_ICONS.get(monster_type_id, "❓")
    result["type_id"] = monster_type_id
    return result


def calculate_set_bonuses(db, username):
    """Sum up set bonuses from all equipped gear pieces."""
    equipped = db.execute(
        "SELECT set_name FROM gear WHERE username=? AND equipped=1 AND set_name IS NOT NULL",
        (username,)
    ).fetchall()
    counts = {}
    for g in equipped:
        sn = g["set_name"]
        if sn:
            counts[sn] = counts.get(sn, 0) + 1
    bonuses = {"attack_bonus": 0, "defense_bonus": 0, "speed_bonus": 0, "hp_bonus": 0}
    for set_name, count in counts.items():
        if set_name in SET_BONUSES:
            for pieces, bonus in sorted(SET_BONUSES[set_name].items()):
                if count >= pieces:
                    for stat, val in bonus.items():
                        bonuses[stat] = bonuses.get(stat, 0) + val
    return bonuses


def get_combat_power(username):
    db = get_db()
    try:
        p = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
        level = p["level"] if p else 1
        cp = 10 + level * 3
        equipped = db.execute(
            "SELECT attack_bonus, defense_bonus, speed_bonus, hp_bonus FROM gear "
            "WHERE username=? AND equipped=1 AND type='combat'", (username,)
        ).fetchall()
        for item in equipped:
            cp += item["attack_bonus"] + item["defense_bonus"] + item["speed_bonus"] + (item["hp_bonus"] // 5)
        sb = calculate_set_bonuses(db, username)
        cp += sb["attack_bonus"] + sb["defense_bonus"] + sb["speed_bonus"] + (sb["hp_bonus"] // 5)
        for buff in get_active_buffs(db):
            if buff["buff_type"] == "festival":
                cp = int(cp * 1.1)
    finally:
        db.close()
    return cp

def update_passive_energy(username):
    """Lazy 10-energy/hr passive regen. Manages its own DB connection."""
    db = get_db()
    try:
        penguin = db.execute(
            "SELECT energy, max_energy, last_energy_update FROM penguins WHERE username=?",
            (username,)
        ).fetchone()
        if not penguin:
            return
        now = int(time.time())
        last_update = penguin["last_energy_update"] or 0
        if last_update == 0:
            db.execute("UPDATE penguins SET last_energy_update=? WHERE username=?", (now, username))
            db.commit()
            return
        energy_to_add = int((now - last_update) / 3600.0 * 10)
        if energy_to_add > 0:
            max_energy = penguin["max_energy"] or 100
            new_energy = min(max_energy, (penguin["energy"] or 0) + energy_to_add)
            db.execute(
                "UPDATE penguins SET energy=?, last_energy_update=? WHERE username=?",
                (new_energy, now, username)
            )
            db.commit()
    finally:
        db.close()


def calculate_win_chance(player_cp, monster_cp):
    return max(5, min(95, 50 + (player_cp - monster_cp)))

def get_evaluation(win_chance):
    if win_chance >= 90: return "Free Real Estate"
    if win_chance >= 75: return "Easy Peasy"
    if win_chance >= 60: return "Feeling Lucky"
    if win_chance >= 50: return "Coin Flip"
    if win_chance >= 40: return "Sweaty Flippers"
    if win_chance >= 25: return "Pray to the Mayor"
    if win_chance >= 10: return "Basically Suicide"
    return "Miracle Required"

def resolve_fight(player_cp, monster_cp):
    win_chance = calculate_win_chance(player_cp, monster_cp)
    roll = random.randint(1, 100)
    return {
        "victory": roll <= win_chance,
        "roll": roll,
        "win_chance": win_chance,
        "evaluation": get_evaluation(win_chance),
        "player_cp": player_cp,
        "monster_cp": monster_cp,
    }


def get_combat_stats(db, username):
    p     = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
    level = p["level"] if p else 1
    attack  = 5 + level * 2
    defense = 5 + level * 2
    speed   = 5 + level
    hp      = 50 + level * 5
    equipped = db.execute(
        "SELECT attack_bonus, defense_bonus, speed_bonus, hp_bonus FROM gear WHERE username=? AND equipped=1",
        (username,)
    ).fetchall()
    for g in equipped:
        attack  += g["attack_bonus"]
        defense += g["defense_bonus"]
        speed   += g["speed_bonus"]
        hp      += g["hp_bonus"]
    sb = calculate_set_bonuses(db, username)
    attack  += sb["attack_bonus"]
    defense += sb["defense_bonus"]
    speed   += sb["speed_bonus"]
    hp      += sb["hp_bonus"]
    return {"attack": attack, "defense": defense, "speed": speed, "hp": hp, "level": level}


def generate_gear_drop(monster_tier):
    """Generate a random gear drop for a given monster tier."""
    weights  = _GEAR_DROP_RARITY_WEIGHTS.get(monster_tier, _GEAR_DROP_RARITY_WEIGHTS[1])
    pool     = [r for r, w in weights.items() for _ in range(w)]
    rarity   = random.choice(pool)
    slot     = random.choice(["weapon", "chest", "boots", "helm"])
    tmpl     = GEAR_TEMPLATES[rarity][slot]
    stats    = {k: random.randint(v[0], v[1]) for k, v in tmpl.items()}
    name     = _GEAR_DROP_NAMES[slot][rarity]
    item_id  = f"drop_{slot}_{rarity}_{int(time.time())}_{random.randint(1000,9999)}"
    return {"name": name.upper(), "item_id": item_id, "type": "combat", "slot": slot,
            "rarity": rarity, "set_name": None, **stats}


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
backfill_cosmetics(LEVEL_DATA, COSMETIC_SLOTS)
# Seed building_upgrades rows for each upgradeable building
_seed_db = get_db()
for _bid in BUILDING_UPGRADES:
    _seed_db.execute("INSERT OR IGNORE INTO building_upgrades (building_id) VALUES (?)", (_bid,))
_seed_db.commit()
_seed_db.close()


# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    # Editor mode — only available from localhost
    if request.args.get("editor") == "true":
        host = request.host.split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            return redirect(url_for("home"))
        return render_template("editor.html")

    username = session.get("username")
    if not username:
        return render_template("home.html", logged_in=False, features=FEATURES)
    update_passive_energy(username)
    db = get_db()
    penguin = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not penguin:
        session.clear()
        db.close()
        return render_template("home.html", logged_in=False, features=FEATURES)
    ensure_resources(db, username)

    # ── Streak + daily mission — trigger once per calendar day ──────────────
    today = get_today()
    streak_row_pre = db.execute("SELECT last_login_date FROM login_streaks WHERE username=?", (username,)).fetchone()
    is_new_day = not streak_row_pre or streak_row_pre["last_login_date"] != today
    if is_new_day:
        streak = update_login_streak(db, username, today)
        if not session.get("daily_reward"):
            session["daily_reward"] = compute_daily_reward()
        milestone = award_streak_milestone(db, username, streak)
        if milestone and not session.get("streak_reward"):
            session["streak_reward"] = milestone
        advance_mission(db, username, "login_today", today)
        check_achievements(db, username)

    # Always update last_active so welcome-back and active-ping work correctly
    db.execute("UPDATE penguins SET last_active=? WHERE username=?", (int(time.time()), username))

    db.commit()
    resources  = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    streak_row = db.execute("SELECT current_streak FROM login_streaks WHERE username=?", (username,)).fetchone()
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
        ensure_resources(db, username)
        db.execute(
            "INSERT OR IGNORE INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
            (username, "first_login", int(time.time()))
        )
    except Exception:
        session["new_user"] = False
    db.commit()
    db.close()
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/profile/<username>")
def profile(username):
    update_passive_energy(username)
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
    p  = db.execute(
        "SELECT job, job_started, job_duration, energy, max_energy, hotel_uses_today, last_hotel_date FROM penguins WHERE username=?",
        (username,)
    ).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    ensure_resources(db, username)
    gold = get_gold(db, username)
    today_str = get_today()
    hotel_uses = p["hotel_uses_today"] or 0
    last_hotel = p["last_hotel_date"] or ""
    hotel_remaining = 2 if last_hotel != today_str else max(0, 2 - hotel_uses)
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
        "preview_earnings":       preview_earnings,
        "hotel_remaining_today":  hotel_remaining,
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

    # Apply active mayor buffs
    xp_mult = resource_mult = gold_mult = 1.0
    for _buff in get_active_buffs(db):
        bt = _buff["buff_type"]
        if bt == "double_resources": resource_mult *= 2.0; gold_mult *= 2.0
        elif bt == "double_xp":     xp_mult        *= 2.0
        elif bt == "double_gold":   gold_mult       *= 2.0
        elif bt == "festival":      xp_mult *= 2.0; gold_mult *= 2.0

    earned    = {}
    level_ups = []
    ensure_resources(db, username)

    for resource, rate_per_hour in b.get("produces", {}).items():
        if resource == "xp":
            amount = int(rate_per_hour * stream_mult * (1 + building_bonus) * hours_worked * xp_mult)
        elif resource == "gold":
            amount = int(rate_per_hour * stream_mult * (1 + gathering_bonus + building_bonus) * hours_worked * gold_mult)
        else:
            amount = int(rate_per_hour * stream_mult * (1 + gathering_bonus + building_bonus) * hours_worked * resource_mult)
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
    today = get_today()
    p  = db.execute(
        "SELECT energy, max_energy, job, hotel_uses_today, last_hotel_date FROM penguins WHERE username=?",
        (username,)
    ).fetchone()
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
    uses_today = (p["hotel_uses_today"] or 0) if (p["last_hotel_date"] or "") == today else 0
    if uses_today >= 2:
        db.close()
        return jsonify({"status": "error", "message": "The penguins at the hotel are exhausted. Come back tomorrow! 💤"})
    cost = 100 if uses_today == 0 else 500
    ensure_resources(db, username)
    gold = get_gold(db, username)
    if gold < cost:
        db.close()
        return jsonify({"status": "error", "message": f"Not enough gold! Need {cost} gold.", "need": cost, "have": gold})
    to_restore = max_e - energy
    add_gold(db, username, -cost)
    db.execute("UPDATE penguins SET energy=?, hotel_uses_today=?, last_hotel_date=? WHERE username=?",
               (max_e, uses_today + 1, today, username))
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
    seal_ids = {s["id"] for s in SEAL_SHOP}
    cosmetics = []
    for g in rows:
        d = dict(g)
        if d.get("rarity") == "milestone":
            lvl = _COSMETIC_LEVEL_MAP.get(d.get("name", ""), "?")
            d["source"] = f"Level {lvl} Reward"
        elif d.get("item_id") in seal_ids:
            d["source"] = "Seal Shop"
        elif d.get("rarity") == "achievement":
            d["source"] = "Achievement"
        else:
            d["source"] = "Gear Shop"
        cosmetics.append(d)
    return jsonify({"cosmetics": cosmetics})


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

_MAX_FIRST_KILLS = sum(len(m["variants"]) for m in MONSTER_TYPES.values())

@app.route("/combat/monsters/<username>")
def combat_monsters(username):
    if not FEATURES.get("combat", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!", "monsters": []})
    update_passive_energy(username)
    today = get_today()
    try:
        db = get_db()
        p  = db.execute("SELECT level, energy, max_energy FROM penguins WHERE username=?", (username,)).fetchone()
        player_level = p["level"] if p else 1
        killed_today = {
            row["monster_id"] for row in
            db.execute("SELECT monster_id FROM monster_kills WHERE username=? AND killed_date=?", (username, today))
        }
        first_kills_done = {
            (row["monster_type"], row["variant_name"]) for row in
            db.execute("SELECT monster_type, variant_name FROM first_kills WHERE username=?", (username,))
        }
        db.close()
        player_cp = get_combat_power(username)
        result = []
        for type_id, mtype in MONSTER_TYPES.items():
            variant    = get_daily_variant(type_id)
            mcp        = mtype["combat_power"]
            win_chance = calculate_win_chance(player_cp, mcp)
            rdef       = mtype["rewards"]
            res_parts  = [f"{lo}-{hi} {k.replace('_',' ')}" for k, (lo, hi) in rdef["resources"].items()]
            is_new     = (type_id, variant["name"]) not in first_kills_done
            result.append({
                "type":         type_id,
                "name":         variant["name"],
                "icon":         variant["icon"],
                "tier":         mtype["tier"],
                "combat_power": mcp,
                "energy_cost":  mtype["energy_cost"],
                "min_level":    mtype["min_level"],
                "rewards_preview": {
                    "gold":            f"{rdef['gold'][0]}-{rdef['gold'][1]}",
                    "xp":              f"{rdef['xp'][0]}-{rdef['xp'][1]}",
                    "resources":       ", ".join(res_parts),
                    "gear_drop_chance": rdef["gear_drop_chance"],
                },
                "win_chance":   win_chance,
                "evaluation":   get_evaluation(win_chance),
                "killed_today": type_id in killed_today,
                "is_new":       is_new,
                "locked":       player_level < mtype["min_level"],
            })
        return jsonify({
            "monsters":           result,
            "player_cp":          player_cp,
            "player_level":       player_level,
            "player_energy":      p["energy"] if p else 100,
            "player_max_energy":  p["max_energy"] if p else 100,
            "first_kills_count":  len(first_kills_done),
            "max_first_kills":    _MAX_FIRST_KILLS,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "monsters": []})


@app.route("/combat/fight", methods=["POST"])
def combat_fight():
    if not FEATURES.get("combat", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    db = None
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        monster_id = data.get("monster_id", "")

        update_passive_energy(username)

        mtype = MONSTER_TYPES.get(monster_id)
        if not mtype:
            return jsonify({"status": "error", "message": "Unknown monster."})

        today = get_today()
        db = get_db()
        p = db.execute("SELECT level, energy FROM penguins WHERE username=?", (username,)).fetchone()
        if not p:
            return jsonify({"status": "error", "message": "Penguin not found."})
        if p["level"] < mtype["min_level"]:
            return jsonify({"status": "error", "message": f"Need level {mtype['min_level']}."})

        energy_cost = mtype["energy_cost"]
        if (p["energy"] or 0) < energy_cost:
            return jsonify({"status": "error", "message": f"Need {energy_cost} energy to fight."})

        if db.execute(
            "SELECT 1 FROM monster_kills WHERE username=? AND monster_id=? AND killed_date=?",
            (username, monster_id, today)
        ).fetchone():
            return jsonify({"status": "error", "message": "Already defeated today."})

        variant = get_daily_variant(monster_id)
        monster_name = variant["name"]

        is_first_kill_eligible = not db.execute(
            "SELECT 1 FROM first_kills WHERE username=? AND monster_type=? AND variant_name=?",
            (username, monster_id, monster_name)
        ).fetchone()

        db.execute("UPDATE penguins SET energy=MAX(0,energy-?) WHERE username=?", (energy_cost, username))
        energy_remaining = max(0, (p["energy"] or 0) - energy_cost)

        player_cp = get_combat_power(username)
        fight = resolve_fight(player_cp, mtype["combat_power"])

        advance_mission(db, username, "fight_1", today)
        ensure_resources(db, username)

        rewards = {}
        consolation_xp = 0
        is_first_kill = False

        if fight["victory"]:
            rdef = mtype["rewards"]
            multiplier = 2 if is_first_kill_eligible else 1
            gold      = random.randint(rdef["gold"][0], rdef["gold"][1]) * multiplier
            xp        = random.randint(rdef["xp"][0],   rdef["xp"][1])   * multiplier
            resources = {k: random.randint(lo, hi) * multiplier for k, (lo, hi) in rdef["resources"].items()}

            add_gold(db, username, gold)
            award_xp(db, username, xp)
            for res, amt in resources.items():
                db.execute(f"UPDATE resources SET {res}={res}+? WHERE username=?", (amt, username))

            if is_first_kill_eligible:
                is_first_kill = True
                db.execute(
                    "INSERT OR IGNORE INTO first_kills (username, monster_type, variant_name, killed_at) VALUES (?,?,?,?)",
                    (username, monster_id, monster_name, int(time.time()))
                )

            gear_drop = None
            if random.random() < rdef["gear_drop_chance"]:
                gear_drop = generate_gear_drop(mtype["tier"])
                db.execute(
                    "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, "
                    "attack_bonus, defense_bonus, speed_bonus, hp_bonus, equipped, obtained_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)",
                    (username, gear_drop["item_id"], gear_drop["name"], gear_drop["set_name"],
                     gear_drop["type"], gear_drop["slot"], gear_drop["rarity"],
                     gear_drop["attack_bonus"], gear_drop["defense_bonus"],
                     gear_drop["speed_bonus"], gear_drop["hp_bonus"], int(time.time()))
                )

            rewards = {"gold": gold, "xp": xp, "resources": resources}
            if gear_drop:
                rewards["gear_drop"] = {
                    "name":     gear_drop["name"],
                    "rarity":   gear_drop["rarity"],
                    "slot":     gear_drop["slot"],
                    "set_name": gear_drop["set_name"],
                }

            loot_summary = f"+{gold} gold, +{xp} xp"
            if is_first_kill:
                loot_summary += " [FIRST KILL!]"
            if gear_drop:
                loot_summary += f" + {gear_drop['name']} ({gear_drop['rarity']})"
            log_event(db, "combat", f"{username} defeated {monster_name}! {loot_summary} 🎉", username)
            advance_mission(db, username, "first_fight", today)
            check_achievements(db, username)
            db.execute(
                "INSERT INTO monster_kills (username, monster_id, killed_date, loot_summary) VALUES (?,?,?,?)",
                (username, monster_id, today, str(rewards))
            )
        else:
            consolation_xp = max(1, mtype["rewards"]["xp"][0] // 4)
            award_xp(db, username, consolation_xp)
            log_event(db, "combat", f"{username} was defeated by {monster_name}...", username)
        db.commit()

        resp = {
            "status":           "success",
            "victory":          fight["victory"],
            "roll":             fight["roll"],
            "win_chance":       fight["win_chance"],
            "evaluation":       fight["evaluation"],
            "player_cp":        fight["player_cp"],
            "monster_cp":       fight["monster_cp"],
            "energy_spent":     energy_cost,
            "energy_remaining": energy_remaining,
            "monster_name":     monster_name,
            "monster_icon":     variant["icon"],
            "is_first_kill":    is_first_kill,
        }
        if fight["victory"]:
            resp["rewards"] = rewards
        else:
            resp["consolation_xp"] = consolation_xp
        return jsonify(resp)

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if db: db.close()


# ── COMMUNITY BOSS ───────────────────────────────────────────────────────────

@app.route("/combat/boss/status")
def boss_status():
    if not FEATURES.get("combat", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!", "boss": None})
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM community_boss WHERE defeated_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            db.close()
            return jsonify({"boss": None, "active": False})
        boss_id = row["id"]
        parts   = db.execute(
            "SELECT username, damage_dealt, hits FROM boss_participants WHERE boss_id=? ORDER BY damage_dealt DESC",
            (boss_id,)
        ).fetchall()
        db.close()
        return jsonify({
            "active":       True,
            "boss": {
                "id":          boss_id,
                "name":        row["name"],
                "icon":        COMMUNITY_BOSS["icon"],
                "max_hp":      row["max_hp"],
                "current_hp":  row["current_hp"],
                "spawned_at":  row["spawned_at"],
                "spawned_by":  row["spawned_by"],
            },
            "participants": [dict(p) for p in parts],
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "boss": None})
    finally:
        if db:
            db.close()


@app.route("/combat/boss/attack", methods=["POST"])
def boss_attack():
    if not FEATURES.get("combat", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    db = None
    try:
        data     = request.get_json(silent=True) or {}
        username = data.get("username", "")

        db  = get_db()
        p   = db.execute("SELECT level, energy FROM penguins WHERE username=?", (username,)).fetchone()
        if not p:
            return jsonify({"status": "error", "message": "Penguin not found."})

        boss_row = db.execute(
            "SELECT * FROM community_boss WHERE defeated_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not boss_row:
            return jsonify({"status": "error", "message": "No active boss right now."})

        energy_cost = COMMUNITY_BOSS["energy_cost"]
        if (p["energy"] or 0) < energy_cost:
            return jsonify({"status": "error", "message": f"Need {energy_cost} energy to fight the boss."})

        boss_id = boss_row["id"]
        stats   = get_combat_stats(db, username)
        mspd    = COMMUNITY_BOSS["speed"]
        pspd    = stats["speed"]
        matk    = COMMUNITY_BOSS["attack"]
        mdef    = COMMUNITY_BOSS["defense"]
        patk    = stats["attack"]

        if pspd >= mspd:
            hit_dmg = max(1, patk - mdef // 2 + random.randint(-3, 3))
        else:
            hit_dmg = max(1, patk - mdef // 2 + random.randint(-5, 0))

        new_hp   = max(0, boss_row["current_hp"] - hit_dmg)
        defeated = new_hp <= 0
        now      = int(time.time())

        db.execute("UPDATE community_boss SET current_hp=? WHERE id=?", (new_hp, boss_id))
        db.execute("UPDATE penguins SET energy=MAX(0,energy-?) WHERE username=?", (energy_cost, username))

        db.execute(
            "INSERT INTO boss_participants (boss_id, username, damage_dealt, hits, last_hit_at) "
            "VALUES (?,?,?,1,?) ON CONFLICT(boss_id,username) DO UPDATE SET "
            "damage_dealt=damage_dealt+excluded.damage_dealt, hits=hits+1, last_hit_at=excluded.last_hit_at",
            (boss_id, username, hit_dmg, now)
        )

        ensure_resources(db, username)
        hit_rewards = COMMUNITY_BOSS["hit_rewards"]
        award_xp(db, username, hit_rewards.get("xp", 0))
        add_gold(db, username, hit_rewards.get("gold", 0))

        kill_rewards = {}
        if defeated:
            db.execute("UPDATE community_boss SET defeated_at=? WHERE id=?", (now, boss_id))
            kill_rewards = COMMUNITY_BOSS["kill_rewards"]
            participants = db.execute(
                "SELECT username FROM boss_participants WHERE boss_id=?", (boss_id,)
            ).fetchall()
            for part in participants:
                pname = part["username"]
                ensure_resources(db, pname)
                award_xp(db, pname, kill_rewards.get("xp", 0))
                add_gold(db, pname, kill_rewards.get("gold", 0))
                for res in ("blood_gems", "spell_fragments"):
                    if kill_rewards.get(res):
                        db.execute(f"UPDATE resources SET {res}={res}+? WHERE username=?",
                                   (kill_rewards[res], pname))
            log_event(db, "combat",
                      f"The village defeated {COMMUNITY_BOSS['name']}! {len(participants)} penguins fought! 🎉",
                      username)

        db.commit()
        return jsonify({
            "status":       "success",
            "hit_damage":   hit_dmg,
            "boss_hp":      new_hp,
            "boss_max_hp":  boss_row["max_hp"],
            "defeated":     defeated,
            "hit_rewards":  hit_rewards,
            "kill_rewards": kill_rewards if defeated else {},
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if db:
            db.close()


@app.route("/mayor/spawn-boss", methods=["POST"])
def mayor_spawn_boss():
    key = request.args.get("key", "")
    mayor_key = os.getenv("MAYOR_KEY", "")
    authed = session.get("username") == "mbarepingu" or (mayor_key and key == mayor_key)
    if not authed:
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    db = None
    try:
        db      = get_db()
        active  = db.execute(
            "SELECT id FROM community_boss WHERE defeated_at IS NULL"
        ).fetchone()
        if active:
            return jsonify({"status": "error", "message": "A boss is already active."})
        now      = int(time.time())
        spawner  = session.get("username") or "mayor"
        db.execute(
            "INSERT INTO community_boss (name, max_hp, current_hp, spawned_at, spawned_by) VALUES (?,?,?,?,?)",
            (COMMUNITY_BOSS["name"], COMMUNITY_BOSS["max_hp"], COMMUNITY_BOSS["max_hp"], now, spawner)
        )
        log_event(db, "combat",
                  f"⚠️ {COMMUNITY_BOSS['name']} has appeared! Fight together to defeat it!", spawner)
        db.commit()
        return jsonify({"status": "success", "message": f"{COMMUNITY_BOSS['name']} has been spawned!"})
    except Exception as e:
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
    return jsonify({"missions": missions, "date": today, "is_live": bool(_stream_was_live)})


@app.route("/missions/<username>/claim/<key>", methods=["POST"])
def claim_stream_mission(username, key):
    defn = MISSION_DEFS.get(key)
    if not defn or not defn.get("stream"):
        return jsonify({"status": "error", "message": "Not a claimable stream mission."})
    if not _stream_was_live:
        return jsonify({"status": "error", "message": "Stream must be live to claim this mission."})
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
    update_passive_energy(username)
    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"show": False})

    now         = int(time.time())
    last_active = p["last_active"] or 0

    if last_active == 0:
        db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
        db.commit()
        db.close()
        return jsonify({"show": False})

    hours_away = min((now - last_active) / 3600.0, 12.0)

    if hours_away < 0.5:
        db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
        db.commit()
        db.close()
        return jsonify({"show": False})

    ensure_resources(db, username)

    # ── Active job preview (READ ONLY — never auto-collect) ──────────────────
    active_job = None
    if p["job"]:
        b = BUILDINGS.get(p["job"])
        if b and b.get("type") == "job":
            job_started  = p["job_started"] or 0
            elapsed_secs = now - job_started
            hours_worked = min(elapsed_secs / 3600.0, JOB_CAP_HOURS)
            hours_remaining = max(0.0, JOB_CAP_HOURS - hours_worked)
            wb_bonus = get_total_gathering_bonus(p["level"] or 1) / 100.0
            produces  = b.get("produces", {})
            # Pick the primary non-gold, non-xp resource for the preview
            resource_type   = next((r for r in produces if r not in ("gold", "xp")), None)
            res_rate        = produces.get(resource_type, 0) if resource_type else 0
            gold_rate       = produces.get("gold", 0)
            xp_rate         = produces.get("xp", 0)
            resources_so_far = int(res_rate * (1 + wb_bonus) * hours_worked) if resource_type else 0
            gold_so_far      = int(gold_rate * (1 + wb_bonus) * hours_worked)
            xp_so_far        = int(xp_rate * hours_worked)
            active_job = {
                "building":        p["job"],
                "building_name":   b["name"],
                "building_icon":   b.get("icon", "🏢"),
                "hours_worked":    round(hours_worked, 2),
                "hours_remaining": round(hours_remaining, 2),
                "resources_so_far": resources_so_far,
                "resource_type":    resource_type,
                "gold_so_far":      gold_so_far,
                "xp_so_far":        xp_so_far,
                "complete":         hours_worked >= JOB_CAP_HOURS,
            }

    # ── Passive earnings (always awarded) ────────────────────────────────────
    passive_gold = int(min(hours_away, 12.0) * 3.0)
    passive_xp   = int(min(hours_away, 12.0) * 5.0)
    leveled_passive = False
    if passive_gold > 0:
        add_gold(db, username, passive_gold)
    if passive_xp > 0:
        lv, _ = award_xp(db, username, passive_xp)
        if lv:
            leveled_passive = True

    # ── Village news (notable events since last_active) ───────────────────────
    notable_types = ("village", "prestige", "mayor", "milestone")
    news_rows = db.execute(
        f"SELECT message FROM event_log WHERE event_type IN ({','.join('?'*len(notable_types))})"
        " AND created_at > ? AND username != ? ORDER BY created_at DESC LIMIT 5",
        (*notable_types, last_active, username)
    ).fetchall()
    village_news = [r["message"] for r in news_rows]

    # ── Streak check (ensure home-route streak is up-to-date) ────────────────
    today = get_today()
    streak_row = db.execute("SELECT last_login_date FROM login_streaks WHERE username=?", (username,)).fetchone()
    if not streak_row or streak_row["last_login_date"] != today:
        update_login_streak(db, username, today)

    db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
    db.commit()
    db.close()

    return jsonify({
        "show":             True,
        "hours_away":       round(hours_away, 1),
        "active_job":       active_job,
        "passive_earnings": {
            "gold":       passive_gold,
            "xp":         passive_xp,
            "leveled_up": leveled_passive,
        },
        "village_news": village_news,
    })


# ── ACTIVE PING ───────────────────────────────────────────────────────────────

@app.route("/active/<username>")
def active(username):
    update_passive_energy(username)
    db = get_db()
    p  = db.execute("SELECT energy FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "skip"})
    now = int(time.time())
    db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
    db.commit()
    db.close()
    return jsonify({"status": "ok", "energy": p["energy"] or 0})


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
    max_level     = row["max_level"]     if row else 3
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
    player_building_total = 0
    player_total_contributions = 0
    next_milestone = None
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

        r2 = db.execute(
            "SELECT SUM(amount) as total FROM building_donations WHERE building_id=? AND username=?",
            (building_id, username)
        ).fetchone()
        player_building_total = (r2["total"] if r2 else 0) or 0

        p2 = db.execute("SELECT total_contributions FROM penguins WHERE username=?", (username,)).fetchone()
        player_total_contributions = ((p2["total_contributions"] if p2 else 0) or 0)

        for threshold in sorted(CONTRIBUTION_MILESTONES.keys()):
            if player_total_contributions < threshold:
                next_milestone = {"threshold": threshold, **CONTRIBUTION_MILESTONES[threshold]}
                break

    db.close()
    return jsonify({"status": "success", **info,
                    "contributors": contributors,
                    "player_resources": player_resources,
                    "player_building_total": player_building_total,
                    "player_total_contributions": player_total_contributions,
                    "next_milestone": next_milestone})


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
    max_level     = row["max_level"]     if row else 3

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

    # XP reward for donor
    if resource_type == "gold":
        xp_earned = amount // 4
    elif resource_type in ("blood_gems", "bones"):
        xp_earned = amount
    else:
        xp_earned = amount // 2

    donation_level_ups = []
    if xp_earned > 0:
        _, lv_rewards = award_xp(db, username, xp_earned)
        donation_level_ups.extend(lv_rewards)

    # Track total contributions
    p_contrib = db.execute("SELECT total_contributions FROM penguins WHERE username=?", (username,)).fetchone()
    old_total = ((p_contrib["total_contributions"] if p_contrib else 0) or 0)
    new_total = old_total + amount
    db.execute("UPDATE penguins SET total_contributions=? WHERE username=?", (new_total, username))

    # Milestone check
    milestone_unlocked = None
    for milestone, reward in sorted(CONTRIBUTION_MILESTONES.items()):
        if old_total < milestone <= new_total:
            item_id = reward["name"].lower().replace(" ", "_").replace("'", "").replace(",", "")
            existing = db.execute(
                "SELECT COUNT(*) as cnt FROM gear WHERE username=? AND item_id=? AND type='cosmetic'",
                (username, item_id)
            ).fetchone()
            if not existing or existing["cnt"] == 0:
                db.execute(
                    "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
                    "VALUES (?,?,?,'cosmetic','card_frame','milestone',0,?)",
                    (username, item_id, reward["name"], int(time.time()))
                )
            log_event(db, "milestone",
                      f"🎉 {username} unlocked '{reward['name']}' for contributing {milestone:,} total resources!",
                      username)
            milestone_unlocked = {"name": reward["name"], "description": reward["description"], "threshold": milestone}

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
        "status":                  "success",
        "donated":                 amount,
        "resource":                resource_type,
        "building_level":          new_level,
        "level_up":                leveled_up,
        "xp_earned":               xp_earned,
        "new_total_contributions": new_total,
        "milestone_unlocked":      milestone_unlocked,
        "level_ups":               donation_level_ups,
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


# ── PENGUIN BOUTIQUE ──────────────────────────────────────────────────────────

@app.route("/boutique/items")
def boutique_items():
    username = request.args.get("username", "")
    db = get_db()
    owned_ids = {row["item_id"] for row in db.execute(
        "SELECT item_id FROM gear WHERE username=? AND type='cosmetic' AND rarity='shop'",
        (username,)
    ).fetchall()}
    equipped_ids = {row["item_id"] for row in db.execute(
        "SELECT item_id FROM gear WHERE username=? AND type='cosmetic' AND rarity='shop' AND equipped=1",
        (username,)
    ).fetchall()}
    player_gold = get_gold(db, username)
    db.close()
    result = {}
    for category, items in BOUTIQUE_ITEMS.items():
        result[category] = [
            {**item, "owned": item["id"] in owned_ids, "equipped": item["id"] in equipped_ids}
            for item in items
        ]
    return jsonify({"status": "success", "categories": result, "player_gold": player_gold})


@app.route("/boutique/buy", methods=["POST"])
def boutique_buy():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    item_id  = data.get("item_id", "")
    item = next(
        (i for items in BOUTIQUE_ITEMS.values() for i in items if i["id"] == item_id),
        None
    )
    if not item:
        return jsonify({"status": "error", "message": "Item not found."})
    db = get_db()
    if get_gold(db, username) < item["price"]:
        shortfall = item["price"] - get_gold(db, username)
        db.close()
        return jsonify({"status": "error", "message": f"Not enough gold! Need {shortfall:,} more."})
    existing = db.execute(
        "SELECT 1 FROM gear WHERE username=? AND item_id=? AND type='cosmetic' AND rarity='shop'",
        (username, item_id)
    ).fetchone()
    if existing:
        db.close()
        return jsonify({"status": "error", "message": "Already owned!"})
    db.execute("UPDATE resources SET gold=gold-? WHERE username=?", (item["price"], username))
    db.execute(
        "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
        "VALUES (?,?,?,'cosmetic',?,'shop',0,?)",
        (username, item_id, item["name"], item["slot"], int(time.time()))
    )
    gold_remaining = get_gold(db, username)
    log_event(db, "shop", f"{username} purchased {item['name']} from The Penguin Boutique! 🛍️", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "item": item, "gold_remaining": gold_remaining})


@app.route("/boutique/equip", methods=["POST"])
def boutique_equip():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "")
    item_id  = data.get("item_id", "")
    db = get_db()
    gear_row = db.execute(
        "SELECT id, slot, equipped FROM gear WHERE username=? AND item_id=? AND type='cosmetic' AND rarity='shop'",
        (username, item_id)
    ).fetchone()
    if not gear_row:
        db.close()
        return jsonify({"status": "error", "message": "Item not found in wardrobe."})
    if gear_row["equipped"]:
        db.execute("UPDATE gear SET equipped=0 WHERE id=?", (gear_row["id"],))
        db.commit(); db.close()
        return jsonify({"status": "success", "equipped": False})
    db.execute("UPDATE gear SET equipped=0 WHERE username=? AND slot=?", (username, gear_row["slot"]))
    db.execute("UPDATE gear SET equipped=1 WHERE id=?", (gear_row["id"],))
    db.commit(); db.close()
    return jsonify({"status": "success", "equipped": True})


@app.route("/boutique/preview/<item_id>")
def boutique_preview(item_id):
    item = next(
        (i for items in BOUTIQUE_ITEMS.values() for i in items if i["id"] == item_id),
        None
    )
    if not item:
        return jsonify({"status": "error", "message": "Item not found."})
    return jsonify({"status": "success", "item": item})


# ── PENGUIN CARD & PUBLIC PROFILE ─────────────────────────────────────────────
import io
from PIL import Image, ImageDraw, ImageFont

CARD_FONT_PATH  = os.path.join(os.path.dirname(__file__), "static", "fonts", "PressStart2P-Regular.ttf")
CARD_SPRITE_PATH = os.path.join(os.path.dirname(__file__), "static", "penguin.png")
CARD_W, CARD_H  = 600, 340
LEFT_W           = 190

_COLORS = {
    "bg":     (28,  28,  28),
    "purple": (168, 110, 255),
    "pink":   (255, 127, 229),
    "orange": (255, 140,   0),
    "green":  ( 74, 255, 107),
    "white":  (255, 255, 255),
    "gray":   (136, 136, 136),
    "dark":   ( 18,  18,  18),
}

def _font(size):
    try:
        return ImageFont.truetype(CARD_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()

def _job_label(job):
    labels = {
        "sea_lion_pit":  "Fishing",
        "parkmusement":  "Circus",
        "cursed_temple": "Monk",
        "club_soda":     "Herbalism",
        "guillotine":    "Executioner",
    }
    return labels.get(job, job.replace("_", " ").title() if job else "Resting")


def _get_public_penguin(username):
    """Return (penguin_row, resources_row, earned_titles, gold) or None."""
    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return None
    ensure_resources(db, username)
    r  = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    gold = get_gold(db, username)
    titles = get_all_earned_titles(db, username)
    # top building contribution
    top_contrib = db.execute(
        "SELECT building_id, SUM(amount) AS total FROM building_donations "
        "WHERE username=? GROUP BY building_id ORDER BY total DESC LIMIT 1",
        (username,)
    ).fetchone()
    # favourite job (most hours)
    hour_cols = ["fishing_hours", "herbalism_hours", "circus_hours", "monk_hours", "executioner_hours"]
    hours_map = {c: (p[c] or 0) for c in hour_cols}
    fav_col   = max(hours_map, key=hours_map.get)
    fav_hours = hours_map[fav_col]
    fav_label_map = {
        "fishing_hours": "Fishing", "herbalism_hours": "Herbalism",
        "circus_hours": "Circus", "monk_hours": "Monk", "executioner_hours": "Executioner",
    }
    fav_job = fav_label_map[fav_col] if fav_hours > 0 else None
    total_hours = sum(hours_map.values())
    # top achievement
    ach = db.execute(
        "SELECT achievement_id FROM achievements WHERE username=? ORDER BY unlocked_at ASC LIMIT 1",
        (username,)
    ).fetchone()
    # card cosmetics
    cosmetics = db.execute(
        "SELECT item_id FROM gear WHERE username=? AND type='cosmetic' AND equipped=1",
        (username,)
    ).fetchall()
    cosmetic_ids = {c["item_id"] for c in cosmetics if c["item_id"]}
    db.close()
    level, _, _ = xp_progress(p["xp"] or 0)
    return {
        "p": dict(p), "r": dict(r) if r else {}, "gold": gold,
        "titles": titles, "level": level,
        "top_contrib": dict(top_contrib) if top_contrib else None,
        "fav_job": fav_job, "total_hours": round(total_hours, 1),
        "top_ach": ach["achievement_id"] if ach else None,
        "cosmetic_ids": cosmetic_ids,
    }


def _generate_card_image(data):
    d   = data["p"]
    lv  = data["level"]
    img = Image.new("RGB", (CARD_W, CARD_H), _COLORS["bg"])
    draw = ImageDraw.Draw(img)

    has_golden_frame  = "golden_frame"  in data["cosmetic_ids"]
    has_sparkle       = "animated_sparkle" in data["cosmetic_ids"]

    # Outer border
    border_col = _COLORS["orange"] if has_golden_frame else _COLORS["purple"]
    for i in range(3):
        draw.rectangle([i, i, CARD_W-1-i, CARD_H-1-i], outline=border_col)

    # Divider line
    for y in range(4, CARD_H-4):
        draw.point((LEFT_W, y), fill=(50, 50, 50))

    # ── LEFT: sprite + username + title ──
    try:
        sprite = Image.open(CARD_SPRITE_PATH).convert("RGBA").resize((80, 80), Image.NEAREST)
        bg_patch = Image.new("RGB", (80, 80), _COLORS["bg"])
        bg_patch.paste(sprite, mask=sprite.split()[3])
        img.paste(bg_patch, (LEFT_W//2 - 40, 40))
    except Exception:
        pass

    username = d.get("username", "UNKNOWN")
    draw.text((LEFT_W//2, 135), username.upper(), font=_font(7), fill=_COLORS["white"], anchor="mm")
    active_title = d.get("active_title")
    if active_title:
        draw.text((LEFT_W//2, 153), active_title, font=_font(6), fill=_COLORS["purple"], anchor="mm")

    prestige = d.get("prestige") or 0
    if prestige > 0:
        stars = "★" * prestige
        draw.text((LEFT_W//2, 170), stars, font=_font(8), fill=_COLORS["pink"], anchor="mm")

    # Gathering bonus chip
    from level_config import get_total_gathering_bonus
    gb = get_total_gathering_bonus(lv)
    if gb > 0:
        draw.text((LEFT_W//2, CARD_H - 30), f"+{gb}% gather", font=_font(5), fill=_COLORS["green"], anchor="mm")

    # ── RIGHT: stats ──
    rx = LEFT_W + 18
    ry = 20
    draw.text((rx, ry), "PENGUIN VILLAGE", font=_font(9), fill=_COLORS["purple"])
    ry += 28

    draw.text((rx, ry), f"LEVEL {lv}", font=_font(10), fill=_COLORS["white"])
    ry += 26

    job_str = _job_label(d.get("job"))
    draw.text((rx, ry), f"JOB: {job_str.upper()}", font=_font(7), fill=_COLORS["orange"])
    ry += 20

    gold_val = data.get("gold", 0)
    draw.text((rx, ry), f"GOLD: {gold_val}", font=_font(7), fill=_COLORS["orange"])
    ry += 20

    if active_title:
        draw.text((rx, ry), f'"{active_title}"', font=_font(6), fill=_COLORS["purple"])
        ry += 18

    fav = data.get("fav_job")
    if fav:
        draw.text((rx, ry), f"BEST AT: {fav.upper()}", font=_font(6), fill=_COLORS["gray"])
        ry += 16

    total_h = data.get("total_hours", 0)
    draw.text((rx, ry), f"HOURS WORKED: {total_h}", font=_font(5), fill=_COLORS["gray"])
    ry += 14

    # Sparkle corners
    if has_sparkle:
        for cx, cy in [(10,10),(CARD_W-20,10),(10,CARD_H-20),(CARD_W-20,CARD_H-20)]:
            draw.text((cx, cy), "✦", font=_font(8), fill=_COLORS["pink"])

    # URL footer
    draw.text((CARD_W//2, CARD_H - 12),
              f"mbarepingu.com/penguin/{username.lower()}",
              font=_font(5), fill=_COLORS["gray"], anchor="mm")

    return img


@app.route("/penguin/<username>")
def public_profile(username):
    data = _get_public_penguin(username)
    if not data:
        return render_template("profile.html", exists=False, username=username)
    d   = data["p"]
    lv  = data["level"]
    return render_template(
        "profile.html",
        exists=True,
        username=d["username"],
        level=lv,
        prestige=d.get("prestige") or 0,
        active_title=d.get("active_title"),
        job=_job_label(d.get("job")),
        gold=data["gold"],
        total_hours=data["total_hours"],
        fav_job=data["fav_job"],
        top_ach=data["top_ach"],
        top_contrib=data["top_contrib"],
        titles=data["titles"],
        og_image=request.host_url.rstrip("/") + f"/card/{username}/image",
        og_url=request.host_url.rstrip("/") + f"/penguin/{username}",
    )


@app.route("/card/<username>")
def card_page(username):
    data = _get_public_penguin(username)
    if not data:
        return f"<h1>Penguin not found</h1>", 404
    d  = data["p"]
    lv = data["level"]
    og_img = request.host_url.rstrip("/") + f"/card/{username}/image"
    og_url = request.host_url.rstrip("/") + f"/penguin/{username}"
    desc   = f"Level {lv}"
    if d.get("active_title"):
        desc += f" {d['active_title']}"
    desc += f" | {_job_label(d.get('job'))} | Penguin Village"
    return render_template(
        "profile.html",
        exists=True,
        username=d["username"],
        level=lv,
        prestige=d.get("prestige") or 0,
        active_title=d.get("active_title"),
        job=_job_label(d.get("job")),
        gold=data["gold"],
        total_hours=data["total_hours"],
        fav_job=data["fav_job"],
        top_ach=data["top_ach"],
        top_contrib=data["top_contrib"],
        titles=data["titles"],
        og_image=og_img,
        og_url=og_url,
        card_only=True,
    )


@app.route("/card/<username>/image")
def card_image(username):
    data = _get_public_penguin(username)
    if not data:
        return "Not found", 404
    img = _generate_card_image(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype="image/png")


_VILLAGE_LAYOUT_PATH = os.path.join(os.path.dirname(__file__), "static", "village_layout.json")

_BUILDING_HOME_TILES = {
    "hotel":         (4,  6),
    "sea_lion_pit":  (3, 11),
    "club_soda":     (8,  5),
    "cursed_temple": (15, 5),
    "parkmusement":  (9, 11),
    "guillotine":    (15,10),
    "award_hall":    (6, 16),
    "bank":          (11,15),
    "barracks":      (16,16),
    "horny_jail":    (1, 13),
}
_DEFAULT_HOME_TILE = (5, 10)


@app.route("/village/layout/save", methods=["POST"])
def save_village_layout():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"status": "error", "message": "Only accessible from localhost"}), 403
    data = request.get_json(silent=True)
    if not data or "grid" not in data or "buildings" not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    with open(_VILLAGE_LAYOUT_PATH, "w") as f:
        json.dump(data, f, indent=2)
    return jsonify({"status": "success"})


@app.route("/village/layout")
def village_layout():
    try:
        with open(_VILLAGE_LAYOUT_PATH) as f:
            layout = json.load(f)
    except FileNotFoundError:
        return jsonify({"error": "layout not found"}), 404

    db = get_db()
    rows = db.execute("SELECT building_id, current_level FROM building_upgrades").fetchall()
    db.close()
    levels = {r["building_id"]: r["current_level"] for r in rows}
    for bid in BUILDING_UPGRADES:
        levels.setdefault(bid, 1)

    layout["building_levels"] = levels
    return jsonify(layout)


@app.route("/village/penguins")
def village_penguins():
    cutoff = int(time.time()) - 1800
    db = get_db()
    rows = db.execute(
        """SELECT p.username, p.job, p.level, p.prestige, p.active_title
           FROM penguins p
           WHERE p.last_active > ?
           ORDER BY p.last_active DESC
           LIMIT 50""",
        (cutoff,)
    ).fetchall()
    db.close()

    penguins = []
    for r in rows:
        job = r["job"]
        home = _BUILDING_HOME_TILES.get(job, _DEFAULT_HOME_TILE)
        penguins.append({
            "username":     r["username"],
            "job":          job,
            "level":        r["level"] or 1,
            "prestige":     r["prestige"] or 0,
            "active_title": r["active_title"],
            "startGridX":   home[0],
            "startGridY":   home[1],
        })

    return jsonify({"penguins": penguins})


# ── BUFFS/ACTIVE (public endpoint for player buff banner) ────────────────────

@app.route("/buffs/active")
def buffs_active():
    db = get_db()
    buffs = get_active_buffs(db)
    db.close()
    now = int(time.time())
    return jsonify({"buffs": [{
        "buff_type":    b["buff_type"],
        "name":         BUFF_NAMES.get(b["buff_type"], b["buff_type"]),
        "expires_at":   b["expires_at"],
        "seconds_left": max(0, b["expires_at"] - now),
    } for b in buffs]})


# ── MAYOR DASHBOARD ──────────────────────────────────────────────────────────

@app.route("/mayor")
def mayor_dashboard():
    if not _is_mayor_authed():
        return redirect(url_for("home"))
    db = get_db()
    now = int(time.time())
    total_players   = db.execute("SELECT COUNT(*) as c FROM penguins").fetchone()["c"]
    online_players  = db.execute(
        "SELECT COUNT(*) as c FROM penguins WHERE last_active > ?", (now - 1800,)
    ).fetchone()["c"]
    active_24h      = db.execute(
        "SELECT COUNT(*) as c FROM penguins WHERE last_active > ?", (now - 86400,)
    ).fetchone()["c"]
    active_buffs    = get_active_buffs(db)
    recent_events   = db.execute(
        "SELECT * FROM event_log ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    building_levels = {}
    for bid in BUILDING_UPGRADES:
        row = db.execute("SELECT current_level FROM building_upgrades WHERE building_id=?", (bid,)).fetchone()
        building_levels[bid] = row["current_level"] if row else 1
    db.close()
    is_live = _stream_is_live()
    return render_template(
        "mayor.html",
        total_players=total_players,
        online_players=online_players,
        active_24h=active_24h,
        active_buffs=active_buffs,
        recent_events=[dict(e) for e in recent_events],
        building_levels=building_levels,
        building_upgrades=BUILDING_UPGRADES,
        buff_names=BUFF_NAMES,
        is_live=is_live,
        mayor_key=MAYOR_KEY,
    )


@app.route("/mayor/stats")
def mayor_stats():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    db  = get_db()
    now = int(time.time())
    total   = db.execute("SELECT COUNT(*) as c FROM penguins").fetchone()["c"]
    online  = db.execute("SELECT COUNT(*) as c FROM penguins WHERE last_active > ?", (now - 1800,)).fetchone()["c"]
    active  = db.execute("SELECT COUNT(*) as c FROM penguins WHERE last_active > ?", (now - 86400,)).fetchone()["c"]
    top5    = db.execute(
        "SELECT username, level, prestige FROM penguins ORDER BY level DESC, prestige DESC LIMIT 5"
    ).fetchall()
    today_events = db.execute(
        "SELECT COUNT(*) as c FROM event_log WHERE created_at > ?", (now - 86400,)
    ).fetchone()["c"]
    buffs   = get_active_buffs(db)
    db.close()
    return jsonify({
        "total_players": total,
        "online_players": online,
        "active_24h": active,
        "is_live": _stream_is_live(),
        "active_buffs": [{
            "buff_type": b["buff_type"],
            "name": BUFF_NAMES.get(b["buff_type"], b["buff_type"]),
            "seconds_left": max(0, b["expires_at"] - now),
        } for b in buffs],
        "top_players": [dict(r) for r in top5],
        "today_events": today_events,
    })


@app.route("/mayor/buff", methods=["POST"])
def mayor_buff():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data     = request.get_json(silent=True) or {}
    buff_type = data.get("buff_type", "").strip()
    duration  = int(data.get("duration_minutes", 30))
    if buff_type not in BUFF_NAMES:
        return jsonify({"status": "error", "message": "Unknown buff type."})
    if duration < 1 or duration > 480:
        return jsonify({"status": "error", "message": "Duration must be 1–480 minutes."})
    now       = int(time.time())
    expires   = now + duration * 60
    db = get_db()
    db.execute(
        "INSERT INTO active_buffs (buff_type, multiplier, activated_at, expires_at, activated_by) VALUES (?,?,?,?,?)",
        (buff_type, 2.0, now, expires, MAYOR_USERNAME)
    )
    log_event(db, "village",
              f"👑 The Mayor activated {BUFF_NAMES[buff_type]} for {duration} minutes!",
              MAYOR_USERNAME)
    db.commit()
    db.close()
    return jsonify({"status": "success", "buff_type": buff_type, "expires_at": expires,
                    "duration_minutes": duration})


@app.route("/mayor/grant-title", methods=["POST"])
def mayor_grant_title():
    if not _is_mayor_authed():
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
        return jsonify({"status": "error", "message": f"Player '{username}' not found."})
    try:
        existing = json.loads(p["ceremonial_titles"] or "[]")
    except Exception:
        existing = []
    if title not in existing:
        existing.append(title)
        db.execute("UPDATE penguins SET ceremonial_titles=? WHERE username=?",
                   (json.dumps(existing), username))
    log_event(db, "village", f"👑 The Mayor granted {username} the title: {title}!", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "username": username, "title": title})


@app.route("/mayor/gift", methods=["POST"])
def mayor_gift():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data       = request.get_json(silent=True) or {}
    username   = data.get("username", "").strip()
    gift_type  = data.get("gift_type", "gold").strip()
    amount     = int(data.get("amount", 0))
    resource_t = data.get("resource_type", "fish").strip()
    cosmetic_n = data.get("cosmetic_name", "").strip()

    db = get_db()
    # Random active player
    if username.lower() == "random":
        cutoff = int(time.time()) - 86400
        rows = db.execute(
            "SELECT username FROM penguins WHERE last_active > ? ORDER BY RANDOM() LIMIT 1", (cutoff,)
        ).fetchall()
        if not rows:
            db.close()
            return jsonify({"status": "error", "message": "No active players in last 24h."})
        username = rows[0]["username"]

    p = db.execute("SELECT id FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": f"Player '{username}' not found."})

    ensure_resources(db, username)
    if gift_type == "gold":
        if amount <= 0:
            db.close(); return jsonify({"status": "error", "message": "Amount must be positive."})
        add_gold(db, username, amount)
        log_event(db, "village", f"👑 The Mayor gifted {amount} gold to {username}! 🪙", username)
    elif gift_type == "seals":
        if amount <= 0:
            db.close(); return jsonify({"status": "error", "message": "Amount must be positive."})
        db.execute("UPDATE resources SET mayor_seals=mayor_seals+? WHERE username=?", (amount, username))
        log_event(db, "village", f"👑 The Mayor gifted {amount} Mayor's Seals to {username}! 👑", username)
    elif gift_type == "resources":
        if resource_t not in ("fish","herbs","blood_gems","bones","spell_fragments"):
            db.close(); return jsonify({"status": "error", "message": "Invalid resource type."})
        if amount <= 0:
            db.close(); return jsonify({"status": "error", "message": "Amount must be positive."})
        db.execute(f"UPDATE resources SET {resource_t}={resource_t}+? WHERE username=?", (amount, username))
        log_event(db, "village", f"👑 The Mayor gifted {amount} {resource_t} to {username}!", username)
    elif gift_type == "cosmetic":
        if not cosmetic_n:
            db.close(); return jsonify({"status": "error", "message": "cosmetic_name required."})
        item_id  = cosmetic_n.lower().replace(" ", "_").replace("'", "")
        slot     = COSMETIC_SLOTS.get(cosmetic_n, "accessory")
        db.execute(
            "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
            "VALUES (?,?,?,'cosmetic',?,'achievement',0,?)",
            (username, item_id, cosmetic_n, slot, int(time.time()))
        )
        log_event(db, "village", f"👑 The Mayor gifted {username} the cosmetic: {cosmetic_n}! ✨", username)
    else:
        db.close(); return jsonify({"status": "error", "message": "Unknown gift type."})

    db.commit()
    db.close()
    return jsonify({"status": "success", "recipient": username, "gift_type": gift_type})


@app.route("/mayor/announce", methods=["POST"])
def mayor_announce():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()[:200]
    if not message:
        return jsonify({"status": "error", "message": "message required."})
    db = get_db()
    log_event(db, "mayor", f"📢 {message}", MAYOR_USERNAME)
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": message})


@app.route("/mayor/blizzard", methods=["POST"])
def mayor_blizzard():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data        = request.get_json(silent=True) or {}
    energy_loss = max(1, min(100, int(data.get("energy_loss", 30))))
    db  = get_db()
    res = db.execute(
        "UPDATE penguins SET energy = MAX(0, energy - ?) WHERE 1=1", (energy_loss,)
    )
    affected = res.rowcount
    log_event(db, "village",
              f"🌨️ A blizzard hit the village! Everyone lost {energy_loss} energy!",
              MAYOR_USERNAME)
    db.commit()
    db.close()
    return jsonify({"status": "success", "energy_loss": energy_loss, "players_affected": affected})


@app.route("/mayor/building-boost", methods=["POST"])
def mayor_building_boost():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data          = request.get_json(silent=True) or {}
    building_id   = data.get("building_id", "").strip()
    resource_type = data.get("resource_type", "").strip()
    amount        = int(data.get("amount", 0))

    cfg = BUILDING_UPGRADES.get(building_id)
    if not cfg:
        return jsonify({"status": "error", "message": "Unknown building."})
    if resource_type not in _RES_COL:
        return jsonify({"status": "error", "message": "Invalid resource."})
    if amount <= 0:
        return jsonify({"status": "error", "message": "Amount must be positive."})

    db = get_db()
    ensure_building_row(db, building_id)
    col = _RES_COL[resource_type]
    db.execute(f"UPDATE building_upgrades SET {col}={col}+? WHERE building_id=?", (amount, building_id))

    # Check if building levels up
    row = db.execute("SELECT * FROM building_upgrades WHERE building_id=?", (building_id,)).fetchone()
    current_level = row["current_level"]
    leveled_up    = False
    while current_level < (row["max_level"] or 5):
        next_level = current_level + 1
        reqs = {k: v for k, v in cfg["levels"][next_level].items() if k != "benefit"}
        donated = {k: (row[_RES_COL[k]] if k in _RES_COL else 0) for k in reqs}
        # re-read row after potential update
        row = db.execute("SELECT * FROM building_upgrades WHERE building_id=?", (building_id,)).fetchone()
        donated = {k: (row[_RES_COL[k]] if k in _RES_COL else 0) for k in reqs}
        if all(donated[k] >= reqs[k] for k in reqs):
            db.execute("UPDATE building_upgrades SET current_level=? WHERE building_id=?",
                       (next_level, building_id))
            log_event(db, "village",
                      f"🏗️ {cfg['name']} has been upgraded to level {next_level}!",
                      MAYOR_USERNAME)
            current_level = next_level
            leveled_up = True
        else:
            break

    log_event(db, "village",
              f"👑 The Mayor boosted {cfg['name']} with {amount} {resource_type}!",
              MAYOR_USERNAME)
    db.commit()
    db.close()
    return jsonify({"status": "success", "building_id": building_id, "leveled_up": leveled_up,
                    "new_level": current_level})


@app.route("/mayor/events")
def mayor_events():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM event_log ORDER BY created_at DESC LIMIT 30"
    ).fetchall()
    db.close()
    return jsonify({"events": [dict(r) for r in rows]})


@app.route("/mayor/lookup")
def mayor_lookup():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"status": "error", "message": "username required."})
    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Player not found."})
    ensure_resources(db, username)
    r  = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    ls = db.execute("SELECT current_streak FROM login_streaks WHERE username=?", (username,)).fetchone()
    db.close()
    return jsonify({
        "status": "ok",
        "player": {
            "username":     p["username"],
            "level":        p["level"] or 1,
            "xp":           p["xp"] or 0,
            "job":          p["job"],
            "prestige":     p["prestige"] or 0,
            "active_title": p["active_title"],
            "energy":       p["energy"] or 0,
            "max_energy":   p["max_energy"] or 100,
            "streak":       ls["current_streak"] if ls else 0,
            "gold":         r["gold"] if r else 0,
            "fish":         r["fish"] if r else 0,
            "herbs":        r["herbs"] if r else 0,
            "mayor_seals":  r["mayor_seals"] if r else 0,
        }
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
