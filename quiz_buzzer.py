#!/usr/bin/env python3
"""
Schlagfertig – Quiz Buzzer
Fixes: MC Antworten, Sieger, Punktestand, schwarzer Übergang
"""
import RPi.GPIO as GPIO
import pygame
import json, time, sys, os, threading
import socketio as sio_client
from queue import Queue

KONFIG_DATEI = os.path.join(os.path.dirname(__file__), "quiz_config.json")
STATE_DATEI  = os.path.join(os.path.dirname(__file__), ".spiel_state")

# ─────────────────────────────────────────────
#  WEBSOCKET CLIENT
# ─────────────────────────────────────────────
sio = sio_client.Client(reconnection=True, reconnection_attempts=0)
ws_verbunden = False
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

@sio.on('state_update')
def on_state(data): befehle.put(('state_update', data))

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
#  GPIO
# ─────────────────────────────────────────────
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

SF_GR = SF_MI = SF_KL = None
BR = HO = 0
screen = None

def display_setup():
    global SF_GR, SF_MI, SF_KL, BR, HO, screen
    pygame.init()
    info = pygame.display.Info()
    BR, HO = info.current_w, info.current_h
    screen = pygame.display.set_mode((BR, HO), pygame.FULLSCREEN)
    pygame.display.set_caption("Schlagfertig")
    SF_GR = pygame.font.SysFont("DejaVu Sans", 86, bold=True)
    SF_MI = pygame.font.SysFont("DejaVu Sans", 46)
    SF_KL = pygame.font.SysFont("DejaVu Sans", 28)

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

def zeige_wartebildschirm(puls):
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
    pygame.display.flip()

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

def zeige_frage_screen(frage_dict, nr, gesamt, spielmodus='frei', mc_gewaehlt=None, mc_aufgeloest=False):
    screen.fill(DUNKEL)
    if not frage_dict:
        pygame.display.flip()
        return

    # Kategorie + Nummer
    kat_txt = SF_KL.render(
        f"Frage {nr}/{gesamt}  ·  {frage_dict.get('kategorie','')}  ·  {frage_dict.get('schwierigkeit','').capitalize()}",
        True, (110,110,180))
    blit_mitte(kat_txt, 46)

    # Frage Text
    istMC = spielmodus == 'mc' or frage_dict.get('modus') == 'mc'
    worte = frage_dict.get("frage","").split()
    zeilen, z = [], []
    for w in worte:
        p = " ".join(z+[w])
        if SF_MI.size(p)[0] > BR-160: zeilen.append(" ".join(z)); z=[w]
        else: z.append(w)
    if z: zeilen.append(" ".join(z))

    y_start = HO//2 - (len(zeilen)*63)//2 - (120 if istMC else 0)
    for line in zeilen:
        blit_mitte(SF_MI.render(line, True, WEISS), y_start)
        y_start += 63

    # MC Antworten
    if istMC and frage_dict.get("antworten_mc") and len(frage_dict["antworten_mc"]) == 4:
        mc = frage_dict["antworten_mc"]
        richtig_idx = frage_dict.get("richtige_antwort_index", 0)
        farben = [(67,97,238),(247,37,133),(244,162,97),(46,196,182)]
        buchst = ["A","B","C","D"]
        kw = (BR-120)//2
        kh = 80
        positionen = [
            (60, HO-220), (60+kw+20, HO-220),
            (60, HO-130), (60+kw+20, HO-130)
        ]
        for i, (ax, ay) in enumerate(positionen):
            if i >= len(mc): break
            farbe = list(farben[i])

            if mc_aufgeloest:
                if i == richtig_idx:
                    # Richtige Antwort grün
                    pygame.draw.rect(screen, (30, 160, 80), (ax,ay,kw,kh), border_radius=14)
                    pygame.draw.rect(screen, (60, 220, 120), (ax,ay,kw,kh), border_radius=14, width=4)
                elif i == mc_gewaehlt:
                    # Falsch gewählte Antwort rot
                    pygame.draw.rect(screen, (160, 30, 30), (ax,ay,kw,kh), border_radius=14)
                    pygame.draw.rect(screen, (220, 60, 60), (ax,ay,kw,kh), border_radius=14, width=4)
                else:
                    # Andere ausgegraut
                    pygame.draw.rect(screen, (40,40,50), (ax,ay,kw,kh), border_radius=14)
            elif mc_gewaehlt == i:
                # Gewählte Antwort blau umrandet
                pygame.draw.rect(screen, tuple(farbe), (ax,ay,kw,kh), border_radius=14)
                pygame.draw.rect(screen, WEISS, (ax,ay,kw,kh), border_radius=14, width=4)
            else:
                pygame.draw.rect(screen, tuple(farbe), (ax,ay,kw,kh), border_radius=14)

            # Text
            txt_farbe = WEISS if i != 2 else (30,30,30)
            lbl = SF_MI.render(f"{buchst[i]}", True, txt_farbe)
            ant = SF_KL.render(mc[i], True, txt_farbe)
            screen.blit(lbl, (ax+18, ay+kh//2-lbl.get_height()//2))
            screen.blit(ant, (ax+60, ay+kh//2-ant.get_height()//2))

    if not istMC:
        blit_mitte(SF_KL.render("Buzzer drücken!", True, (80,200,120)), HO-54)

    pygame.display.flip()

def zeige_gewinner_screen(spieler_obj, punkte_wert, ms, warteschlange, spieler_map):
    farbe = hex_zu_rgb(spieler_obj["farbe"])
    screen.fill(dunkler(farbe,.28))
    pw,ph = 580,340
    px = BR//2-pw//2
    py = HO//2-ph//2-60
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
        ini = SF_GR.render(spieler_obj["name"][0].upper(), True, WEISS)
        screen.blit(ini, (BR//2-ini.get_width()//2, py+92-ini.get_height()//2))
    blit_mitte(SF_GR.render(spieler_obj["name"], True, WEISS), py+182)
    blit_mitte(SF_KL.render("hat gebuzzert!", True, (220,220,220)), py+274)
    info = f"Punktestand: {punkte_wert}"
    if ms: info += f"  ·  Reaktion: {ms} ms"
    blit_mitte(SF_KL.render(info, True, (160,160,160)), py+ph+26)

    # Warteschlange anzeigen
    rang_icons = ["🥇","🥈","🥉","4."]
    if len(warteschlange) > 1:
        wq_y = py+ph+60
        for i, e in enumerate(warteschlange):
            if i == 0: continue
            s = spieler_map.get(e["nr"])
            if s:
                farbe_s = hex_zu_rgb(s["farbe"])
                wq_txt = SF_KL.render(f"{rang_icons[i]} {s['name']}  +{e.get('ms',0)} ms", True, (150,150,150))
                blit_mitte(wq_txt, wq_y)
                wq_y += 36

    pygame.display.flip()

def zeige_ergebnis_screen(richtig, delta):
    screen.fill((10,55,25) if richtig else (55,10,10))
    msg   = f"+{delta} Punkte!" if richtig else f"−{delta} Punkte!"
    farbe = (60,220,100) if richtig else (220,70,70)
    blit_mitte(SF_GR.render(msg, True, farbe), HO//2-50)
    pygame.display.flip()

def zeige_punktestand_screen(spieler_liste, punkte):
    screen.fill(DUNKEL)
    blit_mitte(SF_GR.render("PUNKTESTAND", True, WEISS), 40)
    n = len(spieler_liste)
    bw = min(240, (BR-80)//n - 14)
    bh = 300
    gx = (BR - (n*bw + (n-1)*14))//2
    gy = HO//2 - bh//2 + 30
    # Nach Punkten sortiert anzeigen
    sortiert = sorted(spieler_liste, key=lambda s: punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)), reverse=True)
    for i, s in enumerate(sortiert):
        pkt = punkte.get(s["nr"], punkte.get(str(s["nr"]), 0))
        zeichne_kachel(s, pkt, gx+i*(bw+14), gy, bw, bh)
        # Rang anzeigen
        rang = ["🥇","🥈","🥉","4."][i] if i < 4 else f"{i+1}."
        rang_surf = SF_MI.render(rang, True, WEISS)
        screen.blit(rang_surf, (gx+i*(bw+14) + bw//2 - rang_surf.get_width()//2, gy-50))
    pygame.display.flip()

def zeige_sieger_screen(spieler_liste, punkte):
    screen.fill(DUNKEL)
    blit_mitte(SF_GR.render("SPIELENDE!", True, WEISS), 58)
    if not spieler_liste:
        pygame.display.flip()
        return
    max_p = max((punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)) for s in spieler_liste), default=0)
    sieger = [s for s in spieler_liste if punkte.get(s["nr"], punkte.get(str(s["nr"]), 0)) == max_p]
    if len(sieger) == 1:
        s = sieger[0]
        farbe = hex_zu_rgb(s["farbe"])
        kr = 100
        foto_surf = _foto_cache.get(s["nr"])
        if foto_surf:
            fs = pygame.transform.smoothscale(foto_surf, (kr*2, kr*2))
            screen.blit(fs, (BR//2 - kr, HO//2 - 80 - kr))
        else:
            pygame.draw.circle(screen, farbe, (BR//2, HO//2-80), kr)
            ini = SF_GR.render(s["name"][0].upper(), True, WEISS)
            screen.blit(ini, (BR//2-ini.get_width()//2, HO//2-80-ini.get_height()//2))
        blit_mitte(SF_GR.render("🏆 " + s["name"] + " gewinnt!", True, farbe), HO//2+50)
        blit_mitte(SF_MI.render(f"{max_p} Punkte", True, WEISS), HO//2+140)
    else:
        namen = " & ".join(s["name"] for s in sieger)
        blit_mitte(SF_MI.render(f"Unentschieden: {namen}!", True, WEISS), HO//2+50)
        blit_mitte(SF_MI.render(f"{max_p} Punkte", True, WEISS), HO//2+120)
    pygame.display.flip()

# ─────────────────────────────────────────────
#  BUZZER THREAD
# ─────────────────────────────────────────────
buzzer_aktiv = True
buzzer_gesperrt = False
buzzer_start_zeit = None

def buzzer_thread(spieler):
    global buzzer_gesperrt, buzzer_start_zeit
    letzter = {s["nr"]: GPIO.HIGH for s in spieler}
    while buzzer_aktiv:
        if not buzzer_gesperrt:
            for s in spieler:
                jetzt = GPIO.input(s["gpio"])
                if jetzt == GPIO.LOW and letzter[s["nr"]] == GPIO.HIGH:
                    ms = int((time.time() - buzzer_start_zeit) * 1000) if buzzer_start_zeit else 0
                    buzzer_gesperrt = True
                    try:
                        sio.emit('buzzer_gedrueckt', {'nr': s["nr"], 'ms': ms})
                    except: pass
                    befehle.put(('buzzer_local', {'nr': s["nr"], 'ms': ms}))
                letzter[s["nr"]] = jetzt
        time.sleep(0.001)

# ─────────────────────────────────────────────
#  HAUPTPROGRAMM
# ─────────────────────────────────────────────
def main():
    global buzzer_aktiv, buzzer_gesperrt, buzzer_start_zeit

    konfig = lade_konfig()
    spieler = konfig["spieler"]
    spieler_map = {s["nr"]: s for s in spieler}

    gpio_setup(spieler)
    display_setup()
    _foto_cache.clear()

    # Sofort schwarzen Bildschirm zeigen (kein Desktop sichtbar)
    zeige_schwarz()

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
                warteschlange = []
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
                # Nach 2 Sek Punktestand zeigen
                time.sleep(2)
                modus = "punktestand"

            elif befehl == 'zeige_ergebnis':
                richtig = data.get('richtig', False)
                delta = data.get('delta', 10)
                # Punkte aktualisieren
                p_raw = data.get('punkte', {}) if 'punkte' in data else {}
                zeige_ergebnis_screen(richtig, delta)
                time.sleep(2)
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
                buzzer_start_zeit = time.time()
                if modus == "punktestand":
                    modus = "frage"

            elif befehl == 'zeige_sieger':
                p_raw = data.get('punkte', {})
                spieler_liste = data.get('spieler', spieler)
                for nr in punkte:
                    punkte[nr] = p_raw.get(str(nr), p_raw.get(nr, punkte[nr]))
                zeige_sieger_screen(spieler_liste, punkte)
                modus = "sieger"

            elif befehl == 'buzzer_local':
                nr = data.get('nr')
                ms = data.get('ms', 0)
                if not any(e['nr'] == nr for e in warteschlange):
                    warteschlange.append({'nr': nr, 'ms': ms})
                if len(warteschlange) == 1:
                    letzter_gewinner_nr = nr
                    modus = "gewinner"

        # Bildschirm rendern
        if modus == "warten":
            puls += 0.02 * puls_richtung
            if puls >= 1.0: puls_richtung = -1
            if puls <= 0.0: puls_richtung = 1
            zeige_wartebildschirm(puls)

        elif modus == "frage":
            zeige_frage_screen(aktuelle_frage, frage_nr, frage_gesamt, spielmodus, mc_gewaehlt, mc_aufgeloest)

        elif modus == "gewinner":
            if letzter_gewinner_nr and letzter_gewinner_nr in spieler_map:
                s = spieler_map[letzter_gewinner_nr]
                pkt = punkte.get(letzter_gewinner_nr, 0)
                ms = warteschlange[0]['ms'] if warteschlange else 0
                zeige_gewinner_screen(s, pkt, ms, warteschlange, spieler_map)

        elif modus == "punktestand":
            zeige_punktestand_screen(spieler, punkte)

        elif modus == "sieger":
            pass  # Sieger-Screen bleibt stehen

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
