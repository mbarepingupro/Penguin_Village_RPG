from dotenv import load_dotenv
import os
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
        "redirect_uri": TWITCH_REDIRECT_URI
    })

    token_data = token_response.json()
    access_token = token_data.get("access_token")

    user_response = http_requests.get("https://api.twitch.tv/helix/users", headers={
        "Authorization": f"Bearer {access_token}",
        "Client-Id": TWITCH_CLIENT_ID
    })

    user_data = user_response.json()
    username = user_data["data"][0]["login"]

    session["username"] = username

    # Auto-register if first time logging in
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO penguins (username) VALUES (?)",
            (username,)
        )
        db.commit()
        session["new_user"] = True
    except:
        session["new_user"] = False
    finally:
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
    db.commit()
    db.close()

    if request.args.get("redirect"):
        return redirect(url_for("home"))
    return jsonify({
        "status": "success",
        "message": f"{username} collected {coins_earned} coins from {penguin['job']}!",
        "coins_earned": coins_earned,
        "minutes_worked": minutes_worked
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
