#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  Schlagfertig – Display-Starter                         ║
# ║                                                          ║
# ║  Öffnet auf dem HDMI-Display die Kiosk-Ansicht          ║
# ║  (/display) in nativer Auflösung.                       ║
# ║                                                          ║
# ║  Wird automatisch beim Desktop-Start ausgeführt.        ║
# ╚══════════════════════════════════════════════════════════╝

SERVER_URL="http://localhost:5000"

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

# HDMI auf native Auflösung setzen (damit Chromium den vollen Bildschirm füllt)
xrandr --auto 2>/dev/null || true

# ── HDMI-Display: Kiosk-Ansicht ─────────────────────────────
DISPLAY=:0 chromium-browser \
    --user-data-dir=/tmp/chromium-sg-display \
    --noerrdialogs \
    --disable-infobars \
    --kiosk \
    --no-sandbox \
    --disable-translate \
    --disable-features=TranslateUI \
    --disable-extensions \
    --disable-component-update \
    --autoplay-policy=no-user-gesture-required \
    --password-store=basic \
    --check-for-update-interval=31536000 \
    --app="$SERVER_URL/display" \
    &

echo "Display gestartet."
wait
