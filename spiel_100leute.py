#!/usr/bin/env python3
"""
Schlagfertig – Spielmodus "100 Leute gefragt"
Block 1: Datenfundament – CSV-Parser + tagesbasierte Shuffle-Persistenz.

Fragen-CSV (fragen_100leute.csv / fragen_fastfive.csv):
    Frage,Antwort1,Punkte1,Antwort2,Punkte2, ... (bis 6 Antworten)

Shuffle-Logik:
    - Erstes Spiel des Tages -> alle Fragen zufaellig mischen
    - Gespielte Fragen werden markiert (markiere_gespielt)
    - Weiteres Spiel am selben Tag -> macht mit den restlichen Fragen weiter
    - Naechster Tag -> automatisch neu mischen
    - Zustand wird in ~/.schlagfertig_shuffle.json gespeichert
"""
import os, csv, json, random, hashlib, subprocess, base64, threading, time as _time
from datetime import date

BASIS         = os.path.dirname(os.path.abspath(__file__))
CSV_HAUPT     = os.path.join(BASIS, "fragen_100leute.csv")
CSV_FASTFIVE  = os.path.join(BASIS, "fragen_fastfive.csv")
SHUFFLE_DATEI = os.path.expanduser("~/.schlagfertig_shuffle.json")

MAX_ANTWORTEN = 6
FF_ANZAHL_FRAGEN = 5


def _frage_id(frage_text):
    """Stabile ID aus dem Fragetext – ueberlebt das Umsortieren der CSV."""
    norm = " ".join(frage_text.strip().lower().split())
    return hashlib.md5(norm.encode("utf-8")).hexdigest()[:10]


def lade_fragen(pfad):
    """Liest eine 100-Leute-CSV und liefert eine Liste:
        [{id, frage, antworten:[{text, punkte}, ...]}, ...]
    Antworten sind absteigend nach Punkten sortiert (Tafel-Reihenfolge)."""
    if not os.path.exists(pfad):
        return []
    with open(pfad, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    # optionale Kopfzeile ueberspringen
    start = 0
    if rows and rows[0] and rows[0][0].strip().lower() in ("frage", "question"):
        start = 1

    fragen, gesehen = [], set()
    for row in rows[start:]:
        if not row or not row[0].strip():
            continue
        frage = row[0].strip()
        antworten = []
        i = 1
        while i < len(row) and len(antworten) < MAX_ANTWORTEN:
            text = row[i].strip()
            punkte_raw = row[i + 1].strip() if i + 1 < len(row) else ""
            if text:
                try:
                    punkte = int(punkte_raw)
                except ValueError:
                    punkte = 0
                antworten.append({"text": text, "punkte": punkte})
            i += 2
        if not antworten:
            continue
        antworten.sort(key=lambda a: a["punkte"], reverse=True)
        fid = _frage_id(frage)
        if fid in gesehen:
            continue
        gesehen.add(fid)
        fragen.append({"id": fid, "frage": frage, "antworten": antworten})
    return fragen


# ── Shuffle-Persistenz ──────────────────────────────────────────────
def _lade_shuffle():
    try:
        with open(SHUFFLE_DATEI, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _speichere_shuffle(state):
    try:
        with open(SHUFFLE_DATEI, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"Shuffle-Speicherfehler: {e}")


def _pool_state(state, pool, alle_ids):
    heute = date.today().isoformat()
    p = state.get(pool)
    if not p or p.get("datum") != heute:
        reihenfolge = alle_ids[:]
        random.shuffle(reihenfolge)
        p = {"datum": heute, "reihenfolge": reihenfolge, "gespielt": []}
    else:
        fehlende = [i for i in alle_ids if i not in p["reihenfolge"]]
        if fehlende:
            random.shuffle(fehlende)
            p["reihenfolge"].extend(fehlende)
        p["reihenfolge"] = [i for i in p["reihenfolge"] if i in alle_ids]
        p["gespielt"]    = [i for i in p["gespielt"] if i in alle_ids]
    state[pool] = p
    return p


def hole_naechste(anzahl, pool="haupt"):
    pfad = CSV_HAUPT if pool == "haupt" else CSV_FASTFIVE
    fragen = lade_fragen(pfad)
    if not fragen:
        return []
    by_id = {f["id"]: f for f in fragen}
    state = _lade_shuffle()
    p = _pool_state(state, pool, list(by_id.keys()))
    offen = [i for i in p["reihenfolge"] if i not in p["gespielt"]]
    if len(offen) < anzahl:
        random.shuffle(p["reihenfolge"])
        p["gespielt"] = []
        offen = p["reihenfolge"][:]
    gewaehlt = offen[:anzahl]
    _speichere_shuffle(state)
    return [by_id[i] for i in gewaehlt]


def markiere_gespielt(ids, pool="haupt"):
    state = _lade_shuffle()
    p = state.get(pool)
    if not p:
        return
    for i in ids:
        if i not in p["gespielt"]:
            p["gespielt"].append(i)
    _speichere_shuffle(state)


def anzahl_verfuegbar(pool="haupt"):
    pfad = CSV_HAUPT if pool == "haupt" else CSV_FASTFIVE
    fragen = lade_fragen(pfad)
    if not fragen:
        return 0
    ids = [f["id"] for f in fragen]
    state = _lade_shuffle()
    p = state.get(pool)
    if not p or p.get("datum") != date.today().isoformat():
        return len(ids)
    return len([i for i in ids if i not in p.get("gespielt", [])])


# ════════════════════════════════════════════════════════════════════
#  SPIELZUSTAND
# ════════════════════════════════════════════════════════════════════
NAMESPACE = "/100leute"

def _neue_duell():
    return {"erster_team": None, "antwort_a": None, "antwort_b": None,
            "gewinner": None, "buzzer_offen": False}

def _neuer_ff():
    return {"fragen": [], "aktuell": 0, "dran": "A", "timer_laueft": False,
            "timer_rest": 0, "punkte_a": 0, "punkte_b": 0,
            "fertig_a": False, "fertig_b": False}

def _neuer_state():
    return {
        "phase": "setup",
        "config": {"runden": 3, "ff_timer": True, "ff_zeit1": 20, "ff_zeit2": 25,
                   "ff_ziel": 400, "buzzer_a": 1, "buzzer_b": 2},
        "teams": {
            "A": {"name": "Team A", "foto": "", "punkte": 0},
            "B": {"name": "Team B", "foto": "", "punkte": 0},
        },
        "runde": 0, "aktive_frage": None, "duell": _neue_duell(),
        "strikes": 0, "aktives_team": None, "rundentopf": 0,
        "rundenende": None, "musik": False, "beamer_aktiv": False, "ff": None,
        "fragen_queue": [],
    }

state = _neuer_state()
_socketio  = None
_steuerung = {"stop_pygame": None, "start_pygame": None}
_chromium  = None

# ── Fast-Five-Timer ─────────────────────────────────────────────────
_ff_stop_ev = threading.Event()

def _ff_timer_stoppen():
    _ff_stop_ev.set()

def _ff_timer_loop():
    while not _ff_stop_ev.wait(1.0):
        ff = state.get("ff")
        if not ff or not ff.get("timer_laueft") or state.get("phase") != "fastfive":
            break
        rest = ff.get("timer_rest", 0) - 1
        ff["timer_rest"] = max(0, rest)
        ff["timer_laueft"] = rest > 0
        _broadcast()
        if rest <= 0:
            break

def _ff_timer_starten():
    global _ff_stop_ev
    ff = state.get("ff")
    if not ff or ff.get("timer_laueft") or ff.get("timer_rest", 0) <= 0:
        return
    _ff_stop_ev = threading.Event()
    ff["timer_laueft"] = True
    threading.Thread(target=_ff_timer_loop, daemon=True).start()
    _broadcast()

def _ff_beenden_intern():
    ff = state.get("ff") or {}
    _ff_timer_stoppen()
    if state.get("ff"):
        state["ff"]["timer_laueft"] = False
    state["teams"]["A"]["punkte"] += ff.get("punkte_a", 0)
    state["teams"]["B"]["punkte"] += ff.get("punkte_b", 0)
    state["phase"] = "ende"
    _broadcast()

def _broadcast():
    if _socketio:
        _socketio.emit("state", state, namespace=NAMESPACE)

def _apply_setup(data):
    cfg = data.get("config", {})
    for k in list(state["config"].keys()):
        if k in cfg:
            state["config"][k] = cfg[k]
    teams = data.get("teams", {})
    for t in ("A", "B"):
        if t in teams and "name" in teams[t]:
            state["teams"][t]["name"] = teams[t]["name"]
    fragen_ids = data.get("fragen_ids")
    if fragen_ids:
        fragen = lade_fragen(CSV_HAUPT)
        by_id  = {f["id"]: f for f in fragen}
        state["fragen_queue"] = [
            {"id": f["id"], "frage": f["frage"],
             "antworten": [{"text": a["text"], "punkte": a["punkte"], "auf": False}
                           for a in f["antworten"]]}
            for fid in fragen_ids if (f := by_id.get(fid))
        ]
        if "runden" not in cfg:
            state["config"]["runden"] = max(1, len(state["fragen_queue"]))
    else:
        state["fragen_queue"] = []

# ── Buzzer-Duell-Logik ──────────────────────────────────────────────
def _on_buzz(team):
    if state.get("phase") != "buzzerduell":
        return
    d = state.get("duell") or {}
    if not d.get("buzzer_offen") or d.get("erster_team"):
        return
    d["erster_team"] = team
    _broadcast()

def _aktualisiere_rundentopf():
    af = state.get("aktive_frage")
    state["rundentopf"] = sum(a["punkte"] for a in af["antworten"] if a.get("auf")) if af else 0

def _runde_beenden(gewinner):
    topf = state.get("rundentopf", 0)
    if gewinner in ("A", "B"):
        state["teams"][gewinner]["punkte"] += topf
    state["rundenende"] = {"gewinner": gewinner, "topf": topf}
    state["phase"] = "rundenende"

def _naechste_runde():
    state["rundentopf"]   = 0
    state["strikes"]      = 0
    state["aktive_frage"] = None
    state["aktives_team"] = None
    state["duell"]        = _neue_duell()
    state["rundenende"]   = None
    if state["runde"] >= state["config"]["runden"]:
        state["phase"] = "fastfive"
    else:
        state["runde"] += 1
        state["phase"] = "buzzerduell"

def _duell_gewinner(d):
    af = state.get("aktive_frage") or {"antworten": []}
    def punkte(idx):
        if isinstance(idx, int) and 0 <= idx < len(af["antworten"]):
            return af["antworten"][idx]["punkte"]
        return -1
    pa, pb = punkte(d["antwort_a"]), punkte(d["antwort_b"])
    if pa == pb:
        return d.get("erster_team") or "A"
    return "A" if pa > pb else "B"

# ── GPIO-Buzzer-Reader (lgpio für Pi 5) ─────────────────────────────
_buzzer_reader_aktiv = False
_buzzer_thread = None

def _starte_buzzer_reader():
    global _buzzer_reader_aktiv, _buzzer_thread
    if _buzzer_reader_aktiv:
        return
    _buzzer_reader_aktiv = True
    _buzzer_thread = threading.Thread(target=_buzzer_reader_loop, daemon=True)
    _buzzer_thread.start()

def _stoppe_buzzer_reader():
    global _buzzer_reader_aktiv
    _buzzer_reader_aktiv = False

def _buzzer_reader_loop():
    try:
        import lgpio
    except Exception as e:
        print(f"100leute: lgpio nicht verfuegbar ({e}) – sim_buzzer nutzbar.")
        return
    try:
        with open(os.path.join(BASIS, "quiz_config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        spieler = {s["nr"]: s["gpio"] for s in cfg.get("spieler", [])}
    except Exception as e:
        print(f"100leute: quiz_config laden fehlgeschlagen: {e}")
        return

    pin_team = {}
    if state["config"]["buzzer_a"] in spieler:
        pin_team[spieler[state["config"]["buzzer_a"]]] = "A"
    if state["config"]["buzzer_b"] in spieler:
        pin_team[spieler[state["config"]["buzzer_b"]]] = "B"
    if not pin_team:
        print("100leute: keine Buzzer-Pins gemappt.")
        return

    h = lgpio.gpiochip_open(0)
    for pin in pin_team:
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
    letzter = {pin: 1 for pin in pin_team}
    print(f"100leute: Buzzer-Reader aktiv (Pins {list(pin_team)})")

    while _buzzer_reader_aktiv:
        for pin, team in pin_team.items():
            jetzt = lgpio.gpio_read(h, pin)
            if jetzt == 0 and letzter[pin] == 1:
                _on_buzz(team)
            letzter[pin] = jetzt
        _time.sleep(0.005)

    lgpio.gpiochip_close(h)
    print("100leute: Buzzer-Reader gestoppt")


def _kill_display_chromium():
    """Beendet den /display-Chromium damit das Spiel den vollen Bildschirm bekommt."""
    subprocess.run(["pkill", "-f", "chromium-sg-display"], capture_output=True)
    _time.sleep(2.0)  # Chromium braucht Zeit für graceful shutdown
    subprocess.run(["pkill", "-9", "-f", "chromium-sg-display"], capture_output=True)
    _time.sleep(0.5)


def _setze_einzelbildschirm(env):
    """Nur den TV-HDMI aktivieren, alle anderen Outputs (DSI, zweiter HDMI) deaktivieren.
    Mit DSI aktiv im X11-Virtual-Desktop zeigt Chromium kiosk nur den halben Bildschirm."""
    xr = subprocess.run(["xrandr"], env=env, capture_output=True, text=True)
    hdmi_primary = None
    cmd = ["xrandr"]
    for line in xr.stdout.splitlines():
        if not line or line[0].isspace():
            continue
        parts = line.split()
        if not parts or parts[0] == 'Screen':
            continue
        name = parts[0]
        if 'HDMI' in name:
            if ' connected' in line and ' disconnected' not in line:
                if not hdmi_primary:
                    hdmi_primary = name
                    cmd += ["--output", name, "--primary", "--mode", "1920x1080", "--pos", "0x0"]
                else:
                    cmd += ["--output", name, "--off"]
            else:
                cmd += ["--output", name, "--off"]
        else:
            cmd += ["--output", name, "--off"]
    if hdmi_primary:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"100leute: xrandr FEHLER ({r.returncode}): {r.stderr.strip()}")
        else:
            print(f"100leute: xrandr → 1920x1080 auf {hdmi_primary}")
        _time.sleep(0.5)
    else:
        print("100leute: xrandr – kein HDMI gefunden, nutze --auto")
        subprocess.run(["xrandr", "--auto"], env=env, capture_output=True)


def _starte_display_chromium():
    """Startet den /display-Chromium neu nach Ende des Spiels."""
    start_script = os.path.join(BASIS, "pi-config", "start-display.sh")
    if os.path.exists(start_script):
        env = {**os.environ, "DISPLAY": ":0"}
        subprocess.Popen(
            ["bash", start_script], env=env,
            start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )


def starte_beamer():
    global _chromium
    if _steuerung["stop_pygame"]:
        try:
            _steuerung["stop_pygame"]()
        except Exception as e:
            print(f"100leute: stop_pygame Fehler: {e}")
    _time.sleep(0.3)
    _kill_display_chromium()
    _starte_buzzer_reader()

    url  = "http://localhost:5000/spiel/100leute"
    env  = {**os.environ, "DISPLAY": ":0"}
    _setze_einzelbildschirm(env)
    import shutil
    shutil.rmtree("/tmp/chromium-sg-100leute", ignore_errors=True)
    flags = ["--user-data-dir=/tmp/chromium-sg-100leute",
             "--kiosk", "--no-sandbox", "--noerrdialogs", "--disable-infobars",
             "--disable-session-crashed-bubble", "--password-store=basic",
             "--autoplay-policy=no-user-gesture-required",
             "--disable-translate", "--disable-features=TranslateUI",
             "--disable-extensions", "--disable-component-update",
             url]
    _chromium = None
    for binary in ("chromium-browser", "chromium"):
        try:
            _chromium = subprocess.Popen([binary] + flags, env=env,
                                          preexec_fn=os.setsid)
            print(f"100leute: Beamer gestartet ({binary})")
            break
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"100leute: Chromium-Start Fehler: {e}")
            break
    state["beamer_aktiv"] = True
    _broadcast()


def stoppe_beamer():
    global _chromium
    _ff_timer_stoppen()
    _stoppe_buzzer_reader()
    _time.sleep(0.1)
    if _chromium:
        try:
            _chromium.terminate()
        except Exception:
            pass
        _chromium = None
    state["beamer_aktiv"] = False
    _broadcast()
    if _steuerung["start_pygame"]:
        try:
            _steuerung["start_pygame"]()
        except Exception as e:
            print(f"100leute: start_pygame Fehler: {e}")


def init_app(app, socketio, stop_pygame=None, start_pygame=None):
    global _socketio
    _socketio = socketio
    _steuerung["stop_pygame"]  = stop_pygame
    _steuerung["start_pygame"] = start_pygame

    from flask import send_from_directory, jsonify
    from flask_socketio import emit

    @app.route("/spiel/100leute")
    def beamer_100leute():
        return send_from_directory(BASIS, "beamer_100leute.html")

    @app.route("/moderator/100leute")
    def moderator_100leute():
        return send_from_directory(BASIS, "moderator_100leute.html")

    @app.route("/api/100leute/info")
    def info_100leute():
        return jsonify({"haupt_verfuegbar": anzahl_verfuegbar("haupt"),
                        "fastfive_verfuegbar": anzahl_verfuegbar("fastfive")})

    @app.route("/100leute/teamfoto/<team>")
    def teamfoto_100leute(team):
        team = team.upper()
        fn = f"team_{team}.jpg"
        if team not in ("A", "B") or not os.path.exists(os.path.join(BASIS, fn)):
            return ("", 404)
        return send_from_directory(BASIS, fn)

    @socketio.on("connect", namespace=NAMESPACE)
    def _on_connect():
        emit("state", state)

    @socketio.on("setup", namespace=NAMESPACE)
    def _on_setup(data):
        _apply_setup(data)
        _broadcast()

    @socketio.on("team_foto", namespace=NAMESPACE)
    def _on_team_foto(data):
        team  = (data.get("team") or "").upper()
        daten = data.get("data", "")
        if team not in ("A", "B") or not daten.startswith("data:image"):
            return
        try:
            b64 = daten.split(",", 1)[1]
            with open(os.path.join(BASIS, f"team_{team}.jpg"), "wb") as f:
                f.write(base64.b64decode(b64))
            state["teams"][team]["foto"] = f"/100leute/teamfoto/{team}?v={int(_time.time())}"
            _broadcast()
        except Exception as e:
            print(f"100leute: Team-Foto Fehler: {e}")

    @socketio.on("beamer_starten", namespace=NAMESPACE)
    def _on_beamer_starten(data=None):
        starte_beamer()

    @socketio.on("spiel_starten", namespace=NAMESPACE)
    def _on_spiel_starten(data=None):
        if data:
            _apply_setup(data)
        state["teams"]["A"]["punkte"] = 0
        state["teams"]["B"]["punkte"] = 0
        state["runde"]        = 1
        state["strikes"]      = 0
        state["rundentopf"]   = 0
        state["aktive_frage"] = None
        state["aktives_team"] = None
        state["duell"]        = _neue_duell()
        state["ff"]           = None
        state["phase"]        = "buzzerduell"
        if not state.get("beamer_aktiv"):
            starte_beamer()
        else:
            _broadcast()

    @socketio.on("frage_freigeben", namespace=NAMESPACE)
    def _on_frage_freigeben(data=None):
        if state.get("fragen_queue"):
            state["aktive_frage"] = state["fragen_queue"].pop(0)
        else:
            fragen = hole_naechste(1, "haupt")
            if not fragen:
                return
            f = fragen[0]
            state["aktive_frage"] = {
                "id": f["id"], "frage": f["frage"],
                "antworten": [{"text": a["text"], "punkte": a["punkte"], "auf": False}
                              for a in f["antworten"]],
            }
        state["duell"] = _neue_duell()
        state["duell"]["buzzer_offen"] = True
        _aktualisiere_rundentopf()
        _broadcast()

    @socketio.on("sim_buzzer", namespace=NAMESPACE)
    def _on_sim_buzzer(data):
        team = (data.get("team") or "").upper()
        if team in ("A", "B"):
            _on_buzz(team)

    @socketio.on("duell_antwort", namespace=NAMESPACE)
    def _on_duell_antwort(data):
        team = (data.get("team") or "").upper()
        idx  = data.get("idx")
        if team not in ("A", "B") or state.get("aktive_frage") is None:
            return
        d = state["duell"]
        meins   = "antwort_a" if team == "A" else "antwort_b"
        anderes = "antwort_b" if team == "A" else "antwort_a"
        if d[meins] is not None:
            return
        if isinstance(idx, int) and idx >= 0 and d[anderes] == idx:
            return
        d[meins] = idx
        if isinstance(idx, int) and 0 <= idx < len(state["aktive_frage"]["antworten"]):
            state["aktive_frage"]["antworten"][idx]["auf"] = True
        _aktualisiere_rundentopf()
        if d["antwort_a"] is not None and d["antwort_b"] is not None:
            d["gewinner"] = _duell_gewinner(d)
            d["buzzer_offen"] = False
        _broadcast()

    @socketio.on("duell_reset_antworten", namespace=NAMESPACE)
    def _on_duell_reset_antworten(data=None):
        d  = state.get("duell")
        af = state.get("aktive_frage")
        if not d or not af:
            return
        for idx in (d.get("antwort_a"), d.get("antwort_b")):
            if isinstance(idx, int) and 0 <= idx < len(af["antworten"]):
                af["antworten"][idx]["auf"] = False
        d["antwort_a"] = None
        d["antwort_b"] = None
        d["gewinner"]  = None
        _aktualisiere_rundentopf()
        _broadcast()

    @socketio.on("hauptrunde_starten", namespace=NAMESPACE)
    def _on_hauptrunde_starten(data=None):
        d = state.get("duell") or {}
        state["aktives_team"] = d.get("gewinner") or "A"
        state["strikes"]      = 0
        if state.get("aktive_frage"):
            markiere_gespielt([state["aktive_frage"]["id"]], "haupt")
        _aktualisiere_rundentopf()
        state["phase"] = "hauptrunde"
        _broadcast()

    @socketio.on("hauptrunde_aufdecken", namespace=NAMESPACE)
    def _on_hauptrunde_aufdecken(data):
        af = state.get("aktive_frage")
        if state.get("phase") != "hauptrunde" or not af:
            return
        idx = data.get("idx")
        if not (isinstance(idx, int) and 0 <= idx < len(af["antworten"])):
            return
        if af["antworten"][idx]["auf"]:
            return
        af["antworten"][idx]["auf"] = True
        _aktualisiere_rundentopf()
        if all(a["auf"] for a in af["antworten"]):
            _runde_beenden(state.get("aktives_team") or "A")
        _broadcast()

    @socketio.on("hauptrunde_strike", namespace=NAMESPACE)
    def _on_hauptrunde_strike(data=None):
        if state.get("phase") != "hauptrunde":
            return
        state["strikes"] = min(3, state.get("strikes", 0) + 1)
        if state["strikes"] >= 3:
            state["phase"] = "stehlen"
        _broadcast()

    @socketio.on("stehlen_aufdecken", namespace=NAMESPACE)
    def _on_stehlen_aufdecken(data):
        af = state.get("aktive_frage")
        if state.get("phase") != "stehlen" or not af:
            return
        idx = data.get("idx")
        if isinstance(idx, int) and 0 <= idx < len(af["antworten"]) and not af["antworten"][idx]["auf"]:
            af["antworten"][idx]["auf"] = True
            _aktualisiere_rundentopf()
        gegner = "B" if state.get("aktives_team") == "A" else "A"
        _runde_beenden(gegner)
        _broadcast()

    @socketio.on("stehlen_falsch", namespace=NAMESPACE)
    def _on_stehlen_falsch(data=None):
        if state.get("phase") != "stehlen":
            return
        _runde_beenden(state.get("aktives_team") or "A")
        _broadcast()

    @socketio.on("naechste_runde", namespace=NAMESPACE)
    def _on_naechste_runde(data=None):
        if state.get("phase") != "rundenende":
            return
        _naechste_runde()
        _broadcast()

    @socketio.on("musik_toggle", namespace=NAMESPACE)
    def _on_musik_toggle(data=None):
        state["musik"] = not state.get("musik", False)
        _broadcast()

    @socketio.on("spiel_beenden", namespace=NAMESPACE)
    def _on_spiel_beenden(data=None):
        state["phase"] = "setup"
        stoppe_beamer()

    @socketio.on("reset", namespace=NAMESPACE)
    def _on_reset(data=None):
        global state
        _ff_timer_stoppen()
        beamer_war_aktiv = state.get("beamer_aktiv", False)
        state = _neuer_state()
        state["beamer_aktiv"] = beamer_war_aktiv
        _broadcast()

    @socketio.on("ff_starten", namespace=NAMESPACE)
    def _on_ff_starten(data=None):
        if state.get("phase") != "fastfive":
            return
        fragen = hole_naechste(FF_ANZAHL_FRAGEN, "fastfive")
        if fragen:
            markiere_gespielt([f["id"] for f in fragen], "fastfive")
        ff = _neuer_ff()
        ff["fragen"] = [
            {"id": f["id"], "frage": f["frage"],
             "antworten": [{"text": a["text"], "punkte": a["punkte"],
                            "auf": False, "von": None} for a in f["antworten"]]}
            for f in fragen
        ]
        ff["timer_rest"] = state["config"]["ff_zeit1"]
        state["ff"] = ff
        _broadcast()

    @socketio.on("ff_aufdecken", namespace=NAMESPACE)
    def _on_ff_aufdecken(data):
        ff = state.get("ff")
        if not ff or state.get("phase") != "fastfive":
            return
        ak = ff["aktuell"]
        fragen = ff["fragen"]
        if not (0 <= ak < len(fragen)):
            return
        antworten = fragen[ak]["antworten"]
        idx = data.get("idx")
        if not (isinstance(idx, int) and 0 <= idx < len(antworten)):
            return
        a = antworten[idx]
        if a["auf"]:
            return
        a["auf"] = True
        a["von"] = ff["dran"]
        if ff["dran"] == "A":
            ff["punkte_a"] += a["punkte"]
        else:
            ff["punkte_b"] += a["punkte"]
        _broadcast()

    @socketio.on("ff_naechste_frage", namespace=NAMESPACE)
    def _on_ff_naechste_frage(data=None):
        ff = state.get("ff")
        if not ff or state.get("phase") != "fastfive":
            return
        _ff_timer_stoppen()
        ff["timer_laueft"] = False
        ak = ff["aktuell"]
        naechste = ak + 1
        if naechste >= len(ff["fragen"]):
            if ff["dran"] == "A":
                ff["fertig_a"] = True
                ff["dran"]     = "B"
                ff["aktuell"]  = 0
                ff["timer_rest"] = state["config"]["ff_zeit2"]
                _broadcast()
            else:
                ff["fertig_b"] = True
                _ff_beenden_intern()
        else:
            ff["aktuell"] = naechste
            _broadcast()

    @socketio.on("ff_timer_start", namespace=NAMESPACE)
    def _on_ff_timer_start(data=None):
        if state.get("phase") == "fastfive":
            _ff_timer_starten()

    @socketio.on("ff_timer_stop", namespace=NAMESPACE)
    def _on_ff_timer_stop(data=None):
        ff = state.get("ff")
        if ff:
            _ff_timer_stoppen()
            ff["timer_laueft"] = False
            _broadcast()

    @socketio.on("ff_beenden", namespace=NAMESPACE)
    def _on_ff_beenden(data=None):
        if state.get("phase") == "fastfive":
            _ff_beenden_intern()

    print("100leute: Routen + SocketIO registriert")
