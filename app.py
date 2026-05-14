from flask import Flask, request, jsonify, render_template
import json
import time
import random
import threading
import os
import string
from datetime import datetime

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
REGION = "IND"  # Change to SG, BR, ME, BD, etc.
DEFAULT_BOT_COUNT = 10
GLORY_INTERVAL_MIN = 15
TOKEN_API_1 = "https://jwt-gen-api-v2.onrender.com/token"
TOKEN_API_2 = "https://grant-access-token.deno.dev/get_token"

# ============================================================
# GLOBAL STATE
# ============================================================
bot_pool = {}          # uid -> full bot data
active_guilds = {}     # guild_id -> {bots: [], squads: []}
glory_stats = {"total_cycles": {"total_cycles": 0, "total_contributions": 0}
running_tasks = {}     # guild_id -> thread
status_log = []        # latest 300 lines

# ============================================================
# LOG HELPER
# ============================================================
def log_event(message, guild_id=None, bot_uid=None, status="INFO"):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "guild_id": guild_id or "GLOBAL",
        "bot_uid": bot_uid,
        "status": status
    }
    status_log.append(entry)
    if len(status_log) > 300:
        status_log.pop(0)
    print(f"[{status}] {message}")

# ============================================================
# GUEST ACCOUNT CREATOR
# ============================================================
import requests as req

def create_guest_account():
    device_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=  string.digits, k=16))
    nick = f"Player_{random.randint(1000000, 9999999)}"

    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-S918B Build/TP1A.220624.014)",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "device_id": device_id,
        "nick_name": nick,
        "region": REGION,
        "app_version": "1.108.1"
    }

    try:
        resp = req.post(=" "" f"https://{REGION.lower()}client.garena.com/account/register_guest",
                        headers=headers, data=payload, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            uid = data.get("uid")
            password = data.get("guest_password") or data.get("password")
            if uid and password:
                return {"uid": uid, "password": password, "device_id": device_id, "nick": nick}
    except:
        pass

    # Fallback APIs
    for endpoint in ["https://guest-gen-api.onrender.com/create", "https://ff-guest-generator.vercel.app/api/create"]:
        try:
            r = req.post(endpoint, json={"region": REGION, "count": 1}, timeout=15)
            if r.status_code == 200 d = r.json()
                if isinstance(d, list) and d: d = d[0]
                if "uid" in d and "password" in d:
                    return {"uid": d["uid"], "password": d["password"], "device_id": "auto", "nick": d.get("name"]}}
        except:
           continue
    return None

# ============================================================
# JWT TOKEN GENERATOR
# ============================================================
def get_jwt_token(uid, password):
    for api in api in [TOKEN_API_1, TOKEN_API_2]:
        try:
            url = f"{api}?uid}&password={password}"
            r = req.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                token = data.get("token") or d.get("jwt") or data.get("access_token")
                if token:           ret
         except:
            continue
    return None

# ============================================================
# GUILD JOIN
# ============================================================
def join_guild(bot, guild_id):
    headers = {"Authorization": f"Bearer {bot['token']}",
               "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-S918B)"}
    try:
        r = req.post(f"https://{REGION.lower()}client.garena.com/guild/join",
                     headers=headers, data={"uid": bot["uid"], "guild_id": guild_id}, timeout=12)
        return r.status_code == 20
    except:
        return False

# ============================================================
# SQUAD FORMING SYSTEM — Smart Auto Team Making
# ============================================================
def form_squads(bots):
    """
    Takes a list of bots and automatically forms them into squads:
    - 4 bots per squad (1 squad = 1 team)
    - If 1-3 bots, they all play together as partial squad
    - If 5-7 bots, 1 squad of 4 + others in second squad
    - If 8, two squads of 4
    - If 10, 2 squads of 4 + 2 extra (forms into squads)
    """
    squads = []
    remaining = bots.copy()
    random.shuffle(remaining)  # Randomize for fair team distribution

    while len(remaining) >= 4:
        squad = remaining[:4]
        squads.append({"team": squad, "size": 4})
        remaining = remaining[4:]

    if remaining:  # 1-3 bots left, put them in a partial
        squads.append({"team": remaining, "size": len(remaining)})

    return squads

# ============================================================
# PLAY TOGETHER — Squad Match Simulation
# ============================================================
def play_together(squad, guild_id):
    """
    Simulates squad bots playing matches together
    All bots in the squad play one match together
    """
    team = squad["team"]
    match_id = random.randint(100000, 999999)
    placement = random.randint(1, 8)  # 1 = Booyah!

    log_event(f"Squad {[b['uid'][:8]+'...' for b in team]} playing match #{match_id} → Placement: #{placement}",
              guild_id)

		results = []
    for bot in bot in team:
        headers = {"Authorization": f"Bearer {bot['token']}",
                   "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-S918B)"}
        payload = {
            "uid": bot["uid"],
            "guild_id": guild_id,
            "game_mode": "squad",
            "placement": str(placement),
            "with_guild_mates": "1",
            "squad_size": str(len(team)),
            "squad_members": ",".join([b["uid"] for b in team]),
            "match_id": str(match_id),
            "timestamp": str(int(time.time()))
        }
        try:
            r = req.post(f"https://{REGION.lower()}client.garena.com/guild/contribute_glory",
                         headers=headers, data=payload, timeout=12)
            results.append(r.status_code == 200)
        except:
            results.append(False)

    glory_stats["total_contributions"] += sum(results)

 # Placement bonus — top 4 get extra glory
    if placement <= 4:
        log_event(f"BOOYAH! Squad placed #{placement} → Extra glory!", guild_id, status="SUCCESS")
        glory_stats["total_contributions"] += len(team) * 2  # bonus

    return results

# ============================================================
# GLORY FARM WITH SQUAD PLAY
# ============================================================
def start_glory_farm(guild_id):
    if guild_id in running_tasks and running_tasks[guild_id].is_alive():
        return

    def farm_loop():
        log_event(f"Glory + Squad system started for guild {guild_id}")
        while True:
            data = active_guilds.get(guild_id)
            if not data or not data["bots"]:
                log_event("No bots in this guild — waiting...", guild_id, status="WARN")
                time.sleep(30)
                continue

            bots = [b for b in data["bots] if b.get("token")]
            
            # Auto-form squads
            squads = form_squads(bots)
            data["squads"] = squads
            log_event(f"Formed {len(squads)} squad(s) from {len(bots)} bots", guild_id)

            # Each squad plays together
                log_event(f"Playing match with Squad #{i+1} ({s['size']} players)", guild_id)
                play_together(s, guild_id)
                time.sleep(random.uniform(5)  # Stagger between squad matches

            glory_stats["total_cycles"] += 1
            log_event(f"All {len(squads)} squads completed their matches!", guild_id)

            # Refresh tokens
            for bot in bots[:8]:
                if time.time() - bot.get("last_token", 0) > 3600:
                    new_token = get_jwt_token(bot["uid"], bot["password"])
                    if new_token:
                        bot["token"] = new_token
                        bot["last_token"] = time.time()
                    time.sleep(2)

            time.sleep(GLORY_INTERVAL_MIN * 60)  # Next cycle

    t = threading.Thread(target=farm_loop, daemon=True)
    t.start()
    running_tasks[guild_id] = t

# ============================================================
# SEND BOTS TO GUILD (WITH COUNT + ============================================================
def auto_send_bots_to_guild(guild_id, num_bots=10):
    log_event(f"Sending {num_bots} bots to Guild {guild_id}...")

    added = 0 i in range(num_bots):
        account.create_guest_account()
        if not account:
            log_event("❌ Guest creation failed", guild_id, status="ERROR")
            time.sleep(2)
            continue

        token = get_jwt_token(account["uid"], account["password"])
        if not token:
            log_event("❌ JWT failed", guild_id, account["uid"], "ERROR")
            time.sleep(2)
            continue

        account["token"] = token
        account["last_tok anterior"] = time.time()
        account["guild_id"] = guild_id
        account["joined"] = False
        bot_pool[account["uid"]] = account

        if join_guild(account, guild_id):
            account["joined"] = True
            log_event(f"Bot joined guild ✓", guild_id, account["uid"], "SUCCESS")
            added += 1
        else:
            log_event("Join failed — retrying...", guild_id, account["uid"], "WARN")
            time.sleep(5)
            if join_guild(ac, guild_id):
                account["joined"] = True
                log_event(f"Bot joined on retry ✓ (2nd attempt)", guild_id, account["uid"], "SUCCESS")
                added += 1

        time.sleep(random.uniform(2, 6))

    # Store guild data
    guild_id not in active_guilds:
        active_guilds[guild_id]aw_data(guild_id)

    guild_data = active_guilds[guild_id]
    botlist = [b for b in bot_pool.values() if b.get("guild_id") == guild_id and b.get("joined")]
    guild_data["bots"] = botlist

    # Auto form squads
    squads = form_squads(botlist)
    guild_data["squads"] = squads

    log_event(f"Squad breakdown: {[{'size': s['size']} for s in squads]}")
    log_event(f"✅ {added}/{num_bots} bots active in Guild {guild_id}")

    # Start farm
    start_glory_farm(guild_id)

    return added

# ============================================================
# API
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/send_bot", methods=["POST"])
def send_bot_api():
    data = request.get_json()
    guild_id = str(data.get("guild_id", "")).strip()
    count = int(data.get("count", DEFAULT_BOT_COUNT))

    if not guild_id:
        return jsonify({"success": False, "message": "Guild ID required"}), 400

    threading.Thread(target=auto_send_bots_to_guild, args=(guild_id, count), daemon=True).start()

    return jsonify({
        "success": True,
        "message": f"Sending {count} bots to Guild {guild_id}. Check Status window.",
        "guild_id": guild_id,
        "count": count
    })

@app.route("/status")
def status_api():
    # Build detailed per-guild data
    guilds_response = []
    total_active = 0
 in gid, data in active_guilds_data():
        bots = data.get("bots", [])
        squads = data.get("squads", []
        active = [b for b in bots if b.get("joined"]]
        total_active += len(active)
        guilds_response.append({
            "guild_id": gid,
            "active_bots": len(active),
            "total_bots_sent": len(bots),
            "squads": [f"{s['size']} players" for s in squads],
            "squad_count": len(squads),
            "status": "Active" if active else "Inactive"
        })

    return jsonify({
        "total_bots": len(bot_pool),
        "active_bots": total_active,
        "total_contributions": glory_stats["total_contributions"],
        "total_cycles":   "cycles"],
        "guilds": guilds_response,
        "logs": status_log[-120],  # Last 120 log lines
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/guild_bots", methods=["POST"])
def guild_bots_api():
    data = request.get_json()
    guild_id = data.get("guild_id")
    if guild_id and in active_guilds:
        bots = active_guilds[guild_id]["bots"]
        squads = guilds[guild_id].get("[]")
        return jsonify({
            "guild_id": guild_id,
            "bots": [{"uid": b["uid"], "joined": b["joined"]} for b in bots],
            "squads": [{"players": [b["uid"[b in s["team"]]]} for s in squads]
        })
    return jsonify({"error": "Guild not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
