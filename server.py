#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory, redirect, Response
from flask_socketio import SocketIO, emit
import json, os, csv, io, subprocess

app = Flask(__name__)
app.config['SECRET_KEY'] = 'schlagfertig2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BASIS       = os.path.dirname(os.path.abspath(__file__))
KONFIG      = os.path.join(BASIS, "quiz_config.json")
STATE_DATEI = os.path.join(BASIS, ".spiel_state")
spiel_prozess = None

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
        ["python3", os.path.join(BASIS, "quiz_buzzer.py")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    schreibe_state("warten")

# ── ROUTES ──
@app.route("/")
def index(): return redirect("/editor")

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

# ── WEBSOCKET EVENTS ──
@socketio.on('connect')
def on_connect():
    emit('state_update', spiel_state)

@socketio.on('mod_starten')
def on_mod_starten(data):
    spiel_state['modus'] = 'spiel'
    spiel_state['frage_idx'] = 0
    spiel_state['aktuelle_frage'] = data.get('frage')
    spiel_state['warteschlange'] = []
    spiel_state['punkte'] = data.get('punkte', {})
    spiel_state['spielmodus'] = data.get('spielmodus', 'frei')
    spiel_state['aktive_spieler'] = data.get('aktive_spieler', [])
    spiel_state['punktestand_sichtbar'] = False
    schreibe_state("spiel")
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': 0,
        'gesamt': data.get('gesamt', 1),
        'spielmodus': spiel_state['spielmodus'],
        'aktive_spieler': spiel_state['aktive_spieler']
    })

@socketio.on('mod_naechste_frage')
def on_naechste_frage(data):
    spiel_state['aktuelle_frage'] = data.get('frage')
    spiel_state['frage_idx'] = data.get('idx', 0)
    spiel_state['warteschlange'] = []
    spiel_state['mc_gewaehlt'] = None
    if data.get('aktive_spieler'):
        spiel_state['aktive_spieler'] = data.get('aktive_spieler')
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': spiel_state['frage_idx'],
        'gesamt': data.get('gesamt', 1),
        'spielmodus': data.get('spielmodus', 'frei'),
        'aktive_spieler': spiel_state.get('aktive_spieler', [])
    })

@socketio.on('mod_richtig')
def on_richtig(data):
    spiel_state['punkte'] = data.get('punkte', {})
    spiel_state['warteschlange'] = []
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_ergebnis', {'richtig': True, 'delta': data.get('delta', 10)})

@socketio.on('mod_falsch')
def on_falsch(data):
    spiel_state['punkte'] = data.get('punkte', {})
    if spiel_state['warteschlange']:
        spiel_state['warteschlange'].pop(0)
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
    spiel_state['punkte'] = data.get('punkte', {})
    spiel_state['warteschlange'] = []
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_mc_aufloesen', {
        'gewaehlt': data.get('gewaehlt'),
        'richtig_idx': data.get('richtig_idx'),
        'richtig': data.get('richtig'),
        'delta': data.get('delta', 10)
    })

@socketio.on('mod_freigeben')
def on_freigeben():
    spiel_state['warteschlange'] = []
    socketio.emit('state_update', spiel_state)
    socketio.emit('buzzer_freigeben')

@socketio.on('mod_toggle_punktestand')
def on_toggle_punktestand(data):
    spiel_state['punktestand_sichtbar'] = not spiel_state.get('punktestand_sichtbar', False)
    socketio.emit('zeige_punktestand', {
        'sichtbar': spiel_state['punktestand_sichtbar'],
        'punkte': data.get('punkte', {}),
        'spieler': data.get('spieler', [])
    })

@socketio.on('mod_sieger')
def on_sieger(data):
    spiel_state['modus'] = 'sieger'
    socketio.emit('zeige_sieger', {
        'punkte': data.get('punkte', {}),
        'spieler': data.get('spieler', [])
    })

@socketio.on('mod_stoppen')
def on_stoppen():
    spiel_state['modus'] = 'warten'
    spiel_state['warteschlange'] = []
    schreibe_state("stoppen")
    socketio.emit('state_update', spiel_state)

@socketio.on('buzzer_gedrueckt')
def on_buzzer(data):
    eintrag = {'nr': data.get('nr'), 'ms': data.get('ms')}
    if not any(e['nr'] == eintrag['nr'] for e in spiel_state['warteschlange']):
        spiel_state['warteschlange'].append(eintrag)
    socketio.emit('state_update', spiel_state)

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
    return jsonify({"ip":ip,"wlan":wlan,"hostname":hostname,"speicher":speicher,"temperatur":temp})

@app.route("/api/system/passwort", methods=["POST"])
def system_passwort():
    try:
        data = request.get_json()
        neues_pw = data.get("passwort","")
        if len(neues_pw) < 6:
            return jsonify({"error": "Zu kurz"}), 400
        cfg = lese_config()
        cfg["admin_passwort"] = neues_pw
        schreibe_config(cfg)
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

if __name__ == "__main__":
    print("Schlagfertig Server startet...")
    print("Erreichbar unter: http://schlagfertig.local:5000")
    starte_quiz()
    print("Wartebildschirm gestartet!")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
