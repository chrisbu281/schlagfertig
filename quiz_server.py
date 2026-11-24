# Silvester-Quiz – lokaler Quiz-Server (nur Python, keine Zusatzpakete)
# Start:  python quiz_server.py
# Moderator (Laptop):   http://localhost:8080/admin
# Beamer:               http://localhost:8080/host
# Gäste (Handy, gleiches WLAN): per QR-Code auf dem Beamer

import json, os, random, socket, sys, threading, time, uuid, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8080
BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE, "einstellungen.json")

with open(os.path.join(BASE, "fragen.json"), encoding="utf-8") as f:
    QUESTIONS = json.load(f)

DEFAULT_SETTINGS = {
    "selected": list(range(len(QUESTIONS))),  # Fragen-Nummern (0-basiert) in Spielreihenfolge
    "timer": "frage",                         # "aus" | "frage" (Zeit aus fragen.json) | Zahl (Sekunden für alle)
    "shuffle": False,                         # Reihenfolge beim Start mischen
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    s["selected"] = [i for i in s["selected"] if isinstance(i, int) and 0 <= i < len(QUESTIONS)]
    return s


def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


lock = threading.Lock()
settings = load_settings()
game = {"phase": "lobby", "pos": -1, "playlist": [], "start": 0.0, "deadline": None}
players = {}  # token -> {"name", "score", "answers": {pos: {"a", "pts"}}, "prev_rank", "joined", "seen"}


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())


JOIN_URL = f"http://{local_ip()}:{PORT}"


# ---------- Spiellogik ----------

def seconds_for(qi):
    t = settings["timer"]
    if t == "aus":
        return None
    if t == "frage":
        return QUESTIONS[qi]["sekunden"]
    return int(t)


def current_qi():
    pos = game["pos"]
    return game["playlist"][pos] if 0 <= pos < len(game["playlist"]) else None


def ranking():
    return sorted(players.items(), key=lambda kv: (-kv[1]["score"], kv[1]["name"].lower()))


def rank_of(token):
    for i, (t, _) in enumerate(ranking()):
        if t == token:
            return i + 1
    return None


def tick():
    """Frage automatisch beenden, wenn Zeit um oder alle geantwortet haben."""
    if game["phase"] == "question":
        pos = game["pos"]
        everyone = players and all(pos in p["answers"] for p in players.values())
        timeout = game["deadline"] is not None and time.time() >= game["deadline"]
        if timeout or everyone:
            game["phase"] = "reveal"


def remaining():
    if game["deadline"] is None:
        return None
    return max(0, round(game["deadline"] - time.time(), 1))


def start_question(pos):
    ranks = {t: i for i, (t, _) in enumerate(ranking())}
    for t, p in players.items():
        p["prev_rank"] = ranks[t]
    game["pos"] = pos
    qi = game["playlist"][pos]
    secs = seconds_for(qi)
    game["start"] = time.time()
    game["deadline"] = game["start"] + secs if secs else None
    game["secs"] = secs
    game["phase"] = "question"


def host_next():
    ph = game["phase"]
    if ph == "lobby":
        if not settings["selected"]:
            return
        game["playlist"] = list(settings["selected"])
        if settings["shuffle"]:
            random.shuffle(game["playlist"])
        start_question(0)
    elif ph == "leaderboard":
        if game["pos"] + 1 >= len(game["playlist"]):
            game["phase"] = "final"
        else:
            start_question(game["pos"] + 1)
    elif ph == "question":
        game["phase"] = "reveal"
    elif ph == "reveal":
        game["phase"] = "final" if game["pos"] >= len(game["playlist"]) - 1 else "leaderboard"


def host_reset():
    game.update({"phase": "lobby", "pos": -1, "playlist": [], "start": 0.0, "deadline": None})
    for p in players.values():
        p["score"] = 0
        p["answers"] = {}
        p["prev_rank"] = None


def question_public():
    qi = current_qi()
    q = QUESTIONS[qi]
    return {"nr": game["pos"] + 1, "total": len(game["playlist"]), "text": q["frage"],
            "answers": q["antworten"], "seconds": game.get("secs")}


def board():
    pos = game["pos"]
    out = []
    for i, (t, p) in enumerate(ranking()):
        last = p["answers"].get(pos)
        out.append({"name": p["name"], "score": p["score"],
                    "gained": last["pts"] if last else 0,
                    "up": (p["prev_rank"] - i) if p.get("prev_rank") is not None else 0})
    return out


def player_state(token):
    p = players.get(token)
    if not p:
        return {"phase": "nojoin"}
    p["seen"] = time.time()
    st = {"phase": game["phase"], "name": p["name"], "score": p["score"],
          "rank": rank_of(token), "players": len(players)}
    if game["phase"] in ("question", "reveal"):
        pos = game["pos"]
        st["q"] = question_public()
        mine = p["answers"].get(pos)
        st["myAnswer"] = mine["a"] if mine else None
        if game["phase"] == "question":
            st["remaining"] = remaining()
        else:
            st["correct"] = QUESTIONS[current_qi()]["richtig"] - 1
            st["gained"] = mine["pts"] if mine else 0
    return st


def host_state():
    """Für den Beamer – ohne richtige Antwort während der Frage."""
    st = {"phase": game["phase"], "url": JOIN_URL,
          "total": len(game["playlist"]) if game["phase"] != "lobby" else len(settings["selected"]),
          "timer": settings["timer"],
          "players": [p["name"] for _, p in sorted(players.items(), key=lambda kv: kv[1]["joined"])]}
    if game["phase"] in ("question", "reveal"):
        pos = game["pos"]
        st["q"] = question_public()
        st["answered"] = sum(1 for p in players.values() if pos in p["answers"])
        if game["phase"] == "question":
            st["remaining"] = remaining()
        else:
            st["correct"] = QUESTIONS[current_qi()]["richtig"] - 1
            counts = [0, 0, 0, 0]
            for p in players.values():
                if pos in p["answers"]:
                    counts[p["answers"][pos]["a"]] += 1
            st["counts"] = counts
    if game["phase"] in ("leaderboard", "final"):
        st["board"] = board()
    return st


def admin_state():
    """Für den Moderator – mit Lösungen und Spielerstatus."""
    st = host_state()
    now = time.time()
    pos = game["pos"]
    st["settings"] = settings
    st["questions"] = [{"text": q["frage"], "answers": q["antworten"], "richtig": q["richtig"],
                        "sekunden": q["sekunden"]} for q in QUESTIONS]
    st["playlist"] = game["playlist"]
    st["pos"] = pos
    if game["phase"] in ("question", "reveal"):
        st["correct"] = QUESTIONS[current_qi()]["richtig"] - 1
    st["playerList"] = [{"name": p["name"], "score": p["score"],
                         "online": now - p.get("seen", 0) < 5,
                         "answered": pos in p["answers"] if pos >= 0 else False}
                        for _, p in ranking()]
    return st


# ---------- HTTP ----------

PAGES = {"/": "spieler.html", "/index.html": "spieler.html"}
LOCAL_PAGES = {"/host": "host.html", "/admin": "admin.html"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, name, ctype="text/html; charset=utf-8"):
        with open(os.path.join(BASE, name), "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in PAGES:
            return self.send_file(PAGES[u.path])
        if u.path == "/qrcode.js":
            return self.send_file("qrcode.js", "application/javascript; charset=utf-8")
        if u.path in LOCAL_PAGES:
            # Wenn als Iframe vom Party Hub geladen: localhost-Check aufheben
            if not self.is_local():
                return self.send_json({"error": "Nur am Laptop"}, 403)
            return self.send_file(LOCAL_PAGES[u.path])
        if u.path == "/api/state":
            token = parse_qs(u.query).get("token", [""])[0]
            with lock:
                tick()
                return self.send_json(player_state(token))
        if u.path in ("/api/host/state", "/api/admin/state"):
            if not self.is_local():
                return self.send_json({"error": "Nur am Laptop"}, 403)
            with lock:
                tick()
                return self.send_json(admin_state() if "admin" in u.path else host_state())
        self.send_json({"error": "Nicht gefunden"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        body = self.read_body()
        if u.path == "/api/join":
            name = " ".join(str(body.get("name", "")).split())[:20]
            if not name:
                return self.send_json({"error": "Bitte gib einen Namen ein."})
            with lock:
                if any(p["name"].lower() == name.lower() for p in players.values()):
                    return self.send_json({"error": f"„{name}" ist schon vergeben – nimm einen anderen Namen."})
                token = uuid.uuid4().hex
                players[token] = {"name": name, "score": 0, "answers": {}, "prev_rank": None,
                                  "joined": time.time(), "seen": time.time()}
                return self.send_json({"token": token})
        if u.path == "/api/answer":
            token = str(body.get("token", ""))
            try:
                a = int(body.get("answer"))
            except Exception:
                return self.send_json({"error": "Ungültig"})
            with lock:
                tick()
                p = players.get(token)
                pos = game["pos"]
                if not p or game["phase"] != "question" or pos in p["answers"] or not 0 <= a <= 3:
                    return self.send_json({"ok": False})
                q = QUESTIONS[current_qi()]
                pts = 0
                if a == q["richtig"] - 1:
                    secs = game.get("secs")
                    if secs:
                        used = min(1.0, (time.time() - game["start"]) / secs)
                        pts = round(1000 * (1 - used / 2))  # 500–1000, schneller = mehr
                    else:
                        pts = 1000  # ohne Timer: jede richtige Antwort gleich viel
                p["answers"][pos] = {"a": a, "pts": pts}
                p["score"] += pts
                tick()
                return self.send_json({"ok": True})
        if u.path.startswith("/api/host/") or u.path.startswith("/api/admin/"):
            if not self.is_local():
                return self.send_json({"error": "Nur am Laptop"}, 403)
            action = u.path.rsplit("/", 1)[-1]
            with lock:
                tick()
                if action == "next":
                    host_next()
                elif action == "reset":
                    host_reset()
                elif action == "kick":
                    name = body.get("name")
                    for t in [t for t, p in players.items() if p["name"] == name]:
                        del players[t]
                elif action == "settings":
                    if game["phase"] != "lobby":
                        return self.send_json({"error": "Einstellungen nur vor dem Start änderbar."})
                    sel = body.get("selected")
                    if isinstance(sel, list):
                        settings["selected"] = [i for i in sel if isinstance(i, int) and 0 <= i < len(QUESTIONS)]
                    tm = body.get("timer")
                    if tm in ("aus", "frage") or (isinstance(tm, int) and 5 <= tm <= 240):
                        settings["timer"] = tm
                    if "shuffle" in body:
                        settings["shuffle"] = bool(body["shuffle"])
                    save_settings()
                return self.send_json(admin_state() if "admin" in u.path else host_state())
        self.send_json({"error": "Nicht gefunden"}, 404)


if __name__ == "__main__":
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    except OSError:
        print("Port %d ist belegt – läuft das Quiz schon in einem anderen Fenster?" % PORT)
        webbrowser.open("http://localhost:%d/admin" % PORT)
        input("Enter drücken zum Schließen ...")
        sys.exit(1)
    print("=" * 60)
    print("  SILVESTER-QUIZ läuft  (" + str(len(QUESTIONS)) + " Fragen im Katalog)")
    print("  Moderator:  http://localhost:%d/admin" % PORT)
    print("  Beamer:     http://localhost:%d/host" % PORT)
    print("  Gäste:      " + JOIN_URL + "   (oder QR-Code auf dem Beamer)")
    print("  Dieses Fenster offen lassen. Beenden: Strg+C oder Fenster schließen.")
    print("=" * 60)
    # Browser nur öffnen wenn NICHT vom Party Hub gestartet
    if not os.environ.get("QUIZ_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/admin" % PORT)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
