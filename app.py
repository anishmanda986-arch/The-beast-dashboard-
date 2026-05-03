from flask import Flask, render_template, redirect, url_for, session, request, jsonify, g
import requests
import os
import sqlite3
import json
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "nexus-super-secret-key-change-this")

DB_PATH = os.path.join(os.path.dirname(__file__), "../bot/data/nexus.db")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
DISCORD_API = "https://discord.com/api/v10"
OAUTH_URL = (
    f"https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
    f"&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify+guilds"
)

# ── DB ─────────────────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def db_query(sql, params=(), one=False):
    cur = get_db().execute(sql, params)
    rows = cur.fetchone() if one else cur.fetchall()
    return rows

def db_execute(sql, params=()):
    db = get_db()
    db.execute(sql, params)
    db.commit()

# ── Auth ───────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if int(session["user"]["id"]) != OWNER_ID:
            return render_template("error.html", msg="Owner access only."), 403
        return f(*args, **kwargs)
    return decorated

def get_discord_user(token):
    r = requests.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {token}"})
    return r.json() if r.ok else None

def get_discord_guilds(token):
    r = requests.get(f"{DISCORD_API}/users/@me/guilds", headers={"Authorization": f"Bearer {token}"})
    return r.json() if r.ok else []

# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    user = session.get("user")
    return render_template("index.html", user=user, oauth_url=OAUTH_URL)

@app.route("/login")
def login():
    return redirect(OAUTH_URL)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    r = requests.post(f"{DISCORD_API}/oauth2/token", data=data)
    if not r.ok:
        return redirect(url_for("index"))
    tokens = r.json()
    user = get_discord_user(tokens["access_token"])
    if not user:
        return redirect(url_for("index"))
    session["user"] = user
    session["access_token"] = tokens["access_token"]
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = session["user"]
    is_owner = int(user["id"]) == OWNER_ID
    # Stats
    total_users = db_query("SELECT COUNT(DISTINCT user_id) as c FROM users", one=True)["c"]
    total_balance = db_query("SELECT COALESCE(SUM(balance),0) as s FROM users", one=True)["s"]
    pending_withdrawals = db_query("SELECT COUNT(*) as c FROM withdrawals WHERE status='pending'", one=True)["c"]
    open_tickets = db_query("SELECT COUNT(*) as c FROM tickets WHERE status='open'", one=True)["c"]
    recent_logs = db_query("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 8")
    return render_template(
        "dashboard.html",
        user=user, is_owner=is_owner,
        total_users=total_users,
        total_balance=round(float(total_balance), 2),
        pending_withdrawals=pending_withdrawals,
        open_tickets=open_tickets,
        recent_logs=recent_logs,
        page="dashboard"
    )

@app.route("/users")
@login_required
def users():
    user = session["user"]
    is_owner = int(user["id"]) == OWNER_ID
    search = request.args.get("q", "")
    if search:
        rows = db_query(
            "SELECT * FROM users WHERE CAST(user_id AS TEXT) LIKE ? ORDER BY balance DESC LIMIT 50",
            (f"%{search}%",)
        )
    else:
        rows = db_query("SELECT * FROM users ORDER BY balance DESC LIMIT 100")
    return render_template("users.html", user=user, is_owner=is_owner, users=rows, search=search, page="users")

@app.route("/withdrawals")
@login_required
def withdrawals():
    user = session["user"]
    is_owner = int(user["id"]) == OWNER_ID
    status_filter = request.args.get("status", "")
    if status_filter:
        rows = db_query("SELECT * FROM withdrawals WHERE status=? ORDER BY created_at DESC", (status_filter,))
    else:
        rows = db_query("SELECT * FROM withdrawals ORDER BY created_at DESC LIMIT 100")
    return render_template("withdrawals.html", user=user, is_owner=is_owner, withdrawals=rows, status_filter=status_filter, page="withdrawals")

@app.route("/tickets")
@login_required
def tickets():
    user = session["user"]
    is_owner = int(user["id"]) == OWNER_ID
    rows = db_query("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 100")
    return render_template("tickets.html", user=user, is_owner=is_owner, tickets=rows, page="tickets")

@app.route("/settings")
@owner_required
def settings():
    user = session["user"]
    guilds = db_query("SELECT * FROM guilds")
    return render_template("settings.html", user=user, is_owner=True, guilds=guilds, page="settings")

# ── API ────────────────────────────────────────────────────────────────────────
@app.route("/api/user/<int:user_id>/balance", methods=["POST"])
@owner_required
def api_set_balance(user_id):
    data = request.get_json()
    amount = float(data.get("amount", 0))
    hold = bool(data.get("hold", False))
    col = "hold_balance" if hold else "balance"
    guild_id = int(data.get("guild_id", 0))
    db_execute(f"UPDATE users SET {col}=? WHERE user_id=? AND guild_id=?", (amount, user_id, guild_id))
    return jsonify({"success": True})

@app.route("/api/withdrawal/<int:wid>/approve", methods=["POST"])
@owner_required
def api_approve_withdrawal(wid):
    w = db_query("SELECT * FROM withdrawals WHERE id=?", (wid,), one=True)
    if not w:
        return jsonify({"error": "Not found"}), 404
    db_execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
    db_execute("UPDATE users SET hold_balance=hold_balance-? WHERE user_id=? AND guild_id=?",
               (w["amount"], w["user_id"], w["guild_id"]))
    return jsonify({"success": True})

@app.route("/api/withdrawal/<int:wid>/reject", methods=["POST"])
@owner_required
def api_reject_withdrawal(wid):
    data = request.get_json()
    reason = data.get("reason", "Rejected by admin")
    w = db_query("SELECT * FROM withdrawals WHERE id=?", (wid,), one=True)
    if not w:
        return jsonify({"error": "Not found"}), 404
    db_execute("UPDATE withdrawals SET status='rejected', note=? WHERE id=?", (reason, wid))
    db_execute("UPDATE users SET hold_balance=hold_balance-?, balance=balance+? WHERE user_id=? AND guild_id=?",
               (w["amount"], w["amount"], w["user_id"], w["guild_id"]))
    return jsonify({"success": True})

@app.route("/api/settings/task", methods=["POST"])
@owner_required
def api_update_task():
    data = request.get_json()
    guild_id = int(data.get("guild_id", 0))
    task = data.get("task", "")
    db_execute("UPDATE guilds SET earn_task=? WHERE guild_id=?", (task, guild_id))
    return jsonify({"success": True})

@app.route("/api/stats")
@login_required
def api_stats():
    rows = db_query(
        "SELECT DATE(timestamp) as day, SUM(amount) as total FROM transactions WHERE amount>0 GROUP BY day ORDER BY day DESC LIMIT 7"
    )
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    app.run(debug=True, port=5000)
