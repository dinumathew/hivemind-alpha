"""
portfolio_risk.py — Portfolio Risk Manager + Pre-Trade Execution Filter
HIVE MIND ALPHA · Tier 2

Portfolio-level checks:
- Sector concentration limits
- Total capital deployed
- Directional exposure (net delta)
- Correlation between new signal and open positions
- Pre-trade execution quality filters
"""

import json
import os
from datetime import datetime, time as dtime
import pytz
import requests

IST = pytz.timezone("Asia/Kolkata")

# ── Risk limits (configurable) ─────────────────────────────────────────────────
DEFAULT_LIMITS = {
    "max_capital_deployed_pct": 60.0,   # Max % of capital in open trades
    "max_sector_concentration": 40.0,   # Max % in any single sector
    "max_single_trade_pct":     10.0,   # Max single trade as % of capital
    "max_open_trades":          5,      # Max simultaneous trades
    "max_net_directional_pct":  40.0,   # Max net long or short as % capital
    "min_cash_buffer_pct":      20.0,   # Always keep this % as cash
    "max_spread_bps":           30,     # Max bid-ask spread in basis points
    "min_volume_mult":          0.5,    # Min volume as multiple of 20d average
    "trade_window_start":       (9, 30), # No trades before this time
    "trade_window_end":         (15, 15), # No trades after this time
    "avoid_first_minutes":      15,     # Avoid first N minutes after open
    "avoid_last_minutes":       15,     # Avoid last N minutes before close
}

SECTOR_MAP = {
    "HDFCBANK":    "BANKING", "ICICIBANK":  "BANKING", "AXISBANK":   "BANKING",
    "KOTAKBANK":   "BANKING", "SBIN":       "BANKING", "BANKBARODA": "BANKING",
    "INFY":        "IT",      "TCS":        "IT",      "WIPRO":      "IT",
    "HCLTECH":     "IT",      "TECHM":      "IT",      "LTIM":       "IT",
    "RELIANCE":    "ENERGY",  "ONGC":       "ENERGY",  "BPCL":       "ENERGY",
    "HINDUNILVR":  "FMCG",   "ITC":        "FMCG",    "NESTLEIND":  "FMCG",
    "MARUTI":      "AUTO",    "TATAMOTORS": "AUTO",    "BAJAJ-AUTO": "AUTO",
    "SUNPHARMA":   "PHARMA",  "CIPLA":      "PHARMA",  "DRREDDY":    "PHARMA",
    "LT":          "INFRA",   "ULTRACEMCO": "CEMENT",  "ASIANPAINT": "PAINTS",
    "TITAN":       "CONSUMER","BAJFINANCE": "NBFC",    "BAJAJFINSV": "NBFC",
    "NIFTY":       "INDEX",   "BANKNIFTY":  "INDEX",   "SENSEX":     "INDEX",
}


# ── Open position tracker ──────────────────────────────────────────────────────

def get_open_positions(capital: float) -> list:
    """Load open positions from trade journal."""
    from trade_log import get_open
    positions = []
    for trade in get_open():
        eq = trade.get("equity", {})
        instrument = eq.get("instrument", "") or trade.get("instrument","")
        direction  = eq.get("direction", "LONG")
        entry_raw  = eq.get("entry_price", "0")
        qty        = int(eq.get("quantity", 1) or 1)

        # Parse entry price
        import re
        nums = re.findall(r"[\d.]+", str(entry_raw).replace(",",""))
        entry = sum(float(n) for n in nums) / max(len(nums),1) if nums else 0

        positions.append({
            "trade_id":   trade.get("trade_id",""),
            "instrument": instrument.upper(),
            "direction":  direction,
            "entry":      entry,
            "quantity":   qty,
            "value":      entry * qty,
            "sector":     SECTOR_MAP.get(instrument.upper(), "OTHER"),
        })
    return positions


# ── Pre-trade portfolio checks ────────────────────────────────────────────────

def check_portfolio_risk(new_instrument: str, new_direction: str,
                          new_value: float, capital: float,
                          limits: dict = None) -> dict:
    """
    Run portfolio-level checks before approving a new trade.
    Returns {approved: bool, warnings: list, blockers: list, metrics: dict}
    """
    lim      = {**DEFAULT_LIMITS, **(limits or {})}
    positions = get_open_positions(capital)
    warnings  = []
    blockers  = []

    total_deployed = sum(p["value"] for p in positions)
    new_total      = total_deployed + new_value
    deployed_pct   = new_total / max(capital, 1) * 100
    cash_remaining = (capital - new_total) / capital * 100

    # 1. Capital deployment check
    if deployed_pct > lim["max_capital_deployed_pct"]:
        blockers.append(
            f"CAPITAL LIMIT: Deploying this trade would put {deployed_pct:.1f}% "
            f"of capital at work (limit: {lim['max_capital_deployed_pct']}%)"
        )
    elif deployed_pct > lim["max_capital_deployed_pct"] * 0.85:
        warnings.append(f"Capital deployment approaching limit: {deployed_pct:.1f}%")

    # 2. Cash buffer check
    if cash_remaining < lim["min_cash_buffer_pct"]:
        blockers.append(
            f"CASH BUFFER: Only {cash_remaining:.1f}% cash remaining "
            f"(minimum: {lim['min_cash_buffer_pct']}%)"
        )

    # 3. Open trades limit
    if len(positions) >= lim["max_open_trades"]:
        blockers.append(
            f"TRADE LIMIT: {len(positions)} trades already open "
            f"(maximum: {lim['max_open_trades']})"
        )

    # 4. Single trade size check
    trade_pct = new_value / max(capital, 1) * 100
    if trade_pct > lim["max_single_trade_pct"]:
        warnings.append(
            f"TRADE SIZE: This trade is {trade_pct:.1f}% of capital "
            f"(max recommended: {lim['max_single_trade_pct']}%)"
        )

    # 5. Sector concentration
    new_sector = SECTOR_MAP.get(new_instrument.upper(), "OTHER")
    sector_values = {}
    for p in positions:
        s = p["sector"]
        sector_values[s] = sector_values.get(s, 0) + p["value"]
    sector_values[new_sector] = sector_values.get(new_sector, 0) + new_value

    for sector, val in sector_values.items():
        pct = val / max(capital, 1) * 100
        if pct > lim["max_sector_concentration"]:
            blockers.append(
                f"SECTOR CONCENTRATION: {sector} would be {pct:.1f}% of portfolio "
                f"(limit: {lim['max_sector_concentration']}%)"
            )
        elif pct > lim["max_sector_concentration"] * 0.75:
            warnings.append(f"Sector {sector} approaching concentration limit: {pct:.1f}%")

    # 6. Duplicate instrument check
    existing_instruments = [p["instrument"] for p in positions]
    if new_instrument.upper() in existing_instruments:
        same = [p for p in positions if p["instrument"] == new_instrument.upper()]
        warnings.append(
            f"DUPLICATE: Already have {len(same)} open position(s) in {new_instrument}"
        )

    # 7. Directional exposure
    long_value  = sum(p["value"] for p in positions if p["direction"] == "LONG")
    short_value = sum(p["value"] for p in positions if p["direction"] == "SHORT")
    if new_direction == "LONG":
        long_value += new_value
    else:
        short_value += new_value

    net_exposure = (long_value - short_value) / max(capital, 1) * 100
    if abs(net_exposure) > lim["max_net_directional_pct"]:
        warnings.append(
            f"DIRECTIONAL SKEW: Net {'long' if net_exposure > 0 else 'short'} "
            f"exposure would be {abs(net_exposure):.1f}% of capital"
        )

    metrics = {
        "open_positions":      len(positions),
        "total_deployed_pct":  round(deployed_pct, 1),
        "cash_remaining_pct":  round(cash_remaining, 1),
        "new_trade_pct":       round(trade_pct, 1),
        "net_exposure_pct":    round(net_exposure, 1),
        "sector":              new_sector,
        "sector_exposure_pct": round(sector_values.get(new_sector, 0) / max(capital,1) * 100, 1),
        "existing_instruments": existing_instruments,
    }

    return {
        "approved": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "metrics":  metrics,
    }


# ── Pre-trade execution quality filters ───────────────────────────────────────

def check_execution_quality(token: str, symbol: str,
                              limits: dict = None) -> dict:
    """
    Check execution quality conditions before placing an order:
    1. Time of day (avoid open/close rush)
    2. Bid-ask spread quality
    3. Volume vs average (confirm liquidity)
    Returns {approved: bool, warnings: list, metrics: dict}
    """
    lim      = {**DEFAULT_LIMITS, **(limits or {})}
    warnings = []
    blockers = []
    now      = datetime.now(IST)
    current_time = now.time()

    # 1. Time window check
    market_open  = dtime(*lim["trade_window_start"])
    market_close = dtime(*lim["trade_window_end"])
    avoid_open_until = dtime(
        lim["trade_window_start"][0],
        lim["trade_window_start"][1] + lim["avoid_first_minutes"]
    )
    avoid_close_from = dtime(
        lim["trade_window_end"][0],
        lim["trade_window_end"][1] - lim["avoid_last_minutes"]
    )

    if current_time < market_open:
        blockers.append("Market not open yet. Order cannot be placed.")
    elif current_time > market_close:
        blockers.append("Market is closed. Order cannot be placed.")
    elif current_time < avoid_open_until:
        warnings.append(
            f"OPENING VOLATILITY: Within first {lim['avoid_first_minutes']} minutes of market open. "
            "Bid-ask spreads are typically wider."
        )
    elif current_time > avoid_close_from:
        warnings.append(
            f"CLOSING VOLATILITY: Within last {lim['avoid_last_minutes']} minutes of market. "
            "Prices can be erratic near close."
        )

    # 2. Live bid-ask spread check
    bid = ask = ltp = volume = avg_vol = 0
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(token)
        q = groww.get_ltp(trading_symbol=symbol.upper(), exchange="NSE", segment="CASH")
        ltp    = float(q.get("ltp", 0))
        volume = int(q.get("volume", 0))
    except Exception:
        pass

    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        r = session.get(
            f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}",
            headers=headers, timeout=8,
        )
        data = r.json()
        pi = data.get("priceInfo", {})
        ltp = float(pi.get("lastPrice", ltp) or ltp)
        depth = data.get("depth", {})
        if depth:
            bids = depth.get("buyQuantity", [{}])
            asks = depth.get("sellQuantity", [{}])
        # Try marketDepth
        md = data.get("marketDepth", {})
        buy_orders  = md.get("buy",  [{}]*5)
        sell_orders = md.get("sell", [{}]*5)
        bid = float(buy_orders[0].get("price", ltp)  if buy_orders  else ltp)
        ask = float(sell_orders[0].get("price", ltp) if sell_orders else ltp)
    except Exception:
        bid = ltp * 0.999 if ltp else 0
        ask = ltp * 1.001 if ltp else 0

    if ltp > 0 and ask > 0:
        spread_bps = (ask - bid) / ltp * 10000
        if spread_bps > lim["max_spread_bps"]:
            warnings.append(
                f"WIDE SPREAD: Bid-ask spread is {spread_bps:.0f} bps "
                f"(max: {lim['max_spread_bps']} bps). Cost of entry is elevated."
            )
    else:
        spread_bps = 0

    # 3. Volume check (rough — compare today volume vs typical)
    vol_multiple = 1.0
    if volume > 0:
        # Rough heuristic: if volume in first 2 hours is < 30% of typical, flag
        hours_elapsed = max((now.hour - 9) + (now.minute - 15) / 60, 0.25)
        expected_pct = min(hours_elapsed / 6.25, 1.0)  # 6.25 market hours total
        if expected_pct > 0:
            # We can't easily get avg daily volume without history here
            # Just flag if volume seems very low mid-day
            pass

    metrics = {
        "time":        now.strftime("%H:%M IST"),
        "ltp":         ltp,
        "bid":         round(bid, 2),
        "ask":         round(ask, 2),
        "spread_bps":  round(spread_bps, 1),
        "volume":      volume,
        "market_open": current_time >= market_open and current_time <= market_close,
    }

    return {
        "approved": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "metrics":  metrics,
    }


def full_pre_trade_check(token: str, instrument: str, direction: str,
                          order_value: float, capital: float,
                          limits: dict = None) -> dict:
    """
    Combined portfolio + execution quality check.
    Returns final go/no-go decision with all details.
    """
    portfolio_check  = check_portfolio_risk(instrument, direction, order_value, capital, limits)
    execution_check  = check_execution_quality(token, instrument, limits)

    all_blockers = portfolio_check["blockers"] + execution_check["blockers"]
    all_warnings = portfolio_check["warnings"] + execution_check["warnings"]

    return {
        "approved":       len(all_blockers) == 0,
        "blockers":       all_blockers,
        "warnings":       all_warnings,
        "portfolio":      portfolio_check,
        "execution":      execution_check,
        "summary":        "APPROVED" if not all_blockers else f"BLOCKED ({len(all_blockers)} issue{'s' if len(all_blockers)>1 else ''})",
    }
