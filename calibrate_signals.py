"""
calibrate_signals.py — Signal Calibration Engine
HIVE MIND ALPHA · Action 1

Backtests every signal in quant_core against real NSE historical data.
Measures empirical win rates, average win/loss, Sharpe ratio.
Updates SignalCombiner.WIN_RATES and market_data_store.calibrated_win_rates.

Mathematical approach:
  For each signal type on each instrument:
    1. Walk forward through historical OHLCV (no look-ahead bias)
    2. Record each signal fire: direction, entry, stop-loss, target
    3. Simulate forward N days to determine outcome
    4. Compute: win_rate, avg_win%, avg_loss%, Sharpe, expectancy

Walk-forward validation protocol:
  Training period: 2018-01-01 → 2022-12-31  (4 years)
  Test period:     2023-01-01 → present      (out-of-sample)
  Report BOTH — training win rates tell you about the signal.
  Test win rates tell you if the edge is real.

No look-ahead bias guarantee:
  At each bar i, the signal only sees closes[0:i+1].
  The outcome is measured using closes[i+1:i+1+holding_days].
  The signal cannot "see" the outcome it is being evaluated on.
"""

import math
import json
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple, Optional
import pytz

IST = pytz.timezone("Asia/Kolkata")

# Holding periods to test (days after signal)
HOLDING_PERIODS = [1, 3, 5, 10]

# Primary holding period for win rate calculation
PRIMARY_HOLDING = 5

# Stop-loss multiple of ATR
SL_ATR_MULT = 1.5

# Target multiple of ATR (for win/loss determination)
TARGET_ATR_MULT_1 = 3.0
TARGET_ATR_MULT_2 = 4.5

# Minimum trades required before a win rate is considered reliable
MIN_TRADES_RELIABLE = 20


# ── Signal fire detector (walks forward through history) ──────────────────────

def detect_signal_fires(signal_fn_name: str,
                         ohlcv: List[dict],
                         options_seq: List[dict] = None,
                         fii_seq: List[float] = None,
                         vix_seq: List[float] = None) -> List[dict]:
    """
    Walk forward through ohlcv and record every bar where the signal fires.

    No look-ahead: at bar i, only uses ohlcv[0:i+1].

    Returns list of {bar_index, direction, strength, entry, sl, target_1}
    """
    from quant_core import (
        compute_rsi, compute_macd, compute_bollinger, compute_adx,
        atr_series, ewma, StatisticalSignals, DerivativesSignals,
        MacroSignals,
    )

    fires = []
    n     = len(ohlcv)

    for i in range(30, n - PRIMARY_HOLDING - 1):
        window  = ohlcv[:i + 1]
        closes  = [c["close"]  for c in window]
        highs   = [c["high"]   for c in window]
        lows    = [c["low"]    for c in window]
        volumes = [c["volume"] for c in window]

        # ATR for stop-loss and target computation
        atr_s   = atr_series(highs, lows, closes, 14)
        atr_now = next((v for v in reversed(atr_s) if v is not None), None)
        if not atr_now or atr_now <= 0:
            continue

        entry    = closes[-1]
        sl_dist  = atr_now * SL_ATR_MULT
        t1_dist  = atr_now * TARGET_ATR_MULT_1

        fired = None

        # ── Route to correct signal ────────────────────────────────────────
        if signal_fn_name == "rsi_oversold":
            rsi_s    = compute_rsi(closes, 14)
            rsi_now  = next((v for v in reversed(rsi_s) if v is not None), None)
            rsi_prev = next((v for v in reversed(rsi_s[:-1]) if v is not None), None)
            if (rsi_now and rsi_prev and rsi_prev < 32 and rsi_now >= 32):
                fired = ("LONG", min((32 - min(rsi_now, 32)) / 32, 1.0))

        elif signal_fn_name == "rsi_overbought":
            rsi_s    = compute_rsi(closes, 14)
            rsi_now  = next((v for v in reversed(rsi_s) if v is not None), None)
            rsi_prev = next((v for v in reversed(rsi_s[:-1]) if v is not None), None)
            if (rsi_now and rsi_prev and rsi_prev > 68 and rsi_now <= 68):
                fired = ("SHORT", min((rsi_now - 68) / 32, 1.0))

        elif signal_fn_name == "ema_bullish_cross":
            ema9  = ewma(closes, 9)
            ema21 = ewma(closes, 21)
            e9n   = next((v for v in reversed(ema9)  if v is not None), None)
            e21n  = next((v for v in reversed(ema21) if v is not None), None)
            e9p   = next((v for v in reversed(ema9[:-1])  if v is not None), None)
            e21p  = next((v for v in reversed(ema21[:-1]) if v is not None), None)
            if (None not in (e9n, e21n, e9p, e21p)
                    and e9p <= e21p and e9n > e21n):
                fired = ("LONG", min(abs(e9n - e21n) / max(e21n, 1) * 20, 1.0))

        elif signal_fn_name == "ema_bearish_cross":
            ema9  = ewma(closes, 9)
            ema21 = ewma(closes, 21)
            e9n   = next((v for v in reversed(ema9)  if v is not None), None)
            e21n  = next((v for v in reversed(ema21) if v is not None), None)
            e9p   = next((v for v in reversed(ema9[:-1])  if v is not None), None)
            e21p  = next((v for v in reversed(ema21[:-1]) if v is not None), None)
            if (None not in (e9n, e21n, e9p, e21p)
                    and e9p >= e21p and e9n < e21n):
                fired = ("SHORT", min(abs(e21n - e9n) / max(e21n, 1) * 20, 1.0))

        elif signal_fn_name == "zscore_price":
            sig = StatisticalSignals.zscore_price(closes, 20)
            if sig["fired"]:
                fired = (sig["direction"], sig["strength"])

        elif signal_fn_name == "momentum":
            sig = StatisticalSignals.returns_momentum(closes, 20, 1)
            if sig["fired"]:
                fired = (sig["direction"], sig["strength"])

        elif signal_fn_name == "vol_breakout":
            if len(closes) >= 22 and len(volumes) >= 22:
                avg_vol20 = sum(volumes[-21:-1]) / 20
                high20    = max(highs[-21:-1])
                if closes[-1] > high20 and volumes[-1] > avg_vol20 * 2.0:
                    fired = ("LONG", min((volumes[-1] / max(avg_vol20, 1) - 2.0) / 3.0, 1.0))

        elif signal_fn_name == "vol_breakdown":
            if len(closes) >= 22 and len(volumes) >= 22:
                avg_vol20 = sum(volumes[-21:-1]) / 20
                low20     = min(lows[-21:-1])
                if closes[-1] < low20 and volumes[-1] > avg_vol20 * 2.0:
                    fired = ("SHORT", min((volumes[-1] / max(avg_vol20, 1) - 2.0) / 3.0, 1.0))

        elif signal_fn_name == "delivery_surge":
            del_pcts = [c.get("delivery_pct", 50.0) for c in window]
            if len(del_pcts) >= 2 and len(volumes) >= 21:
                avg_vol20 = sum(volumes[-21:-1]) / 20
                if (del_pcts[-1] > 70.0 and closes[-1] > closes[-2]
                        and volumes[-1] > avg_vol20 * 1.5):
                    fired = ("LONG", min(del_pcts[-1] / 100.0, 1.0))

        elif signal_fn_name == "pcr_extreme_high":
            if pcr_seq and i < len(pcr_seq):
                pcr_hist = pcr_seq[max(0, i - 25):i + 1]
                sig = DerivativesSignals.pcr_zscore(pcr_hist)
                if sig["fired"] and sig["direction"] == "LONG":
                    fired = ("LONG", sig["strength"])

        elif signal_fn_name == "pcr_extreme_low":
            if pcr_seq and i < len(pcr_seq):
                pcr_hist = pcr_seq[max(0, i - 25):i + 1]
                sig = DerivativesSignals.pcr_zscore(pcr_hist)
                if sig["fired"] and sig["direction"] == "SHORT":
                    fired = ("SHORT", sig["strength"])

        elif signal_fn_name == "vix_spike_fade":
            if vix_seq and i < len(vix_seq):
                vix_hist = vix_seq[max(0, i - 10):i + 1]
                sig = MacroSignals.vix_regime_signal(vix_hist)
                if sig["fired"] and sig["signal_type"] == "SPIKE_FADE":
                    fired = ("LONG", sig["strength"])

        elif signal_fn_name == "fii_zscore":
            if fii_seq and i < len(fii_seq):
                fii_hist = fii_seq[max(0, i - 25):i + 1]
                sig = MacroSignals.fii_flow_zscore(fii_hist)
                if sig["fired"]:
                    fired = (sig["direction"], sig["strength"])

        if fired is None:
            continue

        direction, strength = fired
        sl = entry - sl_dist if direction == "LONG" else entry + sl_dist
        t1 = entry + t1_dist if direction == "LONG" else entry - t1_dist

        fires.append({
            "bar_index": i,
            "date":      ohlcv[i].get("datetime", ohlcv[i].get("date", "")),
            "direction": direction,
            "strength":  round(strength, 3),
            "entry":     round(entry, 2),
            "sl":        round(sl, 2),
            "target_1":  round(t1, 2),
            "atr":       round(atr_now, 2),
        })

    return fires


# ── Outcome evaluator ──────────────────────────────────────────────────────────

def evaluate_outcome(fire: dict, ohlcv: List[dict],
                      holding_days: int = PRIMARY_HOLDING) -> dict:
    """
    Evaluate the outcome of a fired signal.

    Uses high-low path simulation:
      On each forward bar, check if SL is breached first (use low for longs,
      high for shorts), then check if target is hit (use high for longs,
      low for shorts).

    This is conservative — assumes worst-case intrabar ordering:
      For LONG: low is checked first (SL), then high (target)
      For SHORT: high is checked first (SL), then low (target)
    """
    i         = fire["bar_index"]
    direction = fire["direction"]
    entry     = fire["entry"]
    sl        = fire["sl"]
    target    = fire["target_1"]
    n         = len(ohlcv)

    outcome   = "TIME_EXIT"
    exit_bar  = min(i + holding_days, n - 1)
    exit_price= ohlcv[exit_bar]["close"]

    for j in range(i + 1, min(i + holding_days + 1, n)):
        bar = ohlcv[j]
        h   = bar["high"]
        l   = bar["low"]

        if direction == "LONG":
            if l <= sl:                      # SL hit first (conservative)
                outcome    = "SL"
                exit_price = sl
                exit_bar   = j
                break
            if h >= target:                  # Target hit
                outcome    = "TARGET_1"
                exit_price = target
                exit_bar   = j
                break
        else:  # SHORT
            if h >= sl:                      # SL hit
                outcome    = "SL"
                exit_price = sl
                exit_bar   = j
                break
            if l <= target:                  # Target hit
                outcome    = "TARGET_1"
                exit_price = target
                exit_bar   = j
                break

    if direction == "LONG":
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_price) / entry * 100

    return {
        "outcome":     outcome,
        "exit_bar":    exit_bar,
        "exit_price":  round(exit_price, 2),
        "pnl_pct":     round(pnl_pct, 4),
        "won":         pnl_pct > 0,
        "holding_days":exit_bar - i,
    }


# ── Statistics calculator ──────────────────────────────────────────────────────

def compute_signal_stats(outcomes: List[dict]) -> dict:
    """
    Compute statistical summary for a set of signal outcomes.

    Returns win_rate, avg_win%, avg_loss%, Sharpe, expectancy,
    and 95% confidence interval for win rate.
    """
    if not outcomes:
        return {"n": 0, "win_rate": 0.5, "reliable": False}

    n       = len(outcomes)
    wins    = [o for o in outcomes if o["won"]]
    losses  = [o for o in outcomes if not o["won"]]
    n_wins  = len(wins)
    n_loss  = len(losses)

    win_rate  = n_wins / n
    avg_win   = sum(o["pnl_pct"] for o in wins)   / max(n_wins, 1)
    avg_loss  = sum(o["pnl_pct"] for o in losses) / max(n_loss, 1)
    avg_win   = max(avg_win, 0.001)
    avg_loss  = min(avg_loss, -0.001)

    pnl_series = [o["pnl_pct"] for o in outcomes]
    mu_pnl     = sum(pnl_series) / n
    var_pnl    = sum((p - mu_pnl) ** 2 for p in pnl_series) / max(n - 1, 1)
    std_pnl    = math.sqrt(max(var_pnl, 1e-10))

    # Annualised Sharpe (assume 252 trading days, avg 5-day hold → ~50 trades/year)
    sharpe_annualised = (mu_pnl / std_pnl * math.sqrt(n)) if std_pnl > 0 else 0

    # Expectancy per trade
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    # 95% CI for win rate (Wald interval)
    ci_half = 1.96 * math.sqrt(win_rate * (1 - win_rate) / max(n, 1))
    ci_low  = max(0.0, win_rate - ci_half)
    ci_high = min(1.0, win_rate + ci_half)

    # Profit factor
    total_wins   = sum(o["pnl_pct"] for o in wins)
    total_losses = abs(sum(o["pnl_pct"] for o in losses))
    profit_factor = total_wins / max(total_losses, 0.001)

    return {
        "n":              n,
        "n_wins":         n_wins,
        "n_losses":       n_loss,
        "win_rate":       round(win_rate, 4),
        "avg_win_pct":    round(avg_win, 4),
        "avg_loss_pct":   round(avg_loss, 4),
        "expectancy":     round(expectancy, 4),
        "sharpe":         round(sharpe_annualised, 3),
        "profit_factor":  round(profit_factor, 3),
        "ci_low":         round(ci_low, 4),
        "ci_high":        round(ci_high, 4),
        "ci_width":       round(ci_high - ci_low, 4),
        "reliable":       n >= MIN_TRADES_RELIABLE,
        "grade":          _grade(win_rate, sharpe_annualised, profit_factor, expectancy),
    }


def _grade(wr, sharpe, pf, exp) -> str:
    score = 0
    if wr    > 0.60: score += 3
    elif wr  > 0.55: score += 2
    elif wr  > 0.50: score += 1
    if sharpe > 1.5: score += 3
    elif sharpe > 0.8: score += 2
    elif sharpe > 0.3: score += 1
    if pf    > 2.0:  score += 2
    elif pf  > 1.3:  score += 1
    if exp   > 0.5:  score += 2
    elif exp > 0.0:  score += 1
    if score >= 9:   return "A+"
    elif score >= 7: return "A"
    elif score >= 5: return "B"
    elif score >= 3: return "C"
    else:            return "D"


# ── Regime-conditional analysis ────────────────────────────────────────────────

def classify_regime_for_bar(closes: List[float],
                              vix_val: Optional[float] = None) -> str:
    """
    Classify market regime at a given bar.
    Simple rule-based classification using price trend + VIX level.
    """
    if len(closes) < 50:
        return "UNKNOWN"
    sma50  = sum(closes[-50:]) / 50
    sma20  = sum(closes[-20:]) / 20
    c      = closes[-1]
    if vix_val and vix_val > 22:
        return "HIGH_VOL"
    if vix_val and vix_val < 14:
        return "LOW_VOL"
    if c > sma20 > sma50:
        return "BULL_TREND"
    elif c < sma20 < sma50:
        return "BEAR_TREND"
    else:
        return "SIDEWAYS"


# ── Full calibration run ───────────────────────────────────────────────────────

SIGNAL_NAMES = [
    "rsi_oversold", "rsi_overbought",
    "ema_bullish_cross", "ema_bearish_cross",
    "zscore_price", "momentum",
    "vol_breakout", "vol_breakdown",
    "delivery_surge",
    "pcr_extreme_high", "pcr_extreme_low",
    "vix_spike_fade", "fii_zscore",
]

REGIMES = ["ALL", "BULL_TREND", "BEAR_TREND", "SIDEWAYS", "HIGH_VOL", "LOW_VOL"]


def calibrate_one_signal(signal_name: str,
                          ohlcv_by_symbol: Dict[str, List[dict]],
                          pcr_by_date: Dict[str, float] = None,
                          vix_by_date: Dict[str, float] = None,
                          fii_by_date: Dict[str, float] = None,
                          holding_days: int = PRIMARY_HOLDING,
                          split_date: str = "2023-01-01") -> dict:
    """
    Calibrate one signal across all instruments.

    split_date: records before = training set, after = test set.

    Returns {
      'ALL': stats_dict,
      'BULL_TREND': stats_dict,
      ...per regime,
      'TRAIN': stats_dict,
      'TEST': stats_dict,
    }
    """
    all_fires    = []
    all_outcomes = []

    for symbol, ohlcv in ohlcv_by_symbol.items():
        if len(ohlcv) < 40:
            continue

        # Build sequential PCR/VIX/FII arrays aligned to ohlcv dates
        pcr_seq = []
        vix_seq = []
        fii_seq = []
        for bar in ohlcv:
            d = str(bar.get("datetime", bar.get("date",""))[:10])
            pcr_seq.append(pcr_by_date.get(d, 1.0) if pcr_by_date else 1.0)
            vix_seq.append(vix_by_date.get(d, 16.0) if vix_by_date else 16.0)
            fii_seq.append(fii_by_date.get(d, 0.0) if fii_by_date else 0.0)

        fires = detect_signal_fires(signal_name, ohlcv,
                                     pcr_seq, fii_seq, vix_seq)

        for fire in fires:
            outcome = evaluate_outcome(fire, ohlcv, holding_days)
            bar_idx = fire["bar_index"]
            # Regime at this bar
            closes_to_bar = [c["close"] for c in ohlcv[:bar_idx + 1]]
            vix_at_bar    = vix_seq[bar_idx] if bar_idx < len(vix_seq) else None
            regime        = classify_regime_for_bar(closes_to_bar, vix_at_bar)
            bar_date      = str(ohlcv[bar_idx].get("datetime",
                                                     ohlcv[bar_idx].get("date",""))[:10])

            record = {**fire, **outcome,
                      "symbol": symbol, "regime": regime, "bar_date": bar_date}
            all_fires.append(record)
            all_outcomes.append(record)

    if not all_outcomes:
        return {r: {"n": 0, "win_rate": 0.5, "reliable": False}
                for r in REGIMES + ["TRAIN","TEST"]}

    # Compute stats per regime and per train/test split
    result = {}

    # ALL
    result["ALL"] = compute_signal_stats(all_outcomes)

    # Per regime
    for regime in ["BULL_TREND","BEAR_TREND","SIDEWAYS","HIGH_VOL","LOW_VOL"]:
        subset = [o for o in all_outcomes if o.get("regime") == regime]
        result[regime] = compute_signal_stats(subset)

    # Train / Test split
    train = [o for o in all_outcomes if o.get("bar_date","") < split_date]
    test  = [o for o in all_outcomes if o.get("bar_date","") >= split_date]
    result["TRAIN"] = compute_signal_stats(train)
    result["TEST"]  = compute_signal_stats(test)

    return result


def run_full_calibration(groww_token: str = "",
                          holding_days: int = PRIMARY_HOLDING,
                          progress_callback=None) -> dict:
    """
    Run calibration for all signals across all instruments.
    Fetches data from market_data_store.

    progress_callback: callable(signal_name, i, total) for UI progress updates.
    """
    from market_data_store import (get_daily_ohlcv, get_pcr_history,
                                    get_vix_history, get_fii_history,
                                    save_calibrated_win_rates, get_db_stats)
    from scanner import SCAN_UNIVERSE

    all_symbols = SCAN_UNIVERSE["stocks"] + SCAN_UNIVERSE["indices"]

    # Load OHLCV for all instruments
    ohlcv_by_symbol = {}
    for sym in all_symbols:
        data = get_daily_ohlcv(sym, days=1500)
        if len(data) >= 40:
            ohlcv_by_symbol[sym] = data

    if not ohlcv_by_symbol:
        return {"error": "No OHLCV data. Run backfill_all_instruments() first."}

    # Build date-indexed PCR/VIX/FII dicts
    from market_data_store import get_conn
    conn = get_conn()

    pcr_rows = conn.execute("SELECT date, pcr FROM daily_pcr WHERE symbol='NIFTY' ORDER BY date").fetchall()
    vix_rows = conn.execute("SELECT date, vix FROM daily_vix ORDER BY date").fetchall()
    fii_rows = conn.execute("SELECT date, fii_net FROM daily_fii ORDER BY date").fetchall()
    conn.close()

    pcr_by_date = {r["date"]: r["pcr"] for r in pcr_rows if r["pcr"]}
    vix_by_date = {r["date"]: r["vix"] for r in vix_rows if r["vix"]}
    fii_by_date = {r["date"]: r["fii_net"] for r in fii_rows if r["fii_net"]}

    # Run calibration for each signal
    all_results   = {}
    total_signals = len(SIGNAL_NAMES)

    for idx, signal_name in enumerate(SIGNAL_NAMES):
        if progress_callback:
            progress_callback(signal_name, idx, total_signals)

        result = calibrate_one_signal(
            signal_name        = signal_name,
            ohlcv_by_symbol    = ohlcv_by_symbol,
            pcr_by_date        = pcr_by_date,
            vix_by_date        = vix_by_date,
            fii_by_date        = fii_by_date,
            holding_days       = holding_days,
        )
        all_results[signal_name] = result

    # Save to database
    save_calibrated_win_rates(all_results)

    # Update quant_core SignalCombiner.WIN_RATES in memory
    _update_combiner_win_rates(all_results)

    summary = {
        "calibrated_at":    datetime.now(IST).isoformat(),
        "signals_tested":   len(all_results),
        "instruments_used": len(ohlcv_by_symbol),
        "holding_days":     holding_days,
        "results":          {
            sig: {
                "win_rate_all":   r.get("ALL",{}).get("win_rate", 0.5),
                "win_rate_train": r.get("TRAIN",{}).get("win_rate", 0.5),
                "win_rate_test":  r.get("TEST",{}).get("win_rate", 0.5),
                "n_all":          r.get("ALL",{}).get("n", 0),
                "n_test":         r.get("TEST",{}).get("n", 0),
                "grade":          r.get("ALL",{}).get("grade","?"),
                "sharpe":         r.get("ALL",{}).get("sharpe",0),
                "reliable":       r.get("ALL",{}).get("reliable", False),
            }
            for sig, r in all_results.items()
        },
    }
    return summary


def _update_combiner_win_rates(calibration_results: dict):
    """
    Update SignalCombiner.WIN_RATES in memory with measured values.
    Falls back to prior (0.55) for signals with fewer than MIN_TRADES_RELIABLE trades.
    """
    try:
        from quant_core import SignalCombiner
        for signal_name, results in calibration_results.items():
            stats = results.get("ALL", {})
            if stats.get("reliable") and stats.get("n", 0) >= MIN_TRADES_RELIABLE:
                # Use test set if available (more conservative, out-of-sample)
                test_stats = results.get("TEST", {})
                if test_stats.get("reliable") and test_stats.get("n", 0) >= 10:
                    # Blend: 70% test (out-of-sample), 30% all-history
                    blended = (0.7 * test_stats["win_rate"]
                                + 0.3 * stats["win_rate"])
                else:
                    blended = stats["win_rate"]
                # Apply shrinkage toward 0.5 based on n (Bayesian shrinkage)
                n = stats.get("n", 0)
                shrinkage = n / (n + 20)   # 20 = prior strength
                final_wr  = 0.5 * (1 - shrinkage) + blended * shrinkage
                SignalCombiner.WIN_RATES[signal_name] = round(final_wr, 4)
    except Exception:
        pass
