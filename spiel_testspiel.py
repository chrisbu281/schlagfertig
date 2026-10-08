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


def starte_beamer():
    global _chromium
    if _steuerung["stop_pygame"]:
        try:
            _steuerung["stop_pygame"]()
        except Exception as e:
            print(f"testspiel: stop_pygame Fehler: {e}")
    _time.sleep(0.3)
    url   = "http://localhost:5000/spiel/testspiel"
    env   = {**os.environ, "DISPLAY": ":0"}
    flags = ["--user-data-dir=/tmp/chromium-sg-testspiel",
             "--kiosk", "--no-sandbox", "--noerrdialogs", "--disable-infobars",
             "--disable-session-crashed-bubble", "--password-store=basic",
             "--autoplay-policy=no-user-gesture-required", url]
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
