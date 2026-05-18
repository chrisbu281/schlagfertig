#!/usr/bin/env python3
"""
Schlagfertig – Quiz Buzzer mit WebSocket
Empfängt Befehle vom Flask Server via WebSocket
"""
import RPi.GPIO as GPIO
import pygame
import json, time, random, sys, os, threading
import socketio as sio_client

KONFIG_DATEI = os.path.join(os.path.dirname(__file__), "quiz_config.json")
STATE_DATEI  = os.path.join(os.path.dirname(__file__), ".spiel_state")

# ─────────────────────────────────────────────
#  WEBSOCKET CLIENT
# ─────────────────────────────────────────────

sio = sio_client.Client()
ws_verbunden = False

# Befehlswarteschlange für Thread-sichere Kommunikation
from queue import Queue
befehle = Queue()

@sio.event
def connect():
    global ws_verbunden
    ws_verbunden = True
    print("WebSocket verbunden!")

@sio.event
def disconnect():
    global ws_verbunden
    ws_verbunden = False
    print("WebSocket getrennt!")

@sio.on('zeige_frage')
def on_zeige_frage(data):
    befehle.put(('zeige_frage', data))

@sio.on('zeige_ergebnis')
def on_zeige_ergebnis(data):
    befehle.put(('zeige_ergebnis', data))

@sio.on('buzzer_freigeben')
def on_buzzer_freigeben():
    befehle.put(('buzzer_freigeben', {}))

@sio.on('state_update')
def on_state_update(data):
    befehle.put(('state_update', data))

def verbinde_websocket():
    while True:
        try:
            if not ws_verbunden:
                sio.connect('http://localhost:5000')
        except Exception as e:
            print(f"WebSocket Verbindungsfehler: {e}")
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
    with open(STATE_DATEI, "w") as f:
        f.write(modus)

def lese_state():
    try:
        with open(STATE_DATEI, "r") as f:
            return f.read().strip()
    except:
        return "warten"

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
#  GPIO
# ─────────────────────────────────────────────

def gpio_setup(spieler):
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for s in spieler:
        GPIO.setup(s["gpio"], GPIO.IN, pull_up_down=GPIO.PUD_UP)

def gpio_cleanup():
    GPIO.cleanup()

# ─────────────────────────────────────────────
#  DISPLAY
# ─────────────────────────────────────────────

WEISS  = (255, 255, 255)
DUNKEL = (18,  18,  28)
ROT    = (230, 57,  70)

SF_GR = SF_MI = SF_KL = None
BR = HO = 0

def display_setup():
    global SF_GR, SF_MI, SF_KL, BR, HO
    pygame.init()
    info = pygame.display.Info()
    BR, HO = info.current_w, info.current_h
    pygame.display.set_mode((BR, HO), pygame.FULLSCREEN)
    pygame.display.set_caption("Schlagfertig")
    SF_GR = pygame.font.SysFont("DejaVu Sans", 86, bold=True)
    SF_MI = pygame.font.SysFont("DejaVu Sans", 46)
    SF_KL = pygame.font.SysFont("DejaVu Sans", 28)

def blit_mitte(screen, surf, y):
    screen.blit(surf, (BR//2 - surf.get_width()//2, y))

def zeichne_kachel(screen, s, pkt, x, y, bw, bh, highlight=False):
    farbe    = hex_zu_rgb(s["farbe"])
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
        initial = s["name"][0].upper() if s["name"] else "?"
        ini_s = SF_GR.render(initial, True, WEISS)
        screen.blit(ini_s, (mx - ini_s.get_width()//2, y+68 - ini_s.get_height()//2))
    ns = SF_KL.render(s["name"], True, WEISS)
    screen.blit(ns, (mx - ns.get_width()//2, y+130))
    ps = SF_GR.render(str(pkt), True, WEISS)
    screen.blit(ps, (mx - ps.get_width()//2, y+168))
    ls = SF_KL.render("Punkte", True, (210,210,210))
    screen.blit(ls, (mx - ls.get_width()//2, y+268))

def zeige_wartebildschirm(puls_alpha, spieler, punkte):
    screen = pygame.display.get_surface()
    screen.fill(DUNKEL)

    # Logo
    logo1 = SF_GR.render("SCHLAG", True, WEISS)
    logo2 = SF_GR.render("FERTIG", True, ROT)
    gesamt_b = logo1.get_width() + logo2.get_width() + 10
    x = BR//2 - gesamt_b//2
    y = HO//2 - 160
    screen.blit(logo1, (x, y))
    screen.blit(logo2, (x + logo1.get_width() + 10, y))

    sub = SF_KL.render("Quiz Buzzer System", True, (100, 100, 120))
    blit_mitte(screen, sub, HO//2 - 60)

    warte_surf = SF_MI.render("Warten auf Moderator...", True,
                               (int(80 + puls_alpha * 80), int(80 + puls_alpha * 80), int(100 + puls_alpha * 80)))
    blit_mitte(screen, warte_surf, HO//2)

    hint = SF_KL.render("http://schlagfertig.local:5000", True, (40, 40, 60))
    blit_mitte(screen, hint, HO - 54)
    pygame.display.flip()

def zeige_startbildschirm(spieler, punkte, highlight_nr=None):
    screen = pygame.display.get_surface()
    screen.fill(DUNKEL)
    blit_mitte(screen, SF_GR.render("SCHLAGFERTIG", True, WEISS), 34)
    n = len(spieler)
    bw = min(255, (BR-80)//n - 14)
    bh = 314
    gx = (BR - (n*bw + (n-1)*14))//2
    gy = HO//2 - bh//2 + 28
    for i, s in enumerate(spieler):
        zeichne_kachel(screen, s, punkte.get(str(s["nr"]), punkte.get(s["nr"], 0)),
                       gx+i*(bw+14), gy, bw, bh, highlight=s["nr"]==highlight_nr)
    pygame.display.flip()

def zeige_frage_screen(frage_dict, nr, gesamt, zeige_mc=False):
    screen = pygame.display.get_surface()
    screen.fill(DUNKEL)
    if frage_dict:
        kat = SF_KL.render(
            f"Frage {nr}/{gesamt}  ·  {frage_dict.get('kategorie','')}  ·  {frage_dict.get('schwierigkeit','').capitalize()}",
            True, (110,110,180))
        blit_mitte(screen, kat, 58)
        worte = frage_dict.get("frage","").split()
        zeilen, z = [], []
        for w in worte:
            p = " ".join(z+[w])
            if SF_MI.size(p)[0] > BR-160: zeilen.append(" ".join(z)); z=[w]
            else: z.append(w)
        if z: zeilen.append(" ".join(z))
        y = HO//2 - (len(zeilen)*63)//2 - (80 if zeige_mc else 0)
        for line in zeilen:
            blit_mitte(screen, SF_MI.render(line, True, WEISS), y); y += 63

        if zeige_mc and frage_dict.get("antworten_mc"):
            mc = frage_dict["antworten_mc"]
            farben = [(67,97,238),(247,37,133),(244,162,97),(46,196,182)]
            buchst = ["A","B","C","D"]
            kw, kh = (BR-120)//2, 70
            positionen = [(60,HO-200),(60+kw+20,HO-200),(60,HO-120),(60+kw+20,HO-120)]
            for i,(ax,ay) in enumerate(positionen):
                if i >= len(mc): break
                pygame.draw.rect(screen, farben[i], (ax,ay,kw,kh), border_radius=12)
                txt = SF_KL.render(f"{buchst[i]}: {mc[i]}", True, WEISS)
                screen.blit(txt, (ax+16, ay+kh//2-txt.get_height()//2))

    blit_mitte(screen, SF_KL.render("Buzzer drücken!", True, (80,200,120)), HO-54)
    pygame.display.flip()

def zeige_gewinner_screen(spieler_obj, punkte_wert, ms, warteschlange=[]):
    screen = pygame.display.get_surface()
    farbe  = hex_zu_rgb(spieler_obj["farbe"])
    screen.fill(dunkler(farbe,.28))
    pw,ph = 560,320; px=BR//2-pw//2; py=HO//2-ph//2-50
    pygame.draw.rect(screen, farbe, (px,py,pw,ph), border_radius=22)
    kr = 72
    foto_surf = _foto_cache.get(spieler_obj["nr"])
    if foto_surf is None and spieler_obj.get("foto"):
        foto_surf = lade_foto(spieler_obj, groesse=kr*2)
        _foto_cache[spieler_obj["nr"]] = foto_surf
    if foto_surf:
        fs = pygame.transform.smoothscale(foto_surf, (kr*2, kr*2))
        screen.blit(fs, (BR//2 - kr, py+92 - kr))
    else:
        pygame.draw.circle(screen, farbe, (BR//2, py+92), kr)
        initial = spieler_obj["name"][0].upper()
        ini_s = SF_GR.render(initial, True, WEISS)
        screen.blit(ini_s, (BR//2-ini_s.get_width()//2, py+92-ini_s.get_height()//2))
    blit_mitte(screen, SF_GR.render(spieler_obj["name"], True, WEISS), py+182)
    blit_mitte(screen, SF_KL.render("hat gebuzzert!", True, (220,220,220)), py+274)
    info = f"Punktestand: {punkte_wert}"
    if ms: info += f"  ·  Reaktion: {ms} ms"
    blit_mitte(screen, SF_KL.render(info, True, (160,160,160)), py+ph+26)

    # Warteschlange
    rang_icons = ["🥇","🥈","🥉","4."]
    if len(warteschlange) > 1:
        wq_y = py+ph+60
        for i, e in enumerate(warteschlange):
            if i == 0: continue
            s = next((sp for sp in konfig_global["spieler"] if sp["nr"]==e["nr"]), None)
            if s:
                wq_txt = SF_KL.render(f"{rang_icons[i]} {s['name']} wartet...", True, (120,120,120))
                blit_mitte(screen, wq_txt, wq_y)
                wq_y += 34

    pygame.display.flip()

def zeige_ergebnis_screen(richtig, delta):
    screen = pygame.display.get_surface()
    screen.fill((10,55,25) if richtig else (55,10,10))
    msg   = f"+{delta} Punkte!" if richtig else f"−{delta} Punkte!"
    farbe = (60,220,100) if richtig else (220,70,70)
    blit_mitte(screen, SF_GR.render(msg, True, farbe), HO//2-50)
    pygame.display.flip()

# ─────────────────────────────────────────────
#  BUZZER POLLING THREAD
# ─────────────────────────────────────────────

buzzer_aktiv = True
buzzer_gesperrt = False
buzzer_start_zeit = None

def buzzer_thread(spieler):
    global buzzer_gesperrt, buzzer_start_zeit
    letzter = {s["nr"]: GPIO.input(s["gpio"]) for s in spieler}
    while buzzer_aktiv:
        if not buzzer_gesperrt:
            for s in spieler:
                jetzt = GPIO.input(s["gpio"])
                if jetzt == GPIO.LOW and letzter[s["nr"]] == GPIO.HIGH:
                    ms = int((time.time() - buzzer_start_zeit) * 1000) if buzzer_start_zeit else 0
                    buzzer_gesperrt = True
                    # An Server melden
                    try:
                        sio.emit('buzzer_gedrueckt', {'nr': s["nr"], 'ms': ms})
                    except:
                        pass
                    befehle.put(('buzzer_local', {'nr': s["nr"], 'ms': ms}))
                letzter[s["nr"]] = jetzt
        time.sleep(0.001)

# ─────────────────────────────────────────────
#  HAUPTPROGRAMM
# ─────────────────────────────────────────────

konfig_global = None

def main():
    global konfig_global, buzzer_aktiv, buzzer_gesperrt, buzzer_start_zeit

    konfig_global = lade_konfig()
    spieler = konfig_global["spieler"]
    spieler_map = {s["nr"]: s for s in spieler}

    gpio_setup(spieler)
    display_setup()
    _foto_cache.clear()

    # WebSocket Verbindung in eigenem Thread
    ws_thread = threading.Thread(target=verbinde_websocket, daemon=True)
    ws_thread.start()

    # Buzzer Thread
    buz_thread = threading.Thread(target=buzzer_thread, args=(spieler,), daemon=True)
    buz_thread.start()

    # Pulsieren für Wartebildschirm
    puls = 0.0
    richtung = 1

    # Spielzustand
    aktueller_modus = "warten"  # warten | frage | gewinner | ergebnis
    aktuelle_frage = None
    frage_nr = 0
    frage_gesamt = 1
    punkte = {s["nr"]: 0 for s in spieler}
    letzter_gewinner = None
    warteschlange = []
    mc_aktiv = False

    schreibe_state("warten")

    clock = pygame.time.Clock()

    while True:
        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                buzzer_aktiv = False
                gpio_cleanup()
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    buzzer_aktiv = False
                    gpio_cleanup()
                    pygame.quit()
                    sys.exit()

        # Befehle aus Queue verarbeiten
        while not befehle.empty():
            befehl, data = befehle.get()

            if befehl == 'zeige_frage':
                aktuelle_frage = data.get('frage')
                frage_nr = data.get('idx', 0) + 1
                frage_gesamt = data.get('gesamt', 1)
                mc_aktiv = data.get('mc_aktiv', False)
                warteschlange = []
                buzzer_gesperrt = False
                buzzer_start_zeit = time.time()
                aktueller_modus = "frage"

            elif befehl == 'zeige_ergebnis':
                richtig = data.get('richtig', False)
                delta = data.get('delta', 10)
                zeige_ergebnis_screen(richtig, delta)
                aktueller_modus = "ergebnis"
                pygame.time.set_timer(pygame.USEREVENT, 2000)

            elif befehl == 'buzzer_freigeben':
                buzzer_gesperrt = False
                warteschlange = []
                buzzer_start_zeit = time.time()
                if aktueller_modus == "frage":
                    zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, mc_aktiv)

            elif befehl == 'state_update':
                punkte_raw = data.get('punkte', {})
                for nr in punkte:
                    punkte[nr] = punkte_raw.get(str(nr), punkte_raw.get(nr, 0))
                warteschlange = data.get('warteschlange', [])
                if data.get('modus') == 'warten' and aktueller_modus != 'warten':
                    aktueller_modus = 'warten'

            elif befehl == 'buzzer_local':
                nr = data.get('nr')
                ms = data.get('ms', 0)
                if not any(e['nr'] == nr for e in warteschlange):
                    warteschlange.append({'nr': nr, 'ms': ms})
                if len(warteschlange) == 1:
                    letzter_gewinner = nr
                    aktueller_modus = "gewinner"

        # Timer Event für Ergebnis
        for event in pygame.event.get([pygame.USEREVENT]):
            if aktueller_modus == "ergebnis":
                aktueller_modus = "startbildschirm"
                pygame.time.set_timer(pygame.USEREVENT, 0)

        # Bildschirm rendern
        if aktueller_modus == "warten":
            puls += 0.02 * richtung
            if puls >= 1.0: richtung = -1
            if puls <= 0.0: richtung = 1
            zeige_wartebildschirm(puls, spieler, punkte)

        elif aktueller_modus == "startbildschirm":
            zeige_startbildschirm(spieler, punkte)
            aktueller_modus = "frage"

        elif aktueller_modus == "frage":
            zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, mc_aktiv)

        elif aktueller_modus == "gewinner":
            if letzter_gewinner and letzter_gewinner in spieler_map:
                s = spieler_map[letzter_gewinner]
                pkt = punkte.get(letzter_gewinner, 0)
                ms = warteschlange[0]['ms'] if warteschlange else 0
                zeige_gewinner_screen(s, pkt, ms, warteschlange)

        clock.tick(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        GPIO.cleanup()
        pygame.quit()
        print("\nBeendet.")
