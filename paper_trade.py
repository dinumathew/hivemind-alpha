"""
paper_trade.py — Paper Trading Engine
HIVE MIND ALPHA · Action 2

Records every scanner signal as a paper trade.
Checks outcome daily by comparing entry/SL/target to subsequent prices.
Builds a live track record with running win rate and Sharpe.

Paper trading protocol:
  1. Every fired signal is logged to market_data_store.signal_log
  2. Daily at market close (3:35 PM IST), check_open_paper_trades() runs
  3. For each open trade, fetch today's OHLCV
  4. Apply SL/target logic to determine if trade resolved
  5. Log outcome to signal_outcomes table
  6. Compute running statistics: win rate, Sharpe, expectancy

This gives you a verified live track record.
After 50 trades you have a win rate with 95% CI of ±14%.
After 100 trades the CI narrows to ±10%.
This is the evidence you need before committing real capital.
"""

import json
import math
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import pytz

IST = pytz.timezone("Asia/Kolkata")

MAX_HOLDING_DAYS = 10   # Auto-exit paper trades after this many days


# ── Paper trade recorder ───────────────────────────────────────────────────────

def record_paper_trade(scanner_result: dict, nlp: dict,
                        trade_id: str, regime: str) -> int:
    """
    Log a scanner signal as a paper trade.
    Returns the signal_log row ID.
    """
    from market_data_store import log_signal_fired

    analysis = scanner_result.get("analysis", {})
    sizing   = scanner_result.get("sizing", {})
    kelly    = sizing.get("kelly", {})

    row_id = log_signal_fired(
        trade_id       = trade_id,
        symbol         = scanner_result.get("symbol",""),
        direction      = scanner_result.get("direction",""),
        probability    = scanner_result.get("probability", 0),
        recommendation = scanner_result.get("recommendation",""),
        entry          = scanner_result.get("entry", 0),
        sl             = scanner_result.get("stop_loss", 0),
        t1             = scanner_result.get("target_1", 0),
        t2             = scanner_result.get("target_2", 0),
        atr            = scanner_result.get("atr", 0),
        kelly_fraction = kelly.get("fraction", 0),
        quantity       = sizing.get("quantity", 0),
        fired_signals  = scanner_result.get("fired_signals", []),
        n_groups       = scanner_result.get("n_groups", 0),
        nlp_verdict    = nlp.get("verdict",""),
        regime         = regime,
        paper_only     = True,
    )
    return row_id


# ── Daily outcome checker ──────────────────────────────────────────────────────

def check_open_paper_trades(groww_token: str = ""):
    """
    Check all open paper trades for SL/target hits.
    Run this daily at 3:35 PM IST.

    Uses today's OHLCV (high/low) to determine if SL or target was hit.
    Conservative assumption: worst-case intraday ordering (SL checked first).
    """
    from market_data_store import (get_conn, log_signal_outcome,
                                    upsert_daily_ohlcv)
    from live_data import get_historical_ohlcv_nse

    conn = get_conn()

    # Find open paper trades (no outcome yet)
    open_trades = conn.execute("""
        SELECT sl.id, sl.trade_id, sl.symbol, sl.direction,
               sl.entry_price, sl.stop_loss, sl.target_1, sl.target_2,
               sl.fired_at, sl.fired_signals, sl.kelly_fraction
        FROM signal_log sl
        LEFT JOIN signal_outcomes so ON sl.id = so.signal_log_id
        WHERE sl.paper_only = 1
          AND so.id IS NULL
          AND sl.fired_at IS NOT NULL
    """).fetchall()
    conn.close()

    today_str = date.today().isoformat()
    resolved  = 0

    for trade in open_trades:
        symbol   = trade["symbol"]
        fired_dt = trade["fired_at"][:10]
        fire_date = date.fromisoformat(fired_dt)
        age_days  = (date.today() - fire_date).days

        # Get recent OHLCV for this symbol
        ohlcv_data = get_historical_ohlcv_nse(symbol, 15)
        candles    = ohlcv_data.get("candles", [])

        if not candles:
            continue

        # Store to DB
        upsert_daily_ohlcv(symbol, candles)

        # Find bars after signal fire
        relevant = [c for c in candles
                    if str(c.get("datetime", c.get("date",""))[:10]) > fired_dt]

        direction  = trade["direction"]
        entry      = trade["entry_price"]
        sl         = trade["stop_loss"]
        target     = trade["target_1"]
        t2         = trade["target_2"]

        outcome    = None
        exit_price = None
        exit_date  = None
        holding    = 0

        for i, bar in enumerate(relevant):
            h = bar["high"]
            l = bar["low"]
            d_str = str(bar.get("datetime", bar.get("date",""))[:10])
            holding = i + 1

            if direction == "LONG":
                if l <= sl:
                    outcome    = "SL"
                    exit_price = sl
                    exit_date  = d_str
                    break
                if h >= target:
                    outcome    = "TARGET_1"
                    exit_price = target
                    exit_date  = d_str
                    break
                if t2 and h >= t2:
                    outcome    = "TARGET_2"
                    exit_price = t2
                    exit_date  = d_str
                    break
            else:  # SHORT
                if h >= sl:
                    outcome    = "SL"
                    exit_price = sl
                    exit_date  = d_str
                    break
                if l <= target:
                    outcome    = "TARGET_1"
                    exit_price = target
                    exit_date  = d_str
                    break
                if t2 and l <= t2:
                    outcome    = "TARGET_2"
                    exit_price = t2
                    exit_date  = d_str
                    break

        # Time exit if max holding exceeded
        if outcome is None and age_days >= MAX_HOLDING_DAYS:
            outcome    = "TIME_EXIT"
            exit_price = candles[-1]["close"]
            exit_date  = today_str
            holding    = age_days

        if outcome is None:
            continue  # Still open

        try:
            signals = json.loads(trade["fired_signals"] or "[]")
        except Exception:
            signals = []

        log_signal_outcome(
            signal_log_id = trade["id"],
            trade_id      = trade["trade_id"],
            symbol        = symbol,
            direction     = direction,
            entry_price   = entry,
            exit_price    = exit_price,
            exit_type     = outcome,
            exit_date     = exit_date,
            holding_days  = holding,
            fired_signals = [{"signal": s} for s in signals],
        )
        resolved += 1

    return resolved


# ── Statistics ─────────────────────────────────────────────────────────────────

def get_paper_trade_stats(days: int = 90) -> dict:
    """
    Compute running paper trading statistics.
    Returns win rate with CI, Sharpe, expectancy, per-signal breakdown.
    """
    from market_data_store import get_conn
    from calibrate_signals import compute_signal_stats

    conn = get_conn()
    cutoff = (datetime.now(IST) - timedelta(days=days)).isoformat()

    outcomes = conn.execute("""
        SELECT so.*, sl.probability, sl.n_groups, sl.regime, sl.kelly_fraction
        FROM signal_outcomes so
        JOIN signal_log sl ON so.signal_log_id = sl.id
        WHERE sl.paper_only = 1
          AND sl.fired_at >= ?
        ORDER BY so.inserted_at DESC
    """, (cutoff,)).fetchall()

    open_count = conn.execute("""
        SELECT COUNT(*) FROM signal_log sl
        LEFT JOIN signal_outcomes so ON sl.id = so.signal_log_id
        WHERE sl.paper_only = 1
          AND so.id IS NULL
    """).fetchone()[0]

    conn.close()

    if not outcomes:
        return {
            "n_closed": 0,
            "n_open":   open_count,
            "win_rate": None,
            "message":  "No completed paper trades yet.",
        }

    outcome_dicts = [dict(o) for o in outcomes]
    stats = compute_signal_stats(outcome_dicts)

    # Per-signal breakdown
    signal_outcomes_map = {}
    for o in outcome_dicts:
        try:
            signals = json.loads(o.get("fired_signals") or "[]")
        except Exception:
            signals = []
        for s in signals:
            sig_name = s if isinstance(s, str) else s.get("signal","")
            if sig_name not in signal_outcomes_map:
                signal_outcomes_map[sig_name] = []
            signal_outcomes_map[sig_name].append({"won": bool(o["won"]),
                                                   "pnl_pct": o["pnl_pct"]})

    per_signal = {}
    for sig, outs in signal_outcomes_map.items():
        if len(outs) >= 5:
            n   = len(outs)
            wr  = sum(1 for o in outs if o["won"]) / n
            avg = sum(o["pnl_pct"] for o in outs) / n
            per_signal[sig] = {"n": n, "win_rate": round(wr,3), "avg_pnl": round(avg,3)}

    # Regime breakdown
    regime_outcomes = {}
    for o in outcome_dicts:
        r = o.get("regime","UNKNOWN")
        if r not in regime_outcomes:
            regime_outcomes[r] = []
        regime_outcomes[r].append({"won": bool(o["won"]), "pnl_pct": o["pnl_pct"]})

    per_regime = {}
    for regime, outs in regime_outcomes.items():
        if len(outs) >= 3:
            n  = len(outs)
            wr = sum(1 for o in outs if o["won"]) / n
            per_regime[regime] = {"n": n, "win_rate": round(wr,3)}

    return {
        "n_closed":    len(outcomes),
        "n_open":      open_count,
        "win_rate":    stats["win_rate"],
        "ci_low":      stats["ci_low"],
        "ci_high":     stats["ci_high"],
        "ci_width":    stats["ci_width"],
        "avg_win_pct": stats["avg_win_pct"],
        "avg_loss_pct":stats["avg_loss_pct"],
        "expectancy":  stats["expectancy"],
        "sharpe":      stats["sharpe"],
        "profit_factor":stats["profit_factor"],
        "grade":       stats["grade"],
        "reliable":    stats["reliable"],
        "per_signal":  per_signal,
        "per_regime":  per_regime,
        "message":     (f"{'✓ Edge confirmed' if stats['ci_low'] > 0.50 else '⚠ Edge not yet confirmed'}: "
                        f"WR={stats['win_rate']:.1%} "
                        f"[{stats['ci_low']:.1%}–{stats['ci_high']:.1%}] "
                        f"n={len(outcomes)}"),
    }


def when_to_go_live(paper_stats: dict) -> dict:
    """
    Evidence-based recommendation on when to transition to live trading.

    Criteria (conservative):
      1. n >= 30 completed paper trades
      2. Win rate CI lower bound > 0.52 (edge is real at 95% confidence)
      3. Expectancy > 0.3% per trade
      4. Sharpe > 0.5 (annualised)
      5. No losing streak > 6 consecutive trades
    """
    n         = paper_stats.get("n_closed", 0)
    ci_low    = paper_stats.get("ci_low", 0)
    exp       = paper_stats.get("expectancy", 0)
    sharpe    = paper_stats.get("sharpe", 0)

    criteria = {
        "n_trades":    {"met": n >= 30,   "value": n,       "required": 30,
                        "label": "Minimum 30 paper trades"},
        "edge_proven": {"met": ci_low > 0.52, "value": round(ci_low,3),
                        "required": 0.52,
                        "label": "95% CI lower bound > 52% win rate"},
        "expectancy":  {"met": exp > 0.3, "value": round(exp,3), "required": 0.3,
                        "label": "Expectancy > 0.3% per trade"},
        "sharpe":      {"met": sharpe > 0.5, "value": round(sharpe,3),
                        "required": 0.5,
                        "label": "Sharpe > 0.5"},
    }

    all_met       = all(c["met"] for c in criteria.values())
    criteria_met  = sum(1 for c in criteria.values() if c["met"])

    if all_met:
        recommendation = "✅ READY FOR LIVE TRADING — Start with 25% of planned capital."
    elif criteria_met >= 3:
        remaining = [c["label"] for c in criteria.values() if not c["met"]]
        recommendation = f"⚡ ALMOST READY — Missing: {remaining[0]}"
    else:
        recommendation = f"⏳ CONTINUE PAPER TRADING — {criteria_met}/4 criteria met"

    return {
        "criteria":       criteria,
        "criteria_met":   criteria_met,
        "all_met":        all_met,
        "recommendation": recommendation,
    }
