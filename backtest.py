"""
backtest.py — Backtesting Engine
HIVE MIND ALPHA · Tier 1

Replays scanner signal logic against 2 years of historical OHLCV data.
Measures win rate, Sharpe ratio, max drawdown, avg R:R per signal type.
Stores results in backtest_results.json for agent weight calibration.
"""

import json
import os
import math
from datetime import datetime, timedelta, date
from typing import Optional
import pytz

IST = pytz.timezone("Asia/Kolkata")
RESULTS_FILE = "backtest_results.json"


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_historical_data(token: str, symbol: str,
                           days: int = 500) -> list:
    """
    Fetch historical daily OHLCV from Groww API (primary) or NSE (fallback).
    Returns list of dicts: {datetime, open, high, low, close, volume}
    """
    # Try Groww first
    try:
        from growwapi import GrowwAPI
        from datetime import datetime as dt
        groww    = GrowwAPI(token)
        end_dt   = dt.now(IST)
        start_dt = end_dt - timedelta(days=days)
        resp = groww.get_historical_candle_data(
            trading_symbol=symbol.upper(),
            exchange="NSE",
            segment="CASH",
            start_time=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            interval="1d",
        )
        candles = resp.get("candles", []) or []
        if candles:
            return _parse_groww_candles(candles)
    except Exception:
        pass

    # Fallback to NSE free API
    return _fetch_nse_historical(symbol, days)


def _parse_groww_candles(candles: list) -> list:
    result = []
    for c in candles:
        try:
            if isinstance(c, list):
                result.append({
                    "datetime": str(c[0]),
                    "open":  float(c[1]), "high": float(c[2]),
                    "low":   float(c[3]), "close":float(c[4]),
                    "volume":int(c[5]),
                })
            else:
                result.append({
                    "datetime": str(c.get("timestamp","")),
                    "open":  float(c.get("open",0)),
                    "high":  float(c.get("high",0)),
                    "low":   float(c.get("low", 0)),
                    "close": float(c.get("close",0)),
                    "volume":int(c.get("volume",0)),
                })
        except Exception:
            pass
    return sorted(result, key=lambda x: x["datetime"])


def _fetch_nse_historical(symbol: str, days: int) -> list:
    import requests
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=8)
        end_dt   = date.today()
        start_dt = end_dt - timedelta(days=days)
        r = session.get(
            f"https://www.nseindia.com/api/historical/securityArchives"
            f"?from={start_dt.strftime('%d-%m-%Y')}"
            f"&to={end_dt.strftime('%d-%m-%Y')}"
            f"&symbol={symbol.upper()}&dataType=priceVolumeDeliverable&series=EQ",
            timeout=12,
        )
        data = r.json().get("data", [])
        candles = []
        for d in data:
            try:
                candles.append({
                    "datetime": d.get("CH_TIMESTAMP",""),
                    "open":   float(d.get("CH_OPENING_PRICE",0) or 0),
                    "high":   float(d.get("CH_TRADE_HIGH_PRICE",0) or 0),
                    "low":    float(d.get("CH_TRADE_LOW_PRICE",0) or 0),
                    "close":  float(d.get("CH_CLOSING_PRICE",0) or 0),
                    "volume": int(d.get("CH_TOT_TRADED_QTY",0) or 0),
                    "delivery_pct": float(d.get("COP_DELIV_PERC",0) or 0),
                })
            except Exception:
                pass
        return sorted(candles, key=lambda x: x["datetime"])
    except Exception:
        return []


# ── Technical signal generators (deterministic — no LLM) ─────────────────────

def compute_signals_on_candles(candles: list) -> list:
    """
    For each candle beyond the warmup period, compute all signals.
    Returns list of {date, close, signals: {...}, entry_eligible: bool}
    """
    if len(candles) < 50:
        return []

    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [c["volume"] for c in candles]

    results = []
    for i in range(50, len(candles)):
        c_slice = closes[:i+1]
        h_slice = highs[:i+1]
        l_slice = lows[:i+1]
        v_slice = volumes[:i+1]

        sma20 = _sma(c_slice, 20)
        sma50 = _sma(c_slice, 50)
        ema9  = _ema(c_slice, 9)
        ema21 = _ema(c_slice, 21)
        rsi   = _rsi(c_slice, 14)
        atr   = _atr(h_slice, l_slice, c_slice, 14)
        bb_up, bb_mid, bb_lo = _bollinger(c_slice, 20)
        vol_ratio = v_slice[-1] / max(_sma(v_slice, 20), 1)

        price = c_slice[-1]
        prev  = c_slice[-2] if len(c_slice) > 1 else price

        # Signal logic
        signals = {
            "rsi_oversold":       rsi is not None and rsi < 32,
            "rsi_overbought":     rsi is not None and rsi > 68,
            "ema_bullish_cross":  ema9 and ema21 and ema9 > ema21 and _ema(c_slice[:-1], 9) < _ema(c_slice[:-1], 21),
            "ema_bearish_cross":  ema9 and ema21 and ema9 < ema21 and _ema(c_slice[:-1], 9) > _ema(c_slice[:-1], 21),
            "sma_golden_cross":   sma20 and sma50 and sma20 > sma50 and _sma(c_slice[:-1], 20) < _sma(c_slice[:-1], 50),
            "sma_death_cross":    sma20 and sma50 and sma20 < sma50 and _sma(c_slice[:-1], 20) > _sma(c_slice[:-1], 50),
            "bb_lower_touch":     bb_lo and price <= bb_lo * 1.005,
            "bb_upper_touch":     bb_up and price >= bb_up * 0.995,
            "vol_breakout":       vol_ratio > 2.0 and price > prev,
            "vol_breakdown":      vol_ratio > 2.0 and price < prev,
            "above_sma20":        sma20 and price > sma20,
            "above_sma50":        sma50 and price > sma50,
            "trend_bullish":      sma20 and sma50 and price > sma20 > sma50,
            "trend_bearish":      sma20 and sma50 and price < sma20 < sma50,
        }

        results.append({
            "date":    candles[i]["datetime"][:10],
            "close":   price,
            "high":    candles[i]["high"],
            "low":     candles[i]["low"],
            "volume":  candles[i]["volume"],
            "rsi":     rsi,
            "sma20":   sma20,
            "sma50":   sma50,
            "ema9":    ema9,
            "ema21":   ema21,
            "atr":     atr,
            "bb_up":   bb_up,
            "bb_lo":   bb_lo,
            "vol_ratio": vol_ratio,
            "signals": signals,
        })
    return results


# ── Backtest simulator ─────────────────────────────────────────────────────────

def run_backtest(
    candles: list,
    signal_name: str,
    direction: str = "LONG",
    sl_atr_mult: float = 1.5,
    target_rr: float = 2.0,
    max_hold_days: int = 10,
) -> dict:
    """
    Backtest a single signal type against historical candles.

    signal_name:  one of the keys in signals dict above
    direction:    LONG or SHORT
    sl_atr_mult:  stop-loss = entry ± (ATR * sl_atr_mult)
    target_rr:    target = entry + (risk * target_rr)
    max_hold_days: exit after N days if neither SL nor target hit

    Returns comprehensive performance metrics.
    """
    signal_data = compute_signals_on_candles(candles)
    if not signal_data:
        return {"success": False, "error": "Insufficient data"}

    trades = []
    in_trade = False

    for i, bar in enumerate(signal_data):
        if in_trade:
            continue

        if not bar["signals"].get(signal_name):
            continue
        if bar["atr"] is None or bar["atr"] == 0:
            continue

        entry_price = bar["close"]
        atr         = bar["atr"]
        risk        = atr * sl_atr_mult

        if direction == "LONG":
            stop_loss = entry_price - risk
            target    = entry_price + risk * target_rr
        else:
            stop_loss = entry_price + risk
            target    = entry_price - risk * target_rr

        # Simulate forward until SL, target, or max hold
        trade_result = None
        exit_bar     = None
        hold_days    = 0

        for j in range(i + 1, min(i + max_hold_days + 1, len(signal_data))):
            future = signal_data[j]
            hold_days += 1

            if direction == "LONG":
                if future["low"] <= stop_loss:
                    trade_result = "SL"
                    exit_price   = stop_loss
                    exit_bar     = future["date"]
                    break
                if future["high"] >= target:
                    trade_result = "TARGET"
                    exit_price   = target
                    exit_bar     = future["date"]
                    break
            else:
                if future["high"] >= stop_loss:
                    trade_result = "SL"
                    exit_price   = stop_loss
                    exit_bar     = future["date"]
                    break
                if future["low"] <= target:
                    trade_result = "TARGET"
                    exit_price   = target
                    exit_bar     = future["date"]
                    break

        if trade_result is None:
            # Time exit
            if i + max_hold_days < len(signal_data):
                exit_price   = signal_data[i + max_hold_days]["close"]
                exit_bar     = signal_data[i + max_hold_days]["date"]
                trade_result = "TIME"
            else:
                continue

        if direction == "LONG":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100

        actual_rr = abs(pnl_pct) / (risk / entry_price * 100) if risk > 0 else 0

        trades.append({
            "entry_date":   bar["date"],
            "exit_date":    exit_bar,
            "entry_price":  entry_price,
            "exit_price":   exit_price,
            "stop_loss":    stop_loss,
            "target":       target,
            "result":       trade_result,
            "pnl_pct":      round(pnl_pct, 2),
            "actual_rr":    round(actual_rr, 2),
            "hold_days":    hold_days,
            "signal":       signal_name,
            "direction":    direction,
        })

    if not trades:
        return {
            "success":      True,
            "signal":       signal_name,
            "direction":    direction,
            "total_trades": 0,
            "win_rate":     0,
            "error":        "No trades generated",
        }

    return _compute_metrics(trades, signal_name, direction)


def _compute_metrics(trades: list, signal_name: str, direction: str) -> dict:
    """Compute comprehensive performance metrics from trade list."""
    winners = [t for t in trades if t["pnl_pct"] > 0]
    losers  = [t for t in trades if t["pnl_pct"] <= 0]
    sl_hits = [t for t in trades if t["result"] == "SL"]
    tgt_hits= [t for t in trades if t["result"] == "TARGET"]

    pnl_series = [t["pnl_pct"] for t in trades]
    total_pnl  = sum(pnl_series)
    win_rate   = len(winners) / len(trades) * 100 if trades else 0
    avg_win    = sum(t["pnl_pct"] for t in winners) / max(len(winners), 1)
    avg_loss   = sum(t["pnl_pct"] for t in losers)  / max(len(losers),  1)
    profit_factor = abs(sum(t["pnl_pct"] for t in winners)) / max(abs(sum(t["pnl_pct"] for t in losers)), 0.001)
    avg_rr     = sum(t["actual_rr"] for t in trades) / len(trades)
    avg_hold   = sum(t["hold_days"] for t in trades) / len(trades)

    # Sharpe ratio (daily returns, annualised)
    if len(pnl_series) > 1:
        mean_r = total_pnl / len(pnl_series)
        std_r  = math.sqrt(sum((r - mean_r)**2 for r in pnl_series) / (len(pnl_series)-1))
        sharpe = (mean_r / max(std_r, 0.001)) * math.sqrt(252)
    else:
        sharpe = 0

    # Max drawdown
    peak = 0; trough = 0; max_dd = 0
    running = 0
    for r in pnl_series:
        running += r
        if running > peak:
            peak = running
            trough = running
        if running < trough:
            trough = running
            dd = peak - trough
            if dd > max_dd:
                max_dd = dd

    # Expectancy
    expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)

    return {
        "success":       True,
        "signal":        signal_name,
        "direction":     direction,
        "total_trades":  len(trades),
        "win_rate":      round(win_rate, 1),
        "total_pnl_pct": round(total_pnl, 1),
        "avg_win_pct":   round(avg_win, 2),
        "avg_loss_pct":  round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio":  round(sharpe, 2),
        "max_drawdown":  round(max_dd, 2),
        "avg_rr":        round(avg_rr, 2),
        "avg_hold_days": round(avg_hold, 1),
        "expectancy":    round(expectancy, 2),
        "sl_hits":       len(sl_hits),
        "target_hits":   len(tgt_hits),
        "time_exits":    len(trades) - len(sl_hits) - len(tgt_hits),
        "trades":        trades[-20:],  # Last 20 for display
        "grade":         _grade_signal(win_rate, sharpe, profit_factor, expectancy),
    }


def _grade_signal(win_rate, sharpe, profit_factor, expectancy) -> str:
    score = 0
    if win_rate > 55: score += 2
    elif win_rate > 45: score += 1
    if sharpe > 1.5: score += 2
    elif sharpe > 0.8: score += 1
    if profit_factor > 2.0: score += 2
    elif profit_factor > 1.3: score += 1
    if expectancy > 0.5: score += 2
    elif expectancy > 0: score += 1

    if score >= 7: return "A"
    elif score >= 5: return "B"
    elif score >= 3: return "C"
    else: return "D"


# ── Run full backtest suite ────────────────────────────────────────────────────

ALL_SIGNALS = [
    ("rsi_oversold",    "LONG"),
    ("rsi_overbought",  "SHORT"),
    ("ema_bullish_cross","LONG"),
    ("ema_bearish_cross","SHORT"),
    ("sma_golden_cross","LONG"),
    ("sma_death_cross", "SHORT"),
    ("bb_lower_touch",  "LONG"),
    ("bb_upper_touch",  "SHORT"),
    ("vol_breakout",    "LONG"),
    ("vol_breakdown",   "SHORT"),
    ("trend_bullish",   "LONG"),
    ("trend_bearish",   "SHORT"),
]


def run_full_backtest_suite(token: str, symbol: str,
                             days: int = 500,
                             sl_atr_mult: float = 1.5,
                             target_rr: float = 2.0,
                             max_hold: int = 10) -> dict:
    """
    Run all signal types against historical data for a symbol.
    Returns ranked results with grades.
    """
    candles = fetch_historical_data(token, symbol, days)
    if len(candles) < 60:
        return {"success": False, "error": f"Insufficient data: {len(candles)} candles"}

    results = {}
    for sig, direction in ALL_SIGNALS:
        r = run_backtest(candles, sig, direction, sl_atr_mult, target_rr, max_hold)
        if r.get("success") and r.get("total_trades", 0) > 0:
            results[f"{sig}_{direction}"] = r

    # Rank by Sharpe ratio
    ranked = sorted(results.values(),
                    key=lambda x: x.get("sharpe_ratio", -99), reverse=True)

    summary = {
        "success":      True,
        "symbol":       symbol.upper(),
        "candles_used": len(candles),
        "date_range":   f"{candles[0]['datetime'][:10]} to {candles[-1]['datetime'][:10]}",
        "signals_tested": len(ALL_SIGNALS),
        "signals_with_trades": len(results),
        "best_signal":  ranked[0] if ranked else None,
        "worst_signal": ranked[-1] if ranked else None,
        "all_results":  ranked,
        "grade_A_signals": [r["signal"] for r in ranked if r.get("grade") == "A"],
        "grade_B_signals": [r["signal"] for r in ranked if r.get("grade") == "B"],
        "timestamp":    datetime.now(IST).isoformat(),
    }

    _save_results(symbol, summary)
    return summary


def _save_results(symbol: str, data: dict):
    existing = {}
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing[symbol.upper()] = data
    with open(RESULTS_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)


def load_backtest_results(symbol: str = None) -> dict:
    if not os.path.exists(RESULTS_FILE):
        return {}
    try:
        with open(RESULTS_FILE) as f:
            data = json.load(f)
        if symbol:
            return data.get(symbol.upper(), {})
        return data
    except Exception:
        return {}


# ── Math helpers ───────────────────────────────────────────────────────────────

def _sma(data, period):
    if len(data) < period: return None
    return sum(data[-period:]) / period

def _ema(data, period):
    if len(data) < period: return None
    k = 2 / (period + 1)
    val = sum(data[:period]) / period
    for p in data[period:]:
        val = p * k + val * (1 - k)
    return val

def _rsi(data, period=14):
    if len(data) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(data)):
        ch = data[i] - data[i-1]
        gains.append(max(ch, 0))
        losses.append(max(-ch, 0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0: return 100
    return round(100 - 100 / (1 + ag / al), 1)

def _atr(highs, lows, closes, period=14):
    if len(highs) < period + 1: return None
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
           for i in range(1, len(highs))]
    return sum(trs[-period:]) / period

def _bollinger(data, period=20, std=2):
    if len(data) < period: return None, None, None
    s = data[-period:]
    m = sum(s) / period
    v = sum((x-m)**2 for x in s) / period
    sd = v ** 0.5
    return round(m + std*sd, 2), round(m, 2), round(m - std*sd, 2)
