"""
groww_data.py — Live market data via Groww Trading API
Replaces kite_data.py for users with Groww API instead of Kite.
Groww API: https://groww.in/trade-api  |  ₹499/month
"""

import requests
from datetime import datetime, date
import pytz

IST = pytz.timezone("Asia/Kolkata")

# ── Groww API base ─────────────────────────────────────────────────────────────
GROWW_BASE = "https://api.groww.in/v1"

INDEX_SYMBOLS = {
    "NIFTY 50":       {"symbol": "NIFTY",     "exchange": "NSE", "segment": "INDICES"},
    "SENSEX":         {"symbol": "SENSEX",     "exchange": "BSE", "segment": "INDICES"},
    "BANKNIFTY":      {"symbol": "BANKNIFTY",  "exchange": "NSE", "segment": "INDICES"},
    "INDIA VIX":      {"symbol": "INDIA VIX",  "exchange": "NSE", "segment": "INDICES"},
    "NIFTY IT":       {"symbol": "NIFTY IT",   "exchange": "NSE", "segment": "INDICES"},
    "NIFTY AUTO":     {"symbol": "NIFTY AUTO", "exchange": "NSE", "segment": "INDICES"},
    "NIFTY FMCG":     {"symbol": "NIFTY FMCG", "exchange": "NSE", "segment": "INDICES"},
    "NIFTY PHARMA":   {"symbol": "NIFTY PHARMA","exchange": "NSE","segment": "INDICES"},
    "NIFTY PSU BANK": {"symbol": "NIFTY PSU BANK","exchange":"NSE","segment": "INDICES"},
    "NIFTY METAL":    {"symbol": "NIFTY METAL", "exchange": "NSE","segment": "INDICES"},
    "NIFTY REALTY":   {"symbol": "NIFTY REALTY","exchange": "NSE","segment": "INDICES"},
}

TOP_STOCKS = [
    "RELIANCE","HDFCBANK","INFY","TCS","ICICIBANK",
    "HINDUNILVR","ITC","SBIN","BAJFINANCE","KOTAKBANK",
    "LT","AXISBANK","ASIANPAINT","MARUTI","TITAN",
    "WIPRO","ULTRACEMCO","NESTLEIND","POWERGRID","NTPC",
]


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }


def _get(url: str, token: str, params: dict = None) -> dict:
    try:
        r = requests.get(url, headers=_headers(token), params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ── Live indices ───────────────────────────────────────────────────────────────
def get_live_indices_groww(token: str) -> dict:
    """Fetch live quotes for major indices using Groww API."""
    result = {}
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(token)

        for name, info in INDEX_SYMBOLS.items():
            try:
                q = groww.get_ltp(
                    trading_symbol=info["symbol"],
                    exchange=info["exchange"],
                    segment=info["segment"],
                )
                ltp   = float(q.get("ltp", 0))
                close = float(q.get("close", ltp) or ltp)
                change = round(ltp - close, 2)
                change_pct = round((ltp - close) / max(close, 1) * 100, 2)
                result[name] = {
                    "last_price": ltp,
                    "change":     change,
                    "change_pct": change_pct,
                    "open":       float(q.get("open", 0) or 0),
                    "high":       float(q.get("high", 0) or 0),
                    "low":        float(q.get("low",  0) or 0),
                    "close":      close,
                    "volume":     int(q.get("volume", 0) or 0),
                }
            except Exception:
                pass

        return {
            "success":   True,
            "data":      result,
            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except ImportError:
        return _fallback_indices()
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


def _fallback_indices() -> dict:
    """NSE free data fallback when SDK unavailable."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=8)
        r = session.get("https://www.nseindia.com/api/allIndices",
                        headers=headers, timeout=8)
        data = r.json().get("data", [])

        mapping = {
            "NIFTY 50": "NIFTY 50", "NIFTY BANK": "BANKNIFTY",
            "NIFTY IT": "NIFTY IT", "NIFTY AUTO": "NIFTY AUTO",
            "NIFTY FMCG": "NIFTY FMCG", "NIFTY PHARMA": "NIFTY PHARMA",
            "NIFTY PSU BANK": "NIFTY PSU BANK", "NIFTY METAL": "NIFTY METAL",
            "NIFTY REALTY": "NIFTY REALTY", "INDIA VIX": "INDIA VIX",
        }

        result = {}
        for item in data:
            key = mapping.get(item.get("indexSymbol",""))
            if key:
                ltp   = float(item.get("last", 0))
                prev  = float(item.get("previousClose", ltp) or ltp)
                result[key] = {
                    "last_price": ltp,
                    "change":     round(ltp - prev, 2),
                    "change_pct": round((ltp - prev) / max(prev,1) * 100, 2),
                    "open":  float(item.get("open", 0) or 0),
                    "high":  float(item.get("high", 0) or 0),
                    "low":   float(item.get("low",  0) or 0),
                    "close": prev,
                    "volume": 0,
                }

        # Add SENSEX from BSE
        try:
            bse = requests.get(
                "https://api.bseindia.com/BseIndiaAPI/api/GetSensexData/w",
                timeout=6
            ).json()
            sensex_ltp = float(bse.get("CurrValue","0").replace(",",""))
            sensex_prev= float(bse.get("PrevClose","0").replace(",",""))
            result["SENSEX"] = {
                "last_price": sensex_ltp,
                "change":     round(sensex_ltp - sensex_prev, 2),
                "change_pct": round((sensex_ltp-sensex_prev)/max(sensex_prev,1)*100, 2),
                "open": 0, "high": 0, "low": 0, "close": sensex_prev, "volume": 0,
            }
        except Exception:
            pass

        return {
            "success":   bool(result),
            "data":      result,
            "source":    "NSE/BSE free API",
            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


# ── Stock quote ────────────────────────────────────────────────────────────────
def get_stock_quote_groww(token: str, symbol: str, exchange: str = "NSE") -> dict:
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(token)
        q = groww.get_ltp(
            trading_symbol=symbol.upper(),
            exchange=exchange,
            segment="CASH",
        )
        ltp   = float(q.get("ltp", 0))
        close = float(q.get("close", ltp) or ltp)
        return {
            "success":    True,
            "symbol":     symbol.upper(),
            "exchange":   exchange,
            "last_price": ltp,
            "change":     round(ltp - close, 2),
            "change_pct": round((ltp-close)/max(close,1)*100, 2),
            "open":       float(q.get("open", 0) or 0),
            "high":       float(q.get("high", 0) or 0),
            "low":        float(q.get("low",  0) or 0),
            "close":      close,
            "volume":     int(q.get("volume", 0) or 0),
            "52w_high":   float(q.get("52WeekHigh", 0) or 0),
            "52w_low":    float(q.get("52WeekLow",  0) or 0),
            "best_bid":   0, "best_ask": 0, "bid_qty": 0, "ask_qty": 0,
            "timestamp":  datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── VIX ────────────────────────────────────────────────────────────────────────
def get_vix_data_groww(token: str) -> dict:
    """Get India VIX — tries Groww API, falls back to NSE scrape."""
    vix = 0
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(token)
        q = groww.get_ltp(trading_symbol="INDIA VIX", exchange="NSE", segment="INDICES")
        vix = float(q.get("ltp", 0))
    except Exception:
        pass

    if not vix:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.nseindia.com/",
            }
            session = requests.Session()
            session.get("https://www.nseindia.com", headers=headers, timeout=8)
            r = session.get(
                "https://www.nseindia.com/api/allIndices",
                headers=headers, timeout=8,
            )
            for item in r.json().get("data", []):
                if item.get("indexSymbol") == "INDIA VIX":
                    vix = float(item.get("last", 0))
                    break
        except Exception:
            pass

    if not vix:
        return {"success": False, "error": "Could not fetch VIX"}

    prev  = vix  # fallback
    chg   = 0.0

    if   vix < 13:  regime, note, color = "COMPLACENCY",    "Extremely low — consider hedges",      "AMBER"
    elif vix < 16:  regime, note, color = "LOW VOLATILITY", "Calm — option selling favourable",      "GREEN"
    elif vix < 20:  regime, note, color = "MODERATE",       "Normal — balanced strategies",          "GREEN"
    elif vix < 25:  regime, note, color = "ELEVATED",       "Rising fear — reduce leverage",         "AMBER"
    elif vix < 30:  regime, note, color = "HIGH FEAR",      "Stress — contrarian buy forming",       "RED"
    else:           regime, note, color = "EXTREME FEAR",   "Panic — historically good LT entry",    "RED"

    return {
        "success": True, "vix": vix, "change": chg, "change_pct": 0.0,
        "high": vix, "low": vix,
        "regime": regime, "regime_note": note, "color": color,
        "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
    }


# ── Options chain via NSE (free) ───────────────────────────────────────────────
def get_options_chain_groww(token: str, underlying: str = "NIFTY") -> dict:
    """Fetch options chain from NSE (free, no broker API needed)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=8)

        ul_map = {"NIFTY": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
        ul = ul_map.get(underlying.upper(), "NIFTY")

        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={ul}"
        r = session.get(url, headers=headers, timeout=10)
        data = r.json()

        records   = data.get("records", {})
        spot      = float(records.get("underlyingValue", 0))
        expiries  = records.get("expiryDates", [])
        exp       = expiries[0] if expiries else ""
        chain_raw = records.get("data", [])

        chain          = {}
        total_ce_oi    = 0
        total_pe_oi    = 0

        for item in chain_raw:
            if item.get("expiryDate") != exp:
                continue
            strike = item.get("strikePrice", 0)
            if strike not in chain:
                chain[strike] = {"strike": strike, "CE": {}, "PE": {}}
            for opt in ("CE", "PE"):
                d = item.get(opt, {})
                if d:
                    oi = int(d.get("openInterest", 0) or 0)
                    chain[strike][opt] = {
                        "ltp":    float(d.get("lastPrice", 0) or 0),
                        "oi":     oi,
                        "volume": int(d.get("totalTradedVolume", 0) or 0),
                        "iv":     float(d.get("impliedVolatility", 0) or 0),
                        "change": float(d.get("change", 0) or 0),
                        "bid":    0, "ask": 0,
                    }
                    if opt == "CE":  total_ce_oi += oi
                    else:            total_pe_oi += oi

        if not chain:
            return {"success": False, "error": "Empty chain"}

        pcr       = round(total_pe_oi / max(total_ce_oi, 1), 2)
        strikes   = sorted(chain.keys())
        atm       = min(strikes, key=lambda x: abs(x - spot))

        ce_wall   = max(strikes, key=lambda s: chain[s].get("CE",{}).get("oi",0))
        pe_wall   = max(strikes, key=lambda s: chain[s].get("PE",{}).get("oi",0))
        gamma_wall= max(strikes, key=lambda s:
                        chain[s].get("CE",{}).get("oi",0)+chain[s].get("PE",{}).get("oi",0))

        # Max pain
        max_pain = atm
        min_pain = float("inf")
        for ts in strikes:
            loss = sum(
                max(0,(ts-s))*chain[s].get("CE",{}).get("oi",0) +
                max(0,(s-ts))*chain[s].get("PE",{}).get("oi",0)
                for s in strikes
            )
            if loss < min_pain:
                min_pain = loss; max_pain = ts

        return {
            "success":       True,
            "underlying":    ul,
            "expiry":        exp,
            "all_expiries":  expiries[:3],
            "spot_price":    spot,
            "atm_strike":    atm,
            "pcr":           pcr,
            "total_ce_oi":   total_ce_oi,
            "total_pe_oi":   total_pe_oi,
            "max_pain":      max_pain,
            "ce_resistance": ce_wall,
            "pe_support":    pe_wall,
            "gamma_wall":    gamma_wall,
            "chain":         {str(k): v for k,v in chain.items()},
            "sentiment":     "BULLISH" if pcr>1.2 else "BEARISH" if pcr<0.8 else "NEUTRAL",
            "source":        "NSE",
            "timestamp":     datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── FII/DII from NSE (free) ────────────────────────────────────────────────────
def get_fii_dii_data() -> dict:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=8)
        r = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=headers, timeout=8,
        )
        rows = r.json()[:5]
        result = [{
            "date":     row.get("date",""),
            "fii_net":  row.get("fiiNet", 0),
            "dii_net":  row.get("diiNet", 0),
            "fii_buy":  row.get("fiiBuy", 0),
            "fii_sell": row.get("fiiSell", 0),
            "dii_buy":  row.get("diiBuy", 0),
            "dii_sell": row.get("diiSell", 0),
        } for row in rows]

        today = result[0] if result else {}
        fii_t = today.get("fii_net", 0)
        dii_t = today.get("dii_net", 0)
        return {
            "success":       True,
            "today":         today,
            "last_5_days":   result,
            "fii_net_today": fii_t,
            "dii_net_today": dii_t,
            "fii_5d_net":    sum(r.get("fii_net",0) for r in result),
            "dii_5d_net":    sum(r.get("dii_net",0) for r in result),
            "fii_sentiment": "BUYING" if fii_t>0 else "SELLING",
            "dii_sentiment": "BUYING" if dii_t>0 else "SELLING",
            "net_flow":      fii_t + dii_t,
            "timestamp":     datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Top movers from NSE (free) ─────────────────────────────────────────────────
def get_top_movers_nse(n: int = 5) -> dict:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=8)

        gainers_r = session.get(
            "https://www.nseindia.com/api/live-analysis-variations?index=gainers",
            headers=headers, timeout=8,
        ).json()
        losers_r = session.get(
            "https://www.nseindia.com/api/live-analysis-variations?index=losers",
            headers=headers, timeout=8,
        ).json()

        def parse(items):
            return [{"symbol": i.get("symbol",""), "ltp": float(i.get("ltp",0) or 0),
                     "change_pct": float(i.get("perChange",0) or 0)} for i in items[:n]]

        return {
            "success": True,
            "gainers": parse(gainers_r.get("NIFTY",{}).get("data",[])),
            "losers":  parse(losers_r.get("NIFTY",{}).get("data",[])),
            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Master context builder ─────────────────────────────────────────────────────
def build_market_context_groww(token: str) -> str:
    """
    Fetch all live data using Groww API + free NSE feeds,
    and build the context string injected into every agent prompt.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        f_idx  = ex.submit(get_live_indices_groww,   token)
        f_vix  = ex.submit(get_vix_data_groww,       token)
        f_opts = ex.submit(get_options_chain_groww,  token, "NIFTY")
        f_bnk  = ex.submit(get_options_chain_groww,  token, "BANKNIFTY")
        f_fii  = ex.submit(get_fii_dii_data)
        indices  = f_idx.result()
        vix      = f_vix.result()
        opts     = f_opts.result()
        bnk_opts = f_bnk.result()
        fii      = f_fii.result()

    lines = ["=" * 60, "LIVE MARKET DATA — REAL-TIME CONTEXT", "=" * 60]
    lines.append(f"Source: Groww API + NSE Free Feed")
    lines.append(f"Timestamp: {datetime.now(IST).strftime('%d %b %Y %H:%M:%S IST')}")

    idx = indices.get("data", {})
    lines.append("\n📊 LIVE INDEX PRICES:")
    for name in ["NIFTY 50", "SENSEX", "BANKNIFTY", "INDIA VIX"]:
        d = idx.get(name)
        if d:
            arrow = "▲" if d["change"] >= 0 else "▼"
            lines.append(
                f"  {name}: {d['last_price']:,.2f}  {arrow}{abs(d['change']):.2f}"
                f" ({abs(d['change_pct']):.2f}%)  "
                f"O:{d['open']:,.0f} H:{d['high']:,.0f} L:{d['low']:,.0f}"
            )

    lines.append("\n📈 SECTOR SNAPSHOT:")
    for sec in ["NIFTY IT","NIFTY AUTO","NIFTY FMCG","NIFTY PHARMA","NIFTY PSU BANK","NIFTY METAL"]:
        d = idx.get(sec)
        if d:
            arrow = "▲" if d["change_pct"] >= 0 else "▼"
            lines.append(f"  {sec}: {d['last_price']:,.2f}  {arrow}{abs(d['change_pct']):.2f}%")

    if vix.get("success"):
        lines.append(f"\n⚡ INDIA VIX: {vix['vix']:.2f}")
        lines.append(f"   Regime: {vix['regime']} — {vix['regime_note']}")

    for label, oc in [("NIFTY", opts), ("BANKNIFTY", bnk_opts)]:
        if oc.get("success"):
            lines.append(f"\n🔗 {label} OPTIONS CHAIN (Expiry: {oc['expiry']}):")
            lines.append(f"   Spot: {oc['spot_price']:,.2f}  ATM: {oc['atm_strike']:,}")
            lines.append(f"   PCR: {oc['pcr']}  Sentiment: {oc['sentiment']}")
            lines.append(f"   CE OI: {oc['total_ce_oi']:,}  PE OI: {oc['total_pe_oi']:,}")
            lines.append(f"   Max Pain: {oc['max_pain']:,}  CE Wall: {oc['ce_resistance']:,}  PE Wall: {oc['pe_support']:,}")

    if fii.get("success"):
        lines.append(f"\n💰 FII/DII FLOWS:")
        lines.append(f"   FII Today: ₹{fii['fii_net_today']:,.2f} Cr  {fii['fii_sentiment']}")
        lines.append(f"   DII Today: ₹{fii['dii_net_today']:,.2f} Cr  {fii['dii_sentiment']}")
        lines.append(f"   FII 5D Net: ₹{fii['fii_5d_net']:,.2f} Cr")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
