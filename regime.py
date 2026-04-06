"""
regime.py — Market Regime Detector + Dynamic Agent Weight Adjustment
HIVE MIND ALPHA · Tier 3

Detects current market regime from live data:
- BULL TREND, BEAR TREND, SIDEWAYS, HIGH VOLATILITY, LOW VOLATILITY, CRISIS

Adjusts agent weights dynamically based on which agents perform best
in the detected regime (from historical backtest + live performance data).
"""

import json
import os
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
REGIME_FILE = "regime_history.json"


# ── Regime definitions ─────────────────────────────────────────────────────────
REGIMES = {
    "BULL_TREND":      "Strong uptrend with momentum — trend-following strategies work best",
    "BEAR_TREND":      "Sustained downtrend — short strategies and hedges outperform",
    "SIDEWAYS":        "Range-bound market — mean-reversion and options selling favoured",
    "HIGH_VOLATILITY": "Elevated VIX — directional options buys and tight stops needed",
    "LOW_VOLATILITY":  "Compressed VIX — options selling and carry strategies work",
    "CRISIS":          "Extreme fear — only defensive positions, contrarian long setups",
    "RECOVERY":        "Post-crash recovery — quality longs, sector rotation opportunities",
}

# Agent effectiveness per regime (0-1 score — higher = more weight)
REGIME_AGENT_SCORES = {
    "BULL_TREND": {
        "quant_oracle":      0.85,  # Momentum signals fire well
        "value_sentinel":    0.60,  # Fundamentals less urgent in bull
        "macro_titan":       0.75,  # FII flows driving bull
        "chart_hawk":        0.90,  # Breakouts and trend following shine
        "options_architect": 0.70,  # CE buying works well
        "sector_guru":       0.85,  # Sector rotation in bull market
        "risk_guardian":     0.50,  # Less needed in bull, may drag
        "behavioral_lens":   0.65,  # Some FOMO signals
    },
    "BEAR_TREND": {
        "quant_oracle":      0.80,
        "value_sentinel":    0.70,  # Finding value in beaten-down quality
        "macro_titan":       0.90,  # Macro drives bear markets
        "chart_hawk":        0.85,  # Breakdowns and resistance key
        "options_architect": 0.90,  # PE buying, protective puts key
        "sector_guru":       0.65,
        "risk_guardian":     0.95,  # Most important in bear market
        "behavioral_lens":   0.80,  # Panic and fear signals
    },
    "SIDEWAYS": {
        "quant_oracle":      0.90,  # Mean-reversion signals
        "value_sentinel":    0.80,  # Value plays in range
        "macro_titan":       0.55,  # Less macro signal
        "chart_hawk":        0.75,  # Support/resistance key
        "options_architect": 0.95,  # Options selling, iron condors
        "sector_guru":       0.80,  # Sector-specific opportunities
        "risk_guardian":     0.70,
        "behavioral_lens":   0.85,  # Range extremes = sentiment extremes
    },
    "HIGH_VOLATILITY": {
        "quant_oracle":      0.70,
        "value_sentinel":    0.65,
        "macro_titan":       0.80,
        "chart_hawk":        0.65,  # Charts less reliable in volatility
        "options_architect": 0.95,  # Options specialist
        "sector_guru":       0.60,
        "risk_guardian":     0.90,  # Critical in high vol
        "behavioral_lens":   0.85,  # Fear signals most important
    },
    "LOW_VOLATILITY": {
        "quant_oracle":      0.85,
        "value_sentinel":    0.80,
        "macro_titan":       0.70,
        "chart_hawk":        0.80,
        "options_architect": 0.90,  # Selling strategies favoured
        "sector_guru":       0.80,
        "risk_guardian":     0.50,  # Less needed
        "behavioral_lens":   0.70,
    },
    "CRISIS": {
        "quant_oracle":      0.60,
        "value_sentinel":    0.85,  # Long-term value opportunities
        "macro_titan":       0.90,  # Macro is everything in crisis
        "chart_hawk":        0.55,
        "options_architect": 0.80,  # Tail risk hedging
        "sector_guru":       0.65,
        "risk_guardian":     1.00,  # Most important
        "behavioral_lens":   0.90,  # Extreme sentiment = contrarian opportunity
    },
    "RECOVERY": {
        "quant_oracle":      0.80,
        "value_sentinel":    0.90,  # Value stocks recover fastest
        "macro_titan":       0.85,
        "chart_hawk":        0.80,  # Bottoming patterns
        "options_architect": 0.75,
        "sector_guru":       0.90,  # Sector rotation is key in recovery
        "risk_guardian":     0.70,
        "behavioral_lens":   0.80,  # Sentiment shifts matter
    },
}


# ── Regime detection ───────────────────────────────────────────────────────────

def detect_regime(indices_data: dict, vix_data: dict,
                   fii_data: dict = None) -> dict:
    """
    Detect current market regime from live data.
    Returns {regime, confidence, signals, agent_weight_boost}
    """
    signals   = []
    scores    = {r: 0 for r in REGIMES}

    idx = indices_data.get("data", {})
    nifty  = idx.get("NIFTY 50", {})
    sensex = idx.get("SENSEX", {})
    bnk    = idx.get("BANKNIFTY", {})
    vix    = vix_data.get("vix", 15) if vix_data.get("success") else 15

    nifty_chg  = nifty.get("change_pct", 0)
    sensex_chg = sensex.get("change_pct", 0)
    bnk_chg    = bnk.get("change_pct", 0)
    avg_chg    = (nifty_chg + sensex_chg + bnk_chg) / 3

    # VIX signals
    if vix > 30:
        scores["CRISIS"]          += 30
        scores["HIGH_VOLATILITY"] += 15
        signals.append(f"VIX={vix:.1f} (EXTREME FEAR — crisis regime)")
    elif vix > 22:
        scores["HIGH_VOLATILITY"] += 25
        scores["BEAR_TREND"]      += 10
        signals.append(f"VIX={vix:.1f} (elevated — high vol regime)")
    elif vix < 13:
        scores["LOW_VOLATILITY"]  += 25
        scores["BULL_TREND"]      += 10
        signals.append(f"VIX={vix:.1f} (compressed — low vol regime)")
    elif 13 <= vix <= 16:
        scores["BULL_TREND"]      += 10
        scores["LOW_VOLATILITY"]  += 5
        signals.append(f"VIX={vix:.1f} (calm)")
    else:
        scores["SIDEWAYS"]        += 5
        signals.append(f"VIX={vix:.1f} (moderate)")

    # Trend signals from index moves
    if avg_chg > 1.5:
        scores["BULL_TREND"]  += 20
        signals.append(f"Strong up day: avg index change +{avg_chg:.1f}%")
    elif avg_chg > 0.5:
        scores["BULL_TREND"]  += 10
        signals.append(f"Positive day: avg index change +{avg_chg:.1f}%")
    elif avg_chg < -1.5:
        scores["BEAR_TREND"]  += 20
        signals.append(f"Strong down day: avg index change {avg_chg:.1f}%")
    elif avg_chg < -0.5:
        scores["BEAR_TREND"]  += 10
        signals.append(f"Negative day: avg index change {avg_chg:.1f}%")
    else:
        scores["SIDEWAYS"]    += 15
        signals.append(f"Flat day: avg index change {avg_chg:.1f}%")

    # FII signals
    if fii_data and fii_data.get("success"):
        fii_net = fii_data.get("fii_net_today", 0)
        fii_5d  = fii_data.get("fii_5d_net", 0)

        if fii_5d > 3000:
            scores["BULL_TREND"]  += 15
            signals.append(f"FII 5-day buying ₹{fii_5d:.0f} Cr — institutional bull")
        elif fii_5d < -3000:
            scores["BEAR_TREND"]  += 15
            signals.append(f"FII 5-day selling ₹{fii_5d:.0f} Cr — institutional bear")
        elif fii_net > 1000:
            scores["BULL_TREND"]  += 8
        elif fii_net < -1000:
            scores["BEAR_TREND"]  += 8

    # CRISIS check — extreme VIX + severe selloff
    if vix > 28 and avg_chg < -2.0:
        scores["CRISIS"] += 25
        signals.append("CRISIS CONDITIONS: Extreme VIX + severe selloff")

    # RECOVERY check — VIX falling + positive returns
    if 16 < vix < 24 and avg_chg > 0.8:
        scores["RECOVERY"] += 15
        signals.append("Recovery signals: VIX declining, market bouncing")

    # Pick regime with highest score
    regime     = max(scores, key=scores.get)
    top_score  = scores[regime]
    total      = sum(scores.values())
    confidence = round(top_score / max(total, 1) * 100, 1)

    # Get agent weight boosts for this regime
    regime_scores = REGIME_AGENT_SCORES.get(regime, {aid: 0.75 for aid in REGIME_AGENT_SCORES["SIDEWAYS"]})

    # Normalise to weights that sum to 1.0
    total_score = sum(regime_scores.values())
    weights = {aid: round(s / total_score, 4) for aid, s in regime_scores.items()}

    return {
        "regime":      regime,
        "description": REGIMES.get(regime, ""),
        "confidence":  confidence,
        "signals":     signals,
        "all_scores":  scores,
        "regime_weights": weights,
        "timestamp":   datetime.now(IST).isoformat(),
    }


def get_blended_weights(regime_weights: dict,
                         performance_weights: dict,
                         regime_confidence: float = 70.0) -> dict:
    """
    Blend regime-based weights with historical performance weights.
    Higher regime confidence = more regime weight.
    """
    from agent_tracker import AGENT_IDS
    regime_blend = min(regime_confidence / 100, 0.6)  # Max 60% regime influence
    perf_blend   = 1.0 - regime_blend

    blended = {}
    for aid in AGENT_IDS:
        rw = regime_weights.get(aid, 1/8)
        pw = performance_weights.get(aid, 1/8)
        blended[aid] = regime_blend * rw + perf_blend * pw

    # Normalise
    total = sum(blended.values())
    return {aid: round(w / total, 4) for aid, w in blended.items()}


def save_regime(regime_data: dict):
    """Save regime detection to history file."""
    history = []
    if os.path.exists(REGIME_FILE):
        try:
            with open(REGIME_FILE) as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(regime_data)
    history = history[-500:]  # Keep last 500 detections
    with open(REGIME_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def get_regime_history(last_n: int = 20) -> list:
    if not os.path.exists(REGIME_FILE):
        return []
    try:
        with open(REGIME_FILE) as f:
            data = json.load(f)
        return data[-last_n:]
    except Exception:
        return []


def get_regime_stats() -> dict:
    """Summarise regime distribution over recent history."""
    history = get_regime_history(100)
    if not history:
        return {}
    counts = {}
    for h in history:
        r = h.get("regime","UNKNOWN")
        counts[r] = counts.get(r, 0) + 1
    total = len(history)
    return {r: round(c/total*100, 1) for r, c in counts.items()}
