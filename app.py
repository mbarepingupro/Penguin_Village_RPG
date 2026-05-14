from dotenv import load_dotenv
import os
import datetime
from flask import Flask, jsonify, redirect, request, session, url_for, render_template
from database import init_db, get_db
import time
import requests as http_requests
import random

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
SECRET_KEY = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY

MISSION_DEFS = {
    "login_today":  {"title": "SHOW UP",      "desc": "Log in to the village today",        "coins": 5,  "target": 1, "stream": False, "icon": "🐧"},
    "work_today":   {"title": "CLOCK IN",      "desc": "Send your penguin to work",          "coins": 5,  "target": 1, "stream": False, "icon": "⚒️"},
    "collect_1":    {"title": "FIRST HAUL",    "desc": "Collect your earnings once",         "coins": 8,  "target": 1, "stream": False, "icon": "💰"},
    "collect_3":    {"title": "HARD WORKER",   "desc": "Collect earnings 3 times today",     "coins": 20, "target": 3, "stream": False, "icon": "⛏️"},
    "watch_stream": {"title": "LOYAL VIEWER",  "desc": "Watch the stream for 30 minutes",   "coins": 25, "target": 1, "stream": True,  "icon": "📺"},
    "chat_stream":  {"title": "CHATTERBOX",    "desc": "Send a message during the stream",   "coins": 15, "target": 1, "stream": True,  "icon": "💬"},
}
DAILY_MISSIONS = list(MISSION_DEFS.keys())

FURNITURE_CATALOG = {
    "rug":     {"name": "COSY RUG",    "cost":  8, "icon": "🟥"},
    "lamp":    {"name": "ICE LAMP",    "cost":  8, "icon": "🕯️"},
    "chair":   {"name": "ICE CHAIR",   "cost": 15, "icon": "🪑"},
    "plant":   {"name": "SNOW PLANT",  "cost": 12, "icon": "🌿"},
    "table":   {"name": "FISH TABLE",  "cost": 20, "icon": "🍽️"},
    "tv":      {"name": "STREAM TV",   "cost": 25, "icon": "📺"},
    "bed":     {"name": "SNOW BED",    "cost": 30, "icon": "🛏️"},
    "fishtank":{"name": "FISH TANK",   "cost": 35, "icon": "🐠"},
    "penguin": {"name": "PET PENGUIN", "cost": 40, "icon": "🐧"},
    "trophy":  {"name": "TROPHY",      "cost": 50, "icon": "🏆"},
}
IGLOO_COLS = 11
IGLOO_ROWS = 8

BUILDINGS = {
    "cursed_temple": {
        "name": "Cursed Temple", "icon": "⛩️",
        "desc": "Enlightenment costs extra. Spells available while stocks last.",
        "type": "job", "job": "monk", "job_label": "MONK",
        "produces": {"xp": 5, "spell_fragments": 0.2},
        "energy_cost": 25, "pos": {"x": 9, "y": 30},
    },
    "hotel": {
        "name": "Penguin Hotel", "icon": "🏨",
        "desc": "Clean sheets. Warm beds. They charge too much.",
        "type": "rest", "rest_cost": 30,
        "pos": {"x": 12, "y": 62},
    },
    "horny_jail": {
        "name": "Horny Jail", "icon": "🔒",
        "desc": "You're not getting out of here. (Coming soon)",
        "type": "placeholder",
        "pos": {"x": 24, "y": 63},
    },
    "award_hall": {
        "name": "Award Hall", "icon": "🏆",
        "desc": "Your accomplishments. Such as they are. Displayed for all to see.",
        "type": "achievements",
        "pos": {"x": 30, "y": 48},
    },
    "sea_lion_pit": {
        "name": "Ash's Sea Lion Pit", "icon": "🦭",
        "desc": "Throw some fish. Get some fish back. Ash has a system.",
        "type": "job", "job": "fishing", "job_label": "FISHING",
        "produces": {"fish": 1},
        "energy_cost": 10, "pos": {"x": 36, "y": 62},
    },
    "parkmusement": {
        "name": "Ash's Parkmusement", "icon": "🎪",
        "desc": "Juggle. Fall down. Get paid. The circus life chose you.",
        "type": "job", "job": "circus", "job_label": "CIRCUS",
        "produces": {"coins": 2},
        "energy_cost": 20, "pos": {"x": 47, "y": 48},
    },
    "club_soda": {
        "name": "Club Soda", "icon": "🌿",
        "desc": "Herbal tea. Herbal music. Herbal vibes. Very herbal.",
        "type": "job", "job": "herbalism", "job_label": "HERBALISM",
        "produces": {"herbs": 1},
        "energy_cost": 15, "pos": {"x": 67, "y": 58},
    },
    "barracks": {
        "name": "Penguin Barracks", "icon": "⚔️",
        "desc": "Sign up. Show up. Try not to die.",
        "type": "combat",
        "pos": {"x": 79, "y": 57},
    },
    "guillotine": {
        "name": "Gil the Guillotine", "icon": "💀",
        "desc": "A hard day's work. Blood gems don't collect themselves.",
        "type": "job", "job": "executioner", "job_label": "EXECUTIONER",
        "produces": {"blood_gems": 0.5, "bones": 1},
        "energy_cost": 30, "pos": {"x": 84, "y": 58},
    },
}

MONSTERS = {
    "snow_crab":      {"name":"Snow Crab",      "tier":1,"min_level":1,"hp":30, "attack":5, "defense":3, "rewards":{"fish":5,"xp":10},              "drop_name":"Ice Shard",       "drop_chance":0.3,"icon":"🦀"},
    "ice_bat":        {"name":"Ice Bat",         "tier":1,"min_level":1,"hp":20, "attack":8, "defense":2, "rewards":{"herbs":3,"xp":8},               "drop_name":"Bat Wing",        "drop_chance":0.4,"icon":"🦇"},
    "frost_rat":      {"name":"Frost Rat",       "tier":1,"min_level":1,"hp":15, "attack":6, "defense":1, "rewards":{"bones":3,"xp":6},               "drop_name":"Rat Tail",        "drop_chance":0.5,"icon":"🐀"},
    "blizzard_wolf":  {"name":"Blizzard Wolf",   "tier":2,"min_level":4,"hp":60, "attack":15,"defense":8, "rewards":{"blood_gems":3,"xp":20},         "drop_name":"Wolf Fang",       "drop_chance":0.3,"icon":"🐺"},
    "cursed_snowman": {"name":"Cursed Snowman",  "tier":2,"min_level":4,"hp":50, "attack":12,"defense":10,"rewards":{"spell_fragments":3,"xp":18},    "drop_name":"Cursed Carrot",   "drop_chance":0.25,"icon":"☃️"},
    "shadow_penguin": {"name":"Shadow Penguin",  "tier":2,"min_level":4,"hp":55, "attack":14,"defense":7, "rewards":{"bones":5,"xp":22},              "drop_name":"Shadow Feather",  "drop_chance":0.2,"icon":"🐧"},
    "stone_golem":    {"name":"Stone Golem",     "tier":3,"min_level":7,"hp":120,"attack":25,"defense":20,"rewards":{"blood_gems":8,"xp":40},         "drop_name":"Stone Core",      "drop_chance":0.2,"icon":"🗿"},
    "sea_serpent":    {"name":"Sea Serpent",     "tier":3,"min_level":7,"hp":100,"attack":22,"defense":15,"rewards":{"fish":15,"xp":35},              "drop_name":"Serpent Scale",   "drop_chance":0.15,"icon":"🐍"},
    "dark_druid":     {"name":"Dark Druid",      "tier":3,"min_level":7,"hp":110,"attack":28,"defense":12,"rewards":{"spell_fragments":8,"herbs":5,"xp":45},"drop_name":"Druid Staff","drop_chance":0.1,"icon":"🧙"},
}

GEAR_CATALOG = {
    "fish_club":   {"name":"FISH CLUB",       "type":"combat",  "slot":"weapon","attack_bonus":5, "defense_bonus":0, "cost":{"coins":30},           "icon":"🐟"},
    "bone_dagger": {"name":"BONE DAGGER",     "type":"combat",  "slot":"weapon","attack_bonus":8, "defense_bonus":0, "cost":{"bones":5},            "icon":"🗡️"},
    "ice_sword":   {"name":"ICE SWORD",       "type":"combat",  "slot":"weapon","attack_bonus":14,"defense_bonus":0, "cost":{"fish":10,"coins":20}, "icon":"⚔️"},
    "blood_axe":   {"name":"BLOOD AXE",       "type":"combat",  "slot":"weapon","attack_bonus":20,"defense_bonus":0, "cost":{"blood_gems":8},       "icon":"🪓"},
    "fish_vest":   {"name":"FISH SCALE VEST", "type":"combat",  "slot":"armor", "attack_bonus":0, "defense_bonus":5, "cost":{"fish":8},             "icon":"🐠"},
    "bone_shield": {"name":"BONE SHIELD",     "type":"combat",  "slot":"armor", "attack_bonus":0, "defense_bonus":10,"cost":{"bones":8},            "icon":"🦴"},
    "ice_plate":   {"name":"ICE PLATE",       "type":"combat",  "slot":"armor", "attack_bonus":0, "defense_bonus":16,"cost":{"fish":12,"herbs":5},  "icon":"🧊"},
    "tophat":      {"name":"TOP HAT",         "type":"cosmetic","slot":"hat",   "attack_bonus":0, "defense_bonus":0, "cost":{"coins":25},           "icon":"🎩"},
    "party_hat":   {"name":"PARTY HAT",       "type":"cosmetic","slot":"hat",   "attack_bonus":0, "defense_bonus":0, "cost":{"coins":15},           "icon":"🎉"},
    "crown":       {"name":"CROWN",           "type":"cosmetic","slot":"hat",   "attack_bonus":0, "defense_bonus":0, "cost":{"coins":80},           "icon":"👑"},
    "red_cape":    {"name":"RED CAPE",        "type":"cosmetic","slot":"cape",  "attack_bonus":0, "defense_bonus":0, "cost":{"coins":20},           "icon":"🔴"},
    "star_cape":   {"name":"STAR CAPE",       "type":"cosmetic","slot":"cape",  "attack_bonus":0, "defense_bonus":0, "cost":{"herbs":5,"coins":30},"icon":"⭐"},
}

ACHIEVEMENT_DEFS = {
    "first_login":  {"title":"WELCOME HOME",      "desc":"Log in for the first time",       "icon":"🐧"},
    "first_job":    {"title":"CLOCK IN",          "desc":"Complete your first job",          "icon":"⚒️"},
    "first_fight":  {"title":"BRAVE (OR DUMB)",   "desc":"Fight your first monster",         "icon":"⚔️"},
    "first_kill":   {"title":"MONSTER SLAYER",    "desc":"Defeat your first monster",        "icon":"💀"},
    "level_5":      {"title":"RISING STAR",       "desc":"Reach level 5",                    "icon":"⭐"},
    "level_10":     {"title":"VILLAGE LEGEND",    "desc":"Reach level 10",                   "icon":"🌟"},
    "coins_100":    {"title":"GETTING PAID",      "desc":"Accumulate 100 coins",             "icon":"💰"},
    "coins_500":    {"title":"MONEY PENGUIN",     "desc":"Accumulate 500 coins",             "icon":"🤑"},
    "fish_50":      {"title":"FISHER PENGUIN",    "desc":"Catch 50 fish total",              "icon":"🎣"},
    "kill_10":      {"title":"HUNTER",            "desc":"Defeat 10 monsters total",         "icon":"🏹"},
    "igloo_5":      {"title":"HOME SWEET IGLOO",  "desc":"Place 5 items in your igloo",      "icon":"🏠"},
}


def get_today():
    return datetime.date.today().isoformat()

def advance_mission(db, username, key, today, amount=1):
    """Increment a mission's progress. Awards coins automatically on completion. Returns True if newly completed."""
    defn = MISSION_DEFS.get(key)
    if not defn:
        return False
    db.execute(
        "INSERT OR IGNORE INTO daily_missions (username, mission_key, date) VALUES (?, ?, ?)",
        (username, key, today)
    )
    row = db.execute(
        "SELECT progress, completed FROM daily_missions WHERE username=? AND mission_key=? AND date=?",
        (username, key, today)
    ).fetchone()
    if row is None or row["completed"]:
        return False
    target = defn["target"]
    new_progress = min(row["progress"] + amount, target)
    newly_completed = new_progress >= target
    db.execute(
        "UPDATE daily_missions SET progress=?, completed=? WHERE username=? AND mission_key=? AND date=?",
        (new_progress, 1 if newly_completed else 0, username, key, today)
    )
    if newly_completed:
        db.execute(
            "UPDATE penguins SET coins = coins + ? WHERE username = ?",
            (defn["coins"], username)
        )
    return newly_completed


def calc_level(xp):
    return min(10, xp // 100 + 1)

def ensure_resources(db, username):
    db.execute("INSERT OR IGNORE INTO resources (username) VALUES (?)", (username,))

def get_player_stats(db, username):
    p = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
    level = p["level"] if p else 1
    attack = level * 3
    defense = level * 2
    hp = level * 20
    equipped = db.execute(
        "SELECT attack_bonus, defense_bonus FROM gear WHERE username=? AND equipped=1", (username,)
    ).fetchall()
    for g in equipped:
        attack += g["attack_bonus"]
        defense += g["defense_bonus"]
    return {"attack": attack, "defense": defense, "hp": hp, "level": level}

def award_xp(db, username, amount):
    p = db.execute("SELECT xp, level FROM penguins WHERE username=?", (username,)).fetchone()
    if not p: return False
    new_xp = p["xp"] + amount
    new_level = calc_level(new_xp)
    db.execute("UPDATE penguins SET xp=?, level=? WHERE username=?", (new_xp, new_level, username))
    return new_level > p["level"]

def simulate_combat(player_stats, monster):
    php = player_stats["hp"]
    mhp = monster["hp"]
    patk = player_stats["attack"]
    pdef = player_stats["defense"]
    matk = monster["attack"]
    mdef = monster["defense"]
    for _ in range(200):
        if php <= 0 or mhp <= 0: break
        mhp -= max(1, patk - mdef // 2)
        php -= max(1, matk - pdef // 2)
    return php > 0

def check_achievements(db, username):
    p = db.execute("SELECT level, coins, xp FROM penguins WHERE username=?", (username,)).fetchone()
    r = db.execute("SELECT fish FROM resources WHERE username=?", (username,)).fetchone()
    kills = db.execute("SELECT COUNT(*) as c FROM monster_kills WHERE username=?", (username,)).fetchone()
    igloo = db.execute("SELECT COUNT(*) as c FROM igloo_items WHERE username=?", (username,)).fetchone()
    new_ach = []
    def try_unlock(aid):
        try:
            db.execute("INSERT INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
                       (username, aid, int(time.time())))
            new_ach.append(aid)
        except: pass
    if p:
        if p["level"] >= 5:  try_unlock("level_5")
        if p["level"] >= 10: try_unlock("level_10")
        if p["coins"] >= 100: try_unlock("coins_100")
        if p["coins"] >= 500: try_unlock("coins_500")
    if r and r["fish"] >= 50: try_unlock("fish_50")
    if kills and kills["c"] >= 1:  try_unlock("first_kill")
    if kills and kills["c"] >= 10: try_unlock("kill_10")
    if igloo and igloo["c"] >= 5:  try_unlock("igloo_5")
    return new_ach


# Set up the database when the server starts
init_db()

@app.route("/")
def home():
    username = session.get("username")
    if not username:
        return render_template("home.html", logged_in=False)

    db = get_db()
    penguin = db.execute(
        "SELECT * FROM penguins WHERE username = ?",
        (username,)
    ).fetchone()
    db.close()

    if penguin is None:
        session.clear()
        return render_template("home.html", logged_in=False)

    return render_template("home.html", logged_in=True, penguin=penguin)

@app.route("/login")
def login():
    twitch_auth_url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={TWITCH_CLIENT_ID}"
        f"&redirect_uri={TWITCH_REDIRECT_URI}"
        "&response_type=code"
        "&scope=user:read:email"
    )
    return redirect(twitch_auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")

    token_response = http_requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TWITCH_REDIRECT_URI,
    })
    print("TOKEN RESPONSE:", token_response.json())
    token_data = token_response.json()
    access_token = token_data.get("access_token")

    user_response = http_requests.get("https://api.twitch.tv/helix/users", headers={
        "Authorization": f"Bearer {access_token}",
        "Client-Id": TWITCH_CLIENT_ID
    })

    user_data = user_response.json()
    print("TWITCH RESPONSE:", user_data)
    username = user_data["data"][0]["login"]

    session["username"] = username

    # Auto-register if first time logging in, then mark daily login mission
    db = get_db()
    try:
        db.execute("INSERT INTO penguins (username) VALUES (?)", (username,))
        session["new_user"] = True
    except:
        session["new_user"] = False

    today = get_today()
    advance_mission(db, username, "login_today", today)
    ensure_resources(db, username)
    try_unlock = lambda aid: db.execute(
        "INSERT OR IGNORE INTO achievements (username, achievement_id, unlocked_at) VALUES (?,?,?)",
        (username, aid, int(time.time()))
    )
    try_unlock("first_login")
    db.commit()
    db.close()

    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/register/<username>")
def register(username):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute(
            "INSERT INTO penguins (username) VALUES (?)",
            (username,)
        )
        db.commit()
        return jsonify({
            "status": "success",
            "message": f"Welcome to the Penguin Village, {username}!",
            "penguin": {
                "username": username,
                "level": 1,
                "energy": 100,
                "coins": 0,
                "job": None,
                "job_started": 0
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"{username} already has a penguin!"
        })
    finally:
        db.close()

@app.route("/profile/<username>")
def profile(username):
    db = get_db()
    cursor = db.cursor()

    penguin = cursor.execute(
        "SELECT * FROM penguins WHERE username = ?",
        (username,)
    ).fetchone()

    db.close()

    if penguin is None:
        return jsonify({
            "status": "error",
            "message": f"{username} doesn't have a penguin yet!"
        })

    xp = penguin["xp"] if penguin["xp"] else 0
    next_level_xp = calc_level(xp) * 100
    xp_in_level = xp % 100

    return jsonify({
        "status": "success",
        "penguin": {
            "username": penguin["username"],
            "level": penguin["level"],
            "energy": penguin["energy"],
            "coins": penguin["coins"],
            "xp": xp,
            "xp_in_level": xp_in_level,
            "job": penguin["job"] if penguin["job"] else None,
            "job_started": penguin["job_started"]
        }
    })


@app.route("/building/<building_id>")
def building_info(building_id):
    b = BUILDINGS.get(building_id)
    if not b:
        return jsonify({"status":"error","message":"Unknown building."})
    username = request.args.get("username","")
    db = get_db()
    p = db.execute("SELECT job, job_started, energy, coins FROM penguins WHERE username=?", (username,)).fetchone()
    db.close()
    result = {**b, "building_id": building_id}
    if p:
        result["player_job"] = p["job"]
        result["player_job_started"] = p["job_started"]
        result["player_energy"] = p["energy"]
        result["player_coins"] = p["coins"]
        result["working_here"] = (p["job"] == building_id)
        if p["job"] == building_id and b.get("type") == "job":
            mins = (int(time.time()) - p["job_started"]) // 60
            result["minutes_worked"] = mins
            result["preview_earnings"] = {
                k: int(v * mins) for k, v in b["produces"].items()
            }
    return jsonify(result)


@app.route("/work/start", methods=["POST"])
def work_start():
    data = request.get_json(silent=True) or {}
    username = data.get("username","")
    building_id = data.get("building_id","")
    b = BUILDINGS.get(building_id)
    if not b or b.get("type") != "job":
        return jsonify({"status":"error","message":"Not a job building."})
    db = get_db()
    p = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status":"error","message":"Penguin not found."})
    if p["job"] is not None:
        db.close()
        return jsonify({"status":"error","message":f"Already working! Collect first."})
    energy_cost = b.get("energy_cost", 10)
    if p["energy"] < energy_cost:
        db.close()
        return jsonify({"status":"error","message":f"Need {energy_cost} energy."})
    db.execute(
        "UPDATE penguins SET job=?, job_started=?, energy=energy-? WHERE username=?",
        (building_id, int(time.time()), energy_cost, username)
    )
    today = get_today()
    advance_mission(db, username, "work_today", today)
    db.commit()
    db.close()
    return jsonify({"status":"success","message":f"Started {b['job_label']}!","building_id":building_id})


@app.route("/work/collect", methods=["POST"])
def work_collect():
    data = request.get_json(silent=True) or {}
    username = data.get("username","")
    db = get_db()
    p = db.execute("SELECT * FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status":"error","message":"Penguin not found."})
    if not p["job"]:
        db.close()
        return jsonify({"status":"error","message":"Not working."})
    b = BUILDINGS.get(p["job"])
    if not b:
        db.close()
        return jsonify({"status":"error","message":"Invalid job state."})
    mins = (int(time.time()) - p["job_started"]) // 60
    earned = {}
    leveled_up = False
    ensure_resources(db, username)
    for resource, rate in b.get("produces", {}).items():
        amount = int(rate * mins)
        if amount <= 0: continue
        earned[resource] = amount
        if resource == "coins":
            db.execute("UPDATE penguins SET coins=coins+? WHERE username=?", (amount, username))
        elif resource == "xp":
            leveled_up = award_xp(db, username, amount) or leveled_up
        else:
            db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
    db.execute("UPDATE penguins SET job=NULL, job_started=0 WHERE username=?", (username,))
    today = get_today()
    advance_mission(db, username, "collect_1", today)
    advance_mission(db, username, "collect_3", today)
    new_ach = check_achievements(db, username)
    if earned: check_achievements(db, username)
    db.commit()
    db.close()
    return jsonify({
        "status":"success",
        "earned": earned,
        "minutes": mins,
        "leveled_up": leveled_up,
        "new_achievements": new_ach,
        "building": b["name"],
    })


@app.route("/rest", methods=["POST"])
def rest():
    data = request.get_json(silent=True) or {}
    username = data.get("username","")
    db = get_db()
    p = db.execute("SELECT coins, energy FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status":"error","message":"Penguin not found."})
    cost = BUILDINGS["hotel"]["rest_cost"]
    if p["coins"] < cost:
        db.close()
        return jsonify({"status":"error","message":f"Need {cost} coins to rest."})
    db.execute("UPDATE penguins SET coins=coins-?, energy=100 WHERE username=?", (cost, username))
    db.commit()
    db.close()
    return jsonify({"status":"success","message":"Fully rested!","energy":100})


@app.route("/resources/<username>")
def get_resources(username):
    db = get_db()
    ensure_resources(db, username)
    r = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    db.commit()
    db.close()
    return jsonify(dict(r) if r else {})


@app.route("/combat/monsters")
def combat_monsters():
    username = request.args.get("username","")
    today = get_today()
    db = get_db()
    p = db.execute("SELECT level FROM penguins WHERE username=?", (username,)).fetchone()
    player_level = p["level"] if p else 1
    killed_today = set(
        row["monster_id"] for row in
        db.execute("SELECT monster_id FROM monster_kills WHERE username=? AND date=?", (username, today)).fetchall()
    )
    db.close()
    result = []
    for mid, m in MONSTERS.items():
        result.append({**m, "id": mid,
            "can_fight": player_level >= m["min_level"],
            "killed_today": mid in killed_today})
    return jsonify({"monsters": result, "player_level": player_level})


@app.route("/combat/fight", methods=["POST"])
def combat_fight():
    data = request.get_json(silent=True) or {}
    username = data.get("username","")
    monster_id = data.get("monster_id","")
    m = MONSTERS.get(monster_id)
    if not m:
        return jsonify({"status":"error","message":"Unknown monster."})
    today = get_today()
    db = get_db()
    p = db.execute("SELECT level, energy FROM penguins WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status":"error","message":"Penguin not found."})
    if p["level"] < m["min_level"]:
        db.close()
        return jsonify({"status":"error","message":f"Need level {m['min_level']}."})
    already = db.execute(
        "SELECT 1 FROM monster_kills WHERE username=? AND monster_id=? AND date=?",
        (username, monster_id, today)
    ).fetchone()
    if already:
        db.close()
        return jsonify({"status":"error","message":"Already fought this today."})
    stats = get_player_stats(db, username)
    won = simulate_combat(stats, m)
    drop = None
    new_ach = []
    ensure_resources(db, username)
    advance_mission(db, username, "first_fight", today)
    if won:
        for resource, amount in m["rewards"].items():
            if resource == "xp":
                award_xp(db, username, amount)
            elif resource == "coins":
                db.execute("UPDATE penguins SET coins=coins+? WHERE username=?", (amount, username))
            else:
                db.execute(f"UPDATE resources SET {resource}={resource}+? WHERE username=?", (amount, username))
        if random.random() < m["drop_chance"]:
            drop = m["drop_name"]
        db.execute(
            "INSERT OR IGNORE INTO monster_kills (username, monster_id, date) VALUES (?,?,?)",
            (username, monster_id, today)
        )
        new_ach = check_achievements(db, username)
    else:
        db.execute("UPDATE penguins SET energy=MAX(0,energy-20) WHERE username=?", (username,))
        award_xp(db, username, 2)
        db.execute(
            "INSERT OR IGNORE INTO monster_kills (username, monster_id, date) VALUES (?,?,?)",
            (username, monster_id, today)
        )
    db.commit()
    db.close()
    return jsonify({
        "status":"success",
        "won": won,
        "drop": drop,
        "rewards": m["rewards"] if won else {"xp":2},
        "new_achievements": new_ach,
    })


@app.route("/gear/inventory")
def gear_inventory():
    username = request.args.get("username","")
    db = get_db()
    rows = db.execute("SELECT * FROM gear WHERE username=?", (username,)).fetchall()
    db.close()
    return jsonify({"gear": [dict(r) for r in rows], "catalog": GEAR_CATALOG})


@app.route("/gear/buy", methods=["POST"])
def gear_buy():
    data = request.get_json(silent=True) or {}
    username = data.get("username","")
    item_id = data.get("item_id","")
    defn = GEAR_CATALOG.get(item_id)
    if not defn:
        return jsonify({"status":"error","message":"Unknown item."})
    db = get_db()
    p = db.execute("SELECT coins FROM penguins WHERE username=?", (username,)).fetchone()
    r = db.execute("SELECT * FROM resources WHERE username=?", (username,)).fetchone()
    if not p:
        db.close()
        return jsonify({"status":"error","message":"Penguin not found."})
    cost = defn["cost"]
    # Check can afford
    for resource, amount in cost.items():
        if resource == "coins":
            if p["coins"] < amount:
                db.close()
                return jsonify({"status":"error","message":f"Need {amount} coins."})
        else:
            have = r[resource] if r and resource in r.keys() else 0
            if have < amount:
                db.close()
                return jsonify({"status":"error","message":f"Need {amount} {resource}."})
    # Deduct
    for resource, amount in cost.items():
        if resource == "coins":
            db.execute("UPDATE penguins SET coins=coins-? WHERE username=?", (amount, username))
        else:
            db.execute(f"UPDATE resources SET {resource}={resource}-? WHERE username=?", (amount, username))
    db.execute(
        "INSERT INTO gear (username, item_id, name, type, slot, attack_bonus, defense_bonus) VALUES (?,?,?,?,?,?,?)",
        (username, item_id, defn["name"], defn["type"], defn["slot"],
         defn["attack_bonus"], defn["defense_bonus"])
    )
    db.commit()
    db.close()
    return jsonify({"status":"success","message":f"{defn['name']} purchased!"})


@app.route("/gear/equip", methods=["POST"])
def gear_equip():
    data = request.get_json(silent=True) or {}
    username = data.get("username","")
    gear_id = int(data.get("gear_id",0))
    db = get_db()
    item = db.execute("SELECT * FROM gear WHERE id=? AND username=?", (gear_id, username)).fetchone()
    if not item:
        db.close()
        return jsonify({"status":"error","message":"Item not found."})
    if item["equipped"]:
        db.execute("UPDATE gear SET equipped=0 WHERE id=?", (gear_id,))
        db.commit(); db.close()
        return jsonify({"status":"success","equipped":False,"message":f"{item['name']} unequipped."})
    # Unequip other items in same slot
    db.execute("UPDATE gear SET equipped=0 WHERE username=? AND slot=?", (username, item["slot"]))
    db.execute("UPDATE gear SET equipped=1 WHERE id=?", (gear_id,))
    db.commit(); db.close()
    return jsonify({"status":"success","equipped":True,"message":f"{item['name']} equipped."})


@app.route("/achievements/<username>")
def get_achievements(username):
    db = get_db()
    rows = db.execute(
        "SELECT achievement_id, unlocked_at FROM achievements WHERE username=?", (username,)
    ).fetchall()
    db.close()
    unlocked = {r["achievement_id"]: r["unlocked_at"] for r in rows}
    result = []
    for aid, defn in ACHIEVEMENT_DEFS.items():
        result.append({**defn, "id": aid, "unlocked": aid in unlocked,
                       "unlocked_at": unlocked.get(aid)})
    return jsonify({"achievements": result})


@app.route("/leaderboard")
def leaderboard():
    db = get_db()
    penguins = db.execute(
        "SELECT username, level, coins, job FROM penguins ORDER BY coins DESC LIMIT 20"
    ).fetchall()
    db.close()
    return jsonify({"penguins": [dict(p) for p in penguins]})

@app.route("/islive")
def islive():
    try:
        res = http_requests.get(
            "https://api.twitch.tv/helix/streams?user_login=mbarepingu",
            headers={
                "Client-Id": TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {os.getenv('TWITCH_APP_TOKEN', '')}"
            }
        )
        data = res.json()
        live = len(data.get("data", [])) > 0
        return jsonify({"live": live})
    except:
        return jsonify({"live": False})

@app.route("/missions/<username>")
def get_missions(username):
    today = get_today()
    db = get_db()
    for key in DAILY_MISSIONS:
        db.execute(
            "INSERT OR IGNORE INTO daily_missions (username, mission_key, date) VALUES (?, ?, ?)",
            (username, key, today)
        )
    db.commit()
    rows = db.execute(
        "SELECT mission_key, progress, completed FROM daily_missions WHERE username=? AND date=?",
        (username, today)
    ).fetchall()
    db.close()

    key_order = {k: i for i, k in enumerate(DAILY_MISSIONS)}
    missions = sorted([
        {
            "key":       row["mission_key"],
            "title":     MISSION_DEFS[row["mission_key"]]["title"],
            "desc":      MISSION_DEFS[row["mission_key"]]["desc"],
            "coins":     MISSION_DEFS[row["mission_key"]]["coins"],
            "target":    MISSION_DEFS[row["mission_key"]]["target"],
            "stream":    MISSION_DEFS[row["mission_key"]]["stream"],
            "icon":      MISSION_DEFS[row["mission_key"]]["icon"],
            "progress":  row["progress"],
            "completed": bool(row["completed"]),
        }
        for row in rows if row["mission_key"] in MISSION_DEFS
    ], key=lambda m: key_order.get(m["key"], 99))

    return jsonify({"missions": missions, "date": today})


@app.route("/missions/<username>/claim/<key>", methods=["POST"])
def claim_stream_mission(username, key):
    defn = MISSION_DEFS.get(key)
    if not defn or not defn.get("stream"):
        return jsonify({"status": "error", "message": "Not a claimable stream mission."})
    today = get_today()
    db = get_db()
    newly_done = advance_mission(db, username, key, today)
    db.commit()
    db.close()
    if newly_done:
        return jsonify({"status": "success", "message": f"Mission complete! +{defn['coins']} coins", "coins": defn["coins"]})
    return jsonify({"status": "error", "message": "Already completed or not available."})


@app.route("/igloo/<username>")
def get_igloo(username):
    db = get_db()
    items = db.execute(
        "SELECT id, item_key, x, y FROM igloo_items WHERE username=? ORDER BY id",
        (username,)
    ).fetchall()
    penguin = db.execute("SELECT coins FROM penguins WHERE username=?", (username,)).fetchone()
    db.close()
    return jsonify({
        "items":   [dict(r) for r in items],
        "coins":   penguin["coins"] if penguin else 0,
        "catalog": FURNITURE_CATALOG,
    })


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

    penguin = db.execute("SELECT coins FROM penguins WHERE username=?", (username,)).fetchone()
    if not penguin or penguin["coins"] < cost:
        db.close()
        return jsonify({"status": "error", "message": f"Need {cost}G to buy that!"})

    if db.execute("SELECT id FROM igloo_items WHERE username=? AND x=? AND y=?", (username, x, y)).fetchone():
        db.close()
        return jsonify({"status": "error", "message": "That spot is taken!"})

    db.execute("UPDATE penguins SET coins = coins - ? WHERE username=?", (cost, username))
    cursor = db.execute(
        "INSERT INTO igloo_items (username, item_key, x, y) VALUES (?, ?, ?, ?)",
        (username, item_key, x, y)
    )
    new_id    = cursor.lastrowid
    new_coins = db.execute("SELECT coins FROM penguins WHERE username=?", (username,)).fetchone()["coins"]
    db.commit()
    db.close()

    return jsonify({
        "status": "success",
        "item":   {"id": new_id, "item_key": item_key, "x": x, "y": y},
        "coins":  new_coins,
    })


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

    occupant = db.execute(
        "SELECT id FROM igloo_items WHERE username=? AND x=? AND y=? AND id!=?",
        (username, x, y, item_id)
    ).fetchone()
    if occupant:
        db.close()
        return jsonify({"status": "error", "message": "That spot is taken!"})

    db.execute("UPDATE igloo_items SET x=?, y=? WHERE id=?", (x, y, item_id))
    db.commit()
    db.close()
    return jsonify({"status": "success"})


@app.route("/igloo/<username>/remove/<int:item_id>", methods=["POST"])
def igloo_remove(username, item_id):
    db   = get_db()
    item = db.execute(
        "SELECT item_key FROM igloo_items WHERE id=? AND username=?", (item_id, username)
    ).fetchone()
    if not item:
        db.close()
        return jsonify({"status": "error", "message": "Item not found."})

    refund = FURNITURE_CATALOG.get(item["item_key"], {}).get("cost", 0) // 2
    db.execute("DELETE FROM igloo_items WHERE id=?", (item_id,))
    db.execute("UPDATE penguins SET coins = coins + ? WHERE username=?", (refund, username))
    new_coins = db.execute("SELECT coins FROM penguins WHERE username=?", (username,)).fetchone()["coins"]
    db.commit()
    db.close()
    return jsonify({"status": "success", "refund": refund, "coins": new_coins})


@app.route("/active/<username>")
def active(username):
    db = get_db()
    cursor = db.cursor()

    penguin = cursor.execute(
        "SELECT * FROM penguins WHERE username = ?",
        (username,)
    ).fetchone()

    if penguin is None:
        db.close()
        return jsonify({"status": "skip"})

    now = int(time.time())

    # Calculate energy recovery based on last_active
    if penguin["last_active"] > 0:
        minutes_since_active = (now - penguin["last_active"]) // 60
        energy_recovered = minutes_since_active * 2
        new_energy = min(100, penguin["energy"] + energy_recovered)
    else:
        new_energy = penguin["energy"]
        energy_recovered = 0

    cursor.execute(
        "UPDATE penguins SET last_active = ?, energy = ? WHERE username = ?",
        (now, new_energy, username)
    )
    db.commit()
    db.close()

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
