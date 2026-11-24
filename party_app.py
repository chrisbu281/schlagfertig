#!/usr/bin/env python3
"""
Schlagfertig Party Hub – Cross-Platform Server
Starten: python party_app.py
Läuft auf Windows, Mac und Linux – kein Raspberry Pi nötig.
"""
import os, sys, threading, webbrowser, time
from flask import Flask, send_from_directory, redirect, jsonify
from flask_socketio import SocketIO, emit

BASIS = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'silvester-party-hub'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

HUB = '/hub'
_scene = {'name': 'idle'}

# ── Statische Seiten ─────────────────────────────────────────────────────────
@app.route('/')
def r_root():
    return redirect('/dashboard')

@app.route('/dashboard')
def r_dashboard():
    return send_from_directory(BASIS, 'party_dashboard.html')

@app.route('/display')
def r_display():
    return send_from_directory(BASIS, 'party_display.html')

@app.route('/zufall')
def r_zufall():
    return send_from_directory(BASIS, 'zufall.html')

@app.route('/sio.js')
def r_sio():
    # Lokale Kopie bevorzugen (offline-fähig) – sonst CDN
    local = os.path.join(BASIS, 'socket.io.min.js')
    if os.path.exists(local):
        return send_from_directory(BASIS, 'socket.io.min.js')
    return redirect('https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.4/socket.io.min.js')

# ── 100 Leute gefragt (optional) ─────────────────────────────────────────────
_has_100leute = False
try:
    sys.path.insert(0, BASIS)
    import spiel_100leute
    spiel_100leute.init_app(app, socketio,
        stop_pygame=lambda: None,
        start_pygame=lambda: None)
    _has_100leute = True
    print("✓  100 Leute gefragt geladen")
except Exception as e:
    print(f"⚠  100 Leute nicht geladen: {e}")

# ── Hub: Dashboard ↔ Display (Namespace /hub) ────────────────────────────────
@socketio.on('connect', namespace=HUB)
def hub_connect():
    # Neuer Client bekommt sofort die aktuelle Szene
    emit('scene', _scene)

@socketio.on('show_scene', namespace=HUB)
def hub_show_scene(data):
    global _scene
    name = data.get('name', 'idle') if isinstance(data, dict) else str(data)
    _scene = {'name': name}
    emit('scene', _scene, namespace=HUB, broadcast=True)

@app.route('/api/scene')
def api_scene():
    return jsonify(_scene)

# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    PORT = 5000
    URL = f'http://localhost:{PORT}'

    print(f"""
🎉  Schlagfertig Party Hub

    Steuerzentrale (Dashboard):  {URL}/dashboard
    Beamer-Fenster (Display):    {URL}/display
    Zufallsgenerator:            {URL}/zufall""")

    if _has_100leute:
        print(f"""\
    100 Leute – Moderator:       {URL}/moderator/100leute
    100 Leute – Beamer:          {URL}/spiel/100leute
    Buzzer-Seiten:               {URL}/100leute/buzz/A   {URL}/100leute/buzz/B""")

    print(f"""
    Dashboard öffnet sich gleich im Browser …
    Beenden: Strg+C
""")

    def _open():
        time.sleep(1.2)
        webbrowser.open(f'{URL}/dashboard')
    threading.Thread(target=_open, daemon=True).start()

    socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
