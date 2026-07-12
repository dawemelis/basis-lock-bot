# =============================================================
# BASIS-LOCK bot — smycka (PAPER TRADING), bezpecna pro libovolnou
# frekvenci spousteni (1x denne lokalne i 1x hodinove v cloudu).
#   python bot.py
#
# Cloud: GitHub Actions (viz .github/workflows/bot.yml) - bezi 24/7
# bez zapnuteho pocitace. Zdroj dat podle config.DATA_SOURCE.
#
# Zadne realne penize. Bot jen rozhoduje, loguje a vede papirovy ucet.
# Na ostro (CME pres IBKR) se prepne az po obhajobe v backtestu a paperu.
# =============================================================
from datetime import datetime, timezone

import config
import databaze
import basis_lock

if config.DATA_SOURCE == "cme":
    import cme_data as zdroj
else:
    import basis_data as zdroj


def main():
    databaze.init_db()
    ted = datetime.now(timezone.utc)

    # --- 1. Nacti stav uctu (nebo zaloz novy) ---
    ucet = databaze.posledni_kapital()
    if ucet is None:
        ucet = {"cas": None, "celkem": config.START_CAPITAL, "nasazeno": 0.0,
                "rezerva": config.START_CAPITAL}

    # --- 2. Stahni trzni data ---
    spot = zdroj.spot_cena()
    tbill = zdroj.tbill_sazba()
    kontrakty_raw = zdroj.quarterly_kontrakty()
    kontrakty = [{
        "symbol": k["symbol"], "cena": k["cena"], "expirace": k["expirace"],
        "dni": max((k["expirace"] - ted).days, 0),
        "stale": k.get("stale", False),
    } for k in kontrakty_raw]

    # --- 3. Urok rezervy (T-bill) podle REALNE uplynuleho casu ---
    # (pri hodinovem behu se pripise ~1/24 denniho uroku, ne cely den)
    if ucet["rezerva"] > 0 and ucet["cas"] is not None:
        minule = datetime.fromisoformat(ucet["cas"])
        dt_dny = max((ted - minule).total_seconds() / 86400.0, 0.0)
        urok = ucet["rezerva"] * tbill * dt_dny / 365.0
        ucet["rezerva"] += urok
        ucet["celkem"] += urok

    # --- 4. Vyhodnot strategii ---
    pozice = databaze.otevreny_obchod()
    sig = basis_lock.vyhodnot(spot, kontrakty, tbill, pozice)

    # Ochrana: o vikendu je CME zavrene a cena futures je stara ->
    # nevstupovat a nerolovat na neaktualnich cenach (drzet/cash ano).
    data_stale = any(k["stale"] for k in kontrakty)
    if data_stale and sig.akce in ("ENTER", "ROLL"):
        sig.akce = "CASH" if pozice is None else "HOLD"
        sig.poznamka = "CME zavreno / stara cena futures - cekame na cerstvy trh"

    # --- 5. Proved akci (papirove) ---
    if sig.akce == "ENTER":
        notional = basis_lock.velikost_pozice(ucet["celkem"])
        k = next(k for k in kontrakty if k["symbol"] == sig.kontrakt)
        databaze.otevri_obchod(sig.kontrakt, spot, k["cena"], notional,
                               sig.basis_lock_pct)
        ucet["nasazeno"] = notional
        ucet["rezerva"] = ucet["celkem"] - notional
        print(f"ENTER {sig.kontrakt}: notional {notional:,.0f} USD, "
              f"lock {sig.basis_lock_pct*100:.2f} % za {sig.dni_do_expirace} dni "
              f"({sig.basis_cista_rocne*100:.2f} % rocne, hurdle {sig.hurdle*100:.2f} %)")

    elif sig.akce == "EXPIRY_SETTLE" and pozice is not None:
        zisk = pozice["notional"] * pozice["basis_lock_pct"]
        databaze.uzavri_obchod(pozice["id"], zisk)
        ucet["celkem"] += zisk
        ucet["nasazeno"] = 0.0
        ucet["rezerva"] = ucet["celkem"]
        print(f"SETTLE {pozice['kontrakt']}: realizovano {zisk:,.2f} USD (konvergence)")

    elif sig.akce == "ROLL" and pozice is not None:
        # uzavri stary (konvergence tesne pred expiraci) a otevri novy
        zisk = pozice["notional"] * pozice["basis_lock_pct"]
        databaze.uzavri_obchod(pozice["id"], zisk, stav="ROLLED")
        ucet["celkem"] += zisk
        notional = basis_lock.velikost_pozice(ucet["celkem"])
        k = next(k for k in kontrakty if k["symbol"] == sig.kontrakt)
        databaze.otevri_obchod(sig.kontrakt, spot, k["cena"], notional,
                               sig.basis_lock_pct)
        ucet["nasazeno"] = notional
        ucet["rezerva"] = ucet["celkem"] - notional
        print(f"ROLL -> {sig.kontrakt}: zisk {zisk:,.2f} USD, "
              f"novy lock {sig.basis_lock_pct*100:.2f} %")

    else:  # HOLD / CASH
        print(f"{sig.akce}: {sig.poznamka}")

    # --- 6. Zaloguj vse ---
    nejblizsi = kontrakty[0] if kontrakty else None
    databaze.uloz_rozhodnuti(
        spot,
        nejblizsi["cena"] if nejblizsi else 0.0,
        sig.kontrakt or (nejblizsi["symbol"] if nejblizsi else ""),
        sig.dni_do_expirace,
        sig.basis_hruba_rocne, sig.basis_cista_rocne,
        tbill, sig.hurdle, sig.akce, sig.poznamka)
    databaze.uloz_kapital(ucet["celkem"], ucet["nasazeno"], ucet["rezerva"])

    print(f"Ucet: {ucet['celkem']:,.2f} USD "
          f"(nasazeno {ucet['nasazeno']:,.0f}, rezerva {ucet['rezerva']:,.0f}) | "
          f"spot {spot:,.0f} | T-bill {tbill*100:.2f} %")


if __name__ == "__main__":
    main()
