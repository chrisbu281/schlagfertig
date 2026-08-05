#!/usr/bin/env python3
"""
Schlagfertig Cloud-Server
Läuft auf dem NAS (Port 5001).
Verwaltet Benutzerkonten und Fragenbibliotheken.
"""

from flask import Flask, request, jsonify, send_from_directory, Response
import sqlite3, os, json, secrets, hashlib, time, io, csv

app = Flask(__name__)
BASIS   = os.path.dirname(os.path.abspath(__file__))
DB_PFAD = os.path.join(BASIS, "cloud.db")

# ───────────────────────────────── DATENBANK ──────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PFAD)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS benutzer (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            passwort_hash TEXT NOT NULL,
            name          TEXT NOT NULL,
            erstellt_am   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS fragen (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            benutzer_id           INTEGER NOT NULL,
            frage                 TEXT NOT NULL,
            antwort               TEXT NOT NULL,
            kategorie             TEXT DEFAULT 'Allgemein',
            schwierigkeit         TEXT DEFAULT 'leicht',
            modus                 TEXT DEFAULT 'frei',
            antworten_mc          TEXT,
            richtige_antwort_index INTEGER,
            aktiv                 INTEGER DEFAULT 1,
            erstellt_am           TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (benutzer_id) REFERENCES benutzer(id)
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token       TEXT PRIMARY KEY,
            benutzer_id INTEGER NOT NULL,
            erstellt_am INTEGER NOT NULL,
            FOREIGN KEY (benutzer_id) REFERENCES benutzer(id)
        );
    """)
    conn.commit()
    conn.close()

# ─────────────────────────────── HILFSFUNKTIONEN ─────────────────────────────

def hash_pw(pw):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100_000)
    return f"{salt}:{h.hex()}"

def check_pw(pw, stored):
    try:
        salt, h = stored.split(':', 1)
        return hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100_000).hex() == h
    except Exception:
        return False

def neuer_token(benutzer_id):
    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute("INSERT INTO tokens VALUES (?,?,?)", (token, benutzer_id, int(time.time())))
    conn.commit()
    conn.close()
    return token

def authentifiziere(req):
    h = req.headers.get('Authorization', '')
    if not h.startswith('Bearer '):
        return None
    token = h[7:]
    conn = get_db()
    row = conn.execute(
        "SELECT b.* FROM tokens t JOIN benutzer b ON b.id=t.benutzer_id WHERE t.token=?",
        (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def frage_dict(row):
    d = {
        'id': row['id'],
        'frage': row['frage'],
        'antwort': row['antwort'],
        'kategorie': row['kategorie'],
        'schwierigkeit': row['schwierigkeit'],
        'modus': row['modus'],
        'erstellt_am': row['erstellt_am'],
    }
    if row['antworten_mc']:
        d['antworten_mc'] = json.loads(row['antworten_mc'])
        d['richtige_antwort_index'] = row['richtige_antwort_index']
    return d

def cors(resp):
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return resp

@app.after_request
def after(resp):
    return cors(resp)

@app.route('/api/<path:_>', methods=['OPTIONS'])
def options_handler(_):
    return cors(jsonify({}))

# ──────────────────────────────── AUTH-ROUTEN ─────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    d = request.get_json() or {}
    email  = d.get('email',   '').strip().lower()
    pw     = d.get('passwort','')
    name   = d.get('name',    '').strip()

    if not email or not pw or not name:
        return jsonify({"error": "Alle Felder erforderlich"}), 400
    if len(pw) < 6:
        return jsonify({"error": "Passwort zu kurz (min. 6 Zeichen)"}), 400

    try:
        conn = get_db()
        conn.execute("INSERT INTO benutzer (email, passwort_hash, name) VALUES (?,?,?)",
                     (email, hash_pw(pw), name))
        conn.commit()
        uid = conn.execute("SELECT id FROM benutzer WHERE email=?", (email,)).fetchone()['id']
        conn.close()
        return jsonify({"status": "ok", "token": neuer_token(uid), "name": name})
    except sqlite3.IntegrityError:
        return jsonify({"error": "E-Mail bereits registriert"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/auth/login", methods=["POST"])
def login():
    d     = request.get_json() or {}
    email = d.get('email',   '').strip().lower()
    pw    = d.get('passwort','')
    conn  = get_db()
    user  = conn.execute("SELECT * FROM benutzer WHERE email=?", (email,)).fetchone()
    conn.close()
    if not user or not check_pw(pw, user['passwort_hash']):
        return jsonify({"error": "Ungültige Anmeldedaten"}), 401
    return jsonify({"status": "ok", "token": neuer_token(user['id']), "name": user['name']})

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    h = request.headers.get('Authorization', '')
    if h.startswith('Bearer '):
        conn = get_db()
        conn.execute("DELETE FROM tokens WHERE token=?", (h[7:],))
        conn.commit()
        conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/profil")
def get_profil():
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401
    conn = get_db()
    n   = conn.execute("SELECT COUNT(*) AS n FROM fragen WHERE benutzer_id=? AND aktiv=1", (user['id'],)).fetchone()['n']
    kat = conn.execute("SELECT COUNT(DISTINCT kategorie) AS n FROM fragen WHERE benutzer_id=? AND aktiv=1", (user['id'],)).fetchone()['n']
    conn.close()
    return jsonify({"name": user['name'], "email": user['email'],
                    "anzahl_fragen": n, "anzahl_kategorien": kat})

# ──────────────────────────────── FRAGEN-ROUTEN ───────────────────────────────

@app.route("/api/fragen", methods=["GET"])
def get_fragen():
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401

    query  = "SELECT * FROM fragen WHERE benutzer_id=? AND aktiv=1"
    params = [user['id']]

    kat   = request.args.get('kategorie')
    schw  = request.args.get('schwierigkeit')
    mod   = request.args.get('modus')
    suche = request.args.get('suche', '').strip()

    if kat:   query += " AND kategorie=?";        params.append(kat)
    if schw:  query += " AND schwierigkeit=?";    params.append(schw)
    if mod:   query += " AND modus=?";            params.append(mod)
    if suche:
        query += " AND (frage LIKE ? OR antwort LIKE ?)"
        params += [f"%{suche}%", f"%{suche}%"]

    query += " ORDER BY id DESC"

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([frage_dict(r) for r in rows])

@app.route("/api/fragen", methods=["POST"])
def add_fragen():
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401
    data = request.get_json()

    def insert(f):
        mc = json.dumps(f['antworten_mc']) if f.get('antworten_mc') else None
        conn = get_db()
        cur = conn.execute("""
            INSERT INTO fragen
                (benutzer_id, frage, antwort, kategorie, schwierigkeit, modus, antworten_mc, richtige_antwort_index)
            VALUES (?,?,?,?,?,?,?,?)
        """, (user['id'], f['frage'], f['antwort'],
              f.get('kategorie','Allgemein'), f.get('schwierigkeit','leicht'),
              f.get('modus','frei'), mc, f.get('richtige_antwort_index')))
        conn.commit()
        fid = cur.lastrowid
        conn.close()
        return fid

    if isinstance(data, list):
        ids = [insert(f) for f in data]
        return jsonify({"status": "ok", "anzahl": len(ids)})
    return jsonify({"status": "ok", "id": insert(data)})

@app.route("/api/fragen/<int:fid>", methods=["PUT"])
def update_frage(fid):
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401
    f  = request.get_json()
    mc = json.dumps(f['antworten_mc']) if f.get('antworten_mc') else None
    conn = get_db()
    conn.execute("""
        UPDATE fragen
           SET frage=?, antwort=?, kategorie=?, schwierigkeit=?, modus=?,
               antworten_mc=?, richtige_antwort_index=?
         WHERE id=? AND benutzer_id=?
    """, (f['frage'], f['antwort'],
          f.get('kategorie','Allgemein'), f.get('schwierigkeit','leicht'),
          f.get('modus','frei'), mc, f.get('richtige_antwort_index'),
          fid, user['id']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/fragen/<int:fid>", methods=["DELETE"])
def delete_frage(fid):
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401
    conn = get_db()
    conn.execute("UPDATE fragen SET aktiv=0 WHERE id=? AND benutzer_id=?", (fid, user['id']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/fragen/kategorien")
def get_kategorien():
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT kategorie FROM fragen WHERE benutzer_id=? AND aktiv=1 ORDER BY kategorie",
        (user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([r['kategorie'] for r in rows])

@app.route("/api/csv-import", methods=["POST"])
def csv_import():
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401
    if "file" not in request.files:
        return jsonify({"error": "Keine Datei"}), 400

    raw     = request.files["file"].read()
    content = None
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            content = raw.decode(enc); break
        except Exception:
            continue
    if content is None:
        return jsonify({"error": "Datei konnte nicht gelesen werden"}), 400

    modus = request.args.get("modus", "hinzufuegen")   # ersetzen | hinzufuegen
    spielmodus = request.args.get("spielmodus", "frei")

    reader = csv.DictReader(io.StringIO(content))
    fragen, fehler = [], []
    for i, row in enumerate(reader, start=2):
        frage  = row.get("frage",   "").strip()
        antwort = row.get("antwort","").strip()
        if not frage or not antwort:
            fehler.append(f"Zeile {i}: Frage oder Antwort fehlt"); continue
        kat  = row.get("kategorie",    "Allgemein").strip()
        schw = row.get("schwierigkeit","leicht").strip().lower()
        if schw not in ["leicht","mittel","schwer"]: schw = "leicht"
        mc_a = row.get("antwort_a","").strip()
        mc_b = row.get("antwort_b","").strip()
        mc_c = row.get("antwort_c","").strip()
        mc_d = row.get("antwort_d","").strip()
        richtig = row.get("richtige_antwort","").strip().upper()
        fo = {"frage": frage, "antwort": antwort, "kategorie": kat,
              "schwierigkeit": schw, "modus": spielmodus}
        if mc_a and mc_b and mc_c and mc_d:
            fo["antworten_mc"] = [mc_a, mc_b, mc_c, mc_d]
            fo["richtige_antwort_index"] = {"A":0,"B":1,"C":2,"D":3}.get(richtig, 0)
            fo["modus"] = "mc"
        fragen.append(fo)

    if not fragen:
        return jsonify({"error": "Keine gültigen Fragen gefunden", "fehler": fehler}), 400

    conn = get_db()
    if modus == "ersetzen":
        conn.execute("UPDATE fragen SET aktiv=0 WHERE benutzer_id=?", (user['id'],))
        conn.commit()
    for f in fragen:
        mc = json.dumps(f.get('antworten_mc')) if f.get('antworten_mc') else None
        conn.execute("""
            INSERT INTO fragen (benutzer_id, frage, antwort, kategorie, schwierigkeit, modus, antworten_mc, richtige_antwort_index)
            VALUES (?,?,?,?,?,?,?,?)
        """, (user['id'], f['frage'], f['antwort'], f['kategorie'],
              f['schwierigkeit'], f['modus'], mc, f.get('richtige_antwort_index')))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "anzahl": len(fragen), "fehler": fehler})

@app.route("/api/csv-vorlage")
def csv_vorlage():
    v  = "frage,antwort,kategorie,schwierigkeit,antwort_a,antwort_b,antwort_c,antwort_d,richtige_antwort\n"
    v += "Was ist die Hauptstadt von Frankreich?,Paris,Geografie,leicht,Berlin,Paris,Madrid,Rom,B\n"
    v += "Wie viele Planeten hat unser Sonnensystem?,8,Astronomie,leicht,,,,,\n"
    return Response(v, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=schlagfertig_vorlage.csv"})

# ────────────────────────────── PROFIL-EXPORT ─────────────────────────────────
# Dieser Endpoint wird vom Gerät beim Sync aufgerufen.

@app.route("/api/profil/export")
def profil_export():
    user = authentifiziere(request)
    if not user:
        return jsonify({"error": "Nicht angemeldet"}), 401

    query  = "SELECT * FROM fragen WHERE benutzer_id=? AND aktiv=1"
    params = [user['id']]

    kategorien = request.args.getlist('kategorie')
    schw       = request.args.get('schwierigkeit')
    mod        = request.args.get('modus')

    if kategorien:
        query += f" AND kategorie IN ({','.join('?'*len(kategorien))})"
        params.extend(kategorien)
    if schw: query += " AND schwierigkeit=?"; params.append(schw)
    if mod:  query += " AND modus=?";         params.append(mod)

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    fragen = []
    for r in rows:
        f = {"frage": r['frage'], "antwort": r['antwort'], "kategorie": r['kategorie'],
             "schwierigkeit": r['schwierigkeit'], "modus": r['modus'], "basis": False}
        if r['antworten_mc']:
            f['antworten_mc'] = json.loads(r['antworten_mc'])
            f['richtige_antwort_index'] = r['richtige_antwort_index']
        fragen.append(f)

    return jsonify({"name": user['name'], "email": user['email'], "fragen": fragen})

# ─────────────────────────────── FRONTEND ────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(BASIS, "cloud_editor.html")

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("╔══════════════════════════════════════════╗")
    print("║  Schlagfertig Cloud-Server               ║")
    print("║  http://0.0.0.0:5001                     ║")
    print("╚══════════════════════════════════════════╝")
    app.run(host="0.0.0.0", port=5001, debug=False)
