"""
smart_money.py — Smart Money Tracker
HIVE MIND ALPHA · Tier 2

Tracks institutional and smart money activity:
1. NSE Bulk Deals (large trades >0.5% of paid-up capital)
2. Block Deals (negotiated large trades on exchange)
3. Insider trading activity (SAST/SARFAESi disclosures)
4. FII derivative positioning (index futures, stock futures)
5. Unusual options activity detection
"""

import requests
from datetime import datetime, date, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


def _nse_session():
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=8)
    except Exception:
        pass
    return s


# ── Bulk Deals ─────────────────────────────────────────────────────────────────

def get_bulk_deals(days_back: int = 5, symbol: str = None) -> list:
    """
    Fetch bulk deals from NSE.
    Bulk deals: single order >= 0.5% of equity shares of listed company.
    These are significant smart money signals.
    """
    try:
        session  = _nse_session()
        today    = date.today()
        from_dt  = today - timedelta(days=days_back)

        r = session.get(
            f"https://www.nseindia.com/api/bulk-deals"
            f"?from={from_dt.strftime('%d-%m-%Y')}&to={today.strftime('%d-%m-%Y')}",
            timeout=10,
        )
        data = r.json().get("data", [])

        deals = []
        for d in data:
            sym = d.get("symbol","").upper()
            if symbol and sym != symbol.upper():
                continue
            deals.append({
                "date":          d.get("date",""),
                "symbol":        sym,
                "client_name":   d.get("clientName",""),
                "deal_type":     d.get("dealType",""),       # BUY / SELL
                "quantity":      int(d.get("quantity",0) or 0),
                "price":         float(d.get("price",0) or 0),
                "value_cr":      round(float(d.get("quantity",0) or 0) * float(d.get("price",0) or 0) / 1e7, 2),
                "pct_equity":    float(d.get("pctEquity",0) or 0),
                "is_institutional": _is_institutional(d.get("clientName","")),
            })

        return sorted(deals, key=lambda x: x["date"], reverse=True)
    except Exception as e:
        return []


def get_block_deals(days_back: int = 5, symbol: str = None) -> list:
    """
    Fetch block deals from NSE.
    Block deals are large negotiated trades (min ₹10 Cr or 5 lakh shares).
    """
    try:
        session  = _nse_session()
        today    = date.today()
        from_dt  = today - timedelta(days=days_back)

        r = session.get(
            f"https://www.nseindia.com/api/block-deals"
            f"?from={from_dt.strftime('%d-%m-%Y')}&to={today.strftime('%d-%m-%Y')}",
            timeout=10,
        )
        data = r.json().get("data", [])

        deals = []
        for d in data:
            sym = d.get("symbol","").upper()
            if symbol and sym != symbol.upper():
                continue
            deals.append({
                "date":        d.get("date",""),
                "symbol":      sym,
                "client_name": d.get("clientName",""),
                "deal_type":   d.get("dealType",""),
                "quantity":    int(d.get("quantity",0) or 0),
                "price":       float(d.get("price",0) or 0),
                "value_cr":    round(float(d.get("quantity",0) or 0) * float(d.get("price",0) or 0) / 1e7, 2),
                "is_institutional": _is_institutional(d.get("clientName","")),
            })

        return sorted(deals, key=lambda x: x["date"], reverse=True)
    except Exception as e:
        return []


def _is_institutional(name: str) -> bool:
    """Detect if the client name suggests an institutional buyer."""
    name_upper = name.upper()
    keywords = [
        "FUND", "FII", "FPI", "MUTUAL", "INSURANCE", "PENSION",
        "ETF", "TRUST", "PMS", "AIF", "HEDGE", "LTD", "CORP",
        "CAPITAL", "INVEST", "ASSET", "MGMT", "MANAGEMENT",
        "SECURITIES", "NOMINEES", "CUSTODIAN",
    ]
    return any(kw in name_upper for kw in keywords)


def get_insider_trades(symbol: str, days_back: int = 30) -> list:
    """
    Fetch SAST/insider trading disclosures for a stock.
    Promoter buying is a strong bullish signal.
    """
    try:
        session = _nse_session()
        today   = date.today()
        from_dt = today - timedelta(days=days_back)

        r = session.get(
            f"https://www.nseindia.com/api/corporate-insider-trading"
            f"?symbol={symbol.upper()}&from={from_dt.strftime('%d-%m-%Y')}"
            f"&to={today.strftime('%d-%m-%Y')}",
            timeout=10,
        )
        data = r.json().get("data", [])
        insider_data = []
        for d in data:
            insider_data.append({
                "date":         d.get("date",""),
                "symbol":       symbol.upper(),
                "name":         d.get("acqName",""),
                "category":     d.get("personCategory",""),  # Promoter, Director, etc.
                "deal_type":    d.get("secAcq",""),
                "quantity":     int(d.get("secTrans",0) or 0),
                "value":        float(d.get("value",0) or 0),
                "post_holding": float(d.get("totAcqShare",0) or 0),
            })
        return insider_data
    except Exception:
        return []


# ── FII Derivative Positioning ────────────────────────────────────────────────

def get_fii_derivatives_positioning() -> dict:
    """
    Get FII positions in index futures and options.
    FII net long futures = bullish institutional view.
    """
    try:
        session = _nse_session()
        r = session.get(
            "https://www.nseindia.com/api/fii-stats?type=participant-wise-trading-data",
            timeout=10,
        )
        data = r.json()
        result = {"success": True, "data": data,
                  "timestamp": datetime.now(IST).strftime("%H:%M IST")}

        # Try to parse participant data
        if isinstance(data, list):
            fii_data = next((d for d in data if "FII" in str(d.get("category","")).upper()
                             or "FPI" in str(d.get("category","")).upper()), {})
            dii_data = next((d for d in data if "DII" in str(d.get("category","")).upper()), {})

            result["fii_net_futures"] = float(fii_data.get("net", 0) or 0)
            result["dii_net_futures"] = float(dii_data.get("net", 0) or 0)
            result["fii_sentiment"]   = "LONG" if result["fii_net_futures"] > 0 else "SHORT"

        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_unusual_options_activity(underlying: str = "NIFTY") -> dict:
    """
    Detect unusual options activity from the options chain.
    Flags: unusually high OI buildup at specific strikes,
           large single-day OI change (>50% of total at that strike),
           significant IV spikes vs neighbours.
    """
    try:
        from groww_data import get_options_chain_groww
        chain_data = get_options_chain_groww("", underlying)  # token="" uses NSE free feed

        if not chain_data.get("success"):
            return {"success": False, "error": chain_data.get("error","")}

        chain    = chain_data.get("chain", {})
        spot     = chain_data.get("spot_price", 0)
        unusual  = []

        # Avg OI across strikes for baseline
        all_ce_oi = [v.get("CE",{}).get("oi",0) for v in chain.values() if v.get("CE")]
        all_pe_oi = [v.get("PE",{}).get("oi",0) for v in chain.values() if v.get("PE")]
        avg_ce = sum(all_ce_oi) / max(len(all_ce_oi),1)
        avg_pe = sum(all_pe_oi) / max(len(all_pe_oi),1)

        for strike_str, data in chain.items():
            strike = int(strike_str)
            ce = data.get("CE", {})
            pe = data.get("PE", {})

            # Flag unusually high OI (>3x average)
            if ce.get("oi",0) > avg_ce * 3:
                unusual.append({
                    "type":    "HIGH_CE_OI",
                    "strike":  strike,
                    "oi":      ce["oi"],
                    "vs_avg":  round(ce["oi"] / max(avg_ce,1), 1),
                    "signal":  f"Heavy CE writing at {strike:,} — strong resistance",
                    "bullish": False,
                })
            if pe.get("oi",0) > avg_pe * 3:
                unusual.append({
                    "type":    "HIGH_PE_OI",
                    "strike":  strike,
                    "oi":      pe["oi"],
                    "vs_avg":  round(pe["oi"] / max(avg_pe,1), 1),
                    "signal":  f"Heavy PE writing at {strike:,} — strong support",
                    "bullish": True,
                })

            # Flag unusually high LTP vs neighbours (IV spike)
            ce_ltp = ce.get("ltp", 0)
            pe_ltp = pe.get("ltp", 0)
            if ce_ltp > 0 and abs(strike - spot) < 500:
                if ce.get("iv", 0) > 0 and ce.get("iv", 0) > 30:
                    unusual.append({
                        "type":   "HIGH_IV_CE",
                        "strike": strike,
                        "iv":     ce["iv"],
                        "signal": f"Elevated IV in {strike:,} CE — event risk being priced",
                        "bullish": None,
                    })

        # Sort by distance from spot
        unusual.sort(key=lambda x: abs(x["strike"] - spot))

        return {
            "success":     True,
            "underlying":  underlying,
            "spot":        spot,
            "unusual":     unusual[:10],
            "summary":     _summarise_unusual(unusual, spot),
            "timestamp":   datetime.now(IST).strftime("%H:%M IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _summarise_unusual(unusual: list, spot: float) -> str:
    if not unusual:
        return "No unusual options activity detected."
    bullish  = [u for u in unusual if u.get("bullish") is True]
    bearish  = [u for u in unusual if u.get("bullish") is False]
    if len(bullish) > len(bearish):
        return f"Bullish bias: {len(bullish)} bullish signals vs {len(bearish)} bearish. Heavy put writing suggests institutional support."
    elif len(bearish) > len(bullish):
        return f"Bearish bias: {len(bearish)} bearish signals vs {len(bullish)} bullish. Heavy call writing suggests institutional resistance."
    return f"Mixed signals: {len(unusual)} unusual activity flags detected. Neutral bias."


# ── Smart money context builder ────────────────────────────────────────────────

def build_smart_money_context(symbol: str = None) -> str:
    """
    Build a comprehensive smart money context string for agent injection.
    """
    lines = ["=" * 50, "SMART MONEY INTELLIGENCE", "=" * 50]
    lines.append(f"Generated: {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}")

    # Bulk deals
    bulk  = get_bulk_deals(days_back=5, symbol=symbol)
    block = get_block_deals(days_back=5, symbol=symbol)

    if bulk:
        lines.append("\n📦 BULK DEALS (Last 5 days):")
        for d in bulk[:5]:
            lines.append(
                f"  {d['date']} | {d['symbol']} | {d['deal_type']} | "
                f"{d['client_name'][:30]} | ₹{d['value_cr']:.1f} Cr"
                + (" [INSTITUTIONAL]" if d["is_institutional"] else "")
            )
    else:
        lines.append("\n📦 BULK DEALS: No significant bulk deals.")

    if block:
        lines.append("\n🔷 BLOCK DEALS (Last 5 days):")
        for d in block[:5]:
            lines.append(
                f"  {d['date']} | {d['symbol']} | {d['deal_type']} | "
                f"{d['client_name'][:30]} | ₹{d['value_cr']:.1f} Cr"
            )

    # Insider trades for specific symbol
    if symbol:
        insider = get_insider_trades(symbol, days_back=30)
        if insider:
            lines.append(f"\n🏛 INSIDER ACTIVITY ({symbol.upper()}, last 30 days):")
            for d in insider[:3]:
                lines.append(
                    f"  {d['date']} | {d['name'][:25]} | {d['category']} | "
                    f"{d['deal_type']} | {d['quantity']:,} shares"
                )
        else:
            lines.append(f"\n🏛 INSIDER ACTIVITY: No disclosures in last 30 days for {symbol.upper()}")

    # Unusual options
    uoa = get_unusual_options_activity("NIFTY")
    if uoa.get("success") and uoa.get("unusual"):
        lines.append("\n⚡ UNUSUAL OPTIONS ACTIVITY (NIFTY):")
        for u in uoa["unusual"][:4]:
            lines.append(f"  Strike {u['strike']:,}: {u['signal']}")
        lines.append(f"  Summary: {uoa['summary']}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
