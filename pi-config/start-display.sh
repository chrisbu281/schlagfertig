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

# Nur TV-HDMI aktivieren, alle anderen Outputs (DSI, zweiter HDMI) deaktivieren.
# Mit DSI aktiv im X11-Virtual-Desktop zeigt Chromium kiosk nur den halben Bildschirm.
HDMI_PRIMARY=""
XRANDR_CMD="xrandr"
while IFS= read -r line; do
    # Nur Output-Zeilen (beginnen nicht mit Leerzeichen)
    [[ "$line" =~ ^[[:space:]] ]] && continue
    output=$(echo "$line" | awk '{print $1}')
    [[ "$output" == "Screen" ]] && continue
    [[ -z "$output" ]] && continue

    if echo "$line" | grep -q " connected" && ! echo "$line" | grep -q " disconnected"; then
        if echo "$output" | grep -qE "^HDMI" && [ -z "$HDMI_PRIMARY" ]; then
            HDMI_PRIMARY="$output"
            XRANDR_CMD="$XRANDR_CMD --output $output --primary --mode 1920x1080 --pos 0x0"
        else
            XRANDR_CMD="$XRANDR_CMD --output $output --off"
        fi
    else
        XRANDR_CMD="$XRANDR_CMD --output $output --off"
    fi
done < <(xrandr 2>/dev/null)

if [ -n "$HDMI_PRIMARY" ]; then
    eval "$XRANDR_CMD" 2>/dev/null || true
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
