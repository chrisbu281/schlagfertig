"""Operation Silvester – Agentenspiel-Bot (Minimalversion für den Test).

Start:  python bot.py
Zentrale:  http://localhost:8090        (nur auf diesem Laptop erreichbar)
Beamer:    http://localhost:8090/beamer
"""
import asyncio
import configparser
import logging
import random
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from aiohttp import web
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

BASE = Path(__file__).resolve().parent
FOTOS = BASE / "fotos"
STATIC = BASE / "static"
DB_PATH = BASE / "spiel.db"
GAESTE = BASE / "gaeste.txt"
POINTS = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1}
MAX_WAVE = 5
REVEAL_STEPS = 6

logging.basicConfig(format="%(asctime)s  %(message)s", level=logging.INFO, datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
log = logging.getLogger("agentenspiel")


# ---------------------------------------------------------------- Einstellungen
def load_config():
    path = BASE / "einstellungen.ini"
    if not path.exists():
        sys.exit("einstellungen.ini fehlt: einstellungen.beispiel.ini kopieren, "
                 "in einstellungen.ini umbenennen und den Bot-Schlüssel eintragen.")
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    token = cp.get("bot", "token", fallback="").strip()
    if not token or "HIER" in token:
        sys.exit("In einstellungen.ini fehlt der Bot-Schlüssel (token = ...).")
    return {
        "token": token,
        "pin": cp.get("bot", "pin", fallback="").strip(),
        "port": cp.getint("bot", "port", fallback=8090),
    }


# ---------------------------------------------------------------- Datenbank
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS guests(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, chat_id INTEGER UNIQUE,
            photo INTEGER DEFAULT 0, registered_at TEXT, blocked INTEGER DEFAULT 0,
            opened INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS reports(
            id INTEGER PRIMARY KEY, wave INTEGER, reporter_id INTEGER, suspect_id INTEGER,
            reason TEXT, created_at TEXT, favorite INTEGER DEFAULT 0,
            UNIQUE(wave, reporter_id));
        """)
    sync_guest_list()


def sync_guest_list():
    """Neue Namen aus gaeste.txt übernehmen (vorhandene bleiben)."""
    if not GAESTE.exists():
        return
    names = [l.strip() for l in GAESTE.read_text(encoding="utf-8").splitlines()]
    names = [n for n in names if n and not n.startswith("#")]
    with db() as con:
        for n in names:
            con.execute("INSERT OR IGNORE INTO guests(name) VALUES(?)", (n,))


def get(key, default=None):
    with db() as con:
        r = con.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return r["value"] if r and r["value"] is not None else default


def geti(key, default=0):
    v = get(key)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def put(key, value):
    with db() as con:
        con.execute("INSERT INTO state(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, None if value is None else str(value)))


def phase():
    return get("phase", "anmeldung")


def guest(gid):
    with db() as con:
        return con.execute("SELECT * FROM guests WHERE id=?", (gid,)).fetchone()


def guest_by_chat(chat_id):
    with db() as con:
        return con.execute("SELECT * FROM guests WHERE chat_id=?", (chat_id,)).fetchone()


def all_guests():
    with db() as con:
        return con.execute("SELECT * FROM guests ORDER BY name COLLATE NOCASE").fetchall()


def linked_guests(include_blocked=True):
    gs = [g for g in all_guests() if g["chat_id"] is not None]
    return gs if include_blocked else [g for g in gs if not g["blocked"]]


def reports(wave=None):
    q = ("SELECT r.*, a.name AS reporter, b.name AS suspect FROM reports r "
         "JOIN guests a ON a.id=r.reporter_id JOIN guests b ON b.id=r.suspect_id")
    with db() as con:
        if wave is None:
            return con.execute(q + " ORDER BY r.wave DESC, r.created_at DESC").fetchall()
        return con.execute(q + " WHERE r.wave=? ORDER BY r.created_at DESC", (wave,)).fetchall()


# ---------------------------------------------------------------- Auswertung
def agents_for_scoring():
    spy = geti("spy_id")
    return [g for g in linked_guests(include_blocked=False) if g["id"] != spy]


def standings():
    spy = geti("spy_id")
    rows = []
    with db() as con:
        for g in agents_for_scoring():
            hits = con.execute(
                "SELECT wave, created_at FROM reports WHERE reporter_id=? AND suspect_id=? "
                "ORDER BY wave, created_at", (g["id"], spy)).fetchall()
            pts = sum(POINTS[h["wave"]] for h in hits)
            first = (hits[0]["wave"], hits[0]["created_at"]) if hits else (99, "")
            rows.append({"id": g["id"], "name": g["name"], "points": pts,
                         "first_wave": first[0] if hits else None, "_sort": first})
    rows.sort(key=lambda r: (-r["points"], r["_sort"]))
    for r in rows:
        r.pop("_sort")
    return rows


def verdict():
    """Spion ist ENTTARNT, wenn in Welle 5 mindestens die Hälfte richtig liegt."""
    spy = geti("spy_id")
    agent_ids = {g["id"] for g in agents_for_scoring()}
    w5 = [r for r in reports(MAX_WAVE) if r["reporter_id"] in agent_ids]
    correct = sum(1 for r in w5 if r["suspect_id"] == spy)
    total = len(w5)
    return {"enttarnt": total > 0 and correct * 2 >= total, "correct": correct, "total": total}


def erkannt():
    groups = {}
    for r in standings():
        if r["first_wave"]:
            groups.setdefault(r["first_wave"], []).append(r["name"])
    return [{"wave": w, "names": groups[w]} for w in sorted(groups)]


def favorites():
    with db() as con:
        rows = con.execute(
            "SELECT r.wave, r.reason, a.name AS reporter, b.name AS suspect FROM reports r "
            "JOIN guests a ON a.id=r.reporter_id JOIN guests b ON b.id=r.suspect_id "
            "WHERE r.favorite=1 ORDER BY r.wave").fetchall()
    return [dict(r) for r in rows]


def wave_stats():
    spy = geti("spy_id")
    agent_ids = {g["id"] for g in agents_for_scoring()}
    out = []
    for w in range(1, MAX_WAVE + 1):
        rs = [r for r in reports(w) if r["reporter_id"] in agent_ids]
        out.append({"wave": w, "reports": len(rs),
                    "correct": sum(1 for r in rs if r["suspect_id"] == spy),
                    "sent_at": get(f"wave_{w}_at")})
    return out


# ---------------------------------------------------------------- Texte
PHOTO_TEXT = ("Für eine kleine Überraschung an Silvester brauchen wir ein Foto von dir, "
              "am besten ein Selfie. Mehr wird noch nicht verraten 😉\n\n"
              "Schick es einfach hier in den Chat.\n"
              "(Das Foto kann an Silvester in Spielen auftauchen und wird nach der Party gelöscht.)")

START_TEXT = ("⚠️ STRENG GEHEIM ⚠️\n\nNachricht der Zentrale.\n"
              "Erst öffnen, wenn niemand auf dein Handy schaut.")

AGENT_TEXT = """🕵️ DIENSTAUSWEIS
Agent: {name}
Status: aktiv

AUFTRAG
Unter den Gästen befindet sich ein Spion. Finde heraus, wer es ist.

SO LÄUFT ES
• Die Zentrale schickt dir heute Abend 5 Hinweise.
• Nach jedem Hinweis meldest du einen Verdacht: Name + Begründung.
• Nur wer meldet, bekommt den nächsten Hinweis.
• Je früher du richtig liegst, desto mehr Punkte.
• Ob du richtig liegst, erfährst du erst bei der Auflösung.

EHRLICHKEITSREGEL
Fakten-Fragen werden ehrlich beantwortet. Ausweichen ist erlaubt.

Verrate niemandem, was hier steht."""

SPY_TEXT = """🕵️ DIENSTAUSWEIS
Agent: {name}
Status: aktiv

KLEINGEDRUCKTES – NUR FÜR DICH
Du bist der SPION.

Zeig den ganzen Abend diese Merkmale und leg keins davon ab:
{merkmale}

• Lügen ist verboten, ausweichen erlaubt.
• Du bekommst dieselben Hinweise wie alle.
• Gib zum Schein Verdachtsmeldungen ab – sie zählen nicht.

Viel Glück. Die Zentrale hat dich nie gekannt."""

REASON_REJECT = "Die Zentrale akzeptiert keine Meldungen ohne Begründung, Agent. (Mindestens 4 Wörter.)"


def spy_text(g):
    merkmale = [get(f"hint_{i}") for i in range(1, 5)]
    lines = "\n".join(f"{i}. {m}" for i, m in enumerate(merkmale, 1) if m) or "(trägt die Zentrale noch ein)"
    return SPY_TEXT.format(name=g["name"], merkmale=lines)


# ---------------------------------------------------------------- Senden
async def safe_send(bot, chat_id, text, markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=markup)
        return True
    except TelegramError as e:
        log.warning("Senden an %s fehlgeschlagen: %s", chat_id, e)
        return False


async def broadcast(bot, guests, text, markup=None):
    ok = 0
    for g in guests:
        ok += await safe_send(bot, g["chat_id"], text, markup)
        await asyncio.sleep(0.05)
    return ok


async def notify_admin(bot, text):
    chat = get("admin_chat")
    if chat:
        await safe_send(bot, int(chat), text)


def name_buttons(guests, prefix):
    rows, row = [], []
    for g in guests:
        row.append(Btn(g["name"], callback_data=f"{prefix}{g['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return Kb(rows)


def start_markup():
    return Kb([[Btn("📂 Akte öffnen", callback_data="akte")]])


def melden_markup(wave):
    return Kb([[Btn("🔎 Verdacht melden", callback_data=f"melden:{wave}")]])


# ---------------------------------------------------------------- Telegram: Anmeldung
pending = {}  # chat_id -> {"step": "photo"} | {"step": "reason", "wave": n, "suspect": id}


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    g = guest_by_chat(chat)
    if g:
        await update.message.reply_text(
            f"Du bist schon angemeldet als {g['name']}. Halte dein Handy an Silvester bereit 😉")
        return
    free = [x for x in all_guests() if x["chat_id"] is None]
    if not free:
        await update.message.reply_text("Alle Namen sind schon vergeben. Bitte melde dich bei Christoph.")
        return
    await update.message.reply_text("Hi! Wähle bitte deinen Namen aus der Gästeliste:",
                                    reply_markup=name_buttons(free, "reg:"))


async def on_reg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat_id
    gid = int(q.data.split(":")[1])
    if guest_by_chat(chat):
        await q.answer("Du bist schon angemeldet.")
        return
    with db() as con:
        cur = con.execute("UPDATE guests SET chat_id=?, registered_at=? WHERE id=? AND chat_id IS NULL",
                          (chat, now(), gid))
    if cur.rowcount == 0:
        await q.answer("Dieser Name ist schon vergeben.", show_alert=True)
        return
    await q.answer()
    g = guest(gid)
    await q.edit_message_text(f"Hallo {g['name']}! 👋")
    pending[chat] = {"step": "photo"}
    await ctx.bot.send_message(chat, PHOTO_TEXT,
                               reply_markup=Kb([[Btn("Ohne Foto weiter", callback_data="nophoto")]]))
    n_linked, n_all = len(linked_guests()), len(all_guests())
    log.info("Anmeldung: %s (%d/%d)", g["name"], n_linked, n_all)
    await notify_admin(ctx.bot, f"✅ Angemeldet: {g['name']} ({n_linked}/{n_all})")
    if phase() == "laeuft":  # Nachzügler mitten im Spiel
        await safe_send(ctx.bot, chat, START_TEXT, start_markup())


async def on_nophoto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pending.pop(q.message.chat_id, None)
    await q.answer()
    await q.edit_message_text("Alles klar, dann ohne Foto. Wir sehen uns an Silvester 🎆\n"
                              "(Du kannst später jederzeit noch ein Foto schicken.)")


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    g = guest_by_chat(chat)
    if not g:
        await update.message.reply_text("Bitte melde dich zuerst mit /start an.")
        return
    msg = update.message
    tg_file = await (msg.photo[-1].get_file() if msg.photo else msg.document.get_file())
    FOTOS.mkdir(exist_ok=True)
    await tg_file.download_to_drive(FOTOS / f"{g['id']}.jpg")
    with db() as con:
        con.execute("UPDATE guests SET photo=1 WHERE id=?", (g["id"],))
    if pending.get(chat, {}).get("step") == "photo":
        pending.pop(chat, None)
    await msg.reply_text(f"Danke, {g['name']}! Das war's schon. Wir sehen uns an Silvester 🎆")
    log.info("Foto von %s", g["name"])
    await notify_admin(ctx.bot, f"📸 Foto von {g['name']}")


async def cmd_zentrale(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pin = CONFIG["pin"]
    if pin and ctx.args and ctx.args[0] == pin:
        put("admin_chat", update.effective_chat.id)
        await update.message.reply_text("🛰 Zentrale verbunden. Du bekommst ab jetzt jede Anmeldung gemeldet.")
    else:
        await update.message.reply_text("Unbekannter Befehl.")


# ---------------------------------------------------------------- Telegram: Spiel
async def on_akte(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    g = guest_by_chat(q.message.chat_id)
    await q.answer()
    if not g:
        return
    with db() as con:
        con.execute("UPDATE guests SET opened=1 WHERE id=?", (g["id"],))
    text = spy_text(g) if g["id"] == geti("spy_id") else AGENT_TEXT.format(name=g["name"])
    await q.edit_message_text(text)


def report_error(g, wave):
    if g["blocked"]:
        return "Die Zentrale hat dich vom Einsatz abgezogen."
    if phase() != "laeuft" or geti("wave") != wave:
        return "Diese Welle ist schon vorbei. Warte auf die nächste."
    with db() as con:
        if con.execute("SELECT 1 FROM reports WHERE wave=? AND reporter_id=?", (wave, g["id"])).fetchone():
            return "Du hast für diese Welle schon gemeldet."
    return None


async def on_melden(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat_id
    g = guest_by_chat(chat)
    wave = int(q.data.split(":")[1])
    if not g:
        await q.answer("Bitte zuerst mit /start anmelden.", show_alert=True)
        return
    err = report_error(g, wave)
    if err:
        await q.answer(err, show_alert=True)
        return
    await q.answer()
    others = [x for x in linked_guests() if x["id"] != g["id"]]
    await ctx.bot.send_message(chat, f"Welle {wave}: Wen verdächtigst du, Agent?",
                               reply_markup=name_buttons(others, f"sus:{wave}:"))


async def on_suspect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = q.message.chat_id
    g = guest_by_chat(chat)
    _, wave, sid = q.data.split(":")
    wave, sid = int(wave), int(sid)
    err = report_error(g, wave) if g else "Bitte zuerst mit /start anmelden."
    if err:
        await q.answer(err, show_alert=True)
        return
    await q.answer()
    s = guest(sid)
    pending[chat] = {"step": "reason", "wave": wave, "suspect": sid}
    await q.edit_message_text(
        f"Verdacht: {s['name']}\n\nJetzt die Begründung: Was hat {s['name']} vor, "
        f"und woran hast du es gemerkt?\nSchreib es einfach als Nachricht.")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    g = guest_by_chat(chat)
    p = pending.get(chat)
    if not g:
        await update.message.reply_text("Bitte melde dich zuerst mit /start an.")
        return
    if not p or p["step"] != "reason":
        await update.message.reply_text("Die Zentrale meldet sich, sobald es Neues gibt. 🕵️")
        return
    text = update.message.text.strip()
    if len(text.split()) < 4:
        await update.message.reply_text(REASON_REJECT)
        return
    err = report_error(g, p["wave"])
    pending.pop(chat, None)
    if err:
        await update.message.reply_text(err)
        return
    with db() as con:
        con.execute("INSERT INTO reports(wave, reporter_id, suspect_id, reason, created_at) VALUES(?,?,?,?,?)",
                    (p["wave"], g["id"], p["suspect"], text, now()))
    log.info("Meldung W%d: %s -> %s", p["wave"], g["name"], guest(p["suspect"])["name"])
    if p["wave"] == MAX_WAVE:
        await update.message.reply_text("📨 Deine letzte Meldung ist eingegangen. Die Auflösung folgt …")
    else:
        await update.message.reply_text("📨 Meldung bei der Zentrale eingegangen. "
                                        "Halte dich bereit für die nächste Welle.")


# ---------------------------------------------------------------- Web: Zentrale
def ok(**kw):
    return web.json_response({"ok": True, **kw})


def fail(msg):
    return web.json_response({"ok": False, "error": msg})


async def api_state(request):
    spy = geti("spy_id")
    guests = []
    for g in all_guests():
        guests.append({"id": g["id"], "name": g["name"], "linked": g["chat_id"] is not None,
                       "photo": bool(g["photo"]), "blocked": bool(g["blocked"]),
                       "opened": bool(g["opened"]), "is_spy": g["id"] == spy})
    reps = [{"id": r["id"], "wave": r["wave"], "reporter": r["reporter"], "reporter_id": r["reporter_id"],
             "suspect": r["suspect"], "correct": r["suspect_id"] == spy, "reason": r["reason"],
             "time": r["created_at"][11:16], "favorite": bool(r["favorite"]),
             "by_spy": r["reporter_id"] == spy} for r in reports()]
    return web.json_response({
        "phase": phase(), "wave": geti("wave"), "spy_id": spy,
        "hints": {i: get(f"hint_{i}", "") for i in range(1, MAX_WAVE + 1)},
        "finale_other": geti("finale_other"), "reveal_step": geti("reveal_step"),
        "reveal_steps": REVEAL_STEPS, "admin_connected": bool(get("admin_chat")),
        "guests": guests, "reports": reps, "wave_stats": wave_stats(),
        "standings": standings(), "verdict": verdict(),
        "video": (STATIC / "flucht.mp4").exists(),
    })


async def api_settings(request):
    data = await request.json()
    if "spy_id" in data:
        if phase() != "anmeldung":
            return fail("Der Spion lässt sich nach dem Spielstart nicht mehr ändern.")
        put("spy_id", int(data["spy_id"] or 0))
    for i in range(1, 5):
        if f"hint_{i}" in data and geti("wave") < i:
            put(f"hint_{i}", data[f"hint_{i}"].strip())
    if "finale_other" in data and geti("wave") < MAX_WAVE:
        put("finale_other", int(data["finale_other"] or 0))
    return ok()


async def api_start(request):
    bot = request.app["bot"]
    if phase() != "anmeldung":
        return fail("Das Spiel läuft schon.")
    spy = guest(geti("spy_id"))
    if not spy or spy["chat_id"] is None:
        return fail("Erst einen angemeldeten Spion auswählen.")
    put("phase", "laeuft")
    put("wave", 0)
    put("started_at", now())
    n = await broadcast(bot, linked_guests(include_blocked=False), START_TEXT, start_markup())
    log.info("SPIEL GESTARTET – %d Nachrichten", n)
    return ok(sent=n)


async def api_next(request):
    bot = request.app["bot"]
    if phase() != "laeuft":
        return fail("Das Spiel läuft gerade nicht.")
    wave = geti("wave") + 1
    if wave > MAX_WAVE:
        return fail("Alle 5 Wellen sind gelaufen. Jetzt kommt die Auflösung.")
    spy = guest(geti("spy_id"))
    if wave < MAX_WAVE:
        hint = get(f"hint_{wave}", "")
        if not hint:
            return fail(f"Für Welle {wave} ist noch kein Hinweis eingetragen.")
    else:
        other = guest(geti("finale_other"))
        if not other or other["id"] == spy["id"] or other["chat_id"] is None:
            choices = [g for g in linked_guests(include_blocked=False) if g["id"] != spy["id"]]
            if not choices:
                return fail("Es gibt keinen zweiten Namen für das Finale.")
            other = random.choice(choices)
        a, b = random.sample([spy["name"], other["name"]], 2)
        hint = f"Der Spion ist einer dieser beiden: {a} oder {b}."
        put("hint_5", hint)
    put("wave", wave)
    put(f"wave_{wave}_at", now()[11:16])

    guests = linked_guests(include_blocked=False)
    if wave == 1:
        receivers, missed = guests, []
    else:
        done = {r["reporter_id"] for r in reports(wave - 1)}
        receivers = [g for g in guests if g["id"] in done or g["id"] == spy["id"]]
        rec_ids = {g["id"] for g in receivers}
        missed = [g for g in guests if g["id"] not in rec_ids]
    last = "\n\nDas ist die LETZTE Meldung des Abends!" if wave == MAX_WAVE else ""
    text = (f"📡 WELLE {wave} von {MAX_WAVE}\n\nDie Zentrale hat abgefangen:\n„{hint}“\n\n"
            f"Melde jetzt deinen Verdacht. Nur wer meldet, bekommt den nächsten Hinweis.{last}")
    sent = await broadcast(bot, receivers, text, melden_markup(wave))
    miss_text = (f"📡 WELLE {wave} läuft – aber du hast die letzte Meldung verpasst, "
                 f"deshalb gibt es diesen Hinweis nicht für dich.\n\n"
                 f"Melde jetzt einen Verdacht, dann bist du bei der nächsten Welle wieder dabei.")
    await broadcast(bot, missed, miss_text, melden_markup(wave))
    log.info("WELLE %d – Hinweis an %d, verpasst: %d", wave, sent, len(missed))
    return ok(sent=sent, missed=len(missed))


async def api_block(request):
    data = await request.json()
    with db() as con:
        con.execute("UPDATE guests SET blocked=? WHERE id=?", (1 if data.get("blocked") else 0, int(data["id"])))
    return ok()


async def api_fav(request):
    data = await request.json()
    with db() as con:
        con.execute("UPDATE reports SET favorite = 1 - favorite WHERE id=?", (int(data["id"]),))
    return ok()


async def api_unlink(request):
    data = await request.json()
    gid = int(data["id"])
    if phase() != "anmeldung":
        return fail("Während des Spiels nicht möglich.")
    with db() as con:
        con.execute("UPDATE guests SET chat_id=NULL, photo=0, registered_at=NULL, opened=0 WHERE id=?", (gid,))
    (FOTOS / f"{gid}.jpg").unlink(missing_ok=True)
    return ok()


async def api_reveal(request):
    bot = request.app["bot"]
    if phase() != "laeuft":
        return fail("Das Spiel läuft gerade nicht.")
    put("phase", "aufloesung")
    put("reveal_step", 0)
    await broadcast(bot, linked_guests(), "🎬 Die Auflösung beginnt – alle Augen auf den Bildschirm!")
    return ok()


async def api_step(request):
    data = await request.json()
    if phase() != "aufloesung":
        return fail("Erst die Auflösung starten.")
    step = max(0, min(REVEAL_STEPS, geti("reveal_step") + int(data.get("delta", 1))))
    put("reveal_step", step)
    return ok(step=step)


async def api_reset(request):
    data = await request.json()
    with db() as con:
        con.execute("DELETE FROM reports")
        con.execute("UPDATE guests SET blocked=0, opened=0")
        con.execute("DELETE FROM state WHERE key NOT IN ('admin_chat', 'spy_id', "
                    "'hint_1', 'hint_2', 'hint_3', 'hint_4', 'finale_other')")
        if data.get("all"):
            con.execute("UPDATE guests SET chat_id=NULL, photo=0, registered_at=NULL")
            con.execute("DELETE FROM state WHERE key IN ('spy_id', 'finale_other')")
    if data.get("all") and FOTOS.exists():
        shutil.rmtree(FOTOS)
    sync_guest_list()
    pending.clear()
    log.info("ZURÜCKGESETZT (%s)", "alles" if data.get("all") else "nur Spiel")
    return ok()


async def api_reload_guests(request):
    sync_guest_list()
    return ok(count=len(all_guests()))


# ---------------------------------------------------------------- Web: Beamer
async def api_beamer(request):
    d = {"phase": phase(), "step": geti("reveal_step"), "wave": geti("wave")}
    if d["phase"] != "aufloesung":
        return web.json_response(d)
    step = d["step"]
    spy = guest(geti("spy_id"))
    if step >= 1:
        d["spy"] = {"id": spy["id"], "name": spy["name"], "photo": bool(spy["photo"])}
    if step >= 2:
        d["verdict"] = verdict()
    if step >= 3:
        d["video"] = (STATIC / "flucht.mp4").exists()
    if step >= 4:
        d["erkannt"] = erkannt()
    if step >= 5:
        d["theorien"] = favorites()
    if step >= 6:
        d["rangliste"] = standings()[:10]
    return web.json_response(d)


SILHOUETTE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 240">
<rect width="200" height="240" fill="#2b323d"/><circle cx="100" cy="90" r="46" fill="#4a5361"/>
<path d="M20 240c0-60 36-96 80-96s80 36 80 96z" fill="#4a5361"/>
<text x="100" y="105" font-size="48" text-anchor="middle" fill="#8d96a3" font-family="sans-serif">?</text></svg>"""


async def foto(request):
    gid = int(request.match_info["gid"])
    path = FOTOS / f"{gid}.jpg"
    if path.exists():
        return web.FileResponse(path, headers={"Cache-Control": "no-store"})
    return web.Response(text=SILHOUETTE, content_type="image/svg+xml")


async def page(request, name):
    return web.FileResponse(BASE / name, headers={"Cache-Control": "no-store"})


def make_web_app(bot):
    app = web.Application()
    app["bot"] = bot
    app.add_routes([
        web.get("/", lambda r: page(r, "zentrale.html")),
        web.get("/beamer", lambda r: page(r, "beamer.html")),
        web.get("/api/state", api_state),
        web.get("/api/beamer", api_beamer),
        web.get("/foto/{gid}", foto),
        web.post("/api/settings", api_settings),
        web.post("/api/start", api_start),
        web.post("/api/next", api_next),
        web.post("/api/block", api_block),
        web.post("/api/fav", api_fav),
        web.post("/api/unlink", api_unlink),
        web.post("/api/reveal", api_reveal),
        web.post("/api/step", api_step),
        web.post("/api/reset", api_reset),
        web.post("/api/reload_guests", api_reload_guests),
    ])
    STATIC.mkdir(exist_ok=True)
    app.router.add_static("/static/", STATIC)
    return app


async def start_web(application: Application):
    runner = web.AppRunner(make_web_app(application.bot))
    await runner.setup()
    # 127.0.0.1: Die Zentrale ist NUR auf diesem Laptop erreichbar, nicht im WLAN.
    await web.TCPSite(runner, "127.0.0.1", CONFIG["port"]).start()
    me = await application.bot.get_me()
    log.info("Bot @%s läuft.  Zentrale: http://localhost:%d   Beamer: http://localhost:%d/beamer",
             me.username, CONFIG["port"], CONFIG["port"])


# ---------------------------------------------------------------- Start
CONFIG = {}


def main():
    CONFIG.update(load_config())
    init_db()
    if not all_guests():
        log.warning("gaeste.txt ist leer – bitte Namen eintragen (einer pro Zeile).")
    app = Application.builder().token(CONFIG["token"]).post_init(start_web).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("zentrale", cmd_zentrale))
    app.add_handler(CallbackQueryHandler(on_reg, pattern=r"^reg:"))
    app.add_handler(CallbackQueryHandler(on_nophoto, pattern=r"^nophoto$"))
    app.add_handler(CallbackQueryHandler(on_akte, pattern=r"^akte$"))
    app.add_handler(CallbackQueryHandler(on_melden, pattern=r"^melden:"))
    app.add_handler(CallbackQueryHandler(on_suspect, pattern=r"^sus:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
