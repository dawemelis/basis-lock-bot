# =============================================================
# BASIS-LOCK bot — datova vrstva
# Spot cena, quarterly futures (Binance USD-M delivery), T-bill sazba.
# =============================================================
import calendar
from datetime import datetime, timedelta, timezone
from io import StringIO

import pandas as pd
import requests

import config


# ---------- pomocne: kalendar expiraci ----------

def posledni_patek(rok, mesic):
    """Posledni patek daneho mesice (den expirace quarterly kontraktu, 08:00 UTC)."""
    posledni_den = calendar.monthrange(rok, mesic)[1]
    d = datetime(rok, mesic, posledni_den, 8, 0, tzinfo=timezone.utc)
    while d.weekday() != 4:  # 4 = patek
        d -= timedelta(days=1)
    return d


def expirace_od(datum):
    """Vrati seznam nadchazejicich quarterly expiraci (brezen/cerven/zari/prosinec)."""
    vysledek = []
    rok = datum.year
    while len(vysledek) < 4:
        for mesic in (3, 6, 9, 12):
            e = posledni_patek(rok, mesic)
            if e > datum:
                vysledek.append(e)
        rok += 1
    return vysledek[:4]


# ---------- zive ceny ----------

def spot_cena():
    r = requests.get(f"{config.BINANCE_SPOT}/api/v3/ticker/price",
                     params={"symbol": config.SPOT_SYMBOL}, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])


def quarterly_kontrakty():
    """Vrati aktivni delivery kontrakty (CURRENT_QUARTER, NEXT_QUARTER) s cenou a expiraci."""
    r = requests.get(f"{config.BINANCE_FUT}/fapi/v1/exchangeInfo", timeout=15)
    r.raise_for_status()
    symboly = [
        s for s in r.json()["symbols"]
        if s["pair"] == config.FUTURES_PAIR
        and s["contractType"] in ("CURRENT_QUARTER", "NEXT_QUARTER")
        and s["status"] == "TRADING"
    ]
    vysledek = []
    for s in symboly:
        rc = requests.get(f"{config.BINANCE_FUT}/fapi/v1/ticker/price",
                          params={"symbol": s["symbol"]}, timeout=10)
        rc.raise_for_status()
        cena = float(rc.json()["price"])
        expirace = datetime.fromtimestamp(s["deliveryDate"] / 1000, tz=timezone.utc)
        vysledek.append({
            "symbol": s["symbol"],
            "typ": s["contractType"],
            "cena": cena,
            "expirace": expirace,
        })
    return sorted(vysledek, key=lambda x: x["expirace"])


# ---------- T-bill sazba ----------

def tbill_sazba():
    """3M T-bill z FRED (DGS3MO). Kdyz selze, vrati fallback z configu."""
    try:
        r = requests.get(config.FRED_DGS3MO, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        df.columns = ["datum", "sazba"]
        df["sazba"] = pd.to_numeric(df["sazba"], errors="coerce")
        posledni = df["sazba"].dropna().iloc[-1]
        return float(posledni) / 100.0
    except Exception:
        return config.TBILL_FALLBACK


# ---------- historicka data pro backtest ----------

def _klines(url, params):
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbav", "tqav", "ignore"])
    df["datum"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close"] = df["close"].astype(float)
    return df[["datum", "close"]]


def historie_spot(start, end):
    """Denni spot klines po davkach 1000 (Binance limit 1500)."""
    kusy = []
    t = start
    while t < end:
        df = _klines(f"{config.BINANCE_SPOT}/api/v3/klines", {
            "symbol": config.SPOT_SYMBOL, "interval": "1d",
            "startTime": int(t.timestamp() * 1000), "limit": 1000})
        if df.empty:
            break
        kusy.append(df)
        t = df["datum"].iloc[-1] + timedelta(days=1)
    out = pd.concat(kusy, ignore_index=True).drop_duplicates("datum")
    return out[out["datum"] <= end]


def historie_quarterly(start, end):
    """Denni klines CURRENT_QUARTER kontraktu jako spojita rada (continuousKlines)."""
    kusy = []
    t = start
    while t < end:
        df = _klines(f"{config.BINANCE_FUT}/fapi/v1/continuousKlines", {
            "pair": config.FUTURES_PAIR, "contractType": "CURRENT_QUARTER",
            "interval": "1d",
            "startTime": int(t.timestamp() * 1000), "limit": 1000})
        if df.empty:
            break
        kusy.append(df)
        t = df["datum"].iloc[-1] + timedelta(days=1)
    out = pd.concat(kusy, ignore_index=True).drop_duplicates("datum")
    return out[out["datum"] <= end]


def historie_tbill(start, end):
    """Denni rada 3M T-bill sazby z FRED; forward-fill na obchodni dny."""
    try:
        r = requests.get(config.FRED_DGS3MO, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        df.columns = ["datum", "sazba"]
        df["datum"] = pd.to_datetime(df["datum"], utc=True)
        df["sazba"] = pd.to_numeric(df["sazba"], errors="coerce") / 100.0
        df = df.ffill()
        return df[(df["datum"] >= start) & (df["datum"] <= end)]
    except Exception:
        # fallback: konstantni sazba
        dny = pd.date_range(start, end, freq="D", tz="UTC")
        return pd.DataFrame({"datum": dny, "sazba": config.TBILL_FALLBACK})
