"""
market_data_store.py — Historical Market Data Store
HIVE MIND ALPHA · Action 3

SQLite database that accumulates:
  - Daily OHLCV for all 22 instruments (NSE/Groww)
  - Intraday 5-minute candles (Groww API when available)
  - Daily PCR history (options chain)
  - Daily VIX history
  - Daily FII net flows
  - Signal fire log (for calibration)

Why SQLite over files:
  - Atomic writes (no corruption on crash)
  - Indexed queries (fast range lookups)
  - Single file on VPS (/root/hivemind-alpha/market_data.db)
  - Zero infrastructure — no Postgres/Redis needed

Schema is append-only. Records are never deleted (only inserted).
This gives you the full audit trail needed for walk-forward calibration.
"""

import sqlite3
import json
import os
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
import pytz

IST = pytz.timezone("Asia/Kolkata")
DB_PATH = os.path.join(os.path.dirname(__file__), "market_data.db")


# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
-- Daily OHLCV for each instrument
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    date          TEXT NOT NULL,          -- YYYY-MM-DD
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL NOT NULL,
    volume        INTEGER,
    delivery_pct  REAL,
    source        TEXT DEFAULT 'NSE',
    inserted_at   TEXT,
    UNIQUE(symbol, date)
);

-- Intraday 5-minute candles
CREATE TABLE IF NOT EXISTS intraday_5m (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    datetime    TEXT NOT NULL,            -- YYYY-MM-DD HH:MM:SS
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL NOT NULL,
    volume      INTEGER,
    inserted_at TEXT,
    UNIQUE(symbol, datetime)
);

-- Daily PCR for NIFTY and BANKNIFTY
CREATE TABLE IF NOT EXISTS daily_pcr (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,        -- NIFTY or BANKNIFTY
    date            TEXT NOT NULL,
    pcr             REAL,
    total_ce_oi     INTEGER,
    total_pe_oi     INTEGER,
    max_pain        REAL,
    ce_resistance   REAL,
    pe_support      REAL,
    gamma_wall      REAL,
    spot_price      REAL,
    expiry          TEXT,
    inserted_at     TEXT,
    UNIQUE(symbol, date)
);

-- Daily VIX
CREATE TABLE IF NOT EXISTS daily_vix (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,
    vix         REAL NOT NULL,
    change      REAL,
    change_pct  REAL,
    inserted_at TEXT
);

-- Daily FII/DII flows
CREATE TABLE IF NOT EXISTS daily_fii (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,
    fii_net     REAL,
    fii_buy     REAL,
    fii_sell    REAL,
    dii_net     REAL,
    dii_buy     REAL,
    dii_sell    REAL,
    inserted_at TEXT
);

-- Signal fire log — every signal the scanner computes
CREATE TABLE IF NOT EXISTS signal_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT,
    symbol          TEXT NOT NULL,
    fired_at        TEXT NOT NULL,        -- ISO datetime
    direction       TEXT,                 -- LONG or SHORT
    probability     REAL,
    recommendation  TEXT,
    entry_price     REAL,
    stop_loss       REAL,
    target_1        REAL,
    target_2        REAL,
    atr             REAL,
    kelly_fraction  REAL,
    quantity        INTEGER,
    fired_signals   TEXT,                 -- JSON list of signal names
    n_groups        INTEGER,
    nlp_verdict     TEXT,
    regime          TEXT,
    paper_only      INTEGER DEFAULT 1,    -- 1=paper, 0=live
    inserted_at     TEXT
);

-- Signal outcomes — filled in when price hits SL or target
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_log_id   INTEGER REFERENCES signal_log(id),
    trade_id        TEXT,
    symbol          TEXT,
    direction       TEXT,
    entry_price     REAL,
    exit_price      REAL,
    exit_type       TEXT,                 -- SL | TARGET_1 | TARGET_2 | TIME_EXIT
    exit_date       TEXT,
    holding_days    INTEGER,
    pnl_pct         REAL,
    pnl_abs         REAL,
    won             INTEGER,              -- 1=win, 0=loss
    fired_signals   TEXT,                 -- JSON — for per-signal win rate calc
    inserted_at     TEXT
);

-- Calibrated win rates — updated by calibrate_signals.py
CREATE TABLE IF NOT EXISTS calibrated_win_rates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name     TEXT NOT NULL,
    regime          TEXT DEFAULT 'ALL',
    win_rate        REAL,
    avg_win_pct     REAL,
    avg_loss_pct    REAL,
    sharpe          REAL,
    n_observations  INTEGER,
    ci_95_low       REAL,
    ci_95_high      REAL,
    calibrated_at   TEXT,
    UNIQUE(signal_name, regime)
);

CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_symbol_date ON daily_ohlcv(symbol, date);
CREATE INDEX IF NOT EXISTS idx_intraday_symbol_dt ON intraday_5m(symbol, datetime);
CREATE INDEX IF NOT EXISTS idx_signal_log_symbol ON signal_log(symbol, fired_at);
CREATE INDEX IF NOT EXISTS idx_outcomes_signal ON signal_outcomes(signal_log_id);
"""


# ── Connection ─────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Write-ahead logging for concurrency
    conn.execute("PRAGMA synchronous=NORMAL") # Balance safety vs speed
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ── OHLCV writers ──────────────────────────────────────────────────────────────

def upsert_daily_ohlcv(symbol: str, candles: List[dict], source: str = "NSE"):
    """
    Insert or update daily OHLCV records.
    candles: list of {datetime/date, open, high, low, close, volume, delivery_pct}
    Uses INSERT OR IGNORE so existing records are never overwritten.
    """
    if not candles:
        return 0
    now = datetime.now(IST).isoformat()
    conn = get_conn()
    inserted = 0
    for c in candles:
        dt_raw = c.get("datetime") or c.get("date","")
        dt_str = str(dt_raw)[:10]   # Take YYYY-MM-DD portion only
        try:
            conn.execute("""
                INSERT OR IGNORE INTO daily_ohlcv
                (symbol, date, open, high, low, close, volume, delivery_pct, source, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol.upper(), dt_str,
                c.get("open"), c.get("high"), c.get("low"), c.get("close"),
                c.get("volume"), c.get("delivery_pct"),
                source, now,
            ))
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted


def upsert_intraday_5m(symbol: str, candles: List[dict]):
    """Insert 5-minute intraday candles."""
    if not candles:
        return 0
    now = datetime.now(IST).isoformat()
    conn = get_conn()
    inserted = 0
    for c in candles:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO intraday_5m
                (symbol, datetime, open, high, low, close, volume, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol.upper(),
                str(c.get("datetime", c.get("date",""))),
                c.get("open"), c.get("high"), c.get("low"), c.get("close"),
                c.get("volume"), now,
            ))
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted


# ── PCR / VIX / FII writers ────────────────────────────────────────────────────

def upsert_pcr(symbol: str, data: dict, trade_date: str = None):
    """Store today's PCR data for NIFTY or BANKNIFTY."""
    if not data.get("success"):
        return
    today = trade_date or date.today().isoformat()
    now   = datetime.now(IST).isoformat()
    conn  = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO daily_pcr
            (symbol, date, pcr, total_ce_oi, total_pe_oi, max_pain,
             ce_resistance, pe_support, gamma_wall, spot_price, expiry, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol.upper(), today,
            data.get("pcr"), data.get("total_ce_oi"), data.get("total_pe_oi"),
            data.get("max_pain"), data.get("ce_resistance"), data.get("pe_support"),
            data.get("gamma_wall"), data.get("spot_price"), data.get("expiry"), now,
        ))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def upsert_vix(vix_value: float, change: float = 0.0,
               change_pct: float = 0.0, trade_date: str = None):
    """Store today's VIX."""
    today = trade_date or date.today().isoformat()
    now   = datetime.now(IST).isoformat()
    conn  = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO daily_vix (date, vix, change, change_pct, inserted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (today, vix_value, change, change_pct, now))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def upsert_fii(data: dict, trade_date: str = None):
    """Store today's FII/DII flows."""
    if not data.get("success"):
        return
    today = trade_date or date.today().isoformat()
    now   = datetime.now(IST).isoformat()
    td    = data.get("today", {})
    conn  = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO daily_fii
            (date, fii_net, fii_buy, fii_sell, dii_net, dii_buy, dii_sell, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today,
            td.get("fii_net", data.get("fii_net_today")),
            td.get("fii_buy"), td.get("fii_sell"),
            td.get("dii_net", data.get("dii_net_today")),
            td.get("dii_buy"), td.get("dii_sell"),
            now,
        ))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# ── Signal log writers ─────────────────────────────────────────────────────────

def log_signal_fired(trade_id: str, symbol: str, direction: str,
                      probability: float, recommendation: str,
                      entry: float, sl: float, t1: float, t2: float,
                      atr: float, kelly_fraction: float, quantity: int,
                      fired_signals: list, n_groups: int,
                      nlp_verdict: str, regime: str,
                      paper_only: bool = True) -> int:
    """Log a fired signal. Returns the row ID."""
    now  = datetime.now(IST).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO signal_log
            (trade_id, symbol, fired_at, direction, probability, recommendation,
             entry_price, stop_loss, target_1, target_2, atr, kelly_fraction,
             quantity, fired_signals, n_groups, nlp_verdict, regime,
             paper_only, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, symbol.upper(), now, direction, probability, recommendation,
            entry, sl, t1, t2, atr, kelly_fraction, quantity,
            json.dumps([s.get("signal","") for s in fired_signals]),
            n_groups, nlp_verdict, regime,
            1 if paper_only else 0, now,
        ))
        conn.commit()
        return cur.lastrowid
    except Exception:
        return -1
    finally:
        conn.close()


def log_signal_outcome(signal_log_id: int, trade_id: str, symbol: str,
                        direction: str, entry_price: float, exit_price: float,
                        exit_type: str, exit_date: str, holding_days: int,
                        fired_signals: list):
    """Record outcome when a signal's trade closes."""
    if direction == "LONG":
        pnl_pct = (exit_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - exit_price) / entry_price * 100
    pnl_abs = pnl_pct / 100 * entry_price
    won     = 1 if pnl_pct > 0 else 0
    now     = datetime.now(IST).isoformat()
    conn    = get_conn()
    try:
        conn.execute("""
            INSERT INTO signal_outcomes
            (signal_log_id, trade_id, symbol, direction, entry_price, exit_price,
             exit_type, exit_date, holding_days, pnl_pct, pnl_abs, won,
             fired_signals, inserted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_log_id, trade_id, symbol, direction,
            entry_price, exit_price, exit_type, exit_date,
            holding_days, round(pnl_pct, 4), round(pnl_abs, 4), won,
            json.dumps([s.get("signal","") for s in fired_signals]),
            now,
        ))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def save_calibrated_win_rates(rates: dict):
    """Write calibrated win rates to DB. Called by calibrate_signals.py."""
    now  = datetime.now(IST).isoformat()
    conn = get_conn()
    for signal_name, r in rates.items():
        for regime, stats in r.items():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO calibrated_win_rates
                    (signal_name, regime, win_rate, avg_win_pct, avg_loss_pct,
                     sharpe, n_observations, ci_95_low, ci_95_high, calibrated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal_name, regime,
                    stats.get("win_rate"), stats.get("avg_win_pct"),
                    stats.get("avg_loss_pct"), stats.get("sharpe"),
                    stats.get("n"), stats.get("ci_low"), stats.get("ci_high"),
                    now,
                ))
            except Exception:
                pass
    conn.commit()
    conn.close()


# ── Readers ────────────────────────────────────────────────────────────────────

def get_daily_ohlcv(symbol: str, days: int = 90) -> List[dict]:
    """Return daily OHLCV sorted oldest→newest."""
    conn  = get_conn()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows  = conn.execute("""
        SELECT date, open, high, low, close, volume, delivery_pct
        FROM daily_ohlcv
        WHERE symbol = ? AND date >= ?
        ORDER BY date ASC
    """, (symbol.upper(), cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_intraday_5m(symbol: str, days: int = 5) -> List[dict]:
    """Return 5-min intraday candles."""
    cutoff = (datetime.now(IST) - timedelta(days=days)).isoformat()
    conn   = get_conn()
    rows   = conn.execute("""
        SELECT datetime, open, high, low, close, volume
        FROM intraday_5m
        WHERE symbol = ? AND datetime >= ?
        ORDER BY datetime ASC
    """, (symbol.upper(), cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pcr_history(symbol: str, days: int = 60) -> List[float]:
    """Return PCR values as list, oldest first."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn   = get_conn()
    rows   = conn.execute("""
        SELECT pcr FROM daily_pcr
        WHERE symbol = ? AND date >= ? AND pcr IS NOT NULL
        ORDER BY date ASC
    """, (symbol.upper(), cutoff)).fetchall()
    conn.close()
    return [r["pcr"] for r in rows]


def get_vix_history(days: int = 60) -> List[float]:
    """Return VIX values as list, oldest first."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn   = get_conn()
    rows   = conn.execute("""
        SELECT vix FROM daily_vix
        WHERE date >= ? AND vix IS NOT NULL
        ORDER BY date ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [r["vix"] for r in rows]


def get_fii_history(days: int = 30) -> List[float]:
    """Return FII net flows as list, oldest first."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn   = get_conn()
    rows   = conn.execute("""
        SELECT fii_net FROM daily_fii
        WHERE date >= ? AND fii_net IS NOT NULL
        ORDER BY date ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [r["fii_net"] for r in rows]


def get_calibrated_rates() -> Dict[str, Dict]:
    """
    Return calibrated win rates as dict.
    Format: {signal_name: {regime: {win_rate, avg_win_pct, ...}}}
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT signal_name, regime, win_rate, avg_win_pct, avg_loss_pct,
               sharpe, n_observations, ci_95_low, ci_95_high
        FROM calibrated_win_rates
    """).fetchall()
    conn.close()
    result = {}
    for r in rows:
        sn = r["signal_name"]
        if sn not in result:
            result[sn] = {}
        result[sn][r["regime"]] = dict(r)
    return result


def get_signal_log(days: int = 30) -> List[dict]:
    """Return recent signal log entries."""
    cutoff = (datetime.now(IST) - timedelta(days=days)).isoformat()
    conn   = get_conn()
    rows   = conn.execute("""
        SELECT sl.*, so.pnl_pct, so.exit_type, so.exit_date, so.won
        FROM signal_log sl
        LEFT JOIN signal_outcomes so ON sl.id = so.signal_log_id
        WHERE sl.fired_at >= ?
        ORDER BY sl.fired_at DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_db_stats() -> dict:
    """Return record counts for each table."""
    conn = get_conn()
    stats = {}
    for table in ("daily_ohlcv","intraday_5m","daily_pcr",
                  "daily_vix","daily_fii","signal_log","signal_outcomes",
                  "calibrated_win_rates"):
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = n
        except Exception:
            stats[table] = 0
    # Date range for OHLCV
    try:
        r = conn.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT symbol) FROM daily_ohlcv").fetchone()
        stats["ohlcv_range"] = f"{r[0]} → {r[1]} ({r[2]} symbols)"
    except Exception:
        stats["ohlcv_range"] = "empty"
    conn.close()
    return stats


def data_coverage(symbol: str) -> dict:
    """Check how much data we have for a symbol."""
    conn = get_conn()
    r = conn.execute("""
        SELECT COUNT(*) as n, MIN(date) as oldest, MAX(date) as newest
        FROM daily_ohlcv WHERE symbol = ?
    """, (symbol.upper(),)).fetchone()
    conn.close()
    return {"symbol": symbol, "days": r["n"] or 0,
            "oldest": r["oldest"], "newest": r["newest"]}


# ── Bulk historical loader ─────────────────────────────────────────────────────

def backfill_instrument(symbol: str, groww_token: str = "",
                         days: int = 1500) -> dict:
    """
    Backfill historical daily OHLCV using yfinance (Yahoo Finance).

    Why yfinance instead of NSE direct API:
    - NSE blocks cloud hosting IPs (Streamlit Cloud, DigitalOcean, AWS)
    - Yahoo Finance serves NSE data reliably from any IP
    - Returns up to 10 years of daily OHLCV for NSE/BSE symbols
    - Symbol format: RELIANCE.NS, HDFCBANK.NS, ^NSEI (Nifty), ^NSEBANK

    yfinance is already in requirements.txt.
    """
    from datetime import date, timedelta
    import time

    # Symbol mapping for yfinance
    INDEX_MAP = {
        "NIFTY":     "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "SENSEX":    "^BSESN",
    }

    all_candles = []
    source      = "YAHOO"

    # Try Groww first if token available
    if groww_token:
        try:
            from live_data import get_historical_ohlcv_groww
            result = get_historical_ohlcv_groww(groww_token, symbol, "1d", days)
            if result.get("success") and len(result.get("candles", [])) > 50:
                all_candles = result["candles"]
                source      = "GROWW"
        except Exception:
            pass

    # yfinance fallback (works from any server including Streamlit Cloud)
    if not all_candles:
        try:
            import yfinance as yf
            from datetime import datetime as dt2

            sym_upper = symbol.upper()
            yf_sym    = INDEX_MAP.get(sym_upper, f"{sym_upper}.NS")

            end_dt   = date.today()
            start_dt = end_dt - timedelta(days=days)

            ticker = yf.Ticker(yf_sym)
            df     = ticker.history(
                start  = start_dt.strftime("%Y-%m-%d"),
                end    = end_dt.strftime("%Y-%m-%d"),
                interval = "1d",
                auto_adjust = True,
                actions  = False,
            )

            if df is None or df.empty:
                return {"symbol": symbol, "inserted": 0,
                        "error": f"yfinance returned empty data for {yf_sym}"}

            for idx, row in df.iterrows():
                dt_str = str(idx)[:10]
                try:
                    all_candles.append({
                        "datetime":    dt_str,
                        "open":        round(float(row["Open"]),  2),
                        "high":        round(float(row["High"]),  2),
                        "low":         round(float(row["Low"]),   2),
                        "close":       round(float(row["Close"]), 2),
                        "volume":      int(row["Volume"]),
                        "delivery_pct": 50.0,   # Not available from Yahoo
                    })
                except Exception:
                    pass

            all_candles.sort(key=lambda x: x["datetime"])
            source = "YAHOO"

        except ImportError:
            return {"symbol": symbol, "inserted": 0,
                    "error": "yfinance not installed. Add to requirements.txt"}
        except Exception as e:
            return {"symbol": symbol, "inserted": 0,
                    "error": f"yfinance error: {str(e)[:100]}"}

    if not all_candles:
        return {"symbol": symbol, "inserted": 0,
                "error": "No data returned from any source"}

    inserted = upsert_daily_ohlcv(symbol, all_candles, source)
    return {
        "symbol":      symbol,
        "inserted":    inserted,
        "total_days":  len(all_candles),
        "source":      source,
        "date_range":  (f"{all_candles[0].get('datetime','?')[:10]} → "
                        f"{all_candles[-1].get('datetime','?')[:10]}"),
    }


def backfill_all_instruments(groww_token: str = "", days: int = 1500) -> dict:
    """
    Backfill all 22 instruments sequentially.

    Why sequential (not parallel):
    yfinance/Yahoo Finance rate-limits concurrent requests from the same IP.
    Sequential with a 1-second pause between instruments avoids throttling.
    Total time: ~45-60 seconds for 22 instruments.
    """
    import time
    from scanner import SCAN_UNIVERSE

    all_symbols = SCAN_UNIVERSE["stocks"] + SCAN_UNIVERSE["indices"]
    results = {}

    for sym in all_symbols:
        try:
            results[sym] = backfill_instrument(sym, groww_token, days)
        except Exception as e:
            results[sym] = {"symbol": sym, "inserted": 0, "error": str(e)}
        # Rate limit pause — Yahoo Finance throttles concurrent requests
        time.sleep(1.2)

    total_inserted = sum(r.get("inserted", 0) for r in results.values())
    success_count  = sum(1 for r in results.values() if r.get("inserted", 0) > 0)

    return {
        "instruments_loaded": success_count,
        "total_records":      total_inserted,
        "details":            results,
    }


# ── Daily data collection (called by scanner on each cycle) ───────────────────

def collect_daily_snapshot(groww_token: str):
    """
    Collect and store today's PCR, VIX, FII data.
    Called by scanner at start of each scan cycle.
    Builds up the historical record day by day.
    """
    from groww_data import (get_options_chain_groww, get_vix_data_groww,
                             get_fii_dii_data)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_nifty = ex.submit(get_options_chain_groww, groww_token, "NIFTY")
        f_bnk   = ex.submit(get_options_chain_groww, groww_token, "BANKNIFTY")
        f_vix   = ex.submit(get_vix_data_groww, groww_token)
        f_fii   = ex.submit(get_fii_dii_data)

        nifty_opts = f_nifty.result()
        bnk_opts   = f_bnk.result()
        vix_data   = f_vix.result()
        fii_data   = f_fii.result()

    upsert_pcr("NIFTY",     nifty_opts)
    upsert_pcr("BANKNIFTY", bnk_opts)

    if vix_data.get("success"):
        upsert_vix(vix_data["vix"], vix_data.get("change", 0),
                   vix_data.get("change_pct", 0))

    upsert_fii(fii_data)


# ── Initialise on import ───────────────────────────────────────────────────────
init_db()
