from dotenv import load_dotenv
import os
import datetime
from flask import Flask, jsonify, redirect, request, session, url_for, render_template
from database import init_db, get_db
import time
import requests as http_requests

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
SECRET_KEY = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY
VALID_JOBS = ["fishing", "mining", "foraging"]
jobs_list = ", ".join(VALID_JOBS)

MISSION_DEFS = {
    "login_today":  {"title": "SHOW UP",      "desc": "Log in to the village today",        "coins": 5,  "target": 1, "stream": False, "icon": "🐧"},
    "work_today":   {"title": "CLOCK IN",      "desc": "Send your penguin to work",          "coins": 5,  "target": 1, "stream": False, "icon": "⚒️"},
    "collect_1":    {"title": "FIRST HAUL",    "desc": "Collect your earnings once",         "coins": 8,  "target": 1, "stream": False, "icon": "💰"},
    "collect_3":    {"title": "HARD WORKER",   "desc": "Collect earnings 3 times today",     "coins": 20, "target": 3, "stream": False, "icon": "⛏️"},
    "watch_stream": {"title": "LOYAL VIEWER",  "desc": "Watch the stream for 30 minutes",   "coins": 25, "target": 1, "stream": True,  "icon": "📺"},
    "chat_stream":  {"title": "CHATTERBOX",    "desc": "Send a message during the stream",   "coins": 15, "target": 1, "stream": True,  "icon": "💬"},
}
DAILY_MISSIONS = list(MISSION_DEFS.keys())

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
    print("TWITCH RESPONSE:", user_data)  # temporary debug line
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
    
    return jsonify({
        "status": "success",
        "penguin": {
            "username": penguin["username"],
            "level": penguin["level"],
            "energy": penguin["energy"],
            "coins": penguin["coins"],
            "job": penguin["job"] if penguin["job"] else "resting",
            "job_started": penguin["job_started"]
        }
    })

@app.route("/work/<username>/<job>")
def work(username, job):
    db = get_db()
    cursor = db.cursor()

    penguin = cursor.execute(
        "SELECT * FROM penguins WHERE username = ?",
        (username,)
    ).fetchone()

    if penguin is None:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"{username} doesn't have a penguin yet!"
        })
    
    if not job:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"Please specify a job! Avalaible jobs: {jobs_list}"
        })
    
    if job.lower() not in jobs_list:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"{job} is not valid job! Available jobs: {jobs_list}"
        })

    if penguin["job"] is not None:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"{username} is already working as {penguin['job']}!"
        })
    
    cursor.execute(
        "UPDATE penguins SET job = ?, job_started = ? WHERE username = ?",
        (job, int(time.time()), username)
    )
    today = get_today()
    advance_mission(db, username, "work_today", today)
    db.commit()
    db.close()

    if request.args.get("redirect"):
        return redirect(url_for("home"))
    return jsonify({
        "status": "success",
        "message": f"{username} started {job}!",
        "job": job
    })

@app.route("/collect/<username>")
def collect(username):
    db = get_db()
    cursor = db.cursor()

    penguin = cursor.execute(
        "SELECT * FROM penguins WHERE username = ?",
        (username,)
    ).fetchone()

    if penguin is None:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"{username} doesn't have a penguin yet!"
        })
    
    if penguin["job"] is None:
        db.close()
        return jsonify({
            "status": "error",
            "message": f"{username} is not currently working!"
        })
    
    seconds_worked = int(time.time()) - penguin["job_started"]
    minutes_worked = seconds_worked // 60
    coins_earned = minutes_worked

    cursor.execute(
        "UPDATE penguins SET coins = coins + ?, job = NULL, job_started = 0 WHERE username = ?",
        (coins_earned, username)
    )
    today = get_today()
    m1 = advance_mission(db, username, "collect_1", today)
    m3 = advance_mission(db, username, "collect_3", today)
    db.commit()
    db.close()

    missions_completed = [k for k, v in [("collect_1", m1), ("collect_3", m3)] if v]

    if request.args.get("redirect"):
        return redirect(url_for("home"))
    return jsonify({
        "status": "success",
        "message": f"{username} collected {coins_earned} coins from {penguin['job']}!",
        "coins_earned": coins_earned,
        "minutes_worked": minutes_worked,
        "missions_completed": missions_completed
    })

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

    cursor.execute(
        "UPDATE penguins SET last_active = ?, energy = ? WHERE username = ?",
        (now,energy_recovered, username)
    )
    db.commit()
    db.close()

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
