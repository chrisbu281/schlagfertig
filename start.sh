#!/bin/bash
echo ""
echo "  Schlagfertig Party Hub wird gestartet ..."
echo ""

# Python prüfen
if ! command -v python3 &>/dev/null; then
  echo "  FEHLER: Python 3 nicht gefunden."
  echo "  Mac: brew install python3"
  echo "  Linux: sudo apt install python3 python3-pip"
  exit 1
fi

# Abhängigkeiten installieren (falls nötig)
if ! python3 -c "import flask_socketio" &>/dev/null; then
  echo "  Installiere Abhängigkeiten ..."
  pip3 install flask flask-socketio
  echo ""
fi

# Server starten
python3 party_app.py
