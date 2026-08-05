# Schlagfertig – Raspberry Pi Einrichtung

## Displays

| Anschluss | Inhalt | URL |
|-----------|--------|-----|
| **DSI** (eingebaut, 7") | Kiosk-Status + QR-Code | `/display` |
| **HDMI** (TV/Beamer) | Spieler-Anzeige | `/game` |
| **Handy** (WLAN) | Moderator-Panel | `/moderator` |
| **Handy/PC** (WLAN) | Editor | `/editor` |

---

## 1. Server automatisch starten (systemd)

```bash
sudo cp ~/schlagfertig/pi-config/systemd/schlagfertig.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable schlagfertig
sudo systemctl start schlagfertig

# Status prüfen:
sudo systemctl status schlagfertig
```

---

## 2. Chromium auf dem DSI-Display automatisch öffnen

```bash
# Autostart-Verzeichnis anlegen
mkdir -p ~/.config/autostart

# Desktop-Datei kopieren
cp ~/schlagfertig/pi-config/autostart/schlagfertig-display.desktop ~/.config/autostart/

# Start-Skript ausführbar machen
chmod +x ~/schlagfertig/pi-config/start-display.sh
```

Beim nächsten Desktop-Start öffnet sich Chromium automatisch im Kiosk-Modus
und zeigt die Status-/QR-Seite auf dem eingebauten Display.

---

## 3. HDMI-Ausgabe für Spieler aktivieren (optional)

Für einen separaten Fernseher oder Beamer:

```bash
# In start-display.sh den auskommentierten HDMI-Block einkommentieren:
nano ~/schlagfertig/pi-config/start-display.sh
```

Den Block mit `DISPLAY=$HDMI_DISPLAY chromium-browser` einkommentieren.

> **Hinweis**: Für zwei Chromium-Instanzen auf verschiedenen Displays
> braucht man zwei separate X-Server-Instanzen oder Wayland-Outputs.
> Mit dem Raspberry Pi OS (Bookworm, Wayland) am einfachsten mit
> `WAYLAND_DISPLAY=wayland-1` statt `DISPLAY=:1`.

---

## 4. Moderator-Handy verbinden

1. Schlagfertig startet → QR-Code erscheint auf dem eingebauten Display
2. Handy in dasselbe WLAN → QR-Code abscannen
3. Browser öffnet `/moderator` → fertig

Das Handy kann sich jederzeit verbinden und wieder trennen.
Der Moderator kann alternativ auch das eingebaute Display tippen –
über den Button **„Moderator-Panel"** unten rechts.

---

## 5. Empfohlene Hardware

| Komponente | Empfehlung | Preis |
|-----------|------------|-------|
| Display (DSI) | Raspberry Pi Touch Display 2 (7", offiziell) | ~80 € |
| Raspberry Pi | Pi 5 (4 GB) | ~70 € |
| Gehäuse | Raspberry Pi Case for Touch Display 2 | ~15 € |
| SD-Karte | 32 GB Class 10 | ~10 € |

**Alternativ** (günstiger): Waveshare 5" DSI (~35 €) oder 7" DSI (~55 €).

---

## Bedienung zusammengefasst

```
Eingebaut-Display (7" DSI)
  ├── Idle-State:  QR-Code + Netzwerk-Info + Link zu /setup
  ├── Spiel läuft: Frage, Buzzer-Warteschlange, Punktestand
  └── Sieger:      Gewinner-Anzeige mit Tabelle

Moderator-Handy (beliebig per WLAN)
  ├── /moderator → Vollständiges Moderator-Panel
  └── Frei beweglich im Raum

HDMI (optional)
  └── /game → Spieler-Anzeige für TV/Beamer
```
