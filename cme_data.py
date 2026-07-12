# =============================================================
# BASIS-LOCK bot — datova vrstva pro CLOUD (CME pres Yahoo Finance)
# Proc: GitHub Actions runnery bezi v USA a Binance API vraci z US IP
# adres HTTP 451. CME data pres Yahoo funguji odkudkoli — a CME je
# navic cilova infrastruktura schvalene petice.
#
# Stejne rozhrani jako basis_data: spot_cena, quarterly_kontrakty, tbill_sazba.
# =============================================================
from datetime import datetime, timezone

import yfinance as yf

# znovupouzivame kalendar expiraci a T-bill z binance vrstvy
from basis_data import posledni_patek, tbill_sazba  # noqa: F401


def _posledni_close(ticker):
    """Posledni denni close + jeho datum."""
    h = yf.Ticker(ticker).history(period="5d", interval="1d")
    if h.empty:
        raise RuntimeError(f"Yahoo nevratilo data pro {ticker}")
    return float(h["Close"].iloc[-1]), h.index[-1].to_pydatetime()


def spot_cena():
    cena, _ = _posledni_close("BTC-USD")
    return cena


def quarterly_kontrakty():
    """
    CME Bitcoin futures maji mesicni kontrakty, expiraci posledni patek
    mesice. Yahoo 'BTC=F' = front-month kontrakt. Vracime jeden kontrakt
    ve stejnem formatu jako Binance vrstva.
    """
    ted = datetime.now(timezone.utc)
    e = posledni_patek(ted.year, ted.month)
    if e <= ted:  # expirace tenhle mesic uz probehla -> dalsi mesic
        rok = ted.year + 1 if ted.month == 12 else ted.year
        mesic = 1 if ted.month == 12 else ted.month + 1
        e = posledni_patek(rok, mesic)

    cena, cas_close = _posledni_close("BTC=F")
    stale = (ted - cas_close.astimezone(timezone.utc)).days >= 3

    return [{
        "symbol": f"BTC_{e:%Y%m%d}.CME",
        "typ": "FRONT_MONTH",
        "cena": cena,
        "expirace": e,
        "stale": stale,   # True = trh je davno zavreny, cena neaktualni
    }]
