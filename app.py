from dotenv import load_dotenv
import hashlib
import os
import re
import datetime
import random
import sqlite3
from flask import Flask, jsonify, redirect, request, session, url_for, render_template
from database import init_db, get_db, backfill_cosmetics, record_challenge_progress
from feature_flags import FEATURES
from level_config import LEVEL_DATA, get_total_gathering_bonus, get_next_milestone, COSMETIC_SLOTS
from personality_config import (
    SOCIAL_TRAITS, INTEREST_TRAITS, QUIRK_TRAITS, ALL_TRAITS,
    AUTONOMOUS_ACTIONS, CATEGORY_EMOJIS,
    pick_autonomous_action, pick_other_penguin, generate_action_text,
    INTEREST_TOPICS, MAX_INTERESTS, highlight_name,
    GROUP_EVENT_CHANCE_PER_TICK, pick_group_event, format_group_event_text,
)
from raid_config import pick_weekly_metric, pick_boss_name, calculate_attack_damage, cp_damage_bonus, WEEKLY_METRIC_TYPES
from lootbox_config import RESOURCE_TYPES
import raid_settings
import catalog
import math
import time
import requests as http_requests
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _APSCHEDULER_AVAILABLE = True
except ImportError:
    _APSCHEDULER_AVAILABLE = False

load_dotenv()

TWITCH_CLIENT_ID    = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
DISCORD_CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI  = os.getenv("DISCORD_REDIRECT_URI")
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

# ── WORLD AREAS ───────────────────────────────────────────────────────────────
WORLD_AREAS = {
    "penguin_village": {
        "name": "Penguin Village",
        "grid_position": {"row": 1, "col": 1},
        "status": "active",
        "description": "Home sweet home. The heart of the penguin community.",
        "color": "#4aff6b",
        "icon": "🏘️",
        "era": "Era 1"
    },
    "frozen_peaks": {
        "name": "Frozen Peaks",
        "grid_position": {"row": 0, "col": 1},
        "status": "locked",
        "description": "Treacherous mountains hide ancient secrets beneath the ice.",
        "color": "#4a9eff",
        "icon": "🏔️",
        "era": "Era 2",
        "unlock_hint": "Complete Era 1 village goals to unlock"
    },
    "frozen_frontier": {
        "name": "Frozen Frontier",
        "grid_position": {"row": 0, "col": 0},
        "status": "locked",
        "description": "The unexplored north. What lies beyond the blizzard?",
        "color": "#88c8e8",
        "icon": "❄️",
        "era": "Era 3",
        "unlock_hint": "Complete Era 2 to unlock"
    },
    "frozen_wastes": {
        "name": "Frozen Wastes",
        "grid_position": {"row": 0, "col": 2},
        "status": "locked",
        "description": "A barren expanse of eternal winter. Only the brave dare enter.",
        "color": "#B8B8D0",
        "icon": "🌨️",
        "era": "Era 3",
        "unlock_hint": "Complete Era 2 to unlock"
    },
    "western_shores": {
        "name": "Western Shores",
        "grid_position": {"row": 1, "col": 0},
        "status": "locked",
        "description": "Crashing waves and hidden coves. Pirates were spotted here once.",
        "color": "#5B8FA8",
        "icon": "🌊",
        "era": "Era 2",
        "unlock_hint": "Complete Era 1 village goals to unlock"
    },
    "eastern_woods": {
        "name": "Eastern Woods",
        "grid_position": {"row": 1, "col": 2},
        "status": "locked",
        "description": "A dense forest full of mystery. The trees seem to whisper.",
        "color": "#2D5A2D",
        "icon": "🌲",
        "era": "Era 2",
        "unlock_hint": "Complete Era 1 village goals to unlock"
    },
    "sunken_ruins": {
        "name": "Sunken Ruins",
        "grid_position": {"row": 2, "col": 0},
        "status": "locked",
        "description": "An ancient civilization lies beneath the frozen lake.",
        "color": "#3A3A8A",
        "icon": "🏛️",
        "era": "Era 4",
        "unlock_hint": "Complete Era 3 to unlock"
    },
    "southern_shores": {
        "name": "Southern Shores",
        "grid_position": {"row": 2, "col": 1},
        "status": "locked",
        "description": "Warmer waters and sandy beaches. A penguin resort, perhaps?",
        "color": "#D4AC0D",
        "icon": "🏖️",
        "era": "Era 2",
        "unlock_hint": "Complete Era 1 village goals to unlock"
    },
    "the_abyss": {
        "name": "The Abyss",
        "grid_position": {"row": 2, "col": 2},
        "status": "locked",
        "description": "Darkness incarnate. The final frontier. Are you ready?",
        "color": "#4a1a4a",
        "icon": "💀",
        "era": "Era 5",
        "unlock_hint": "Complete Era 4 to unlock"
    }
}

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
            2: {"fish": 2500,  "gold": 1250, "ice_blocks": 5000,  "benefit": "+15% fish rate for everyone"},
            3: {"fish": 12500, "gold": 6250, "ice_blocks": 10000, "benefit": "+30% fish rate for everyone"},
        },
    },
    "club_soda": {
        "name": "Club Soda",
        "levels": {
            2: {"herbs": 2500,  "gold": 1250, "ice_blocks": 5000,  "benefit": "+15% herb rate for everyone"},
            3: {"herbs": 12500, "gold": 6250, "ice_blocks": 10000, "benefit": "+30% herb rate for everyone"},
        },
    },
    "parkmusement": {
        "name": "Ash's Parkmusement",
        "levels": {
            2: {"gold": 3750,  "ice_blocks": 5000,  "benefit": "+15% gold rate for everyone"},
            3: {"gold": 18750, "ice_blocks": 10000, "benefit": "+30% gold rate for everyone"},
        },
    },
    "cursed_temple": {
        "name": "Cursed Temple",
        "levels": {
            2: {"spell_fragments": 2000,  "gold": 1250, "ice_blocks": 5000,  "benefit": "+15% XP rate for everyone"},
            3: {"spell_fragments": 10000, "gold": 6250, "ice_blocks": 10000, "benefit": "+30% XP rate for everyone"},
        },
    },
    "guillotine": {
        "name": "Gil the Guillotine",
        "levels": {
            2: {"blood_gems": 500,  "bones": 500,  "gold": 1250, "ice_blocks": 5000,  "benefit": "+15% blood gem and bone rate for everyone"},
            3: {"blood_gems": 2500, "bones": 2500, "gold": 6250, "ice_blocks": 10000, "benefit": "+30% rate for everyone"},
        },
    },
}

CONTRIBUTION_MILESTONES = {
    100:  {"name": "Contributor's Frame",      "description": "A warm glow for those who give back."},
    500:  {"name": "Builder's Canvas",          "description": "The village remembers your generosity."},
    1000: {"name": "Architect's Backdrop",      "description": "You shaped this village with your own flippers."},
    5000: {"name": "Legendary Founder's Frame", "description": "A living legend of Penguin Village."},
}

BUILDING_CARD_BACKGROUNDS = {
    "sea_lion_pit": {
        "name": "Sea Lion Pit Background",
        "description": "Ocean waves and fishing nets",
        "unlock_amount": 100,
        "image": "card_bg_sea_lion_pit.png",
        "color": "#4a9eff",
        "source": "Ash's Sea Lion Pit",
    },
    "club_soda": {
        "name": "Club Soda Background",
        "description": "Herbs and musical notes",
        "unlock_amount": 100,
        "image": "card_bg_club_soda.png",
        "color": "#4aff6b",
        "source": "Club Soda",
    },
    "parkmusement": {
        "name": "Parkmusement Background",
        "description": "Circus lights and confetti",
        "unlock_amount": 100,
        "image": "card_bg_parkmusement.png",
        "color": "#FF8C00",
        "source": "Ash's Parkmusement",
    },
    "cursed_temple": {
        "name": "Cursed Temple Background",
        "description": "Mystical runes and candles",
        "unlock_amount": 100,
        "image": "card_bg_cursed_temple.png",
        "color": "#A86EFF",
        "source": "Cursed Temple",
    },
    "guillotine": {
        "name": "Gil's Workshop Background",
        "description": "Dark steel and crimson gems",
        "unlock_amount": 100,
        "image": "card_bg_guillotine.png",
        "color": "#ff6b6b",
        "source": "Gil the Guillotine",
    },
    "hotel": {
        "name": "Hotel Lounge Background",
        "description": "Cozy fireplace and warm lights",
        "unlock_amount": 100,
        "image": "card_bg_hotel.png",
        "color": "#C0392B",
        "source": "Penguin Hotel",
    },
}

BUILDING_BONUS_RATES = {1: 0.0, 2: 0.15, 3: 0.30}

STARTER_COLORS = {
    "classic_black":  {"name": "Classic Black",   "body": "#1a1a1a", "belly": "#e8e8e8", "beak": "#FF8C00", "feet": "#FF8C00"},
    "midnight_blue":  {"name": "Midnight Blue",   "body": "#1a1a4e", "belly": "#c8c8e8", "beak": "#FF8C00", "feet": "#FF8C00"},
    "forest_green":   {"name": "Forest Green",    "body": "#1a3a1a", "belly": "#c8e8c8", "beak": "#FF8C00", "feet": "#FF8C00"},
    "deep_red":       {"name": "Deep Red",        "body": "#4a1a1a", "belly": "#e8c8c8", "beak": "#FF8C00", "feet": "#FF8C00"},
    "warm_brown":     {"name": "Warm Brown",      "body": "#3a2a1a", "belly": "#e8d8c8", "beak": "#FF8C00", "feet": "#FF8C00"},
    "steel_gray":     {"name": "Steel Gray",      "body": "#3a3a3a", "belly": "#d8d8d8", "beak": "#FF8C00", "feet": "#FF8C00"},
}

LOCKED_COLORS = {
    "arctic_white":   {"name": "Arctic White",    "unlock": "Prestige 1",          "body": "#e8e8e8", "belly": "#FFFFFF", "beak": "#FF8C00", "feet": "#FF8C00"},
    "royal_blue":     {"name": "Royal Blue",      "unlock": "Prestige 2",          "body": "#1a3a8a", "belly": "#a8c8ff", "beak": "#ffd700", "feet": "#ffd700"},
    "golden_emperor": {"name": "Golden Emperor",  "unlock": "Prestige 3",          "body": "#8a6a1a", "belly": "#fff0c8", "beak": "#ffd700", "feet": "#ffd700"},
    "shadow_purple":  {"name": "Shadow Purple",   "unlock": "Defeat 100 monsters", "body": "#3a1a4a", "belly": "#c8a8d8", "beak": "#A86EFF", "feet": "#A86EFF"},
    "frost_crystal":  {"name": "Frost Crystal",   "unlock": "Reach Level 30",      "body": "#88c8e8", "belly": "#e8f8ff", "beak": "#4a9eff", "feet": "#4a9eff"},
    "neon_pink":      {"name": "Neon Pink",        "unlock": "Twitch Subscriber",   "body": "#cc3a7a", "belly": "#ffb8d8", "beak": "#FF7FE5", "feet": "#FF7FE5"},
}

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

def _resolve_hex_color(pcolor):
    """Return a hex body color whether given a hex string or legacy palette key."""
    if pcolor and _HEX_RE.match(pcolor):
        return pcolor
    palette = STARTER_COLORS.get(pcolor) or LOCKED_COLORS.get(pcolor)
    if palette:
        return palette.get("body", "#1a1a1a")
    return "#1a1a1a"


# BOUTIQUE_ITEMS and BARRACKS_SHOP used to be dict literals here; both are
# now DB-backed via catalog.load_boutique_items()/catalog.load_barracks_shop()
# (see catalog.py for the full design-rationale notes preserved from the old
# BARRACKS_SHOP literal's comments, and migrate_catalog_tables.py for the
# one-time seed that populated the boutique_items/barracks_shop tables from
# those literals' exact original values).

# resource column name in building_upgrades table
_RES_COL = {
    "fish": "fish_donated", "herbs": "herbs_donated", "gold": "gold_donated",
    "blood_gems": "blood_gems_donated", "bones": "bones_donated",
    "spell_fragments": "spell_fragments_donated", "ice_blocks": "ice_blocks_donated",
}

# Player-facing display names for resource keys whose raw internal key doesn't
# read naturally (currently only ice_blocks -- other resource keys already
# read fine as-is). Internal identifiers (DB columns, _RES_COL, event types)
# are untouched; this only affects text shown to players.
_RESOURCE_DISPLAY_NAMES = {"ice_blocks": "Ice Blocks"}


def _resource_display_name(resource_type):
    return _RESOURCE_DISPLAY_NAMES.get(resource_type, resource_type)


# ── Events tab sub-tab mapping ────────────────────────────────────────────────
# Maps every event_type currently written to event_log onto one of the four
# Events-tab buckets. "donation" and "building_levelup" were split out of the
# old catch-all "village" type (which also covered joins, streaks, mayor
# gifts, etc.) specifically so donations and building level-ups could be
# told apart from everything else -- see log_event call sites for "donation",
# "level_up" and "building_levelup". "milestone" (card background/frame
# unlocks for cumulative donation totals) is an approximation: it's donation-
# adjacent but not a donation itself, mapped to Donations as the closest fit.
# Anything not listed here (including any future event_type) falls back to
# Activities via _EVENT_BUCKET_DEFAULT rather than raising or disappearing.
_EVENT_BUCKET_DEFAULT = "activities"
_EVENT_TYPE_BUCKETS = {
    "donation":         "donations",
    "milestone":        "donations",   # approximate -- see comment above
    "combat":           "combat",
    "level_up":         "levelups",
    "building_levelup": "levelups",
}


def _event_bucket(event_type):
    return _EVENT_TYPE_BUCKETS.get(event_type, _EVENT_BUCKET_DEFAULT)


# ── Global chat ──────────────────────────────────────────────────────────────
_CHAT_RATE_LIMIT_SECONDS = 5   # one message per N seconds per player
# Hardcoded wordlist — expandable; basic bad-word filter applied on send
_CHAT_BLOCKED_WORDS = frozenset({
    'fuck', 'shit', 'bitch', 'cunt', 'dick', 'cock', 'pussy',
    'nigger', 'nigga', 'fag', 'faggot', 'retard', 'whore', 'slut',
    'kike', 'chink', 'spic',
})

def _chat_has_profanity(text):
    import re as _re
    words = _re.findall(r'\w+', text.lower())
    return any(w in _CHAT_BLOCKED_WORDS for w in words)

# Maps gear slot → visual area (for WEAR system: one item shown per area)
_VISUAL_AREA = {
    "helmet": "head",   "hat":       "head",
    "armor":  "body",   "outfit":    "body",
    "boots":  "feet",   "footwear":  "feet",
    "weapon": "hand",   "accessory": "hand",
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
JOB_CAP_HOURS = 12.0

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
    "bank": {
        "name": "Penguin Bank", "icon": "🏦",
        "desc": "Coming soon. Your savings are definitely safe here.",
        "type": "placeholder",
        "pos": {"x": 11, "y": 15},
    },
}

# ── SOCIAL SYSTEM ─────────────────────────────────────────────────────────────
SOCIAL_MODES = {
    "social": {
        "name": "Be Social", "emoji": "🤝",
        "description": "Your penguin interacts with everyone freely",
        "interaction_chance": 0.7, "target_bias": 0,
    },
    "homebody": {
        "name": "Stay Home", "emoji": "🏠",
        "description": "Your penguin prefers alone time and solo activities",
        "interaction_chance": 0.3, "target_bias": 0,
    },
    "focused": {
        "name": "Focus on Someone", "emoji": "🎯",
        "description": "Your penguin seeks out a specific penguin more often",
        "interaction_chance": 0.6, "target_bias": 0.6,
    },
}

RELATIONSHIP_LEVELS = [
    {"level": "stranger",         "emoji": "❓", "threshold": 0,   "next": "acquaintance",    "next_threshold": 1},
    {"level": "acquaintance",     "emoji": "👋", "threshold": 1,   "next": "friend",          "next_threshold": 10},
    {"level": "friend",           "emoji": "🤝", "threshold": 10,  "next": "village_comrade", "next_threshold": 25},
    {"level": "village_comrade",  "emoji": "💛", "threshold": 25,  "next": "trusted_flippers","next_threshold": 50},
    {"level": "trusted_flippers", "emoji": "⭐", "threshold": 50,  "next": "penguin_mbare",   "next_threshold": 100},
    {"level": "penguin_mbare",    "emoji": "👑", "threshold": 100, "next": None,              "next_threshold": None},
]

RELATIONSHIP_DISPLAY = {
    "stranger":         {"name": "Stranger",         "emoji": "❓", "raid_cp_bonus": 0},
    "acquaintance":     {"name": "Acquaintance",     "emoji": "👋", "raid_cp_bonus": 1},
    "friend":           {"name": "Friend",           "emoji": "🤝", "raid_cp_bonus": 2},
    "village_comrade":  {"name": "Village Comrade",  "emoji": "💛", "raid_cp_bonus": 3},
    "trusted_flippers": {"name": "Trusted Flippers", "emoji": "⭐", "raid_cp_bonus": 4},
    "penguin_mbare":    {"name": "Mbarepingu",       "emoji": "👑", "raid_cp_bonus": 5},
    "rivalry":          {"name": "Rivalry",          "emoji": "⚡", "raid_cp_bonus": 0},
    "crush":            {"name": "Crush",            "emoji": "💘", "raid_cp_bonus": 0},
    "mentor":           {"name": "Mentor",           "emoji": "📚", "raid_cp_bonus": 0},
}

IGLOO_VISIT_REWARDS = {
    "stranger":         {"gold_min": 5,  "gold_max": 10, "res_min": 1, "res_max": 1, "xp": 5},
    "acquaintance":     {"gold_min": 8,  "gold_max": 12, "res_min": 1, "res_max": 2, "xp": 5},
    "friend":           {"gold_min": 10, "gold_max": 15, "res_min": 2, "res_max": 3, "xp": 5},
    "village_comrade":  {"gold_min": 12, "gold_max": 18, "res_min": 2, "res_max": 3, "xp": 8},
    "trusted_flippers": {"gold_min": 15, "gold_max": 25, "res_min": 3, "res_max": 5, "xp": 10},
    "penguin_mbare":    {"gold_min": 20, "gold_max": 35, "res_min": 4, "res_max": 7, "xp": 15},
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

# Per-tier monster CP bands: (easiest_cp, hardest_cp). Tune during
# balance-pass -- target-curve solve 2026-07-17. These are SOLVED, not
# hand-picked: per bracket, the hardest monster's CP satisfies "~30% win at
# the bracket's entry level, ~90% by its last level" and the easiest targets
# "~85% at entry", against realistic total CP (base 10+level*3 plus expected
# gear CP simulated from the real drop/XP systems and calibrated to the
# measured 121-total-CP-at-level-8 data point). Bracket entry->exit total CP:
#   T1 L1->L4:   13 -> 50    T2 L5->L9:  70 -> 135   T3 L10->L14: 152 -> 196
#   T4 L15->L24: 205 -> 269  T5 L25->L30: 273 -> 289
# Solved with the per-tier slope in WIN_CHANCE_TIER_STEEPNESS (see there for
# why the slope had to become tier-dependent): hardest = entry + 20/K,
# easiest = entry - 35/K. Tier 1's easiest clamps at CP 5 (hitting 85% for a
# 13-CP fresh player would need negative monster CP), giving 63% at entry --
# the one target that isn't exactly met, flagged rather than hidden.
# Individual combat_power values below are evenly spaced within these bands,
# preserving each tier's original easiest->hardest monster ordering.
MONSTER_TIER_CP_BANDS = {
    1: (5, 25),     # levels 1-4   (7 monsters)
    2: (32, 92),    # levels 5-9   (7 monsters)
    3: (126, 167),  # levels 10-14 (7 monsters)
    4: (168, 227),  # levels 15-24 (6 monsters)
    5: (264, 278),  # levels 25-30 (4 monsters)
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
        "tier": 1, "min_level": 1, "combat_power": 25,
        "variants": ["Ice Bat", "Cave Bat", "Frost Wing"],
        "energy_cost": 25,
        "rewards": {"gold": [40, 90], "xp": [36, 66], "resources": {"herbs": [20, 40]}, "gear_drop_chance": 0.25},
    },
    "rat": {
        "tier": 1, "min_level": 1, "combat_power": 5,
        "variants": ["Frost Rat", "Sewer Rat", "Snow Mouse"],
        "energy_cost": 25,
        "rewards": {"gold": [25, 75], "xp": [30, 60], "resources": {"bones": [10, 30]}, "gear_drop_chance": 0.20},
    },
    "shell_lurker": {
        "tier": 1, "min_level": 1, "combat_power": 12,
        "variants": ["Tide Shell", "Giant Conch", "Lurking Shell"],
        "energy_cost": 25,
        "rewards": {"gold": [40, 90], "xp": [36, 66], "resources": {"fish": [10, 40]}, "gear_drop_chance": 0.20},
    },
    "ice_squid": {
        "tier": 1, "min_level": 1, "combat_power": 18,
        "variants": ["Baby Squid", "Frost Squid", "Ink Specter"],
        "energy_cost": 25,
        "rewards": {"gold": [50, 90], "xp": [36, 66], "resources": {"fish": [20, 40], "herbs": [10, 20]}, "gear_drop_chance": 0.20},
    },
    "frost_beetle": {
        "tier": 1, "min_level": 1, "combat_power": 8,
        "variants": ["Tunnel Bug", "Ice Crawler", "Crystal Grub"],
        "energy_cost": 25,
        "rewards": {"gold": [30, 70], "xp": [30, 60], "resources": {"bones": [10, 20]}, "gear_drop_chance": 0.20},
    },
    "pufferfish": {
        "tier": 1, "min_level": 1, "combat_power": 22,
        "variants": ["Toxic Puffer", "Spiky Fish", "Blowfish"],
        "energy_cost": 25,
        "rewards": {"gold": [40, 80], "xp": [36, 66], "resources": {"fish": [20, 50], "herbs": [10, 20]}, "gear_drop_chance": 0.25},
    },
    # ── TIER 2 — FROZEN FRONTIER (level 6) ───────────────────────────────────
    "wolf": {
        "tier": 2, "min_level": 5, "combat_power": 42,
        "variants": ["Blizzard Wolf", "Shadow Wolf", "Arctic Dire Wolf"],
        "energy_cost": 25,
        "rewards": {"gold": [100, 200], "xp": [90, 150], "resources": {"bones": [30, 60], "blood_gems": [10, 20]}, "gear_drop_chance": 0.20},
    },
    "snowman": {
        "tier": 2, "min_level": 5, "combat_power": 82,
        "variants": ["Cursed Snowman", "Frost Golem", "Ice Construct"],
        "energy_cost": 25,
        "rewards": {"gold": [110, 210], "xp": [96, 156], "resources": {"spell_fragments": [20, 40]}, "gear_drop_chance": 0.18},
    },
    "shadow_penguin": {
        "tier": 2, "min_level": 5, "combat_power": 72,
        "variants": ["Shadow Penguin", "Dark Penguin", "Void Waddle"],
        "energy_cost": 25,
        "rewards": {"gold": [110, 190], "xp": [84, 144], "resources": {"blood_gems": [20, 40]}, "gear_drop_chance": 0.22},
    },
    "ice_hawk": {
        "tier": 2, "min_level": 5, "combat_power": 32,
        "variants": ["Storm Hawk", "Tundra Raptor", "Frozen Eagle"],
        "energy_cost": 25,
        "rewards": {"gold": [90, 180], "xp": [84, 135], "resources": {"herbs": [30, 60]}, "gear_drop_chance": 0.20},
    },
    "frost_scorpion": {
        "tier": 2, "min_level": 5, "combat_power": 62,
        "variants": ["Ice Stinger", "Polar Pincer", "Frost Venom"],
        "energy_cost": 25,
        "rewards": {"gold": [100, 190], "xp": [90, 144], "resources": {"blood_gems": [10, 30], "bones": [20, 40]}, "gear_drop_chance": 0.18},
    },
    "snow_bear": {
        "tier": 2, "min_level": 5, "combat_power": 92,
        "variants": ["Snowfield Cub", "Frost Grizzly", "Avalanche Bear"],
        "energy_cost": 25,
        "rewards": {"gold": [125, 225], "xp": [105, 165], "resources": {"bones": [40, 80]}, "gear_drop_chance": 0.18},
    },
    "frost_wraith": {
        "tier": 2, "min_level": 5, "combat_power": 52,
        "variants": ["Ice Spirit", "Chilling Specter", "Pale Phantom"],
        "energy_cost": 25,
        "rewards": {"gold": [110, 200], "xp": [90, 150], "resources": {"spell_fragments": [10, 30]}, "gear_drop_chance": 0.22},
    },
    # ── TIER 3 — SHADOW TERRITORY (level 11) ─────────────────────────────────
    "ice_spider": {
        "tier": 3, "min_level": 10, "combat_power": 133,
        "variants": ["Web Creeper", "Frost Widow", "Icy Spinner"],
        "energy_cost": 25,
        "rewards": {"gold": [175, 300], "xp": [120, 195], "resources": {"herbs": [40, 80], "bones": [30, 50]}, "gear_drop_chance": 0.15},
    },
    "frost_shark": {
        "tier": 3, "min_level": 10, "combat_power": 146,
        "variants": ["Glacier Fin", "Deep Frostbite", "Ice Jaw"],
        "energy_cost": 25,
        "rewards": {"gold": [190, 310], "xp": [126, 204], "resources": {"fish": [60, 120]}, "gear_drop_chance": 0.15},
    },
    "tundra_boar": {
        "tier": 3, "min_level": 10, "combat_power": 126,
        "variants": ["Frozen Tusker", "Blizzard Hog", "Snow Crusher"],
        "energy_cost": 25,
        "rewards": {"gold": [165, 290], "xp": [114, 186], "resources": {"bones": [50, 90]}, "gear_drop_chance": 0.15},
    },
    "living_iceblock": {
        "tier": 3, "min_level": 10, "combat_power": 160,
        "variants": ["Frostcube", "Crystalline Mass", "Cryo Entity"],
        "energy_cost": 25,
        "rewards": {"gold": [200, 325], "xp": [135, 210], "resources": {"spell_fragments": [30, 50]}, "gear_drop_chance": 0.14},
    },
    "cursed_owl": {
        "tier": 3, "min_level": 10, "combat_power": 140,
        "variants": ["Night Eye", "Shadow Talon", "Hexed Feather"],
        "energy_cost": 25,
        "rewards": {"gold": [175, 300], "xp": [126, 195], "resources": {"spell_fragments": [20, 50], "herbs": [30, 60]}, "gear_drop_chance": 0.16},
    },
    "glacier_croc": {
        "tier": 3, "min_level": 10, "combat_power": 153,
        "variants": ["Tundra Jaws", "Frost Maw", "Ice Scale"],
        "energy_cost": 25,
        "rewards": {"gold": [190, 315], "xp": [129, 201], "resources": {"fish": [50, 100], "bones": [30, 60]}, "gear_drop_chance": 0.14},
    },
    "night_stalker": {
        "tier": 3, "min_level": 10, "combat_power": 167,
        "variants": ["Shadow Creeper", "Dusk Hunter", "Void Walker"],
        "energy_cost": 25,
        "rewards": {"gold": [200, 325], "xp": [135, 210], "resources": {"blood_gems": [30, 60]}, "gear_drop_chance": 0.15},
    },
    # ── TIER 4 — CURSED DEPTHS (level 16) ────────────────────────────────────
    "golem": {
        "tier": 4, "min_level": 15, "combat_power": 180,
        "variants": ["Stone Golem", "Crystal Golem", "Ancient Guardian"],
        "energy_cost": 25,
        "rewards": {"gold": [275, 425], "xp": [180, 270], "resources": {"bones": [60, 120], "blood_gems": [30, 60]}, "gear_drop_chance": 0.12},
    },
    "serpent": {
        "tier": 4, "min_level": 15, "combat_power": 203,
        "variants": ["Sea Serpent", "Ice Wyrm", "Frost Leviathan"],
        "energy_cost": 25,
        "rewards": {"gold": [290, 450], "xp": [186, 285], "resources": {"fish": [80, 150], "spell_fragments": [30, 50]}, "gear_drop_chance": 0.12},
    },
    "druid": {
        "tier": 4, "min_level": 15, "combat_power": 168,
        "variants": ["Dark Druid", "Cursed Shaman", "Shadow Priest"],
        "energy_cost": 25,
        "rewards": {"gold": [275, 425], "xp": [186, 276], "resources": {"spell_fragments": [50, 90], "herbs": [50, 90]}, "gear_drop_chance": 0.14},
    },
    "ice_drake": {
        "tier": 4, "min_level": 15, "combat_power": 215,
        "variants": ["Frost Whelp", "Arctic Drake", "Glacial Serpent"],
        "energy_cost": 25,
        "rewards": {"gold": [300, 475], "xp": [195, 300], "resources": {"blood_gems": [40, 80], "spell_fragments": [20, 40]}, "gear_drop_chance": 0.12},
    },
    "fallen_knight": {
        "tier": 4, "min_level": 15, "combat_power": 192,
        "variants": ["Lost Paladin", "Cursed Champion", "Hollow Warden"],
        "energy_cost": 25,
        "rewards": {"gold": [290, 460], "xp": [186, 285], "resources": {"bones": [50, 100], "blood_gems": [20, 50]}, "gear_drop_chance": 0.12},
    },
    "blizzard_elemental": {
        "tier": 4, "min_level": 15, "combat_power": 227,
        "variants": ["Storm Core", "Blizzard Wraith", "Polar Force"],
        "energy_cost": 25,
        "rewards": {"gold": [310, 490], "xp": [195, 300], "resources": {"spell_fragments": [40, 80]}, "gear_drop_chance": 0.12},
    },
    # ── TIER 5 — THE ABYSS (level 26) ────────────────────────────────────────
    "elite_frostbear": {
        "tier": 5, "min_level": 25, "combat_power": 264,
        "variants": ["Frostbear Alpha", "Glacial Ursine", "Permafrost Beast"],
        "energy_cost": 25,
        "rewards": {"gold": [450, 700], "xp": [270, 420], "resources": {"blood_gems": [60, 120], "bones": [80, 150]}, "gear_drop_chance": 0.10},
    },
    "frost_demon": {
        "tier": 5, "min_level": 25, "combat_power": 269,
        "variants": ["Frost Wraith Lord", "Infernal Ice", "Arctic Demon"],
        "energy_cost": 25,
        "rewards": {"gold": [500, 750], "xp": [300, 450], "resources": {"blood_gems": [80, 140], "spell_fragments": [50, 100]}, "gear_drop_chance": 0.10},
    },
    "ancient_wyrm": {
        "tier": 5, "min_level": 25, "combat_power": 273,
        "variants": ["Void Dragon", "Ancient Serpent", "Deep Abyss"],
        "energy_cost": 25,
        "rewards": {"gold": [550, 800], "xp": [330, 495], "resources": {"spell_fragments": [80, 150], "blood_gems": [50, 100]}, "gear_drop_chance": 0.08},
    },
    "deaths_herald": {
        "tier": 5, "min_level": 25, "combat_power": 278,
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

# ── GEAR DROP TEMPLATES ───────────────────────────────────────────────────────
# GEAR_TEMPLATES used to be a dict literal here -- now DB-backed via
# catalog.load_gear_templates() (see catalog.py / migrate_catalog_tables.py).

_GEAR_DROP_RARITY_WEIGHTS = {
    1: {"common": 70, "uncommon": 25, "rare": 5,  "epic": 0,  "legendary": 0},
    2: {"common": 40, "uncommon": 40, "rare": 15, "epic": 5,  "legendary": 0},
    3: {"common": 15, "uncommon": 35, "rare": 35, "epic": 14, "legendary": 1},
    4: {"common": 5,  "uncommon": 20, "rare": 40, "epic": 30, "legendary": 5},
    5: {"common": 0,  "uncommon": 10, "rare": 25, "epic": 40, "legendary": 25},
}

# ── SET BONUSES ───────────────────────────────────────────────────────────────
# SET_BONUSES used to be a dict literal here -- now DB-backed via
# catalog.load_set_bonuses() (see catalog.py / migrate_catalog_tables.py).
# COSMETIC_SET_BONUSES below is a separate, differently-shaped dict that was
# NOT part of that migration and stays a literal.

COSMETIC_SET_BONUSES = {
    "Street Style": {
        "required_items": ["Baseball Cap", "Plain T-Shirt", "Sneakers"],
        "bonus": {"gold_per_hour": 2, "description": "+2 gold/hr passive income"},
        "secret": True,
    },
    "Fancy Night Out": {
        "required_items": ["Top Hat", "Full Tuxedo", "Cowboy Boots"],
        "bonus": {"gold_per_hour": 5, "description": "+5 gold/hr passive income"},
        "secret": True,
    },
    "Beach Day": {
        "required_items": ["Party Hat", "Hawaiian Shirt", "Sandals"],
        "bonus": {"fish_per_hour": 1, "description": "+1 fish/hr passive gathering"},
        "secret": True,
    },
    "Mystic Wanderer": {
        "required_items": ["Beret", "Lab Coat", "Rain Boots"],
        "bonus": {"spell_fragments_per_hour": 1, "description": "+1 spell fragment/hr"},
        "secret": True,
    },
    "Dark Lord": {
        "required_items": ["Viking Helmet", "Leather Jacket", "Cowboy Boots"],
        "bonus": {"blood_gems_per_hour": 1, "description": "+1 blood gem/hr"},
        "secret": True,
    },
    "Village Hero": {
        "required_items": ["Village Bandana", "Superhero Cape", "Roller Skates"],
        "bonus": {"xp_per_hour": 3, "description": "+3 XP/hr passive"},
        "secret": True,
    },
    "Royal Penguin": {
        "required_items": ["Pirate Hat", "Tuxedo Vest", "Gold Chain"],
        "bonus": {"gold_per_hour": 8, "description": "+8 gold/hr"},
        "secret": True,
    },
    "Ultimate Collector": {
        "required_items": ["Dragon Wings", "Full Tuxedo", "Monocle"],
        "bonus": {
            "gold_per_hour": 10, "fish_per_hour": 1, "herbs_per_hour": 1,
            "bones_per_hour": 1, "blood_gems_per_hour": 1, "spell_fragments_per_hour": 1,
            "description": "+10 gold/hr, +1 all resources/hr",
        },
        "secret": True,
    },
}

# ── ACHIEVEMENT DEFINITIONS ───────────────────────────────────────────────────
ACHIEVEMENT_DEFS = {
    "first_login":    {"title":"WELCOME HOME",      "desc":"Log in for the first time",         "icon":"🐧", "category":"village",     "reward":{"gold":50}},
    "first_job":      {"title":"CLOCK IN",          "desc":"Complete your first job",           "icon":"⚒️", "category":"jobs",        "reward":{"gold":50}},
    "first_fight":    {"title":"BRAVE (OR DUMB)",   "desc":"Fight your first monster",          "icon":"⚔️", "category":"combat",      "reward":{"gold":75}},
    "first_kill":     {"title":"MONSTER SLAYER",    "desc":"Defeat your first monster",         "icon":"💀", "category":"combat",      "reward":{"gold":100, "gear_tier":1}},
    "level_5":        {"title":"RISING STAR",       "desc":"Reach level 5",                     "icon":"⭐", "category":"village",     "reward":{"gold":150}},
    "level_10":       {"title":"VILLAGE LEGEND",    "desc":"Reach level 10",                    "icon":"🌟", "category":"village",     "reward":{"gold":300, "gear_tier":1}},
    "level_20":       {"title":"SEASONED VETERAN",  "desc":"Reach level 20",                    "icon":"💫", "category":"village",     "reward":{"gold":750, "gear_tier":2}},
    "gold_500":       {"title":"GETTING PAID",      "desc":"Accumulate 500 gold",               "icon":"💰", "category":"collection",  "reward":{"gold":100}},
    "gold_5000":      {"title":"MONEY PENGUIN",     "desc":"Accumulate 5000 gold total",        "icon":"🤑", "category":"collection",  "reward":{"gold":300}},
    "fish_50":        {"title":"FISHER PENGUIN",    "desc":"Collect 50 fish",                   "icon":"🎣", "category":"jobs",        "reward":{"gold":100}},
    "fish_500":       {"title":"MASTER FISHER",     "desc":"Collect 500 fish",                  "icon":"🐟", "category":"jobs",        "reward":{"gold":250}},
    "kill_10":        {"title":"HUNTER",            "desc":"Defeat 10 monsters",                "icon":"🏹", "category":"combat",      "reward":{"gold":150, "gear_tier":1}},
    "kill_50":        {"title":"VETERAN HUNTER",    "desc":"Defeat 50 monsters",                "icon":"🗡️", "category":"combat",      "reward":{"gold":400, "gear_tier":2}},
    "igloo_5":        {"title":"HOME SWEET IGLOO",  "desc":"Place 5 items in your igloo",       "icon":"🏠", "category":"village",     "reward":{"gold":100}},
    "streak_7":       {"title":"DEDICATED",         "desc":"Log in 7 days in a row",            "icon":"🔥", "category":"village",     "reward":{"gold":200}},
    "streak_30":      {"title":"COMMITTED",         "desc":"Log in 30 days in a row",           "icon":"🔥", "category":"village",     "reward":{"gold":500}},
    "prestige_1":         {"title":"REBORN",            "desc":"Prestige for the first time",         "icon":"♻️", "category":"prestige", "reward":{"gold":1000, "gear_tier":3}},
    "first_igloo_visit":  {"title":"WARM WELCOME",     "desc":"Visit your first igloo",              "icon":"🏠", "category":"social",   "reward":{"gold":50}},
    "social_butterfly":   {"title":"SOCIAL BUTTERFLY", "desc":"Visit 50 igloos total",               "icon":"🦋", "category":"social",   "reward":{"gold":250}},
    "best_friends_forever":{"title":"BFF",             "desc":"Reach Best Friend with any penguin",  "icon":"⭐", "category":"social",   "reward":{"gold":300}},
    "popular_penguin":    {"title":"POPULAR PENGUIN",  "desc":"Receive 20 igloo visits",             "icon":"🎉", "category":"social",   "reward":{"gold":200}},
    "village_socialite":  {"title":"THE SOCIALITE",    "desc":"Have 10+ relationships at Friend+",   "icon":"🌟", "category":"social",   "reward":{"gold":400}},
    "lb_top20": {"title":"RISING STAR",     "desc":"Reach top 20 in any leaderboard category", "icon":"📊", "category":"leaderboard"},
    "lb_top10": {"title":"CONTENDER",       "desc":"Reach top 10 in any leaderboard category",  "icon":"🏆", "category":"leaderboard"},
    "lb_top3":  {"title":"CHAMPION",        "desc":"Reach top 3 in any leaderboard category",   "icon":"🥇", "category":"leaderboard"},
    "lb_first": {"title":"VILLAGE LEGEND",  "desc":"Reach #1 in any leaderboard category",      "icon":"👑", "category":"leaderboard"},
}

# ── IGLOO SYSTEM ──────────────────────────────────────────────────────────────

IGLOO_LEVELS = {
    1: {"size": 6,  "name": "Cozy Corner",     "cost": None},
    2: {"size": 8,  "name": "Comfortable Room", "cost": {"gold": 500, "fish": 200}},
    3: {"size": 10, "name": "Spacious Lodge",   "cost": {"gold": 2000, "herbs": 500}},
    4: {"size": 12, "name": "Grand Hall",       "cost": {"gold": 5000}},
}

FLOOR_TYPES = {
    "ice":    {"name": "Ice Floor",   "color": "#b8d8e8", "cost": None},
    "wood":   {"name": "Wood Floor",  "color": "#8B7355", "cost": {"gold": 300}},
    "stone":  {"name": "Stone Floor", "color": "#888888", "cost": {"gold": 500}},
    "carpet": {"name": "Red Carpet",  "color": "#8B2252", "cost": {"gold": 1000}},
    "marble": {"name": "Marble Floor","color": "#e8e8e8", "cost": {"gold": 2500}},
    "dark":   {"name": "Dark Wood",   "color": "#3a2a1a", "cost": {"gold": 1500}},
}

WALL_TYPES = {
    "snow":       {"name": "Snow Walls",   "color": "#e0e8f0", "cost": None},
    "wood":       {"name": "Wooden Walls", "color": "#a0784a", "cost": {"gold": 300}},
    "brick":      {"name": "Brick Walls",  "color": "#8B4513", "cost": {"gold": 800}},
    "crystal":    {"name": "Crystal Walls","color": "#88c8e8", "cost": {"gold": 2000}},
    "dark_stone": {"name": "Dark Stone",   "color": "#4a4a4a", "cost": {"gold": 1500}},
}

IGLOO_FURNITURE = {
    "small_table":        {"name": "Small Table",        "width": 1, "height": 1, "cost": {"gold": 100},  "category": "furniture"},
    "wooden_chair":       {"name": "Wooden Chair",       "width": 1, "height": 1, "cost": {"gold": 80},   "category": "furniture"},
    "rug_small":          {"name": "Small Rug",          "width": 2, "height": 2, "cost": {"gold": 150},  "category": "decor"},
    "candle":             {"name": "Candle",             "width": 1, "height": 1, "cost": {"gold": 50},   "category": "decor"},
    "bookshelf":          {"name": "Bookshelf",          "width": 2, "height": 1, "cost": {"gold": 200},  "category": "furniture"},
    "potted_plant":       {"name": "Potted Plant",       "width": 1, "height": 1, "cost": {"gold": 120},  "category": "decor"},
    "bed":                {"name": "Bed",                "width": 2, "height": 2, "cost": {"gold": 400},  "category": "furniture"},
    "fireplace":          {"name": "Fireplace",          "width": 2, "height": 1, "cost": {"gold": 500},  "category": "furniture"},
    "fish_tank":          {"name": "Fish Tank",          "width": 2, "height": 1, "cost": {"gold": 350, "fish": 50},   "category": "decor"},
    "painting":           {"name": "Painting",           "width": 1, "height": 1, "cost": {"gold": 300},  "category": "decor"},
    "lamp":               {"name": "Floor Lamp",         "width": 1, "height": 1, "cost": {"gold": 200},  "category": "decor"},
    "desk":               {"name": "Writing Desk",       "width": 2, "height": 1, "cost": {"gold": 350},  "category": "furniture"},
    "wardrobe":           {"name": "Wardrobe",           "width": 2, "height": 1, "cost": {"gold": 400},  "category": "furniture"},
    "rug_large":          {"name": "Large Rug",          "width": 3, "height": 3, "cost": {"gold": 500},  "category": "decor"},
    "throne":             {"name": "Throne",             "width": 2, "height": 2, "cost": {"gold": 2000}, "category": "furniture"},
    "grand_piano":        {"name": "Grand Piano",        "width": 3, "height": 2, "cost": {"gold": 3000}, "category": "furniture"},
    "fountain":           {"name": "Indoor Fountain",    "width": 2, "height": 2, "cost": {"gold": 2500, "spell_fragments": 50}, "category": "decor"},
    "trophy_case":        {"name": "Trophy Case",        "width": 2, "height": 1, "cost": {"gold": 1500}, "category": "furniture"},
    "crystal_chandelier": {"name": "Crystal Chandelier", "width": 1, "height": 1, "cost": {"gold": 4000, "spell_fragments": 100}, "category": "decor"},
    "mayors_portrait":    {"name": "Mayor's Portrait",   "width": 1, "height": 1, "cost": None, "category": "special", "source": "Mayor gift"},
    "golden_fish":        {"name": "Golden Fish Trophy", "width": 1, "height": 1, "cost": None, "category": "special", "source": "500 fish collected"},
    "combat_banner":      {"name": "Combat Banner",      "width": 1, "height": 2, "cost": None, "category": "special", "source": "50 monsters defeated"},
}


def _ensure_igloo(db, username):
    db.execute("INSERT OR IGNORE INTO igloos (username) VALUES (?)", (username,))


def _igloo_overlaps(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

# ── SEAL SHOP ─────────────────────────────────────────────────────────────────
SEAL_SHOP = [
    {"id": "royal_crown",         "name": "Royal Crown",          "cost": 50,  "slot": "hat",         "description": "A crown fit for stream royalty."},
    {"id": "stream_cape",         "name": "Streamer's Cape",       "cost": 80,  "slot": "outfit",      "description": "Flows with the energy of live content."},
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
    "chat_stream":  {"title":"CHATTERBOX",      "desc":"Send a message during the stream",  "gold":60,  "target":1, "stream":True,  "icon":"💬"},
    "visit_igloo_3":{"title":"FRIENDLY NEIGHBOR","desc":"Visit 3 igloos today",              "gold":50,  "xp":20, "target":3, "stream":False, "icon":"🏠"},
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


def ensure_player_data(db, username):
    """Ensure all per-player table rows exist. Safe to call multiple times."""
    try:
        db.execute("INSERT OR IGNORE INTO resources (username) VALUES (?)", (username,))
    except Exception as e:
        print(f"[ensure_player_data] resources: {e}")
    try:
        db.execute("INSERT OR IGNORE INTO igloos (username) VALUES (?)", (username,))
    except Exception as e:
        print(f"[ensure_player_data] igloos: {e}")


def get_gold(db, username):
    ensure_resources(db, username)
    r = db.execute("SELECT gold FROM resources WHERE username=?", (username,)).fetchone()
    return r["gold"] if r else 0


def add_gold(db, username, amount):
    ensure_resources(db, username)
    db.execute("UPDATE resources SET gold=gold+? WHERE username=?", (amount, username))
    if amount > 0:
        record_challenge_progress(db, "gold_earned", amount)



def log_event(db, event_type, message, username=None):
    # Highlight the acting player's name wherever it literally appears in the
    # message text, so it stands out in the event log tab / welcome-back
    # popup / news ticker (all render this same message field as HTML).
    # Skipped when the caller already pre-highlighted a display name (e.g.
    # igloo visits) to avoid nesting the span twice.
    if username and username in message and "pname-hl" not in message:
        message = re.sub(re.escape(username), highlight_name(username), message)
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

# N00Tboxes granted per day of the login streak, one real entry per day of a
# full 30-day cycle (tunable) -- every day gets a box, escalating at the
# weekly checkpoints (7/14/21/28) and peaking on day 30. Past day 30 the
# cycle repeats from day 1 (see award_streak_milestone's cycle_day below),
# same wraparound behavior the old 28-day _MILESTONE_TIERS cycle had, just
# now spanning all 30 promised days instead of silently reusing a 4-entry
# table with no day-3/30/60 rewards.
LOGIN_STREAK_LOOTBOX_SCHEDULE = {
    1: 1,  2: 1,  3: 1,  4: 1,  5: 1,  6: 1,
    7: 2,                                       # 1-week checkpoint
    8: 1,  9: 1, 10: 1, 11: 1, 12: 1, 13: 1,
    14: 3,                                      # 2-week checkpoint
    15: 1, 16: 1, 17: 1, 18: 1, 19: 1, 20: 1,
    21: 2,                                      # 3-week checkpoint
    22: 1, 23: 1, 24: 1, 25: 1, 26: 1, 27: 1,
    28: 3,                                      # 4-week checkpoint
    29: 1,
    30: 5,                                      # full-cycle grand finale
}


def compute_daily_reward():
    res_name, res_icon = random.choice(DAILY_RESOURCE_OPTIONS)
    amount = random.randint(2, 5)
    return {"gold": 50, "resource": res_name, "resource_amount": amount, "resource_icon": res_icon}


def award_streak_milestone(db, username, streak):
    """Grant this login-streak day's N00Tbox reward, per LOGIN_STREAK_LOOTBOX_SCHEDULE.

    Fires every day (not just every 7th) -- streak maps onto a repeating
    30-day cycle via cycle_day, so day 31 replays day 1's reward, day 60
    replays day 30's, etc. Reuses the caller's own already-open `db`
    connection (grant_lootbox's optional-db param, same convention as
    raid_settings.get_setting) since this always runs mid-transaction from
    home()/welcome-back's own login-streak update.
    """
    if streak <= 0:
        return None
    cycle_day = ((streak - 1) % 30) + 1
    count = LOGIN_STREAK_LOOTBOX_SCHEDULE[cycle_day]
    lootbox_ids = grant_lootbox(username, count, "login_streak", db=db)
    box_word = "N00Tbox" if count == 1 else "N00Tboxes"
    log_event(db, "achievement",
              f"{username} hit a {streak}-day login streak! +{count} {box_word} 🎁",
              username)
    return {"streak": streak, "cycle_day": cycle_day, "lootbox_count": count,
            "is_milestone": cycle_day in (7, 14, 21, 28, 30), "lootbox_ids": lootbox_ids}


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
        if defn.get("xp"):
            award_xp(db, username, defn["xp"])
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
    """Sum up combat set bonuses from equipped gear pieces. Returns combat_power_bonus."""
    equipped = db.execute(
        "SELECT set_name FROM gear WHERE username=? AND equipped=1 AND type='combat' AND set_name IS NOT NULL",
        (username,)
    ).fetchall()
    set_counts = {}
    for g in equipped:
        sn = g["set_name"]
        if sn:
            set_counts[sn] = set_counts.get(sn, 0) + 1

    equipped_cosmetics = db.execute(
        "SELECT name FROM gear WHERE username=? AND equipped=1 AND type='cosmetic'",
        (username,)
    ).fetchall()
    cosmetic_names = [c["name"] for c in equipped_cosmetics]

    total_cp_bonus = 0
    active_descriptions = []

    # Piece-count tiers are mutually exclusive -- only the HIGHEST tier a
    # player's piece count reaches applies (checked highest-first, first
    # match wins), not every tier whose threshold is met summed together.
    # "secret" is a separate unlock condition (piece count + a specific
    # cosmetic), not a piece-count tier, so it stays additive on top.
    _PIECE_TIERS = (("3pc", 3), ("2pc", 2))

    set_bonuses = catalog.load_set_bonuses(db=db)
    for set_name, count in set_counts.items():
        if set_name not in set_bonuses:
            continue
        set_data = set_bonuses[set_name]
        for tier_key, pieces_required in _PIECE_TIERS:
            if count >= pieces_required and tier_key in set_data:
                total_cp_bonus += set_data[tier_key]["combat_power_bonus"]
                active_descriptions.append(f"{set_name} {tier_key}: {set_data[tier_key]['description']}")
                break
        if count >= 3 and "secret" in set_data:
            if set_data["secret"]["cosmetic_required"] in cosmetic_names:
                total_cp_bonus += set_data["secret"]["combat_power_bonus"]
                active_descriptions.append(f"{set_name} SECRET: {set_data['secret']['description']}")

    return {
        "combat_power_bonus": total_cp_bonus,
        "active_bonuses": active_descriptions,
        # Keep backward compat keys at zero so get_combat_stats() doesn't crash
        "attack_bonus": 0, "defense_bonus": 0, "speed_bonus": 0, "hp_bonus": 0,
    }


def get_combat_power(username):
    db = get_db()
    try:
        p = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
        level = p["level"] if p else 1
        cp = 10 + level * 3
        equipped = db.execute(
            "SELECT combat_power FROM gear WHERE username=? AND equipped=1 AND type='combat'",
            (username,)
        ).fetchall()
        for item in equipped:
            cp += item["combat_power"] or 0
        sb = calculate_set_bonuses(db, username)
        cp += sb.get("combat_power_bonus", 0)
        for buff in get_active_buffs(db):
            if buff["buff_type"] == "festival":
                cp = int(cp * 1.1)
    finally:
        db.close()
    return cp


def check_cosmetic_sets(username, db=None):
    """Check which cosmetic sets are complete and return active bonuses."""
    close_db = False
    if db is None:
        db = get_db()
        close_db = True
    try:
        equipped_cosmetics = db.execute(
            "SELECT name FROM gear WHERE username=? AND equipped=1 AND type='cosmetic'",
            (username,)
        ).fetchall()
        equipped_names = [c["name"] for c in equipped_cosmetics]
    finally:
        if close_db:
            db.close()

    active_bonuses = {}
    for set_name, set_data in COSMETIC_SET_BONUSES.items():
        if all(item in equipped_names for item in set_data["required_items"]):
            for key, val in set_data["bonus"].items():
                if key != "description":
                    active_bonuses[key] = active_bonuses.get(key, 0) + val
            active_bonuses.setdefault("active_sets", []).append({
                "name": set_name,
                "description": set_data["bonus"]["description"],
            })
    return active_bonuses

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


# Per-tier win-chance steepness -- tune during balance-pass, target-curve
# solve 2026-07-17. The target curve per bracket is: hardest monster ~30% win
# at the bracket's entry level and ~90% by its last level, easiest ~85% at
# entry. With realistic CP growth per bracket (simulated from the real drop/
# XP systems, calibrated to the measured 121-total-CP-at-level-8 data point:
# entry->exit total CP of 13->50, 70->135, 152->196, 205->269, 273->289),
# the old fixed slope of 1 %/CP needs exactly 60 CP of growth per bracket to
# span 30%->90% -- only tiers 2 and 4 come close (65/64); tiers 1, 3 and 5
# grow 37/44/16. So the 30->90 target is NOT hittable with monster CP alone:
# each tier's slope is solved as K = 60 / (bracket CP growth) instead.
# Tier 5's steep 3.73 is the honest consequence of gear capping out (only
# ~16 CP of growth across levels 25-30). tier=None keeps the legacy slope of
# 1.0 for any non-tiered caller.
WIN_CHANCE_TIER_STEEPNESS = {
    1: 1.61,  # levels 1-4:   ~37 CP growth
    2: 0.92,  # levels 5-9:   ~65 CP growth
    3: 1.35,  # levels 10-14: ~44 CP growth
    4: 0.94,  # levels 15-24: ~64 CP growth
    5: 3.73,  # levels 25-30: ~16 CP growth
}


def calculate_win_chance(player_cp, monster_cp, tier=None):
    k = WIN_CHANCE_TIER_STEEPNESS.get(tier, 1.0)
    return max(5, min(95, round(50 + k * (player_cp - monster_cp))))

def get_evaluation(win_chance):
    if win_chance >= 90: return "Free Real Estate"
    if win_chance >= 75: return "Easy Peasy"
    if win_chance >= 60: return "Feeling Lucky"
    if win_chance >= 50: return "Coin Flip"
    if win_chance >= 40: return "Sweaty Flippers"
    if win_chance >= 25: return "Pray to the Mayor"
    if win_chance >= 10: return "Basically Suicide"
    return "Miracle Required"

def resolve_fight(player_cp, monster_cp, tier=None):
    win_chance = calculate_win_chance(player_cp, monster_cp, tier)
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


def generate_gear_drop(monster_tier, db=None):
    """Generate a random gear drop for a given monster tier.

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why.
    """
    weights  = _GEAR_DROP_RARITY_WEIGHTS.get(monster_tier, _GEAR_DROP_RARITY_WEIGHTS[1])
    pool     = [r for r, w in weights.items() for _ in range(w)]
    rarity   = random.choice(pool)
    tmpl     = random.choice(catalog.load_gear_templates(db=db)[rarity])
    item_id  = f"drop_{tmpl['slot']}_{rarity}_{int(time.time())}_{random.randint(1000,9999)}"
    return {
        "name": tmpl["name"].upper(),
        "item_id": item_id,
        "type": "combat",
        "slot": tmpl["slot"],
        "rarity": rarity,
        "set_name": tmpl["set_name"],
        "combat_power": tmpl["combat_power"],
        "attack_bonus": 0, "defense_bonus": 0, "speed_bonus": 0, "hp_bonus": 0,
    }


# ── LOOTBOXES ─────────────────────────────────────────────────────────────────
# Standalone system (Phase 4) — not yet wired into raid rewards. Phase 5's
# raid-reward distribution will call grant_lootbox() once the raid ends.

def _roll_lootbox_rarity(db=None):
    """Weighted random rarity roll using the live lootbox_drop_rates setting (sums to 100).

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why.
    """
    rates      = raid_settings.get_setting("lootbox_drop_rates", db=db)
    roll       = random.uniform(0, 100)
    cumulative = 0
    for rarity, pct in rates.items():
        cumulative += pct
        if roll < cumulative:
            return rarity
    return "common"  # float-rounding fallback


def _generate_lootbox_gear(rarity, db=None):
    """Random gear item of an exact rarity — reuses catalog.load_gear_templates(),
    same shape as generate_gear_drop(). Same optional-`db` convention as
    raid_settings.get_setting()."""
    tmpl    = random.choice(catalog.load_gear_templates(db=db)[rarity])
    item_id = f"lootbox_{tmpl['slot']}_{rarity}_{int(time.time())}_{random.randint(1000,9999)}"
    return {
        "name": tmpl["name"].upper(),
        "item_id": item_id,
        "type": "combat",
        "slot": tmpl["slot"],
        "rarity": rarity,
        "set_name": tmpl["set_name"],
        "combat_power": tmpl["combat_power"],
        "attack_bonus": 0, "defense_bonus": 0, "speed_bonus": 0, "hp_bonus": 0,
    }


def open_lootbox(lootbox_id, username):
    """Roll + apply a lootbox's rewards (1 gear item + gold + 1 resource).

    Returns the roll result dict for the frontend to animate, or None if the
    box doesn't exist, isn't owned by username, or was already opened.
    """
    db  = get_db()
    box = db.execute("SELECT * FROM player_lootboxes WHERE id=?", (lootbox_id,)).fetchone()
    if not box or box["username"] != username or box["opened"]:
        db.close()
        return None

    rarity   = _roll_lootbox_rarity(db=db)
    gear     = _generate_lootbox_gear(rarity, db=db)
    gold_range     = raid_settings.get_setting("gold_range", db=db)
    resource_range = raid_settings.get_setting("resource_range", db=db)
    gold     = random.randint(gold_range[0], gold_range[1])
    resource = random.choice(RESOURCE_TYPES)
    amount   = random.randint(resource_range[0], resource_range[1])

    db.execute(
        "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, "
        "attack_bonus, defense_bonus, speed_bonus, hp_bonus, combat_power, equipped, obtained_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
        (username, gear["item_id"], gear["name"], gear["set_name"], gear["type"], gear["slot"],
         gear["rarity"], gear["attack_bonus"], gear["defense_bonus"], gear["speed_bonus"],
         gear["hp_bonus"], gear["combat_power"], int(time.time()))
    )
    add_gold(db, username, gold)
    ensure_resources(db, username)
    db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
    db.execute("UPDATE player_lootboxes SET opened=1 WHERE id=?", (lootbox_id,))
    db.commit()
    db.close()

    return {
        "gear":     {"name": gear["name"], "rarity": gear["rarity"], "slot": gear["slot"], "set_name": gear["set_name"]},
        "gold":     gold,
        "resource": {"type": resource, "amount": amount},
    }


def grant_lootbox(username, count, source, db=None):
    """Insert `count` unopened lootboxes for username. Returns the list of
    newly-inserted player_lootboxes.id values (in insert order) so a caller
    that wants to offer an immediate "Open" action on its award notification
    can target the exact box(es) just granted instead of only the count.

    Stable signature — Phase 5's raid-reward distribution calls this directly,
    e.g. grant_lootbox(username, 3, "raid_reward").

    Pass the caller's own already-open `db` connection when calling mid-
    transaction (same optional-db convention as raid_settings.get_setting) --
    opening a second connection there would contend for the write lock
    against that transaction. Omit `db` for a genuine top-level caller with
    nothing open yet (unchanged from before: opens/commits/closes its own).
    """
    owns_conn = db is None
    if owns_conn:
        db = get_db()
    now = int(time.time())
    ids = []
    for _ in range(count):
        cur = db.execute(
            "INSERT INTO player_lootboxes (username, source, opened, created_at) VALUES (?,?,0,?)",
            (username, source, now)
        )
        ids.append(cur.lastrowid)
    if owns_conn:
        db.commit()
        db.close()
    return ids


# ── RAID RESOLUTION ───────────────────────────────────────────────────────────
# Phase 5 — the single place a raid transitions to a terminal status. Called
# instantly from /raid/attack on boss defeat, and from the Monday timeout sweep.

def calculate_rank_reward(rank, total_participants, db=None):
    """Resource amount for non-podium ranks (below rank_reward_podium_size).

    Placeholder curve, tune during balance-pass — live inputs are the
    resource_range and rank_reward_podium_size raid_settings. Linearly scales
    from the range's ceiling (the rank just below the podium) down to its
    floor (last place), so it neither dwarfs nor trivializes the lootbox
    rewards the podium ranks receive.

    Called once per non-podium participant from resolve_raid()'s own loop --
    pass its `db` through (as resolve_raid does) so this reuses that
    already-open connection instead of opening two more per call.
    """
    resource_range = raid_settings.get_setting("resource_range", db=db)
    podium_size    = raid_settings.get_setting("rank_reward_podium_size", db=db)
    lo, hi = resource_range[0], resource_range[1]
    first_scaled_rank = podium_size + 1

    if total_participants <= first_scaled_rank:
        return hi
    span     = total_participants - first_scaled_rank
    position = (rank - first_scaled_rank) / span
    reward   = hi - position * (hi - lo)
    return max(lo, round(reward))


def resolve_raid(raid_id, reason):
    """End a raid: terminal status, damage leaderboard, rewards, chat announcement.

    reason is "defeated" (boss HP hit 0) or "timeout" (still active at the
    Monday sweep). Returns the leaderboard payload, or None if the raid was
    already resolved (e.g. a defeat and the timeout sweep raced each other).
    """
    db   = get_db()
    raid = db.execute("SELECT * FROM raid_state WHERE id=?", (raid_id,)).fetchone()
    if not raid or raid["status"] != "active":
        db.close()
        return None

    now        = int(time.time())
    new_status = "succeeded" if reason == "defeated" else "failed"
    db.execute("UPDATE raid_state SET status=?, raid_end=? WHERE id=?", (new_status, now, raid_id))
    db.commit()   # release the write lock before grant_lootbox() opens its own connection below

    participants = db.execute(
        "SELECT username, total_damage_dealt FROM raid_participants WHERE raid_id=? "
        "ORDER BY total_damage_dealt DESC", (raid_id,)
    ).fetchall()
    total_participants = len(participants)
    podium_size        = raid_settings.get_setting("rank_reward_podium_size", db=db)
    db.commit()   # release the write lock (get_setting may have just seeded this
                   # key on first read) before the loop below's podium branch calls
                   # grant_lootbox(), which opens its own separate connection

    leaderboard = []
    for rank, p in enumerate(participants, start=1):
        username = p["username"]
        if rank <= podium_size:
            lootbox_count = podium_size - rank + 1
            lootbox_ids = grant_lootbox(username, lootbox_count, "raid_reward")
            # lootbox_ids persisted alongside the count so the results modal
            # can offer a direct "Open" action on the current viewer's own
            # box(es) instead of just the count -- see reward_summary below.
            reward = {"lootboxes": lootbox_count, "lootbox_ids": lootbox_ids}
        else:
            resource = random.choice(RESOURCE_TYPES)
            # db passed through so this reuses the connection instead of
            # opening two more per non-podium participant (see
            # calculate_rank_reward's docstring).
            amount   = calculate_rank_reward(rank, total_participants, db=db)
            ensure_resources(db, username)
            db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
            reward = {"resource_type": resource, "resource_amount": amount}

        # Persisted so GET /raid/results can redisplay the exact reward later
        # without re-rolling (the resource type above is random per participant).
        db.execute(
            "UPDATE raid_participants SET reward_summary=? WHERE raid_id=? AND username=?",
            (json.dumps(reward), raid_id, username)
        )
        db.commit()   # same reason as above — grant_lootbox() on the next iteration needs the lock free
        leaderboard.append({
            "rank": rank, "username": username,
            "total_damage_dealt": p["total_damage_dealt"], "reward": reward,
        })

    top3 = [entry["username"] for entry in leaderboard[:3]]
    if reason == "defeated":
        outcome = f"{raid['boss_name']} has been DEFEATED!"
    else:
        outcome = f"{raid['boss_name']} escaped — the village ran out of time."
    if top3:
        outcome += " Top fighters: " + ", ".join(top3)
    else:
        outcome += " No one joined the fight this time."
    post_chat_message(db, MAYOR_USERNAME, f"📢 {outcome}", now)

    db.commit()
    db.close()

    return {
        "raid_id":     raid_id,
        "boss_name":   raid["boss_name"],
        "raid_status": new_status,
        "reason":      reason,
        "leaderboard": leaderboard,
    }


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
        log_event(db, "level_up", f"{username} reached level {new_level}! 🎉", username)
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


def get_or_create_relationship(db, user1, user2):
    u1, u2 = sorted([user1, user2])
    db.execute(
        "INSERT OR IGNORE INTO relationships (username1, username2) VALUES (?,?)", (u1, u2)
    )
    return db.execute(
        "SELECT * FROM relationships WHERE username1=? AND username2=?", (u1, u2)
    ).fetchone()


def increment_relationship(db, user1, user2):
    """Increment interaction count, update relationship level. Returns (old_level, new_level, new_count)."""
    u1, u2 = sorted([user1, user2])
    row = get_or_create_relationship(db, user1, user2)
    old_count = row["interaction_count"] if row else 0
    new_count = old_count + 1
    old_level = row["relationship_level"] if row else "stranger"

    new_level = "stranger"
    for entry in RELATIONSHIP_LEVELS:
        if new_count >= entry["threshold"]:
            new_level = entry["level"]

    db.execute(
        "UPDATE relationships SET interaction_count=?, relationship_level=?, last_interaction=? "
        "WHERE username1=? AND username2=?",
        (new_count, new_level, int(time.time()), u1, u2)
    )
    return old_level, new_level, new_count


def check_achievements(db, username):
    now   = int(time.time())
    p     = db.execute("SELECT level, xp FROM penguins WHERE username=?", (username,)).fetchone()
    r     = db.execute("SELECT gold, fish FROM resources WHERE username=?", (username,)).fetchone()
    kills = db.execute("SELECT COUNT(*) as c FROM monster_kills WHERE username=?", (username,)).fetchone()
    igloo = db.execute("SELECT COUNT(*) as c FROM igloo_furniture WHERE username=?", (username,)).fetchone()
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
            reward = defn.get("reward")
            if reward:
                ensure_resources(db, username)
                if reward.get("gold"):
                    add_gold(db, username, reward["gold"])
                if reward.get("gear_tier"):
                    gear = generate_gear_drop(reward["gear_tier"], db=db)
                    db.execute(
                        "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, "
                        "attack_bonus, defense_bonus, speed_bonus, hp_bonus, combat_power, equipped, obtained_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                        (username, gear["item_id"], gear["name"], gear["set_name"],
                         gear["type"], gear["slot"], gear["rarity"],
                         gear["attack_bonus"], gear["defense_bonus"],
                         gear["speed_bonus"], gear["hp_bonus"],
                         gear["combat_power"], now)
                    )
        except Exception as e:
            import traceback; traceback.print_exc()

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

    # Social achievements
    try:
        visits_row = db.execute(
            "SELECT total_visits_given, total_visits_received FROM penguins WHERE username=?", (username,)
        ).fetchone()
        if visits_row:
            if visits_row["total_visits_given"] >= 1:  unlock("first_igloo_visit")
            if visits_row["total_visits_given"] >= 50: unlock("social_butterfly")
            if visits_row["total_visits_received"] >= 20: unlock("popular_penguin")
        bf_count = db.execute(
            "SELECT COUNT(*) as c FROM relationships WHERE (username1=? OR username2=?) "
            "AND relationship_level IN ('trusted_flippers','penguin_mbare')", (username, username)
        ).fetchone()
        if bf_count and bf_count["c"] >= 1: unlock("best_friends_forever")
        friend_count = db.execute(
            "SELECT COUNT(*) as c FROM relationships WHERE (username1=? OR username2=?) "
            "AND relationship_level IN ('friend','village_comrade','trusted_flippers','penguin_mbare')", (username, username)
        ).fetchone()
        if friend_count and friend_count["c"] >= 10: unlock("village_socialite")
    except Exception:
        pass

    return new_ach


# ── LEADERBOARD ───────────────────────────────────────────────────────────────

_LB_CATEGORIES = {
    "monsters":  {"col": "total_monsters_defeated",  "label": "Monsters Defeated", "icon": "⚔️"},
    "resources": {"col": "total_resources_collected", "label": "Resources Collected", "icon": "📦"},
    "gold":      {"col": "total_gold_collected",      "label": "Gold Collected",    "icon": "💰"},
    "prestige":  {"col": "prestige",                  "label": "Prestige",          "icon": "♻️"},
    "level":     {"col": "level",                     "label": "Level",             "icon": "⭐"},
}


def _check_lb_achievements(db, username):
    best_rank = None
    for cat, cfg in _LB_CATEGORIES.items():
        col = cfg["col"]
        if cat == "level":
            rows = db.execute(f"SELECT username FROM penguins ORDER BY {col} DESC, xp DESC").fetchall()
        else:
            rows = db.execute(f"SELECT username FROM penguins ORDER BY {col} DESC").fetchall()
        names = [r["username"] for r in rows]
        if username in names:
            rank = names.index(username) + 1
            if best_rank is None or rank < best_rank:
                best_rank = rank

    if best_rank is None:
        return []

    now = int(time.time())
    new_ach = []

    def lb_unlock(aid, gold_reward=0):
        try:
            db.execute(
                "INSERT INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
                (username, aid, now)
            )
            new_ach.append(aid)
            defn = ACHIEVEMENT_DEFS.get(aid, {})
            log_event(db, "achievement",
                      f"{username} unlocked '{defn.get('title','?')}'! {defn.get('icon','')}", username)
            if gold_reward > 0:
                ensure_resources(db, username)
                add_gold(db, username, gold_reward)
            if aid == "lb_top3":
                log_event(db, "village",
                          f"🏆 {username} has reached the TOP 3 on the leaderboard!", username)
        except Exception:
            pass

    if best_rank <= 20: lb_unlock("lb_top20", 100)
    if best_rank <= 10: lb_unlock("lb_top10", 200)
    if best_rank <= 3:  lb_unlock("lb_top3",  500)
    if best_rank == 1:  lb_unlock("lb_first", 1000)
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


def run_autonomous_actions():
    db = get_db()
    try:
        all_penguins = [dict(p) for p in db.execute(
            "SELECT username, penguin_name, trait_social, trait_interest, trait_quirk, "
            "social_mode, social_target FROM penguins WHERE character_created=1"
        ).fetchall()]
        # Attach selected interests to each penguin
        interest_rows = db.execute(
            "SELECT username, interest_key FROM penguin_interests"
        ).fetchall()
        interest_map = {}
        for row in interest_rows:
            interest_map.setdefault(row["username"], []).append(row["interest_key"])
        for p in all_penguins:
            p["interests"] = interest_map.get(p["username"], [])
        # ── social_modes flag gate ──────────────────────────────────────────
        # When off, ignore whatever social_mode/social_target is stored per
        # player and make action selection behave as if everyone is on the
        # default "social" mode. The DB column/values are left untouched —
        # remove this override to re-enable per-player mode weighting.
        if not FEATURES.get("social_modes", False):
            for p in all_penguins:
                p["social_mode"]   = "social"
                p["social_target"] = None
    except Exception as e:
        print(f"[Autonomous] Failed to load penguins: {e}")
        db.close()
        return
    if not all_penguins:
        db.close()
        return
    now = int(time.time())
    generated = 0
    for penguin in all_penguins:
        try:
            action  = pick_autonomous_action(penguin, all_penguins)
            if not action:
                continue
            other_penguin = None
            if action["requires_other"]:
                other_penguin = pick_other_penguin(penguin, all_penguins)
                if not other_penguin:
                    continue
            text   = generate_action_text(action, penguin, other_penguin)
            prefix = CATEGORY_EMOJIS.get(action.get("category", "solo"), "🐧")
            db.execute(
                "INSERT INTO event_log (event_type, message, username, created_at) VALUES (?,?,?,?)",
                ("autonomous", f"{prefix} {text}", penguin["username"], now)
            )
            if action["requires_other"] and other_penguin:
                _record_auto_interaction(db, penguin["username"], other_penguin["username"], action, now)
            generated += 1
        except Exception as e:
            print(f"[Autonomous] Error for {penguin.get('username')}: {e}")

    # ── Group event roll (independent of per-player action selection above) ──
    try:
        if random.random() < GROUP_EVENT_CHANCE_PER_TICK:
            topic_to_players = {}
            for p in all_penguins:
                display_name = p.get("penguin_name") or p["username"]
                for topic_key in p.get("interests", []):
                    topic_to_players.setdefault(topic_key, []).append((p["username"], display_name))
            result = pick_group_event(topic_to_players)
            if result:
                topic_key, entry, participants = result
                text         = format_group_event_text(entry, participants, topic_key)
                prefix       = CATEGORY_EMOJIS.get(entry.get("category", "village"), "🏘️")
                participant_usernames = json.dumps([u for (u, _) in participants])
                # entry["event_type"] is "group" for every GROUP_EVENT_TEMPLATES
                # entry (was previously hardcoded to "village" here even though
                # the field already existed on the template dict, unused).
                db.execute(
                    "INSERT INTO event_log (event_type, message, username, created_at, participants) "
                    "VALUES (?,?,?,?,?)",
                    (entry.get("event_type", "village"), f"{prefix} {text}", None, now, participant_usernames)
                )
    except Exception as e:
        print(f"[Autonomous] Group event error: {e}")

    db.commit()
    # Prune chat messages older than 24 h to keep the table bounded
    cutoff = now - 86400
    db.execute("DELETE FROM chat_messages WHERE created_at < ?", (cutoff,))
    db.commit()
    db.close()
    print(f"[Autonomous] Generated {generated} actions for {len(all_penguins)} penguins")


def _record_auto_interaction(db, user_a, user_b, action, now):
    u1, u2 = sorted([user_a, user_b])
    db.execute("INSERT OR IGNORE INTO relationships (username1, username2) VALUES (?,?)", (u1, u2))


# ── WEEKLY CHALLENGE / RAID SCHEDULER JOBS ───────────────────────────────────

def start_new_weekly_challenge():
    """Monday 00:00 — pick a metric (no back-to-back repeat), open a new challenge."""
    if not FEATURES.get("weekly_raid", False):
        return
    metric = pick_weekly_metric()
    week_start = datetime.date.today().isoformat()
    now = int(time.time())
    db = get_db()
    try:
        # Defensive: a debug action (Set Progress, etc.) can leave a stray
        # 'active' challenge behind if the mayor never explicitly resolved or
        # cancelled it before Monday. weekly_challenges has no constraint
        # enforcing "at most one active" the way raid_state effectively does
        # below -- without this, this job would insert a SECOND active
        # challenge on top of the leftover one.
        stray = db.execute("UPDATE weekly_challenges SET status='cancelled' WHERE status='active'").rowcount
        if stray:
            print(f"[WeeklyChallenge] Cancelled {stray} stray active challenge(s) left over before starting a new one")
        db.execute(
            "INSERT INTO weekly_challenges (metric_type, threshold, current_progress, week_start, status, created_at) "
            "VALUES (?, ?, 0, ?, 'active', ?)",
            (metric["id"], metric["threshold"], week_start, now),
        )
        db.commit()
        print(f"[WeeklyChallenge] New challenge started: {metric['label']} (threshold {metric['threshold']})")
    except Exception as e:
        print(f"[WeeklyChallenge] ERROR starting challenge: {e}")
    finally:
        db.close()


def end_raid_if_timeout():
    """Monday 00:00 (runs before start_new_weekly_challenge) — force-resolve any still-active raid."""
    if not FEATURES.get("weekly_raid", False):
        return
    try:
        db = get_db()
        active_raids = db.execute("SELECT id FROM raid_state WHERE status='active'").fetchall()
        db.close()
        for row in active_raids:
            resolve_raid(row["id"], "timeout")
        print(f"[WeeklyChallenge] Raid timeout sweep complete ({len(active_raids)} raid(s) resolved)")
    except Exception as e:
        print(f"[WeeklyChallenge] ERROR in end_raid_if_timeout: {e}")


def evaluate_weekly_challenge():
    """Friday 09:00 — check if the active challenge was met; create raid_state if so."""
    if not FEATURES.get("weekly_raid", False):
        return
    now = int(time.time())
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, metric_type, threshold, current_progress "
            "FROM weekly_challenges WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            print("[WeeklyChallenge] No active challenge to evaluate")
            return

        challenge_id = row["id"]
        succeeded = row["current_progress"] >= row["threshold"]
        new_status = "succeeded" if succeeded else "failed"

        # Guard against double-spawning a boss: a debug "Start Raid Now" (or a
        # previous cycle's raid that was never resolved) can already have a
        # pending/active raid_state row sitting around when this runs. Check
        # BEFORE picking a boss name, so we don't waste a raid_settings round
        # trip on a name that'll never be used.
        existing_raid = None
        if succeeded:
            existing_raid = db.execute(
                "SELECT id FROM raid_state WHERE status IN ('join_window', 'awaiting_raid', 'active') "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()

        # pick_boss_name(db=db) reuses this connection instead of opening a
        # second one for raid_settings.boss_names -- a prior version of this
        # call relied on call-ordering (running before any write here) to
        # avoid contending with itself for the write lock, exactly the
        # record_challenge_progress() class of bug; passing db through
        # eliminates that risk structurally instead of by discipline.
        boss_name = pick_boss_name(db=db) if (succeeded and not existing_raid) else None

        db.execute(
            "UPDATE weekly_challenges SET status=? WHERE id=?",
            (new_status, challenge_id),
        )

        if succeeded and existing_raid:
            print(
                f"[WeeklyChallenge] Challenge succeeded, but raid #{existing_raid['id']} is already "
                f"pending/active -- skipping a new raid to avoid a double-spawn."
            )
        elif succeeded:
            # raid_join_window on: legacy join-window phase (players sign up here,
            # raid opens Saturday). raid_join_window off (default): skip straight to
            # "won, raid pending" -- no signup, the overlay just shows the challenge
            # as complete until start_raid_if_unlocked() opens the raid Saturday.
            initial_status = "join_window" if FEATURES.get("raid_join_window", False) else "awaiting_raid"
            db.execute(
                "INSERT INTO raid_state "
                "(challenge_id, boss_name, boss_max_hp, boss_current_hp, status, join_window_start, created_at) "
                "VALUES (?, ?, 0, 0, ?, ?, ?)",
                (challenge_id, boss_name, initial_status, now, now),
            )
            print(f"[WeeklyChallenge] Challenge succeeded! Raid unlocked: {boss_name} (status={initial_status})")
        else:
            print(
                f"[WeeklyChallenge] Challenge failed "
                f"({row['current_progress']}/{row['threshold']} {row['metric_type']})"
            )

        db.commit()
    except Exception as e:
        print(f"[WeeklyChallenge] ERROR in evaluate_weekly_challenge: {e}")
    finally:
        db.close()


def start_raid_if_unlocked():
    """Saturday 00:00 — open the raid (boss HP is now flat, not participant-scaled).

    Purely time-triggered: whichever raid_state row is sitting in 'join_window'
    (legacy, raid_join_window on) or 'awaiting_raid' (default, raid_join_window
    off) goes active here, regardless of how many players signed up/attacked
    beforehand -- there's no participant-count dependency left in this
    function at all. If the week's challenge failed, no such row exists and
    this is a no-op, same as before.

    This is the REAL automatic job and its precondition (a challenge must
    have succeeded to produce a pending row in the first place) is
    intentionally untouched -- the Mayor debug panel's "Start Raid Now" no
    longer calls this function at all, precisely so it can spawn a raid with
    no such precondition; see raid_debug_force_start_raid.

    Returns True if a raid actually transitioned to active, False otherwise
    (feature off, nothing pending, or one's already active) -- the real cron
    job ignores this; used by callers that need to tell a real change apart
    from a no-op.
    """
    if not FEATURES.get("weekly_raid", False):
        return False
    now = int(time.time())
    db = get_db()
    try:
        # Defensive: don't spawn a second boss on top of one a debug action
        # (or a previous cycle) already left active and unresolved.
        already_active = db.execute(
            "SELECT id FROM raid_state WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if already_active:
            print(f"[WeeklyChallenge] Raid #{already_active['id']} is already active — skipping (won't start a second one)")
            return False

        raid = db.execute(
            "SELECT id FROM raid_state WHERE status IN ('join_window', 'awaiting_raid') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not raid:
            print("[WeeklyChallenge] No raid pending — nothing to start")
            return False

        raid_id     = raid["id"]
        boss_max_hp = raid_settings.get_setting("boss_hp_flat", db=db)

        db.execute(
            "UPDATE raid_state SET status='active', boss_max_hp=?, boss_current_hp=?, raid_start=? "
            "WHERE id=?",
            (boss_max_hp, boss_max_hp, now, raid_id),
        )
        db.commit()
        print(f"[WeeklyChallenge] Raid {raid_id} started — boss HP {boss_max_hp} (flat)")
        return True
    except Exception as e:
        print(f"[WeeklyChallenge] ERROR in start_raid_if_unlocked: {e}")
        return False
    finally:
        db.close()


if _APSCHEDULER_AVAILABLE and (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug):
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(run_autonomous_actions, "interval", minutes=60, id="autonomous_actions",
                       misfire_grace_time=60)
    # Weekly challenge + raid lifecycle (all UTC)
    # end_raid_if_timeout MUST complete before start_new_weekly_challenge — both
    # used to be registered at the identical Mon 00:00:00 trigger time, which
    # APScheduler does not guarantee an execution order for. Staggered by one
    # minute so ordering is enforced by distinct next_run_time values instead.
    _scheduler.add_job(end_raid_if_timeout,        "cron", day_of_week="mon", hour=0, minute=0,
                       id="end_raid_timeout",       misfire_grace_time=300)
    _scheduler.add_job(start_new_weekly_challenge,  "cron", day_of_week="mon", hour=0, minute=1,
                       id="start_weekly_challenge",  misfire_grace_time=300)
    _scheduler.add_job(evaluate_weekly_challenge,   "cron", day_of_week="fri", hour=9, minute=0,
                       id="evaluate_weekly_challenge", misfire_grace_time=300)
    _scheduler.add_job(start_raid_if_unlocked,      "cron", day_of_week="sat", hour=0, minute=0,
                       id="start_raid",              misfire_grace_time=300)
    _scheduler.start()
    print("[Scheduler] Autonomous actions scheduler started — runs every 60 minutes")
    print("[Scheduler] Weekly challenge/raid jobs registered (Mon 00:00 timeout, Mon 00:01 new challenge, Fri 09:00, Sat 00:00)")
elif not _APSCHEDULER_AVAILABLE:
    print("[Scheduler] WARNING: apscheduler not available — autonomous actions disabled")


# ── ROUTES ───────────────────────────────────────────────────────────────────

# Legacy join-window schedule (raid_join_window flag only) set by the
# scheduler jobs above: opens Friday 09:00 UTC, closes Saturday 00:00 UTC
# when start_raid_if_unlocked() flips the raid to 'active'. Not stored on
# raid_state, so derive it from join_window_start rather than adding a
# migration for it. With raid_join_window off (default), raid_state goes
# straight from 'awaiting_raid' to 'active' at the same Saturday 00:00 UTC
# job — there's no window to compute an end time for.
_RAID_REWARD_PREVIEW = "Top damage dealers win N00Tboxes + resources"


_METRIC_LABELS = {m["id"]: m["label"] for m in WEEKLY_METRIC_TYPES}


@app.route("/raid/status")
def raid_status():
    if not FEATURES.get("weekly_raid", False):
        return jsonify({"status": "none"})

    db  = get_db()
    row = db.execute("SELECT * FROM raid_state ORDER BY id DESC LIMIT 1").fetchone()

    if row and row["status"] == "awaiting_raid":
        # Challenge succeeded, raid_join_window is off, and the boss hasn't
        # spawned yet -- purely a Fri-evening-to-Sat-morning holding state.
        # Reuses the weekly-challenge-bar overlay slot/shape (current_progress
        # pinned at threshold) so the frontend can render it with the same
        # updateChallengeBar() renderer as challenge_active, just a different
        # label -- see raid.js.
        challenge = db.execute(
            "SELECT metric_type, threshold FROM weekly_challenges WHERE id=?",
            (row["challenge_id"],)
        ).fetchone()
        db.close()
        threshold = challenge["threshold"] if challenge else 0
        metric_type = challenge["metric_type"] if challenge else None
        return jsonify({
            "status":            "awaiting_raid",
            "boss_name":         row["boss_name"],
            "metric_type":       metric_type,
            "metric_label":      _METRIC_LABELS.get(metric_type, metric_type),
            "current_progress":  threshold,
            "threshold":         threshold,
        })

    if not row or row["status"] not in ("join_window", "active"):
        # No raid pending — surface the Mon-Fri weekly challenge progress instead,
        # so the map overlay can show its progress bar in the same slot the
        # join icon / boss HP bar occupy once a raid exists.
        challenge = db.execute(
            "SELECT metric_type, current_progress, threshold FROM weekly_challenges "
            "WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        db.close()
        if not challenge:
            return jsonify({"status": "none"})
        return jsonify({
            "status":            "challenge_active",
            "metric_type":       challenge["metric_type"],
            "metric_label":      _METRIC_LABELS.get(challenge["metric_type"], challenge["metric_type"]),
            "current_progress":  challenge["current_progress"],
            "threshold":         challenge["threshold"],
        })

    participant_count = db.execute(
        "SELECT COUNT(*) as cnt FROM raid_participants WHERE raid_id=?", (row["id"],)
    ).fetchone()["cnt"]

    # Server-verified join state (not the client's session-local flag) --
    # lets a second device/session correctly show "Joined ✓" on load instead
    # of only after that specific browser has clicked Join itself.
    username = session.get("username")
    already_joined = False
    if username:
        already_joined = db.execute(
            "SELECT 1 FROM raid_participants WHERE raid_id=? AND username=?", (row["id"], username)
        ).fetchone() is not None
    db.close()

    join_window_end = None
    if row["join_window_start"]:
        start_dt = datetime.datetime.utcfromtimestamp(row["join_window_start"])
        end_dt   = datetime.datetime.combine(start_dt.date() + datetime.timedelta(days=1), datetime.time(0, 0))
        join_window_end = int(end_dt.replace(tzinfo=datetime.timezone.utc).timestamp())

    payload = {
        "status":             row["status"],
        "raid_id":            row["id"],
        "boss_name":          row["boss_name"],
        "participant_count":  participant_count,
        "joined":             already_joined,
        "join_window_start":  row["join_window_start"],
        "join_window_end":    join_window_end,
        "reward_preview":     _RAID_REWARD_PREVIEW,
    }
    if row["status"] == "active":
        payload["boss_current_hp"] = row["boss_current_hp"]
        payload["boss_max_hp"]     = row["boss_max_hp"]
    return jsonify(payload)


_CHALLENGE_START_FLAVOR = {
    "gold_earned":        "Let's make some money!",
    "resources_gathered": "Let's gather some resources!",
    "monsters_killed":    "Let's hunt some monsters!",
}


@app.route("/lifecycle-notices/<username>")
def lifecycle_notices(username):
    """One-shot popup notices for weekly-challenge/raid lifecycle transitions.

    Compares the latest weekly_challenges/raid_state rows against the
    per-player "last delivered" markers and returns only what this specific
    player hasn't seen yet, then advances those markers -- so a transition
    (challenge started, challenge resolved, raid weekend opened, raid
    resolved) is surfaced to each player exactly once, however often they
    poll. Only looks at the single latest row of each table (not a full
    history), matching how far back the existing welcome-back summary looks.
    """
    if not FEATURES.get("weekly_raid", False):
        return jsonify({"notices": []})

    db = get_db()
    p = db.execute(
        "SELECT notice_challenge_start_id, notice_challenge_result_id, "
        "notice_raid_start_id, notice_raid_result_id FROM penguins WHERE username=?",
        (username,)
    ).fetchone()
    if not p:
        db.close()
        return jsonify({"notices": []})

    notices = []
    updates = {}

    challenge = db.execute("SELECT * FROM weekly_challenges ORDER BY id DESC LIMIT 1").fetchone()
    if challenge:
        cid = challenge["id"]
        metric_label = _METRIC_LABELS.get(challenge["metric_type"], challenge["metric_type"])
        if cid > (p["notice_challenge_start_id"] or 0):
            notices.append({
                "type": "challenge_start",
                "title": "NEW WEEKLY CHALLENGE!",
                "subtitle": _CHALLENGE_START_FLAVOR.get(challenge["metric_type"], "Let's take on this week's challenge!"),
                "description": f"Goal: {challenge['threshold']} {metric_label}",
            })
            updates["notice_challenge_start_id"] = cid
        if challenge["status"] in ("succeeded", "failed") and cid > (p["notice_challenge_result_id"] or 0):
            won = challenge["status"] == "succeeded"
            notices.append({
                "type": "challenge_result_success" if won else "challenge_result_fail",
                "title": "CHALLENGE COMPLETE!" if won else "CHALLENGE FAILED!",
                "subtitle": "The village hit the goal! The raid begins Saturday morning!" if won
                            else "We came up short this week. Better luck next time!",
                "description": f"{challenge['current_progress']}/{challenge['threshold']} {metric_label}",
            })
            updates["notice_challenge_result_id"] = cid

    raid = db.execute("SELECT * FROM raid_state ORDER BY id DESC LIMIT 1").fetchone()
    if raid:
        rid = raid["id"]
        # 'awaiting_raid' (raid_join_window off, default) means the boss
        # hasn't spawned yet -- the raid isn't actually raidable until
        # Saturday's status='active' flip, so don't announce "raid weekend"
        # early. 'join_window' (legacy, raid_join_window on) already means
        # players can act (sign up) the moment it opens, so that still fires
        # immediately, same as before this change.
        if raid["status"] != "awaiting_raid" and rid > (p["notice_raid_start_id"] or 0):
            notices.append({
                "type": "raid_start",
                "title": "RAID WEEKEND!",
                "subtitle": f"The {raid['boss_name']} has awoken! Join the raid before the weekend ends!",
                "description": "Your CP influences your rolls! Gear up and attack! (e.g. 50 CP gives +5 flat to rolls)",
            })
            updates["notice_raid_start_id"] = rid
        if raid["status"] in ("succeeded", "failed") and rid > (p["notice_raid_result_id"] or 0):
            won = raid["status"] == "succeeded"
            notices.append({
                "type": "raid_result_success" if won else "raid_result_fail",
                "title": "RAID VICTORY!" if won else "RAID DEFEATED...",
                "subtitle": f"{raid['boss_name']} has been vanquished! Check your rewards." if won
                            else f"{raid['boss_name']} proved too strong this time. The village regroups.",
                "description": "",
            })
            updates["notice_raid_result_id"] = rid

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE penguins SET {set_clause} WHERE username=?", (*updates.values(), username))
        db.commit()
    db.close()
    return jsonify({"notices": notices})


@app.route("/raid/join", methods=["POST"])
def raid_join():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    if not FEATURES.get("weekly_raid", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    if not FEATURES.get("raid_join_window", False):
        # Route/table stay intact for re-enabling later — see feature_flags.py.
        # No raid_state row is ever created with status='join_window' while
        # this is off, so the query below would always return "no raid open"
        # anyway; this just gives a truthful message instead of that generic one.
        return jsonify({"status": "disabled", "message": "No signup needed — just attack the boss directly once the raid starts!"})

    db  = get_db()
    row = db.execute(
        "SELECT id FROM raid_state WHERE status='join_window' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "No raid is open for joining right now."})

    raid_id  = row["id"]
    existing = db.execute(
        "SELECT 1 FROM raid_participants WHERE raid_id=? AND username=?", (raid_id, username)
    ).fetchone()
    if not existing:
        try:
            db.execute(
                "INSERT INTO raid_participants (raid_id, username, joined_at) VALUES (?, ?, ?)",
                (raid_id, username, int(time.time())),
            )
            db.commit()
        except sqlite3.IntegrityError:
            # Two near-simultaneous requests for the same account (e.g. a
            # second device/session) can both pass the SELECT above before
            # either INSERT commits. raid_participants' UNIQUE(raid_id,
            # username) constraint rejects the loser here instead of ever
            # persisting a duplicate row -- treat that exactly like the
            # pre-check already found them, not an error.
            db.rollback()

    participant_count = db.execute(
        "SELECT COUNT(*) as cnt FROM raid_participants WHERE raid_id=?", (raid_id,)
    ).fetchone()["cnt"]
    db.close()
    return jsonify({"status": "success", "participant_count": participant_count})


@app.route("/raid/attack", methods=["POST"])
def raid_attack():
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    if not FEATURES.get("weekly_raid", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})

    db   = get_db()
    raid = db.execute(
        "SELECT * FROM raid_state WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not raid:
        db.close()
        return jsonify({"status": "error", "message": "No raid is active right now."}), 409

    raid_id = raid["id"]

    # get_combat_power() is read-only (safe regardless of ordering); cp_damage_bonus()
    # reuses this route's own db instead of opening a second connection for
    # raid_settings.cp_damage_bonus_divisor, the same fix applied to
    # pick_boss_name()/record_challenge_progress() elsewhere in this raid system.
    player_cp = get_combat_power(username)
    cp_bonus  = cp_damage_bonus(player_cp, db=db)

    if FEATURES.get("raid_join_window", False):
        participant = db.execute(
            "SELECT 1 FROM raid_participants WHERE raid_id=? AND username=?", (raid_id, username)
        ).fetchone()
        if not participant:
            db.close()
            return jsonify({"status": "error", "message": "You haven't joined this raid."}), 403
    else:
        # No join phase -- any logged-in player can attack once the raid is
        # active. total_damage_dealt still needs a raid_participants row to
        # accumulate onto (resolve_raid()'s leaderboard reads from that table
        # unchanged), so upsert one on first attack instead of requiring a
        # prior join. INSERT OR IGNORE is race-safe against a second
        # device/session's simultaneous first attack for the same account —
        # raid_participants' UNIQUE(raid_id, username) makes the loser a no-op
        # rather than an error.
        db.execute(
            "INSERT OR IGNORE INTO raid_participants (raid_id, username, joined_at) VALUES (?, ?, ?)",
            (raid_id, username, int(time.time())),
        )

    p = db.execute(
        "SELECT energy, build_free_rolls FROM penguins WHERE username=?", (username,)
    ).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Player not found."})

    energy       = p["energy"] or 0
    free_rolls   = p["build_free_rolls"] or 0
    energy_cost  = 5   # same cost as /build/roll
    is_free_roll = free_rolls > 0

    if not is_free_roll:
        if energy < energy_cost:
            db.close()
            return jsonify({"status": "error", "message": f"Need {energy_cost} energy to attack! Rest at the hotel."})
        db.execute("UPDATE penguins SET energy=energy-? WHERE username=?", (energy_cost, username))

    roll        = random.randint(1, 20)
    base_damage = calculate_attack_damage(roll)
    # cp_bonus (computed above, before any write on this connection) applies
    # identically here regardless of whether this turns out to be a normal
    # roll or a free-roll/crit roll (that only affects free_rolls bookkeeping
    # below, not this damage total).
    damage        = base_damage + cp_bonus
    is_crit       = (roll == 20 and not is_free_roll)
    normal_return = False

    # Shares the same build_free_rolls bank as /build/roll — a crit on either
    # roll type grants 5 free rolls usable on either endpoint.
    if is_free_roll:
        new_free_rolls = free_rolls - 1
        normal_return  = (new_free_rolls == 0)
        db.execute("UPDATE penguins SET build_free_rolls=? WHERE username=?", (new_free_rolls, username))
    elif is_crit:
        new_free_rolls = 5
        db.execute("UPDATE penguins SET build_free_rolls=5 WHERE username=?", (username,))
    else:
        new_free_rolls = 0

    new_boss_hp = max(0, raid["boss_current_hp"] - damage)
    db.execute("UPDATE raid_state SET boss_current_hp=? WHERE id=?", (new_boss_hp, raid_id))
    db.execute(
        "UPDATE raid_participants SET total_damage_dealt=total_damage_dealt+? WHERE raid_id=? AND username=?",
        (damage, raid_id, username),
    )
    award_xp(db, username, roll)
    p2 = db.execute("SELECT energy FROM penguins WHERE username=?", (username,)).fetchone()
    db.commit()
    db.close()

    payload = {
        "status":               "success",
        "roll":                 roll,
        "damage_dealt":         damage,
        # Breakdown so the frontend can optionally show "roll: X + CP bonus: Y
        # = Z damage" -- damage_dealt above is unchanged/still the total, so
        # nothing requires the frontend to use these.
        "base_damage":          base_damage,
        "cp_bonus":             cp_bonus,
        "total_damage":         damage,
        "player_cp":            player_cp,
        "boss_current_hp":      new_boss_hp,
        "boss_max_hp":          raid["boss_max_hp"],
        "was_crit":             is_crit,
        "normal_return":        normal_return,
        "free_rolls_remaining": new_free_rolls,
        "xp_earned":            roll,
        "energy_remaining":     (p2["energy"] if p2 else energy - (0 if is_free_roll else energy_cost)),
    }

    if new_boss_hp <= 0:
        # Resolve instantly for responsive UX rather than waiting on a scheduler
        # tick — resolve_raid re-opens its own db handle after the commit above
        # so it sees this attack's damage in the final ranking.
        resolution = resolve_raid(raid_id, "defeated")
        if resolution:
            payload["resolution"] = resolution

    return jsonify(payload)


@app.route("/raid/results/<int:raid_id>")
def raid_results(raid_id):
    if not session.get("username"):
        return jsonify({"status": "error", "message": "Not logged in."})

    db   = get_db()
    raid = db.execute("SELECT * FROM raid_state WHERE id=?", (raid_id,)).fetchone()
    # 'active' is included so the leaderboard can be viewed live, mid-raid —
    # reward_summary is only populated at resolution time, so in-progress
    # entries just come back with reward: {} (nothing decided yet).
    if not raid or raid["status"] not in ("succeeded", "failed", "active"):
        db.close()
        return jsonify({"status": "error", "message": "No results available for this raid."})

    rows = db.execute(
        "SELECT username, total_damage_dealt, reward_summary FROM raid_participants "
        "WHERE raid_id=? ORDER BY total_damage_dealt DESC", (raid_id,)
    ).fetchall()
    db.close()

    leaderboard = []
    for rank, r in enumerate(rows, start=1):
        reward = json.loads(r["reward_summary"]) if r["reward_summary"] else {}
        leaderboard.append({
            "rank": rank, "username": r["username"],
            "total_damage_dealt": r["total_damage_dealt"], "reward": reward,
        })

    return jsonify({
        "status":      "success",
        "raid_id":     raid_id,
        "boss_name":   raid["boss_name"],
        "raid_status": raid["status"],
        "leaderboard": leaderboard,
    })


@app.route("/world/areas")
def world_areas():
    return jsonify({"areas": WORLD_AREAS})


@app.route("/editor")
def editor():
    username = session.get("username")
    if not username or username != MAYOR_USERNAME:
        return redirect(url_for("home"))
    return render_template("editor.html")


@app.route("/")
def home():
    username = session.get("username")
    auth_error = request.args.get("error", "")
    if not username:
        return render_template("home.html", logged_in=False, features=FEATURES, penguin=None,
                               auth_error=auth_error)
    update_passive_energy(username)
    db = get_db()
    _prow = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not _prow:
        session.clear()
        db.close()
        return render_template("home.html", logged_in=False, features=FEATURES, penguin=None)
    penguin = dict(_prow)
    penguin.setdefault("penguin_shape", "normal")
    penguin.setdefault("penguin_color", "#1a1a1a")
    penguin.setdefault("penguin_name", username)
    penguin.setdefault("character_created", 0)
    penguin.setdefault("tutorial_completed", 0)
    penguin.setdefault("tutorial_step", 0)
    penguin.setdefault("trait_social", None)
    penguin.setdefault("trait_interest", None)
    penguin.setdefault("trait_quirk", None)
    penguin.setdefault("social_mode", "social")
    penguin.setdefault("social_target", None)
    penguin.setdefault("total_contributions", 0)
    penguin.setdefault("total_monsters_defeated", 0)
    penguin.setdefault("total_resources_collected", 0)
    penguin.setdefault("total_gold_collected", 0)
    penguin.setdefault("prestige", 0)
    penguin.setdefault("active_title", None)
    penguin.setdefault("tutorial_rewards_given", "[]")
    penguin.setdefault("last_active", 0)
    penguin["penguin_color"] = _resolve_hex_color(penguin.get("penguin_color") or "#1a1a1a")
    ensure_resources(db, username)
    ensure_player_data(db, username)

    # ── Character creation gate ────────────────────────────────────────────────
    if not penguin["character_created"]:
        db.close()
        return render_template(
            "character_creation.html",
            username=username,
            mode="create",
            current_name=None,
            current_color="#1a1a1a",
            current_shape="normal",
            preset_colors=_PRESET_COLORS,
            social_traits=SOCIAL_TRAITS,
            interest_traits=INTEREST_TRAITS,
            quirk_traits=QUIRK_TRAITS,
        )

    # ── Streak + daily mission — trigger once per calendar day ──────────────
    today = get_today()
    streak_row_pre = db.execute("SELECT last_login_date FROM login_streaks WHERE username=?", (username,)).fetchone()
    is_new_day = not streak_row_pre or streak_row_pre["last_login_date"] != today
    daily_lootbox_awarded = False
    daily_lootbox_id = None
    if is_new_day:
        streak = update_login_streak(db, username, today)
        if not session.get("daily_reward"):
            session["daily_reward"] = compute_daily_reward()
        milestone = award_streak_milestone(db, username, streak)
        if milestone and not session.get("streak_reward"):
            session["streak_reward"] = milestone
        advance_mission(db, username, "login_today", today)
        check_achievements(db, username)
        # First login of the calendar day -- grant_lootbox() reuses this
        # route's own already-open `db` (see its docstring) rather than
        # opening a second connection mid-transaction. Capture the id so the
        # award toast can offer a direct "Open" action on this exact box.
        daily_lootbox_id = grant_lootbox(username, 1, "daily_login", db=db)[0]
        daily_lootbox_awarded = True

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
        daily_lootbox_awarded=daily_lootbox_awarded,
        daily_lootbox_id=daily_lootbox_id,
        features=FEATURES,
        level_data=LEVEL_DATA,
        tutorial_completed=bool(penguin["tutorial_completed"]) if penguin["tutorial_completed"] else False,
        tutorial_step=int(penguin["tutorial_step"] or 0),
        social_traits=SOCIAL_TRAITS,
        interest_traits=INTEREST_TRAITS,
        quirk_traits=QUIRK_TRAITS,
        auth_error=auth_error,
    )


@app.route("/login")
def login():
    return redirect(
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={TWITCH_CLIENT_ID}"
        f"&redirect_uri={TWITCH_REDIRECT_URI}"
        "&response_type=code&scope=user:read:email"
    )


@app.route("/auth/callback")
def callback():
    code = request.args.get("code")
    try:
        token_resp = http_requests.post("https://id.twitch.tv/oauth2/token", data={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": TWITCH_REDIRECT_URI,
        }, timeout=10)
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("No access token")
        user_resp = http_requests.get(
            "https://api.twitch.tv/helix/users",
            headers={"Authorization": f"Bearer {access_token}", "Client-Id": TWITCH_CLIENT_ID},
            timeout=10,
        )
        username = user_resp.json()["data"][0]["login"]
    except Exception:
        return redirect("/?error=twitch_auth_failed")
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
    ensure_player_data(db, username)
    db.commit()
    db.close()
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/login/discord")
def login_discord():
    return redirect(
        "https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        "&response_type=code&scope=identify"
    )


@app.route("/auth/discord/callback")
def discord_callback():
    code = request.args.get("code")
    try:
        # Exchange code for access token
        token_resp = http_requests.post(
            "https://discord.com/api/oauth2/token",
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "client_id":     DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "redirect_uri":  DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("No access token")

        # Fetch Discord user identity
        user_resp = http_requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user_data    = user_resp.json()
        discord_id   = user_data["id"]
        discord_user = user_data.get("global_name") or user_data.get("username")
    except Exception:
        return redirect("/?error=discord_auth_failed")

    db = get_db()
    try:
        # 1. Returning user — look up by stable discord_id first
        row = db.execute(
            "SELECT username FROM penguins WHERE discord_id = ?", (discord_id,)
        ).fetchone()

        if row:
            username = row["username"]
            session["new_user"] = False
        else:
            # 2. New Discord user — resolve a unique username
            taken = db.execute(
                "SELECT username FROM penguins WHERE username = ?", (discord_user,)
            ).fetchone()
            username = discord_user if not taken else f"{discord_user}_{discord_id[-4:]}"

            db.execute("INSERT INTO penguins (username) VALUES (?)", (username,))
            session["new_user"] = True
            log_event(db, "village", f"{username} joined the village! 🐧", username)
            ensure_resources(db, username)
            db.execute(
                "INSERT OR IGNORE INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
                (username, "first_login", int(time.time()))
            )

        # Always sync auth metadata in case of first login or id not yet stored
        db.execute(
            "UPDATE penguins SET auth_provider='discord', discord_id=? WHERE username=?",
            (discord_id, username),
        )
        ensure_player_data(db, username)
        db.commit()
    except Exception:
        db.rollback()
        db.close()
        return redirect("/?error=discord_auth_failed")

    db.close()
    session["username"] = username
    return redirect(url_for("home"))


@app.route("/reshape")
def reshape_page():
    username = session.get("username")
    if not username:
        return redirect(url_for("home"))
    db = get_db()
    p = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    db.close()
    if not p:
        return redirect(url_for("home"))
    current_color = _resolve_hex_color(p["penguin_color"] or "#1a1a1a")
    current_name  = p["penguin_name"] or ""
    current_shape = p["penguin_shape"] or "normal"
    return render_template(
        "character_creation.html",
        username=username,
        mode="reshape",
        current_name=current_name,
        current_color=current_color,
        current_shape=current_shape,
        preset_colors=_PRESET_COLORS,
        social_traits=SOCIAL_TRAITS,
        interest_traits=INTEREST_TRAITS,
        quirk_traits=QUIRK_TRAITS,
    )


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
    pcolor = _resolve_hex_color(p["penguin_color"] if p["penguin_color"] else "#1a1a1a")
    pname  = p["penguin_name"]  if p["penguin_name"]  else p["username"]
    return jsonify({
        "status": "success",
        "penguin": {
            "username":        p["username"],
            "penguin_name":    pname,
            "penguin_color":   pcolor,
            "penguin_shape":   p["penguin_shape"] or "normal",
            "color_palette":   {},
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
            "social_mode":     (p["social_mode"]   if p["social_mode"]   is not None else "social"),
            "social_target":   (p["social_target"] if p["social_target"] is not None else None),
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
    db.execute(
        "UPDATE penguins SET total_gold_collected=total_gold_collected+? WHERE username=?",
        (reward["gold"], username)
    )
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
    """Sidebar streak widget data -- reflects the real 30-day
    LOGIN_STREAK_LOOTBOX_SCHEDULE cycle (see award_streak_milestone), not a
    generic 7-day-only view. `week_days` is the current 7-day chunk of the
    cycle (days 1-7, 8-14, 15-21, 22-28, or the final 29-30 pair), each
    entry carrying that day's real N00Tbox count so the widget never
    mislabels which days are big-reward days (e.g. day 30 isn't a multiple
    of 7, so a naive mod-7 view would miss it entirely)."""
    db  = get_db()
    row = db.execute(
        "SELECT current_streak, longest_streak FROM login_streaks WHERE username=?", (username,)
    ).fetchone()
    db.close()
    cur       = row["current_streak"] if row else 1
    cycle_day = ((cur - 1) % 30) + 1

    week_start = ((cycle_day - 1) // 7) * 7 + 1
    week_days  = []
    d = week_start
    while d <= 30 and d < week_start + 7:
        week_days.append({
            "day":    d,
            "count":  LOGIN_STREAK_LOOTBOX_SCHEDULE[d],
            "status": "done" if d < cycle_day else ("today" if d == cycle_day else "upcoming"),
        })
        d += 1

    # Days until the next big-reward day (count > 1), searching forward
    # through the 30-day cycle; today counts as 0 days away if it's itself
    # a milestone day.
    days_to_next_milestone = 0
    next_milestone_count   = LOGIN_STREAK_LOOTBOX_SCHEDULE[cycle_day]
    for offset in range(30):
        d = ((cycle_day - 1 + offset) % 30) + 1
        if LOGIN_STREAK_LOOTBOX_SCHEDULE[d] > 1:
            days_to_next_milestone = offset
            next_milestone_count   = LOGIN_STREAK_LOOTBOX_SCHEDULE[d]
            break

    return jsonify({
        "current":                cur,
        "longest":                row["longest_streak"] if row else 1,
        "cycle_day":              cycle_day,
        "cycle_length":           30,
        "today_lootbox_count":    LOGIN_STREAK_LOOTBOX_SCHEDULE[cycle_day],
        "week_days":              week_days,
        "days_to_next_milestone": days_to_next_milestone,
        "next_milestone_count":   next_milestone_count,
    })


@app.route("/leaderboard")
def leaderboard():
    db = get_db()
    rows = db.execute(
        "SELECT p.username, p.penguin_name, p.penguin_color, p.level, p.xp, p.prestige, p.job, p.active_title, r.gold "
        "FROM penguins p LEFT JOIN resources r ON p.username=r.username "
        "ORDER BY p.level DESC, p.xp DESC LIMIT 20"
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d["display_name"] = d["penguin_name"] or d["username"]
        d["penguin_color"] = _resolve_hex_color(d.get("penguin_color") or "#1a1a1a")
        result.append(d)
    return jsonify({"penguins": result})


@app.route("/leaderboard/all")
def leaderboard_all():
    username = request.args.get("username", "")
    db = get_db()
    player_ranks = {}
    for cat, cfg in _LB_CATEGORIES.items():
        col = cfg["col"]
        if cat == "level":
            rows = db.execute(f"SELECT username, {col} FROM penguins ORDER BY {col} DESC, xp DESC").fetchall()
        elif cat == "prestige":
            rows = db.execute(f"SELECT username, {col} FROM penguins ORDER BY {col} DESC, level DESC").fetchall()
        else:
            rows = db.execute(f"SELECT username, {col} FROM penguins ORDER BY {col} DESC").fetchall()
        names = [r["username"] for r in rows]
        rank = (names.index(username) + 1) if username in names else None
        value = next((r[col] for r in rows if r["username"] == username), 0)
        player_ranks[cat] = {"rank": rank, "value": value}
    db.close()
    return jsonify({"player_ranks": player_ranks})


@app.route("/leaderboard/<category>")
def leaderboard_category(category):
    if category not in _LB_CATEGORIES:
        return jsonify({"status": "error", "message": "Unknown category"})
    username = request.args.get("username", "")
    cfg = _LB_CATEGORIES[category]
    col = cfg["col"]
    db = get_db()
    if category == "level":
        rows = db.execute(
            f"SELECT username, penguin_name, {col}, level, xp, prestige FROM penguins "
            f"ORDER BY {col} DESC, xp DESC LIMIT 20"
        ).fetchall()
        all_rows = db.execute(
            f"SELECT username, {col} FROM penguins ORDER BY {col} DESC, xp DESC"
        ).fetchall()
    elif category == "prestige":
        rows = db.execute(
            f"SELECT username, penguin_name, {col}, level, xp, prestige FROM penguins "
            f"ORDER BY {col} DESC, level DESC LIMIT 20"
        ).fetchall()
        all_rows = db.execute(
            f"SELECT username, {col} FROM penguins ORDER BY {col} DESC, level DESC"
        ).fetchall()
    else:
        rows = db.execute(
            f"SELECT username, penguin_name, {col}, level, xp, prestige FROM penguins "
            f"ORDER BY {col} DESC LIMIT 20"
        ).fetchall()
        all_rows = db.execute(
            f"SELECT username, {col} FROM penguins ORDER BY {col} DESC"
        ).fetchall()
    total = len(all_rows)
    all_names = [r["username"] for r in all_rows]
    player_rank = (all_names.index(username) + 1) if username in all_names else None
    player_value = next((r[col] for r in all_rows if r["username"] == username), 0)
    entries = []
    for i, r in enumerate(rows):
        entries.append({
            "rank":         i + 1,
            "username":     r["username"],
            "penguin_name": r["penguin_name"] or r["username"],
            "value":        r[col],
            "level":        r["level"],
            "prestige":     r["prestige"],
        })
    db.close()
    return jsonify({
        "status":       "success",
        "category":     category,
        "label":        cfg["label"],
        "icon":         cfg["icon"],
        "entries":      entries,
        "player_rank":  player_rank,
        "player_value": player_value,
        "total":        total,
    })


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
    username = session.get("username", "").strip()
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
    username    = session.get("username", "")
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
    username = session.get("username", "")
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

    # Apply cosmetic set bonuses
    cosmetic_bonuses = check_cosmetic_sets(username)
    if cosmetic_bonuses and hours_worked > 0:
        def _cb_earn(key, col, amount):
            if amount <= 0:
                return
            db.execute(f"UPDATE resources SET {col}={col}+? WHERE username=?", (amount, username))
            earned[key] = earned.get(key, 0) + amount

        extra_gold        = int(cosmetic_bonuses.get("gold_per_hour", 0)             * hours_worked)
        extra_fish        = int(cosmetic_bonuses.get("fish_per_hour", 0)             * hours_worked)
        extra_herbs       = int(cosmetic_bonuses.get("herbs_per_hour", 0)            * hours_worked)
        extra_bones       = int(cosmetic_bonuses.get("bones_per_hour", 0)            * hours_worked)
        extra_blood_gems  = int(cosmetic_bonuses.get("blood_gems_per_hour", 0)       * hours_worked)
        extra_frags       = int(cosmetic_bonuses.get("spell_fragments_per_hour", 0)  * hours_worked)
        extra_xp          = int(cosmetic_bonuses.get("xp_per_hour", 0)               * hours_worked)
        if extra_gold > 0:
            add_gold(db, username, extra_gold)
            earned["gold"] = earned.get("gold", 0) + extra_gold
        _cb_earn("fish",             "fish",             extra_fish)
        _cb_earn("herbs",            "herbs",            extra_herbs)
        _cb_earn("bones",            "bones",            extra_bones)
        _cb_earn("blood_gems",       "blood_gems",       extra_blood_gems)
        _cb_earn("spell_fragments",  "spell_fragments",  extra_frags)
        if extra_xp > 0:
            _, lvl_rewards = award_xp(db, username, extra_xp)
            level_ups.extend(lvl_rewards)
            earned["xp"] = earned.get("xp", 0) + extra_xp

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

    _track_res = sum(v for k, v in earned.items() if k not in ("gold", "xp") and v > 0)
    _track_gold = earned.get("gold", 0)
    if _track_res > 0:
        record_challenge_progress(db, "resources_gathered", _track_res)
    if _track_res > 0 or _track_gold > 0:
        db.execute(
            "UPDATE penguins SET total_resources_collected=total_resources_collected+?, "
            "total_gold_collected=total_gold_collected+? WHERE username=?",
            (_track_res, _track_gold, username)
        )
    db.execute("UPDATE penguins SET job=NULL, job_started=0, job_duration=0 WHERE username=?", (username,))
    today = get_today()
    advance_mission(db, username, "collect_1", today)
    advance_mission(db, username, "collect_3", today)
    new_ach = check_achievements(db, username)
    if _track_res > 0 or _track_gold > 0:
        new_ach += _check_lb_achievements(db, username)

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
        try:
            _, event_exclusive = _find_shop_definition(d.get("item_id"), "cosmetic", db=db)
        except Exception as e:
            print(f"[gear_cosmetics] event_exclusive lookup failed for gear id={d.get('id')} item_id={d.get('item_id')!r}: {e}")
            event_exclusive = False
        d["event_exclusive"] = event_exclusive
        cosmetics.append(d)
    active = check_cosmetic_sets(username, db)
    db.close()
    return jsonify({"cosmetics": cosmetics, "active_sets": active.get("active_sets", [])})


@app.route("/gear/cosmetics/equip", methods=["POST"])
def gear_cosmetics_equip():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
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

    # Check for newly discovered cosmetic sets
    newly_discovered = []
    if action == "equip":
        equipped_cosmetics = db.execute(
            "SELECT name FROM gear WHERE username=? AND equipped=1 AND type='cosmetic'",
            (username,)
        ).fetchall()
        equipped_names = [c["name"] for c in equipped_cosmetics]
        now = int(time.time())
        for set_name, set_data in COSMETIC_SET_BONUSES.items():
            if all(itm in equipped_names for itm in set_data["required_items"]):
                already = db.execute(
                    "SELECT 1 FROM discovered_sets WHERE username=? AND set_name=?",
                    (username, set_name)
                ).fetchone()
                if not already:
                    db.execute(
                        "INSERT OR IGNORE INTO discovered_sets (username, set_name, discovered_at) VALUES (?,?,?)",
                        (username, set_name, now)
                    )
                    newly_discovered.append({
                        "set_name": set_name,
                        "description": set_data["bonus"]["description"],
                    })
                    log_event(db, "village",
                              f"🔮 {username} discovered the secret of the {set_name} set!", username)
        if newly_discovered:
            db.commit()

    db.close()
    return jsonify({"status": "success", "newly_discovered": newly_discovered})


@app.route("/gear/cosmetics/discovered")
def gear_cosmetics_discovered():
    username = request.args.get("username", "")
    db = get_db()
    rows = db.execute(
        "SELECT set_name FROM discovered_sets WHERE username=? ORDER BY discovered_at",
        (username,)
    ).fetchall()
    db.close()
    result = []
    for row in rows:
        sn = row["set_name"]
        if sn in COSMETIC_SET_BONUSES:
            result.append({
                "set_name": sn,
                "description": COSMETIC_SET_BONUSES[sn]["bonus"]["description"],
            })
    return jsonify({"discovered": result})


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
            win_chance = calculate_win_chance(player_cp, mcp, mtype["tier"])
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
        username = session.get("username", "")
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
        fight = resolve_fight(player_cp, mtype["combat_power"], mtype["tier"])

        advance_mission(db, username, "fight_1", today)
        ensure_resources(db, username)

        rewards = {}
        consolation_xp = 0
        is_first_kill = False
        combat_level_ups = []
        consolation_level_ups = []

        if fight["victory"]:
            rdef = mtype["rewards"]
            multiplier = 2 if is_first_kill_eligible else 1
            gold      = random.randint(rdef["gold"][0], rdef["gold"][1]) * multiplier
            xp        = random.randint(rdef["xp"][0],   rdef["xp"][1])   * multiplier
            resources = {k: random.randint(lo, hi) * multiplier for k, (lo, hi) in rdef["resources"].items()}

            add_gold(db, username, gold)
            _, combat_level_ups = award_xp(db, username, xp)
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
                gear_drop = generate_gear_drop(mtype["tier"], db=db)
                db.execute(
                    "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, "
                    "attack_bonus, defense_bonus, speed_bonus, hp_bonus, combat_power, equipped, obtained_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                    (username, gear_drop["item_id"], gear_drop["name"], gear_drop["set_name"],
                     gear_drop["type"], gear_drop["slot"], gear_drop["rarity"],
                     gear_drop["attack_bonus"], gear_drop["defense_bonus"],
                     gear_drop["speed_bonus"], gear_drop["hp_bonus"],
                     gear_drop["combat_power"], int(time.time()))
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
            db.execute(
                "UPDATE penguins SET total_monsters_defeated=total_monsters_defeated+1, "
                "total_gold_collected=total_gold_collected+? WHERE username=?",
                (gold, username)
            )
            record_challenge_progress(db, "monsters_killed", 1)
            _check_lb_achievements(db, username)
        else:
            consolation_xp = max(1, mtype["rewards"]["xp"][0] // 4)
            _, consolation_level_ups = award_xp(db, username, consolation_xp)
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
            "level_ups":        combat_level_ups or consolation_level_ups,
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
        username = session.get("username", "")

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
    username = request.args.get("username", "")
    db = get_db()
    ensure_resources(db, username)
    rows    = db.execute("SELECT * FROM gear WHERE username=? ORDER BY id", (username,)).fetchall()
    gold    = get_gold(db, username)
    r       = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    sb      = calculate_set_bonuses(db, username)
    db.close()
    player_cp = get_combat_power(username)
    gear_list = []
    for g in rows:
        gd = dict(g)
        # Bank pricing/event-exclusive lookups are best-effort per item -- a
        # bad catalog entry or malformed gear row must not 500 the whole
        # inventory response for every other item the player owns.
        try:
            gd["bank_sellable"]   = (gd["slot"] or "") not in _BANK_UNSELLABLE_SLOTS
            _, event_exclusive    = _find_shop_definition(gd["item_id"], gd["type"])
            gd["event_exclusive"] = event_exclusive
            gd["bank_sell_value"] = calculate_bank_sell_price(gd) if gd["bank_sellable"] else 0
        except Exception as e:
            print(f"[gear_inventory] pricing failed for gear id={gd.get('id')} item_id={gd.get('item_id')!r}: {e}")
            gd["bank_sellable"]   = False
            gd["event_exclusive"] = False
            gd["bank_sell_value"] = 0
        gear_list.append(gd)
    return jsonify({
        "gear":        gear_list,
        "gold":        gold,
        "resources":   dict(r) if r else {},
        "player_cp":   player_cp,
        "set_bonuses": sb,
    })


@app.route("/gear/equip", methods=["POST"])
def gear_equip():
    if not FEATURES.get("gear_equip", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
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
    db.execute("UPDATE gear SET equipped=0 WHERE username=? AND type=? AND slot=?", (username, item["type"], item["slot"]))
    db.execute("UPDATE gear SET equipped=1 WHERE id=?", (gear_id,))
    new_ach = check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "equipped": True, "message": f"{item['name']} equipped.", "new_achievements": new_ach})


@app.route("/gear/unequip", methods=["POST"])
def gear_unequip():
    if not FEATURES.get("gear_equip", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    gear_id  = int(data.get("gear_id", 0))
    db = get_db()
    item = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    db.execute("UPDATE gear SET equipped=0 WHERE id=?", (gear_id,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "equipped": False, "message": f"{item['name']} unequipped."})


@app.route("/gear/wear", methods=["POST"])
def gear_wear():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    gear_id  = int(data.get("gear_id", 0))
    db = get_db()
    item = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    area = _VISUAL_AREA.get(item["slot"])
    if not area:
        db.close()
        return jsonify({"status": "error", "message": "This item has no visual area."})
    # Unwear all items in the same visual area (across all types)
    slots_in_area = [s for s, a in _VISUAL_AREA.items() if a == area]
    placeholders  = ",".join("?" * len(slots_in_area))
    db.execute(
        f"UPDATE gear SET worn=0 WHERE username=? AND slot IN ({placeholders})",
        (username, *slots_in_area)
    )
    db.execute("UPDATE gear SET worn=1 WHERE id=?", (gear_id,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "worn": True, "message": f"{item['name']} is now worn."})


@app.route("/gear/unwear", methods=["POST"])
def gear_unwear():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    gear_id  = int(data.get("gear_id", 0))
    db = get_db()
    item = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    db.execute("UPDATE gear SET worn=0 WHERE id=?", (gear_id,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "worn": False, "message": f"{item['name']} unworn."})


# ── LOOTBOXES ────────────────────────────────────────────────────────────────

@app.route("/lootbox/inventory/<username>")
def lootbox_inventory(username):
    session_user = session.get("username")
    if not session_user or (session_user != username and not _is_mayor_authed()):
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    db   = get_db()
    rows = db.execute(
        "SELECT * FROM player_lootboxes WHERE username=? ORDER BY id DESC", (username,)
    ).fetchall()
    db.close()
    return jsonify({"status": "success", "lootboxes": [dict(r) for r in rows]})


@app.route("/lootbox/open/<int:lootbox_id>", methods=["POST"])
def lootbox_open_route(lootbox_id):
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    db  = get_db()
    box = db.execute("SELECT username FROM player_lootboxes WHERE id=?", (lootbox_id,)).fetchone()
    db.close()
    if not box:
        return jsonify({"status": "error", "message": "Lootbox not found."}), 404
    if box["username"] != username:
        return jsonify({"status": "error", "message": "Not your lootbox."}), 403

    result = open_lootbox(lootbox_id, username)
    if result is None:
        return jsonify({"status": "error", "message": "Already opened or invalid."})
    return jsonify({"status": "success", **result})


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


# ── SOCIAL SYSTEM ENDPOINTS ───────────────────────────────────────────────────

@app.route("/penguin/social-mode", methods=["POST"])
def set_social_mode():
    data = request.get_json() or {}
    username = session.get("username", "")
    mode = data.get("mode")
    target = data.get("target") or None
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    if mode not in SOCIAL_MODES:
        return jsonify({"status": "error", "message": "Invalid social mode."})
    db = get_db()
    if not db.execute("SELECT 1 FROM penguins WHERE username=?", (username,)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    if mode == "focused" and target:
        if not db.execute("SELECT 1 FROM penguins WHERE username=?", (target,)).fetchone():
            db.close()
            return jsonify({"status": "error", "message": f"Penguin '{target}' not found."})
    else:
        if mode != "focused":
            target = None
    db.execute("UPDATE penguins SET social_mode=?, social_target=? WHERE username=?", (mode, target, username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "mode": mode, "mode_name": SOCIAL_MODES[mode]["name"], "target": target})


@app.route("/penguin/search")
def search_penguins():
    q = request.args.get("q", "").strip()
    current = session.get("username", "")
    if len(q) < 1:
        return jsonify({"results": []})
    db = get_db()
    rows = db.execute(
        "SELECT username, penguin_name, level FROM penguins "
        "WHERE (username LIKE ? OR penguin_name LIKE ?) AND username != ? "
        "ORDER BY level DESC LIMIT 5",
        (f"%{q}%", f"%{q}%", current)
    ).fetchall()
    db.close()
    return jsonify({"results": [
        {"username": r["username"], "penguin_name": r["penguin_name"], "level": r["level"]}
        for r in rows
    ]})


@app.route("/igloo/visit", methods=["POST"])
def igloo_visit():
    data = request.get_json() or {}
    visitor = data.get("visitor_username") or session.get("username")
    host = data.get("host_username")
    if not visitor:
        return jsonify({"status": "error", "message": "Not logged in."})
    if not host:
        return jsonify({"status": "error", "message": "Host username required."})
    if visitor == host:
        return jsonify({"status": "error", "message": "You can't visit your own igloo!"})

    db = get_db()
    visitor_row = db.execute("SELECT * FROM penguins WHERE username=?", (visitor,)).fetchone()
    host_row    = db.execute("SELECT * FROM penguins WHERE username=?", (host,)).fetchone()
    if not visitor_row:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})
    if not host_row:
        db.close()
        return jsonify({"status": "error", "message": "Host penguin not found."})

    today = get_today()

    if db.execute(
        "SELECT 1 FROM igloo_visits WHERE visitor=? AND host=? AND visited_date=?", (visitor, host, today)
    ).fetchone():
        # Igloos can be entered as many times as a player likes -- rewards
        # are just capped to once per host per day. Still let them in
        # (loadVisitedIgloo runs regardless of this response's rewards), but
        # skip re-granting gold/resources/xp/relationship/achievements.
        host_name = host_row["penguin_name"] or host
        rel = get_or_create_relationship(db, visitor, host)
        db.commit()
        db.close()
        rel_level = rel["relationship_level"] if rel else "stranger"
        level_name = RELATIONSHIP_DISPLAY.get(rel_level, {}).get("name", rel_level.replace("_"," ").title())
        return jsonify({
            "status": "success",
            "already_visited": True,
            "message": f"Welcome back to {host_name}'s igloo! (Rewards already claimed today.)",
            "rewards": {"gold": 0, "resource_type": None, "resource_amount": 0, "xp": 0},
            "relationship": {
                "level": level_name, "old_level": level_name,
                "level_changed": False,
                "interaction_count": rel["interaction_count"] if rel else 0,
                "next_level": None, "interactions_needed": 0,
            },
            "new_achievements": [],
            "level_ups": [],
        })

    rel = get_or_create_relationship(db, visitor, host)
    rel_level = rel["relationship_level"] if rel else "stranger"
    reward_cfg = IGLOO_VISIT_REWARDS.get(rel_level, IGLOO_VISIT_REWARDS["stranger"])

    gold_reward  = random.randint(reward_cfg["gold_min"], reward_cfg["gold_max"])
    res_type     = random.choice(["fish", "herbs", "bones", "spell_fragments"])
    res_amount   = random.randint(reward_cfg["res_min"], reward_cfg["res_max"])
    xp_reward    = reward_cfg["xp"]

    add_gold(db, visitor, gold_reward)
    ensure_resources(db, visitor)
    db.execute(f"UPDATE resources SET {res_type}={res_type}+? WHERE username=?",
               (res_amount, visitor))
    db.execute(
        "UPDATE penguins SET total_visits_given=total_visits_given+1, "
        "total_gold_collected=total_gold_collected+? WHERE username=?",
        (gold_reward, visitor)
    )
    _, igloo_level_ups = award_xp(db, visitor, xp_reward)
    db.execute("UPDATE penguins SET total_visits_received=total_visits_received+1 WHERE username=?", (host,))

    db.execute(
        "INSERT INTO igloo_visits (visitor, host, visited_date, reward_gold, reward_resource_type, reward_resource_amount) "
        "VALUES (?,?,?,?,?,?)",
        (visitor, host, today, gold_reward, res_type, res_amount)
    )

    old_level, new_level, interaction_count = increment_relationship(db, visitor, host)
    advance_mission(db, visitor, "visit_igloo_3", today)
    new_ach = check_achievements(db, visitor)

    visitor_name = visitor_row["penguin_name"] or visitor
    host_name    = host_row["penguin_name"] or host
    res_emojis   = {"fish": "🐟", "herbs": "🌿", "bones": "🦴", "spell_fragments": "✨"}
    log_event(db, "social",
        f"🏠 {highlight_name(visitor_name)} visited {highlight_name(host_name)}'s igloo and found "
        f"{res_emojis.get(res_type,'📦')} {res_amount} {res_type} and 🪙 {gold_reward} gold!", visitor)

    # Fetch host igloo data for frontend rendering
    _ensure_igloo(db, host)
    host_igloo_row  = db.execute("SELECT * FROM igloos WHERE username=?", (host,)).fetchone()
    host_furniture_rows = db.execute(
        "SELECT item_id, grid_x, grid_y, rotation FROM igloo_furniture WHERE username=?", (host,)
    ).fetchall()
    host_igloo = None
    if host_igloo_row:
        rl = host_igloo_row["room_level"]
        hf = []
        for r in host_furniture_rows:
            d = IGLOO_FURNITURE.get(r["item_id"], {})
            hf.append({"item_id": r["item_id"], "grid_x": r["grid_x"], "grid_y": r["grid_y"],
                       "rotation": r["rotation"], "width": d.get("width",1), "height": d.get("height",1)})
        host_igloo = {
            "room_level": rl, "room_size": IGLOO_LEVELS[rl]["size"],
            "room_name":  IGLOO_LEVELS[rl]["name"],
            "floor_type": host_igloo_row["floor_type"],
            "wall_type":  host_igloo_row["wall_type"],
            "furniture":  hf,
        }

    db.commit()
    db.close()

    level_name     = RELATIONSHIP_DISPLAY.get(new_level, {}).get("name", new_level.replace("_"," ").title())
    old_level_name = RELATIONSHIP_DISPLAY.get(old_level, {}).get("name", old_level.replace("_"," ").title())

    next_level_name     = None
    interactions_needed = 0
    for i, entry in enumerate(RELATIONSHIP_LEVELS):
        if entry["level"] == new_level:
            if entry["next"]:
                next_level_name     = RELATIONSHIP_DISPLAY.get(entry["next"], {}).get("name", entry["next"])
                interactions_needed = max(0, entry["next_threshold"] - interaction_count)
            break

    return jsonify({
        "status": "success",
        "message": f"{visitor_name} visited {host_name}'s igloo!",
        "rewards": {"gold": gold_reward, "resource_type": res_type, "resource_amount": res_amount, "xp": xp_reward},
        "relationship": {
            "level": level_name, "old_level": old_level_name,
            "level_changed": old_level != new_level,
            "interaction_count": interaction_count,
            "next_level": next_level_name, "interactions_needed": interactions_needed,
        },
        "new_achievements": new_ach,
        "host_igloo": host_igloo,
        "level_ups": igloo_level_ups,
    })


@app.route("/igloo/visits-today/<username>")
def igloo_visits_today(username):
    db  = get_db()
    today = get_today()

    visited_rows = db.execute(
        "SELECT iv.host, p.penguin_name FROM igloo_visits iv "
        "LEFT JOIN penguins p ON p.username=iv.host "
        "WHERE iv.visitor=? AND iv.visited_date=?",
        (username, today)
    ).fetchall()
    visited_today    = [{"username": r["host"], "penguin_name": r["penguin_name"]} for r in visited_rows]
    visited_usernames = {v["username"] for v in visited_today}

    visitor_row  = db.execute("SELECT social_target FROM penguins WHERE username=?", (username,)).fetchone()
    social_target = visitor_row["social_target"] if visitor_row else None

    rel_rows = db.execute(
        "SELECT CASE WHEN r.username1=? THEN r.username2 ELSE r.username1 END as other_username, "
        "r.interaction_count, r.relationship_level, p.penguin_name, p.level "
        "FROM relationships r "
        "JOIN penguins p ON p.username = CASE WHEN r.username1=? THEN r.username2 ELSE r.username1 END "
        "WHERE (r.username1=? OR r.username2=?) ORDER BY r.interaction_count DESC LIMIT 20",
        (username, username, username, username)
    ).fetchall()

    suggestions = []
    if social_target and social_target not in visited_usernames:
        st = db.execute("SELECT username, penguin_name, level FROM penguins WHERE username=?", (social_target,)).fetchone()
        if st:
            rel = get_or_create_relationship(db, username, social_target)
            db.commit()
            suggestions.append({
                "username": st["username"], "penguin_name": st["penguin_name"], "level": st["level"],
                "rel_level": rel["relationship_level"] if rel else "stranger", "is_target": True
            })

    for r in rel_rows:
        if r["other_username"] not in visited_usernames and r["other_username"] != social_target and len(suggestions) < 5:
            suggestions.append({
                "username": r["other_username"], "penguin_name": r["penguin_name"], "level": r["level"],
                "rel_level": r["relationship_level"], "is_target": False
            })

    if len(suggestions) < 5:
        skip = {s["username"] for s in suggestions} | visited_usernames | {username}
        placeholders = ",".join("?" * len(skip))
        extra = db.execute(
            f"SELECT username, penguin_name, level FROM penguins WHERE username NOT IN ({placeholders}) LIMIT 5",
            list(skip)
        ).fetchall()
        for r in extra:
            if len(suggestions) < 5:
                rel = get_or_create_relationship(db, username, r["username"])
                db.commit()
                suggestions.append({
                    "username": r["username"], "penguin_name": r["penguin_name"], "level": r["level"],
                    "rel_level": rel["relationship_level"] if rel else "stranger", "is_target": False
                })

    db.close()
    return jsonify({
        "visited_today": visited_today,
        "suggestions": suggestions[:5],
    })


@app.route("/relationships/<username>")
def get_relationships(username):
    db    = get_db()
    today = get_today()

    rows = db.execute(
        "SELECT p.username as other_username, p.penguin_name, "
        "COALESCE(r.interaction_count, 0) as interaction_count, "
        "COALESCE(r.relationship_level, 'stranger') as relationship_level "
        "FROM penguins p "
        "LEFT JOIN relationships r ON "
        "  ((r.username1=? AND r.username2=p.username) OR "
        "   (r.username2=? AND r.username1=p.username)) "
        "WHERE p.character_created=1 AND p.username!=? "
        "ORDER BY COALESCE(r.interaction_count,0) DESC",
        (username, username, username)
    ).fetchall()

    visited_set = {r["host"] for r in db.execute(
        "SELECT host FROM igloo_visits WHERE visitor=? AND visited_date=?", (username, today)
    ).fetchall()}

    rels = []
    for r in rows:
        level = r["relationship_level"] or "stranger"
        disp  = RELATIONSHIP_DISPLAY.get(level, {"name": level.replace("_"," ").title(), "emoji": "❓"})
        progress_pct = 0
        next_level_name = None
        interactions_needed = 0
        for i, entry in enumerate(RELATIONSHIP_LEVELS):
            if entry["level"] == level:
                if entry["next"]:
                    span = entry["next_threshold"] - entry["threshold"]
                    into = r["interaction_count"] - entry["threshold"]
                    progress_pct = min(100, int(into / max(1, span) * 100))
                    next_level_name = RELATIONSHIP_DISPLAY.get(entry["next"], {}).get("name")
                    interactions_needed = max(0, entry["next_threshold"] - r["interaction_count"])
                else:
                    progress_pct = 100
                break
        rels.append({
            "username": r["other_username"], "penguin_name": r["penguin_name"],
            "interaction_count": r["interaction_count"],
            "level": level, "level_name": disp["name"], "emoji": disp["emoji"],
            "progress_pct": progress_pct, "next_level": next_level_name,
            "interactions_needed": interactions_needed,
            "visited_today": r["other_username"] in visited_set,
        })
    db.close()
    return jsonify({"relationships": rels})


# ── EVENT LOG ─────────────────────────────────────────────────────────────────

def _format_time_ago(ts):
    diff = int(time.time()) - int(ts)
    if diff < 60:   return "just now"
    if diff < 3600: return f"{diff // 60}m ago"
    if diff < 86400: return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


@app.route("/events")
def get_events():
    cutoff = int(time.time()) - 86400  # last 24 hours
    db     = get_db()
    rows   = db.execute(
        "SELECT * FROM event_log WHERE created_at > ? ORDER BY created_at DESC LIMIT 100",
        (cutoff,)
    ).fetchall()
    db.close()
    events = []
    for r in rows:
        e = dict(r)
        e["bucket"] = _event_bucket(e["event_type"])
        events.append(e)
    return jsonify({"events": events})


@app.route("/events/share/<int:event_id>", methods=["POST"])
def share_event_to_twitch(event_id):
    # TODO StreamerBot: wire this up to the real StreamerBot integration —
    # no StreamerBot endpoints exist in this codebase yet, so this only logs
    # the request and returns a not-implemented response for now.
    username = session.get("username")
    print(f"[EventShare] {username or 'anonymous'} requested Twitch share for event_id={event_id}")
    return jsonify({"status": "not_implemented", "message": "Twitch sharing is coming soon."}), 501


@app.route("/events/recent")
def events_recent():
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM event_log WHERE event_type != 'admin_debug' ORDER BY created_at DESC LIMIT 40"
    ).fetchall()
    db.close()
    return jsonify({"events": [{
        **dict(r),
        "time_ago": _format_time_ago(r["created_at"])
    } for r in rows]})


@app.route("/debug/run-autonomous", methods=["POST"])
def debug_run_autonomous():
    key = request.args.get("key", "")
    if not MAYOR_KEY or key != MAYOR_KEY:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    run_autonomous_actions()
    return jsonify({"status": "success", "message": "Autonomous actions executed"})


# ── IGLOO ─────────────────────────────────────────────────────────────────────

@app.route("/igloo/<username>")
def get_igloo(username):
    db = get_db()
    _ensure_igloo(db, username)
    igloo = db.execute("SELECT * FROM igloos WHERE username=?", (username,)).fetchone()
    p = db.execute("SELECT penguin_color, penguin_shape, doorbell_tune FROM penguins WHERE username=?", (username,)).fetchone()
    host_color = _resolve_hex_color((p["penguin_color"] if p else None) or "#1a1a1a")
    host_shape = (p["penguin_shape"] if p else None) or "normal"
    host_doorbell_tune = None
    if p and p["doorbell_tune"]:
        try:
            host_doorbell_tune = json.loads(p["doorbell_tune"])
        except (TypeError, ValueError):
            host_doorbell_tune = None

    # Same {area: item_id} shape /village/penguins already builds for the map
    # renderer -- the igloo-visit host sprite reuses that renderer's worn-item
    # drawing rather than a separate query shape.
    host_worn_items = {}
    worn_rows = db.execute(
        "SELECT slot, item_id FROM gear WHERE worn=1 AND username=?", (username,)
    ).fetchall()
    for w in worn_rows:
        area = _VISUAL_AREA.get(w["slot"])
        if area and w["item_id"]:
            host_worn_items[area] = w["item_id"]

    room_level = igloo["room_level"]
    room_size  = IGLOO_LEVELS[room_level]["size"]
    placed = db.execute(
        "SELECT id, item_id, grid_x, grid_y, rotation FROM igloo_furniture WHERE username=? ORDER BY grid_y*100+grid_x",
        (username,)
    ).fetchall()
    furniture_list = []
    for row in placed:
        defn = IGLOO_FURNITURE.get(row["item_id"], {})
        furniture_list.append({
            "id":      row["id"],
            "item_id": row["item_id"],
            "grid_x":  row["grid_x"],
            "grid_y":  row["grid_y"],
            "rotation":row["rotation"],
            "width":   defn.get("width",  1),
            "height":  defn.get("height", 1),
        })
    owned = db.execute(
        "SELECT item_id, placed FROM igloo_items WHERE username=? ORDER BY obtained_at",
        (username,)
    ).fetchall()
    import json as _json
    unlocked_floors = list(set((igloo["unlocked_floors"] or "ice").split(",")))
    unlocked_walls  = list(set((igloo["unlocked_walls"]  or "snow").split(",")))
    try:    floor_cells = _json.loads(igloo["floor_cells"] or "{}")
    except: floor_cells = {}
    try:    wall_cells  = _json.loads(igloo["wall_cells"]  or "{}")
    except: wall_cells  = {}
    db.commit()
    db.close()
    return jsonify({
        "room_level":       room_level,
        "room_size":        room_size,
        "room_name":        IGLOO_LEVELS[room_level]["name"],
        "floor_type":       igloo["floor_type"],
        "wall_type":        igloo["wall_type"],
        "furniture":        furniture_list,
        "owned_items":      [{"item_id": r["item_id"], "placed": bool(r["placed"])} for r in owned],
        "unlocked_floors":  unlocked_floors,
        "unlocked_walls":   unlocked_walls,
        "floor_cells":      floor_cells,
        "wall_cells":       wall_cells,
        "host_color":       host_color,
        "host_shape":       host_shape,
        "host_worn_items":  host_worn_items,
        "host_doorbell_tune": host_doorbell_tune,
    })


# One octave, fixed pitch set for the igloo doorbell chiptune creator --
# slot values are indices into this list (or null for a rest). Reused by
# the frontend for both the creator UI's picker and the playback frequency.
DOORBELL_NOTE_FREQS = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]  # C4..C5 major scale


@app.route("/igloo/doorbell", methods=["POST"])
def save_doorbell_tune():
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    data = request.get_json(silent=True) or {}
    tune = data.get("tune")

    if tune is not None:
        if not isinstance(tune, list) or len(tune) != 12:
            return jsonify({"status": "error", "message": "Tune must be exactly 12 slots."})
        for slot in tune:
            if slot is not None and (not isinstance(slot, int) or not (0 <= slot < len(DOORBELL_NOTE_FREQS))):
                return jsonify({"status": "error", "message": "Each slot must be null or 0-7."})

    db = get_db()
    db.execute(
        "UPDATE penguins SET doorbell_tune=? WHERE username=?",
        (json.dumps(tune) if tune is not None else None, username)
    )
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/igloo/shop")
def igloo_shop():
    username = request.args.get("username", "")
    db = get_db()
    owned_ids = set()
    igloo_data = None
    player_gold = 0
    if username:
        _ensure_igloo(db, username)
        owned_ids = {r["item_id"] for r in db.execute(
            "SELECT item_id FROM igloo_items WHERE username=?", (username,)
        ).fetchall()}
        igloo_row = db.execute("SELECT * FROM igloos WHERE username=?", (username,)).fetchone()
        if igloo_row:
            igloo_data = dict(igloo_row)
        ensure_resources(db, username)
        player_gold = get_gold(db, username)
    db.commit()
    db.close()
    furniture = {iid: {**defn, "owned": iid in owned_ids} for iid, defn in IGLOO_FURNITURE.items()}
    return jsonify({
        "status":       "success",
        "furniture":    furniture,
        "floor_types":  FLOOR_TYPES,
        "wall_types":   WALL_TYPES,
        "igloo_levels": {k: dict(v) for k, v in IGLOO_LEVELS.items()},
        "current_igloo":igloo_data,
        "player_gold":  player_gold,
    })


@app.route("/igloo/buy-furniture", methods=["POST"])
def igloo_buy_furniture():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    item_id  = data.get("item_id", "")
    defn = IGLOO_FURNITURE.get(item_id)
    if not defn:
        return jsonify({"status": "error", "message": "Item not found."})
    cost = defn.get("cost")
    if cost is None:
        return jsonify({"status": "error", "message": "This item cannot be purchased."})
    db = get_db()
    if db.execute("SELECT 1 FROM igloo_items WHERE username=? AND item_id=?", (username, item_id)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": "Already owned!"})
    ensure_resources(db, username)
    res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    for resource, amount in cost.items():
        if (res[resource] or 0) < amount:
            db.close()
            return jsonify({"status": "error", "message": f"Need {amount} {resource.replace('_',' ')}!"})
    for resource, amount in cost.items():
        db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))
    db.execute(
        "INSERT INTO igloo_items (username, item_id, obtained_at, placed) VALUES (?,?,?,0)",
        (username, item_id, int(time.time()))
    )
    new_gold = get_gold(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "item_id": item_id, "gold_remaining": new_gold})


@app.route("/igloo/place", methods=["POST"])
def igloo_place():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    item_id  = data.get("item_id", "")
    grid_x   = int(data.get("grid_x", -1))
    grid_y   = int(data.get("grid_y", -1))
    defn = IGLOO_FURNITURE.get(item_id)
    if not defn:
        return jsonify({"status": "error", "message": "Unknown item."})
    db = get_db()
    _ensure_igloo(db, username)
    owned = db.execute(
        "SELECT id, placed FROM igloo_items WHERE username=? AND item_id=?", (username, item_id)
    ).fetchone()
    if not owned:
        db.close()
        return jsonify({"status": "error", "message": "You don't own this item."})
    if owned["placed"]:
        db.close()
        return jsonify({"status": "error", "message": "Item is already placed."})
    igloo = db.execute("SELECT room_level FROM igloos WHERE username=?", (username,)).fetchone()
    room_size = IGLOO_LEVELS[igloo["room_level"]]["size"]
    w, h = defn["width"], defn["height"]
    if grid_x < 0 or grid_y < 0 or grid_x + w > room_size or grid_y + h > room_size:
        db.close()
        return jsonify({"status": "error", "message": "Out of bounds."})
    placed = db.execute(
        "SELECT item_id, grid_x, grid_y FROM igloo_furniture WHERE username=?", (username,)
    ).fetchall()
    for p in placed:
        pd = IGLOO_FURNITURE.get(p["item_id"], {})
        if _igloo_overlaps(grid_x, grid_y, w, h, p["grid_x"], p["grid_y"], pd.get("width",1), pd.get("height",1)):
            db.close()
            return jsonify({"status": "error", "message": "That space is occupied!"})
    cur = db.execute(
        "INSERT INTO igloo_furniture (username, item_id, grid_x, grid_y, rotation) VALUES (?,?,?,?,0)",
        (username, item_id, grid_x, grid_y)
    )
    placement_id = cur.lastrowid
    db.execute("UPDATE igloo_items SET placed=1 WHERE username=? AND item_id=?", (username, item_id))
    check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "placement_id": placement_id})


@app.route("/igloo/remove", methods=["POST"])
def igloo_remove():
    data         = request.get_json(silent=True) or {}
    username     = session.get("username", "")
    placement_id = int(data.get("placement_id", -1))
    db = get_db()
    row = db.execute(
        "SELECT item_id FROM igloo_furniture WHERE id=? AND username=?", (placement_id, username)
    ).fetchone()
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "Placement not found."})
    db.execute("DELETE FROM igloo_furniture WHERE id=?", (placement_id,))
    db.execute("UPDATE igloo_items SET placed=0 WHERE username=? AND item_id=?", (username, row["item_id"]))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/igloo/move", methods=["POST"])
def igloo_move():
    data         = request.get_json(silent=True) or {}
    username     = session.get("username", "")
    placement_id = int(data.get("placement_id", -1))
    new_x        = int(data.get("new_grid_x", -1))
    new_y        = int(data.get("new_grid_y", -1))
    db = get_db()
    row = db.execute(
        "SELECT item_id FROM igloo_furniture WHERE id=? AND username=?", (placement_id, username)
    ).fetchone()
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "Placement not found."})
    defn = IGLOO_FURNITURE.get(row["item_id"], {})
    w, h = defn.get("width", 1), defn.get("height", 1)
    igloo = db.execute("SELECT room_level FROM igloos WHERE username=?", (username,)).fetchone()
    room_size = IGLOO_LEVELS[igloo["room_level"]]["size"]
    if new_x < 0 or new_y < 0 or new_x + w > room_size or new_y + h > room_size:
        db.close()
        return jsonify({"status": "error", "message": "Out of bounds."})
    others = db.execute(
        "SELECT item_id, grid_x, grid_y FROM igloo_furniture WHERE username=? AND id!=?",
        (username, placement_id)
    ).fetchall()
    for p in others:
        pd = IGLOO_FURNITURE.get(p["item_id"], {})
        if _igloo_overlaps(new_x, new_y, w, h, p["grid_x"], p["grid_y"], pd.get("width",1), pd.get("height",1)):
            db.close()
            return jsonify({"status": "error", "message": "That space is occupied!"})
    db.execute("UPDATE igloo_furniture SET grid_x=?, grid_y=? WHERE id=?", (new_x, new_y, placement_id))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/igloo/upgrade", methods=["POST"])
def igloo_upgrade():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    db = get_db()
    _ensure_igloo(db, username)
    igloo = db.execute("SELECT room_level FROM igloos WHERE username=?", (username,)).fetchone()
    current_level = igloo["room_level"]
    next_level    = current_level + 1
    if next_level not in IGLOO_LEVELS:
        db.close()
        return jsonify({"status": "error", "message": "Already at max level!"})
    cost = IGLOO_LEVELS[next_level]["cost"]
    if cost:
        ensure_resources(db, username)
        res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
        for resource, amount in cost.items():
            if (res[resource] or 0) < amount:
                db.close()
                return jsonify({"status": "error", "message": f"Need {amount} {resource.replace('_',' ')}!"})
        for resource, amount in cost.items():
            db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))
    db.execute("UPDATE igloos SET room_level=? WHERE username=?", (next_level, username))
    level_name = IGLOO_LEVELS[next_level]["name"]
    log_event(db, "igloo", f"🏠 {username} upgraded their igloo to {level_name}!", username)
    db.commit()
    db.close()
    return jsonify({
        "status":     "success",
        "room_level": next_level,
        "room_size":  IGLOO_LEVELS[next_level]["size"],
        "level_name": level_name,
    })


@app.route("/igloo/floor", methods=["POST"])
def igloo_change_floor():
    data       = request.get_json(silent=True) or {}
    username   = session.get("username", "")
    floor_type = data.get("floor_type", "")
    if floor_type not in FLOOR_TYPES:
        return jsonify({"status": "error", "message": "Invalid floor type."})
    ft = FLOOR_TYPES[floor_type]
    db = get_db()
    _ensure_igloo(db, username)
    igloo = db.execute("SELECT * FROM igloos WHERE username=?", (username,)).fetchone()
    unlocked = set((igloo["unlocked_floors"] or "ice").split(","))
    if floor_type not in unlocked:
        if ft["cost"]:
            ensure_resources(db, username)
            res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
            for resource, amount in ft["cost"].items():
                if (res[resource] or 0) < amount:
                    db.close()
                    return jsonify({"status": "error", "message": f"Need {amount} {resource.replace('_',' ')}!"})
            for resource, amount in ft["cost"].items():
                db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))
        unlocked.add(floor_type)
        db.execute("UPDATE igloos SET unlocked_floors=? WHERE username=?", (",".join(sorted(unlocked)), username))
    db.execute("UPDATE igloos SET floor_type=?, floor_cells='{}' WHERE username=?", (floor_type, username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "floor_type": floor_type, "floor_cells": {}, "unlocked_floors": sorted(list(unlocked))})


@app.route("/igloo/wall", methods=["POST"])
def igloo_change_wall():
    data      = request.get_json(silent=True) or {}
    username  = session.get("username", "")
    wall_type = data.get("wall_type", "")
    if wall_type not in WALL_TYPES:
        return jsonify({"status": "error", "message": "Invalid wall type."})
    wt = WALL_TYPES[wall_type]
    db = get_db()
    _ensure_igloo(db, username)
    igloo = db.execute("SELECT * FROM igloos WHERE username=?", (username,)).fetchone()
    unlocked = set((igloo["unlocked_walls"] or "snow").split(","))
    if wall_type not in unlocked:
        if wt["cost"]:
            ensure_resources(db, username)
            res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
            for resource, amount in wt["cost"].items():
                if (res[resource] or 0) < amount:
                    db.close()
                    return jsonify({"status": "error", "message": f"Need {amount} {resource.replace('_',' ')}!"})
            for resource, amount in wt["cost"].items():
                db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))
        unlocked.add(wall_type)
        db.execute("UPDATE igloos SET unlocked_walls=? WHERE username=?", (",".join(sorted(unlocked)), username))
    db.execute("UPDATE igloos SET wall_type=?, wall_cells='{}' WHERE username=?", (wall_type, username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "wall_type": wall_type, "wall_cells": {}, "unlocked_walls": sorted(list(unlocked))})


@app.route("/igloo/floor-cell", methods=["POST"])
def igloo_paint_floor_cell():
    import json as _json
    data       = request.get_json(silent=True) or {}
    username   = session.get("username", "")
    floor_type = data.get("floor_type", "")
    gx         = data.get("gx")
    gy         = data.get("gy")
    if floor_type not in FLOOR_TYPES:
        return jsonify({"status": "error", "message": "Invalid floor type."})
    if gx is None or gy is None:
        return jsonify({"status": "error", "message": "Missing cell coordinates."})
    db = get_db()
    _ensure_igloo(db, username)
    igloo = db.execute("SELECT * FROM igloos WHERE username=?", (username,)).fetchone()
    unlocked = set((igloo["unlocked_floors"] or "ice").split(","))
    if floor_type not in unlocked:
        db.close()
        return jsonify({"status": "error", "message": f"Unlock '{floor_type}' first from the floor palette."})
    room_level = igloo["room_level"]
    room_size  = IGLOO_LEVELS[room_level]["size"]
    if not (0 <= int(gx) < room_size and 0 <= int(gy) < room_size):
        db.close()
        return jsonify({"status": "error", "message": "Cell out of range."})
    try:    cells = _json.loads(igloo["floor_cells"] or "{}")
    except: cells = {}
    cell_key = f"{int(gx)},{int(gy)}"
    cells[cell_key] = floor_type
    db.execute("UPDATE igloos SET floor_cells=? WHERE username=?", (_json.dumps(cells), username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "floor_cells": cells})


@app.route("/igloo/wall-cell", methods=["POST"])
def igloo_paint_wall_cell():
    import json as _json
    data      = request.get_json(silent=True) or {}
    username  = session.get("username", "")
    wall_type = data.get("wall_type", "")
    side      = data.get("side", "")
    index     = data.get("index")
    if wall_type not in WALL_TYPES:
        return jsonify({"status": "error", "message": "Invalid wall type."})
    if side not in ("left", "right") or index is None:
        return jsonify({"status": "error", "message": "Missing wall side/index."})
    db = get_db()
    _ensure_igloo(db, username)
    igloo = db.execute("SELECT * FROM igloos WHERE username=?", (username,)).fetchone()
    unlocked = set((igloo["unlocked_walls"] or "snow").split(","))
    if wall_type not in unlocked:
        db.close()
        return jsonify({"status": "error", "message": f"Unlock '{wall_type}' first from the wall palette."})
    room_level = igloo["room_level"]
    room_size  = IGLOO_LEVELS[room_level]["size"]
    if not (0 <= int(index) < room_size):
        db.close()
        return jsonify({"status": "error", "message": "Wall index out of range."})
    try:    cells = _json.loads(igloo["wall_cells"] or "{}")
    except: cells = {}
    cell_key = f"{side}_{int(index)}"
    cells[cell_key] = wall_type
    db.execute("UPDATE igloos SET wall_cells=? WHERE username=?", (_json.dumps(cells), username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "wall_cells": cells})


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
    # "donation", "level_up" and "building_levelup" used to be logged as
    # "village" (see log_event call sites) before the Events-tab rework split
    # them out for sub-tab bucketing -- kept here too so they don't silently
    # disappear from this feed. "group" is deliberately excluded: those are
    # surfaced per-participant via the penguin_activities section below instead.
    notable_types = ("village", "prestige", "mayor", "milestone", "donation", "level_up", "building_levelup")
    news_rows = db.execute(
        f"SELECT message FROM event_log WHERE event_type IN ({','.join('?'*len(notable_types))})"
        " AND created_at > ? AND username != ? ORDER BY created_at DESC LIMIT 5",
        (*notable_types, last_active, username)
    ).fetchall()
    village_news = [r["message"] for r in news_rows]

    # ── Igloo visitors while away ─────────────────────────────────────────────
    try:
        from datetime import datetime, timezone as _tz
        away_date = datetime.fromtimestamp(last_active, tz=_tz.utc).strftime("%Y-%m-%d")
        today_str = get_today()
        visitor_rows = db.execute(
            "SELECT DISTINCT iv.visitor, p.penguin_name FROM igloo_visits iv "
            "LEFT JOIN penguins p ON p.username=iv.visitor "
            "WHERE iv.host=? AND iv.visited_date >= ?",
            (username, away_date)
        ).fetchall()
        for vr in visitor_rows:
            vname = vr["penguin_name"] or vr["visitor"]
            village_news.insert(0, f"🏠 {vname} stopped by your igloo while you were away!")
    except Exception:
        pass

    # ── Streak check (ensure home-route streak is up-to-date) ────────────────
    today = get_today()
    streak_row = db.execute("SELECT last_login_date FROM login_streaks WHERE username=?", (username,)).fetchone()
    if not streak_row or streak_row["last_login_date"] != today:
        new_streak = update_login_streak(db, username, today)
        milestone = award_streak_milestone(db, username, new_streak)
        if milestone and not session.get("streak_reward"):
            session["streak_reward"] = milestone

    # ── Autonomous activities & group events while away ───────────────────────
    penguin_activities = []
    try:
        combined = []

        auto_rows = db.execute(
            "SELECT message, created_at FROM event_log "
            "WHERE username=? AND event_type='autonomous' AND created_at > ? "
            "ORDER BY created_at DESC LIMIT 10",
            (username, last_active)
        ).fetchall()
        combined.extend({"message": r["message"], "created_at": r["created_at"]} for r in auto_rows)

        # Group events don't have a single acting username -- they store the
        # participant list as a JSON array in `participants` instead.
        group_rows = db.execute(
            "SELECT message, created_at, participants FROM event_log "
            "WHERE event_type='group' AND participants IS NOT NULL AND created_at > ? "
            "ORDER BY created_at DESC LIMIT 20",
            (last_active,)
        ).fetchall()
        for row in group_rows:
            try:
                participant_usernames = json.loads(row["participants"])
            except (TypeError, ValueError):
                continue
            if username in participant_usernames:
                combined.append({"message": row["message"], "created_at": row["created_at"]})

        combined.sort(key=lambda item: item["created_at"] or 0, reverse=True)
        for item in combined[:5]:
            ago_secs = now - (item["created_at"] or 0)
            if ago_secs < 3600:
                ago_str = f"{max(1, ago_secs // 60)}m ago"
            elif ago_secs < 86400:
                ago_str = f"{ago_secs // 3600}h ago"
            else:
                ago_str = f"{ago_secs // 86400}d ago"
            penguin_activities.append({"message": item["message"], "time_ago": ago_str})
    except Exception:
        pass

    db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
    db.commit()
    db.close()

    return jsonify({
        "show":               True,
        "hours_away":         round(hours_away, 1),
        "active_job":         active_job,
        "passive_earnings":   {
            "gold":       passive_gold,
            "xp":         passive_xp,
            "leveled_up": leveled_passive,
        },
        "village_news":       village_news,
        "penguin_activities": penguin_activities,
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
    username = session.get("username", "").strip()
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
    username = session.get("username", "").strip()
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
    # Derived from _RES_COL (the same map /building/donate uses to pick the
    # column to write) so every donatable resource — including ice_blocks —
    # is covered here without needing to be hand-added to a second list.
    donated       = {res: ((row[col] if row else 0) or 0) for res, col in _RES_COL.items()}
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
            # Same _RES_COL keys as `donated` above, read from `resources`
            # instead of `building_upgrades` -- keeps every donatable
            # resource (incl. ice_blocks) in sync with the donate route.
            player_resources = {res: (r[res] or 0) for res in _RES_COL}
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

    # Building background progress
    player_bg_progress = 0
    player_bg_unlocked = False
    if username and building_id in BUILDING_CARD_BACKGROUNDS:
        bct = db.execute(
            "SELECT total_contributed, background_unlocked FROM building_contributions_tracker "
            "WHERE username=? AND building_id=?",
            (username, building_id)
        ).fetchone()
        if bct:
            player_bg_progress = bct["total_contributed"] or 0
            player_bg_unlocked = bool(bct["background_unlocked"])

    db.close()
    return jsonify({"status": "success", **info,
                    "contributors": contributors,
                    "player_resources": player_resources,
                    "player_building_total": player_building_total,
                    "player_total_contributions": player_total_contributions,
                    "next_milestone": next_milestone,
                    "player_bg_progress": player_bg_progress,
                    "player_bg_unlocked": player_bg_unlocked})


@app.route("/building/donate", methods=["POST"])
def building_donate():
    data          = request.get_json(silent=True) or {}
    username      = session.get("username", "").strip()
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
        return jsonify({"status": "error", "message": f"{_resource_display_name(resource_type)} is not needed for the next upgrade."})

    # Check player has enough
    ensure_resources(db, username)
    if resource_type == "gold":
        player_have = get_gold(db, username)
    else:
        r = db.execute(f"SELECT {resource_type} FROM resources WHERE username=?", (username,)).fetchone()
        player_have = (r[resource_type] if r else 0) or 0

    if player_have < amount:
        db.close()
        return jsonify({"status": "error", "message": f"Not enough {_resource_display_name(resource_type)}. Have {player_have}, need {amount}."})

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

    log_event(db, "donation",
              f"{username} donated {amount} {_resource_display_name(resource_type)} to {cfg['name']}",
              username)

    # XP reward for donor
    if resource_type == "gold":
        xp_earned = amount // 4
    elif resource_type in ("blood_gems", "bones"):
        xp_earned = amount
    elif resource_type == "ice_blocks":
        xp_earned = max(1, amount // 2)  # 50% of donated, minimum 1 XP
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

    # Track per-building contribution for card background unlock
    building_bg_unlocked = None
    if building_id in BUILDING_CARD_BACKGROUNDS:
        db.execute(
            "INSERT INTO building_contributions_tracker (username, building_id, total_contributed, background_unlocked) "
            "VALUES (?, ?, ?, 0) ON CONFLICT(username, building_id) DO UPDATE SET "
            "total_contributed = total_contributed + excluded.total_contributed",
            (username, building_id, amount)
        )
        bct = db.execute(
            "SELECT total_contributed, background_unlocked FROM building_contributions_tracker "
            "WHERE username=? AND building_id=?",
            (username, building_id)
        ).fetchone()
        if bct and (bct["total_contributed"] or 0) >= 100 and not bct["background_unlocked"]:
            bg_info = BUILDING_CARD_BACKGROUNDS[building_id]
            db.execute(
                "UPDATE building_contributions_tracker SET background_unlocked=1 "
                "WHERE username=? AND building_id=?",
                (username, building_id)
            )
            item_id = f"card_bg_{building_id}"
            existing_bg = db.execute(
                "SELECT COUNT(*) as cnt FROM gear WHERE username=? AND item_id=? AND type='cosmetic'",
                (username, item_id)
            ).fetchone()
            if not existing_bg or existing_bg["cnt"] == 0:
                db.execute(
                    "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
                    "VALUES (?,?,?,'cosmetic','card_background','building',0,?)",
                    (username, item_id, bg_info["name"], int(time.time()))
                )
            log_event(db, "milestone",
                      f"🖼️ {username} unlocked the {bg_info['source']} card background!",
                      username)
            building_bg_unlocked = {
                "name": bg_info["name"],
                "description": bg_info["description"],
                "source": bg_info["source"],
            }

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
        log_event(db, "building_levelup",
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
        "building_bg_unlocked":    building_bg_unlocked,
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


@app.route("/card/backgrounds/<username>")
def card_backgrounds(username):
    db = get_db()
    rows = db.execute(
        "SELECT item_id, name, slot, rarity, equipped FROM gear "
        "WHERE username=? AND type='cosmetic' AND slot IN ('card_frame', 'card_background') "
        "ORDER BY obtained_at",
        (username,)
    ).fetchall()
    db.close()

    # Build lookup for color and source
    bg_color_map = {f"card_bg_{bid}": info["color"] for bid, info in BUILDING_CARD_BACKGROUNDS.items()}
    bg_source_map = {f"card_bg_{bid}": info["source"] for bid, info in BUILDING_CARD_BACKGROUNDS.items()}
    milestone_names = {v["name"]: True for v in CONTRIBUTION_MILESTONES.values()}

    results = []
    for r in rows:
        item_id = r["item_id"] or ""
        name = r["name"] or ""
        is_milestone = name in milestone_names
        source = bg_source_map.get(item_id, ("Contribution Milestone" if is_milestone else "Unknown"))
        color = bg_color_map.get(item_id, "#888888")
        image = None
        for bid, info in BUILDING_CARD_BACKGROUNDS.items():
            if item_id == f"card_bg_{bid}":
                image = info["image"]
                break
        results.append({
            "item_id": item_id,
            "name": name,
            "slot": r["slot"],
            "source": source,
            "color": color,
            "image": image,
            "equipped": bool(r["equipped"]),
        })
    return jsonify({"backgrounds": results})


@app.route("/card/background/equip", methods=["POST"])
def card_background_equip():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "").strip()
    item_id  = data.get("item_id", "").strip()
    db = get_db()
    item = db.execute(
        "SELECT * FROM gear WHERE username=? AND item_id=? AND type='cosmetic' "
        "AND slot IN ('card_frame', 'card_background')",
        (username, item_id)
    ).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Background not owned."})
    # Unequip all card frames and backgrounds for this user
    db.execute(
        "UPDATE gear SET equipped=0 WHERE username=? AND type='cosmetic' "
        "AND slot IN ('card_frame', 'card_background')",
        (username,)
    )
    db.execute("UPDATE gear SET equipped=1 WHERE username=? AND item_id=?", (username, item_id))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


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
    for category, items in catalog.load_boutique_items().items():
        result[category] = [
            {**item, "owned": item["id"] in owned_ids, "equipped": item["id"] in equipped_ids}
            for item in items
        ]
    return jsonify({"status": "success", "categories": result, "player_gold": player_gold})


@app.route("/boutique/buy", methods=["POST"])
def boutique_buy():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    item_id  = data.get("item_id", "")
    item = next(
        (i for items in catalog.load_boutique_items().values() for i in items if i["id"] == item_id),
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
    username = session.get("username", "")
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
        (i for items in catalog.load_boutique_items().values() for i in items if i["id"] == item_id),
        None
    )
    if not item:
        return jsonify({"status": "error", "message": "Item not found."})
    return jsonify({"status": "success", "item": item})


# ── BARRACKS SHOP ─────────────────────────────────────────────────────────────

@app.route("/barracks/shop/<username>")
def barracks_shop(username):
    if not FEATURES.get("gear_equip", False):
        return jsonify({"status": "disabled", "shop": catalog.load_barracks_shop(), "owned_ids": [], "gold": 0, "resources": {}})
    db = get_db()
    ensure_resources(db, username)
    owned = db.execute(
        "SELECT item_id FROM gear WHERE username=? AND type='combat'", (username,)
    ).fetchall()
    owned_ids = [r["item_id"] for r in owned if r["item_id"]]
    gold = get_gold(db, username)
    res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    db.close()
    return jsonify({
        "status": "ok",
        "shop": catalog.load_barracks_shop(),
        "owned_ids": owned_ids,
        "gold": gold,
        "resources": dict(res) if res else {},
    })


@app.route("/barracks/buy", methods=["POST"])
def barracks_buy():
    if not FEATURES.get("gear_equip", False):
        return jsonify({"status": "disabled", "message": "This feature is coming soon!"})
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    item_id  = data.get("item_id", "")

    defn = None
    rarity = None
    for r, items in catalog.load_barracks_shop().items():
        for item in items:
            if item["id"] == item_id:
                defn   = item
                rarity = r
                break
        if defn:
            break

    if not defn:
        return jsonify({"status": "error", "message": "Unknown item."})

    db = get_db()
    ensure_resources(db, username)

    already = db.execute(
        "SELECT id FROM gear WHERE username=? AND item_id=? AND type='combat'",
        (username, item_id)
    ).fetchone()
    if already:
        db.close()
        return jsonify({"status": "error", "message": "You already own this item."})

    r = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    if not r:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    for resource, amount in defn["cost"].items():
        have = r["gold"] if resource == "gold" else (r[resource] if resource in r.keys() else 0)
        if have < amount:
            db.close()
            return jsonify({"status": "error", "message": f"Need {amount} {resource}."})

    for resource, amount in defn["cost"].items():
        if resource == "gold":
            add_gold(db, username, -amount)
        else:
            db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))

    db.execute(
        "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, "
        "attack_bonus, defense_bonus, speed_bonus, hp_bonus, combat_power, obtained_at) "
        "VALUES (?,?,?,NULL,'combat',?,?,0,0,0,0,?,?)",
        (username, item_id, defn["name"], defn["slot"], rarity,
         defn["combat_power"], int(time.time()))
    )
    log_event(db, "gear_purchase", f"{username} forged {defn['name']} from the Barracks", username)
    new_ach = check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": f"{defn['name']} forged!", "new_achievements": new_ach})


# ── PENGUIN CUSTOMIZATION ─────────────────────────────────────────────────────

def _get_unlocked_colors(db, penguin):
    """Return list of locked color IDs that this penguin has unlocked."""
    unlocked = []
    prestige = penguin["prestige"] or 0
    level    = penguin["level"]    or 1
    username = penguin["username"]

    if prestige >= 1: unlocked.append("arctic_white")
    if prestige >= 2: unlocked.append("royal_blue")
    if prestige >= 3: unlocked.append("golden_emperor")

    if level >= 30:   unlocked.append("frost_crystal")

    kill_count = db.execute(
        "SELECT COUNT(DISTINCT killed_date||monster_id) FROM monster_kills WHERE username=?",
        (username,)
    ).fetchone()[0] or 0
    if kill_count >= 100: unlocked.append("shadow_purple")

    stream_tier = penguin["stream_tier"] or 0
    if stream_tier >= 1: unlocked.append("neon_pink")

    return unlocked


def _validate_penguin_name(name, username):
    """Return cleaned name or raise ValueError."""
    import re
    name = name.strip()
    if not name:
        return username  # default to Twitch username
    if len(name) > 16:
        raise ValueError("Name must be 16 characters or fewer.")
    if not re.match(r'^[a-zA-Z0-9_\-]+$', name):
        raise ValueError("Name may only contain letters, numbers, underscores, and hyphens.")
    return name


@app.route("/penguin/colors")
def penguin_colors():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    db = get_db()
    penguin = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not penguin:
        db.close()
        return jsonify({"status": "error", "message": "Not found."})
    unlocked = _get_unlocked_colors(db, penguin)
    db.close()

    starters = {k: dict(v) for k, v in STARTER_COLORS.items()}
    locked   = {}
    for cid, cdata in LOCKED_COLORS.items():
        entry = dict(cdata)
        entry["unlocked"] = cid in unlocked
        locked[cid] = entry

    return jsonify({"status": "success", "starter": starters, "locked": locked, "player_unlocked": unlocked})


_PRESET_COLORS = [
    "#1a1a1a", "#1a1a4e", "#1a3a1a", "#4a1a1a", "#3a2a1a", "#3a3a3a",
    "#1a4a4a", "#4a1a4a", "#4a3a1a", "#1a1a3a", "#2a4a2a", "#4a2a2a",
    "#3a1a3a", "#2a3a4a", "#4a4a1a", "#1a3a3a", "#3a1a1a", "#2a2a4a",
    "#4a3a3a", "#1a4a1a",
]

@app.route("/penguin/creation-data")
def penguin_creation_data():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    db = get_db()
    p = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    db.close()
    if not p:
        return jsonify({"status": "error", "message": "Not found."})
    return jsonify({
        "status": "success",
        "username": username,
        "current_name": p["penguin_name"] or "",
        "current_color": _resolve_hex_color(p["penguin_color"] or "#1a1a1a"),
        "current_shape": p["penguin_shape"] or "normal",
        "current_social": p["trait_social"],
        "current_interest": p["trait_interest"],
        "current_quirk": p["trait_quirk"],
        "shapes": ["normal", "tall"],
        "preset_colors": _PRESET_COLORS,
    })


@app.route("/penguin/create", methods=["POST"])
def penguin_create():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    data = request.get_json(silent=True) or {}

    try:
        pname = _validate_penguin_name(data.get("penguin_name", ""), username)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)})

    raw_color = data.get("penguin_color", "#1a1a1a")
    pcolor = _resolve_hex_color(raw_color)

    pshape = data.get("penguin_shape", "normal")
    if pshape not in ("normal", "tall"):
        pshape = "normal"

    t_social   = data.get("trait_social")   if data.get("trait_social")   in SOCIAL_TRAITS   else None
    t_interest = data.get("trait_interest") if data.get("trait_interest") in INTEREST_TRAITS else None
    t_quirk    = data.get("trait_quirk")    if data.get("trait_quirk")    in QUIRK_TRAITS    else None

    db = get_db()
    db.execute(
        "UPDATE penguins SET penguin_name=?, penguin_color=?, penguin_shape=?, character_created=1, "
        "trait_social=?, trait_interest=?, trait_quirk=? WHERE username=?",
        (pname, pcolor, pshape, t_social, t_interest, t_quirk, username)
    )
    ensure_player_data(db, username)
    log_event(db, "character_created", f"{username} created their penguin as '{pname}' ({pcolor}, {pshape})", username)
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/penguin/reshape", methods=["POST"])
def penguin_reshape():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    data = request.get_json(silent=True) or {}

    try:
        pname = _validate_penguin_name(data.get("penguin_name", ""), username)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)})

    raw_color = data.get("penguin_color", "#1a1a1a")
    pcolor = _resolve_hex_color(raw_color)

    pshape = data.get("penguin_shape", "normal")
    if pshape not in ("normal", "tall"):
        pshape = "normal"

    db = get_db()
    penguin = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not penguin:
        db.close()
        return jsonify({"status": "error", "message": "Not found."})

    # Charge 2000 gold
    gold = get_gold(db, username)
    if gold < 2000:
        db.close()
        return jsonify({"status": "error", "message": "Not enough gold. Need 2,000 gold."})

    add_gold(db, username, -2000)

    t_social   = data.get("trait_social")   if data.get("trait_social")   in SOCIAL_TRAITS   else None
    t_interest = data.get("trait_interest") if data.get("trait_interest") in INTEREST_TRAITS else None
    t_quirk    = data.get("trait_quirk")    if data.get("trait_quirk")    in QUIRK_TRAITS    else None

    db.execute(
        "UPDATE penguins SET penguin_name=?, penguin_color=?, penguin_shape=?, "
        "trait_social=?, trait_interest=?, trait_quirk=? WHERE username=?",
        (pname, pcolor, pshape,
         t_social or penguin["trait_social"],
         t_interest or penguin["trait_interest"],
         t_quirk or penguin["trait_quirk"],
         username)
    )
    db.commit()
    log_event(db, "reshape", f"{username} reshaped their penguin at the Cursed Temple! ({pcolor}, {pshape})", username)
    db.close()
    return jsonify({"status": "success", "new_name": pname, "new_color": pcolor, "new_shape": pshape})


@app.route("/penguin/set-traits", methods=["POST"])
def penguin_set_traits():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    data = request.get_json(silent=True) or {}

    t_social   = data.get("trait_social")   if data.get("trait_social")   in SOCIAL_TRAITS   else None
    t_interest = data.get("trait_interest") if data.get("trait_interest") in INTEREST_TRAITS else None
    t_quirk    = data.get("trait_quirk")    if data.get("trait_quirk")    in QUIRK_TRAITS    else None

    db = get_db()
    penguin = db.execute(
        "SELECT trait_social, trait_interest, trait_quirk FROM penguins WHERE username=?", (username,)
    ).fetchone()
    if not penguin:
        db.close()
        return jsonify({"status": "error", "message": "Not found."})

    if penguin["trait_social"] or penguin["trait_interest"] or penguin["trait_quirk"]:
        db.close()
        return jsonify({"status": "error", "message": "Traits already set. Use Cursed Temple to change them."})

    db.execute(
        "UPDATE penguins SET trait_social=?, trait_interest=?, trait_quirk=? WHERE username=?",
        (t_social, t_interest, t_quirk, username)
    )
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/tutorial/complete", methods=["POST"])
def tutorial_complete():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    db = get_db()
    db.execute("UPDATE penguins SET tutorial_completed=1 WHERE username=?", (username,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/tutorial/advance", methods=["POST"])
def tutorial_advance():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    step     = int(data.get("step", 0))
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    db = get_db()
    db.execute("UPDATE penguins SET tutorial_step=? WHERE username=?", (step, username))
    # Completion threshold = one past the last step index (steps 0-16, so 17).
    # Must match TUTORIAL_TOTAL_STEPS in home.html's TutorialManager. Players
    # who completed under the old 12-step threshold already have
    # tutorial_completed=1 stored, so raising this doesn't re-open theirs.
    if step >= 17:
        db.execute("UPDATE penguins SET tutorial_completed=1 WHERE username=?", (username,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "step": step})


@app.route("/tutorial/reset", methods=["POST"])
def tutorial_reset():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    db = get_db()
    try:
        db.execute("UPDATE penguins SET tutorial_step=0, tutorial_completed=0 WHERE username=?", (username,))
        db.commit()
    except Exception as e:
        print(f"[Tutorial] Reset failed: {e}")
    db.close()
    return jsonify({"status": "success"})


@app.route("/tutorial/gift", methods=["POST"])
def tutorial_gift():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    step     = int(data.get("step", 0))
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    db = get_db()
    p  = db.execute("SELECT tutorial_rewards_given FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    rewards_given = json.loads(p["tutorial_rewards_given"] or "[]")
    if step in rewards_given:
        db.close()
        return jsonify({"status": "already_given", "message": "Reward already given."})

    ensure_resources(db, username)
    earned     = {}
    level_ups  = []

    STEP_GIFTS = {
        2:  {"fish": 50,  "gold": 30,  "xp": 50},
        4:  {"gold": 100, "herbs": 20, "bones": 10, "spell_fragments": 5},
        # Key 11 is the tutorial's FINAL farewell gift. The farewell step's
        # index in home.html has since moved (new steps were inserted before
        # it), but the gift stays keyed as 11 so players who already received
        # it under the old numbering aren't gifted twice -- the frontend
        # farewell step posts {step: 11} explicitly, whatever its index.
        11: {"gold": 200, "mayor_seals": 1},
        # N00Tbox intro step -- one free box to open during the tutorial.
        12: {"lootboxes": 1},
    }

    for resource, amount in STEP_GIFTS.get(step, {}).items():
        if amount <= 0:
            continue
        if resource == "gold":
            add_gold(db, username, amount)
            earned["gold"] = amount
        elif resource == "xp":
            _, lvl_rewards = award_xp(db, username, amount)
            level_ups.extend(lvl_rewards)
            earned["xp"] = amount
        elif resource == "mayor_seals":
            db.execute("UPDATE resources SET mayor_seals=mayor_seals+? WHERE username=?", (amount, username))
            earned["mayor_seals"] = amount
        elif resource == "lootboxes":
            # Reuses this route's own open connection (grant_lootbox's
            # optional-db param) -- we're mid-transaction here.
            grant_lootbox(username, amount, "tutorial", db=db)
            earned["lootboxes"] = amount
        else:
            db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
            earned[resource] = amount

    rewards_given.append(step)
    db.execute("UPDATE penguins SET tutorial_rewards_given=? WHERE username=?",
               (json.dumps(rewards_given), username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "earned": earned, "level_ups": level_ups})


@app.route("/tutorial/starter-fight", methods=["POST"])
def tutorial_starter_fight():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    db = get_db()
    p  = db.execute("SELECT tutorial_rewards_given FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    rewards_given = json.loads(p["tutorial_rewards_given"] or "[]")
    if 5 in rewards_given:
        db.close()
        return jsonify({"status": "already_given", "message": "Tutorial fight already completed."})

    ensure_resources(db, username)
    add_gold(db, username, 30)
    _, level_ups = award_xp(db, username, 20)

    template = random.choice(catalog.load_gear_templates(db=db)["common"])
    now      = int(time.time())
    db.execute(
        "INSERT INTO gear (username, name, type, slot, rarity, set_name, combat_power, equipped, obtained_at) "
        "VALUES (?,?,?,?,?,?,?,0,?)",
        (username, template["name"], "combat", template["slot"], "common",
         template["set_name"], template["combat_power"], now)
    )
    gear_id = db.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

    rewards_given.append(5)
    db.execute("UPDATE penguins SET tutorial_rewards_given=? WHERE username=?",
               (json.dumps(rewards_given), username))
    log_event(db, "combat", f"{username} defeated the Tutorial Snow Crab! 🦀 (Tutorial)", username)
    db.commit()
    db.close()
    return jsonify({
        "status":     "success",
        "earned":     {"gold": 30, "xp": 20},
        "gear_drop":  {"name": template["name"], "slot": template["slot"], "rarity": "common", "id": gear_id},
        "level_ups":  level_ups,
    })


@app.route("/tutorial/free-boutique", methods=["POST"])
def tutorial_free_boutique():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    item_id  = data.get("item_id", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    db = get_db()
    p  = db.execute("SELECT tutorial_rewards_given FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    rewards_given = json.loads(p["tutorial_rewards_given"] or "[]")
    if 7 in rewards_given:
        db.close()
        return jsonify({"status": "already_given", "message": "Free item already claimed."})

    item = next(
        (i for items in catalog.load_boutique_items(db=db).values() for i in items if i["id"] == item_id),
        None
    )
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})

    existing = db.execute(
        "SELECT 1 FROM gear WHERE username=? AND item_id=? AND type='cosmetic'",
        (username, item_id)
    ).fetchone()
    if existing:
        db.close()
        return jsonify({"status": "error", "message": "Already owned!"})

    now = int(time.time())
    db.execute(
        "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
        "VALUES (?,?,?,'cosmetic',?,'shop',0,?)",
        (username, item_id, item["name"], item["slot"], now)
    )
    rewards_given.append(7)
    db.execute("UPDATE penguins SET tutorial_rewards_given=? WHERE username=?",
               (json.dumps(rewards_given), username))
    log_event(db, "shop", f"{username} received a free gift from the Mayor: {item['name']}! 🎁", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "item": item})


@app.route("/tutorial/free-rest", methods=["POST"])
def tutorial_free_rest():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    db = get_db()
    p  = db.execute("SELECT energy, max_energy, tutorial_rewards_given FROM penguins WHERE username=?",
                    (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    rewards_given = json.loads(p["tutorial_rewards_given"] or "[]")
    if 8 in rewards_given:
        db.close()
        return jsonify({"status": "already_given"})

    max_e    = p["max_energy"] or 100
    restored = max_e - (p["energy"] or 0)
    db.execute("UPDATE penguins SET energy=? WHERE username=?", (max_e, username))
    rewards_given.append(8)
    db.execute("UPDATE penguins SET tutorial_rewards_given=? WHERE username=?",
               (json.dumps(rewards_given), username))
    db.commit()
    db.close()
    return jsonify({"status": "success", "new_energy": max_e, "restored": max(0, restored)})


@app.route("/help/dismissed/<username>")
def help_dismissed_list(username):
    db = get_db()
    rows = db.execute("SELECT help_key FROM help_dismissed WHERE username=?", (username,)).fetchall()
    db.close()
    return jsonify({"dismissed": [r["help_key"] for r in rows]})


@app.route("/help/dismiss", methods=["POST"])
def help_dismiss():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    help_key = data.get("help_key") or data.get("key", "")
    if not username or not help_key:
        return jsonify({"status": "error"})
    db = get_db()
    db.execute("INSERT OR IGNORE INTO help_dismissed (username, help_key) VALUES (?,?)", (username, help_key))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/help/reset", methods=["POST"])
def help_reset():
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error"})
    db = get_db()
    db.execute("DELETE FROM help_dismissed WHERE username=?", (username,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


# ── PENGUIN CARD & PUBLIC PROFILE ─────────────────────────────────────────────
import io
from PIL import Image, ImageDraw, ImageFont

CARD_FONT_PATH  = os.path.join(os.path.dirname(__file__), "static", "fonts", "PressStart2P-Regular.ttf")
_CARD_SPRITE_DIR = os.path.join(os.path.dirname(__file__), "static")
CARD_W, CARD_H  = 600, 340
LEFT_W           = 190

# Mirrors SHAPE_CONFIG in village_map.js (frameWidth/frameHeight) -- worn-item
# art under static/penguin_wearing/ is a 2-frame walk strip, so this is the
# size of frame 0 (the standing pose) to crop out of it before compositing.
_CARD_SHAPE_FRAME = {
    "normal": (32, 40),
    "tall":   (32, 50),
}
# Mirrors _AREA_FOLDER in village_map.js -- visual area -> sprite folder name.
_CARD_AREA_FOLDER = {"head": "hats", "body": "outfits", "feet": "footwear", "hand": "accessories"}

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


def _recolor_sprite_pil(sprite_rgba, hex_color):
    """PIL equivalent of recolor.js recolorPenguin() — same pixel logic, same constants.

    Body pixels are all RGB(0,0,0) in the current sprites, so scale=max(1.0, 0/26)=1.0
    and every body pixel is painted exactly the target color.  Belly (brightness>180)
    and beak/feet (orange guard) are left untouched, matching the JS behaviour.
    """
    if not hex_color or hex_color == "#1a1a1a":
        return sprite_rgba
    try:
        tr = int(hex_color[1:3], 16)
        tg = int(hex_color[3:5], 16)
        tb = int(hex_color[5:7], 16)
    except (ValueError, IndexError):
        return sprite_rgba

    result = sprite_rgba.copy()
    px = result.load()
    w, h = result.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            brightness = (r + g + b) / 3
            if brightness > 180:
                continue                                  # belly / white
            if r > 150 and 80 < g < 180 and b < 80:
                continue                                  # beak / feet (orange)
            scale = max(1.0, brightness / 26.0)
            px[x, y] = (
                min(255, int(tr * scale)),
                min(255, int(tg * scale)),
                min(255, int(tb * scale)),
                a,
            )
    return result

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
    # worn cosmetics (for card visual) -- slot is included so the card can
    # layer gear by visual area (_VISUAL_AREA), the same slot->area mapping
    # used everywhere else worn gear is drawn (e.g. _drawSidebarWornItems).
    cosmetics = db.execute(
        "SELECT item_id, slot FROM gear WHERE username=? AND type='cosmetic' AND worn=1",
        (username,)
    ).fetchall()
    cosmetic_ids = {c["item_id"] for c in cosmetics if c["item_id"]}
    worn_by_area = {}
    for c in cosmetics:
        if not c["item_id"]:
            continue
        area = _VISUAL_AREA.get(c["slot"])
        if area:
            worn_by_area[area] = c["item_id"]
    # Equipped card background + card frame -- these are two INDEPENDENT
    # slots, not a mutually-exclusive pair: the Inventory > Cosmetics tab's
    # equip route (/gear/cosmetics/equip) only sweeps the exact slot being
    # equipped, so a player can have one of each equipped at the same time
    # (the OTHER equip route, /card/background/equip, sweeps both slots
    # together, but it's not the only path a player can equip through).
    # Queried separately -- a single "LIMIT 1 across both slots" query would
    # silently return only one of the two and drop the other entirely.
    equipped_background_row = db.execute(
        "SELECT item_id, name FROM gear WHERE username=? AND type='cosmetic' "
        "AND slot='card_background' AND equipped=1 LIMIT 1",
        (username,)
    ).fetchone()
    equipped_frame_row = db.execute(
        "SELECT item_id, name FROM gear WHERE username=? AND type='cosmetic' "
        "AND slot='card_frame' AND equipped=1 LIMIT 1",
        (username,)
    ).fetchone()
    equipped_background = dict(equipped_background_row) if equipped_background_row else None
    equipped_frame       = dict(equipped_frame_row) if equipped_frame_row else None
    db.close()
    level, _, _ = xp_progress(p["xp"] or 0)
    pcolor   = _resolve_hex_color(p["penguin_color"] if p["penguin_color"] else "#1a1a1a")
    pname    = p["penguin_name"]  if p["penguin_name"]  else p["username"]
    return {
        "p": dict(p), "r": dict(r) if r else {}, "gold": gold,
        "titles": titles, "level": level,
        "top_contrib": dict(top_contrib) if top_contrib else None,
        "fav_job": fav_job, "total_hours": round(total_hours, 1),
        "top_ach": ach["achievement_id"] if ach else None,
        "cosmetic_ids": cosmetic_ids,
        "worn_by_area": worn_by_area,
        "penguin_name": pname,
        "penguin_color": pcolor,
        "penguin_shape": p["penguin_shape"] or "normal",
        "color_palette": {},
        "equipped_background": equipped_background,
        "equipped_frame": equipped_frame,
    }


def _generate_card_image(data):
    d   = data["p"]
    lv  = data["level"]
    img = Image.new("RGB", (CARD_W, CARD_H), _COLORS["bg"])
    # Card background — drawn first (behind everything, including the frame
    # border below) — try image file, fall back to theme color. Independent
    # of whatever card_frame is ALSO equipped (see _get_public_penguin).
    equipped_background = data.get("equipped_background")
    if equipped_background:
        item_id = equipped_background.get("item_id", "")
        bg_drawn = False
        # Try to load image
        bg_img_path = os.path.join(os.path.dirname(__file__), "static", "card_backgrounds",
                                   BUILDING_CARD_BACKGROUNDS.get(
                                       item_id.replace("card_bg_", ""), {}
                                   ).get("image", ""))
        if bg_img_path.endswith(".png") and os.path.exists(bg_img_path):
            try:
                bg_img = Image.open(bg_img_path).convert("RGB").resize((CARD_W, CARD_H), Image.LANCZOS)
                img.paste(bg_img)
                bg_drawn = True
            except Exception:
                pass
        if not bg_drawn:
            # Solid theme color fallback
            bid = item_id.replace("card_bg_", "")
            bg_info = BUILDING_CARD_BACKGROUNDS.get(bid)
            if bg_info:
                hex_col = bg_info["color"].lstrip("#")
                r_val = int(hex_col[0:2], 16)
                g_val = int(hex_col[2:4], 16)
                b_val = int(hex_col[4:6], 16)
                img.paste(Image.new("RGB", (CARD_W, CARD_H), (r_val, g_val, b_val)))
    draw = ImageDraw.Draw(img)

    # Frame border, drawn after (in front of) the background fill above.
    # golden_frame (Seal Shop) is currently the ONLY card_frame item with any
    # defined visual treatment -- it recolors the outer border. Checked
    # against the actually-EQUIPPED frame (equipped_frame) rather than
    # cosmetic_ids, which is built from worn=1 rows and can never be true
    # for card_frame items -- they have no visual area (_VISUAL_AREA) and no
    # wear UI at all, so this check previously could never fire for a real
    # player. The four CONTRIBUTION_MILESTONES frames (Contributor's Frame,
    # Builder's Canvas, Architect's Backdrop, Legendary Founder's Frame)
    # still have NO defined visual anywhere (no color, no overlay image) --
    # flagged for a design call rather than invented here.
    equipped_frame   = data.get("equipped_frame")
    frame_item_id    = equipped_frame.get("item_id", "") if equipped_frame else ""
    has_golden_frame = frame_item_id == "golden_frame"
    has_sparkle      = "animated_sparkle" in data["cosmetic_ids"]

    # Outer border
    border_col = _COLORS["orange"] if has_golden_frame else _COLORS["purple"]
    for i in range(3):
        draw.rectangle([i, i, CARD_W-1-i, CARD_H-1-i], outline=border_col)

    # Divider line
    for y in range(4, CARD_H-4):
        draw.point((LEFT_W, y), fill=(50, 50, 50))

    # ── LEFT: full-height portrait, left-aligned ──
    # Target box is now (almost) the entire left panel instead of a small
    # fixed 80x80 corner box -- _SPRITE_MARGIN keeps clear of the outer
    # border/divider, and an extra bottom margin keeps clear of the URL
    # footer drawn later. Same aspect-ratio-preserving scale-by-limiting-
    # dimension as before (unchanged), just against a much bigger box.
    _SPRITE_MARGIN     = 4
    _SPRITE_BOTTOM_PAD = 20  # extra clearance above the URL footer
    _SPRITE_BOX_W = LEFT_W - _SPRITE_MARGIN * 2
    _SPRITE_BOX_H = CARD_H - _SPRITE_MARGIN - _SPRITE_BOTTOM_PAD
    try:
        _shape = d.get("penguin_shape") or "normal"
        _sprite_file = f"penguin_{_shape}_static.png"
        _sprite_path = os.path.join(_CARD_SPRITE_DIR, _sprite_file)
        if not os.path.exists(_sprite_path):
            _sprite_path = os.path.join(_CARD_SPRITE_DIR, "penguin_normal_static.png")
        raw = Image.open(_sprite_path).convert("RGBA")
        # Scale against the shape's nominal wearable-frame box (fw x fh),
        # NOT the static sprite's own raster size -- mirrors home.html's
        # _drawPenguinOnCanvas/_drawSidebarWornItems, which scale/position
        # against SHAPE_CONFIG's frameWidth/frameHeight for exactly this
        # reason. penguin_normal_static.png is only 32px tall vs. the
        # wearable-art convention of 40px (8px of headroom reserved above
        # the head for hats), so scaling/cropping gear against the raw
        # sprite's own 32px height stretched every "normal"-shape gear
        # layer ~1.25x too tall and floating without that headroom.
        # "tall" isn't affected -- its static sprite is already 50px,
        # matching its frame exactly.
        fw, fh = _CARD_SHAPE_FRAME.get(_shape, _CARD_SHAPE_FRAME["normal"])
        scale = min(_SPRITE_BOX_W / fw, _SPRITE_BOX_H / fh)
        new_w = max(1, round(raw.width * scale))
        new_h = max(1, round(raw.height * scale))
        sprite = raw.resize((new_w, new_h), Image.NEAREST)
        pcolor = data.get("penguin_color", "#1a1a1a")
        sprite = _recolor_sprite_pil(sprite, pcolor)
        bg_patch = Image.new("RGB", (_SPRITE_BOX_W, _SPRITE_BOX_H), _COLORS["bg"])

        # The frame box itself is left-aligned (x=0) and vertically centered
        # in the sprite box -- same placement as before. Gear anchors to
        # this frame box's own top-left corner; the base sprite is
        # bottom-anchored within it (pushed down by the frame/sprite height
        # difference) so its feet land on the frame's bottom edge exactly
        # where gear art (which already spans the full frame, headroom
        # included) expects the body to be -- same bottom-anchor correction
        # as _drawPenguinOnCanvas's "(cfg.frameHeight - srcH) * scale" term.
        frame_h_scaled = fh * scale
        frame_x = 0
        frame_y = (_SPRITE_BOX_H - frame_h_scaled) / 2
        gear_xy = (round(frame_x), round(frame_y))
        paste_xy = (round(frame_x), round(frame_y + (fh - raw.height) * scale))
        bg_patch.paste(sprite, paste_xy, mask=sprite.split()[3])

        # Worn gear layers, same order/folder-mapping as home.html's
        # _drawSidebarWornItems: footwear -> outfit -> hat -> accessory.
        # Each overlay is cropped to its native frame (fw x fh) and
        # resized/anchored against the SAME frame box the base sprite used
        # above (gear_xy), so gear lands exactly where its own art was
        # designed to sit relative to the body, not shifted/oversized
        # relative to the enlarged base sprite.
        for area in ("feet", "body", "head", "hand"):
            item_id = data.get("worn_by_area", {}).get(area)
            if not item_id:
                continue
            folder = _CARD_AREA_FOLDER[area]
            item_path = os.path.join(_CARD_SPRITE_DIR, "penguin_wearing", _shape, folder, f"{item_id}.png")
            if not os.path.exists(item_path):
                continue  # tolerate missing overlay art, same as SpriteLoader's fallback
            try:
                overlay = Image.open(item_path).convert("RGBA")
                # Overlay art is a 2-frame walk strip -- crop out frame 0
                # (the standing pose), same source region _drawSidebarWornItems
                # samples via its drawImage source-rect.
                crop_w, crop_h = min(fw, overlay.width), min(fh, overlay.height)
                overlay = overlay.crop((0, 0, crop_w, crop_h))
                ow = max(1, round(crop_w * scale))
                oh = max(1, round(crop_h * scale))
                overlay = overlay.resize((ow, oh), Image.NEAREST)
                bg_patch.paste(overlay, gear_xy, mask=overlay.split()[3])
            except Exception:
                continue

        img.paste(bg_patch, (_SPRITE_MARGIN, _SPRITE_MARGIN))
    except Exception:
        pass

    # ── RIGHT: ID-card-style text panel ──
    # Dark, high-opacity panel behind the whole text column so every field
    # stays legible regardless of the equipped background image/color. Done
    # as an RGBA alpha-composite (only the panel rectangle gets partial
    # alpha; everywhere else is untouched) rather than flattening the whole
    # canvas, so the sprite/border/divider drawn above are unaffected.
    panel_box = (LEFT_W + 4, 4, CARD_W - 4, CARD_H - 4)
    _panel_overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    ImageDraw.Draw(_panel_overlay).rectangle(panel_box, fill=(*_COLORS["dark"], round(255 * 0.88)))
    # Back to RGB immediately -- _generate_card_image has always returned an
    # RGB image (getpixel() callers throughout the codebase/tests expect
    # 3-tuples), so the RGBA intermediate used for the alpha-composite must
    # not leak out as the function's return mode.
    img = Image.alpha_composite(img.convert("RGBA"), _panel_overlay).convert("RGB")
    draw = ImageDraw.Draw(img)  # re-bind: alpha_composite returns a new image

    username    = d.get("username", "UNKNOWN")
    active_title = d.get("active_title")
    prestige    = d.get("prestige") or 0
    job_str     = _job_label(d.get("job"))
    gold_val    = data.get("gold", 0)
    fav         = data.get("fav_job")
    total_h     = data.get("total_hours", 0)
    from level_config import get_total_gathering_bonus
    gb = get_total_gathering_bonus(lv)

    rx           = LEFT_W + 18
    value_x      = rx + 78     # fixed value column so rows align, ID-card style
    divider_x0   = LEFT_W + 10
    divider_x1   = CARD_W - 10
    label_font   = _font(7)
    ry = 18
    draw.text((rx, ry), "PENGUIN VILLAGE", font=_font(12), fill=_COLORS["purple"])
    ry += 24
    draw.line([(divider_x0, ry), (divider_x1, ry)], fill=(70, 70, 80))
    ry += 10

    def _field(label, value, value_fill, value_font_size):
        nonlocal ry
        draw.text((rx, ry), label, font=label_font, fill=_COLORS["gray"])
        draw.text((value_x, ry - 2), value, font=_font(value_font_size), fill=value_fill)
        ry += 26
        draw.line([(divider_x0, ry), (divider_x1, ry)], fill=(60, 60, 70))
        ry += 10

    _field("NAME",  username.upper(), _COLORS["white"], 11)
    if prestige > 0:
        _field("RANK", "★" * prestige, _COLORS["pink"], 11)
    _field("LEVEL", str(lv), _COLORS["white"], 12)
    _field("JOB",   job_str.upper(), _COLORS["orange"], 9)
    _field("GOLD",  str(gold_val), _COLORS["orange"], 9)
    if active_title:
        _field("TITLE", f'"{active_title}"', _COLORS["purple"], 8)
    if fav:
        _field("BEST AT", fav.upper(), _COLORS["white"], 8)
    _field("HOURS", str(total_h), _COLORS["gray"], 8)
    if gb > 0:
        _field("GATHER", f"+{gb}%", _COLORS["green"], 8)

    # Sparkle corners
    if has_sparkle:
        for cx, cy in [(10,10),(CARD_W-20,10),(10,CARD_H-20),(CARD_W-20,CARD_H-20)]:
            draw.text((cx, cy), "✦", font=_font(8), fill=_COLORS["pink"])

    # URL footer
    draw.text((CARD_W//2, CARD_H - 12),
              f"mbarepingu.com/penguin/{username.lower()}",
              font=_font(5), fill=_COLORS["gray"], anchor="mm")

    # Watermark, composited last so it sits above everything -- alpha-
    # multiplied (each pixel's own alpha scaled by 0.4), not a flat 40%
    # layer, so semi-transparent parts of the logo art stay proportionally
    # lighter rather than all being clamped to one opacity. Small footprint
    # in the bottom-right corner so it can't obscure the ID-card text panel.
    watermark_path = os.path.join(os.path.dirname(__file__), "static", "watermark_logo.png")
    if os.path.exists(watermark_path):
        try:
            wm = Image.open(watermark_path).convert("RGBA")
            wm_w = max(1, round(CARD_W * 0.15))
            wm_scale = wm_w / wm.width
            wm_h = max(1, round(wm.height * wm_scale))
            wm = wm.resize((wm_w, wm_h), Image.LANCZOS)
            r, g, b, a = wm.split()
            a = a.point(lambda px: round(px * 0.4))
            wm.putalpha(a)
            wm_margin = 8
            img.paste(wm, (CARD_W - wm_w - wm_margin, CARD_H - wm_h - wm_margin), mask=wm)
        except Exception:
            pass

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
        penguin_shape=d.get("penguin_shape") or "normal",
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
        card_cache_bust=int(time.time()),
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
        penguin_shape=d.get("penguin_shape") or "normal",
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
        card_cache_bust=int(time.time()),
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
    # as_attachment so the DOWNLOAD button (downloadCard() in home.html)
    # actually triggers a file download instead of just opening the PNG
    # inline in the new tab it window.open()s.
    return send_file(buf, mimetype="image/png", as_attachment=True,
                      download_name=f"{username}_card.png")


@app.route("/card/<username>/share", methods=["POST"])
def share_card_to_twitch(username):
    # TODO StreamerBot: wire this up to the real StreamerBot integration --
    # no StreamerBot endpoints exist in this codebase yet, so this only logs
    # the request and returns a not-implemented response for now. Mirrors
    # share_event_to_twitch's stub shape exactly.
    requester = session.get("username")
    print(f"[CardShare] {requester or 'anonymous'} requested Twitch share for card username={username}")
    return jsonify({"status": "not_implemented", "message": "Twitch sharing is coming soon."}), 501


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
    username = session.get("username")
    if username != MAYOR_USERNAME:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
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
    now = int(time.time())
    # Online threshold: seen within 3 minutes (2× the 90s client ping interval)
    online_cutoff = now - 180
    db = get_db()
    rows = db.execute(
        """SELECT p.username, p.penguin_name, p.penguin_color, p.penguin_shape,
                  p.job, p.level, p.prestige, p.active_title, p.last_active
           FROM penguins p
           WHERE p.character_created = 1
           ORDER BY p.last_active DESC
           LIMIT 50""",
    ).fetchall()

    # Build worn_items map for all penguins in one query
    worn_map = {}
    if rows:
        unames = tuple(r["username"] for r in rows)
        placeholders = ",".join("?" * len(unames))
        worn_rows = db.execute(
            f"SELECT username, slot, item_id FROM gear WHERE worn=1 AND username IN ({placeholders})",
            unames
        ).fetchall()
        for w in worn_rows:
            area = _VISUAL_AREA.get(w["slot"])
            if area and w["item_id"]:
                worn_map.setdefault(w["username"], {})[area] = w["item_id"]

    db.close()

    penguins = []
    for r in rows:
        job       = r["job"]
        pcolor    = r["penguin_color"] or "#1a1a1a"
        body_color = _resolve_hex_color(pcolor)
        pname     = r["penguin_name"] or r["username"]
        is_online = (r["last_active"] or 0) > online_cutoff
        entry = {
            "username":      r["username"],
            "display_name":  pname,
            "penguin_color": body_color,
            "penguin_shape": r["penguin_shape"] or "normal",
            "job":           job,
            "level":         r["level"] or 1,
            "prestige":      r["prestige"] or 0,
            "active_title":  r["active_title"],
            "is_online":     is_online,
            "worn_items":    worn_map.get(r["username"], {}),
        }
        # Only working penguins get a home tile — jobless penguins get a
        # random walkable spawn on the client side via randomWalkableTile()
        if job and job in _BUILDING_HOME_TILES:
            home = _BUILDING_HOME_TILES[job]
            entry["startGridX"] = home[0]
            entry["startGridY"] = home[1]
        penguins.append(entry)

    return jsonify({"penguins": penguins})


# ── PRESENCE PING ─────────────────────────────────────────────────────────────
# Lightweight heartbeat — client POSTs every 90s to keep last_active fresh.
# Online detection: last_active > now - 180 (3 min window).
# Reusable: any feature needing "is player currently online?" queries
# penguins.last_active against this same threshold.

@app.route("/presence/ping", methods=["POST"])
def presence_ping():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"status": "skip"})
    now = int(time.time())
    db  = get_db()
    db.execute("UPDATE penguins SET last_active=? WHERE username=?", (now, username))
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


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

    # ── Raid Debug: current cycle status (read-only, refreshed on page load) ──
    current_challenge = db.execute(
        "SELECT * FROM weekly_challenges ORDER BY id DESC LIMIT 1"
    ).fetchone()
    current_raid = db.execute("SELECT * FROM raid_state ORDER BY id DESC LIMIT 1").fetchone()
    raid_participant_count = 0
    if current_raid:
        raid_participant_count = db.execute(
            "SELECT COUNT(*) as cnt FROM raid_participants WHERE raid_id=?", (current_raid["id"],)
        ).fetchone()["cnt"]
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
        cosmetic_slots=COSMETIC_SLOTS,
        current_challenge=dict(current_challenge) if current_challenge else None,
        current_raid=dict(current_raid) if current_raid else None,
        raid_participant_count=raid_participant_count,
        weekly_metric_types=WEEKLY_METRIC_TYPES,
        raid_settings_all=raid_settings.get_all_settings(),
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


@app.route("/mayor/gift/gear", methods=["POST"])
def mayor_gift_gear():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    slot     = data.get("slot", "").strip()
    item_id  = data.get("item_id", "").strip()
    name     = data.get("name", "").strip()
    if not username or not slot or not item_id or not name:
        return jsonify({"status": "error", "message": "username, slot, item_id, and name required."})
    COMBAT_SLOTS    = {"weapon", "armor", "helmet", "boots"}
    COSMETIC_SLOTS2 = {"hat", "outfit", "footwear", "accessory"}
    if slot not in COMBAT_SLOTS | COSMETIC_SLOTS2:
        return jsonify({"status": "error", "message": "Invalid slot."})
    item_type = "combat" if slot in COMBAT_SLOTS else "cosmetic"
    db = get_db()
    p  = db.execute("SELECT id FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": f"Player '{username}' not found."})
    db.execute(
        "INSERT INTO gear (username, item_id, name, type, slot, rarity, equipped, obtained_at) "
        "VALUES (?,?,?,?,?,'mayor_gift',0,?)",
        (username, item_id, name, item_type, slot, int(time.time()))
    )
    log_event(db, "village", f"👑 The Mayor gifted {username} the gear: {name} ({slot})! ⚔️", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "recipient": username, "item_id": item_id, "slot": slot})


@app.route("/mayor/items/all", methods=["GET"])
def mayor_items_all():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    items = []

    # boutique_items (purchasable cosmetics: hat/outfit/footwear/accessory)
    for _category, entries in catalog.load_boutique_items().items():
        for entry in entries:
            items.append({
                "id":     entry["id"],
                "name":   entry["name"],
                "slot":   entry["slot"],
                "rarity": entry.get("tier", "common"),
                "source": "boutique",
            })

    # barracks_shop (purchasable combat gear with rarity)
    for rarity, entries in catalog.load_barracks_shop().items():
        for entry in entries:
            items.append({
                "id":     entry["id"],
                "name":   entry["name"],
                "slot":   entry["slot"],
                "rarity": rarity,
                "source": "barracks",
            })

    # de-duplicate by item_id (first occurrence wins)
    seen = set()
    unique_items = []
    for item in items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique_items.append(item)

    # group by slot for the response
    by_slot = {}
    for item in unique_items:
        by_slot.setdefault(item["slot"], []).append(item)

    # print full list to terminal
    print("\n=== /mayor/items/all — full item list ===")
    for slot_name in sorted(by_slot):
        print(f"  [{slot_name}]")
        for it in sorted(by_slot[slot_name], key=lambda x: x["name"]):
            print(f"    {it['id']:30s}  {it['name']:30s}  {it['rarity']:12s}  ({it['source']})")
    print(f"  Total: {len(unique_items)} items across {len(by_slot)} slots")
    print("=========================================\n")

    return jsonify({"status": "success", "by_slot": by_slot, "items": unique_items})


# ── MAYOR ITEMS TAB: catalog CRUD (barracks_shop/boutique_items/          ──
# ── gear_templates/set_bonuses -- see catalog.py for the read-side       ──
# ── loaders these tables also back) ─────────────────────────────────────
_CATALOG_TABLES = {
    "barracks_shop":  {"pk": "id",       "columns": ["id", "name", "slot", "rarity", "combat_power", "cost", "event_exclusive"]},
    "boutique_items": {"pk": "id",       "columns": ["id", "name", "category", "slot", "price", "tier", "event_exclusive"]},
    "gear_templates": {"pk": "id",       "columns": ["id", "name", "slot", "rarity", "set_name", "combat_power"]},
    "set_bonuses":    {"pk": "set_name", "columns": ["set_name", "pieces_needed", "bonus_2pc_cp", "bonus_2pc_desc",
                                                      "bonus_3pc_cp", "bonus_3pc_desc", "secret_cosmetic_required",
                                                      "secret_cp", "secret_desc"]},
}
_CATALOG_COMBAT_SLOTS   = {"weapon", "armor", "helmet", "boots"}
_CATALOG_COSMETIC_SLOTS = {"hat", "outfit", "footwear", "accessory"}
_CATALOG_RARITIES       = {"common", "uncommon", "rare", "epic", "legendary"}
_CATALOG_RESOURCES      = {"gold", "fish", "herbs", "blood_gems", "bones", "spell_fragments", "ice_blocks"}
_CATALOG_TIERS          = {"cheap", "mid", "expensive"}
_CATALOG_CATEGORIES     = {"hats", "outfits", "footwear", "accessories"}
# id (barracks_shop/boutique_items/gear_templates) is a slug: matches the
# style every existing seeded id already uses, and keeps it safe to embed
# in an onclick="...('${id}')" attribute in the Items tab UI without any
# HTML/JS escaping edge cases. set_name is a display name (existing values
# are "Word Word" style), so it's allowed spaces but nothing else that
# could break out of that same attribute context.
_CATALOG_ID_RE       = re.compile(r'^[a-z0-9_]+$')
_CATALOG_SET_NAME_RE = re.compile(r"^[A-Za-z0-9' ]+$")


def _validate_catalog_row(catalog_name, data):
    """Validate + shape a create/edit payload for one catalog table into a
    dict of column -> stored value (cost pre-JSON-encoded, booleans as 0/1).
    Raises ValueError with a player-facing message on anything invalid.
    id/set_name (the PK) is required and, for barracks_shop/boutique_items,
    is the same id gear rows reference forever -- the frontend treats it as
    immutable after creation (not enforced here beyond "must be present";
    the id simply becomes the row's new content on any save, same as every
    other field, so the UI is responsible for not offering to edit it)."""
    if catalog_name == "barracks_shop":
        id_   = (data.get("id") or "").strip()
        name  = (data.get("name") or "").strip()
        slot  = data.get("slot")
        rarity = data.get("rarity")
        combat_power = data.get("combat_power")
        cost  = data.get("cost") or {}
        event_exclusive = bool(data.get("event_exclusive"))
        if not id_ or not name:
            raise ValueError("id and name are required.")
        if not _CATALOG_ID_RE.match(id_):
            raise ValueError("id must be lowercase letters/digits/underscores only (e.g. iron_sword).")
        if slot not in _CATALOG_COMBAT_SLOTS:
            raise ValueError(f"slot must be one of {sorted(_CATALOG_COMBAT_SLOTS)}.")
        if rarity not in _CATALOG_RARITIES:
            raise ValueError(f"rarity must be one of {sorted(_CATALOG_RARITIES)}.")
        if not isinstance(combat_power, int) or isinstance(combat_power, bool) or combat_power < 0:
            raise ValueError("combat_power must be a non-negative integer.")
        if not isinstance(cost, dict) or not cost:
            raise ValueError("cost must be a non-empty resource -> amount mapping.")
        for res, amt in cost.items():
            if res not in _CATALOG_RESOURCES:
                raise ValueError(f"unknown resource in cost: {res}")
            if not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0:
                raise ValueError(f"cost[{res}] must be a positive integer.")
        return {"id": id_, "name": name, "slot": slot, "rarity": rarity,
                "combat_power": combat_power, "cost": json.dumps(cost),
                "event_exclusive": int(event_exclusive)}

    if catalog_name == "boutique_items":
        id_   = (data.get("id") or "").strip()
        name  = (data.get("name") or "").strip()
        category = data.get("category")
        slot  = data.get("slot")
        price = data.get("price")
        tier  = data.get("tier")
        event_exclusive = bool(data.get("event_exclusive"))
        if not id_ or not name:
            raise ValueError("id and name are required.")
        if not _CATALOG_ID_RE.match(id_):
            raise ValueError("id must be lowercase letters/digits/underscores only (e.g. baseball_cap).")
        if category not in _CATALOG_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(_CATALOG_CATEGORIES)}.")
        if slot not in _CATALOG_COSMETIC_SLOTS:
            raise ValueError(f"slot must be one of {sorted(_CATALOG_COSMETIC_SLOTS)}.")
        if not isinstance(price, int) or isinstance(price, bool) or price < 0:
            raise ValueError("price must be a non-negative integer.")
        if tier not in _CATALOG_TIERS:
            raise ValueError(f"tier must be one of {sorted(_CATALOG_TIERS)}.")
        return {"id": id_, "name": name, "category": category, "slot": slot,
                "price": price, "tier": tier, "event_exclusive": int(event_exclusive)}

    if catalog_name == "gear_templates":
        id_   = (data.get("id") or "").strip()
        name  = (data.get("name") or "").strip()
        slot  = data.get("slot")
        rarity = data.get("rarity")
        set_name = (data.get("set_name") or "").strip() or None
        combat_power = data.get("combat_power")
        if not id_ or not name:
            raise ValueError("id and name are required.")
        if not _CATALOG_ID_RE.match(id_):
            raise ValueError("id must be lowercase letters/digits/underscores only (e.g. rusty_sword_weapon_common).")
        if slot not in _CATALOG_COMBAT_SLOTS:
            raise ValueError(f"slot must be one of {sorted(_CATALOG_COMBAT_SLOTS)}.")
        if rarity not in _CATALOG_RARITIES:
            raise ValueError(f"rarity must be one of {sorted(_CATALOG_RARITIES)}.")
        if set_name is not None and not _CATALOG_SET_NAME_RE.match(set_name):
            raise ValueError("set_name may only contain letters, digits, spaces, and apostrophes.")
        if not isinstance(combat_power, int) or isinstance(combat_power, bool) or combat_power < 0:
            raise ValueError("combat_power must be a non-negative integer.")
        return {"id": id_, "name": name, "slot": slot, "rarity": rarity,
                "set_name": set_name, "combat_power": combat_power}

    if catalog_name == "set_bonuses":
        set_name = (data.get("set_name") or "").strip()
        pieces_needed = data.get("pieces_needed")
        bonus_2pc_cp   = data.get("bonus_2pc_cp")
        bonus_2pc_desc = (data.get("bonus_2pc_desc") or "").strip()
        bonus_3pc_cp   = data.get("bonus_3pc_cp")
        bonus_3pc_desc = (data.get("bonus_3pc_desc") or "").strip()
        secret_cosmetic_required = (data.get("secret_cosmetic_required") or "").strip() or None
        secret_cp   = data.get("secret_cp")
        secret_desc = (data.get("secret_desc") or "").strip()
        if not set_name:
            raise ValueError("set_name is required.")
        if not _CATALOG_SET_NAME_RE.match(set_name):
            raise ValueError("set_name may only contain letters, digits, spaces, and apostrophes.")
        if secret_cosmetic_required is not None and not _CATALOG_SET_NAME_RE.match(secret_cosmetic_required):
            raise ValueError("secret_cosmetic_required may only contain letters, digits, spaces, and apostrophes.")
        for label, val in (("pieces_needed", pieces_needed), ("bonus_2pc_cp", bonus_2pc_cp),
                            ("bonus_3pc_cp", bonus_3pc_cp), ("secret_cp", secret_cp)):
            if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                raise ValueError(f"{label} must be a non-negative integer.")
        if not bonus_2pc_desc or not bonus_3pc_desc or not secret_desc:
            raise ValueError("bonus_2pc_desc, bonus_3pc_desc, and secret_desc are all required.")
        return {"set_name": set_name, "pieces_needed": pieces_needed,
                "bonus_2pc_cp": bonus_2pc_cp, "bonus_2pc_desc": bonus_2pc_desc,
                "bonus_3pc_cp": bonus_3pc_cp, "bonus_3pc_desc": bonus_3pc_desc,
                "secret_cosmetic_required": secret_cosmetic_required,
                "secret_cp": secret_cp, "secret_desc": secret_desc}

    raise ValueError("Unknown catalog.")


def _catalog_delete_safety_check(db, catalog_name, row):
    """Returns (severity, message): 'block' refuses the delete outright
    (even with confirm=true) because it would crash live gameplay, not just
    look empty; 'warn' requires the caller to resend with confirm=true but
    otherwise proceeds; None means delete freely.

    gear_templates is the one hard-block case: generate_gear_drop() and
    _generate_lootbox_gear() do random.choice(templates_for_that_rarity),
    which raises IndexError on an empty list -- deleting the LAST template
    for a rarity that a monster tier still rolls would crash the very next
    drop of that rarity, not just render an empty admin list.

    set_bonuses only warns (never blocks), per explicit product decision:
    editing/deleting it already changes effective combat power live for
    anyone with matching pieces equipped (calculate_set_bonuses() looks the
    set up in the CURRENT set_bonuses table every time, not from anything
    stored on the gear row) -- same category as other live-tunable knobs
    (buffs, raid settings) that already take effect immediately."""
    if catalog_name == "gear_templates":
        rarity = row["rarity"]
        remaining = db.execute(
            "SELECT COUNT(*) c FROM gear_templates WHERE rarity=? AND id != ?", (rarity, row["id"])
        ).fetchone()["c"]
        if remaining == 0:
            reachable = any(w.get(rarity, 0) > 0 for w in _GEAR_DROP_RARITY_WEIGHTS.values())
            if reachable:
                return ("block",
                        f"This is the LAST {rarity} gear template, and at least one monster tier "
                        f"still rolls {rarity} drops -- deleting it would crash the next {rarity} "
                        f"drop. Add another {rarity} template before deleting this one.")
            return ("warn", f"This is the last {rarity} gear template. No monster tier currently "
                             f"rolls {rarity} drops, so this is safe, but double-check first.")
    elif catalog_name == "barracks_shop":
        rarity = row["rarity"]
        remaining = db.execute(
            "SELECT COUNT(*) c FROM barracks_shop WHERE rarity=? AND id != ?", (rarity, row["id"])
        ).fetchone()["c"]
        if remaining == 0:
            return ("warn", f"This is the last {rarity}-tier item in the Barracks shop -- deleting "
                             f"it leaves that rarity tab empty (the shop still renders fine, just "
                             f"nothing to buy in {rarity}).")
    elif catalog_name == "boutique_items":
        category = row["category"]
        remaining = db.execute(
            "SELECT COUNT(*) c FROM boutique_items WHERE category=? AND id != ?", (category, row["id"])
        ).fetchone()["c"]
        if remaining == 0:
            return ("warn", f"This is the last item in the {category} category -- deleting it "
                             f"leaves that Boutique category empty.")
    elif catalog_name == "set_bonuses":
        set_name = row["set_name"]
        affected = db.execute(
            "SELECT username, COUNT(*) c FROM gear WHERE set_name=? AND equipped=1 AND type='combat' "
            "GROUP BY username HAVING c >= 2",
            (set_name,)
        ).fetchall()
        if affected:
            names = ", ".join(a["username"] for a in affected[:5])
            more  = f" (+{len(affected)-5} more)" if len(affected) > 5 else ""
            return ("warn", f"{len(affected)} player(s) currently have 2+ equipped {set_name} pieces "
                             f"and will immediately lose this set bonus if deleted: {names}{more}.")
    return (None, None)


@app.route("/mayor/catalog/<catalog_name>")
def mayor_catalog_list(catalog_name):
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    if catalog_name not in _CATALOG_TABLES:
        return jsonify({"status": "error", "message": "Unknown catalog."}), 404
    db   = get_db()
    rows = db.execute(f"SELECT * FROM {catalog_name} ORDER BY rowid").fetchall()
    db.close()
    items = [dict(r) for r in rows]
    if catalog_name == "barracks_shop":
        for it in items:
            it["cost"] = json.loads(it["cost"])
    return jsonify({"status": "success", "items": items})


@app.route("/mayor/catalog/<catalog_name>/save", methods=["POST"])
def mayor_catalog_save(catalog_name):
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    if catalog_name not in _CATALOG_TABLES:
        return jsonify({"status": "error", "message": "Unknown catalog."}), 404
    cfg  = _CATALOG_TABLES[catalog_name]
    data = request.get_json(silent=True) or {}
    try:
        row = _validate_catalog_row(catalog_name, data)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)})

    db = get_db()
    pk_col = cfg["pk"]
    pk_val = row[pk_col]
    is_edit = db.execute(f"SELECT 1 FROM {catalog_name} WHERE {pk_col}=?", (pk_val,)).fetchone() is not None

    # set_bonuses: editing an existing entry changes live combat power for
    # anyone with matching pieces equipped right now (see
    # _catalog_delete_safety_check's docstring) -- warn once, same
    # warn-don't-block UX as delete, per explicit product decision.
    if catalog_name == "set_bonuses" and is_edit and not data.get("confirm"):
        affected = db.execute(
            "SELECT username, COUNT(*) c FROM gear WHERE set_name=? AND equipped=1 AND type='combat' "
            "GROUP BY username HAVING c >= 2",
            (pk_val,)
        ).fetchall()
        if affected:
            names = ", ".join(a["username"] for a in affected[:5])
            more  = f" (+{len(affected)-5} more)" if len(affected) > 5 else ""
            db.close()
            return jsonify({"status": "warning", "message":
                f"{len(affected)} player(s) currently have 2+ equipped {pk_val} pieces and will "
                f"immediately feel this change: {names}{more}."})

    cols = cfg["columns"]
    col_list      = ",".join(cols)
    placeholders  = ",".join("?" for _ in cols)
    update_clause = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk_col)
    db.execute(
        f"INSERT INTO {catalog_name} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT({pk_col}) DO UPDATE SET {update_clause}",
        [row[c] for c in cols]
    )
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": f"{pk_val} {'updated' if is_edit else 'created'}.", "is_edit": is_edit})


@app.route("/mayor/catalog/<catalog_name>/delete", methods=["POST"])
def mayor_catalog_delete(catalog_name):
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    if catalog_name not in _CATALOG_TABLES:
        return jsonify({"status": "error", "message": "Unknown catalog."}), 404
    cfg    = _CATALOG_TABLES[catalog_name]
    data   = request.get_json(silent=True) or {}
    pk_col = cfg["pk"]
    pk_val = (data.get(pk_col) or "").strip()
    confirmed = bool(data.get("confirm"))
    if not pk_val:
        return jsonify({"status": "error", "message": f"{pk_col} required."})

    db  = get_db()
    row = db.execute(f"SELECT * FROM {catalog_name} WHERE {pk_col}=?", (pk_val,)).fetchone()
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "Not found."})

    severity, message = _catalog_delete_safety_check(db, catalog_name, dict(row))
    if severity == "block":
        db.close()
        return jsonify({"status": "error", "message": message})
    if severity == "warn" and not confirmed:
        db.close()
        return jsonify({"status": "warning", "message": message})

    db.execute(f"DELETE FROM {catalog_name} WHERE {pk_col}=?", (pk_val,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": f"{pk_val} deleted."})


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
            log_event(db, "building_levelup",
                      f"🏗️ {cfg['name']} has been upgraded to level {next_level}!",
                      MAYOR_USERNAME)
            current_level = next_level
            leveled_up = True
        else:
            break

    log_event(db, "village",
              f"👑 The Mayor boosted {cfg['name']} with {amount} {_resource_display_name(resource_type)}!",
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


@app.route("/mayor/players")
def mayor_list_players():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    db = get_db()
    players = db.execute(
        "SELECT username, penguin_name, level, character_created, tutorial_completed, last_active FROM penguins ORDER BY last_active DESC"
    ).fetchall()
    db.close()
    return jsonify({"status": "success", "players": [dict(p) for p in players], "total": len(players)})


@app.route("/mayor/delete-player", methods=["POST"])
def mayor_delete_player():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data = request.get_json(silent=True) or {}
    username_to_delete = (data.get("username") or "").strip()
    if not username_to_delete:
        return jsonify({"status": "error", "message": "No username provided"})
    if username_to_delete == MAYOR_USERNAME:
        return jsonify({"status": "error", "message": "Cannot delete the Mayor!"})
    db = get_db()
    if not db.execute("SELECT 1 FROM penguins WHERE username=?", (username_to_delete,)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": f"Player '{username_to_delete}' not found"})
    delete_queries = [
        ("penguins",                      "DELETE FROM penguins WHERE username=?",                               (username_to_delete,)),
        ("resources",                     "DELETE FROM resources WHERE username=?",                              (username_to_delete,)),
        ("igloos",                        "DELETE FROM igloos WHERE username=?",                                 (username_to_delete,)),
        ("igloo_furniture",               "DELETE FROM igloo_furniture WHERE username=?",                        (username_to_delete,)),
        ("igloo_items",                   "DELETE FROM igloo_items WHERE username=?",                            (username_to_delete,)),
        ("igloo_visits",                  "DELETE FROM igloo_visits WHERE visitor=? OR host=?",                  (username_to_delete, username_to_delete)),
        ("gear",                          "DELETE FROM gear WHERE username=?",                                   (username_to_delete,)),
        ("help_dismissed",                "DELETE FROM help_dismissed WHERE username=?",                         (username_to_delete,)),
        ("monster_kills",                 "DELETE FROM monster_kills WHERE username=?",                          (username_to_delete,)),
        ("event_log",                     "DELETE FROM event_log WHERE username=?",                              (username_to_delete,)),
        ("relationships",                 "DELETE FROM relationships WHERE username_a=? OR username_b=?",        (username_to_delete, username_to_delete)),
        ("building_contributions_tracker","DELETE FROM building_contributions_tracker WHERE username=?",         (username_to_delete,)),
        ("discovered_sets",               "DELETE FROM discovered_sets WHERE username=?",                        (username_to_delete,)),
        ("building_donations",            "DELETE FROM building_donations WHERE username=?",                     (username_to_delete,)),
        ("achievements",                  "DELETE FROM achievements WHERE username=?",                           (username_to_delete,)),
        ("login_streaks",                 "DELETE FROM login_streaks WHERE username=?",                          (username_to_delete,)),
        ("daily_missions",                "DELETE FROM daily_missions WHERE username=?",                         (username_to_delete,)),
    ]
    tables_cleaned = []
    for table_name, query, params in delete_queries:
        try:
            db.execute(query, params)
            tables_cleaned.append(table_name)
        except Exception as e:
            print(f"[Mayor] Delete from {table_name} failed: {e}")
    db.commit()
    db.close()
    print(f"[Mayor] Player '{username_to_delete}' deleted by {session.get('username') or 'key auth'}. Tables: {tables_cleaned}")
    return jsonify({"status": "success", "message": f"Player '{username_to_delete}' has been completely deleted.", "tables_cleaned": tables_cleaned})


# ── MAYOR RAID DEBUG ──────────────────────────────────────────────────────────
# Force-action routes call the real scheduler-job / resolution functions
# directly (no duplicated logic). Every action is mayor-authed and logged to
# event_log under "admin_debug" (excluded from the public news ticker) so
# there's a trail of manual overrides vs. natural cycle events.

def _raid_debug_flag_check():
    if not FEATURES.get("weekly_raid", False):
        return jsonify({"status": "error", "message": "weekly_raid flag is off — enable it first."})
    return None


def _debug_raid_challenge_anchor(db):
    """Return a weekly_challenges.id to satisfy raid_state.challenge_id's NOT
    NULL foreign key for a debug-triggered raid that may have no real weekly
    challenge behind it at all. Reuses the latest existing challenge row
    (whatever its status) if one exists; otherwise inserts a minimal
    placeholder (status='cancelled', so it's invisible to every real query —
    all of them only ever look for status='active') purely to anchor the FK.
    """
    row = db.execute("SELECT id FROM weekly_challenges ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return row["id"]
    cur = db.execute(
        "INSERT INTO weekly_challenges (metric_type, threshold, current_progress, week_start, status, created_at) "
        "VALUES (?, 0, 0, ?, 'cancelled', ?)",
        (WEEKLY_METRIC_TYPES[0]["id"], datetime.date.today().isoformat(), int(time.time())),
    )
    return cur.lastrowid


@app.route("/mayor/raid-debug/settings/<key>", methods=["POST"])
def raid_debug_save_setting(key):
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    if key not in raid_settings.DEFAULTS:
        return jsonify({"status": "error", "message": "Unknown setting."}), 404

    data  = request.get_json(silent=True) or {}
    value = data.get("value")

    try:
        if key == "weekly_metric_thresholds":
            value = {k: int(v) for k, v in value.items()}
            if any(v <= 0 for v in value.values()):
                raise ValueError("Thresholds must be positive.")
            valid_ids = {m["id"] for m in WEEKLY_METRIC_TYPES}
            if set(value.keys()) != valid_ids:
                raise ValueError("Must supply a threshold for every metric: " + ", ".join(sorted(valid_ids)))
        elif key in ("boss_hp_per_participant", "boss_hp_flat", "cp_damage_bonus_divisor"):
            value = int(value)
            if value <= 0:
                raise ValueError("Must be positive.")
        elif key == "lootbox_drop_rates":
            value = {k: float(v) for k, v in value.items()}
            valid_rarities = {"legendary", "rare", "epic", "uncommon", "common"}
            if set(value.keys()) != valid_rarities:
                raise ValueError("Must supply all 5 rarities: " + ", ".join(sorted(valid_rarities)))
            total = sum(value.values())
            if abs(total - 100) > 0.01:
                raise ValueError(f"Rates must sum to 100 (got {total}).")
        elif key in ("gold_range", "resource_range"):
            value = [int(value[0]), int(value[1])]
            if value[0] < 0 or value[1] < value[0]:
                raise ValueError("Range must be [min, max] with 0 <= min <= max.")
        elif key == "rank_reward_podium_size":
            value = int(value)
            if value < 1 or value > 20:
                raise ValueError("Podium size must be between 1 and 20.")
        elif key == "boss_names":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError("Must be a list of names (one per line).")
            value = [v.strip() for v in value if v.strip()]
            if not value:
                raise ValueError("Must supply at least one boss name.")
            if len(value) > 50:
                raise ValueError("Too many boss names (max 50).")
            if any(len(v) > 60 for v in value):
                raise ValueError("Each name must be 60 characters or fewer.")
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        return jsonify({"status": "error", "message": str(e) or "Invalid value."})

    raid_settings.set_setting(key, value)

    mayor = session.get("username") or "key-auth"
    db = get_db()
    log_event(db, "admin_debug", f"👑 [RAID DEBUG] {mayor} updated raid setting '{key}' → {value}", mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "key": key, "value": value})


@app.route("/mayor/raid-debug/force-new-challenge", methods=["POST"])
def raid_debug_force_new_challenge():
    """Start a fresh weekly challenge immediately. With no metric_type in the
    body, picks randomly via the real scheduler job (unchanged default
    behavior). With one, opens that exact metric at its current live
    threshold instead -- mayor-selectable for testing, while the automatic
    Monday cycle keeps picking randomly."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    data        = request.get_json(silent=True) or {}
    metric_type = (data.get("metric_type") or "").strip()
    mayor       = session.get("username") or "key-auth"

    if metric_type:
        valid_ids = {m["id"] for m in WEEKLY_METRIC_TYPES}
        if metric_type not in valid_ids:
            return jsonify({"status": "error", "message": f"Unknown metric '{metric_type}'."})
        week_start = datetime.date.today().isoformat()
        now        = int(time.time())

        db = get_db()
        # get_setting() reuses this connection instead of opening its own for
        # raid_settings.weekly_metric_thresholds.
        thresholds = raid_settings.get_setting("weekly_metric_thresholds", db=db)
        threshold  = thresholds.get(metric_type, 0)
        cancelled = db.execute("UPDATE weekly_challenges SET status='cancelled' WHERE status='active'").rowcount
        db.execute(
            "INSERT INTO weekly_challenges (metric_type, threshold, current_progress, week_start, status, created_at) "
            "VALUES (?, ?, 0, ?, 'active', ?)",
            (metric_type, threshold, week_start, now),
        )
        row = db.execute("SELECT * FROM weekly_challenges ORDER BY id DESC LIMIT 1").fetchone()
        log_event(db, "admin_debug",
                  f"👑 [RAID DEBUG] {mayor} force-started a new weekly challenge "
                  f"(metric: {metric_type}, mayor-selected, threshold {threshold})"
                  + (f" (cancelled {cancelled} active challenge)" if cancelled else ""),
                  mayor)
        db.commit()
        db.close()
        return jsonify({"status": "success", "challenge": dict(row) if row else None})

    db = get_db()
    cancelled = db.execute("UPDATE weekly_challenges SET status='cancelled' WHERE status='active'").rowcount
    db.commit()
    db.close()

    start_new_weekly_challenge()  # the real Monday scheduler job — not duplicated (random metric)

    db  = get_db()
    row = db.execute("SELECT * FROM weekly_challenges ORDER BY id DESC LIMIT 1").fetchone()
    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} force-started a new weekly challenge"
              + (f" (cancelled {cancelled} active challenge)" if cancelled else ""),
              mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "challenge": dict(row) if row else None})


@app.route("/mayor/raid-debug/set-progress", methods=["POST"])
def raid_debug_set_progress():
    """Directly set the active challenge's current_progress -- for nudging it
    to any state (near-threshold, wildly over, etc.) without only having a
    snap-to-threshold force-succeed available."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    data = request.get_json(silent=True) or {}
    try:
        value = int(data.get("value"))
        if value < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Progress must be a non-negative integer."})

    mayor = session.get("username") or "key-auth"
    db = get_db()
    challenge = db.execute(
        "SELECT id, threshold FROM weekly_challenges WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not challenge:
        db.close()
        return jsonify({"status": "error", "message": "No active challenge to set progress on."})

    db.execute("UPDATE weekly_challenges SET current_progress=? WHERE id=?", (value, challenge["id"]))
    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} set weekly challenge progress to {value} (threshold {challenge['threshold']})",
              mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "current_progress": value, "threshold": challenge["threshold"]})


@app.route("/mayor/raid-debug/force-fail-challenge", methods=["POST"])
def raid_debug_force_fail_challenge():
    """Force the active challenge to evaluate as failed right now, regardless
    of its current progress -- the counterpart to force-succeed."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    mayor = session.get("username") or "key-auth"
    db = get_db()
    challenge = db.execute(
        "SELECT id FROM weekly_challenges WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not challenge:
        db.close()
        return jsonify({"status": "error", "message": "No active challenge to force-fail."})
    # Guarantees it evaluates as failed regardless of current progress.
    db.execute("UPDATE weekly_challenges SET current_progress=0 WHERE id=?", (challenge["id"],))
    db.commit()
    db.close()

    evaluate_weekly_challenge()  # the real Friday scheduler job — not duplicated

    db  = get_db()
    row = db.execute("SELECT * FROM weekly_challenges ORDER BY id DESC LIMIT 1").fetchone()
    log_event(db, "admin_debug", f"👑 [RAID DEBUG] {mayor} force-failed the active weekly challenge", mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "challenge": dict(row) if row else None})


@app.route("/mayor/raid-debug/cancel-challenge", methods=["POST"])
def raid_debug_cancel_challenge():
    """True abort: mark the active challenge cancelled directly, bypassing
    evaluate_weekly_challenge() entirely -- no succeeded/failed status is
    ever recorded and no lifecycle-notice popup fires (that route only
    triggers on status succeeded/failed), and the raid system is untouched."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    mayor = session.get("username") or "key-auth"
    db = get_db()
    cancelled = db.execute("UPDATE weekly_challenges SET status='cancelled' WHERE status='active'").rowcount
    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} cancelled the current weekly challenge ({cancelled} row(s)) "
              f"— no outcome recorded, raid untouched",
              mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "challenges_cancelled": cancelled})


@app.route("/mayor/raid-debug/force-succeed-challenge", methods=["POST"])
def raid_debug_force_succeed_challenge():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    mayor = session.get("username") or "key-auth"
    db = get_db()
    challenge = db.execute(
        "SELECT id, threshold FROM weekly_challenges WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not challenge:
        db.close()
        return jsonify({"status": "error", "message": "No active challenge to force-succeed."})
    db.execute("UPDATE weekly_challenges SET current_progress=? WHERE id=?", (challenge["threshold"], challenge["id"]))
    db.commit()
    db.close()

    evaluate_weekly_challenge()  # the real Friday scheduler job — not duplicated

    db   = get_db()
    raid = db.execute("SELECT * FROM raid_state ORDER BY id DESC LIMIT 1").fetchone()
    log_event(db, "admin_debug", f"👑 [RAID DEBUG] {mayor} force-succeeded the active weekly challenge", mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "raid": dict(raid) if raid else None})


@app.route("/mayor/raid-debug/force-start-raid", methods=["POST"])
def raid_debug_force_start_raid():
    """Spawn a raid boss immediately -- fully decoupled from weekly-challenge
    state. Works whether a challenge succeeded, is still active, failed, was
    cancelled, or doesn't exist at all. This deliberately does NOT call
    start_raid_if_unlocked() (the real automatic Saturday job, which keeps
    its existing precondition of a succeeded challenge unchanged) -- it
    inserts a fresh 'active' raid_state row directly.

    boss_name in the body picks it explicitly (mayor-selected); omitted/blank
    falls back to a fresh random pick from raid_settings.boss_names, same
    pool the automatic cycle draws from.
    """
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    data = request.get_json(silent=True) or {}
    requested_boss_name = (data.get("boss_name") or "").strip()
    mayor = session.get("username") or "key-auth"
    now   = int(time.time())

    db = get_db()
    # pick_boss_name()/get_setting() reuse this connection instead of opening
    # their own for raid_settings.boss_names/boss_hp_flat.
    boss_name   = requested_boss_name or pick_boss_name(db=db)
    boss_max_hp = raid_settings.get_setting("boss_hp_flat", db=db)

    # At most one live raid at a time -- neutralize anything else pending/
    # active first so the automatic Saturday job and Monday timeout sweep
    # never find two "active" rows to referee later.
    superseded = db.execute(
        "UPDATE raid_state SET status='cancelled' WHERE status IN ('join_window', 'awaiting_raid', 'active')"
    ).rowcount

    challenge_id = _debug_raid_challenge_anchor(db)
    cur = db.execute(
        "INSERT INTO raid_state "
        "(challenge_id, boss_name, boss_max_hp, boss_current_hp, status, raid_start, created_at) "
        "VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (challenge_id, boss_name, boss_max_hp, boss_max_hp, now, now),
    )
    raid_id = cur.lastrowid

    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} force-started a new raid immediately: {boss_name} "
              f"(HP {boss_max_hp}, no weekly-challenge precondition)"
              + (f" — superseded {superseded} previous pending/active raid(s)" if superseded else ""),
              mayor)
    db.commit()

    raid = db.execute("SELECT * FROM raid_state WHERE id=?", (raid_id,)).fetchone()
    db.close()
    return jsonify({"status": "success", "raid": dict(raid) if raid else None})


@app.route("/mayor/raid-debug/set-boss-hp", methods=["POST"])
def raid_debug_set_boss_hp():
    """Directly set the active raid's boss_current_hp -- for testing
    near-defeat or fresh-start states without landing real damage. Does not
    itself trigger resolution even at 0; use Force Resolve for that, or let
    the next real attack finish it off."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    data = request.get_json(silent=True) or {}
    mayor = session.get("username") or "key-auth"
    db = get_db()
    raid = db.execute(
        "SELECT id, boss_max_hp FROM raid_state WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not raid:
        db.close()
        return jsonify({"status": "error", "message": "No active raid to set HP on."})

    try:
        value = int(data.get("value"))
    except (TypeError, ValueError):
        db.close()
        return jsonify({"status": "error", "message": "HP must be an integer."})
    if value < 0 or value > raid["boss_max_hp"]:
        db.close()
        return jsonify({"status": "error", "message": f"HP must be between 0 and {raid['boss_max_hp']} (current max HP)."})

    db.execute("UPDATE raid_state SET boss_current_hp=? WHERE id=?", (value, raid["id"]))
    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} set boss HP to {value}/{raid['boss_max_hp']}", mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "boss_current_hp": value, "boss_max_hp": raid["boss_max_hp"]})


@app.route("/mayor/raid-debug/cancel-raid", methods=["POST"])
def raid_debug_cancel_raid():
    """True abort: mark the current pending/active raid cancelled directly,
    bypassing resolve_raid() entirely -- no rewards distributed, no chat
    announcement, no leaderboard resolution, and the weekly challenge is
    untouched."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    mayor = session.get("username") or "key-auth"
    db = get_db()
    cancelled = db.execute(
        "UPDATE raid_state SET status='cancelled' WHERE status IN ('join_window', 'awaiting_raid', 'active')"
    ).rowcount
    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} cancelled the current raid ({cancelled} row(s)) "
              f"— no rewards/announcement, weekly challenge untouched",
              mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "raids_cancelled": cancelled})


@app.route("/mayor/raid-debug/rename-boss", methods=["POST"])
def raid_debug_rename_boss():
    """Rename the current/last-spawned boss directly -- a quick one-off edit for
    testing, distinct from managing the boss_names pool new bosses get picked from."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"status": "error", "message": "Name cannot be empty."})
    if len(name) > 60:
        return jsonify({"status": "error", "message": "Name must be 60 characters or fewer."})

    db   = get_db()
    raid = db.execute("SELECT id FROM raid_state ORDER BY id DESC LIMIT 1").fetchone()
    if not raid:
        db.close()
        return jsonify({"status": "error", "message": "No raid exists yet to rename."})

    db.execute("UPDATE raid_state SET boss_name=? WHERE id=?", (name, raid["id"]))
    mayor = session.get("username") or "key-auth"
    log_event(db, "admin_debug", f"👑 [RAID DEBUG] {mayor} renamed the current boss to '{name}'", mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "boss_name": name})


@app.route("/mayor/raid-debug/force-resolve", methods=["POST"])
def raid_debug_force_resolve():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    flag_err = _raid_debug_flag_check()
    if flag_err:
        return flag_err

    data   = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    if reason not in ("defeated", "timeout"):
        return jsonify({"status": "error", "message": "reason must be 'defeated' or 'timeout'."})

    db   = get_db()
    raid = db.execute("SELECT id FROM raid_state WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
    db.close()
    if not raid:
        return jsonify({"status": "error", "message": "No active raid to resolve."})

    result = resolve_raid(raid["id"], reason)  # the real resolution function — not duplicated
    if result is None:
        return jsonify({"status": "error", "message": "Raid was already resolved (lost a race)."})

    mayor = session.get("username") or "key-auth"
    db = get_db()
    log_event(db, "admin_debug", f"👑 [RAID DEBUG] {mayor} force-resolved raid #{raid['id']} as {reason}", mayor)
    db.commit()
    db.close()
    return jsonify({"status": "success", "result": result})


@app.route("/mayor/raid-debug/cancel-cycle", methods=["POST"])
def raid_debug_cancel_cycle():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    mayor = session.get("username") or "key-auth"
    db = get_db()
    challenges_cancelled = db.execute("UPDATE weekly_challenges SET status='cancelled' WHERE status='active'").rowcount
    raids_cancelled = db.execute(
        "UPDATE raid_state SET status='cancelled' WHERE status IN ('join_window', 'awaiting_raid', 'active')"
    ).rowcount
    log_event(db, "admin_debug",
              f"👑 [RAID DEBUG] {mayor} cancelled the current cycle "
              f"({challenges_cancelled} challenge(s), {raids_cancelled} raid(s)) — no rewards distributed",
              mayor)
    db.commit()
    db.close()
    return jsonify({
        "status": "success",
        "challenges_cancelled": challenges_cancelled,
        "raids_cancelled": raids_cancelled,
    })


# ── PENGUIN BANK ─────────────────────────────────────────────────────────────

_BANK_RESOURCES = {"gold", "fish", "herbs", "blood_gems", "bones", "spell_fragments"}

# Fallback flat price by rarity, used only when an item has no catalog entry to
# read a real gold cost from (milestone/tutorial rewards, Seal Shop exclusives --
# items never sold for gold in the first place). Buyback = ceil(sell_price * 1.2).
_BANK_SELL_PRICES = {
    "common":    30,
    "uncommon":  100,
    "rare":      300,
    "epic":      800,
    "legendary": 2500,
}

BANK_SELL_DISCOUNT               = 0.5  # standard resale: 50% of the item's original gold cost
BANK_EVENT_ITEM_SELL_MULTIPLIER  = 1.5  # event-exclusive items sell above cost instead of at a discount -- tune during balance-pass

# Slots that must never be sellable regardless of item type (titles aren't gear
# rows at all, so they need no exclusion here).
_BANK_UNSELLABLE_SLOTS = {"card_frame", "card_background"}


def _find_shop_definition(item_id, item_type, db=None):
    """Look up an item's original shop listing across every catalog it could
    have come from, keyed by the item type recorded on the player's gear row.
    Returns (gold_cost, event_exclusive), or (None, False) if the item was
    never sold for gold anywhere (milestone/tutorial rewards, Seal Shop
    exclusives, etc.) -- callers should fall back to a flat price in that case.

    Defensive against a malformed catalog entry (a "cost" that isn't a dict,
    a missing "gold"/"price" key, etc.) -- returns (None, False) in that case
    too rather than raising, same as a genuinely-unlisted item, so one bad
    catalog entry can't take down every price lookup that runs after it.

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why."""
    try:
        if item_type == "combat":
            for items in catalog.load_barracks_shop(db=db).values():
                for item in items:
                    if item["id"] == item_id:
                        return item.get("cost", {}).get("gold", 0), bool(item.get("event_exclusive"))
        else:
            for items in catalog.load_boutique_items(db=db).values():
                for item in items:
                    if item["id"] == item_id:
                        return item.get("price"), bool(item.get("event_exclusive"))
    except (AttributeError, TypeError) as e:
        print(f"[_find_shop_definition] malformed catalog entry for item_id={item_id!r} type={item_type!r}: {e}")
        return None, False
    return None, False


def calculate_bank_sell_price(gear_row, db=None):
    """Gold the bank pays for a player's item. Standard items sell at
    BANK_SELL_DISCOUNT of their real shop cost (gold portion only); event-
    exclusive items sell at BANK_EVENT_ITEM_SELL_MULTIPLIER instead. Items with
    no shop listing (rewards, Seal Shop exclusives) fall back to the flat
    rarity-based _BANK_SELL_PRICES. Never raises -- a bad catalog entry or an
    unexpected gold_cost type falls back to the flat price instead.

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why."""
    fallback = _BANK_SELL_PRICES.get(gear_row["rarity"] or "common", 30)
    try:
        gold_cost, event_exclusive = _find_shop_definition(gear_row["item_id"], gear_row["type"], db=db)
        if gold_cost is None:
            return fallback
        if event_exclusive:
            return math.ceil(gold_cost * BANK_EVENT_ITEM_SELL_MULTIPLIER)
        return math.floor(gold_cost * BANK_SELL_DISCOUNT)
    except (TypeError, ValueError) as e:
        print(f"[calculate_bank_sell_price] bad gold_cost for item_id={gear_row['item_id']!r}: {e}")
        return fallback


@app.route("/bank/listings")
def bank_get_listings():
    username = request.args.get("username", "")
    db = get_db()
    rows = db.execute(
        "SELECT bl.*, g.name AS gear_name, g.slot AS gear_slot, g.type AS gear_type, "
        "g.rarity AS gear_rarity, g.combat_power AS gear_cp, g.set_name AS gear_set "
        "FROM bank_listings bl LEFT JOIN gear g ON bl.offer_gear_id = g.id "
        "WHERE bl.status='open' AND bl.seller_username != ? "
        "ORDER BY bl.created_at DESC LIMIT 60",
        (username,)
    ).fetchall()
    db.close()
    return jsonify({"listings": [dict(r) for r in rows]})


@app.route("/bank/my-listings")
def bank_my_listings():
    username = request.args.get("username", "")
    db = get_db()
    rows = db.execute(
        "SELECT bl.*, g.name AS gear_name, g.slot AS gear_slot, g.type AS gear_type, "
        "g.rarity AS gear_rarity, g.combat_power AS gear_cp, g.set_name AS gear_set "
        "FROM bank_listings bl LEFT JOIN gear g ON bl.offer_gear_id = g.id "
        "WHERE bl.seller_username=? AND bl.status='open' "
        "ORDER BY bl.created_at DESC",
        (username,)
    ).fetchall()
    db.close()
    return jsonify({"listings": [dict(r) for r in rows]})


@app.route("/bank/list-item", methods=["POST"])
def bank_list_item():
    data        = request.get_json(silent=True) or {}
    username    = session.get("username", "")
    gear_id     = data.get("gear_id")
    ask_resource = data.get("ask_resource", "")
    ask_amount  = int(data.get("ask_amount", 0))

    if ask_resource not in _BANK_RESOURCES:
        return jsonify({"status": "error", "message": "Invalid resource."})
    if ask_amount <= 0:
        return jsonify({"status": "error", "message": "Amount must be positive."})

    db = get_db()
    g = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
    if not g:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})
    if g["equipped"]:
        db.close()
        return jsonify({"status": "error", "message": "Unequip the item before listing it."})
    if g["worn"]:
        db.close()
        return jsonify({"status": "error", "message": "Remove the item before listing it."})
    if g["listed"]:
        db.close()
        return jsonify({"status": "error", "message": "Item is already listed."})

    now = int(time.time())
    db.execute("UPDATE gear SET listed=1 WHERE id=?", (gear_id,))
    db.execute(
        "INSERT INTO bank_listings "
        "(seller_username, listing_type, offer_gear_id, ask_resource, ask_amount, status, created_at) "
        "VALUES (?,?,?,?,?,'open',?)",
        (username, "item", gear_id, ask_resource, ask_amount, now)
    )
    log_event(db, "bank", f"🏦 {username} listed an item for sale in the Penguin Bank!", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": "Item listed for sale."})


@app.route("/bank/list-resource", methods=["POST"])
def bank_list_resource():
    data           = request.get_json(silent=True) or {}
    username       = session.get("username", "")
    offer_resource = data.get("offer_resource", "")
    offer_amount   = int(data.get("offer_amount", 0))
    ask_resource   = data.get("ask_resource", "")
    ask_amount     = int(data.get("ask_amount", 0))

    if offer_resource not in _BANK_RESOURCES or ask_resource not in _BANK_RESOURCES:
        return jsonify({"status": "error", "message": "Invalid resource."})
    if offer_resource == ask_resource:
        return jsonify({"status": "error", "message": "Can't trade a resource for itself."})
    if offer_amount <= 0 or ask_amount <= 0:
        return jsonify({"status": "error", "message": "Amounts must be positive."})

    db = get_db()
    ensure_resources(db, username)
    res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    if not res:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    have = res["gold"] if offer_resource == "gold" else res[offer_resource]
    if have < offer_amount:
        db.close()
        return jsonify({"status": "error", "message": f"Not enough {offer_resource.replace('_', ' ')}."})

    col = offer_resource
    db.execute(f"UPDATE resources SET {col}={col}-? WHERE username=?", (offer_amount, username))

    now = int(time.time())
    db.execute(
        "INSERT INTO bank_listings "
        "(seller_username, listing_type, offer_resource, offer_amount, ask_resource, ask_amount, status, created_at) "
        "VALUES (?,?,?,?,?,?,'open',?)",
        (username, "resource", offer_resource, offer_amount, ask_resource, ask_amount, now)
    )
    log_event(db, "bank",
        f"🏦 {username} posted a trade: {offer_amount} {offer_resource.replace('_',' ')} "
        f"for {ask_amount} {ask_resource.replace('_',' ')}!", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": "Trade offer posted."})


@app.route("/bank/cancel/<int:listing_id>", methods=["POST"])
def bank_cancel_listing(listing_id):
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    db       = get_db()
    listing  = db.execute(
        "SELECT * FROM bank_listings WHERE id=? AND seller_username=? AND status='open'",
        (listing_id, username)
    ).fetchone()
    if not listing:
        db.close()
        return jsonify({"status": "error", "message": "Listing not found."})

    if listing["listing_type"] == "item":
        db.execute("UPDATE gear SET listed=0 WHERE id=?", (listing["offer_gear_id"],))
    else:
        col = listing["offer_resource"]
        ensure_resources(db, username)
        db.execute(f"UPDATE resources SET {col}={col}+? WHERE username=?",
                   (listing["offer_amount"], username))

    db.execute("UPDATE bank_listings SET status='cancelled' WHERE id=?", (listing_id,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": "Listing cancelled."})


@app.route("/bank/accept/<int:listing_id>", methods=["POST"])
def bank_accept_listing(listing_id):
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")  # the buyer
    db       = get_db()
    listing  = db.execute(
        "SELECT * FROM bank_listings WHERE id=? AND status='open'", (listing_id,)
    ).fetchone()
    if not listing:
        db.close()
        return jsonify({"status": "error", "message": "Listing not found or already completed."})
    if listing["seller_username"] == username:
        db.close()
        return jsonify({"status": "error", "message": "You can't accept your own listing."})

    ensure_resources(db, username)
    buyer_res = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    if not buyer_res:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    ask_col  = listing["ask_resource"]
    ask_have = buyer_res["gold"] if ask_col == "gold" else buyer_res[ask_col]
    if ask_have < listing["ask_amount"]:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"You need {listing['ask_amount']} {listing['ask_resource'].replace('_', ' ')}."
        })

    seller = listing["seller_username"]
    ensure_resources(db, seller)
    now    = int(time.time())

    # Buyer pays seller the asked resource
    db.execute(f"UPDATE resources SET {ask_col}={ask_col}-? WHERE username=?",
               (listing["ask_amount"], username))
    db.execute(f"UPDATE resources SET {ask_col}={ask_col}+? WHERE username=?",
               (listing["ask_amount"], seller))

    if listing["listing_type"] == "item":
        db.execute(
            "UPDATE gear SET username=?, listed=0, equipped=0, worn=0 WHERE id=?",
            (username, listing["offer_gear_id"])
        )
        gear = db.execute("SELECT name FROM gear WHERE id=?",
                          (listing["offer_gear_id"],)).fetchone()
        item_name = gear["name"] if gear else "item"
        log_event(db, "bank",
            f"🏦 {username} bought {item_name} from {seller} "
            f"for {listing['ask_amount']} {listing['ask_resource'].replace('_', ' ')}!", username)
    else:
        offer_col = listing["offer_resource"]
        db.execute(f"UPDATE resources SET {offer_col}={offer_col}+? WHERE username=?",
                   (listing["offer_amount"], username))
        log_event(db, "bank",
            f"🏦 {seller} traded {listing['offer_amount']} {listing['offer_resource'].replace('_', ' ')} "
            f"with {username} for {listing['ask_amount']} {listing['ask_resource'].replace('_', ' ')}!", username)

    db.execute(
        "UPDATE bank_listings SET status='completed', completed_at=?, buyer_username=? WHERE id=?",
        (now, username, listing_id)
    )
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": "Trade complete!"})


@app.route("/bank/sell-to-bank", methods=["POST"])
def bank_sell_to_bank():
    """Sells one or more of the player's gear items to the bank in a single
    batch. Accepts either the original single-item {"gear_id": N} shape
    (kept working for backward compatibility) or a new {"gear_ids": [N, ...]}
    list for a multi-select sell. Each item is processed with the exact same
    per-item logic/checks as before, just looped; gold is credited once as a
    running total rather than per item. Items that fail an individual check
    (not found, unsellable slot, currently listed) are skipped rather than
    aborting the whole batch, and reported back in "errors" -- so one bad
    item in a multi-select can't block selling the rest."""
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")

    gear_ids = data.get("gear_ids")
    if gear_ids is None:
        single = data.get("gear_id")
        gear_ids = [single] if single else []

    db = get_db()
    total_gold           = 0
    sold_items            = []
    errors                = []
    was_equipped_or_worn  = False
    now                   = int(time.time())

    for gear_id in gear_ids:
        g = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
        if not g:
            errors.append("Item not found.")
            continue
        if (g["slot"] or "") in _BANK_UNSELLABLE_SLOTS:
            errors.append(f"{g['name']} can't be sold.")
            continue
        if g["listed"]:
            errors.append(f"Cancel your listing for {g['name']} before selling to the bank.")
            continue

        if g["equipped"] or g["worn"]:
            was_equipped_or_worn = True
        sell_price = calculate_bank_sell_price(g, db=db)
        buy_price  = math.ceil(sell_price * 1.2)

        add_gold(db, username, sell_price)
        # Auto-unequip/un-wear as part of the sale rather than rejecting it --
        # there's no "dangling equipped-but-not-owned" state once username
        # flips to '__bank__' below, since these flags are cleared in the
        # same update.
        db.execute(
            "UPDATE gear SET username='__bank__', bank_sell_price=?, bank_listed_at=?, "
            "equipped=0, worn=0, listed=0, original_owner=? WHERE id=?",
            (buy_price, now, username, gear_id)
        )
        log_event(db, "bank",
            f"🏦 {username} sold {g['name']} to the Penguin Bank for {sell_price} gold!", username)
        total_gold += sell_price
        sold_items.append({"gear_id": gear_id, "name": g["name"], "sell_price": sell_price})

    if not sold_items:
        db.close()
        return jsonify({"status": "error", "message": errors[0] if errors else "No item selected."})

    db.commit()
    db.close()
    message = (f"Sold {sold_items[0]['name']} for {total_gold} 🪙 gold!" if len(sold_items) == 1
               else f"Sold {len(sold_items)} items for {total_gold} 🪙 gold!")
    return jsonify({
        "status":               "success",
        "message":              message,
        "total_gold":           total_gold,
        "sold_count":           len(sold_items),
        "sold_items":           sold_items,
        "errors":               errors,
        "was_equipped_or_worn": was_equipped_or_worn,
    })


@app.route("/bank/shop")
def bank_shop():
    username = request.args.get("username", "")
    now      = int(time.time())
    db       = get_db()
    # Expire items older than 30 days: the buyback window is over, so the
    # item leaves the economy for good -- DELETE the row. (This used to
    # UPDATE username to NULL, which violated gear.username's NOT NULL
    # constraint and 500'd this whole tab the moment ANY bank item aged past
    # the window; a NULL-username row would also have been unreachable dead
    # weight, since every gear query filters by username.) The sweep is
    # best-effort: if it ever fails, log and still serve the shop (with
    # stale items) rather than crash the tab.
    try:
        db.execute(
            "DELETE FROM gear "
            "WHERE username='__bank__' AND bank_listed_at > 0 AND bank_listed_at < ?",
            (now - 30 * 86400,)
        )
        db.commit()
    except Exception as e:
        print(f"[BankShop] expiry sweep failed (serving shop anyway): {e}")
        db.rollback()
    rows = db.execute(
        "SELECT * FROM gear WHERE username='__bank__' ORDER BY bank_listed_at DESC"
    ).fetchall()
    db.close()
    return jsonify({"items": [dict(r) for r in rows]})


@app.route("/bank/shop-buy/<int:gear_id>", methods=["POST"])
def bank_shop_buy(gear_id):
    data     = request.get_json(silent=True) or {}
    username = session.get("username", "")
    db       = get_db()

    g = db.execute(
        "SELECT * FROM gear WHERE id=? AND username='__bank__'", (gear_id,)
    ).fetchone()
    if not g:
        db.close()
        return jsonify({"status": "error", "message": "Item no longer available."})

    ensure_resources(db, username)
    res = db.execute("SELECT gold FROM resources WHERE username=?", (username,)).fetchone()
    if not res or res["gold"] < g["bank_sell_price"]:
        db.close()
        return jsonify({"status": "error", "message": f"You need {g['bank_sell_price']} 🪙 gold."})

    db.execute("UPDATE resources SET gold=gold-? WHERE username=?", (g["bank_sell_price"], username))
    db.execute(
        "UPDATE gear SET username=?, bank_sell_price=0, bank_listed_at=0 WHERE id=?",
        (username, gear_id)
    )
    log_event(db, "bank",
        f"🏦 {username} bought {g['name']} from the Penguin Bank for {g['bank_sell_price']} gold!", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "message": f"Bought {g['name']}!"})


MINIGAME_BUILDING_IDS = ("sea_lion_pit", "club_soda", "parkmusement", "cursed_temple", "guillotine")


def calculate_minigame_rewards(building_id, score, player_level):
    base = {
        "sea_lion_pit":  {"fish": 15, "gold": 5, "xp": 10},
        "club_soda":     {"herbs": 15, "gold": 5, "xp": 10},
        "parkmusement":  {"gold": 20, "xp": 10},
        "cursed_temple": {"spell_fragments": 12, "gold": 5, "xp": 10},
        "guillotine":    {"blood_gems": 6, "bones": 6, "gold": 5, "xp": 10},
    }
    # `score` is now the player's raw, uncapped score (see minigame_complete --
    # scores used to be clamped to 0-100 before storage/display; now only the
    # reward multiplier below still works on that old 0-100 scale, so it's
    # reproduced here internally rather than changing the payout curve.
    # Capping at 100 for this calculation only replicates the exact old
    # multiplier behavior (which maxed out at score=100 either way), so
    # reward amounts are unaffected by the raw-score change.
    reward_score = min(100, score)
    multiplier = max(0.2, min(2.0, reward_score / 50.0))
    gather_bonus = 1 + (player_level or 1) * 0.05
    rewards = {}
    for resource, amount in base.get(building_id, {}).items():
        if resource == "xp":
            rewards[resource] = max(1, int(amount * multiplier))
        else:
            rewards[resource] = max(1, int(amount * multiplier * gather_bonus))
    return rewards


def calculateIceBlockReward(roll):
    """Return ice_blocks earned for a given 1-20 roll. Isolated for future multipliers."""
    return roll


@app.route("/build/roll", methods=["POST"])
def build_roll():
    username = session.get("username", "")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    db = get_db()
    p = db.execute(
        "SELECT energy, build_free_rolls FROM penguins WHERE username=?", (username,)
    ).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Player not found."})

    energy          = p["energy"] or 0
    free_rolls      = p["build_free_rolls"] or 0
    energy_cost     = 5
    is_free_roll    = free_rolls > 0
    normal_return   = False

    if not is_free_roll:
        if energy < energy_cost:
            db.close()
            return jsonify({"status": "error", "message": f"Need {energy_cost} energy to build! Rest at the hotel."})
        db.execute("UPDATE penguins SET energy=energy-? WHERE username=?", (energy_cost, username))

    roll            = random.randint(1, 20)
    ice_earned      = calculateIceBlockReward(roll)
    is_crit         = (roll == 20 and not is_free_roll)

    if is_free_roll:
        new_free_rolls = free_rolls - 1
        normal_return  = (new_free_rolls == 0)
        db.execute("UPDATE penguins SET build_free_rolls=? WHERE username=?", (new_free_rolls, username))
    elif is_crit:
        new_free_rolls = 5
        db.execute("UPDATE penguins SET build_free_rolls=5 WHERE username=?", (username,))
    else:
        new_free_rolls = 0

    db.execute("UPDATE resources SET ice_blocks=ice_blocks+? WHERE username=?", (ice_earned, username))
    award_xp(db, username, roll)
    r = db.execute("SELECT ice_blocks, gold FROM resources WHERE username=?", (username,)).fetchone()
    p2 = db.execute("SELECT energy FROM penguins WHERE username=?", (username,)).fetchone()
    db.commit()
    db.close()

    return jsonify({
        "status":           "success",
        "roll":             roll,
        "ice_blocks_earned": ice_earned,
        "ice_blocks_total": r["ice_blocks"] if r else ice_earned,
        "xp_earned":        roll,
        "free_rolls_remaining": new_free_rolls,
        "is_crit":          is_crit,
        "normal_return":    normal_return,
        "energy_remaining": (p2["energy"] if p2 else energy - (0 if is_free_roll else energy_cost)),
    })


@app.route("/minigame/start", methods=["POST"])
def minigame_start():
    data        = request.get_json(silent=True) or {}
    username    = session.get("username", "")
    building_id = data.get("building_id", "")
    is_tutorial = bool(data.get("tutorial", False))

    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})
    if building_id not in MINIGAME_BUILDING_IDS:
        return jsonify({"status": "error", "message": "No mini-game at this building."})

    db = get_db()
    p  = db.execute("SELECT energy, job FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    energy = p["energy"] or 0
    if not is_tutorial:
        if p["job"]:
            db.close()
            return jsonify({"status": "error", "message": "Collect your passive job first!"})
        if energy < 10:
            db.close()
            return jsonify({"status": "error", "message": "Need 10 energy to play! Rest at the hotel."})
        db.execute("UPDATE penguins SET energy=energy-10 WHERE username=?", (username,))
        db.commit()
        energy -= 10

    session["active_minigame"] = {"username": username, "building_id": building_id}
    db.close()
    return jsonify({"status": "success", "energy_remaining": energy})


@app.route("/minigame/complete", methods=["POST"])
def minigame_complete():
    data        = request.get_json(silent=True) or {}
    username    = session.get("username", "")
    building_id = data.get("building_id", "")
    # Raw score, no upper clamp — each game keeps its own natural scale now
    # (fish caught, combo points, etc). Used to be clamped to 0-100 here; see
    # calculate_minigame_rewards() for where that old scale is preserved
    # internally so reward payouts are unaffected by this change.
    score = max(0, round(float(data.get("score", 0))))

    if not username:
        return jsonify({"status": "error", "message": "Not logged in."})

    active = session.pop("active_minigame", None)
    if not active or active.get("username") != username or active.get("building_id") != building_id:
        return jsonify({"status": "error", "message": "No active mini-game found. Start the game first."})

    db = get_db()
    p  = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Penguin not found."})

    ensure_resources(db, username)
    rewards = calculate_minigame_rewards(building_id, score, p["level"] or 1)
    level_up_info = {"leveled": False}

    for resource, amount in rewards.items():
        if resource == "gold":
            add_gold(db, username, amount)
        elif resource == "xp":
            leveled, lvl_rewards = award_xp(db, username, amount)
            if leveled and lvl_rewards:
                level_up_info = {"leveled": True, "level": lvl_rewards[0].get("level", 0)}
        else:
            db.execute(
                f"UPDATE resources SET {resource}={resource}+? WHERE username=?",
                (amount, username)
            )

    now = int(time.time())
    if building_id in MINIGAME_BUILDING_IDS:
        db.execute(
            "INSERT INTO minigame_scores (username, building_id, score, played_at) VALUES (?,?,?,?)",
            (username, building_id, score, now)
        )

    log_event(db, "work", f"{username} played the {building_id} mini-game! Score: {score}", username)
    db.commit()
    db.close()
    return jsonify({"status": "success", "rewards": rewards, "level_up": level_up_info})


@app.route("/award-hall/minigame-records")
def minigame_records():
    """All-time top score per minigame, for the Award Hall's Minigames tab.
    Always available -- unlike the weekly leaderboard, this isn't gated
    behind minigame_leaderboard since it's just a records display."""
    db = get_db()
    records = {}
    for building_id in MINIGAME_BUILDING_IDS:
        row = db.execute(
            "SELECT ms.username, ms.score, ms.played_at, p.penguin_name FROM minigame_scores ms "
            "LEFT JOIN penguins p ON p.username = ms.username "
            "WHERE ms.building_id=? ORDER BY ms.score DESC, ms.played_at ASC LIMIT 1",
            (building_id,)
        ).fetchone()
        records[building_id] = {
            "username":      row["username"],
            "penguin_name":  row["penguin_name"] or row["username"],
            "score":         row["score"],
            "played_at":     row["played_at"],
        } if row else None
    db.close()
    return jsonify({"status": "success", "records": records})


# ── WEEKLY MINIGAME LEADERBOARD ───────────────────────────────────────────────
# Monday 00:00 UTC -> Saturday 00:00 UTC, mirroring the raid/challenge week but
# deliberately ending before the weekend raid window (raids run Sat->Mon) so
# the two reward systems never compete for the same moment.

def _minigame_week_bounds(reference_ts=None):
    """(week_start_ts, week_end_ts) for the Mon 00:00 -> Sat 00:00 UTC window
    containing reference_ts (default: now)."""
    ref = datetime.datetime.utcfromtimestamp(reference_ts if reference_ts is not None else time.time())
    monday   = ref.date() - datetime.timedelta(days=ref.weekday())
    saturday = monday + datetime.timedelta(days=5)
    week_start = datetime.datetime.combine(monday,   datetime.time(0, 0)).replace(tzinfo=datetime.timezone.utc)
    week_end   = datetime.datetime.combine(saturday, datetime.time(0, 0)).replace(tzinfo=datetime.timezone.utc)
    return int(week_start.timestamp()), int(week_end.timestamp())


def _compute_weekly_minigame_leaderboard(week_start, week_end):
    """Combined weekly ranking across all 5 minigames.

    Raw scores aren't comparable across games (each has its own natural scale
    -- fish caught vs combo points vs memory rounds), so a player's
    contribution from a given game is normalized against THAT GAME's own top
    score for the week: contribution = player_best_in_game / week_top_in_game
    * 100. That guarantees whoever tops any single game this week always
    contributes exactly 100 points for it, and a player who skips a game
    contributes 0 for it. The combined score is the sum of all 5 games'
    contributions (max possible: 500, from placing #1 in every game).

    Returns [(username, total_score), ...] sorted best-first.
    """
    db = get_db()
    rows = db.execute(
        "SELECT username, building_id, MAX(score) as best FROM minigame_scores "
        "WHERE played_at >= ? AND played_at < ? GROUP BY username, building_id",
        (week_start, week_end)
    ).fetchall()
    db.close()

    game_top    = {}
    player_best = {}
    for r in rows:
        player_best[(r["username"], r["building_id"])] = r["best"]
        game_top[r["building_id"]] = max(game_top.get(r["building_id"], 0), r["best"])

    totals = {}
    for (username, building_id), best in player_best.items():
        top = game_top.get(building_id, 0)
        contribution = (best / top * 100) if top > 0 else 0
        totals[username] = totals.get(username, 0) + contribution

    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


@app.route("/minigame/leaderboard")
def minigame_leaderboard_route():
    if not FEATURES.get("minigame_leaderboard", False):
        return jsonify({"status": "error", "message": "The weekly mini-game leaderboard isn't live yet."})
    username = request.args.get("username", "")
    week_start, week_end = _minigame_week_bounds()
    ranked = _compute_weekly_minigame_leaderboard(week_start, week_end)

    db = get_db()
    entries = []
    for i, (uname, total) in enumerate(ranked[:20], start=1):
        p = db.execute("SELECT penguin_name FROM penguins WHERE username=?", (uname,)).fetchone()
        entries.append({
            "rank":         i,
            "username":     uname,
            "penguin_name": (p["penguin_name"] if p else None) or uname,
            "score":        round(total, 1),
        })
    db.close()

    all_names   = [u for u, _ in ranked]
    player_rank = (all_names.index(username) + 1) if username in all_names else None
    return jsonify({
        "status":      "success",
        "entries":     entries,
        "player_rank": player_rank,
        "week_start":  week_start,
        "week_end":    week_end,
    })


# Tunable: linear reward curve for non-podium weekly-minigame ranks, mirroring
# calculate_rank_reward()'s raid curve but with its own podium size/resource
# range so retuning raid rewards can never silently retune this system too.
MINIGAME_WEEKLY_PODIUM_SIZE    = 3
MINIGAME_WEEKLY_RESOURCE_RANGE = (20, 200)  # (floor, ceiling) -- adjust freely


def calculate_minigame_rank_reward(rank, total_participants):
    lo, hi = MINIGAME_WEEKLY_RESOURCE_RANGE
    first_scaled_rank = MINIGAME_WEEKLY_PODIUM_SIZE + 1
    if total_participants <= first_scaled_rank:
        return hi
    span     = total_participants - first_scaled_rank
    position = (rank - first_scaled_rank) / span
    reward   = hi - position * (hi - lo)
    return max(lo, round(reward))


def resolve_weekly_minigame_leaderboard():
    """Saturday 00:00 UTC -- resolves the just-ended Mon->Sat minigame week.
    Rank 1/2/3 get 3/2/1 N00Tboxes (grant_lootbox, source "minigame_weekly"),
    ranks 4+ get a resource via the linear curve above, and the top 3 are
    announced in chat -- mirrors resolve_raid()'s reward pattern."""
    if not FEATURES.get("minigame_leaderboard", False):
        return
    try:
        now = int(time.time())
        # A minute before this exact midnight still falls inside the week
        # that's ending right now, so the boundaries computed from it are
        # the just-finished Mon->Sat window rather than the new one starting.
        week_start, week_end = _minigame_week_bounds(now - 60)
        ranked = _compute_weekly_minigame_leaderboard(week_start, week_end)
        if not ranked:
            print("[MinigameWeekly] No scores this week -- nothing to resolve.")
            return

        db = get_db()
        top3 = []
        for rank, (username, total) in enumerate(ranked, start=1):
            if rank <= MINIGAME_WEEKLY_PODIUM_SIZE:
                lootbox_count = MINIGAME_WEEKLY_PODIUM_SIZE - rank + 1
                db.commit()   # release the write lock -- grant_lootbox() opens its own connection
                grant_lootbox(username, lootbox_count, "minigame_weekly")
                top3.append(username)
            else:
                resource = random.choice(RESOURCE_TYPES)
                amount   = calculate_minigame_rank_reward(rank, len(ranked))
                ensure_resources(db, username)
                db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
                db.commit()   # same reason as above -- keep the lock free between iterations

        if top3:
            post_chat_message(
                db, MAYOR_USERNAME,
                f"🎮 Weekly Mini-Game Champions: {', '.join(top3)}! N00Tboxes awarded to the top 3!",
                now
            )
            db.commit()
        db.close()
        print(f"[MinigameWeekly] Resolved week {week_start}-{week_end}: {len(ranked)} player(s) ranked, top3={top3}")
    except Exception as e:
        print(f"[MinigameWeekly] ERROR resolving weekly leaderboard: {e}")


# Registered here (rather than alongside the raid/challenge jobs above) since
# resolve_weekly_minigame_leaderboard is defined much later in this file than
# that block — _scheduler is already running by this point, and add_job() on
# a live BackgroundScheduler is the documented way to add jobs after start().
# Saturday 00:00 UTC, same trigger time as start_raid ("start_raid" job,
# registered above) -- staggered by 2 minutes (rather than colliding with it
# or the 1-minute stagger already used between the Monday jobs) so the two
# unrelated reward systems never race for the same instant.
if _APSCHEDULER_AVAILABLE and (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug):
    _scheduler.add_job(resolve_weekly_minigame_leaderboard, "cron", day_of_week="sat", hour=0, minute=2,
                       id="resolve_minigame_weekly", misfire_grace_time=300)


@app.route("/mayor/debug/penguin", methods=["POST"])
def mayor_debug_penguin():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data     = request.get_json(silent=True) or {}
    target   = data.get("username", "").strip()
    if not target:
        return jsonify({"status": "error", "message": "username required."})

    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (target,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": f"Player '{target}' not found."})

    mayor = session.get("username") or "key-auth"
    changed = []

    # ── Resources ─────────────────────────────────────────────────────────────
    ensure_resources(db, target)
    res_fields = ["gold", "fish", "herbs", "blood_gems", "bones", "spell_fragments"]
    res_updates = {}
    for f in res_fields:
        if f in data:
            try:
                res_updates[f] = int(data[f])
            except (ValueError, TypeError):
                pass
    if res_updates:
        set_clause = ", ".join(f"{k}=?" for k in res_updates)
        db.execute(f"UPDATE resources SET {set_clause} WHERE username=?",
                   list(res_updates.values()) + [target])
        changed.append(f"resources: {res_updates}")

    # ── Penguin table fields ───────────────────────────────────────────────────
    penguin_updates = {}

    if "name" in data and data["name"].strip():
        penguin_updates["penguin_name"] = data["name"].strip()[:16]
        changed.append(f"name={penguin_updates['penguin_name']}")

    if "color" in data and re.match(r'^#[0-9a-fA-F]{6}$', data["color"]):
        penguin_updates["penguin_color"] = data["color"]
        changed.append(f"color={data['color']}")

    if "shape" in data and data["shape"] in ("normal", "tall"):
        penguin_updates["penguin_shape"] = data["shape"]
        changed.append(f"shape={data['shape']}")

    if "energy" in data:
        try:
            penguin_updates["energy"] = max(0, min(int(data["energy"]), p["max_energy"] or 100))
            changed.append(f"energy={penguin_updates['energy']}")
        except (ValueError, TypeError):
            pass

    # Level override: set xp to the minimum XP for that level
    if "level" in data:
        try:
            target_level = max(1, min(30, int(data["level"])))
            new_xp = sum(int(80 * (l ** 2.2)) for l in range(1, target_level))
            penguin_updates["level"] = target_level
            penguin_updates["xp"] = new_xp
            changed.append(f"level={target_level} xp={new_xp}")
        except (ValueError, TypeError):
            pass

    if penguin_updates:
        set_clause = ", ".join(f"{k}=?" for k in penguin_updates)
        db.execute(f"UPDATE penguins SET {set_clause} WHERE username=?",
                   list(penguin_updates.values()) + [target])

    # ── Streak ─────────────────────────────────────────────────────────────────
    streak_updates = {}
    if "current_streak" in data:
        try:
            streak_updates["current_streak"] = max(0, int(data["current_streak"]))
            changed.append(f"streak={streak_updates['current_streak']}")
        except (ValueError, TypeError):
            pass
    if "last_login_date" in data and re.match(r'^\d{4}-\d{2}-\d{2}$', data.get("last_login_date", "")):
        streak_updates["last_login_date"] = data["last_login_date"]
        changed.append(f"last_login_date={data['last_login_date']}")
    if streak_updates:
        db.execute("INSERT OR IGNORE INTO login_streaks (username, current_streak, longest_streak, last_login_date) VALUES (?,0,0,'')", (target,))
        set_clause = ", ".join(f"{k}=?" for k in streak_updates)
        db.execute(f"UPDATE login_streaks SET {set_clause} WHERE username=?",
                   list(streak_updates.values()) + [target])

    # ── Force-equip gear slot ──────────────────────────────────────────────────
    # data["equip"] = {"slot": "weapon", "item_id": "sword_01", "name": "Debug Sword", "type": "combat"}
    equip_req = data.get("equip")
    if equip_req and equip_req.get("slot"):
        slot      = equip_req["slot"].strip()
        item_id   = equip_req.get("item_id", f"debug_{slot}_{int(time.time())}").strip()
        name      = equip_req.get("name", f"Debug {slot.title()}").strip()
        item_type = equip_req.get("type", "combat").strip()
        # Unequip current in slot, then insert+equip new item
        db.execute("UPDATE gear SET equipped=0 WHERE username=? AND slot=? AND equipped=1", (target, slot))
        db.execute(
            "INSERT INTO gear (username, item_id, name, set_name, type, slot, rarity, "
            "attack_bonus, defense_bonus, speed_bonus, hp_bonus, combat_power, equipped, obtained_at) "
            "VALUES (?,?,?,NULL,?,?,'debug',0,0,0,0,0,1,?)",
            (target, item_id, name, item_type, slot, int(time.time()))
        )
        changed.append(f"equip slot={slot} item={item_id}")

    if not changed:
        db.close()
        return jsonify({"status": "ok", "message": "No changes applied."})

    db.commit()
    summary = "; ".join(changed)
    log_event(db, "admin_debug", f"👑 [DEBUG] {mayor} edited {target}: {summary}", target)
    import traceback as _tb
    print(f"[MAYOR DEBUG] {mayor} → {target}: {summary}")
    db.close()
    return jsonify({"status": "success", "target": target, "changed": changed})


@app.route("/mayor/debug/penguin/fetch", methods=["GET"])
def mayor_debug_penguin_fetch():
    """Return current state of a player for pre-filling the debug form."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    target = request.args.get("username", "").strip()
    if not target:
        return jsonify({"status": "error", "message": "username required."})
    db = get_db()
    p  = db.execute("SELECT * FROM penguins WHERE username=?", (target,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status": "error", "message": "Not found."})
    ensure_resources(db, target)
    r  = db.execute("SELECT * FROM resources WHERE username=?", (target,)).fetchone()
    ls = db.execute("SELECT current_streak, last_login_date FROM login_streaks WHERE username=?", (target,)).fetchone()
    db.close()
    return jsonify({
        "status": "ok",
        "player": {
            "username":       p["username"],
            "name":           p["penguin_name"] or "",
            "color":          p["penguin_color"] or "#1a1a1a",
            "shape":          p["penguin_shape"] or "normal",
            "level":          p["level"] or 1,
            "xp":             p["xp"] or 0,
            "energy":         p["energy"] or 0,
            "max_energy":     p["max_energy"] or 100,
            "gold":           r["gold"] if r else 0,
            "fish":           r["fish"] if r else 0,
            "herbs":          r["herbs"] if r else 0,
            "blood_gems":     r["blood_gems"] if r else 0,
            "bones":          r["bones"] if r else 0,
            "spell_fragments":r["spell_fragments"] if r else 0,
            "current_streak": ls["current_streak"] if ls else 0,
            "last_login_date":ls["last_login_date"] if ls else "",
        }
    })


# ── GLOBAL CHAT ──────────────────────────────────────────────────────────────

@app.route("/chat/messages")
def chat_get_messages():
    now    = int(time.time())
    cutoff = now - 86400          # last 24 hours only
    db     = get_db()
    rows   = db.execute(
        "SELECT username, message, created_at "
        "FROM chat_messages WHERE created_at > ? "
        "ORDER BY created_at ASC LIMIT 100",
        (cutoff,)
    ).fetchall()
    db.close()
    return jsonify({
        "messages": [
            {"username": r["username"], "message": r["message"], "created_at": r["created_at"]}
            for r in rows
        ]
    })


def post_chat_message(db, username, message, now=None):
    """Insert a chat message on an existing db handle. Shared by the player-facing
    /chat/send route (below) and system announcements like raid resolution —
    system callers skip the rate-limit/profanity checks since they're trusted."""
    db.execute(
        "INSERT INTO chat_messages (username, message, created_at) VALUES (?,?,?)",
        (username, message, now if now is not None else int(time.time()))
    )


@app.route("/chat/send", methods=["POST"])
def chat_send_message():
    data     = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    message  = data.get("message", "").strip()

    if not username or not message:
        return jsonify({"status": "error", "message": "Missing username or message."}), 400
    if len(message) > 200:
        return jsonify({"status": "error", "message": "Message too long (max 200 chars)."}), 400
    if _chat_has_profanity(message):
        return jsonify({"status": "filtered", "message": "Message contains disallowed content."}), 400

    now = int(time.time())
    db  = get_db()

    last_row = db.execute(
        "SELECT MAX(created_at) as t FROM chat_messages WHERE username=?", (username,)
    ).fetchone()
    last_ts = last_row["t"] if last_row else None
    if last_ts and (now - last_ts) < _CHAT_RATE_LIMIT_SECONDS:
        wait = _CHAT_RATE_LIMIT_SECONDS - (now - last_ts)
        db.close()
        return jsonify({"status": "rate_limited", "message": f"Please wait {wait}s before sending again."}), 429

    post_chat_message(db, username, message, now)
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


# ── PLAYER INTERESTS ─────────────────────────────────────────────────────────

def get_all_topics(db):
    """Hardcoded INTEREST_TOPICS plus mayor-approved custom_topics, merged.
    Custom topics never override a built-in key of the same name."""
    topics = dict(INTEREST_TOPICS)
    for row in db.execute("SELECT key, label, emoji FROM custom_topics").fetchall():
        topics.setdefault(row["key"], {"label": row["label"], "emoji": row["emoji"]})
    return topics


def _slugify_topic_key(text):
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug[:40] or f"topic_{int(time.time())}"


@app.route("/interests")
def get_interests():
    """Return the master topic list and the current player's selections."""
    username = session.get("username")
    selected = []
    db = get_db()
    if username:
        rows = db.execute(
            "SELECT interest_key FROM penguin_interests WHERE username=?", (username,)
        ).fetchall()
        selected = [r["interest_key"] for r in rows]
    topics = get_all_topics(db)
    db.close()
    return jsonify({
        "topics":   [{"key": k, **v} for k, v in topics.items()],
        "selected": selected,
        "max":      MAX_INTERESTS,
    })


@app.route("/interests/save", methods=["POST"])
def save_interests():
    """Replace a player's interest selections (up to MAX_INTERESTS)."""
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."}), 401
    data = request.get_json(force=True) or {}
    keys = data.get("interests", [])
    if not isinstance(keys, list):
        return jsonify({"status": "error", "message": "interests must be a list."}), 400
    db = get_db()
    all_topics = get_all_topics(db)
    valid = [k for k in keys if k in all_topics][:MAX_INTERESTS]
    db.execute("DELETE FROM penguin_interests WHERE username=?", (username,))
    for key in valid:
        db.execute(
            "INSERT OR IGNORE INTO penguin_interests (username, interest_key) VALUES (?,?)",
            (username, key)
        )
    db.commit()
    db.close()
    return jsonify({"status": "ok", "saved": valid})


@app.route("/interests/suggest", methods=["POST"])
def suggest_topic():
    """Submit a player suggestion for a new interest topic.
    Stored for admin review — not auto-added to the live list.
    Admin view: SELECT * FROM topic_suggestions ORDER BY created_at DESC;
    """
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not logged in."}), 401
    data       = request.get_json(force=True) or {}
    suggestion = data.get("suggestion", "").strip()
    if not suggestion:
        return jsonify({"status": "error", "message": "Suggestion cannot be empty."}), 400
    if len(suggestion) > 100:
        return jsonify({"status": "error", "message": "Suggestion too long (max 100 chars)."}), 400
    now = int(time.time())
    db  = get_db()
    recent = db.execute(
        "SELECT COUNT(*) as c FROM topic_suggestions WHERE username=? AND suggestion=? AND created_at > ?",
        (username, suggestion, now - 86400)
    ).fetchone()
    if recent and recent["c"] > 0:
        db.close()
        return jsonify({"status": "duplicate", "message": "You already suggested that recently."})
    db.execute(
        "INSERT INTO topic_suggestions (username, suggestion, created_at) VALUES (?,?,?)",
        (username, suggestion, now)
    )
    db.commit()
    db.close()
    return jsonify({"status": "ok"})


# ── MAYOR: TOPIC SUGGESTIONS ─────────────────────────────────────────────────

@app.route("/mayor/topic-suggestions")
def mayor_topic_suggestions():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM topic_suggestions WHERE status='pending' OR status IS NULL "
        "ORDER BY created_at DESC"
    ).fetchall()
    db.close()
    return jsonify({"status": "success", "suggestions": [dict(r) for r in rows]})


@app.route("/mayor/topic-suggestions/accept", methods=["POST"])
def mayor_accept_topic_suggestion():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data = request.get_json(force=True) or {}
    sid  = data.get("id")
    db   = get_db()
    row  = db.execute("SELECT * FROM topic_suggestions WHERE id=?", (sid,)).fetchone()
    if not row:
        db.close()
        return jsonify({"status": "error", "message": "Suggestion not found."}), 404
    key = _slugify_topic_key(row["suggestion"])
    if key not in get_all_topics(db):
        db.execute(
            "INSERT OR IGNORE INTO custom_topics (key, label, emoji, created_at) VALUES (?,?,?,?)",
            (key, row["suggestion"], "🏷️", int(time.time()))
        )
    db.execute("UPDATE topic_suggestions SET status='accepted' WHERE id=?", (sid,))
    db.commit()
    db.close()
    return jsonify({"status": "success", "key": key})


@app.route("/mayor/topic-suggestions/reject", methods=["POST"])
def mayor_reject_topic_suggestion():
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data = request.get_json(force=True) or {}
    sid  = data.get("id")
    db   = get_db()
    if not db.execute("SELECT 1 FROM topic_suggestions WHERE id=?", (sid,)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": "Suggestion not found."}), 404
    # Marked dismissed, not deleted — keeps a full history of past suggestions.
    db.execute("UPDATE topic_suggestions SET status='rejected' WHERE id=?", (sid,))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/mayor/topics/add", methods=["POST"])
def mayor_add_topic():
    """Let the mayor add a topic directly to the live list, bypassing suggestions."""
    if not _is_mayor_authed():
        return jsonify({"status": "error", "message": "Unauthorized."}), 403
    data  = request.get_json(force=True) or {}
    label = (data.get("label") or "").strip()
    emoji = (data.get("emoji") or "🏷️").strip() or "🏷️"
    if not label:
        return jsonify({"status": "error", "message": "Label cannot be empty."}), 400
    if len(label) > 40:
        return jsonify({"status": "error", "message": "Label too long (max 40 chars)."}), 400
    db  = get_db()
    key = _slugify_topic_key(label)
    if key in get_all_topics(db):
        db.close()
        return jsonify({"status": "error", "message": f"Topic '{label}' already exists."}), 400
    db.execute(
        "INSERT INTO custom_topics (key, label, emoji, created_at) VALUES (?,?,?,?)",
        (key, label, emoji, int(time.time()))
    )
    db.commit()
    db.close()
    return jsonify({"status": "success", "key": key, "label": label, "emoji": emoji})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
