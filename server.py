#!/usr/bin/env python3
"""
Schlagfertig – Flask Server mit WebSocket
"""
from flask import Flask, request, jsonify, send_from_directory, redirect, Response
from flask_socketio import SocketIO, emit
import json, os, csv, io, subprocess, threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'schlagfertig2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BASIS       = os.path.dirname(os.path.abspath(__file__))
KONFIG      = os.path.join(BASIS, "quiz_config.json")
STATE_DATEI = os.path.join(BASIS, ".spiel_state")
spiel_prozess = None

# Spielzustand
spiel_state = {
    "modus": "warten",        # warten | spiel
    "aktuelle_frage": None,
    "frage_idx": 0,
    "warteschlange": [],
    "punkte": {},
    "mc_aktiv": False
}

def schreibe_state(modus):
    with open(STATE_DATEI, "w") as f:
        f.write(modus)

def lese_state():
    try:
        with open(STATE_DATEI, "r") as f:
            return f.read().strip()
    except:
        return "warten"

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

# ─────────────────────────────────────────────
#  WEBSOCKET EVENTS
# ─────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    emit('state_update', spiel_state)

@socketio.on('mod_starten')
def on_mod_starten(data):
    """Moderator startet das Spiel"""
    spiel_state['modus'] = 'spiel'
    spiel_state['frage_idx'] = 0
    spiel_state['aktuelle_frage'] = data.get('frage')
    spiel_state['warteschlange'] = []
    spiel_state['punkte'] = data.get('punkte', {})
    schreibe_state("spiel")
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': spiel_state['frage_idx'],
        'gesamt': data.get('gesamt', 1),
        'mc_aktiv': spiel_state['mc_aktiv']
    })

@socketio.on('mod_naechste_frage')
def on_naechste_frage(data):
    """Moderator wechselt zur nächsten Frage"""
    spiel_state['aktuelle_frage'] = data.get('frage')
    spiel_state['frage_idx'] = data.get('idx', 0)
    spiel_state['warteschlange'] = []
    spiel_state['mc_aktiv'] = False
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': spiel_state['frage_idx'],
        'gesamt': data.get('gesamt', 1),
        'mc_aktiv': False
    })

@socketio.on('mod_richtig')
def on_richtig(data):
    """Moderator bewertet Antwort als richtig"""
    spiel_state['punkte'] = data.get('punkte', {})
    spiel_state['warteschlange'] = []
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_ergebnis', {'richtig': True, 'delta': data.get('delta', 10)})

@socketio.on('mod_falsch')
def on_falsch(data):
    """Moderator bewertet Antwort als falsch"""
    spiel_state['punkte'] = data.get('punkte', {})
    if spiel_state['warteschlange']:
        spiel_state['warteschlange'].pop(0)
    socketio.emit('state_update', spiel_state)
    socketio.emit('zeige_ergebnis', {'richtig': False, 'delta': data.get('delta', 5)})

@socketio.on('mod_freigeben')
def on_freigeben():
    """Moderator gibt Buzzer frei"""
    spiel_state['warteschlange'] = []
    socketio.emit('state_update', spiel_state)
    socketio.emit('buzzer_freigeben')

@socketio.on('mod_mc_toggle')
def on_mc_toggle(data):
    """Moderator blendet MC Antworten ein/aus"""
    spiel_state['mc_aktiv'] = data.get('aktiv', False)
    socketio.emit('zeige_frage', {
        'frage': spiel_state['aktuelle_frage'],
        'idx': spiel_state['frage_idx'],
        'gesamt': data.get('gesamt', 1),
        'mc_aktiv': spiel_state['mc_aktiv']
    })

@socketio.on('buzzer_gedrueckt')
def on_buzzer(data):
    """quiz_buzzer.py meldet Buzzer-Druck"""
    eintrag = {'nr': data.get('nr'), 'ms': data.get('ms')}
    if not any(e['nr'] == eintrag['nr'] for e in spiel_state['warteschlange']):
        spiel_state['warteschlange'].append(eintrag)
    socketio.emit('state_update', spiel_state)

@socketio.on('mod_stoppen')
def on_stoppen():
    """Moderator stoppt das Spiel"""
    spiel_state['modus'] = 'warten'
    spiel_state['warteschlange'] = []
    schreibe_state("stoppen")
    socketio.emit('state_update', spiel_state)

# ─────────────────────────────────────────────
#  REST API
# ─────────────────────────────────────────────

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
        import time; time.sleep(1)
        starte_quiz()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/spiel/status")
def spiel_status():
    return jsonify({
        "laeuft": spiel_laeuft(),
        "state": lese_state()
    })

@app.route("/api/csv-upload", methods=["POST"])
def csv_upload():
    try:
        if "file" not in request.files:
            return jsonify({"error": "Keine Datei"}), 400
        file = request.files["file"]
        content = file.read().decode("utf-8-sig")
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
            fo = {"frage":frage,"antwort":antwort,"kategorie":kat,"schwierigkeit":schw,"modus":"auto"}
            if mc_a and mc_b and mc_c and mc_d:
                fo["antworten_mc"] = [mc_a,mc_b,mc_c,mc_d]
                fo["richtige_antwort_index"] = {"A":0,"B":1,"C":2,"D":3}.get(richtig,0)
                fo["modus"] = "mc"
            fragen.append(fo)
        if not fragen:
            return jsonify({"error":"Keine Fragen","fehler":fehler}), 400
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
    return Response(v, mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=schlagfertig_vorlage.csv"})

if __name__ == "__main__":
    print("Schlagfertig Server startet...")
    print("Erreichbar unter: http://schlagfertig.local:5000")
    starte_quiz()
    print("Wartebildschirm gestartet!")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
