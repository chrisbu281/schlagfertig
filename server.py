#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory, redirect, Response
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import json, os, csv, io, subprocess, urllib.request, urllib.parse, sys, threading
try:
    import requests as _requests
except ImportError:
    _requests = None
import spiel_100leute

app = Flask(__name__)
app.config['SECRET_KEY'] = 'schlagfertig2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BASIS        = os.path.dirname(os.path.abspath(__file__))
KONFIG       = os.path.join(BASIS, "quiz_config.json")
STATE_DATEI  = os.path.join(BASIS, ".spiel_state")
CLOUD_KONFIG = os.path.join(BASIS, ".cloud_config.json")
GAST_FRAGEN  = os.path.join(BASIS, "fragen_default.json")
SETUP_DATEI  = os.path.join(BASIS, ".setup_fertig")
SOUNDS_DIR   = os.path.join(BASIS, "sounds")
GIFS_DIR     = os.path.join(BASIS, "gifs")
MEME_KONFIG  = os.path.join(BASIS, "meme_board.json")
os.makedirs(SOUNDS_DIR, exist_ok=True)
os.makedirs(GIFS_DIR, exist_ok=True)

# Supabase
SUPABASE_BASE     = "https://drjdushdhzgkfkigocxd.supabase.co"
SUPABASE_SYNC     = f"{SUPABASE_BASE}/storage/v1/object/public/sync/fragen.json"

# Key aus Umgebungsvariable oder .env-Datei im Projektordner lesen
def _lade_anon_key():
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not key:
        env_pfad = os.path.join(BASIS, ".env")
        try:
            with open(env_pfad, encoding="utf-8") as f:
                for zeile in f:
                    zeile = zeile.strip()
                    if zeile.startswith("SUPABASE_ANON_KEY="):
                        key = zeile.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    return key

SUPABASE_ANON_KEY = _lade_anon_key()

# ── SUPABASE HELPERS ──
def _sb_headers(token=None):
    h = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def _sb_auth(email, passwort):
    url  = f"{SUPABASE_BASE}/auth/v1/token?grant_type=password"
    body = json.dumps({"email": email, "password": passwort}).encode()
    req  = urllib.request.Request(url, data=body, headers=_sb_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def _sb_refresh(refresh_token):
    url  = f"{SUPABASE_BASE}/auth/v1/token?grant_type=refresh_token"
    body = json.dumps({"refresh_token": refresh_token}).encode()
    req  = urllib.request.Request(url, data=body, headers=_sb_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def _sb_fragen(access_token):
    url = f"{SUPABASE_BASE}/rest/v1/fragen?select=*&order=erstellt_am.asc"
    req = urllib.request.Request(url, headers=_sb_headers(access_token))
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def _konvertiere_frage(f):
    # MC-Antworten aus Einzelspalten (antwort_a/b/c/d) in Liste umwandeln
    mc_liste = [f.get("antwort_a"), f.get("antwort_b"), f.get("antwort_c"), f.get("antwort_d")]
    mc_liste = [a for a in mc_liste if a]  # leere rausfiltern
    richtig_buchstabe = (f.get("richtige_antwort") or "").upper()
    richtig_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(richtig_buchstabe)

    # modus aus modi-Array ableiten; Supabase nutzt "multiple_choice", Pi intern "mc"
    # Fallback: wenn antwort_a vorhanden → ist MC, egal was modi sagt
    modi = f.get("modi") or []
    ist_mc = "mc" in modi or "multiple_choice" in modi or len(mc_liste) >= 2
    modus = "mc" if ist_mc else "frei"

    return {
        "_gewaehlt": False,
        "id": f.get("id"),
        "frage": f.get("frage", ""),
        "antwort": f.get("antwort", ""),
        "kategorie": f.get("kategorie"),
        "schwierigkeit": f.get("schwierigkeit"),
        "modus": modus,
        "antworten_mc": mc_liste if mc_liste else None,
        "richtige_antwort_index": richtig_idx,
        "bild_url": f.get("bild_url"),
        "audio_url": f.get("audio_url"),
        "video_url": f.get("video_url"),
    }

def _speichere_fragen_lokal(roh):
    fragen = [_konvertiere_frage(f) for f in roh]
    config = lese_oder_erstelle_config()
    config["fragen"] = fragen
    with open(KONFIG, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    return fragen
spiel_prozess = None

# ── MEME-BOARD ──
STANDARD_MEME_BOARD = {"kacheln": [
    {"id":"applaus",       "name":"Applaus",         "icon":"👏","kategorie":"reaktion","typ":"sound","sound":None},
    {"id":"trommelwirbel", "name":"Trommelwirbel",   "icon":"🥁","kategorie":"spannung","typ":"sound","sound":None},
    {"id":"lacher",        "name":"Lacher",          "icon":"😂","kategorie":"reaktion","typ":"sound","sound":None},
    {"id":"fail",          "name":"Fail-Sound",      "icon":"💥","kategorie":"ergebnis","typ":"sound","sound":None},
    {"id":"falsch",        "name":"Falsche Antwort", "icon":"❌","kategorie":"ergebnis","typ":"sound","sound":None},
    {"id":"signal",        "name":"Signalton",       "icon":"🔔","kategorie":"spannung","typ":"sound","sound":None},
    {"id":"ticktack",      "name":"Tick-Tack",       "icon":"⏳","kategorie":"spannung","typ":"sound","sound":None},
    {"id":"fanfare",       "name":"Fanfare",         "icon":"🎺","kategorie":"ergebnis","typ":"gif","sound":None,"gif":None},
    {"id":"konfetti",      "name":"Konfetti-Sieg",   "icon":"🎉","kategorie":"ergebnis","typ":"gif","sound":None,"gif":None},
]}

def lade_meme_board():
    if not os.path.exists(MEME_KONFIG):
        with open(MEME_KONFIG, "w", encoding="utf-8") as f:
            json.dump(STANDARD_MEME_BOARD, f, ensure_ascii=False, indent=2)
        return STANDARD_MEME_BOARD
    with open(MEME_KONFIG, "r", encoding="utf-8") as f:
        return json.load(f)

ADMIN_ROLLEN_DATEI = os.path.join(BASIS, "admin_rollen.json")

def _lade_umgebungs_key(name):
    """Liest einen Schlüssel aus Umgebungsvariable oder .env-Datei im Projektordner."""
    key = os.environ.get(name, "")
    if not key:
        env_pfad = os.path.join(BASIS, ".env")
        try:
            with open(env_pfad, encoding="utf-8") as f:
                for zeile in f:
                    zeile = zeile.strip()
                    if zeile.startswith(f"{name}="):
                        key = zeile.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    return key

def giphy_api_key():
    key = _lade_umgebungs_key("GIPHY_API_KEY")
    if not key and os.path.exists(KONFIG):
        with open(KONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        key = (cfg.get("einstellungen") or {}).get("giphy_api_key", "")
    return key

def freesound_api_key():
    return _lade_umgebungs_key("FREESOUND_API_KEY")

def lese_admin_emails():
    admins = set()
    env_admins = _lade_umgebungs_key("ADMIN_EMAILS")
    if env_admins:
        admins.update(e.strip().lower() for e in env_admins.split(",") if e.strip())
    if os.path.exists(ADMIN_ROLLEN_DATEI):
        try:
            with open(ADMIN_ROLLEN_DATEI, "r", encoding="utf-8") as f:
                d = json.load(f)
            admins.update(e.lower() for e in d.get("admins", []))
        except Exception:
            pass
    return admins

def ist_admin(email):
    return bool(email) and email.lower() in lese_admin_emails()

def schreibe_admin_emails(emails):
    with open(ADMIN_ROLLEN_DATEI, "w", encoding="utf-8") as f:
        json.dump({"admins": sorted(e.lower() for e in emails)}, f, ensure_ascii=False, indent=2)

def check_admin():
    cfg = lese_cloud_config()
    if not ist_admin(cfg.get("email", "")):
        return jsonify({"error": "Zugriff verweigert – keine Adminrechte"}), 403
    return None

_popup_timer = None   # server-side 3s timer for buzzer popup
_popup_aktiv = False  # True while popup should be visible; False after timer fired

spiel_state = {
    "modus": "warten",
    "aktuelle_frage": None,
    "frage_idx": 0,
    "warteschlange": [],
    "punkte": {},
    "spielmodus": "frei",
    "mc_gewaehlt": None,
    "punktestand_sichtbar": False
}

# Letzter Buzzer-Druck pro Spieler-Nr  { nr: unix_timestamp }
buzzer_zuletzt = {}

# ── CLOUD-CONFIG HELPERS ──
def lese_cloud_config():
    try:
        with open(CLOUD_KONFIG, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def schreibe_cloud_config(cfg):
    with open(CLOUD_KONFIG, "w") as f:
        json.dump(cfg, f, indent=2)

def lese_oder_erstelle_config():
    """Liest quiz_config.json, erstellt sie mit Standardwerten falls nicht vorhanden."""
    if os.path.exists(KONFIG):
        with open(KONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"einstellungen": {}, "spieler": [], "fragen": []}

def cloud_request(methode, url, token=None, daten=None, timeout=15):
    """Hilfsfunktion für HTTP-Requests zum Cloud-Server."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(daten).encode() if daten else None
    req = urllib.request.Request(url, data=body, headers=headers, method=methode)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def schreibe_state(modus):
    with open(STATE_DATEI, "w") as f: f.write(modus)

def lese_state():
    try:
        with open(STATE_DATEI, "r") as f: return f.read().strip()
    except: return "warten"

def spiel_laeuft():
    return spiel_prozess is not None and spiel_prozess.poll() is None

def starte_quiz():
    global spiel_prozess
    env = {**os.environ, "DISPLAY": ":0"}
    spiel_prozess = subprocess.Popen(
        [sys.executable, os.path.join(BASIS, "quiz_buzzer.py")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    schreibe_state("warten")

def stoppe_pygame():
    """Beendet quiz_buzzer.py (für 100-Leute-Modus, der Chromium statt pygame nutzt)."""
    global spiel_prozess
    schreibe_state("stoppen")
    if spiel_laeuft():
        spiel_prozess.terminate()
        try:
            spiel_prozess.wait(timeout=3)
        except Exception:
            spiel_prozess.kill()
        spiel_prozess = None

# ── ROUTES ──
@app.route("/")
def index():
    # WLAN noch nicht eingerichtet? → Setup-Assistent (einmalig)
    if not os.path.exists(SETUP_DATEI):
        return redirect("/setup")
    # Sonst: bei jedem Boot zur Anmelde-/Modusauswahl
    return redirect("/login")

@app.route("/setup")
def setup_page():
    return send_from_directory(BASIS, "setup.html")

@app.route("/login")
def login_page():
    return send_from_directory(BASIS, "login.html")

# ══════════════════════════════════════════════════════════════════════════════
# SETUP-ASSISTENT ROUTEN
# ══════════════════════════════════════════════════════════════════════════════

def _get_ip():
    try:
        return subprocess.check_output("hostname -I", shell=True).decode().strip().split()[0]
    except Exception:
        return None

def _get_wlan_ssid():
    try:
        return subprocess.check_output("iwgetid -r", shell=True).decode().strip()
    except Exception:
        return None

@app.route("/api/setup/status")
def setup_status():
    ip   = _get_ip()
    ssid = _get_wlan_ssid()
    cfg  = lese_cloud_config()
    return jsonify({
        "wlan":  {"verbunden": bool(ip), "ssid": ssid or "", "ip": ip or ""},
        "cloud": {"modus": cfg.get("modus",""), "name": cfg.get("benutzer_name",""), "email": cfg.get("email","")},
        "setup_fertig": os.path.exists(SETUP_DATEI),
    })

@app.route("/api/setup/ip")
def setup_ip():
    ip   = _get_ip()
    ssid = _get_wlan_ssid()
    return jsonify({"ip": ip or "", "ssid": ssid or "", "url": f"http://{ip}:5000" if ip else ""})

@app.route("/api/setup/wlan/scan")
def setup_wlan_scan():
    try:
        subprocess.run(["nmcli", "device", "wifi", "rescan"], timeout=5, capture_output=True)
        import time; time.sleep(2)
        out = subprocess.check_output(
            ["nmcli", "--terse", "--fields", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            timeout=10
        ).decode("utf-8", errors="replace")
        netzwerke, seen = [], set()
        for line in out.strip().splitlines():
            # rsplit von rechts: SIGNAL und SECURITY enthalten keine Doppelpunkte
            parts = line.rsplit(":", 2)
            if len(parts) < 2:
                continue
            ssid = parts[0].replace("\\:", ":").strip()
            if not ssid or ssid == "--" or ssid in seen:
                continue
            seen.add(ssid)
            try:    signal = int(parts[1])
            except Exception: signal = 0
            secured = len(parts) > 2 and "--" not in parts[2] and parts[2].strip() != ""
            netzwerke.append({"ssid": ssid, "signal": signal, "secured": secured})
        netzwerke.sort(key=lambda x: x["signal"], reverse=True)
        return jsonify(netzwerke)
    except FileNotFoundError:
        return jsonify({"error": "nmcli nicht gefunden – WLAN-Verwaltung nicht verfügbar"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/setup/wlan/verbinden", methods=["POST"])
def setup_wlan_verbinden():
    d       = request.get_json() or {}
    ssid    = d.get("ssid", "").strip()
    passwort = d.get("passwort", "").strip()
    if not ssid:
        return jsonify({"error": "SSID fehlt"}), 400
    try:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if passwort:
            cmd += ["password", passwort]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            import time; time.sleep(1)
            return jsonify({"status": "ok", "ip": _get_ip() or ""})
        err = (r.stderr or r.stdout).strip()
        return jsonify({"error": err or "Verbindung fehlgeschlagen"}), 400
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Zeitüberschreitung – Verbindung fehlgeschlagen"}), 408
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/setup/qr")
def setup_qr():
    """QR-Code als SVG.
    ?phone=1  → URL zeigt auf /setup?mode=phone  (für TV-Bildschirm)
    sonst     → URL zeigt auf Geräte-Startseite  (für Moderator-Verbindung)
    """
    try:
        import qrcode, qrcode.image.svg, io
        ip   = _get_ip() or "schlagfertig.local"
        base = f"http://{ip}:5000"
        if request.args.get("phone") == "1":
            url = base + "/setup?mode=phone"
        else:
            url = base
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        return Response(buf.getvalue(), mimetype="image/svg+xml")
    except ImportError:
        return Response("", status=503)   # Fallback: JS zeigt URL-Text
    except Exception:
        return Response("", status=500)

@app.route("/api/setup/abschliessen", methods=["POST"])
def setup_abschliessen():
    with open(SETUP_DATEI, "w") as f:
        f.write("fertig")
    return jsonify({"status": "ok"})

@app.route("/display")
def display_page():
    return redirect('/game', code=301)

@app.route("/qr")
def qr_seite():
    return send_from_directory(BASIS, "qr_bild.html")

@app.route("/game")
def game_page():
    import time as _t
    v = request.args.get('v')
    if not v:
        return redirect(f'/game?v={int(_t.time())}', code=302)
    resp = send_from_directory(BASIS, "game.html")
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '-1'
    return resp

@app.route("/moderator")
def moderator_page():
    return send_from_directory(BASIS, "moderator.html")

@app.route("/sio.js")
def sio_js():
    """Socket.IO client JS – lokal gecacht, einmal vom CDN geholt."""
    ziel = os.path.join(BASIS, "socket.io.min.js")
    if not os.path.exists(ziel):
        # Einmalig herunterladen und cachen
        try:
            cdn = "https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"
            req = urllib.request.Request(cdn, headers={"User-Agent": "Schlagfertig/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                with open(ziel, "wb") as f:
                    f.write(r.read())
        except Exception:
            from flask import redirect
            return redirect("https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js")
    return send_from_directory(BASIS, "socket.io.min.js",
                               mimetype="application/javascript",
                               max_age=604800)

@app.route("/spielmodus")
def spielmodus_page():
    return send_from_directory(BASIS, "spielmodus.html")

@app.route("/editor")
def editor(): return send_from_directory(BASIS, "quiz_editor.html")

@app.route("/api/config", methods=["GET"])
def get_config():
    if not os.path.exists(KONFIG):
        return jsonify({"error": "Keine Konfiguration"}), 404
    with open(KONFIG, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/api/config", methods=["POST"])
def save_config():
    try:
        data = request.get_json()
        with open(KONFIG, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/spiel/starten", methods=["POST"])
def spiel_starten():
    global spiel_prozess
    try:
        if not spiel_laeuft():
            starte_quiz()
        schreibe_state("warten")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/spiel/stoppen", methods=["POST"])
def spiel_stoppen():
    global spiel_prozess
    try:
        schreibe_state("stoppen")
        if spiel_laeuft():
            spiel_prozess.terminate()
            spiel_prozess.wait()
        import time
        time.sleep(0.5)
        starte_quiz()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/spiel/status")
def spiel_status():
    return jsonify({"laeuft": spiel_laeuft(), "state": lese_state()})

@app.route("/api/buzzer/status")
def buzzer_status():
    """Gibt zurück wann jeder Buzzer zuletzt gedrückt wurde."""
    import time as _time
    now = _time.time()
    return jsonify({
        "buzzer": {str(nr): {"ts": ts, "vor_sek": round(now - ts, 1)}
                   for nr, ts in buzzer_zuletzt.items()},
        "gesamt": len(buzzer_zuletzt),
    })

@app.route("/api/buzzer/reset", methods=["POST"])
def buzzer_reset():
    """Setzt Buzzer-Status zurück (Testmodus neu starten)."""
    buzzer_zuletzt.clear()
    socketio.emit('buzzer_status_reset')
    return jsonify({"status": "ok"})

# ══════════════════════════════════════════════════════════════════════════════
# CLOUD-SYNC ROUTEN
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/cloud/config", methods=["GET"])
def cloud_config_get():
    cfg = lese_cloud_config()
    anzahl = 0
    try:
        with open(KONFIG, encoding="utf-8") as f:
            qcfg = json.load(f)
            anzahl = len(qcfg.get("fragen", []))
    except Exception:
        pass
    return jsonify({
        "cloud_url":  cfg.get("cloud_url", ""),
        "name":       cfg.get("benutzer_name", ""),
        "email":      cfg.get("email", ""),
        "modus":      cfg.get("modus", ""),
        "anzahl":     anzahl,
        "rolle":      "admin" if ist_admin(cfg.get("email","")) else "user",
    })

def lade_supabase_fragen(url=None):
    """Lädt Fragen vom öffentlichen Supabase-Bucket und konvertiert ins lokale Format."""
    ziel = url or SUPABASE_SYNC
    req  = urllib.request.Request(ziel, headers={"User-Agent": "Schlagfertig/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = json.loads(r.read().decode())
    roh = raw if isinstance(raw, list) else raw.get("fragen", raw.get("data", []))
    fragen = []
    for f in roh:
        fragen.append({
            "_gewaehlt":              False,
            "id":                     f.get("id"),
            "frage":                  f.get("frage", ""),
            "antwort":                f.get("antwort", ""),
            "kategorie":              f.get("kategorie"),
            "schwierigkeit":          f.get("schwierigkeit"),
            "modus":                  f.get("modus", "frei"),
            "antworten_mc":           f.get("antworten_mc"),
            "richtige_antwort_index": f.get("richtige_antwort_index"),
            "bild_url":               f.get("bild_url"),
            "audio_url":              f.get("audio_url"),
            "video_url":              f.get("video_url"),
        })
    return fragen

@app.route("/api/cloud/sync", methods=["POST"])
def cloud_sync():
    """Konto-Login und personalisierte Fragen laden (Supabase-Auth – kommt bald)."""
    # TODO: Supabase User-Auth implementieren wenn Accounts aktiv sind.
    # Bis dahin: gleicher Ablauf wie Gastmodus (öffentliche Bibliothek).
    try:
        fragen = lade_supabase_fragen()
        config = lese_oder_erstelle_config()
        config["fragen"] = fragen
        with open(KONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        schreibe_cloud_config({"modus": "gast"})
        return jsonify({"status": "ok", "name": "Gast", "anzahl": len(fragen)})
    except urllib.error.URLError as e:
        return jsonify({"error": f"Supabase nicht erreichbar: {e.reason}"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cloud/sync-refresh", methods=["POST"])
def cloud_sync_refresh():
    """Fragen erneut von Supabase laden."""
    try:
        fragen = lade_supabase_fragen()
        config = lese_oder_erstelle_config()
        config["fragen"] = fragen
        with open(KONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok", "anzahl": len(fragen)})
    except urllib.error.URLError as e:
        return jsonify({"error": f"Supabase nicht erreichbar: {e.reason}"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cloud/gast", methods=["POST"])
def cloud_gast():
    """Gastmodus: Fragen von Supabase laden, kein Account nötig."""
    try:
        fragen = lade_supabase_fragen()
        config = lese_oder_erstelle_config()
        config["fragen"] = fragen
        with open(KONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        schreibe_cloud_config({"modus": "gast"})
        return jsonify({"status": "ok", "anzahl": len(fragen)})
    except urllib.error.URLError:
        # Kein Internet: lokale Fragen nutzen (Fallback)
        schreibe_cloud_config({"modus": "gast"})
        return jsonify({"status": "ok", "anzahl": 0, "offline": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cloud/abmelden", methods=["POST"])
def cloud_abmelden():
    """Cloud-Konto vom Gerät abmelden."""
    schreibe_cloud_config({})
    return jsonify({"status": "ok"})

@app.route("/api/cloud/login", methods=["POST"])
def cloud_login():
    """Supabase-Login mit E-Mail + Passwort – lädt Fragen des Benutzers."""
    if not SUPABASE_ANON_KEY:
        return jsonify({"error": "SUPABASE_ANON_KEY nicht gesetzt (siehe /etc/environment auf dem Pi)"}), 503
    d        = request.get_json() or {}
    email    = d.get("email", "").strip()
    passwort = d.get("passwort", "")
    if not email or not passwort:
        return jsonify({"error": "E-Mail und Passwort erforderlich"}), 400
    try:
        sess  = _sb_auth(email, passwort)
        at    = sess["access_token"]
        rt    = sess.get("refresh_token", "")
        user  = sess.get("user", {})
        name  = (user.get("user_metadata") or {}).get("name") or email.split("@")[0]
        roh   = _sb_fragen(at)
        fragen = _speichere_fragen_lokal(roh)
        rolle = "admin" if ist_admin(email) else "user"
        schreibe_cloud_config({
            "modus": "konto", "email": email,
            "benutzer_name": name, "user_id": user.get("id", ""),
            "access_token": at, "refresh_token": rt, "rolle": rolle,
        })
        return jsonify({"status": "ok", "name": name, "anzahl": len(fragen), "rolle": rolle})
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return jsonify({"error": "E-Mail oder Passwort falsch"}), 401
        return jsonify({"error": f"Supabase-Fehler {e.code}"}), e.code
    except urllib.error.URLError:
        return jsonify({"error": "Supabase nicht erreichbar – WLAN prüfen"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cloud/auto-refresh", methods=["POST"])
def cloud_auto_refresh():
    """Erneuert Token und lädt Fragen neu – für automatischen Login nach Neustart."""
    cfg = lese_cloud_config()
    if cfg.get("modus") != "konto":
        return jsonify({"error": "Kein gespeichertes Konto"}), 400
    at  = cfg.get("access_token", "")
    rt  = cfg.get("refresh_token", "")
    name  = cfg.get("benutzer_name", "")
    email = cfg.get("email", "")
    # Erst mit bestehendem Token versuchen
    try:
        roh    = _sb_fragen(at)
        fragen = _speichere_fragen_lokal(roh)
        return jsonify({"status": "ok", "name": name, "email": email, "anzahl": len(fragen),
                        "rolle": "admin" if ist_admin(email) else "user"})
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403) or not rt:
            return jsonify({"error": f"Fehler {e.code}"}), e.code
    # Token abgelaufen → erneuern
    try:
        sess    = _sb_refresh(rt)
        new_at  = sess["access_token"]
        new_rt  = sess.get("refresh_token", rt)
        roh     = _sb_fragen(new_at)
        fragen  = _speichere_fragen_lokal(roh)
        cfg["access_token"]  = new_at
        cfg["refresh_token"] = new_rt
        cfg["rolle"] = "admin" if ist_admin(email) else "user"
        schreibe_cloud_config(cfg)
        return jsonify({"status": "ok", "name": name, "email": email, "anzahl": len(fragen),
                        "rolle": cfg["rolle"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route("/api/csv-upload", methods=["POST"])
def csv_upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Keine Datei"}), 400
        file = request.files["file"]
        spielmodus = request.args.get("spielmodus", "frei")
        # Verschiedene Encodings versuchen
        raw = file.read()
        content = None
        for encoding in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1', 'iso-8859-1']:
            try:
                content = raw.decode(encoding)
                break
            except:
                continue
        if content is None:
            return jsonify({"error": "Datei konnte nicht gelesen werden – bitte als UTF-8 speichern"}), 400
        reader = csv.DictReader(io.StringIO(content))
        fragen, fehler = [], []
        for i, row in enumerate(reader, start=2):
            frage   = row.get("frage","").strip()
            antwort = row.get("antwort","").strip()
            if not frage or not antwort:
                fehler.append(f"Zeile {i}: fehlt"); continue
            kat  = row.get("kategorie","Allgemein").strip()
            schw = row.get("schwierigkeit","leicht").strip().lower()
            if schw not in ["leicht","mittel","schwer"]: schw="leicht"
            mc_a = row.get("antwort_a","").strip()
            mc_b = row.get("antwort_b","").strip()
            mc_c = row.get("antwort_c","").strip()
            mc_d = row.get("antwort_d","").strip()
            richtig = row.get("richtige_antwort","").strip().upper()
            fo = {"frage":frage,"antwort":antwort,"kategorie":kat,"schwierigkeit":schw,"modus":spielmodus,"basis":False}
            if mc_a and mc_b and mc_c and mc_d:
                fo["antworten_mc"] = [mc_a,mc_b,mc_c,mc_d]
                fo["richtige_antwort_index"] = {"A":0,"B":1,"C":2,"D":3}.get(richtig,0)
                fo["modus"] = "mc"
            fragen.append(fo)
        if not fragen:
            return jsonify({"error":"Keine gültigen Fragen gefunden","fehler":fehler}), 400
        config = json.load(open(KONFIG,"r",encoding="utf-8")) if os.path.exists(KONFIG) else {"einstellungen":{},"spieler":[],"fragen":[]}
        if request.args.get("modus") == "hinzufuegen":
            config["fragen"].extend(fragen)
        else:
            config["fragen"] = fragen
        json.dump(config, open(KONFIG,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
        return jsonify({"status":"ok","anzahl":len(fragen),"fehler":fehler})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/api/csv-vorlage")
def csv_vorlage():
    v  = "frage,antwort,kategorie,schwierigkeit,antwort_a,antwort_b,antwort_c,antwort_d,richtige_antwort\n"
    v += "Was ist die Hauptstadt von Frankreich?,Paris,Geografie,leicht,Berlin,Paris,Madrid,Rom,B\n"
    v += "Wie viele Planeten hat unser Sonnensystem?,8,Astronomie,leicht,,,,,\n"
    v += "Wer hat euch verkuppelt?,Max Mustermann,Hochzeit,leicht,,,,,\n"
    return Response(v, mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=schlagfertig_vorlage.csv"})

def _punkte_zu_nr(punkte_roh):
    """Wandelt name-basierte Punkte ({"Max": 10}) in nr-basierte ({"1": 10}) um."""
    aktive = spiel_state.get('aktive_spieler', [])
    name_zu_nr = {s['name']: str(s['nr']) for s in aktive if 'name' in s and 'nr' in s}
    if not name_zu_nr:
        return punkte_roh
    konv = {}
    for k, v in punkte_roh.items():
        konv[name_zu_nr.get(str(k), str(k))] = v
    return konv

# ── WEBSOCKET EVENTS ──
@socketio.on('connect')
def on_connect():
    emit('state_update', spiel_state)
    if not _popup_aktiv:
        emit('buzzer_popup_ausblenden')

@socketio.on('mod_starten')
def on_mod_starten(data):
    spiel_state['modus'] = 'spiel'
    spiel_state['frage_idx'] = 0
    spiel_state['aktuelle_frage'] = data.get('frage')
    spiel_state['warteschlange'] = []
    spiel_state['aktive_spieler'] = data.get('aktive_spieler', [])
    spiel_state['punkte'] = _punkte_zu_nr(data.get('punkte', {}))
    spiel_state['spielmodus'] = data.get('spielmodus', 'frei')
    spiel_state['punktestand_sichtbar'] = False
    spiel_state['zeitlimit_aktiv'] = data.get('zeitlimit_aktiv', False)
    spiel_state['zeitlimit_sek'] = data.get('zeitlimit_sek', 30)
    schreibe_state("spiel")
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': 0,
        'gesamt': data.get('gesamt', 1),
        'spielmodus': spiel_state['spielmodus'],
        'aktive_spieler': spiel_state['aktive_spieler'],
        'zeitlimit_aktiv': spiel_state['zeitlimit_aktiv'],
        'zeitlimit_sek': spiel_state['zeitlimit_sek']
    })

@socketio.on('mod_naechste_frage')
def on_naechste_frage(data):
    spiel_state['aktuelle_frage'] = data.get('frage')
    spiel_state['frage_idx'] = data.get('idx', 0)
    spiel_state['warteschlange'] = []
    spiel_state['mc_gewaehlt'] = None
    _cancel_popup_timer()
    if data.get('aktive_spieler'):
        spiel_state['aktive_spieler'] = data.get('aktive_spieler')
    spiel_state['zeitlimit_aktiv'] = data.get('zeitlimit_aktiv', spiel_state.get('zeitlimit_aktiv', False))
    spiel_state['zeitlimit_sek'] = data.get('zeitlimit_sek', spiel_state.get('zeitlimit_sek', 30))
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': spiel_state['frage_idx'],
        'gesamt': data.get('gesamt', 1),
        'spielmodus': data.get('spielmodus', 'frei'),
        'aktive_spieler': spiel_state.get('aktive_spieler', []),
        'zeitlimit_aktiv': spiel_state['zeitlimit_aktiv'],
        'zeitlimit_sek': spiel_state['zeitlimit_sek']
    })

@socketio.on('mod_richtig')
def on_richtig(data):
    spiel_state['punkte'] = _punkte_zu_nr(data.get('punkte', {}))
    spiel_state['warteschlange'] = []
    _cancel_popup_timer()
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_ergebnis', {'richtig': True, 'delta': data.get('delta', 10)})

@socketio.on('mod_falsch')
def on_falsch(data):
    spiel_state['punkte'] = _punkte_zu_nr(data.get('punkte', {}))
    if spiel_state['warteschlange']:
        spiel_state['warteschlange'].pop(0)
    _cancel_popup_timer()
    # Nächsten Spieler in der Warteschlange anzeigen
    if spiel_state['warteschlange']:
        _starte_popup_timer()
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_ergebnis', {
        'richtig': False,
        'delta': data.get('delta', 5),
        'punkte': spiel_state['punkte'],
        'warteschlange': spiel_state['warteschlange']
    })

@socketio.on('mod_mc_auswahl')
def on_mc_auswahl(data):
    spiel_state['mc_gewaehlt'] = data.get('idx')
    socketio.emit('zeige_mc_auswahl', {
        'idx': data.get('idx'),
        'antwort': data.get('antwort')
    })

@socketio.on('mod_mc_aufloesen')
def on_mc_aufloesen(data):
    spiel_state['punkte'] = _punkte_zu_nr(data.get('punkte', {}))
    richtig = data.get('richtig', False)
    if richtig:
        spiel_state['warteschlange'] = []
        _cancel_popup_timer()
    else:
        if spiel_state['warteschlange']:
            spiel_state['warteschlange'].pop(0)
        _cancel_popup_timer()
        if spiel_state['warteschlange']:
            _starte_popup_timer()
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_mc_aufloesen', {
        'gewaehlt': data.get('gewaehlt'),
        'richtig_idx': data.get('richtig_idx'),
        'falsch_idx': data.get('falsch_idx'),
        'richtig': richtig,
        'delta': data.get('delta', 10),
        'punkte': spiel_state['punkte'],
        'warteschlange': spiel_state['warteschlange']
    })

@socketio.on('mod_freigeben')
def on_freigeben():
    spiel_state['warteschlange'] = []
    _cancel_popup_timer()
    socketio.emit('state_update', spiel_state)
    socketio.emit('buzzer_freigeben')

@socketio.on('mod_meme')
def on_mod_meme(data):
    gif = data.get('gif')
    if not gif:
        return
    payload = {'gif': gif}
    socketio.emit('zeige_meme', payload)
    socketio.emit('zeige_meme', payload, namespace='/100leute')

@socketio.on('mod_toggle_punktestand')
def on_toggle_punktestand(data):
    spiel_state['punktestand_sichtbar'] = not spiel_state.get('punktestand_sichtbar', False)
    socketio.emit('zeige_punktestand', {
        'sichtbar': spiel_state['punktestand_sichtbar'],
        'punkte': _punkte_zu_nr(data.get('punkte', {})),
        'spieler': data.get('spieler', [])
    })

@socketio.on('mod_sieger')
def on_sieger(data):
    spiel_state['modus'] = 'sieger'
    socketio.emit('zeige_sieger', {
        'punkte': _punkte_zu_nr(data.get('punkte', {})),
        'spieler': data.get('spieler', [])
    })

@socketio.on('mod_stoppen')
def on_stoppen():
    spiel_state['modus'] = 'warten'
    spiel_state['warteschlange'] = []
    _cancel_popup_timer()
    schreibe_state("stoppen")
    socketio.emit('state_update', spiel_state)

def _starte_popup_timer():
    global _popup_timer, _popup_aktiv
    if _popup_timer is not None:
        _popup_timer.cancel()
    _popup_aktiv = True
    def _timer_callback():
        global _popup_aktiv
        _popup_aktiv = False
        socketio.emit('buzzer_popup_ausblenden')
    _popup_timer = threading.Timer(3.0, _timer_callback)
    _popup_timer.daemon = True
    _popup_timer.start()

def _cancel_popup_timer():
    global _popup_timer, _popup_aktiv
    if _popup_timer is not None:
        _popup_timer.cancel()
        _popup_timer = None
    _popup_aktiv = False
    socketio.emit('buzzer_popup_ausblenden')

@socketio.on('buzzer_gedrueckt')
def on_buzzer(data):
    import time as _time
    nr = data.get('nr')
    eintrag = {'nr': nr, 'ms': data.get('ms')}
    neu = not any(e['nr'] == eintrag['nr'] for e in spiel_state['warteschlange'])
    if neu:
        spiel_state['warteschlange'].append(eintrag)
    # Letzten Druckzeitpunkt speichern (für Buzzer-Status)
    if nr is not None:
        buzzer_zuletzt[nr] = _time.time()
        socketio.emit('buzzer_status_update', {'nr': nr, 'ts': buzzer_zuletzt[nr]})
    socketio.emit('state_update', spiel_state)
    # Popup nur für den ersten Spieler in der Warteschlange anzeigen
    if neu and len(spiel_state['warteschlange']) == 1:
        _starte_popup_timer()

@socketio.on('test_start')
def on_test_start():
    """Browser öffnet Buzzer-Tab → Test-Modus an quiz_buzzer.py weiterleiten."""
    socketio.emit('test_start')

@socketio.on('test_stop')
def on_test_stop():
    """Browser verlässt Buzzer-Tab → Test-Modus beenden."""
    socketio.emit('test_stop')

@socketio.on('buzzer_test_press')
def on_buzzer_test_press(data):
    """Empfängt rohen Buzzer-Druck im Testmodus und leitet ihn an Clients weiter."""
    nr = data.get('nr')
    if nr is not None:
        import time as _time
        buzzer_zuletzt[nr] = _time.time()
        socketio.emit('buzzer_status_update', {'nr': nr, 'ts': buzzer_zuletzt[nr]})

@socketio.on('buzzer_test_release')
def on_buzzer_test_release(data):
    """Buzzer wurde losgelassen im Testmodus."""
    nr = data.get('nr')
    if nr is not None:
        buzzer_zuletzt.pop(nr, None)
        socketio.emit('buzzer_status_clear', {'nr': nr})

@socketio.on('buzzer_reset_test')
def on_buzzer_reset_test():
    """Setzt alle Buzzer-Zeitstempel zurück (für Testmodus)."""
    buzzer_zuletzt.clear()
    socketio.emit('buzzer_status_reset')

@app.route("/sounds/<dateiname>")
def serve_sound(dateiname):
    return send_from_directory(BASIS, dateiname)

@app.route("/api/sound-upload", methods=["POST"])
def sound_upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Keine Datei"}), 400
        file = request.files["file"]
        if not file.filename.endswith(('.mp3', '.wav', '.ogg')):
            return jsonify({"error": "Nur MP3, WAV oder OGG erlaubt"}), 400
        # Datei speichern
        ziel = os.path.join(BASIS, file.filename)
        file.save(ziel)
        return jsonify({"status": "ok", "dateiname": file.filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/meme-sounds/<dateiname>")
def serve_meme_sound(dateiname):
    return send_from_directory(SOUNDS_DIR, dateiname)

@app.route("/gifs/<dateiname>")
def serve_gif(dateiname):
    return send_from_directory(GIFS_DIR, dateiname)

@app.route("/api/meme-board", methods=["GET"])
def meme_board_get():
    return jsonify(lade_meme_board())

@app.route("/api/meme-board", methods=["POST"])
def meme_board_save():
    try:
        data = request.get_json()
        with open(MEME_KONFIG, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/meme-sound-upload", methods=["POST"])
def meme_sound_upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Keine Datei"}), 400
        file = request.files["file"]
        if not file.filename.lower().endswith(('.mp3', '.wav', '.ogg')):
            return jsonify({"error": "Nur MP3, WAV oder OGG erlaubt"}), 400
        dateiname = secure_filename(file.filename)
        file.save(os.path.join(SOUNDS_DIR, dateiname))
        return jsonify({"status": "ok", "dateiname": dateiname})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/gifs-liste")
def gifs_liste():
    dateien = sorted(f for f in os.listdir(GIFS_DIR) if f.lower().endswith(('.gif', '.mp4', '.webp')))
    return jsonify({"dateien": dateien})

@app.route("/api/giphy-search")
def giphy_search():
    q = request.args.get("q", "").strip()
    key = giphy_api_key()
    if not key:
        return jsonify({"error": "Kein Giphy-API-Key – bitte GIPHY_API_KEY in .env auf dem Pi setzen"}), 400
    if not q:
        return jsonify({"results": []})
    if not _requests:
        return jsonify({"error": "requests-Bibliothek nicht installiert"}), 500
    try:
        r = _requests.get("https://api.giphy.com/v1/gifs/search", params={
            "api_key": key, "q": q, "limit": 15, "rating": "pg-13", "lang": "de"
        }, timeout=8)
        d = r.json()
        ergebnisse = [{
            "id": g["id"],
            "titel": g.get("title") or q,
            "vorschau": g["images"]["fixed_width_small"]["url"],
            "gif_url": g["images"]["fixed_width"]["url"],
        } for g in d.get("data", [])]
        return jsonify({"results": ergebnisse})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/giphy-download", methods=["POST"])
def giphy_download():
    try:
        data = request.get_json()
        gif_url = data.get("gif_url")
        gif_id = data.get("id", "gif")
        if not gif_url:
            return jsonify({"error": "Keine GIF-URL"}), 400
        if not _requests:
            return jsonify({"error": "requests-Bibliothek nicht installiert"}), 500
        dateiname = secure_filename(f"giphy_{gif_id}.gif")
        r = _requests.get(gif_url, timeout=15)
        with open(os.path.join(GIFS_DIR, dateiname), "wb") as f:
            f.write(r.content)
        return jsonify({"status": "ok", "dateiname": dateiname})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/system/info", methods=["GET"])
def system_info():
    import subprocess
    try:
        ip = subprocess.check_output("hostname -I", shell=True).decode().strip().split()[0]
    except: ip = "Unbekannt"
    try:
        wlan = subprocess.check_output("iwgetid -r", shell=True).decode().strip()
    except: wlan = "Kein WLAN"
    try:
        hostname = subprocess.check_output("hostname", shell=True).decode().strip()
    except: hostname = "schlagfertig"
    try:
        df = subprocess.check_output("df -h / | tail -1", shell=True).decode().strip().split()
        speicher = f"{df[2]} von {df[1]} genutzt ({df[4]})"
    except: speicher = "Unbekannt"
    try:
        temp = subprocess.check_output("vcgencmd measure_temp", shell=True).decode().strip().replace("temp=","")
    except: temp = "Unbekannt"
    try:
        version_datei = os.path.join(BASIS, "VERSION")
        version = open(version_datei).read().strip() if os.path.exists(version_datei) else "?"
    except: version = "?"
    try:
        commit = subprocess.check_output(
            "git -C " + BASIS + " rev-parse --short HEAD 2>/dev/null",
            shell=True).decode().strip()
    except: commit = ""
    version_str = f"v{version}" + (f" ({commit})" if commit else "")
    return jsonify({"ip":ip,"wlan":wlan,"hostname":hostname,"speicher":speicher,"temperatur":temp,"version":version_str})

@app.route("/api/system/passwort", methods=["POST"])
def system_passwort():
    try:
        data = request.get_json()
        neues_pw = data.get("passwort","")
        if len(neues_pw) < 6:
            return jsonify({"error": "Zu kurz"}), 400
        cfg = lese_oder_erstelle_config()
        cfg["admin_passwort"] = neues_pw
        with open(KONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/system/shutdown", methods=["POST"])
def system_shutdown():
    import threading
    def do_shutdown():
        import time
        time.sleep(1)
        os.system("sudo shutdown -h now")
    threading.Thread(target=do_shutdown, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route("/api/system/reboot", methods=["POST"])
def system_reboot():
    import threading
    def do_reboot():
        import time
        time.sleep(1)
        os.system("sudo reboot")
    threading.Thread(target=do_reboot, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route("/api/system/update-check")
def system_update_check():
    try:
        subprocess.run(
            ["git", "-C", BASIS, "fetch", "origin", "main"],
            timeout=15, capture_output=True
        )
        aktuell = subprocess.check_output(
            ["git", "-C", BASIS, "rev-parse", "--short", "HEAD"], timeout=5
        ).decode().strip()
        neu = subprocess.check_output(
            ["git", "-C", BASIS, "rev-parse", "--short", "origin/main"], timeout=5
        ).decode().strip()
        msg = subprocess.check_output(
            ["git", "-C", BASIS, "log", "-1", "--format=%s", "origin/main"], timeout=5
        ).decode().strip()
        # Versionsnummer aus der neuen Version lesen
        try:
            neue_version = subprocess.check_output(
                ["git", "-C", BASIS, "show", f"origin/main:VERSION"], timeout=5
            ).decode().strip()
        except Exception:
            neue_version = ""
        try:
            version_datei = os.path.join(BASIS, "VERSION")
            akt_version = open(version_datei).read().strip() if os.path.exists(version_datei) else ""
        except Exception:
            akt_version = ""
        return jsonify({
            "aktuell": aktuell,
            "neu": neu,
            "version_aktuell": f"v{akt_version}" if akt_version else aktuell,
            "version_neu": f"v{neue_version}" if neue_version else neu,
            "update_verfuegbar": aktuell != neu,
            "nachricht": msg if aktuell != neu else "",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/system/update", methods=["POST"])
def system_update():
    def do_update():
        import time
        try:
            subprocess.run(["git", "-C", BASIS, "pull", "origin", "main"], timeout=60, capture_output=True)
            venv_pip = os.path.join(BASIS, "env", "bin", "pip")
            if os.path.exists(venv_pip):
                subprocess.run(
                    [venv_pip, "install", "-q", "-r", os.path.join(BASIS, "requirements.txt")],
                    timeout=120, capture_output=True
                )
        except Exception:
            pass
        time.sleep(1)
        os.system("sudo systemctl restart schlagfertig")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route("/einstellungen")
def einstellungen_page():
    return send_from_directory(BASIS, "einstellungen.html")

@app.route("/appstore")
def appstore_page():
    return send_from_directory(BASIS, "appstore.html")

INSTALLIERT_DATEI = os.path.join(BASIS, "installierte_spiele.json")

def _lade_installiert():
    try:
        with open(INSTALLIERT_DATEI, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def _speichere_installiert(ids):
    with open(INSTALLIERT_DATEI, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)

@app.route("/api/appstore/katalog")
def appstore_katalog():
    pfad = os.path.join(BASIS, "spiele_katalog.json")
    if not os.path.exists(pfad):
        return jsonify([])
    with open(pfad, encoding="utf-8") as f:
        katalog = json.load(f)
    installiert = _lade_installiert()
    for eintrag in katalog:
        eintrag["installiert"] = eintrag["id"] in installiert
    return jsonify(katalog)

@app.route("/api/appstore/installieren", methods=["POST"])
def appstore_installieren():
    d = request.get_json() or {}
    spiel_id = d.get("id", "").strip()
    if not spiel_id:
        return jsonify({"error": "ID fehlt"}), 400
    installiert = _lade_installiert()
    installiert.add(spiel_id)
    _speichere_installiert(installiert)
    return jsonify({"status": "ok"})

@app.route("/api/appstore/deinstallieren", methods=["POST"])
def appstore_deinstallieren():
    d = request.get_json() or {}
    spiel_id = d.get("id", "").strip()
    installiert = _lade_installiert()
    installiert.discard(spiel_id)
    _speichere_installiert(installiert)
    return jsonify({"status": "ok"})

@app.route("/spiele/<spiel_id>/moderator")
def spiel_moderator(spiel_id):
    pfad = os.path.join(BASIS, "spiele", spiel_id, "moderator.html")
    if not os.path.exists(pfad):
        return "Spiel nicht gefunden", 404
    return send_from_directory(os.path.join(BASIS, "spiele", spiel_id), "moderator.html")

@app.route("/spiele/<spiel_id>/beamer")
def spiel_beamer(spiel_id):
    pfad = os.path.join(BASIS, "spiele", spiel_id, "beamer.html")
    if not os.path.exists(pfad):
        return "Spiel nicht gefunden", 404
    return send_from_directory(os.path.join(BASIS, "spiele", spiel_id), "beamer.html")

@app.route("/api/api-keys-status")
def api_keys_status():
    return jsonify({
        "giphy":     bool(giphy_api_key()),
        "freesound": bool(freesound_api_key()),
    })

@app.route("/api/freesound-search")
def freesound_search():
    q   = request.args.get("q", "").strip()
    key = freesound_api_key()
    if not key:
        return jsonify({"error": "Kein Freesound-API-Key – bitte FREESOUND_API_KEY in .env auf dem Pi setzen"}), 400
    if not q:
        return jsonify({"results": []})
    if not _requests:
        return jsonify({"error": "requests-Bibliothek nicht installiert"}), 500
    try:
        r = _requests.get("https://freesound.org/apiv2/search/text/", params={
            "query": q, "token": key,
            "fields": "id,name,username,duration,previews",
            "filter": "duration:[0.5 TO 30]",
            "page_size": 15,
        }, timeout=10)
        d = r.json()
        ergebnisse = [{
            "id":       s["id"],
            "name":     s["name"],
            "nutzer":   s.get("username",""),
            "dauer":    round(s.get("duration", 0), 1),
            "vorschau": (s.get("previews") or {}).get("preview-hq-mp3",""),
        } for s in d.get("results", []) if (s.get("previews") or {}).get("preview-hq-mp3")]
        return jsonify({"results": ergebnisse})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/freesound-download", methods=["POST"])
def freesound_download():
    try:
        data      = request.get_json()
        vorschau  = data.get("vorschau_url","")
        sound_id  = data.get("id", "sound")
        name_roh  = data.get("name", f"freesound_{sound_id}")
        if not vorschau:
            return jsonify({"error": "Keine Vorschau-URL"}), 400
        if not _requests:
            return jsonify({"error": "requests-Bibliothek nicht installiert"}), 500
        r = _requests.get(vorschau, timeout=20)
        r.raise_for_status()
        basis = os.path.splitext(secure_filename(name_roh))[0] or f"freesound_{sound_id}"
        dateiname = f"{basis}.mp3"
        with open(os.path.join(SOUNDS_DIR, dateiname), "wb") as f:
            f.write(r.content)
        return jsonify({"status": "ok", "dateiname": dateiname})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/rollen", methods=["GET"])
def admin_rollen_get():
    err = check_admin()
    if err: return err
    return jsonify({"admins": sorted(lese_admin_emails())})

@app.route("/api/admin/rollen", methods=["POST"])
def admin_rollen_post():
    err = check_admin()
    if err: return err
    d      = request.get_json() or {}
    aktion = d.get("aktion")  # "hinzufuegen" | "entfernen"
    email  = (d.get("email","")).strip().lower()
    if not email:
        return jsonify({"error": "E-Mail fehlt"}), 400
    admins = set(lese_admin_emails())
    if aktion == "hinzufuegen":
        admins.add(email)
    elif aktion == "entfernen":
        admins.discard(email)
    else:
        return jsonify({"error": "Unbekannte Aktion"}), 400
    schreibe_admin_emails(admins)
    return jsonify({"status": "ok", "admins": sorted(admins)})

# ── 100-LEUTE-MODUL REGISTRIEREN ──────────────────────────────────────────────
spiel_100leute.init_app(app, socketio, stop_pygame=stoppe_pygame, start_pygame=starte_quiz)

if __name__ == "__main__":
    print("Schlagfertig Server startet...")
    print("Erreichbar unter: http://schlagfertig.local:5000")
    starte_quiz()
    print("Wartebildschirm gestartet!")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
