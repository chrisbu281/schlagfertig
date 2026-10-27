#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  Schlagfertig – Display-Starter (Flutter)               ║
# ║                                                          ║
# ║  Startet die Flutter-Display-App auf dem TV (HDMI).     ║
# ║  Wird automatisch beim Desktop-Start ausgeführt.        ║
# ╚══════════════════════════════════════════════════════════╝

SERVER_URL="http://localhost:5000"
FLUTTER_BUILD_DIR="/home/pi/schlagfertig/flutter_app/build/linux"
FLUTTER_BIN=$(find "$FLUTTER_BUILD_DIR" -name "schlagfertig" -path "*/release/bundle/*" 2>/dev/null | head -1)

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

# Altes Chromium beenden (falls noch aus vorheriger Installation aktiv)
pkill -f "chromium-sg-display" 2>/dev/null || true
sleep 0.5

# Nur TV-HDMI aktivieren, alle anderen Outputs deaktivieren
HDMI_PRIMARY=""
XRANDR_CMD="xrandr"
while IFS= read -r line; do
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

# Flutter-Binary prüfen
if [ -z "$FLUTTER_BIN" ] || [ ! -x "$FLUTTER_BIN" ]; then
    echo "FEHLER: Flutter-Release-Binary nicht gefunden unter $FLUTTER_BUILD_DIR"
    echo "Bitte zuerst auf dem Pi ausführen:"
    echo "  cd /home/pi/schlagfertig/flutter_app && flutter build linux --release"
    exit 1
fi

echo "Starte Flutter-Display: $FLUTTER_BIN"

# Flutter-App starten
DISPLAY=:0 "$FLUTTER_BIN" &
FLUTTER_PID=$!

# Fenster nach dem Start per wmctrl/xdotool auf Vollbild setzen
for i in $(seq 1 20); do
    sleep 1
    if wmctrl -l 2>/dev/null | grep -qi "schlagfertig"; then
        wmctrl -r "schlagfertig" -b add,fullscreen 2>/dev/null || true
        echo "Display Vollbild gesetzt (wmctrl)"
        break
    fi
    # Fallback: xdotool
    if xdotool search --class "schlagfertig" 2>/dev/null | head -1 | grep -q .; then
        xdotool search --class "schlagfertig" windowfocus windowsize "$(xdpyinfo | grep 'dimensions:' | awk '{print $2}' | tr 'x' ' ')" 2>/dev/null || true
        break
    fi
done

echo "Display gestartet (Flutter PID: $FLUTTER_PID)"
wait $FLUTTER_PID
