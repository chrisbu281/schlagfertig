#!/usr/bin/env python3
"""
Schlagfertig – Quiz Buzzer
Fixes: MC Antworten, Sieger, Punktestand, schwarzer Übergang
"""
import RPi.GPIO as GPIO
import pygame
import json, time, sys, os, threading, atexit
import socketio as sio_client
from queue import Queue
try:
    from PIL import Image, ImageSequence
    _PIL_VERFUEGBAR = True
except ImportError:
    _PIL_VERFUEGBAR = False
    print("Hinweis: Pillow nicht installiert – GIFs werden nur als Standbild angezeigt. (pip install Pillow)")

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
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for s in spieler:
        GPIO.setup(s["gpio"], GPIO.IN, pull_up_down=GPIO.PUD_UP)

def gpio_cleanup():
    try: GPIO.cleanup()
    except: pass

# ─────────────────────────────────────────────
#  DISPLAY
# ─────────────────────────────────────────────
WEISS  = (255, 255, 255)
DUNKEL = (18,  18,  28)
ROT    = (230, 57,  70)
SCHWARZ = (0, 0, 0)

# ═══ THEME SYSTEM ═══
THEMES = {
    'frei': {
        'name': 'Standard',
        'bg_color': (13, 13, 23),
        'text_color': (255, 255, 255),
        'accent_color': (100, 150, 255),
        'success_color': (30, 200, 90),
        'error_color': (230, 60, 60),
        'popup_alpha': 140
    },
    'mc': {
        'name': 'Neon',
        'bg_color': (8, 8, 18),
        'text_color': (255, 255, 255),
        'accent_color': (0, 255, 255),
        'success_color': (57, 255, 20),
        'error_color': (255, 0, 150),
        'popup_alpha': 160,
        'neon_colors': [
            (0, 255, 255),      # Cyan
            (255, 0, 150),      # Pink
            (57, 255, 20),      # Green
            (255, 255, 0)       # Yellow
        ]
    }
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
    pygame.init()
    info = pygame.display.Info()
    BR, HO = info.current_w, info.current_h
    screen = pygame.display.set_mode((BR, HO), pygame.FULLSCREEN)
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

def zeige_frage_screen(frage_dict, nr, gesamt, spielmodus='frei', mc_gewaehlt=None, mc_aufgeloest=False, do_flip=True):
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
            if mc_aufgeloest:
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

def zeige_spieler_dran_screen(spieler_obj, text="Du darfst antworten!", warteschlange=[], frage_dict=None, frage_nr=1, frage_gesamt=1, spielmodus='frei', mc_gewaehlt=None, do_flip=True):
    """Zeigt Pop-up über der Frage wer dran ist"""
    # Erst Frage im Hintergrund zeigen (ohne flip!)
    if frage_dict:
        zeige_frage_screen(frage_dict, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, False, do_flip=False)

    # Pop-up darüber zeichnen
    farbe = hex_zu_rgb(spieler_obj["farbe"])
    theme = current_theme or THEMES['frei']
    istMC = spielmodus == 'mc'

    # Halbtransparenter dunkler Hintergrund
    overlay = pygame.Surface((BR, HO), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, theme.get('popup_alpha', 140)))
    screen.blit(overlay, (0, 0))

    # Pop-up Karte
    pw, ph = 580, 360
    px = BR//2 - pw//2
    py = HO//2 - ph//2

    # NEON-Border für MC
    if istMC:
        pygame.draw.rect(screen, farbe, (px, py, pw, ph), border_radius=26, width=4)

    # Schatten (für Tiefe)
    schatten = pygame.Surface((pw+12, ph+12), pygame.SRCALPHA)
    schatten.fill((0,0,0,120))
    screen.blit(schatten, (px+6, py+6))

    # Karte Hintergrund
    if istMC:
        # Neon-Border für MC
        pygame.draw.rect(screen, dunkler(farbe,.5), (px, py, pw, ph), border_radius=26)
        pygame.draw.rect(screen, farbe, (px+2, py+2, pw-4, ph-4), border_radius=24)
        pygame.draw.rect(screen, farbe, (px, py, pw, ph), border_radius=26, width=3)
    else:
        pygame.draw.rect(screen, dunkler(farbe,.3), (px, py, pw, ph), border_radius=24)
        pygame.draw.rect(screen, farbe, (px+2, py+2, pw-4, ph-4), border_radius=22)
    
    # Foto oder Avatar
    kr = 75
    foto_surf = _foto_cache.get(spieler_obj["nr"])
    if foto_surf is None and spieler_obj.get("foto"):
        foto_surf = lade_foto(spieler_obj, groesse=kr*2)
        _foto_cache[spieler_obj["nr"]] = foto_surf
    if foto_surf:
        fs = pygame.transform.smoothscale(foto_surf, (kr*2, kr*2))
        screen.blit(fs, (BR//2 - kr, py+70 - kr))
    else:
        pygame.draw.circle(screen, dunkler(farbe,.5), (BR//2, py+70), kr+4)
        pygame.draw.circle(screen, farbe, (BR//2, py+70), kr)
        ini = SF_MI.render(spieler_obj["name"][0].upper(), True, WEISS)
        screen.blit(ini, (BR//2-ini.get_width()//2, py+70-ini.get_height()//2))

    # Name (größer)
    name_font = pygame.font.SysFont("DejaVu Sans", 48, bold=True)
    name_surf = name_font.render(spieler_obj["name"], True, WEISS)
    screen.blit(name_surf, (BR//2 - name_surf.get_width()//2, py+155))

    # Text
    txt_surf = SF_MI.render(text, True, (220,220,220))
    screen.blit(txt_surf, (BR//2 - txt_surf.get_width()//2, py+225))
    
    # Warteschlange unten
    if len(warteschlange) > 1:
        rang_icons = ["🥇","🥈","🥉","4.","5.","6."]
        wq_y = py + ph + 24
        for i, e in enumerate(warteschlange):
            if i == 0: continue
            s_nr = e.get('nr')
            s_ms = e.get('ms', 0)
            s = spieler_map_global.get(s_nr)
            s_name = s['name'] if s else f"Spieler {s_nr}"
            ms_txt = f"  +{s_ms} ms" if s_ms else ""
            wq_txt = SF_KL.render(f"{rang_icons[i]} {s_name}{ms_txt}", True, (200,200,200))
            screen.blit(wq_txt, (BR//2 - wq_txt.get_width()//2, wq_y))
            wq_y += 38

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
    rang_emojis = ["🥇", "🥈", "🥉", "4."]
    for i, s in enumerate(sortiert):
        pkt = punkte.get(s["nr"], punkte.get(str(s["nr"]), 0))
        zeichne_kachel(s, pkt, gx+i*(bw+14), gy, bw, bh)
        rang_text = rang_emojis[i] if i < 3 else f"{i+1}."
        if i < 3 and SF_EMOJI:
            rang_surf = SF_EMOJI.render(rang_text, True, WEISS)
        else:
            rang_surf = SF_MI.render(rang_text, True, WEISS)
        screen.blit(rang_surf, (gx+i*(bw+14) + bw//2 - rang_surf.get_width()//2, gy-54))
    if do_flip: pygame.display.flip()

def zeige_sieger_screen(spieler_liste, punkte):
    screen.fill(DUNKEL)
    blit_mitte(SF_GR.render("SPIELENDE!", True, WEISS), 30)

    if not spieler_liste:
        pygame.display.flip()
        return

    # Nach Punkten sortieren
    sortiert = sorted(spieler_liste,
        key=lambda s: punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)),
        reverse=True)

    def zeichne_podium_karte(s, pkt, cx, cy, groesse):
        farbe = hex_zu_rgb(s["farbe"])
        kr = groesse // 2
        pygame.draw.circle(screen, dunkler(farbe, .5), (cx, cy), kr+4)
        pygame.draw.circle(screen, farbe, (cx, cy), kr)
        foto_surf = _foto_cache.get(s["nr"])
        if foto_surf is None and s.get("foto"):
            foto_surf = lade_foto(s, groesse=kr*2)
            _foto_cache[s["nr"]] = foto_surf
        if foto_surf:
            fs = pygame.transform.smoothscale(foto_surf, (kr*2, kr*2))
            screen.blit(fs, (cx-kr, cy-kr))
        else:
            ini = SF_MI.render(s["name"][0].upper(), True, WEISS)
            screen.blit(ini, (cx-ini.get_width()//2, cy-ini.get_height()//2))
        font_n = pygame.font.SysFont("DejaVu Sans", max(18, groesse//3), bold=True)
        font_p = pygame.font.SysFont("DejaVu Sans", max(14, groesse//4))
        name_s = font_n.render(s["name"], True, WEISS)
        pkt_s = font_p.render(f"{pkt} Punkte", True, (200,200,200))
        screen.blit(name_s, (cx-name_s.get_width()//2, cy+kr+8))
        screen.blit(pkt_s, (cx-pkt_s.get_width()//2, cy+kr+8+name_s.get_height()+4))

    # 🥇 Platz 1 – groß oben mitte
    if len(sortiert) >= 1:
        s1 = sortiert[0]
        p1 = punkte.get(s1["nr"], punkte.get(str(s1["nr"]), 0))
        rang = SF_MI.render("1.", True, (255,215,0))
        screen.blit(rang, (BR//2-rang.get_width()//2, 110))
        zeichne_podium_karte(s1, p1, BR//2, 230, 110)

    # 🥈 Platz 2 – links
    if len(sortiert) >= 2:
        s2 = sortiert[1]
        p2 = punkte.get(s2["nr"], punkte.get(str(s2["nr"]), 0))
        rang = SF_KL.render("2.", True, (192,192,192))
        screen.blit(rang, (BR//4-rang.get_width()//2, 270))
        zeichne_podium_karte(s2, p2, BR//4, 360, 80)

    # 🥉 Platz 3 – rechts
    if len(sortiert) >= 3:
        s3 = sortiert[2]
        p3 = punkte.get(s3["nr"], punkte.get(str(s3["nr"]), 0))
        rang = SF_KL.render("3.", True, (205,127,50))
        screen.blit(rang, (BR*3//4-rang.get_width()//2, 270))
        zeichne_podium_karte(s3, p3, BR*3//4, 360, 80)

    # Platz 4-6 – Liste unten
    y = HO - 160
    for i, s in enumerate(sortiert[3:]):
        pkt = punkte.get(s["nr"], punkte.get(str(s["nr"]), 0))
        farbe = hex_zu_rgb(s["farbe"])
        kr = 22
        cx = BR//2 - 180
        foto_surf = _foto_cache.get(s["nr"])
        if foto_surf:
            fs = pygame.transform.smoothscale(foto_surf, (kr*2, kr*2))
            screen.blit(fs, (cx-kr, y-kr))
        else:
            pygame.draw.circle(screen, farbe, (cx, y), kr)
            ini = SF_KL.render(s["name"][0].upper(), True, WEISS)
            screen.blit(ini, (cx-ini.get_width()//2, y-ini.get_height()//2))
        txt = SF_KL.render(f"{i+4}.  {s['name']}  –  {pkt} Punkte", True, (160,160,160))
        screen.blit(txt, (cx+kr+12, y-txt.get_height()//2))
        y += 46

    pygame.display.flip()

# ─────────────────────────────────────────────
#  BUZZER THREAD
# ─────────────────────────────────────────────
buzzer_aktiv = True
buzzer_gesperrt = False
buzzer_start_zeit = None
buzzer_warteschlange_lokal = []  # Lokale Kopie der Warteschlange

def buzzer_thread(spieler):
    global buzzer_gesperrt, buzzer_start_zeit, buzzer_warteschlange_lokal
    # Sicherstellen dass GPIO korrekt initialisiert ist
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for s in spieler:
            GPIO.setup(s["gpio"], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except: pass

    letzter = {s["nr"]: GPIO.HIGH for s in spieler}
    erster_buzz_zeit = None

    while buzzer_aktiv:
        for s in spieler:
            jetzt = GPIO.input(s["gpio"])
            if jetzt == GPIO.LOW and letzter[s["nr"]] == GPIO.HIGH:
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
                    try:
                        sio.emit('buzzer_gedrueckt', {'nr': nr, 'ms': ms})
                    except: pass
                    befehle.put(('buzzer_local', {'nr': nr, 'ms': ms}))

            letzter[s["nr"]] = jetzt
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
    global buzzer_aktiv, buzzer_gesperrt, buzzer_start_zeit

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

    schreibe_state("warten")
    clock = pygame.time.Clock()

    while True:
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

        # Befehle verarbeiten
        while not befehle.empty():
            befehl, data = befehle.get()

            if befehl == 'zeige_frage':
                aktuelle_frage = data.get('frage')
                frage_nr = data.get('idx', 0) + 1
                frage_gesamt = data.get('gesamt', 1)
                spielmodus = data.get('spielmodus', 'frei')
                set_modus_theme(spielmodus)  # Theme setzen
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
                mc_aufgeloest = True
                # Punkte aktualisieren
                p_raw = data.get('punkte', {})
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))
                zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, True)
                # Nach 5 Sek Punktestand zeigen
                time.sleep(5)
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
                warteschlange = data.get('warteschlange', [])
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
                if modus == "punktestand":
                    modus = "frage"

            elif befehl == 'zeige_sieger':
                p_raw = data.get('punkte', {})
                # Aktive Spieler vom Editor übernehmen
                aktive_spieler = data.get('spieler', spieler)
                # Konvertiere falls nötig
                if aktive_spieler and isinstance(aktive_spieler[0], dict):
                    spieler_liste = aktive_spieler
                else:
                    spieler_liste = spieler
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))
                spiele_sound(sounds_config.get('sieger'))
                zeige_sieger_screen(spieler_liste, punkte)
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
            puls += 0.02 * puls_richtung
            if puls >= 1.0: puls_richtung = -1
            if puls <= 0.0: puls_richtung = 1
            zeige_wartebildschirm(puls, do_flip=not meme_aktiv)

        elif modus == "frage":
            zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, mc_aufgeloest, do_flip=not meme_aktiv)

        elif modus == "gewinner":
            if letzter_gewinner_nr and letzter_gewinner_nr in spieler_map:
                s = spieler_map[letzter_gewinner_nr]
                # Buzzer Fenster nach 2 Sek schließen
                if buzzer_fenster_offen and popup_timer and (time.time() - popup_timer) > 2.0:
                    buzzer_fenster_offen = False
                    buzzer_gesperrt = True
                # Pop-up anzeigen (ohne Ranking)
                zeige_spieler_dran_screen(s, "Du darfst antworten!",
                    [], aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, do_flip=not meme_aktiv)
                # Nach 3 Sekunden zurück zur Frage
                if popup_timer and (time.time() - popup_timer) > 3.0:
                    popup_timer = None
                    buzzer_fenster_offen = False
                    zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, False)
                    modus = "frage"

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
