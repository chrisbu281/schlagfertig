#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Schlagfertig – Setup-Skript für Raspberry Pi 4 / 5
#  Verwendung: sudo bash setup.sh
# ═══════════════════════════════════════════════════════════════
set -e

# ── Konfiguration ────────────────────────────────────────────────
REPO="https://github.com/chrisbu281/schlagfertig"
BRANCH="main"
INSTALL_DIR="/home/pi/schlagfertig"
PI_USER="pi"
SERVER_URL="http://localhost:5000/game"
# ────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
info() { echo -e "  ${YELLOW}→${NC}  $1"; }
err()  { echo -e "  ${RED}✗${NC}  $1"; exit 1; }
step() { echo -e "\n${BOLD}[$1]${NC} $2"; }

echo ""
echo -e "  ${BOLD}╔══════════════════════════════════╗${NC}"
echo -e "  ${BOLD}║  SCHLAG${RED}FERTIG${NC}${BOLD}  Setup v1.1       ║${NC}"
echo -e "  ${BOLD}╚══════════════════════════════════╝${NC}"
echo ""

# ── Root-Check ──
[[ $EUID -ne 0 ]] && err "Bitte als root ausführen: sudo bash setup.sh"

# ── Pi-Modell prüfen ──
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "unbekannt")
info "Gerät: $PI_MODEL"
if [[ "$PI_MODEL" != *"Raspberry Pi 4"* ]] && [[ "$PI_MODEL" != *"Raspberry Pi 5"* ]]; then
  echo -e "  ${YELLOW}⚠${NC}  Nur Pi 4/5 offiziell unterstützt. Trotzdem fortfahren? [j/N]"
  read -r antwort
  [[ "$antwort" != "j" && "$antwort" != "J" ]] && exit 0
fi

# ══════════════════════════════════════════════════════════════
step "1/8" "System aktualisieren"
# ══════════════════════════════════════════════════════════════
apt-get update -qq
apt-get upgrade -y -qq
ok "System aktuell"

# ══════════════════════════════════════════════════════════════
step "2/8" "Pakete installieren"
# ══════════════════════════════════════════════════════════════
PAKETE=(
  python3 python3-pip python3-venv python3-pil
  git
  xorg openbox x11-xserver-utils unclutter
  plymouth
  fonts-noto-core fonts-noto-extra
  alsa-utils
  python3-pygame
  swig
  liblgpio-dev
)

# Chromium: Name unterscheidet sich je nach OS-Version
if apt-cache show chromium &>/dev/null; then
  PAKETE+=(chromium)
else
  PAKETE+=(chromium-browser)
fi

# Pakete einzeln installieren – fehlende überspringen statt abbrechen
FEHLEND=()
for pkg in "${PAKETE[@]}"; do
  apt-get install -y -qq "$pkg" 2>/dev/null || FEHLEND+=("$pkg")
done

# libgpiod: Paketname je nach Debian-Version unterschiedlich
if apt-cache show libgpiod2 &>/dev/null; then
  apt-get install -y -qq libgpiod2 2>/dev/null || true
elif apt-cache show libgpiod3 &>/dev/null; then
  apt-get install -y -qq libgpiod3 2>/dev/null || true
fi

[ ${#FEHLEND[@]} -gt 0 ] && info "Übersprungen (nicht verfügbar): ${FEHLEND[*]}"
ok "Pakete installiert"

# Chromium-Binary ermitteln
if command -v chromium &>/dev/null; then
  CHROMIUM_BIN="chromium"
elif command -v chromium-browser &>/dev/null; then
  CHROMIUM_BIN="chromium-browser"
else
  err "Chromium nicht gefunden"
fi
ok "Chromium: $CHROMIUM_BIN"

# ══════════════════════════════════════════════════════════════
step "3/8" "Repository einrichten"
# ══════════════════════════════════════════════════════════════
if [ -d "$INSTALL_DIR/.git" ]; then
  info "Repository vorhanden – wird aktualisiert..."
  cd "$INSTALL_DIR"
  sudo -u "$PI_USER" git fetch origin -q
  sudo -u "$PI_USER" git checkout "$BRANCH" -q
  sudo -u "$PI_USER" git pull origin "$BRANCH" -q
  ok "Repository aktualisiert ($(git rev-parse --short HEAD))"
else
  info "Repository wird geklont..."
  sudo -u "$PI_USER" git clone --branch "$BRANCH" "$REPO" "$INSTALL_DIR" -q
  ok "Repository geklont"
fi

# ══════════════════════════════════════════════════════════════
step "4/8" "Python-Umgebung einrichten"
# ══════════════════════════════════════════════════════════════
cd "$INSTALL_DIR"
if [ ! -d "env" ]; then
  sudo -u "$PI_USER" python3 -m venv env
fi
sudo -u "$PI_USER" env/bin/pip install -q --upgrade pip
sudo -u "$PI_USER" env/bin/pip install -q -r requirements.txt
sudo -u "$PI_USER" env/bin/pip install -q pillow qrcode[pil] requests
ok "Python-Umgebung bereit"

# ══════════════════════════════════════════════════════════════
step "5/8" "Systemd-Dienste einrichten"
# ══════════════════════════════════════════════════════════════

# Flask-Server
cat > /etc/systemd/system/schlagfertig.service << EOF
[Unit]
Description=Schlagfertig Quiz Server
After=network.target

[Service]
Type=simple
User=$PI_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/env/bin/python server.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Buzzer-Display (pygame via HDMI/kmsdrm, Fallback dummy)
cat > /etc/systemd/system/schlagfertig-buzzer.service << EOF
[Unit]
Description=Schlagfertig Quiz Buzzer Display
After=network.target schlagfertig.service
Wants=schlagfertig.service

[Service]
User=$PI_USER
WorkingDirectory=$INSTALL_DIR
Environment=SDL_AUDIODRIVER=alsa
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
SupplementaryGroups=video render
ExecStartPre=/bin/sleep 10
ExecStart=$INSTALL_DIR/env/bin/python $INSTALL_DIR/quiz_buzzer.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable schlagfertig.service
systemctl enable schlagfertig-buzzer.service
ok "Dienste aktiviert (schlagfertig + schlagfertig-buzzer)"

# .env-Datei anlegen falls noch nicht vorhanden (Platzhalter für API-Keys)
ENV_DATEI="$INSTALL_DIR/.env"
if [ ! -f "$ENV_DATEI" ]; then
  cat > "$ENV_DATEI" << 'ENVEOF'
# Schlagfertig API-Keys
# Supabase anon key: Supabase Dashboard → Project Settings → API → anon public
SUPABASE_ANON_KEY=
ENVEOF
  chown "$PI_USER:$PI_USER" "$ENV_DATEI"
  ok ".env-Datei angelegt (bitte SUPABASE_ANON_KEY eintragen)"
else
  ok ".env-Datei bereits vorhanden"
fi

# sudo-Rechte für Server-interne Befehle (Update, Neustart, Shutdown)
echo "$PI_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart schlagfertig, /sbin/reboot, /sbin/shutdown, /sbin/halt" \
  > /etc/sudoers.d/schlagfertig
chmod 440 /etc/sudoers.d/schlagfertig
ok "sudo-Rechte konfiguriert"

# ══════════════════════════════════════════════════════════════
step "6/8" "Plymouth-Splashscreen erstellen"
# ══════════════════════════════════════════════════════════════

THEME_DIR="/usr/share/plymouth/themes/schlagfertig"
mkdir -p "$THEME_DIR"

# Logo-PNG mit Python/PIL generieren
python3 << 'PYEOF'
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1920, 1080
BG    = (8, 8, 15, 255)
WHITE = (255, 255, 255, 255)
RED   = (226, 75, 74, 255)

img  = Image.new('RGBA', (W, H), BG)
draw = ImageDraw.Draw(img)

# Schriftart suchen
font_paths = [
    '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
]
font = None
for fp in font_paths:
    if os.path.exists(fp):
        try:
            font = ImageFont.truetype(fp, 96)
            break
        except Exception:
            pass
if font is None:
    font = ImageFont.load_default()

t1, t2 = "SCHLAG", "FERTIG"
b1 = draw.textbbox((0, 0), t1, font=font)
b2 = draw.textbbox((0, 0), t2, font=font)
w1, h1 = b1[2]-b1[0], b1[3]-b1[1]
w2, h2 = b2[2]-b2[0], b2[3]-b2[1]
gap   = 10
total = w1 + gap + w2
x = (W - total) // 2
y = (H - max(h1, h2)) // 2

draw.text((x,        y), t1, font=font, fill=WHITE)
draw.text((x+w1+gap, y), t2, font=font, fill=RED)

out = '/usr/share/plymouth/themes/schlagfertig/logo.png'
img.save(out)
print(f"  Logo gespeichert: {out}  ({W}×{H}px)")
PYEOF

# Plymouth Theme-Datei
cat > "$THEME_DIR/schlagfertig.plymouth" << 'EOF'
[Plymouth Theme]
Name=Schlagfertig
Description=Schlagfertig Quiz Boot Screen
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/schlagfertig
ScriptFile=/usr/share/plymouth/themes/schlagfertig/schlagfertig.script
EOF

# Plymouth-Script (pulsierendes Logo)
cat > "$THEME_DIR/schlagfertig.script" << 'EOF'
logo_img    = Image("logo.png");
logo_sprite = Sprite(logo_img);

fun position_logo()
{
  logo_sprite.SetX(Window.GetWidth()  / 2 - logo_img.GetWidth()  / 2);
  logo_sprite.SetY(Window.GetHeight() / 2 - logo_img.GetHeight() / 2);
}

position_logo();

fun refresh_callback()
{
  t     = Plymouth.GetTime();
  alpha = 0.45 + 0.55 * Math.Sin(t * 1.8);
  logo_sprite.SetOpacity(alpha);
}

Plymouth.SetRefreshFunction(refresh_callback);
EOF

# Initrd neu bauen mit neuem Theme
plymouth-set-default-theme --rebuild-initrd schlagfertig
ok "Plymouth-Theme installiert und aktiviert"

# ══════════════════════════════════════════════════════════════
step "7/8" "Boot konfigurieren (leise + Plymouth)"
# ══════════════════════════════════════════════════════════════

# cmdline.txt – Textausgabe unterdrücken
for CMDLINE in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  [ -f "$CMDLINE" ] || continue
  if ! grep -q "quiet" "$CMDLINE"; then
    sed -i 's/$/ quiet splash loglevel=0 logo.nologo/' "$CMDLINE"
    ok "Quiet boot aktiviert: $CMDLINE"
  else
    ok "Quiet boot bereits aktiv"
  fi
  break
done

# Konsolenausgabe auf tty3 umleiten (weg vom Bildschirm)
for CMDLINE in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  [ -f "$CMDLINE" ] || continue
  if ! grep -q "console=tty3" "$CMDLINE"; then
    sed -i 's/console=tty1/console=tty3/' "$CMDLINE"
  fi
  break
done

ok "Boot konfiguriert"

# ══════════════════════════════════════════════════════════════
step "8/8" "Kiosk-Modus konfigurieren"
# ══════════════════════════════════════════════════════════════

# Autologin auf tty1 (ohne Desktop)
raspi-config nonint do_boot_behaviour B2

# .bash_profile: startx automatisch auf tty1
cat > "/home/$PI_USER/.bash_profile" << 'EOF'
# Schlagfertig: Kiosk-Modus direkt starten
if [[ -z "$DISPLAY" ]] && [[ "$(tty)" == "/dev/tty1" ]]; then
  exec startx -- -nocursor 2>/dev/null
fi
EOF
chown "$PI_USER:$PI_USER" "/home/$PI_USER/.bash_profile"

# .xinitrc: Openbox + Chromium (kein Desktop)
cat > "/home/$PI_USER/.xinitrc" << XIEOF
#!/bin/bash
# Bildschirmschoner + Energiesparmodus deaktivieren
xset s off
xset s noblank
xset -dpms

# Mauszeiger nach 1s ausblenden
unclutter -idle 1 &

# Warten bis Flask-Server bereit ist (max. 30s)
for i in \$(seq 1 30); do
  curl -sf http://localhost:5000/ > /dev/null 2>&1 && break
  sleep 1
done

# Chromium im Kiosk-Modus
exec $CHROMIUM_BIN \\
  --kiosk \\
  --noerrdialogs \\
  --disable-infobars \\
  --disk-cache-size=1 \\
  --disable-features=TranslateUI,Translate \\
  --check-for-update-interval=31536000 \\
  --window-position=0,0 \\
  "$SERVER_URL"
XIEOF
chown "$PI_USER:$PI_USER" "/home/$PI_USER/.xinitrc"
chmod +x "/home/$PI_USER/.xinitrc"

# Alte Autostart-Dateien entfernen
rm -f "/home/$PI_USER/.config/autostart/schlagfertig-display.desktop"
rm -f "/home/$PI_USER/.config/autostart/schlagfertig-game.desktop"

ok "Kiosk konfiguriert"

# ══════════════════════════════════════════════════════════════
echo ""
echo -e "  ${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "  ${BOLD}║  ${GREEN}Setup abgeschlossen!${NC}${BOLD}               ║${NC}"
echo -e "  ${BOLD}║                                      ║${NC}"
echo -e "  ${BOLD}║  Jetzt neu starten:                  ║${NC}"
echo -e "  ${BOLD}║    sudo reboot                       ║${NC}"
echo -e "  ${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""
