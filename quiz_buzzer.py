#!/usr/bin/env python3
"""
Schlagfertig – Quiz Buzzer
Fixes: MC Antworten, Sieger, Punktestand, schwarzer Übergang
"""
try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    try:
        import rpi_lgpio as GPIO  # Drop-in Ersatz für Pi 5
        print("Hinweis: RPi.GPIO nicht verfügbar – nutze rpi-lgpio")
    except ImportError:
        print("WARNUNG: Weder RPi.GPIO noch rpi-lgpio verfügbar. Buzzer deaktiviert.")
        GPIO = None

import pygame
import json, time, sys, os, threading, atexit, signal, subprocess
import socketio as sio_client
from queue import Queue

_beamer_modus = False
_beamer_modus_wechsel = None  # 'start' oder 'stop' – wird im Hauptloop verarbeitet

def _sigusr1(signum, frame):
    global _beamer_modus, _beamer_modus_wechsel
    _beamer_modus = True
    _beamer_modus_wechsel = 'start'

def _sigusr2(signum, frame):
    global _beamer_modus, _beamer_modus_wechsel
    _beamer_modus = False
    _beamer_modus_wechsel = 'stop'

signal.signal(signal.SIGUSR1, _sigusr1)
signal.signal(signal.SIGUSR2, _sigusr2)
try:
    from PIL import Image, ImageSequence
    _PIL_VERFUEGBAR = True
except ImportError:
    _PIL_VERFUEGBAR = False
    print("Hinweis: Pillow nicht installiert – GIFs werden nur als Standbild angezeigt.")

KONFIG_DATEI = os.path.join(os.path.dirname(__file__), "quiz_config.json")
STATE_DATEI  = os.path.join(os.path.dirname(__file__), ".spiel_state")
PID_DATEI    = os.path.join(os.path.dirname(__file__), ".buzzer.pid")

# ─────────────────────────────────────────────
#  EINZELINSTANZ (verhindert Doppelstart beim Boot)
# ─────────────────────────────────────────────
def _prozess_laeuft(pid):
    """True, wenn ein Prozess mit dieser PID existiert."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False        # Prozess gibt es nicht mehr
    except PermissionError:
        return True         # existiert, gehört aber anderem User
    return True

def pruefe_einzelinstanz():
    """Beendet sich selbst, wenn bereits eine Instanz läuft.
    Fängt auch verwaiste PID-Files nach einem Absturz ab."""
    if os.path.exists(PID_DATEI):
        try:
            with open(PID_DATEI) as f:
                alt_pid = int(f.read().strip())
        except (ValueError, OSError):
            alt_pid = None
        if alt_pid and alt_pid != os.getpid() and _prozess_laeuft(alt_pid):
            print(f"Schlagfertig läuft bereits (PID {alt_pid}) – Doppelstart verhindert.")
            sys.exit(0)
        # verwaiste/ungültige Datei -> wird gleich überschrieben
    with open(PID_DATEI, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(entferne_pid)

def entferne_pid():
    """PID-File nur entfernen, wenn es uns gehört."""
    try:
        with open(PID_DATEI) as f:
            if int(f.read().strip()) == os.getpid():
                os.remove(PID_DATEI)
    except (ValueError, OSError):
        pass

# ─────────────────────────────────────────────
#  WEBSOCKET CLIENT
# ─────────────────────────────────────────────
sio = sio_client.Client(reconnection=True, reconnection_attempts=0)
ws_verbunden = False
befehle = Queue()
test_modus = False   # Buzzer-Test: meldet jeden rohen Tastendruck an die App

@sio.event
def connect():
    global ws_verbunden
    ws_verbunden = True
    print("WebSocket verbunden!")

@sio.event
def disconnect():
    global ws_verbunden
    ws_verbunden = False
    print("WebSocket getrennt – versuche erneut...")

@sio.on('zeige_frage')
def on_zeige_frage(data): befehle.put(('zeige_frage', data))

@sio.on('zeige_ergebnis')
def on_zeige_ergebnis(data): befehle.put(('zeige_ergebnis', data))

@sio.on('zeige_mc_auswahl')
def on_mc_auswahl(data): befehle.put(('zeige_mc_auswahl', data))

@sio.on('zeige_mc_aufloesen')
def on_mc_aufloesen(data): befehle.put(('zeige_mc_aufloesen', data))

@sio.on('zeige_punktestand')
def on_punktestand(data): befehle.put(('zeige_punktestand', data))

@sio.on('zeige_sieger')
def on_sieger(data): befehle.put(('zeige_sieger', data))

@sio.on('buzzer_freigeben')
def on_freigeben(): befehle.put(('buzzer_freigeben', {}))

@sio.on('zeige_meme')
def on_zeige_meme(data): befehle.put(('zeige_meme', data))

@sio.on('state_update')
def on_state(data): befehle.put(('state_update', data))

@sio.on('test_start')
def on_test_start():
    global test_modus
    test_modus = True
    print("Buzzer-Test gestartet")

@sio.on('test_stop')
def on_test_stop():
    global test_modus
    test_modus = False
    print("Buzzer-Test beendet")

def verbinde_websocket():
    while True:
        try:
            if not ws_verbunden:
                sio.connect('http://localhost:5000')
                sio.wait()
        except Exception as e:
            print(f"WS Fehler: {e}")
        time.sleep(3)

# ─────────────────────────────────────────────
#  HILFSFUNKTIONEN
# ─────────────────────────────────────────────
def lade_konfig():
    if not os.path.exists(KONFIG_DATEI):
        print("FEHLER: quiz_config.json nicht gefunden!")
        sys.exit(1)
    with open(KONFIG_DATEI, "r", encoding="utf-8") as f:
        return json.load(f)

def schreibe_state(modus):
    with open(STATE_DATEI, "w") as f: f.write(modus)

def hex_zu_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def dunkler(rgb, f=0.35):
    return tuple(int(c * f) for c in rgb)

def lade_foto(spieler, groesse=96):
    foto_b64 = spieler.get("foto", "")
    if not foto_b64 or not foto_b64.startswith("data:image"):
        return None
    try:
        import base64, io
        header, data = foto_b64.split(",", 1)
        img_bytes = base64.b64decode(data)
        img_io = io.BytesIO(img_bytes)
        surf = pygame.image.load(img_io).convert_alpha()
        surf = pygame.transform.smoothscale(surf, (groesse, groesse))
        kreis = pygame.Surface((groesse, groesse), pygame.SRCALPHA)
        pygame.draw.circle(kreis, (255,255,255,255), (groesse//2, groesse//2), groesse//2)
        surf.blit(kreis, (0,0), special_flags=pygame.BLEND_RGBA_MIN)
        return surf
    except Exception as e:
        print(f"Foto-Fehler: {e}")
        return None

_foto_cache = {}

# ─────────────────────────────────────────────
#  SOUND
# ─────────────────────────────────────────────
sounds_cache = {}

def init_sound():
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        print("Sound initialisiert!")
    except Exception as e:
        print(f"Sound Fehler: {e}")

def spiele_sound(dateiname):
    if not dateiname: return
    try:
        pfad = os.path.join(os.path.dirname(__file__), dateiname)
        if not os.path.exists(pfad): return
        if dateiname not in sounds_cache:
            sounds_cache[dateiname] = pygame.mixer.Sound(pfad)
        sounds_cache[dateiname].play()
    except Exception as e:
        print(f"Sound Wiedergabe Fehler: {e}")
def gpio_setup(spieler):
    if not GPIO: return
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for s in spieler:
            if s.get("gpio"):
                GPIO.setup(s["gpio"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except Exception as e:
        print(f"GPIO-Setup-Fehler: {e}")

def gpio_cleanup():
    if not GPIO: return
    try: GPIO.cleanup()
    except: pass

def gpio_lese(pin):
    """Liest einen GPIO-Pin; gibt GPIO.HIGH zurück wenn GPIO nicht verfügbar."""
    if not GPIO: return 1  # HIGH = nicht gedrückt
    try: return GPIO.input(pin)
    except: return 1

# ─────────────────────────────────────────────
#  DISPLAY
# ─────────────────────────────────────────────
WEISS  = (255, 255, 255)
DUNKEL = (18,  18,  28)
ROT    = (230, 57,  70)
SCHWARZ = (0, 0, 0)

# ═══ THEME SYSTEM ═══
_BASIS_THEME = {
    'name': 'Standard',
    'bg_color': (13, 13, 23),
    'text_color': (255, 255, 255),
    'accent_color': (100, 150, 255),
    'success_color': (30, 200, 90),
    'error_color': (230, 60, 60),
    'popup_alpha': 140,
    'neon_colors': [
        (0, 220, 255),      # Cyan
        (255, 80, 180),     # Pink
        (57, 255, 20),      # Green
        (255, 230, 0)       # Yellow
    ]
}
THEMES = {
    'frei': _BASIS_THEME,
    'mc':   _BASIS_THEME,
}

current_theme = None
current_modus = 'frei'

SF_GR = SF_MI = SF_KL = SF_EMOJI = None
BR = HO = 0
screen = None
spieler_map_global = {}
frame_counter = 0

def set_modus_theme(modus):
    """Setzt das Theme basierend auf Spielmodus"""
    global current_theme, current_modus
    current_modus = modus
    current_theme = THEMES.get(modus, THEMES['frei'])

def zeichne_neon_button(x, y, w, h, text, farbe, buchstabe=None, selected=False, pulsing=False):
    """Zeichnet einen super-simplen Neon-Button ohne teure Effekte"""
    # Button-Body - direkt gezeichnet
    pygame.draw.rect(screen, farbe, (x - w//2, y - h//2, w, h), border_radius=12)

    # Dicker Neon-Border
    border_width = 4 if selected else 2
    pygame.draw.rect(screen, (255, 255, 255) if selected else farbe, (x - w//2, y - h//2, w, h), border_radius=12, width=border_width)

    # Text
    txt_color = (0, 0, 0) if farbe == (255, 255, 0) else (255, 255, 255)
    lbl = SF_KL.render(f"{buchstabe}", True, txt_color)
    screen.blit(lbl, (x - w//2 + 16, y - lbl.get_height()//2))

    txt = SF_KL.render(text[:18], True, txt_color)
    screen.blit(txt, (x - w//2 + 60, y - txt.get_height()//2))

def display_setup():
    global SF_GR, SF_MI, SF_KL, SF_EMOJI, BR, HO, screen
    drivers = []
    if os.environ.get('DISPLAY'):
        drivers.append('x11')
    drivers.extend(['kmsdrm', 'dummy'])
    for driver in drivers:
        try:
            os.environ['SDL_VIDEODRIVER'] = driver
            pygame.init()
            if not pygame.display.get_init():
                raise Exception("Display-Subsystem nicht initialisiert")
            info = pygame.display.Info()
            w, h = info.current_w, info.current_h
            if w <= 0 or h <= 0:
                w, h = 1920, 1080
            screen = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
            BR, HO = w, h
            print(f"Display: {driver} {BR}x{HO}")
            break
        except Exception as e:
            print(f"Display Fehler ({driver}): {e}")
            pygame.quit()
    pygame.display.set_caption("Schlagfertig")
    SF_GR = pygame.font.SysFont("DejaVu Sans", 96, bold=True)
    SF_MI = pygame.font.SysFont("DejaVu Sans", 56, bold=True)
    SF_KL = pygame.font.SysFont("DejaVu Sans", 32)
    # Emoji Schriftart
    try:
        SF_EMOJI = pygame.font.Font("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 48)
    except:
        SF_EMOJI = SF_MI

def blit_mitte(surf, y):
    screen.blit(surf, (BR//2 - surf.get_width()//2, y))

def zeige_schwarz():
    """Schwarzer Bildschirm als Übergang"""
    screen.fill(SCHWARZ)
    pygame.display.flip()

def zeichne_kachel(s, pkt, x, y, bw, bh, highlight=False):
    farbe = hex_zu_rgb(s["farbe"])
    r = 6 if highlight else 0
    pygame.draw.rect(screen, dunkler(farbe,.45), (x,y,bw,bh), border_radius=18)
    pygame.draw.rect(screen, farbe, (x+r,y+r,bw-2*r,bh-2*r), border_radius=14)
    mx = x + bw//2
    kr = 48
    foto_surf = _foto_cache.get(s["nr"])
    if foto_surf is None and s.get("foto"):
        foto_surf = lade_foto(s, groesse=kr*2)
        _foto_cache[s["nr"]] = foto_surf
    if foto_surf:
        screen.blit(foto_surf, (mx - kr, y + 68 - kr))
    else:
        pygame.draw.circle(screen, farbe, (mx, y+68), kr)
        ini_s = SF_GR.render(s["name"][0].upper(), True, WEISS)
        screen.blit(ini_s, (mx - ini_s.get_width()//2, y+68 - ini_s.get_height()//2))
    ns = SF_KL.render(s["name"], True, WEISS)
    screen.blit(ns, (mx - ns.get_width()//2, y+130))
    ps = SF_GR.render(str(pkt), True, WEISS)
    screen.blit(ps, (mx - ps.get_width()//2, y+168))
    ls = SF_KL.render("Punkte", True, (210,210,210))
    screen.blit(ls, (mx - ls.get_width()//2, y+268))

def zeige_gpio_test(spieler, do_flip=True):
    """GPIO-Test-Bildschirm: zeigt Live-Status aller konfigurierten Pins."""
    screen.fill((10, 10, 20))
    titel = SF_MI.render("GPIO-TEST-MODUS", True, (226, 75, 74))
    blit_mitte(titel, 30)
    hint = SF_KL.render("Drücke einen Buzzer – sieh welcher Pin reagiert  |  'T' zum Beenden", True, (120, 120, 140))
    blit_mitte(hint, 110)

    n = len(spieler)
    kw, kh = min(240, (BR - 80) // max(n, 1) - 14), 200
    gx = (BR - (n * kw + (n - 1) * 14)) // 2
    gy = HO // 2 - kh // 2

    for i, s in enumerate(spieler):
        pin = s.get("gpio", "–")
        farbe = hex_zu_rgb(s["farbe"])
        x, y = gx + i * (kw + 14), gy

        gedr = False
        if GPIO and pin and isinstance(pin, int):
            try:
                gedr = (GPIO.input(pin) == 0)  # LOW = gedrückt
            except: pass

        rand_farbe = (57, 255, 20) if gedr else (60, 60, 80)
        pygame.draw.rect(screen, dunkler(farbe, .4), (x, y, kw, kh), border_radius=18)
        pygame.draw.rect(screen, rand_farbe, (x, y, kw, kh), border_radius=18, width=4 if gedr else 2)

        name_s = SF_KL.render(s["name"], True, WEISS)
        screen.blit(name_s, (x + kw // 2 - name_s.get_width() // 2, y + 20))

        pin_txt = SF_MI.render(f"BCM {pin}", True, (57, 255, 20) if gedr else (200, 200, 220))
        screen.blit(pin_txt, (x + kw // 2 - pin_txt.get_width() // 2, y + 70))

        status = SF_KL.render("● GEDRÜCKT" if gedr else "○ offen", True, (57, 255, 20) if gedr else (100, 100, 120))
        screen.blit(status, (x + kw // 2 - status.get_width() // 2, y + 140))

    if do_flip: pygame.display.flip()

def zeige_wartebildschirm(puls, do_flip=True):
    screen.fill(DUNKEL)
    logo1 = SF_GR.render("SCHLAG", True, WEISS)
    logo2 = SF_GR.render("FERTIG", True, ROT)
    gesamt_b = logo1.get_width() + logo2.get_width() + 10
    x = BR//2 - gesamt_b//2
    screen.blit(logo1, (x, HO//2 - 160))
    screen.blit(logo2, (x + logo1.get_width() + 10, HO//2 - 160))
    sub = SF_KL.render("Quiz Buzzer System", True, (100, 100, 120))
    blit_mitte(sub, HO//2 - 60)
    hell = int(80 + puls * 80)
    warte = SF_MI.render("Warten auf Moderator...", True, (hell, hell, hell+20))
    blit_mitte(warte, HO//2)
    hint = SF_KL.render("http://schlagfertig.local:5000", True, (40, 40, 60))
    blit_mitte(hint, HO - 54)
    if do_flip: pygame.display.flip()

def zeige_startbildschirm(spieler, punkte, highlight_nr=None):
    screen.fill(DUNKEL)
    blit_mitte(SF_GR.render("SCHLAGFERTIG", True, WEISS), 34)
    n = len(spieler)
    bw = min(255, (BR-80)//n - 14)
    bh = 314
    gx = (BR - (n*bw + (n-1)*14))//2
    gy = HO//2 - bh//2 + 28
    for i, s in enumerate(spieler):
        pkt = punkte.get(s["nr"], punkte.get(str(s["nr"]), 0))
        zeichne_kachel(s, pkt, gx+i*(bw+14), gy, bw, bh, highlight=s["nr"]==highlight_nr)
    pygame.display.flip()

def zeige_frage_screen(frage_dict, nr, gesamt, spielmodus='frei', mc_gewaehlt=None, mc_aufgeloest=False, do_flip=True, mc_highlight_falsch=None, mc_highlight_richtig=None):
    # Theme-basierte Hintergrundfarbe
    theme = current_theme or THEMES['frei']
    screen.fill(theme['bg_color'])

    if not frage_dict:
        if do_flip: pygame.display.flip()
        return

    # ── HEADER BAR ────────────────────────────────────────────────
    bar_h = 86
    bar = pygame.Surface((BR, bar_h), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 110))
    screen.blit(bar, (0, 0))
    pygame.draw.line(screen, theme['accent_color'], (0, bar_h), (BR, bar_h), 2)

    # "FRAGE X / Y" – zentriert
    nr_surf = SF_KL.render(f"FRAGE  {nr}  /  {gesamt}", True, theme['accent_color'])
    blit_mitte(nr_surf, bar_h // 2 - nr_surf.get_height() // 2)

    # Kategorie – links, gedimmt
    kat = frage_dict.get('kategorie', '')
    if kat:
        kat_surf = SF_KL.render(kat.upper(), True, (155, 155, 180))
        screen.blit(kat_surf, (24, bar_h // 2 - kat_surf.get_height() // 2))

    # Schwierigkeit – rechts als farbiges Pill
    schwier = frage_dict.get('schwierigkeit', '').lower()
    sw_farben = {'leicht': (46, 204, 113), 'mittel': (230, 126, 34), 'schwer': (231, 76, 60)}
    sw_farbe = sw_farben.get(schwier, (100, 100, 130))
    if schwier:
        sw_surf = SF_KL.render(schwier.capitalize(), True, (255, 255, 255))
        pw = sw_surf.get_width() + 30
        ph = sw_surf.get_height() + 12
        pygame.draw.rect(screen, sw_farbe, (BR - pw - 20, bar_h // 2 - ph // 2, pw, ph), border_radius=ph // 2)
        screen.blit(sw_surf, (BR - pw - 20 + 15, bar_h // 2 - ph // 2 + 6))

    # ── FRAGE TEXT ────────────────────────────────────────────────
    istMC = spielmodus == 'mc' or frage_dict.get('modus') == 'mc'
    worte = frage_dict.get("frage","").split()
    zeilen, z = [], []
    for w in worte:
        p = " ".join(z+[w])
        if SF_MI.size(p)[0] > BR-160: zeilen.append(" ".join(z)); z=[w]
        else: z.append(w)
    if z: zeilen.append(" ".join(z))

    y_start = HO//2 - (len(zeilen)*63)//2 - (140 if istMC else 0)
    for line in zeilen:
        blit_mitte(SF_MI.render(line, True, theme['text_color']), y_start)
        y_start += 63

    # ── MC ANTWORTEN ──────────────────────────────────────────────
    if istMC and frage_dict.get("antworten_mc") and len(frage_dict["antworten_mc"]) == 4:
        mc = frage_dict["antworten_mc"]
        richtig_idx = frage_dict.get("richtige_antwort_index", 0)
        neon_farben = [(0, 255, 255), (255, 0, 150), (57, 255, 20), (255, 255, 0)]
        buchst = ["A","B","C","D"]
        kw = (BR-140)//2
        kh = 100
        positionen = [
            (70, HO-240), (70+kw+30, HO-240),
            (70, HO-130), (70+kw+30, HO-130)
        ]
        for i, (ax, ay) in enumerate(positionen):
            if i >= len(mc): break
            farbe = neon_farben[i]
            if mc_highlight_falsch is not None or mc_highlight_richtig is not None:
                if i == mc_highlight_richtig:
                    pygame.draw.rect(screen, (20, 180, 50), (ax, ay, kw, kh), border_radius=14)
                    pygame.draw.rect(screen, (57, 255, 20), (ax, ay, kw, kh), border_radius=14, width=4)
                elif i == mc_highlight_falsch:
                    pygame.draw.rect(screen, (180, 20, 50), (ax, ay, kw, kh), border_radius=14)
                    pygame.draw.rect(screen, (255, 80, 0), (ax, ay, kw, kh), border_radius=14, width=4)
                else:
                    pygame.draw.rect(screen, (40,40,50), (ax,ay,kw,kh), border_radius=14)
            elif mc_aufgeloest:
                if i == richtig_idx:
                    pygame.draw.rect(screen, (20, 180, 50), (ax, ay, kw, kh), border_radius=14)
                    pygame.draw.rect(screen, (57, 255, 20), (ax, ay, kw, kh), border_radius=14, width=4)
                elif i == mc_gewaehlt:
                    pygame.draw.rect(screen, (180, 20, 50), (ax, ay, kw, kh), border_radius=14)
                    pygame.draw.rect(screen, (255, 0, 150), (ax, ay, kw, kh), border_radius=14, width=4)
                else:
                    pygame.draw.rect(screen, (40,40,50), (ax,ay,kw,kh), border_radius=14)
            elif mc_gewaehlt == i:
                pygame.draw.rect(screen, farbe, (ax,ay,kw,kh), border_radius=14)
                pygame.draw.rect(screen, (255,255,255), (ax,ay,kw,kh), border_radius=14, width=4)
            else:
                pygame.draw.rect(screen, farbe, (ax,ay,kw,kh), border_radius=14)
            txt_farbe = (0,0,0) if farbe == (255, 255, 0) else (255,255,255)
            lbl = SF_MI.render(f"{buchst[i]}", True, txt_farbe)
            ant = SF_KL.render(mc[i], True, txt_farbe)
            screen.blit(lbl, (ax+18, ay+kh//2-lbl.get_height()//2))
            screen.blit(ant, (ax+60, ay+kh//2-ant.get_height()//2))

    # ── BUZZER HINWEIS ────────────────────────────────────────────
    if not istMC:
        txt_surf = SF_KL.render("  Buzzer drücken!", True, theme['success_color'])
        # Emoji separat mit SF_EMOJI rendern (unterstützt Farb-Emoji)
        em_font = SF_EMOJI if (SF_EMOJI and SF_EMOJI is not SF_MI) else None
        em_surf = em_font.render("🔔", True, theme['success_color']) if em_font else None
        if em_surf:
            total_w = em_surf.get_width() + txt_surf.get_width()
            x0 = BR // 2 - total_w // 2
            y0 = HO - 62
            screen.blit(em_surf, (x0, y0 + txt_surf.get_height() // 2 - em_surf.get_height() // 2))
            screen.blit(txt_surf, (x0 + em_surf.get_width(), y0))
        else:
            blit_mitte(txt_surf, HO - 62)

    if do_flip: pygame.display.flip()

def zeige_spieler_dran_screen(spieler_obj, text="Du darfst antworten!", warteschlange=[], frage_dict=None, frage_nr=1, frage_gesamt=1, spielmodus='frei', mc_gewaehlt=None, timer_rest=None, do_flip=True):
    """Zeigt Buzzer-Banner über der Frage wer dran ist"""
    farbe = hex_zu_rgb(spieler_obj["farbe"])

    # Frage im Hintergrund (gedimmt)
    if frage_dict:
        zeige_frage_screen(frage_dict, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, False, do_flip=False)
    else:
        screen.fill(DUNKEL)

    # Dunkles Overlay über der Frage
    overlay = pygame.Surface((BR, HO), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    # ── VOLLE BREITE BANNER ────────────────────────────────────────
    bh = 200  # Banner-Höhe
    # Farbiger Hintergrund: satt genug um die Spielerfarbe zu zeigen
    pygame.draw.rect(screen, dunkler(farbe, 0.55), (0, 0, BR, bh))
    # Hellerer Streifen am oberen Rand
    pygame.draw.rect(screen, dunkler(farbe, 0.7), (0, 0, BR, 8))
    # Leuchtender Streifen am unteren Rand des Banners
    pygame.draw.rect(screen, farbe, (0, bh - 6, BR, 6))

    # Avatar (links im Banner)
    kr = 68
    cx = 90
    cy = bh // 2
    foto_surf = _foto_cache.get(spieler_obj["nr"])
    if foto_surf is None and spieler_obj.get("foto"):
        foto_surf = lade_foto(spieler_obj, groesse=kr*2)
        _foto_cache[spieler_obj["nr"]] = foto_surf
    if foto_surf:
        fs = pygame.transform.smoothscale(foto_surf, (kr*2, kr*2))
        screen.blit(fs, (cx - kr, cy - kr))
    else:
        pygame.draw.circle(screen, dunkler(farbe, 0.5), (cx, cy), kr + 4)
        pygame.draw.circle(screen, farbe, (cx, cy), kr)
        ini_font = pygame.font.SysFont("DejaVu Sans", 56, bold=True)
        ini = ini_font.render(spieler_obj["name"][0].upper(), True, WEISS)
        screen.blit(ini, (cx - ini.get_width()//2, cy - ini.get_height()//2))

    # Name (groß)
    name_font = pygame.font.SysFont("DejaVu Sans", 62, bold=True)
    name_surf = name_font.render(spieler_obj["name"], True, WEISS)
    name_x = cx + kr + 20
    name_y = cy - name_surf.get_height() - 6
    screen.blit(name_surf, (name_x, name_y))

    # Subtext "Du darfst antworten!"
    sub_surf = SF_MI.render(text, True, farbe)
    screen.blit(sub_surf, (name_x, cy + 6))

    # Countdown-Timer (wenn aktiv) – innerhalb des Banners
    if timer_rest is not None:
        timer_y = bh - 38
        timer_w = BR - 200
        timer_bar_h = 12
        timer_x = cx + kr + 20
        pygame.draw.rect(screen, (30, 30, 50), (timer_x, timer_y, timer_w, timer_bar_h), border_radius=6)
        if timer_rest > 0:
            fill_ratio = min(1.0, timer_rest / (zeitlimit_sek or 30))
            fill_w = int(timer_w * fill_ratio)
            t_farbe = (int(255*(1-fill_ratio)), int(255*fill_ratio), 40)
            pygame.draw.rect(screen, t_farbe, (timer_x, timer_y, fill_w, timer_bar_h), border_radius=6)
        sek_font = pygame.font.SysFont("DejaVu Sans", 22, bold=True)
        sek_surf = sek_font.render(f"{max(0, int(timer_rest))}s", True, WEISS)
        screen.blit(sek_surf, (timer_x + timer_w + 10, timer_y - 4))

    # Warteschlange (weitere Spieler) unterhalb des Banners
    if len(warteschlange) > 1:
        rang_icons = ["1.", "2.", "3.", "4.", "5.", "6."]
        wq_y = bh + 18
        for i, e in enumerate(warteschlange):
            if i == 0: continue
            s_nr = e.get('nr')
            s_ms = e.get('ms', 0)
            s = spieler_map_global.get(s_nr)
            s_name = s['name'] if s else f"Spieler {s_nr}"
            ms_txt = f"  +{s_ms} ms" if s_ms else ""
            wq_txt = SF_KL.render(f"{rang_icons[i]} {s_name}{ms_txt}", True, (200, 200, 200))
            screen.blit(wq_txt, (BR//2 - wq_txt.get_width()//2, wq_y))
            wq_y += 36

    if do_flip: pygame.display.flip()

def zeige_richtig_screen(delta, frage_dict=None, frage_nr=1, frage_gesamt=1, spielmodus='frei', mc_gewaehlt=None):
    theme = current_theme or THEMES['frei']
    istMC = spielmodus == 'mc'

    if frage_dict:
        zeige_frage_screen(frage_dict, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, False, do_flip=False)
    else:
        screen.fill(theme['bg_color'])

    overlay = pygame.Surface((BR, HO), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    pw, ph = 560, 280
    px = BR//2 - pw//2
    py = HO//2 - ph//2

    pygame.draw.rect(screen, (10, 120, 40), (px+4, py+4, pw, ph), border_radius=28)
    pygame.draw.rect(screen, theme['success_color'], (px, py, pw, ph), border_radius=28)

    if istMC:
        pygame.draw.rect(screen, theme['success_color'], (px, py, pw, ph), border_radius=28, width=3)

    blit_mitte(SF_GR.render("✓ RICHTIG!", True, WEISS), py+75)
    blit_mitte(SF_MI.render(f"+{delta} Punkte", True, (150,255,150)), py+180)
    pygame.display.flip()

def zeige_falsch_screen(delta, frage_dict=None, frage_nr=1, frage_gesamt=1, spielmodus='frei', mc_gewaehlt=None):
    theme = current_theme or THEMES['frei']
    istMC = spielmodus == 'mc'

    if frage_dict:
        zeige_frage_screen(frage_dict, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, False, do_flip=False)
    else:
        screen.fill(theme['bg_color'])

    overlay = pygame.Surface((BR, HO), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    pw, ph = 560, 280
    px = BR//2 - pw//2
    py = HO//2 - ph//2

    pygame.draw.rect(screen, (140, 20, 20), (px+4, py+4, pw, ph), border_radius=28)
    pygame.draw.rect(screen, theme['error_color'], (px, py, pw, ph), border_radius=28)

    if istMC:
        pygame.draw.rect(screen, theme['error_color'], (px, py, pw, ph), border_radius=28, width=3)

    blit_mitte(SF_GR.render("✗ FALSCH!", True, WEISS), py+75)
    blit_mitte(SF_MI.render(f"−{delta} Punkte", True, (255,150,150)), py+180)
    pygame.display.flip()

def zeige_gewinner_screen(spieler_obj, punkte_wert, warteschlange, spieler_map):
    """Zeigt wer zuerst gebuzzert hat"""
    zeige_spieler_dran_screen(spieler_obj, "Du darfst antworten!")

def zeige_ergebnis_screen(richtig, delta):
    if richtig:
        zeige_richtig_screen(delta)
    else:
        zeige_falsch_screen(delta)

def zeige_punktestand_screen(spieler_liste, punkte, do_flip=True):
    screen.fill(DUNKEL)
    blit_mitte(SF_GR.render("PUNKTESTAND", True, WEISS), 40)
    n = len(spieler_liste)
    bw = min(240, (BR-80)//n - 14)
    bh = 300
    gx = (BR - (n*bw + (n-1)*14))//2
    gy = HO//2 - bh//2 + 30
    # Nach Punkten sortiert anzeigen
    sortiert = sorted(spieler_liste, key=lambda s: punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)), reverse=True)
    rang_labels_pts = ["1.", "2.", "3.", "4.", "5.", "6."]
    rang_farben_pts = [(255, 215, 0), (192, 192, 192), (205, 127, 50)]
    for i, s in enumerate(sortiert):
        pkt = punkte.get(s["nr"], punkte.get(str(s["nr"]), 0))
        zeichne_kachel(s, pkt, gx+i*(bw+14), gy, bw, bh)
        rang_text = rang_labels_pts[i] if i < len(rang_labels_pts) else f"{i+1}."
        rang_f = rang_farben_pts[i] if i < 3 else WEISS
        rang_surf = SF_MI.render(rang_text, True, rang_f)
        screen.blit(rang_surf, (gx+i*(bw+14) + bw//2 - rang_surf.get_width()//2, gy-54))
    if do_flip: pygame.display.flip()

def zeige_sieger_screen(spieler_liste, punkte):
    screen.fill(DUNKEL)

    if not spieler_liste:
        pygame.display.flip()
        return

    sortiert = sorted(spieler_liste,
        key=lambda s: punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)),
        reverse=True)

    rang_farben = [(255, 215, 0), (192, 192, 192), (205, 127, 50)]
    rang_labels  = ["1.", "2.", "3.", "4.", "5.", "6."]

    n = len(sortiert)
    max_pkt = max((punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)) for s in sortiert), default=1) or 1

    # Proportionale Schriftgrößen basierend auf Bildschirmhöhe
    titel_sz = max(28, HO // 8)
    row_sz   = max(14, HO // 16)
    font_titel = pygame.font.SysFont("DejaVu Sans", titel_sz, bold=True)
    font_row   = pygame.font.SysFont("DejaVu Sans", row_sz,   bold=True)
    font_pts   = pygame.font.SysFont("DejaVu Sans", row_sz)

    # Titel
    titel_surf = font_titel.render("SPIELENDE!", True, WEISS)
    blit_mitte(titel_surf, int(HO * 0.03))
    titel_bottom = int(HO * 0.03) + titel_surf.get_height() + int(HO * 0.02)

    # Verfügbare Höhe für Liste
    available_h = HO - titel_bottom - int(HO * 0.02)
    row_h = available_h // n
    kr = max(8, min(row_h // 2 - 6, int(HO * 0.07)))

    pad_l = int(BR * 0.04)

    for i, s in enumerate(sortiert):
        pkt    = punkte.get(s["nr"], punkte.get(str(s["nr"]), 0))
        farbe  = hex_zu_rgb(s["farbe"])
        rang_f = rang_farben[i] if i < 3 else (140, 140, 160)

        y  = titel_bottom + i * row_h
        cy = y + row_h // 2

        # Zeilenhintergrund (leicht eingefärbt für Top-3)
        if i < 3:
            row_bg = pygame.Surface((BR - pad_l * 2, row_h - 4), pygame.SRCALPHA)
            row_bg.fill((*dunkler(farbe, 0.25), 70))
            screen.blit(row_bg, (pad_l, y + 2))

        # Rang-Nummer
        rang_surf = font_pts.render(rang_labels[i], True, rang_f)
        screen.blit(rang_surf, (pad_l, cy - rang_surf.get_height()//2))

        # Avatar-Kreis
        cx_av = pad_l + rang_surf.get_width() + kr + int(BR * 0.015)
        foto_surf = _foto_cache.get(s["nr"])
        if foto_surf is None and s.get("foto"):
            foto_surf = lade_foto(s, groesse=kr * 2)
            _foto_cache[s["nr"]] = foto_surf
        pygame.draw.circle(screen, dunkler(farbe, 0.45), (cx_av, cy), kr + 2)
        pygame.draw.circle(screen, farbe, (cx_av, cy), kr)
        if foto_surf:
            fs = pygame.transform.smoothscale(foto_surf, (kr * 2, kr * 2))
            screen.blit(fs, (cx_av - kr, cy - kr))
        else:
            ini_f = pygame.font.SysFont("DejaVu Sans", max(10, kr), bold=True)
            ini   = ini_f.render(s["name"][0].upper(), True, WEISS)
            screen.blit(ini, (cx_av - ini.get_width()//2, cy - ini.get_height()//2))

        # Name
        name_x   = cx_av + kr + int(BR * 0.02)
        name_surf = font_row.render(s["name"], True, WEISS)
        screen.blit(name_surf, (name_x, cy - name_surf.get_height()//2))

        # Punkte-Balken (rechts)
        bar_x  = int(BR * 0.52)
        bar_w  = int(BR * 0.28)
        bar_h  = max(5, kr // 2)
        bar_y  = cy - bar_h // 2
        pygame.draw.rect(screen, (35, 35, 50), (bar_x, bar_y, bar_w, bar_h), border_radius=bar_h)
        fill_w = int(bar_w * pkt / max_pkt)
        if fill_w > 0:
            pygame.draw.rect(screen, farbe, (bar_x, bar_y, fill_w, bar_h), border_radius=bar_h)

        # Punktzahl
        pkt_surf = font_pts.render(str(pkt), True, rang_f)
        pkt_x    = bar_x + bar_w + int(BR * 0.015)
        screen.blit(pkt_surf, (pkt_x, cy - pkt_surf.get_height()//2))
        pkt_lbl  = font_pts.render(" Pkt", True, (90, 90, 110))
        screen.blit(pkt_lbl, (pkt_x + pkt_surf.get_width(), cy - pkt_lbl.get_height()//2))

    pygame.display.flip()

# ─────────────────────────────────────────────
#  BUZZER THREAD
# ─────────────────────────────────────────────
buzzer_aktiv = True
buzzer_gesperrt = False
buzzer_start_zeit = None
buzzer_warteschlange_lokal = []  # Lokale Kopie der Warteschlange

# Zeitlimit-Einstellungen (kommen mit zeige_frage)
zeitlimit_aktiv = False
zeitlimit_sek = 30

def buzzer_thread(spieler):
    global buzzer_gesperrt, buzzer_start_zeit, buzzer_warteschlange_lokal
    gpio_setup(spieler)

    letzter = {s["nr"]: 1 for s in spieler}  # 1 = HIGH = nicht gedrückt
    erster_buzz_zeit = None

    while buzzer_aktiv:
        for s in spieler:
            if not s.get("gpio"): continue
            jetzt = gpio_lese(s["gpio"])
            if jetzt == 0 and letzter[s["nr"]] == 1:  # LOW = gedrückt
                nr = s["nr"]
                # Buzzer-Test: jeden Druck melden, Spiellogik überspringen
                if test_modus:
                    try:
                        sio.emit('buzzer_test_press', {'nr': nr})
                    except: pass
                    letzter[s["nr"]] = jetzt
                    continue
                # Schon in Warteschlange? Ignorieren
                if any(e['nr'] == nr for e in buzzer_warteschlange_lokal):
                    letzter[s["nr"]] = jetzt
                    continue

                ms = int((time.time() - buzzer_start_zeit) * 1000) if buzzer_start_zeit else 0

                # Erster Buzzer
                if len(buzzer_warteschlange_lokal) == 0:
                    erster_buzz_zeit = time.time()
                    buzzer_gesperrt = True

                # Nur innerhalb von 2 Sekunden nach erstem Buzzer erlauben
                if erster_buzz_zeit is None or (time.time() - erster_buzz_zeit) < 2.0:
                    buzzer_warteschlange_lokal.append({'nr': nr, 'ms': ms})
                    print(f"SPIEL: Buzzer {nr} gedrückt (ms={ms})")
                    try:
                        sio.emit('buzzer_gedrueckt', {'nr': nr, 'ms': ms})
                    except: pass
                    befehle.put(('buzzer_local', {'nr': nr, 'ms': ms}))

            elif jetzt == 1 and letzter[s["nr"]] == 0 and test_modus:
                # Steigende Flanke im Testmodus: Loslassen melden
                try:
                    sio.emit('buzzer_test_release', {'nr': s["nr"]})
                except: pass

            letzter[s["nr"]] = jetzt if s.get("gpio") else 1
        time.sleep(0.001)

# ─────────────────────────────────────────────
#  GIF-ANIMATION HILFSFUNKTION
# ─────────────────────────────────────────────
def lade_gif_frames(pfad):
    """Gibt eine Liste von (pygame.Surface, dauer_ms) zurück – alle Frames eines GIF.
    Fällt auf pygame-Einzelframe zurück wenn Pillow fehlt oder keine Animation vorliegt."""
    max_w = int(BR * 0.88)
    max_h = int(HO * 0.88)

    def skaliere_pil(rgba_img):
        """Skaliert ein Pillow-RGBA-Bild mit LANCZOS (schärfste Qualität)."""
        w, h = rgba_img.size
        if w == 0 or h == 0:
            return rgba_img
        faktor = min(max_w / w, max_h / h)
        new_size = (max(1, int(w * faktor)), max(1, int(h * faktor)))
        return rgba_img.resize(new_size, Image.LANCZOS)

    def skaliere_pygame(surf):
        """Fallback-Skalierung via pygame smoothscale."""
        w, h = surf.get_size()
        if w == 0 or h == 0:
            return surf
        faktor = min(max_w / w, max_h / h)
        return pygame.transform.smoothscale(surf, (max(1, int(w * faktor)), max(1, int(h * faktor))))

    if _PIL_VERFUEGBAR:
        try:
            img = Image.open(pfad)
            frames = []
            for frame in ImageSequence.Iterator(img):
                dur = frame.info.get('duration', 100)
                rgba = skaliere_pil(frame.convert('RGBA'))
                surf = pygame.image.frombuffer(rgba.tobytes(), rgba.size, 'RGBA').convert_alpha()
                frames.append((surf, max(20, dur)))
            if frames:
                return frames
        except Exception as e:
            print(f"GIF-Pillow-Fehler: {e}")

    # Fallback: pygame lädt nur Frame 0
    try:
        surf = pygame.image.load(pfad).convert_alpha()
        return [(skaliere_pygame(surf), 100)]
    except Exception as e:
        print(f"GIF-Pygame-Fehler: {e}")
        return None

# ─────────────────────────────────────────────
#  HAUPTPROGRAMM
# ─────────────────────────────────────────────
def main():
    global buzzer_aktiv, buzzer_gesperrt, buzzer_start_zeit, zeitlimit_aktiv, zeitlimit_sek
    global screen, BR, HO, _beamer_modus_wechsel

    pruefe_einzelinstanz()   # Doppelstart beim Boot abfangen

    konfig = lade_konfig()
    spieler = konfig["spieler"]
    spieler_map = {s["nr"]: s for s in spieler}
    global spieler_map_global
    spieler_map_global = spieler_map

    gpio_setup(spieler)
    display_setup()
    init_sound()
    _foto_cache.clear()
    sounds_config = konfig.get("einstellungen", {}).get("sounds", {})

    # Sofort Wartebildschirm zeigen – kein schwarzer Bildschirm
    screen.fill(DUNKEL)
    logo1 = SF_GR.render("SCHLAG", True, WEISS)
    logo2 = SF_GR.render("FERTIG", True, ROT)
    x = BR//2 - (logo1.get_width() + logo2.get_width() + 10)//2
    screen.blit(logo1, (x, HO//2 - 160))
    screen.blit(logo2, (x + logo1.get_width() + 10, HO//2 - 160))
    warte = SF_MI.render("Warten auf Moderator...", True, (100,100,120))
    screen.blit(warte, (BR//2 - warte.get_width()//2, HO//2))
    hint = SF_KL.render("http://schlagfertig.local:5000", True, (40,40,60))
    screen.blit(hint, (BR//2 - hint.get_width()//2, HO-54))
    pygame.display.flip()
    pygame.event.pump()

    # WebSocket Thread
    ws_thread = threading.Thread(target=verbinde_websocket, daemon=True)
    ws_thread.start()

    # Buzzer Thread
    buz_thread = threading.Thread(target=buzzer_thread, args=(spieler,), daemon=True)
    buz_thread.start()

    # Spielzustand
    modus = "warten"
    aktuelle_frage = None
    frage_nr = 0
    frage_gesamt = 1
    spielmodus = "frei"
    punkte = {s["nr"]: 0 for s in spieler}
    warteschlange = []
    mc_gewaehlt = None
    mc_aufgeloest = False
    letzter_gewinner_nr = None
    puls = 0.0
    puls_richtung = 1
    punktestand_sichtbar = False
    popup_timer = None  # Timer für Pop-up
    buzzer_fenster_offen = False  # 2 Sek Fenster nach erstem Buzzer
    aktive_spieler_liste = spieler  # Wird vom Editor übernommen
    meme_frames = None      # Meme-Board: Liste von (Surface, dauer_ms) – alle GIF-Frames
    meme_bis = 0            # Zeitstempel bis wann das Meme sichtbar bleibt
    meme_frame_idx = 0      # Aktuell angezeigter Frame-Index
    meme_frame_start = 0.0  # Zeitstempel, wann der aktuelle Frame begann

    gpio_test_aktiv = False  # 'T' togglet den GPIO-Test-Screen
    schreibe_state("warten")
    clock = pygame.time.Clock()

    while True:
        # Display-Modus wechseln wenn Signal empfangen wurde
        if _beamer_modus_wechsel == 'start':
            _beamer_modus_wechsel = None
            try:
                # Vollbild freigeben → Chromium bekommt den ganzen Bildschirm
                screen = pygame.display.set_mode((1, 1), 0)
                pygame.display.flip()
            except Exception as e:
                print(f"Beamer-Start Display-Fehler: {e}")
        elif _beamer_modus_wechsel == 'stop':
            _beamer_modus_wechsel = None
            try:
                # Vollbild zurück – xrandr wurde bereits in starte_beamer() gesetzt
                time.sleep(0.3)
                info = pygame.display.Info()
                w, h = info.current_w, info.current_h
                if w <= 0 or h <= 0:
                    w, h = 1920, 1080
                screen = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
                BR, HO = w, h
            except Exception as e:
                print(f"Beamer-Stop Display-Fehler: {e}")

        # Beamer-Modus: Fenster ist 1×1, nur Events leeren
        if _beamer_modus:
            for event in pygame.event.get():
                pass
            clock.tick(10)
            continue

        # Pygame Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                buzzer_aktiv = False
                gpio_cleanup()
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                buzzer_aktiv = False
                gpio_cleanup()
                zeige_schwarz()
                pygame.quit()
                sys.exit()
            # 'T' → GPIO-Test-Modus umschalten (nur im Warten-Modus)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_t and modus == "warten":
                gpio_test_aktiv = not gpio_test_aktiv

        # Befehle verarbeiten
        while not befehle.empty():
            befehl, data = befehle.get()

            if befehl == 'zeige_frage':
                aktuelle_frage = data.get('frage')
                frage_nr = data.get('idx', 0) + 1
                frage_gesamt = data.get('gesamt', 1)
                spielmodus = data.get('spielmodus', 'frei')
                set_modus_theme(spielmodus)  # Theme setzen
                zeitlimit_aktiv = data.get('zeitlimit_aktiv', False)
                zeitlimit_sek = data.get('zeitlimit_sek', 30)
                # Aktive Spieler übernehmen und spieler_map aktualisieren!
                if data.get('aktive_spieler'):
                    aktive_spieler_liste = data.get('aktive_spieler')
                    # spieler_map mit neuen Farben/Namen aktualisieren
                    for s in aktive_spieler_liste:
                        nr = s.get('nr')
                        if nr:
                            spieler_map[nr] = s
                            spieler_map_global[nr] = s
                warteschlange = []
                buzzer_warteschlange_lokal.clear()
                mc_gewaehlt = None
                mc_aufgeloest = False
                buzzer_gesperrt = False
                buzzer_start_zeit = time.time()
                punktestand_sichtbar = False
                modus = "frage"
            elif befehl == 'zeige_mc_auswahl':
                mc_gewaehlt = data.get('idx')
                mc_aufgeloest = False
                if modus == "frage":
                    zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, False)

            elif befehl == 'zeige_mc_aufloesen':
                mc_gewaehlt = data.get('gewaehlt')
                richtig = data.get('richtig', False)
                delta = data.get('delta', 10)
                falsch_idx = data.get('falsch_idx')
                richtig_idx_data = data.get('richtig_idx')
                # Punkte aktualisieren
                p_raw = data.get('punkte', {})
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))
                if richtig:
                    mc_aufgeloest = True
                    spiele_sound(sounds_config.get('richtig'))
                    zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, True)
                    time.sleep(5)
                    modus = "punktestand"
                else:
                    # Falsche Antwort: kein Overlay, nur Sound + Farb-Highlights
                    spiele_sound(sounds_config.get('falsch'))
                    zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus,
                                       mc_gewaehlt, False,
                                       mc_highlight_falsch=falsch_idx,
                                       mc_highlight_richtig=richtig_idx_data)
                    time.sleep(3)
                    warteschlange = data.get('warteschlange', warteschlange)
                    if len(warteschlange) > 0:
                        naechster_nr = warteschlange[0]['nr']
                        naechster = spieler_map.get(naechster_nr)
                        if naechster is None:
                            try:
                                alt = int(naechster_nr) if isinstance(naechster_nr, str) else str(naechster_nr)
                                naechster = spieler_map.get(alt)
                            except (ValueError, TypeError):
                                pass
                        if naechster:
                            letzter_gewinner_nr = naechster_nr
                            popup_timer = time.time()
                            buzzer_fenster_offen = False
                            modus = "gewinner"
                    else:
                        modus = "punktestand"

            elif befehl == 'zeige_ergebnis':
                richtig = data.get('richtig', False)
                delta = data.get('delta', 10)
                p_raw = data.get('punkte', {})
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))

                if richtig:
                    spiele_sound(sounds_config.get('richtig'))
                    zeige_richtig_screen(delta, aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt)
                    time.sleep(3)
                    modus = "punktestand"
                else:
                    spiele_sound(sounds_config.get('falsch'))
                    zeige_falsch_screen(delta, aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt)
                    time.sleep(3)
                    warteschlange = data.get('warteschlange', warteschlange)
                    if len(warteschlange) > 0:
                        # Nächster Spieler darf antworten
                        naechster_nr = warteschlange[0]['nr']
                        naechster = spieler_map.get(naechster_nr)
                        if naechster:
                            letzter_gewinner_nr = naechster_nr
                            popup_timer = time.time()
                            buzzer_fenster_offen = False
                            modus = "gewinner"
                    else:
                        # Niemand mehr → Punktestand zeigen
                        modus = "punktestand"

            elif befehl == 'zeige_punktestand':
                sichtbar = data.get('sichtbar', True)
                p_raw = data.get('punkte', {})
                spieler_liste = data.get('spieler', spieler)
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))
                if sichtbar:
                    modus = "punktestand"
                else:
                    modus = "frage"

            elif befehl == 'state_update':
                p_raw = data.get('punkte', {})
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))
                neue_warteschlange = data.get('warteschlange', [])
                # Web-Buzzer: wenn Warteschlange von leer zu nicht-leer während Frage → Popup zeigen
                if len(neue_warteschlange) > 0 and len(warteschlange) == 0 and modus == "frage":
                    erster_nr = neue_warteschlange[0].get('nr')
                    if erster_nr is not None:
                        letzter_gewinner_nr = erster_nr
                        popup_timer = time.time()
                        buzzer_fenster_offen = True
                        modus = "gewinner"
                        spiele_sound(sounds_config.get('buzzer'))
                warteschlange = neue_warteschlange
                if data.get('modus') == 'warten' and modus != 'warten':
                    zeige_schwarz()
                    time.sleep(0.5)
                    modus = 'warten'

            elif befehl == 'buzzer_freigeben':
                buzzer_gesperrt = False
                warteschlange = []
                buzzer_warteschlange_lokal.clear()
                buzzer_start_zeit = time.time()
                popup_timer = None
                buzzer_fenster_offen = False
                if modus in ("punktestand", "gewinner"):
                    modus = "frage"

            elif befehl == 'zeige_sieger':
                p_raw = data.get('punkte', {})
                aktive_spieler = data.get('spieler', spieler)
                spieler_liste = aktive_spieler if aktive_spieler and isinstance(aktive_spieler[0], dict) else spieler
                # Punkte direkt per Spieler aus p_raw aufbauen – vermeidet Key-Typ-Konflikte
                punkte_final = {}
                for s in spieler_liste:
                    nr = s["nr"]
                    v = p_raw.get(str(nr))
                    if v is None:
                        v = p_raw.get(nr)
                    if v is None:
                        v = punkte.get(nr)
                    if v is None:
                        v = punkte.get(str(nr))
                    punkte_final[nr] = v if v is not None else 0
                spiele_sound(sounds_config.get('sieger'))
                zeige_sieger_screen(spieler_liste, punkte_final)
                modus = "sieger"

            elif befehl == 'zeige_meme':
                dateiname = data.get('gif')
                if dateiname:
                    pfad = os.path.join(os.path.dirname(__file__), "gifs", dateiname)
                    frames = lade_gif_frames(pfad)
                    if frames:
                        meme_frames = frames
                        # Anzeigedauer: alle Frames mindestens 2× durchlaufen, min 3 Sek
                        gesamt_ms = sum(d for _, d in frames)
                        meme_bis = time.time() + max(3.0, 2 * gesamt_ms / 1000)
                        meme_frame_idx = 0
                        meme_frame_start = time.time()

            elif befehl == 'buzzer_local':
                nr = data.get('nr')
                ms = data.get('ms', 0)
                if not any(e['nr'] == nr for e in warteschlange):
                    warteschlange.append({'nr': nr, 'ms': ms})
                if len(warteschlange) == 1:
                    letzter_gewinner_nr = nr
                    spiele_sound(sounds_config.get('buzzer'))
                    popup_timer = time.time()  # Timer starten
                    buzzer_fenster_offen = True  # 2 Sek Fenster für weitere Buzzer
                    modus = "gewinner"

        # Meme-Status einmalig ermitteln – steuert ob Render-Funktionen selbst flippen
        meme_aktiv = bool(meme_frames and time.time() < meme_bis)

        # Bildschirm rendern
        if modus == "warten":
            if gpio_test_aktiv:
                zeige_gpio_test(spieler, do_flip=not meme_aktiv)
            else:
                puls += 0.02 * puls_richtung
                if puls >= 1.0: puls_richtung = -1
                if puls <= 0.0: puls_richtung = 1
                zeige_wartebildschirm(puls, do_flip=not meme_aktiv)

        elif modus == "frage":
            zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, mc_aufgeloest, do_flip=not meme_aktiv)

        elif modus == "gewinner":
            s = spieler_map.get(letzter_gewinner_nr)
            if s is None and letzter_gewinner_nr is not None:
                try:
                    alt = int(letzter_gewinner_nr) if isinstance(letzter_gewinner_nr, str) else str(letzter_gewinner_nr)
                    s = spieler_map.get(alt)
                except (ValueError, TypeError):
                    pass
            if s:
                # Buzzer Fenster nach 2 Sek schließen
                if buzzer_fenster_offen and popup_timer and (time.time() - popup_timer) > 2.0:
                    buzzer_fenster_offen = False
                    buzzer_gesperrt = True
                # Countdown berechnen (startet wenn Buzzer-Fenster geschlossen)
                t_rest = None
                if zeitlimit_aktiv and popup_timer and not buzzer_fenster_offen:
                    vergangen = time.time() - popup_timer - 2.0
                    t_rest = max(0.0, zeitlimit_sek - vergangen)
                # Pop-up bleibt bis Moderator Richtig/Falsch klickt
                zeige_spieler_dran_screen(s, "Du darfst antworten!",
                    warteschlange, aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, timer_rest=t_rest, do_flip=not meme_aktiv)

        elif modus == "warte_moderator":
            pass  # Falsch-Screen bleibt stehen bis Moderator nächste Frage drückt

        elif modus == "punktestand":
            zeige_punktestand_screen(aktive_spieler_liste, punkte, do_flip=not meme_aktiv)

        elif modus == "sieger":
            pass  # Sieger-Screen bleibt stehen

        # Meme-Board: animiertes GIF über allem anderen einblenden
        if meme_aktiv:
            # Frame-Advance: nächsten Frame wenn Anzeigedauer abgelaufen
            now = time.time()
            _, frame_dur_ms = meme_frames[meme_frame_idx]
            if (now - meme_frame_start) * 1000 >= frame_dur_ms:
                meme_frame_idx = (meme_frame_idx + 1) % len(meme_frames)
                meme_frame_start = now
            meme_surf = meme_frames[meme_frame_idx][0]
            abdunklung = pygame.Surface((BR, HO), pygame.SRCALPHA)
            abdunklung.fill((0, 0, 0, 200))
            screen.blit(abdunklung, (0, 0))
            screen.blit(meme_surf, (BR//2 - meme_surf.get_width()//2, HO//2 - meme_surf.get_height()//2))
            pygame.display.flip()
        elif meme_frames and time.time() >= meme_bis:
            meme_frames = None

        # Frame-Counter für Animationen
        global frame_counter
        frame_counter = (frame_counter + 1) % 360

        clock.tick(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        gpio_cleanup()
        pygame.quit()
        print("\nBeendet.")
    except Exception as e:
        print(f"Fehler: {e}")
        gpio_cleanup()
        pygame.quit()
