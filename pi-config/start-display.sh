#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  Schlagfertig – Display-Starter                         ║
# ║                                                          ║
# ║  Öffnet auf dem eingebauten DSI-Display die Kiosk-      ║
# ║  Ansicht (/display) und optional auf HDMI die           ║
# ║  Spieler-Ansicht (/game).                               ║
# ║                                                          ║
# ║  Wird automatisch beim Desktop-Start ausgeführt.        ║
# ╚══════════════════════════════════════════════════════════╝

SERVER_URL="http://localhost:5000"
DSI_DISPLAY=":0"      # Primärer Display (DSI, eingebaut)
HDMI_DISPLAY=":1"     # HDMI-Ausgang (optional, für TV/Beamer)

# Warten bis Server bereit
echo "Warte auf Schlagfertig-Server..."
for i in $(seq 1 30); do
    curl -sf "$SERVER_URL/api/spiel/status" > /dev/null && break
    sleep 1
done

# Bildschirmschoner deaktivieren
xset -dpms 2>/dev/null || true
xset s off   2>/dev/null || true
xset s noblank 2>/dev/null || true

# ── DSI-Display: Kiosk-Ansicht ──────────────────────────────
# Zeigt /display  →  Status, QR-Code, Spielzustand
DISPLAY=$DSI_DISPLAY chromium-browser \
    --noerrdialogs \
    --disable-infobars \
    --kiosk \
    --no-sandbox \
    --disable-translate \
    --disable-features=TranslateUI \
    --disable-extensions \
    --check-for-update-interval=31536000 \
    --app="$SERVER_URL/display" \
    &

# ── HDMI-Display: Spieler-Ansicht (optional) ────────────────
# Nur starten wenn ein zweites Display angeschlossen ist.
# Auskommentieren um die HDMI-Ausgabe zu aktivieren:
#
# DISPLAY=$HDMI_DISPLAY chromium-browser \
#     --noerrdialogs \
#     --disable-infobars \
#     --kiosk \
#     --no-sandbox \
#     --app="$SERVER_URL/game" \
#     &

echo "Displays gestartet."
wait
