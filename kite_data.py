"""
kite_data.py — Zerodha Kite Connect real-time market data module
Fetches live prices, options chain, OI, VIX, PCR, FII/DII data
"""

import requests
from datetime import datetime, date
import pytz

IST = pytz.timezone("Asia/Kolkata")

INDEX_SYMBOLS = {
    "NIFTY 50":      "NSE:NIFTY 50",
    "SENSEX":        "BSE:SENSEX",
    "BANKNIFTY":     "NSE:NIFTY BANK",
    "INDIA VIX":     "NSE:INDIA VIX",
    "NIFTY IT":      "NSE:NIFTY IT",
    "NIFTY AUTO":    "NSE:NIFTY AUTO",
    "NIFTY FMCG":    "NSE:NIFTY FMCG",
    "NIFTY PHARMA":  "NSE:NIFTY PHARMA",
    "NIFTY PSU BANK":"NSE:NIFTY PSU BANK",
    "NIFTY METAL":   "NSE:NIFTY METAL",
    "NIFTY REALTY":  "NSE:NIFTY REALTY",
    "NIFTY INFRA":   "NSE:NIFTY INFRA",
}

TOP_STOCKS = [
    "NSE:RELIANCE","NSE:HDFCBANK","NSE:INFY","NSE:TCS",
    "NSE:ICICIBANK","NSE:HINDUNILVR","NSE:ITC","NSE:SBIN",
    "NSE:BAJFINANCE","NSE:KOTAKBANK","NSE:LT","NSE:AXISBANK",
    "NSE:ASIANPAINT","NSE:MARUTI","NSE:TITAN","NSE:WIPRO",
    "NSE:ULTRACEMCO","NSE:NESTLEIND","NSE:POWERGRID","NSE:NTPC",
]


def get_kite_client(api_key: str, access_token: str):
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def generate_login_url(api_key: str) -> str:
    from kiteconnect import KiteConnect
    return KiteConnect(api_key=api_key).login_url()


def generate_access_token(api_key: str, api_secret: str, request_token: str) -> dict:
    from kiteconnect import KiteConnect
    try:
        kite = KiteConnect(api_key=api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)
        return {
            "success":      True,
            "access_token": data["access_token"],
            "user_name":    data.get("user_name", ""),
            "email":        data.get("email", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_live_indices(kite) -> dict:
    try:
        symbols = list(INDEX_SYMBOLS.values())
        quotes = kite.quote(symbols)
        result = {}
        for name, symbol in INDEX_SYMBOLS.items():
            q = quotes.get(symbol, {})
            prev_close = q.get("ohlc", {}).get("close", 1) or 1
            ltp = q.get("last_price", 0)
            result[name] = {
                "last_price": ltp,
                "change":     round(ltp - prev_close, 2),
                "change_pct": round((ltp - prev_close) / prev_close * 100, 2),
                "open":       q.get("ohlc", {}).get("open", 0),
                "high":       q.get("ohlc", {}).get("high", 0),
                "low":        q.get("ohlc", {}).get("low", 0),
                "close":      prev_close,
                "volume":     q.get("volume", 0),
            }
        return {"success": True, "data": result,
                "timestamp": datetime.now(IST).strftime("%H:%M:%S IST")}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


def get_stock_quote(kite, symbol: str, exchange: str = "NSE") -> dict:
    try:
        full = f"{exchange}:{symbol.upper()}"
        quotes = kite.quote([full])
        q = quotes.get(full, {})
        if not q:
            return {"success": False, "error": f"{full} not found"}
        prev_close = q.get("ohlc", {}).get("close", 1) or 1
        ltp = q.get("last_price", 0)
        depth = q.get("depth", {})
        buys  = depth.get("buy",  [{}] * 5)
        sells = depth.get("sell", [{}] * 5)
        return {
            "success":       True,
            "symbol":        symbol.upper(),
            "exchange":      exchange,
            "last_price":    ltp,
            "change":        round(ltp - prev_close, 2),
            "change_pct":    round((ltp - prev_close) / prev_close * 100, 2),
            "open":          q.get("ohlc", {}).get("open", 0),
            "high":          q.get("ohlc", {}).get("high", 0),
            "low":           q.get("ohlc", {}).get("low", 0),
            "close":         prev_close,
            "volume":        q.get("volume", 0),
            "avg_price":     q.get("average_price", 0),
            "oi":            q.get("oi", 0),
            "52w_high":      q.get("week_52_high", 0),
            "52w_low":       q.get("week_52_low", 0),
            "best_bid":      buys[0].get("price", 0)  if buys  else 0,
            "best_ask":      sells[0].get("price", 0) if sells else 0,
            "bid_qty":       buys[0].get("quantity", 0)  if buys  else 0,
            "ask_qty":       sells[0].get("quantity", 0) if sells else 0,
            "timestamp":     datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_options_chain(kite, underlying: str = "NIFTY") -> dict:
    try:
        instruments = kite.instruments("NFO")
        ul = underlying.upper()

        expiries = sorted(set(
            i["expiry"] for i in instruments
            if i["name"] == ul and i["instrument_type"] in ("CE","PE")
            and i["expiry"] >= date.today()
        ))
        if not expiries:
            return {"success": False, "error": f"No expiries found for {ul}"}

        nearest = expiries[0]
        chain_instr = [
            i for i in instruments
            if i["name"] == ul and i["instrument_type"] in ("CE","PE")
            and i["expiry"] == nearest
        ]

        spot_sym = {"NIFTY":"NSE:NIFTY 50","BANKNIFTY":"NSE:NIFTY BANK","SENSEX":"BSE:SENSEX"}.get(ul, "NSE:NIFTY 50")
        spot_price = kite.quote([spot_sym]).get(spot_sym, {}).get("last_price", 0)

        strikes = sorted(set(i["strike"] for i in chain_instr))
        atm = min(strikes, key=lambda x: abs(x - spot_price))
        atm_idx = strikes.index(atm)
        sel_strikes = strikes[max(0, atm_idx - 10): atm_idx + 11]

        syms = [f"NFO:{i['tradingsymbol']}" for i in chain_instr if i["strike"] in sel_strikes]
        quotes = {}
        for start in range(0, len(syms), 400):
            try:
                quotes.update(kite.quote(syms[start:start+400]))
            except Exception:
                pass

        chain = {}
        total_ce_oi = total_pe_oi = 0
        for strike in sel_strikes:
            chain[strike] = {"strike": strike, "CE": {}, "PE": {}}
            for i in chain_instr:
                if i["strike"] != strike:
                    continue
                sym = f"NFO:{i['tradingsymbol']}"
                q   = quotes.get(sym, {})
                oi  = q.get("oi", 0)
                opt = i["instrument_type"]
                chain[strike][opt] = {
                    "symbol": i["tradingsymbol"],
                    "ltp":    q.get("last_price", 0),
                    "oi":     oi,
                    "volume": q.get("volume", 0),
                    "iv":     q.get("implied_volatility", 0),
                    "bid":    q.get("depth", {}).get("buy",  [{}])[0].get("price", 0),
                    "ask":    q.get("depth", {}).get("sell", [{}])[0].get("price", 0),
                    "change": q.get("net_change", 0),
                }
                if opt == "CE": total_ce_oi += oi
                else:           total_pe_oi += oi

        pcr = round(total_pe_oi / max(total_ce_oi, 1), 2)

        # Max pain
        max_pain = atm
        min_pain = float("inf")
        for ts in sel_strikes:
            loss = sum(
                (ts - s) * chain[s].get("CE", {}).get("oi", 0) if ts > s else 0 +
                (s - ts) * chain[s].get("PE", {}).get("oi", 0) if ts < s else 0
                for s in sel_strikes
            )
            if loss < min_pain:
                min_pain = loss
                max_pain = ts

        ce_wall = max(sel_strikes, key=lambda s: chain[s].get("CE", {}).get("oi", 0))
        pe_wall = max(sel_strikes, key=lambda s: chain[s].get("PE", {}).get("oi", 0))
        gamma_wall = max(sel_strikes, key=lambda s:
                         chain[s].get("CE", {}).get("oi", 0) + chain[s].get("PE", {}).get("oi", 0))

        return {
            "success":       True,
            "underlying":    ul,
            "expiry":        nearest.strftime("%d %b %Y"),
            "all_expiries":  [e.strftime("%d %b %Y") for e in expiries[:3]],
            "spot_price":    spot_price,
            "atm_strike":    atm,
            "pcr":           pcr,
            "total_ce_oi":   total_ce_oi,
            "total_pe_oi":   total_pe_oi,
            "max_pain":      max_pain,
            "ce_resistance": ce_wall,
            "pe_support":    pe_wall,
            "gamma_wall":    gamma_wall,
            "chain":         {str(k): v for k, v in chain.items()},
            "sentiment":     "BULLISH" if pcr > 1.2 else "BEARISH" if pcr < 0.8 else "NEUTRAL",
            "timestamp":     datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_vix_data(kite) -> dict:
    try:
        q   = kite.quote(["NSE:INDIA VIX"]).get("NSE:INDIA VIX", {})
        vix = q.get("last_price", 0)
        prev = q.get("ohlc", {}).get("close", 1) or 1
        chg  = round(vix - prev, 2)

        if vix < 13:    regime, note, color = "COMPLACENCY",    "Extremely low — hedges recommended",         "AMBER"
        elif vix < 16:  regime, note, color = "LOW VOLATILITY", "Calm — option selling favourable",            "GREEN"
        elif vix < 20:  regime, note, color = "MODERATE",       "Normal — balanced strategies",                "GREEN"
        elif vix < 25:  regime, note, color = "ELEVATED",       "Rising fear — reduce leverage",               "AMBER"
        elif vix < 30:  regime, note, color = "HIGH FEAR",      "Significant stress — contrarian buy forming", "RED"
        else:           regime, note, color = "EXTREME FEAR",   "Panic — historically good long-term entry",   "RED"

        return {
            "success": True, "vix": vix, "change": chg,
            "change_pct": round(chg / prev * 100, 2),
            "high": q.get("ohlc", {}).get("high", 0),
            "low":  q.get("ohlc", {}).get("low", 0),
            "regime": regime, "regime_note": note, "color": color,
            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_fii_dii_data() -> dict:
    """Fetch FII/DII provisional data from NSE India (no key needed)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get("https://www.nseindia.com/api/fiidiiTradeReact",
                           headers=headers, timeout=10)
        resp.raise_for_status()
        rows = resp.json()[:5]

        result = [{
            "date":     r.get("date",""),
            "fii_buy":  r.get("fiiBuy", 0),
            "fii_sell": r.get("fiiSell", 0),
            "fii_net":  r.get("fiiNet", 0),
            "dii_buy":  r.get("diiBuy", 0),
            "dii_sell": r.get("diiSell", 0),
            "dii_net":  r.get("diiNet", 0),
        } for r in rows]

        today = result[0] if result else {}
        fii_t = today.get("fii_net", 0)
        dii_t = today.get("dii_net", 0)

        return {
            "success":       True,
            "today":         today,
            "last_5_days":   result,
            "fii_net_today": fii_t,
            "dii_net_today": dii_t,
            "fii_5d_net":    sum(r.get("fii_net", 0) for r in result),
            "dii_5d_net":    sum(r.get("dii_net", 0) for r in result),
            "fii_sentiment": "BUYING" if fii_t > 0 else "SELLING",
            "dii_sentiment": "BUYING" if dii_t > 0 else "SELLING",
            "net_flow":      fii_t + dii_t,
            "timestamp":     datetime.now(IST).strftime("%H:%M:%S IST"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_top_movers(kite, n: int = 5) -> dict:
    try:
        quotes = kite.quote(TOP_STOCKS)
        stocks = []
        for sym, q in quotes.items():
            close = q.get("ohlc", {}).get("close", 1) or 1
            ltp   = q.get("last_price", 0)
            stocks.append({
                "symbol":     sym.replace("NSE:", ""),
                "ltp":        ltp,
                "change_pct": round((ltp - close) / close * 100, 2),
                "volume":     q.get("volume", 0),
            })
        stocks.sort(key=lambda x: x["change_pct"], reverse=True)
        return {"success": True, "gainers": stocks[:n], "losers": stocks[-n:][::-1],
                "timestamp": datetime.now(IST).strftime("%H:%M:%S IST")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_market_context(indices: dict, vix: dict, options: dict,
                          fii: dict, stock_quote: dict = None) -> str:
    """Builds a rich real-time context string injected into every agent prompt."""
    lines = ["=" * 60, "LIVE MARKET DATA — REAL-TIME CONTEXT", "=" * 60]

    idx = indices.get("data", {})
    lines.append("\n📊 LIVE INDEX PRICES:")
    for name in ["NIFTY 50", "SENSEX", "BANKNIFTY", "INDIA VIX"]:
        d = idx.get(name)
        if d:
            arrow = "▲" if d["change"] >= 0 else "▼"
            lines.append(f"  {name}: {d['last_price']:,.2f}  {arrow}{abs(d['change']):.2f}"
                         f" ({abs(d['change_pct']):.2f}%)  O:{d['open']:,.0f}"
                         f"  H:{d['high']:,.0f}  L:{d['low']:,.0f}")

    lines.append("\n📈 SECTOR SNAPSHOT:")
    for sec in ["NIFTY IT","NIFTY AUTO","NIFTY FMCG","NIFTY PHARMA","NIFTY PSU BANK","NIFTY METAL"]:
        d = idx.get(sec)
        if d:
            arrow = "▲" if d["change_pct"] >= 0 else "▼"
            lines.append(f"  {sec}: {d['last_price']:,.2f}  {arrow}{abs(d['change_pct']):.2f}%")

    if vix.get("success"):
        lines.append(f"\n⚡ INDIA VIX: {vix['vix']:.2f}  ({'+' if vix['change']>=0 else ''}{vix['change']:.2f})")
        lines.append(f"   Regime: {vix['regime']} — {vix['regime_note']}")

    if options.get("success"):
        o = options
        lines.append(f"\n🔗 OPTIONS CHAIN — {o['underlying']} (Expiry: {o['expiry']}):")
        lines.append(f"   Spot: {o['spot_price']:,.2f}  |  ATM Strike: {o['atm_strike']:,}")
        lines.append(f"   PCR: {o['pcr']}  →  Sentiment: {o['sentiment']}")
        lines.append(f"   Total CE OI: {o['total_ce_oi']:,}  |  Total PE OI: {o['total_pe_oi']:,}")
        lines.append(f"   Max Pain: {o['max_pain']:,}  |  CE Resistance: {o['ce_resistance']:,}  |  PE Support: {o['pe_support']:,}")
        lines.append(f"   Gamma Wall: {o['gamma_wall']:,}")
        lines.append("\n   ATM ± 3 Strikes (CE LTP / OI  |  PE LTP / OI):")
        atm = o["atm_strike"]
        for strike in sorted(int(k) for k in o.get("chain",{}).keys()):
            if abs(strike - atm) <= 150:
                d   = o["chain"].get(str(strike), {})
                ce  = d.get("CE", {})
                pe  = d.get("PE", {})
                mk  = " ◄ ATM" if strike == atm else ""
                lines.append(f"   {strike:,}: CE={ce.get('ltp',0):.1f} OI={ce.get('oi',0):,}"
                              f"  |  PE={pe.get('ltp',0):.1f} OI={pe.get('oi',0):,}{mk}")

    if fii.get("success"):
        lines.append(f"\n💰 FII/DII FLOWS (Provisional — NSE):")
        lines.append(f"   FII Today: ₹{fii['fii_net_today']:,.2f} Cr  →  {fii['fii_sentiment']}")
        lines.append(f"   DII Today: ₹{fii['dii_net_today']:,.2f} Cr  →  {fii['dii_sentiment']}")
        lines.append(f"   FII 5-Day Net: ₹{fii['fii_5d_net']:,.2f} Cr")
        lines.append(f"   Combined Net Today: ₹{fii['net_flow']:,.2f} Cr")

    if stock_quote and stock_quote.get("success"):
        s = stock_quote
        lines.append(f"\n🏢 LIVE QUOTE — {s['symbol']} ({s['exchange']}):")
        lines.append(f"   LTP: ₹{s['last_price']:,.2f}  "
                     f"Change: {'+' if s['change']>=0 else ''}{s['change']:.2f} ({s['change_pct']:+.2f}%)")
        lines.append(f"   O:{s['open']}  H:{s['high']}  L:{s['low']}  PrevClose:{s['close']}")
        lines.append(f"   Volume: {s['volume']:,}  |  52W H:{s['52w_high']:,.2f}  L:{s['52w_low']:,.2f}")
        lines.append(f"   Bid: ₹{s['best_bid']:,.2f} ({s['bid_qty']:,})  |  Ask: ₹{s['best_ask']:,.2f} ({s['ask_qty']:,})")

    lines += ["", "=" * 60,
              f"Timestamp: {datetime.now(IST).strftime('%d %b %Y %H:%M:%S IST')}",
              "=" * 60]
    return "\n".join(lines)
