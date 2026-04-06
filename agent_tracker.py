"""
agent_tracker.py — Agent Performance Tracker + Walk-Forward Weight Calibration
HIVE MIND ALPHA · Tier 1 + Tier 3

Tracks which agents voted correctly on closed trades.
Monthly walk-forward recalibration of agent weights.
Agents with better recent track records get higher consensus weight.
"""

import json
import os
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")
TRACKER_FILE = "agent_performance.json"

AGENT_IDS = [
    "quant_oracle", "value_sentinel", "macro_titan", "chart_hawk",
    "options_architect", "sector_guru", "risk_guardian", "behavioral_lens",
]

# Default equal weights (sum = 1.0)
DEFAULT_WEIGHTS = {aid: 1/8 for aid in AGENT_IDS}


# ── Data layer ─────────────────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(TRACKER_FILE):
        try:
            with open(TRACKER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "votes": [],           # List of vote records
        "weights": DEFAULT_WEIGHTS.copy(),
        "calibration_log": [],
        "last_calibrated": None,
    }


def _save(data: dict):
    with open(TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ── Vote recording ─────────────────────────────────────────────────────────────

def record_vote(trade_id: str, agent_id: str, voted_direction: str,
                instrument: str, conviction: str):
    """
    Record an agent's vote at signal time.
    Called when a signal fires and each agent has cast a vote.
    """
    data = _load()
    data["votes"].append({
        "trade_id":         trade_id,
        "agent_id":         agent_id,
        "voted_direction":  voted_direction.upper(),
        "instrument":       instrument.upper(),
        "conviction":       conviction.upper(),
        "vote_timestamp":   datetime.now(IST).isoformat(),
        "outcome":          None,  # Filled in when trade closes
        "correct":          None,
    })
    _save(data)


def record_votes_from_scan(trade_id: str, agent_results: dict, instrument: str, direction: str):
    """
    Batch record all agent votes from a scanner cycle.
    agent_results: dict of {agent_id: {direction, conviction, found_opportunity}}
    """
    data = _load()
    for agent_id, result in agent_results.items():
        if not result.get("found_opportunity"):
            continue
        voted_dir = result.get("direction", direction)
        conviction = result.get("conviction", "MEDIUM")
        data["votes"].append({
            "trade_id":         trade_id,
            "agent_id":         agent_id,
            "voted_direction":  voted_dir.upper(),
            "instrument":       instrument.upper(),
            "conviction":       conviction.upper(),
            "vote_timestamp":   datetime.now(IST).isoformat(),
            "outcome":          None,
            "correct":          None,
        })
    _save(data)


def record_trade_outcome(trade_id: str, outcome: str, pnl_pct: float):
    """
    Update all votes for a trade with the actual outcome.
    outcome: "WIN" | "LOSS" | "BREAKEVEN"
    Called when a trade closes (SL hit, target hit, or time exit).
    """
    data   = _load()
    is_win = outcome.upper() == "WIN" or pnl_pct > 0

    for vote in data["votes"]:
        if vote["trade_id"] == trade_id:
            vote["outcome"]  = outcome.upper()
            vote["pnl_pct"]  = round(pnl_pct, 2)
            vote["correct"]  = vote["voted_direction"] == ("LONG" if is_win else "SHORT")
            vote["resolved_at"] = datetime.now(IST).isoformat()

    _save(data)


# ── Performance calculation ────────────────────────────────────────────────────

def get_agent_stats(lookback_days: int = 90) -> dict:
    """
    Calculate performance stats for each agent over the lookback period.
    Returns {agent_id: {win_rate, total_votes, correct_votes, conviction_accuracy, score}}
    """
    data   = _load()
    cutoff = (datetime.now(IST) - timedelta(days=lookback_days)).isoformat()

    stats = {}
    for aid in AGENT_IDS:
        votes = [
            v for v in data["votes"]
            if v["agent_id"] == aid
            and v.get("outcome") is not None
            and v.get("vote_timestamp", "") >= cutoff
        ]

        if not votes:
            stats[aid] = {
                "total_votes":   0,
                "correct_votes": 0,
                "win_rate":      50.0,  # Default neutral
                "high_conv_accuracy": 50.0,
                "score":         50.0,
                "last_vote":     None,
            }
            continue

        correct       = [v for v in votes if v.get("correct")]
        high_conv     = [v for v in votes if v.get("conviction") == "HIGH"]
        high_conv_win = [v for v in high_conv if v.get("correct")]

        win_rate      = len(correct) / len(votes) * 100
        hca           = len(high_conv_win) / max(len(high_conv), 1) * 100

        # Score = weighted blend: win rate + conviction accuracy bonus
        score = win_rate * 0.7 + hca * 0.3

        stats[aid] = {
            "total_votes":          len(votes),
            "correct_votes":        len(correct),
            "win_rate":             round(win_rate, 1),
            "high_conv_votes":      len(high_conv),
            "high_conv_accuracy":   round(hca, 1),
            "score":                round(score, 1),
            "last_vote":            votes[-1]["vote_timestamp"][:10] if votes else None,
        }

    return stats


def get_current_weights() -> dict:
    """Return current calibrated agent weights."""
    data = _load()
    weights = data.get("weights", DEFAULT_WEIGHTS.copy())
    # Ensure all agents present
    for aid in AGENT_IDS:
        if aid not in weights:
            weights[aid] = 1/8
    return weights


# ── Walk-forward calibration ───────────────────────────────────────────────────

def calibrate_weights(lookback_days: int = 60,
                       min_votes_required: int = 5,
                       smoothing: float = 0.3) -> dict:
    """
    Walk-forward weight calibration.
    Agents with better recent performance get higher consensus weight.

    smoothing: 0-1. Higher = more conservative (blends with equal weights).
    Returns new weights dict.
    """
    stats = get_agent_stats(lookback_days)
    data  = _load()

    # Only calibrate agents with enough votes
    calibratable = {
        aid: s for aid, s in stats.items()
        if s["total_votes"] >= min_votes_required
    }

    if len(calibratable) < 3:
        # Not enough data — use equal weights
        new_weights = DEFAULT_WEIGHTS.copy()
        data["calibration_log"].append({
            "timestamp":  datetime.now(IST).isoformat(),
            "reason":     f"Insufficient data ({len(calibratable)} agents with {min_votes_required}+ votes)",
            "new_weights": new_weights,
        })
        data["weights"] = new_weights
        data["last_calibrated"] = datetime.now(IST).isoformat()
        _save(data)
        return new_weights

    # Raw weights from performance scores
    scores = {aid: stats[aid]["score"] for aid in AGENT_IDS}
    total_score = sum(scores.values())

    if total_score == 0:
        raw_weights = DEFAULT_WEIGHTS.copy()
    else:
        raw_weights = {aid: scores[aid] / total_score for aid in AGENT_IDS}

    # Apply smoothing: blend with equal weights to prevent over-fitting
    equal_w = 1 / len(AGENT_IDS)
    smoothed = {
        aid: smoothing * equal_w + (1 - smoothing) * raw_weights[aid]
        for aid in AGENT_IDS
    }

    # Normalise to sum = 1.0
    total = sum(smoothed.values())
    new_weights = {aid: round(w / total, 4) for aid, w in smoothed.items()}

    # Save
    prev_weights = data.get("weights", DEFAULT_WEIGHTS.copy())
    data["weights"] = new_weights
    data["last_calibrated"] = datetime.now(IST).isoformat()
    data["calibration_log"].append({
        "timestamp":    datetime.now(IST).isoformat(),
        "lookback_days":lookback_days,
        "agents_used":  list(calibratable.keys()),
        "prev_weights": prev_weights,
        "new_weights":  new_weights,
        "score_basis":  scores,
    })
    # Keep last 24 calibration records
    data["calibration_log"] = data["calibration_log"][-24:]
    _save(data)
    return new_weights


def should_recalibrate() -> bool:
    """Returns True if 30+ days since last calibration or no calibration ever done."""
    data = _load()
    last = data.get("last_calibrated")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(IST) - last_dt).days >= 30
    except Exception:
        return True


def apply_weights_to_consensus(agent_results: dict) -> dict:
    """
    Reweight agent votes in a scanner result using calibrated weights.
    Used by meta-agent to give higher-scoring agents more influence.
    Returns modified agent_results with 'weight' field added.
    """
    weights = get_current_weights()
    weighted = {}
    for aid, result in agent_results.items():
        weighted[aid] = dict(result)
        weighted[aid]["calibrated_weight"] = weights.get(aid, 1/8)
    return weighted


def get_leaderboard() -> list:
    """Return agents sorted by score descending."""
    stats = get_agent_stats(90)
    names = {
        "quant_oracle":      "Quant Oracle (Jim Simons)",
        "value_sentinel":    "Value Sentinel (Buffett)",
        "macro_titan":       "Macro Titan (Soros)",
        "chart_hawk":        "Chart Hawk (Livermore)",
        "options_architect": "Options Architect (Taleb)",
        "sector_guru":       "Sector Guru (Lynch)",
        "risk_guardian":     "Risk Guardian (Dalio)",
        "behavioral_lens":   "Behavioral Lens (Kahneman)",
    }
    weights = get_current_weights()
    rows = []
    for aid, s in stats.items():
        rows.append({
            "agent_id":     aid,
            "name":         names.get(aid, aid),
            "score":        s["score"],
            "win_rate":     s["win_rate"],
            "total_votes":  s["total_votes"],
            "correct_votes":s["correct_votes"],
            "weight":       round(weights.get(aid, 1/8) * 100, 1),
        })
    return sorted(rows, key=lambda x: x["score"], reverse=True)


def get_calibration_history() -> list:
    data = _load()
    return data.get("calibration_log", [])[-10:]
