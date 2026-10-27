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

LOG="/tmp/schlagfertig-display.log"
echo "=== Display-Start $(date) ===" >> "$LOG"
echo "Flutter-Binary: $FLUTTER_BIN" >> "$LOG"

# Flutter mit Neustart-Schleife (crasht es, startet es neu)
while true; do
    echo "[$(date '+%H:%M:%S')] Starte Flutter..." >> "$LOG"

    DISPLAY=:0 "$FLUTTER_BIN" >> "$LOG" 2>&1 &
    FLUTTER_PID=$!

    # Vollbild setzen sobald Fenster erscheint
    for i in $(seq 1 15); do
        sleep 1
        if DISPLAY=:0 wmctrl -l 2>/dev/null | grep -qi "schlagfertig"; then
            DISPLAY=:0 wmctrl -r "schlagfertig" -b add,fullscreen 2>/dev/null || true
            echo "[$(date '+%H:%M:%S')] Vollbild gesetzt" >> "$LOG"
            break
        fi
    done

    wait $FLUTTER_PID
    EXIT_CODE=$?
    echo "[$(date '+%H:%M:%S')] Flutter beendet (Exit: $EXIT_CODE) – Neustart in 3s..." >> "$LOG"
    sleep 3
done
