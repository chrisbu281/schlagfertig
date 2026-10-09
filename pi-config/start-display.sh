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

# Pi 5: TV-HDMI als primären Output setzen, ungenutzten HDMI-Port deaktivieren.
# DSI (7"-Touchscreen) wird NICHT angefasst – der bleibt für die Steuerung aktiv.
HDMI_PRIMARY=""
HDMI_CMD=""
while IFS= read -r output; do
    status=$(xrandr 2>/dev/null | awk -v o="$output" '$0 ~ "^"o" " {print $2; exit}')
    if [ "$status" = "connected" ] && [ -z "$HDMI_PRIMARY" ]; then
        HDMI_PRIMARY="$output"
        HDMI_CMD="--output $output --primary --auto"
    else
        HDMI_CMD="$HDMI_CMD --output $output --off"
    fi
done < <(xrandr 2>/dev/null | grep "^HDMI" | awk '{print $1}')

if [ -n "$HDMI_PRIMARY" ]; then
    xrandr $HDMI_CMD 2>/dev/null || true
    sleep 0.5
else
    xrandr --auto 2>/dev/null || true
fi

# Gecachten Chromium-Zustand löschen (verhindert falsche Fenstergröße nach Neustart)
rm -rf /tmp/chromium-sg-display

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
