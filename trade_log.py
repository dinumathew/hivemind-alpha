"""
trade_log.py — Trade journal, pending queue, audit trail
HIVE MIND ALPHA
"""

import json
import os
import uuid
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
LOG_FILE = "trade_journal.json"


def _load() -> list:
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save(records: list):
    with open(LOG_FILE, "w") as f:
        json.dump(records, f, indent=2, default=str)


def log_signal(query: str, mode: str, consensus: dict) -> str:
    """Log a new trade signal. Returns trade_id."""
    trade_id = str(uuid.uuid4())[:8].upper()
    records = _load()
    records.append({
        "trade_id":   trade_id,
        "timestamp":  datetime.now(IST).isoformat(),
        "query":      query,
        "mode":       mode,
        "stance":     consensus.get("overall_stance", "—"),
        "conviction": consensus.get("conviction", "—"),
        "agreement":  consensus.get("agent_agreement_pct", "—"),
        "thesis":     consensus.get("key_thesis", "—"),
        "equity":     consensus.get("equity_trade", {}),
        "options":    consensus.get("options_trade", {}),
        "status":     "PENDING_APPROVAL",
        "decision":   None,
        "order_id":   None,
        "pnl":        None,
        "notes":      "",
    })
    _save(records)
    return trade_id


def update_status(trade_id: str, status: str,
                  decision: str = None, order_id: str = None,
                  notes: str = ""):
    records = _load()
    for r in records:
        if r["trade_id"] == trade_id:
            r["status"]   = status
            if decision:  r["decision"]  = decision
            if order_id:  r["order_id"]  = order_id
            if notes:     r["notes"]     = notes
            r["updated"]  = datetime.now(IST).isoformat()
    _save(records)


def update_pnl(trade_id: str, pnl: float, exit_price: str = ""):
    records = _load()
    for r in records:
        if r["trade_id"] == trade_id:
            r["pnl"]        = pnl
            r["exit_price"] = exit_price
            r["status"]     = "CLOSED"
            r["closed_at"]  = datetime.now(IST).isoformat()
    _save(records)


def get_all() -> list:
    return _load()


def get_pending() -> list:
    return [r for r in _load() if r["status"] == "PENDING_APPROVAL"]


def get_open() -> list:
    return [r for r in _load() if r["status"] == "EXECUTED"]


def get_summary() -> dict:
    records = _load()
    total    = len(records)
    executed = [r for r in records if r.get("decision") == "approved"]
    rejected = [r for r in records if r.get("decision") == "rejected"]
    closed   = [r for r in records if r.get("pnl") is not None]
    total_pnl = sum(r["pnl"] for r in closed if r["pnl"] is not None)
    winners  = [r for r in closed if r.get("pnl", 0) > 0]
    losers   = [r for r in closed if r.get("pnl", 0) < 0]

    return {
        "total_signals": total,
        "executed":      len(executed),
        "rejected":      len(rejected),
        "open":          len(get_open()),
        "closed":        len(closed),
        "total_pnl":     total_pnl,
        "win_rate":      round(len(winners) / max(len(closed), 1) * 100, 1),
        "winners":       len(winners),
        "losers":        len(losers),
    }
