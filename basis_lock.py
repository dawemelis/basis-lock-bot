# =============================================================
# BASIS-LOCK bot — strategie
# Jadro schvalene Court of Claude:
#   1. Zisk se uzamyka pri vstupu: basis = futures - spot.
#   2. Nasazeni JEN kdyz cista anualizovana basis > T-bill + buffer.
#   3. Default stav bota je T-bill portfolio. Obchod je vyjimka.
#   4. Max 50 % kapitalu v obchodu; zbytek = margin rezerva na +100% rally.
# Zadna predikce ceny. Jedina promenna, kterou se bot uci, je exekuce.
# =============================================================
from dataclasses import dataclass

import config


@dataclass
class Signal:
    akce: str                 # "ENTER" / "CASH" / "HOLD" / "ROLL"
    kontrakt: str = ""
    basis_hruba_rocne: float = 0.0
    basis_cista_rocne: float = 0.0
    basis_lock_pct: float = 0.0   # spread po nakladech za celou drzbu (ne rocne)
    dni_do_expirace: int = 0
    hurdle: float = 0.0
    poznamka: str = ""


def anualizovana_basis(spot, futures, dni_do_expirace):
    """Hruba basis prepoctena na rok. Cim dele do expirace, tim mensi anualizace."""
    if dni_do_expirace <= 0 or spot <= 0:
        return 0.0
    hruba = futures / spot - 1.0
    return hruba * 365.0 / dni_do_expirace


def cista_basis_rocne(spot, futures, dni_do_expirace):
    """Basis po odecteni vsech nakladu (poplatky + skluz), anualizovana."""
    if dni_do_expirace <= 0:
        return 0.0
    hruba_lock = futures / spot - 1.0          # spread za drzbu
    cisty_lock = hruba_lock - config.TOTAL_COST
    return cisty_lock * 365.0 / dni_do_expirace


def vyhodnot(spot, kontrakty, tbill, otevrena_pozice=None):
    """
    Hlavni rozhodovaci funkce. Vraci Signal.

    spot            ... aktualni spot cena
    kontrakty       ... list dictu {symbol, cena, expirace, dni} serazeny dle expirace
    tbill           ... rocni T-bill sazba
    otevrena_pozice ... dict s klicem 'kontrakt' nebo None
    """
    hurdle = tbill + config.HURDLE_BUFFER

    # --- mame otevrenou pozici? ---
    if otevrena_pozice is not None:
        aktualni = next((k for k in kontrakty
                         if k["symbol"] == otevrena_pozice["kontrakt"]), None)
        if aktualni is None:
            # kontrakt uz neexistuje -> expiroval -> vyporadat
            return Signal(akce="EXPIRY_SETTLE", kontrakt=otevrena_pozice["kontrakt"],
                          hurdle=hurdle, poznamka="kontrakt expiroval, konvergence")
        if aktualni["dni"] <= config.ROLL_WINDOW_DAYS:
            # blizko expirace: zkusit roll na dalsi kontrakt, pokud projde hurdle
            dalsi = next((k for k in kontrakty
                          if k["symbol"] != aktualni["symbol"]), None)
            if dalsi is not None:
                cista = cista_basis_rocne(spot, dalsi["cena"], dalsi["dni"])
                if cista > hurdle:
                    return Signal(
                        akce="ROLL", kontrakt=dalsi["symbol"],
                        basis_hruba_rocne=anualizovana_basis(spot, dalsi["cena"], dalsi["dni"]),
                        basis_cista_rocne=cista,
                        basis_lock_pct=(dalsi["cena"] / spot - 1.0) - config.TOTAL_COST,
                        dni_do_expirace=dalsi["dni"], hurdle=hurdle,
                        poznamka="roll: dalsi kontrakt splnuje hurdle")
            return Signal(akce="HOLD", kontrakt=aktualni["symbol"],
                          dni_do_expirace=aktualni["dni"], hurdle=hurdle,
                          poznamka="drzime do expirace, roll neprosel hurdle")
        return Signal(akce="HOLD", kontrakt=aktualni["symbol"],
                      dni_do_expirace=aktualni["dni"], hurdle=hurdle,
                      poznamka="zisk uzamcen pri vstupu, drzime")

    # --- zadna pozice: hledame nejlepsi kontrakt nad hurdle ---
    nejlepsi = None
    for k in kontrakty:
        if k["dni"] < config.MIN_DAYS_TO_EXPIRY:
            continue
        cista = cista_basis_rocne(spot, k["cena"], k["dni"])
        if cista > hurdle and (nejlepsi is None or cista > nejlepsi[1]):
            nejlepsi = (k, cista)

    if nejlepsi is None:
        return Signal(akce="CASH", hurdle=hurdle,
                      poznamka="zadny kontrakt nad hurdle -> jsme T-bill portfolio")

    k, cista = nejlepsi
    return Signal(
        akce="ENTER", kontrakt=k["symbol"],
        basis_hruba_rocne=anualizovana_basis(spot, k["cena"], k["dni"]),
        basis_cista_rocne=cista,
        basis_lock_pct=(k["cena"] / spot - 1.0) - config.TOTAL_COST,
        dni_do_expirace=k["dni"], hurdle=hurdle,
        poznamka="cista basis nad hurdle -> uzamykame spread")


def velikost_pozice(kapital):
    """
    Spot noha = max 50 % kapitalu. Zbytek zustava jako margin + rezerva,
    dimenzovano tak, aby +100% rally shortu nezpusobila likvidaci
    (ztrata shortu pri +100 % = notional, kryto rezervou + ziskem spot nohy).
    """
    return kapital * config.DEPLOYED_FRACTION_MAX
