#!/usr/bin/env python3
"""Test-Spiel 4 — minimales Chromium-Beamer-Testmodul."""

import os, subprocess, time as _time, signal, threading

BASIS     = os.path.dirname(os.path.abspath(__file__))
NAMESPACE = "/testspiel"

_socketio  = None
_chromium  = None
_steuerung = {"stop_pygame": None, "start_pygame": None}
state      = {"phase": "bereit"}


def _broadcast():
    if _socketio:
        _socketio.emit("state", state, namespace=NAMESPACE)


def _kill_display_chromium():
    subprocess.run(["pkill", "-f", "chromium-sg-display"], capture_output=True)
    _time.sleep(0.3)


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
        subprocess.run(cmd, env=env, capture_output=True)
        _time.sleep(0.3)
    else:
        subprocess.run(["xrandr", "--auto"], env=env, capture_output=True)


def _starte_display_chromium():
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
            print(f"testspiel: stop_pygame Fehler: {e}")
    _time.sleep(0.3)
    _kill_display_chromium()
    url   = "http://localhost:5000/spiel/testspiel"
    env   = {**os.environ, "DISPLAY": ":0"}
    _setze_einzelbildschirm(env)
    import shutil
    shutil.rmtree("/tmp/chromium-sg-testspiel", ignore_errors=True)
    flags = ["--user-data-dir=/tmp/chromium-sg-testspiel",
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
            print(f"testspiel: Beamer gestartet ({binary})")
            break
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"testspiel: Chromium-Start Fehler: {e}")
            break
    state["phase"] = "aktiv"
    _broadcast()


def stoppe_beamer():
    global _chromium
    if _chromium:
        try:
            pgid = os.getpgid(_chromium.pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                _chromium.kill()
            except Exception:
                pass
        try:
            _chromium.wait(timeout=2)
        except Exception:
            pass
        _chromium = None
    _time.sleep(0.8)
    _starte_display_chromium()
    state["phase"] = "bereit"
    _broadcast()
    if _steuerung["start_pygame"]:
        try:
            _steuerung["start_pygame"]()
        except Exception as e:
            print(f"testspiel: start_pygame Fehler: {e}")


def init_app(app, socketio, stop_pygame=None, start_pygame=None):
    global _socketio
    _socketio = socketio
    _steuerung["stop_pygame"]  = stop_pygame
    _steuerung["start_pygame"] = start_pygame

    from flask import send_from_directory
    from flask_socketio import emit

    @app.route("/spiel/testspiel")
    def beamer_testspiel():
        return send_from_directory(BASIS, "beamer_testspiel.html")

    @app.route("/moderator/testspiel")
    def moderator_testspiel():
        return send_from_directory(BASIS, "moderator_testspiel.html")

    @socketio.on("connect", namespace=NAMESPACE)
    def _on_connect():
        emit("state", state)

    @socketio.on("spiel_starten", namespace=NAMESPACE)
    def _on_spiel_starten(data=None):
        threading.Thread(target=starte_beamer, daemon=True).start()

    @socketio.on("spiel_beenden", namespace=NAMESPACE)
    def _on_spiel_beenden(data=None):
        threading.Thread(target=stoppe_beamer, daemon=True).start()

    @socketio.on("beamer_reload", namespace=NAMESPACE)
    def _on_beamer_reload(data=None):
        _socketio.emit("beamer_reload", {}, namespace=NAMESPACE)
