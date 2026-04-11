from flask import Flask, jsonify
from database import init_db, get_db
import time

app = Flask(__name__)
VALID_JOBS = ["fishing", "mining", "foraging"]
jobs_list = ", ".join(VALID_JOBS)

# Set up the database when the server starts
init_db()

@app.route("/")
def home():
    return "Penguin Village is alive"

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

    return jsonify({
        "status": "success",
        "message": f"{username} collected {coins_earned} coins from {penguin['job']}!",
        "coins_earned": coins_earned,
        "minutes_worked": minutes_worked
    })

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
    app.run(debug=True)