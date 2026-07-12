# =============================================================
# BASIS-LOCK bot — SQLite databaze
# Pamet bota: kazde denni rozhodnuti a kazdy (papirovy) obchod.
# Stejna filozofie jako databaze.py ve tvem hlavnim projektu.
# =============================================================
import sqlite3
from datetime import datetime, timezone

import config


def _conn():
    return sqlite3.connect(config.DB_FILE)


def init_db():
    """Vytvori tabulky, pokud neexistuji. Volat pri kazdem startu."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS rozhodnuti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cas TEXT NOT NULL,
                spot REAL, futures REAL, kontrakt TEXT,
                dni_do_expirace INTEGER,
                basis_hruba_rocne REAL,      -- anualizovana hruba basis
                basis_cista_rocne REAL,      -- po odecteni nakladu
                tbill REAL, hurdle REAL,
                akce TEXT NOT NULL,          -- ENTER / HOLD / ROLL / CASH / EXPIRY_SETTLE
                poznamka TEXT
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS obchody (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cas_vstup TEXT NOT NULL,
                cas_vystup TEXT,
                kontrakt TEXT NOT NULL,
                spot_vstup REAL, futures_vstup REAL,
                notional REAL,               -- velikost spot nohy v USD
                basis_lock_pct REAL,         -- uzamceny spread po nakladech (% za drzeni)
                ocekavany_zisk REAL,         -- notional * basis_lock_pct
                realizovany_zisk REAL,       -- vyplneno pri expiraci
                stav TEXT NOT NULL           -- OPEN / SETTLED / ROLLED
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS kapital (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cas TEXT NOT NULL,
                celkem REAL NOT NULL,
                nasazeno REAL NOT NULL,      -- v otevrenem obchodu
                rezerva REAL NOT NULL        -- cash / T-bills
            )""")


def ted():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uloz_rozhodnuti(spot, futures, kontrakt, dni, basis_hruba, basis_cista,
                    tbill, hurdle, akce, poznamka=""):
    with _conn() as c:
        c.execute(
            "INSERT INTO rozhodnuti (cas, spot, futures, kontrakt, dni_do_expirace,"
            " basis_hruba_rocne, basis_cista_rocne, tbill, hurdle, akce, poznamka)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ted(), spot, futures, kontrakt, dni, basis_hruba, basis_cista,
             tbill, hurdle, akce, poznamka))


def otevri_obchod(kontrakt, spot, futures, notional, basis_lock_pct):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO obchody (cas_vstup, kontrakt, spot_vstup, futures_vstup,"
            " notional, basis_lock_pct, ocekavany_zisk, stav)"
            " VALUES (?,?,?,?,?,?,?, 'OPEN')",
            (ted(), kontrakt, spot, futures, notional, basis_lock_pct,
             notional * basis_lock_pct))
        return cur.lastrowid


def uzavri_obchod(obchod_id, realizovany_zisk, stav="SETTLED"):
    with _conn() as c:
        c.execute(
            "UPDATE obchody SET cas_vystup=?, realizovany_zisk=?, stav=? WHERE id=?",
            (ted(), realizovany_zisk, stav, obchod_id))


def otevreny_obchod():
    """Vrati posledni otevreny obchod nebo None."""
    with _conn() as c:
        row = c.execute(
            "SELECT id, kontrakt, spot_vstup, futures_vstup, notional, basis_lock_pct"
            " FROM obchody WHERE stav='OPEN' ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return {"id": row[0], "kontrakt": row[1], "spot_vstup": row[2],
            "futures_vstup": row[3], "notional": row[4], "basis_lock_pct": row[5]}


def uloz_kapital(celkem, nasazeno, rezerva):
    with _conn() as c:
        c.execute("INSERT INTO kapital (cas, celkem, nasazeno, rezerva) VALUES (?,?,?,?)",
                  (ted(), celkem, nasazeno, rezerva))


def posledni_kapital():
    with _conn() as c:
        row = c.execute(
            "SELECT cas, celkem, nasazeno, rezerva FROM kapital ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {"cas": row[0], "celkem": row[1], "nasazeno": row[2], "rezerva": row[3]}
