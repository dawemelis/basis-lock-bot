# =============================================================
# BASIS-LOCK bot — konfigurace
# Vsechny parametry strategie na jednom miste.
# =============================================================

# --- Zdroj dat ---
# "cme"     = CME futures pres Yahoo (cloud/GitHub Actions - Binance blokuje US IP)
# "binance" = Binance quarterly (lokalni vyvoj a backtest)
DATA_SOURCE = "cme"

# --- Trh ---
SPOT_SYMBOL = "BTCUSDT"          # spot par na Binance
FUTURES_PAIR = "BTCUSDT"         # podklad pro quarterly futures (USD-M delivery)

# --- Hurdle (prah pro nasazeni kapitalu) ---
# Bot obchoduje JEN kdyz: anualizovana cista basis > TBILL + BUFFER
TBILL_FALLBACK = 0.043           # zalozni rocni sazba T-bill (4.3 %), kdyz FRED nejede
HURDLE_BUFFER = 0.02             # bezpecnostni naraznik +2 p.b. rocne

# --- Naklady (konzervativne) ---
FEE_SPOT = 0.001                 # 0.10 % poplatek spot (vstup)
FEE_FUT = 0.0005                 # 0.05 % taker futures (vstup)
SLIPPAGE = 0.0005                # 0.05 % skluz na kazdou nohu
# Celkove naklady na cely obchod (vstup obou noh + konvergence = exit zdarma u cash-settled):
TOTAL_COST = FEE_SPOT + FEE_FUT + 2 * SLIPPAGE   # = 0.25 % z notional

# --- Rizeni rizika (podle schvalene petice) ---
DEPLOYED_FRACTION_MAX = 0.50     # max 50 % kapitalu do obchodu (spot noha)
# Zbylych 50 % = margin + rezerva v T-bills dimenzovana na +100% rally bez likvidace.
MIN_DAYS_TO_EXPIRY = 7           # do expirace < 7 dni -> uz nevstupovat, jen rolovat/drzet
ROLL_WINDOW_DAYS = 5             # okno pred expiraci, kdy zvazujeme roll na dalsi kontrakt

# --- Paper trading ---
START_CAPITAL = 10_000.0         # startovni papirovy kapital v USD
DB_FILE = "basis_lock.db"        # SQLite databa