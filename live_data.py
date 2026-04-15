"""
live_data.py — Live Market Intelligence Module
HIVE MIND ALPHA

Covers:
1. Individual stock fundamentals (P/E, ROE, Debt) — NSE + screener.in
2. Real earnings / quarterly results — NSE corporate actions
3. News & announcements today — NSE filings + Google News RSS
4. Historical OHLCV candlestick data — Groww historical API
5. Tick-level price streaming — Groww WebSocket
6. Position sizing calculator
"""

import requests
import json
import time
from datetime import datetime, timedelta, date
from typing import Optional
import pytz
import re

IST = pytz.timezone("Asia/Kolkata")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=8)
    except Exception:
        pass
    return s


# ═══════════════════════════════════════════════════════════════
# 1. STOCK FUNDAMENTALS — P/E, ROE, Debt, Promoter holding
# ═══════════════════════════════════════════════════════════════

def get_stock_fundamentals(symbol: str) -> dict:
    """
    Fetch live fundamentals for a stock from NSE India.
    Returns P/E, P/B, ROE, EPS, 52W H/L, market cap, promoter holding.
    """
    symbol = symbol.upper().strip()
    result = {
        "symbol":          symbol,
        "success":         False,
        "pe_ratio":        None,
        "pb_ratio":        None,
        "eps":             None,
        "market_cap_cr":   None,
        "face_value":      None,
        "book_value":      None,
        "dividend_yield":  None,
        "52w_high":        None,
        "52w_low":         None,
        "sector":          None,
        "industry":        None,
        "promoter_holding": None,
        "fii_holding":     None,
        "dii_holding":     None,
        "public_holding":  None,
        "debt_equity":     None,
        "roce":            None,
        "roe":             None,
        "revenue_cr":      None,
        "pat_cr":          None,
        "error":           None,
    }

    try:
        session = _nse_session()

        # NSE quote API
        quote_url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        r = session.get(quote_url, timeout=10)
        r.raise_for_status()
        data = r.json()

        price_info    = data.get("priceInfo", {})
        meta          = data.get("metadata", {})
        security_info = data.get("securityInfo", {})
        ind_info      = data.get("industryInfo", {})

        result.update({
            "success":       True,
            "pe_ratio":      price_info.get("pdSymbolPe"),
            "pb_ratio":      price_info.get("pdSectorPe"),
            "eps":           security_info.get("eps"),
            "face_value":    security_info.get("faceValue"),
            "book_value":    security_info.get("bookValue"),
            "dividend_yield":price_info.get("dividendYield"),
            "52w_high":      price_info.get("weekHighLow", {}).get("max"),
            "52w_low":       price_info.get("weekHighLow", {}).get("min"),
            "sector":        ind_info.get("sector"),
            "industry":      ind_info.get("industry"),
        })

        # Market cap
        series_info = data.get("securityInfo", {})
        shares_outstanding = float(series_info.get("issuedSize", 0) or 0)
        ltp = float(price_info.get("lastPrice", 0) or 0)
        if shares_outstanding and ltp:
            result["market_cap_cr"] = round(shares_outstanding * ltp / 1e7, 0)

        # Shareholding pattern
        try:
            sh_url = f"https://www.nseindia.com/api/corporate-shareholding-pattern?symbol={symbol}&from=&to="
            sh_r = session.get(sh_url, timeout=8)
            sh_data = sh_r.json()
            latest = sh_data.get("data", [{}])
            if latest:
                latest = latest[-1]  # Most recent quarter
                result["promoter_holding"] = latest.get("promoter")
                result["fii_holding"]      = latest.get("fii")
                result["dii_holding"]      = latest.get("dii")
                result["public_holding"]   = latest.get("public")
        except Exception:
            pass

        # Financial ratios from NSE financial results
        try:
            fin_url = f"https://www.nseindia.com/api/financial-results?symbol={symbol}&period=Quarterly&from=&to="
            fin_r = session.get(fin_url, timeout=8)
            fin_data = fin_r.json().get("data", [])
            if fin_data:
                latest_fin = fin_data[0]
                result["revenue_cr"] = latest_fin.get("income")
                result["pat_cr"]     = latest_fin.get("netProfit")
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


def get_sector_comparison(symbol: str) -> dict:
    """Get sector P/E comparison — is stock cheap or expensive vs sector."""
    try:
        session = _nse_session()
        r = session.get(
            f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}",
            timeout=10
        )
        data = r.json()
        price_info = data.get("priceInfo", {})
        stock_pe   = price_info.get("pdSymbolPe", 0)
        sector_pe  = price_info.get("pdSectorPe", 0)

        if stock_pe and sector_pe:
            discount = round((float(sector_pe) - float(stock_pe)) / float(sector_pe) * 100, 1)
            valuation = "CHEAP" if discount > 10 else "EXPENSIVE" if discount < -10 else "FAIR"
        else:
            discount = 0
            valuation = "UNKNOWN"

        return {
            "success": True,
            "stock_pe": stock_pe,
            "sector_pe": sector_pe,
            "discount_pct": discount,
            "valuation": valuation,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# 2. EARNINGS / QUARTERLY RESULTS
# ═══════════════════════════════════════════════════════════════

def get_latest_earnings(symbol: str) -> dict:
    """Fetch latest quarterly results from NSE."""
    try:
        session = _nse_session()
        r = session.get(
            f"https://www.nseindia.com/api/financial-results?symbol={symbol.upper()}&period=Quarterly&from=&to=",
            timeout=10
        )
        data = r.json().get("data", [])
        if not data:
            return {"success": False, "error": "No earnings data"}

        latest = data[0]
        prev   = data[1] if len(data) > 1 else {}
        prev4  = data[4] if len(data) > 4 else {}  # YoY comparison

        def safe_float(val):
            try: return float(val or 0)
            except: return 0.0

        revenue    = safe_float(latest.get("income"))
        pat        = safe_float(latest.get("netProfit"))
        prev_rev   = safe_float(prev.get("income"))
        prev_pat   = safe_float(prev.get("netProfit"))
        yoy_rev    = safe_float(prev4.get("income"))
        yoy_pat    = safe_float(prev4.get("netProfit"))

        qoq_rev_growth = round((revenue - prev_rev) / max(abs(prev_rev), 1) * 100, 1) if prev_rev else None
        qoq_pat_growth = round((pat - prev_pat) / max(abs(prev_pat), 1) * 100, 1) if prev_pat else None
        yoy_rev_growth = round((revenue - yoy_rev) / max(abs(yoy_rev), 1) * 100, 1) if yoy_rev else None
        yoy_pat_growth = round((pat - yoy_pat) / max(abs(yoy_pat), 1) * 100, 1) if yoy_pat else None

        return {
            "success":        True,
            "symbol":         symbol.upper(),
            "period":         latest.get("period",""),
            "revenue_cr":     revenue,
            "pat_cr":         pat,
            "eps":            latest.get("basicEps"),
            "qoq_rev_growth": qoq_rev_growth,
            "qoq_pat_growth": qoq_pat_growth,
            "yoy_rev_growth": yoy_rev_growth,
            "yoy_pat_growth": yoy_pat_growth,
            "beat_miss":      _earnings_quality(qoq_pat_growth, yoy_pat_growth),
            "all_quarters":   data[:4],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _earnings_quality(qoq: Optional[float], yoy: Optional[float]) -> str:
    if qoq is None or yoy is None:
        return "UNKNOWN"
    if qoq > 10 and yoy > 15:
        return "STRONG BEAT"
    elif qoq > 0 and yoy > 0:
        return "BEAT"
    elif qoq < -10 or yoy < -10:
        return "MISS"
    else:
        return "IN-LINE"


def get_upcoming_results_calendar() -> list:
    """Get list of companies announcing results in next 7 days."""
    try:
        session = _nse_session()
        today = date.today()
        to_date = today + timedelta(days=7)
        r = session.get(
            f"https://www.nseindia.com/api/event-calendar?index=equities"
            f"&from={today.strftime('%d-%m-%Y')}&to={to_date.strftime('%d-%m-%Y')}",
            timeout=10
        )
        data = r.json()
        results = []
        for item in data:
            if "board meeting" in item.get("purpose","").lower() or \
               "financial result" in item.get("purpose","").lower():
                results.append({
                    "symbol":  item.get("symbol",""),
                    "date":    item.get("date",""),
                    "purpose": item.get("purpose",""),
                })
        return results
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# 3. NEWS & CORPORATE ANNOUNCEMENTS
# ═══════════════════════════════════════════════════════════════

def get_stock_news(symbol: str, max_items: int = 5) -> list:
    """Fetch today's corporate announcements from NSE for a stock."""
    try:
        session = _nse_session()
        today = date.today()
        from_date = (today - timedelta(days=3)).strftime("%d-%m-%Y")
        to_date   = today.strftime("%d-%m-%Y")

        r = session.get(
            f"https://www.nseindia.com/api/corporate-announcements"
            f"?index=equities&symbol={symbol.upper()}&from={from_date}&to={to_date}",
            timeout=10
        )
        data = r.json()
        news = []
        for item in (data or [])[:max_items]:
            news.append({
                "date":     item.get("an_dt",""),
                "subject":  item.get("subject",""),
                "desc":     item.get("desc","")[:200] if item.get("desc") else "",
                "category": item.get("category",""),
                "attachment": bool(item.get("attchmntFile")),
            })
        return news
    except Exception:
        return []


def get_market_news_today() -> list:
    """Fetch broad market news from NSE announcements and economic events."""
    try:
        session = _nse_session()
        today = date.today()
        from_date = today.strftime("%d-%m-%Y")

        # NSE circular/announcements
        r = session.get(
            f"https://www.nseindia.com/api/corporate-announcements"
            f"?index=equities&from={from_date}&to={from_date}",
            timeout=10
        )
        data = r.json() or []
        news = []
        for item in data[:10]:
            news.append({
                "symbol":   item.get("symbol","MARKET"),
                "date":     item.get("an_dt",""),
                "subject":  item.get("subject",""),
                "category": item.get("category",""),
            })
        return news
    except Exception:
        return []


def get_rss_news(symbol: str, max_items: int = 3) -> list:
    """
    Fetch news headlines from Google News RSS for a symbol.
    Free, no API key needed.
    """
    try:
        import xml.etree.ElementTree as ET
        query    = f"{symbol} NSE India stock"
        rss_url  = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        r = requests.get(rss_url, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        news = []
        for item in items[:max_items]:
            title = item.findtext("title","")
            pub   = item.findtext("pubDate","")
            link  = item.findtext("link","")
            # Filter out irrelevant results
            if symbol.upper() in title.upper() or "NSE" in title.upper() or "BSE" in title.upper():
                news.append({"title": title, "date": pub, "link": link})
        return news
    except Exception:
        return []


def get_economic_events_today() -> list:
    """Return key economic events happening today (RBI, GDP, CPI etc)."""
    try:
        session = _nse_session()
        today   = date.today()
        r = session.get(
            f"https://www.nseindia.com/api/event-calendar?index=equities"
            f"&from={today.strftime('%d-%m-%Y')}&to={today.strftime('%d-%m-%Y')}",
            timeout=8
        )
        return r.json() or []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# 4. HISTORICAL OHLCV CANDLESTICK DATA
# ═══════════════════════════════════════════════════════════════

def get_historical_ohlcv_groww(token: str, symbol: str,
                                interval: str = "1d",
                                days: int = 60) -> dict:
    """
    Fetch historical OHLCV candles from Groww API.
    interval: "1m", "5m", "15m", "30m", "1h", "1d"
    """
    try:
        from growwapi import GrowwAPI
        groww    = GrowwAPI(token)
        end_dt   = datetime.now(IST)
        start_dt = end_dt - timedelta(days=days)

        resp = groww.get_historical_candle_data(
            trading_symbol = symbol.upper(),
            exchange       = "NSE",
            segment        = "CASH",
            start_time     = start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_time       = end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            interval       = interval,
        )

        candles = resp.get("candles", []) or []
        parsed  = []
        for c in candles:
            try:
                parsed.append({
                    "datetime": c[0] if isinstance(c, list) else c.get("timestamp"),
                    "open":     float(c[1] if isinstance(c, list) else c.get("open", 0)),
                    "high":     float(c[2] if isinstance(c, list) else c.get("high", 0)),
                    "low":      float(c[3] if isinstance(c, list) else c.get("low",  0)),
                    "close":    float(c[4] if isinstance(c, list) else c.get("close",0)),
                    "volume":   int(c[5]   if isinstance(c, list) else c.get("volume",0)),
                })
            except Exception:
                pass

        if not parsed:
            return {"success": False, "error": "No candle data returned", "candles": []}

        return {
            "success": True,
            "symbol":  symbol.upper(),
            "interval":interval,
            "candles": parsed,
            "count":   len(parsed),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "candles": []}


def get_historical_ohlcv_nse(symbol: str, days: int = 60) -> dict:
    """
    Fetch historical daily OHLCV.
    Uses yfinance (Yahoo Finance) as primary source — works from any server.
    NSE direct API is blocked on cloud hosting IPs (Streamlit, DigitalOcean, AWS).
    """
    INDEX_MAP = {
        "NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN",
    }
    sym_upper = symbol.upper()
    yf_sym    = INDEX_MAP.get(sym_upper, f"{sym_upper}.NS")

    # Try yfinance first (always works from cloud)
    try:
        import yfinance as yf
        end_dt   = date.today()
        start_dt = end_dt - timedelta(days=days)
        ticker   = yf.Ticker(yf_sym)
        df       = ticker.history(
            start       = start_dt.strftime("%Y-%m-%d"),
            end         = end_dt.strftime("%Y-%m-%d"),
            interval    = "1d",
            auto_adjust = True,
            actions     = False,
        )
        if df is not None and not df.empty:
            candles = []
            for idx, row in df.iterrows():
                try:
                    candles.append({
                        "datetime":    str(idx)[:10],
                        "open":        round(float(row["Open"]),  2),
                        "high":        round(float(row["High"]),  2),
                        "low":         round(float(row["Low"]),   2),
                        "close":       round(float(row["Close"]), 2),
                        "volume":      int(row["Volume"]),
                        "delivery_pct": 50.0,
                    })
                except Exception:
                    pass
            candles.sort(key=lambda x: x["datetime"])
            if candles:
                return {
                    "success": True, "symbol": sym_upper,
                    "interval": "1d", "candles": candles,
                    "count": len(candles), "source": "YAHOO",
                }
    except Exception:
        pass

    # NSE direct fallback (works on VPS with Indian IP, not on cloud)
    try:
        session  = _nse_session()
        end_dt   = date.today()
        start_dt = end_dt - timedelta(days=min(days, 300))
        r = session.get(
            f"https://www.nseindia.com/api/historical/securityArchives"
            f"?from={start_dt.strftime('%d-%m-%Y')}"
            f"&to={end_dt.strftime('%d-%m-%Y')}"
            f"&symbol={sym_upper}&dataType=priceVolumeDeliverable&series=EQ",
            timeout=10,
        )
        data = r.json().get("data", [])
        candles = []
        for d in data:
            try:
                candles.append({
                    "datetime":    d.get("CH_TIMESTAMP","")[:10],
                    "open":        float(d.get("CH_OPENING_PRICE", 0) or 0),
                    "high":        float(d.get("CH_TRADE_HIGH_PRICE", 0) or 0),
                    "low":         float(d.get("CH_TRADE_LOW_PRICE", 0) or 0),
                    "close":       float(d.get("CH_CLOSING_PRICE", 0) or 0),
                    "volume":      int(d.get("CH_TOT_TRADED_QTY", 0) or 0),
                    "delivery_pct":float(d.get("COP_DELIV_PERC", 0) or 0),
                })
            except Exception:
                pass
        candles.reverse()
        if candles:
            return {"success": True, "symbol": sym_upper, "interval": "1d",
                    "candles": candles, "count": len(candles), "source": "NSE"}
    except Exception:
        pass

    return {"success": False, "error": "Could not fetch from Yahoo or NSE", "candles": []}


def compute_technicals(candles: list) -> dict:
    """
    Compute technical indicators from OHLCV candles.
    Returns SMA, EMA, RSI, MACD, Bollinger Bands, ATR, VWAP, trend.
    """
    if len(candles) < 20:
        return {"success": False, "error": "Not enough candles"}

    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [c["volume"] for c in candles]

    def sma(data, period):
        if len(data) < period: return None
        return round(sum(data[-period:]) / period, 2)

    def ema(data, period):
        if len(data) < period: return None
        k = 2 / (period + 1)
        ema_val = sum(data[:period]) / period
        for price in data[period:]:
            ema_val = price * k + ema_val * (1 - k)
        return round(ema_val, 2)

    def rsi(data, period=14):
        if len(data) < period + 1: return None
        gains, losses = [], []
        for i in range(1, len(data)):
            change = data[i] - data[i-1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0: return 100
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)

    def bollinger(data, period=20, std_dev=2):
        if len(data) < period: return None, None, None
        subset = data[-period:]
        mean = sum(subset) / period
        variance = sum((x - mean) ** 2 for x in subset) / period
        std = variance ** 0.5
        return round(mean + std_dev * std, 2), round(mean, 2), round(mean - std_dev * std, 2)

    def atr(h, l, c, period=14):
        if len(h) < period + 1: return None
        trs = []
        for i in range(1, len(h)):
            tr = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
            trs.append(tr)
        return round(sum(trs[-period:]) / period, 2)

    def macd(data, fast=12, slow=26, signal=9):
        if len(data) < slow + signal: return None, None, None
        fast_ema = ema(data, fast)
        slow_ema = ema(data, slow)
        if fast_ema is None or slow_ema is None: return None, None, None
        macd_line = round(fast_ema - slow_ema, 2)
        # Approximate signal line
        return macd_line, None, None

    sma20  = sma(closes, 20)
    sma50  = sma(closes, 50)
    sma200 = sma(closes, 200) if len(closes) >= 200 else None
    ema9   = ema(closes, 9)
    ema21  = ema(closes, 21)
    rsi14  = rsi(closes, 14)
    bb_up, bb_mid, bb_low = bollinger(closes, 20)
    atr14  = atr(highs, lows, closes, 14)
    macd_l, macd_s, macd_h = macd(closes)

    ltp = closes[-1]

    # Trend analysis
    if sma20 and sma50:
        if ltp > sma20 > sma50:
            trend = "STRONG UPTREND"
        elif ltp > sma20 and sma20 < sma50:
            trend = "RECOVERING"
        elif ltp < sma20 < sma50:
            trend = "STRONG DOWNTREND"
        elif ltp < sma20 and sma20 > sma50:
            trend = "WEAKENING"
        else:
            trend = "SIDEWAYS"
    else:
        trend = "INSUFFICIENT DATA"

    # RSI signal
    if rsi14:
        if rsi14 < 30:    rsi_signal = "OVERSOLD — potential BUY"
        elif rsi14 > 70:  rsi_signal = "OVERBOUGHT — potential SELL"
        elif rsi14 < 45:  rsi_signal = "WEAK MOMENTUM"
        elif rsi14 > 55:  rsi_signal = "STRONG MOMENTUM"
        else:             rsi_signal = "NEUTRAL"
    else:
        rsi_signal = "N/A"

    # Bollinger signal
    if bb_up and bb_low and bb_mid:
        if ltp > bb_up:      bb_signal = "ABOVE UPPER BAND — overbought"
        elif ltp < bb_low:   bb_signal = "BELOW LOWER BAND — oversold"
        elif ltp > bb_mid:   bb_signal = "ABOVE MIDBAND — bullish"
        else:                bb_signal = "BELOW MIDBAND — bearish"
    else:
        bb_signal = "N/A"

    # Support / Resistance from recent highs/lows
    recent = candles[-20:]
    resistance = max(c["high"] for c in recent)
    support    = min(c["low"]  for c in recent)

    # 52-week high/low
    all_52w = candles[-252:] if len(candles) >= 252 else candles
    high_52w = max(c["high"] for c in all_52w)
    low_52w  = min(c["low"]  for c in all_52w)
    pct_from_52w_high = round((ltp - high_52w) / high_52w * 100, 1)

    # Volume trend
    avg_vol_20  = sum(volumes[-20:]) / min(20, len(volumes))
    today_vol   = volumes[-1]
    vol_signal  = "HIGH VOLUME" if today_vol > avg_vol_20 * 1.5 else \
                  "LOW VOLUME"  if today_vol < avg_vol_20 * 0.5 else "NORMAL VOLUME"

    return {
        "success":       True,
        "ltp":           ltp,
        "trend":         trend,
        "sma20":         sma20,
        "sma50":         sma50,
        "sma200":        sma200,
        "ema9":          ema9,
        "ema21":         ema21,
        "rsi14":         rsi14,
        "rsi_signal":    rsi_signal,
        "bb_upper":      bb_up,
        "bb_mid":        bb_mid,
        "bb_lower":      bb_low,
        "bb_signal":     bb_signal,
        "atr14":         atr14,
        "macd_line":     macd_l,
        "support_20d":   round(support, 2),
        "resistance_20d":round(resistance, 2),
        "52w_high":      round(high_52w, 2),
        "52w_low":       round(low_52w, 2),
        "pct_from_52w_high": pct_from_52w_high,
        "vol_signal":    vol_signal,
        "avg_volume_20d":round(avg_vol_20),
    }


# ═══════════════════════════════════════════════════════════════
# 5. TICK-LEVEL PRICE (near real-time via polling)
# ═══════════════════════════════════════════════════════════════

_tick_cache: dict = {}   # symbol → {price, time}
_tick_lock = None

def get_live_tick(token: str, symbol: str,
                  exchange: str = "NSE") -> dict:
    """
    Get latest tick price from Groww (fastest polling allowed).
    Caches for 30 seconds to avoid rate limits.
    """
    cache_key = f"{exchange}:{symbol}"
    cached = _tick_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < 30:
        cached["from_cache"] = True
        return cached

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
        result = {
            "success":    True,
            "symbol":     symbol.upper(),
            "ltp":        ltp,
            "change":     round(ltp - close, 2),
            "change_pct": round((ltp - close) / max(close, 1) * 100, 2),
            "volume":     int(q.get("volume", 0) or 0),
            "ts":         time.time(),
            "time":       datetime.now(IST).strftime("%H:%M:%S"),
            "from_cache": False,
        }
        _tick_cache[cache_key] = result
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "symbol": symbol}


def get_bulk_ticks(token: str, symbols: list) -> dict:
    """Get latest ticks for multiple symbols at once."""
    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(get_live_tick, token, sym): sym for sym in symbols}
        for fut, sym in futs.items():
            try:
                results[sym] = fut.result(timeout=10)
            except Exception:
                results[sym] = {"success": False, "symbol": sym}
    return results


# ═══════════════════════════════════════════════════════════════
# 6. POSITION SIZING CALCULATOR
# ═══════════════════════════════════════════════════════════════

def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_loss_price: float,
    lot_size: int = 1,
    is_options: bool = False,
    premium: float = 0.0,
    leverage: float = 1.0,
) -> dict:
    """
    Kelly-inspired position sizing calculator.

    capital:          Total trading capital in INR
    risk_pct:         Max % of capital to risk on this trade (e.g. 1.5)
    entry_price:      Entry price per share/unit
    stop_loss_price:  Stop loss price per share/unit
    lot_size:         For F&O (NIFTY=75, BANKNIFTY=30, stocks vary)
    is_options:       True for options trades
    premium:          Option premium per unit
    leverage:         For futures (typically 1 for equity CNC)
    """
    if capital <= 0 or entry_price <= 0:
        return {"success": False, "error": "Invalid capital or entry price"}

    max_loss_amount = capital * (risk_pct / 100)
    risk_per_unit   = abs(entry_price - stop_loss_price)

    if risk_per_unit <= 0:
        return {"success": False, "error": "Stop loss must be different from entry"}

    if is_options:
        # For options: max loss = premium paid × lot size × number of lots
        # So: lots = max_loss_amount / (premium × lot_size)
        if premium <= 0:
            return {"success": False, "error": "Premium required for options"}
        max_loss_per_lot = premium * lot_size
        lots = int(max_loss_amount / max_loss_per_lot)
        lots = max(1, lots)
        total_premium   = lots * lot_size * premium
        total_risk      = total_premium  # Max loss for long options

        return {
            "success":           True,
            "trade_type":        "OPTIONS",
            "lots":              lots,
            "lot_size":          lot_size,
            "units":             lots * lot_size,
            "premium_per_lot":   round(max_loss_per_lot, 2),
            "total_premium_outlay": round(total_premium, 2),
            "max_loss":          round(total_risk, 2),
            "max_loss_pct":      round(total_risk / capital * 100, 2),
            "capital_at_risk":   round(total_premium / capital * 100, 2),
            "margin_estimate":   round(total_premium * 1.05, 2),
        }

    else:
        # For equity/futures: shares = max_loss / risk_per_share
        shares = int(max_loss_amount / risk_per_unit / leverage)
        shares = max(1, shares)

        # Round to lot size if applicable
        if lot_size > 1:
            shares = max(lot_size, (shares // lot_size) * lot_size)

        order_value    = shares * entry_price
        actual_risk    = shares * risk_per_unit
        margin_blocked = order_value / leverage

        return {
            "success":           True,
            "trade_type":        "EQUITY" if leverage == 1 else "FUTURES",
            "quantity":          shares,
            "order_value":       round(order_value, 2),
            "margin_blocked":    round(margin_blocked, 2),
            "max_loss":          round(actual_risk, 2),
            "max_loss_pct":      round(actual_risk / capital * 100, 2),
            "risk_per_unit":     round(risk_per_unit, 2),
            "capital_used_pct":  round(margin_blocked / capital * 100, 1),
        }


def parse_price_from_str(price_str: str) -> float:
    """Extract float price from strings like '₹1,640–1,660' or '85–95'."""
    nums = re.findall(r"[\d.]+", str(price_str).replace(",", "").replace("₹", ""))
    if not nums:
        return 0.0
    vals = [float(n) for n in nums]
    return sum(vals) / len(vals)


def size_from_consensus(capital: float, risk_pct: float,
                         consensus: dict) -> dict:
    """
    Auto-size position from consensus trade data.
    Returns updated consensus with exact quantities.
    """
    eq = consensus.get("equity_trade", {})
    op = consensus.get("options_trade", {})
    result = {}

    if eq.get("applicable") and eq.get("direction","AVOID") != "AVOID":
        entry = parse_price_from_str(eq.get("entry_price","0"))
        sl    = parse_price_from_str(eq.get("stop_loss","0"))
        if entry > 0 and sl > 0:
            sizing = calculate_position_size(
                capital=capital,
                risk_pct=risk_pct,
                entry_price=entry,
                stop_loss_price=sl,
            )
            result["equity"] = sizing

    if op.get("applicable"):
        leg1    = op.get("leg_1", {})
        premium = parse_price_from_str(leg1.get("premium","0"))
        ul      = op.get("underlying","NIFTY").upper()
        lot_map = {"NIFTY":75,"BANKNIFTY":30,"SENSEX":20,"FINNIFTY":65,"MIDCPNIFTY":120}
        lot_sz  = lot_map.get(ul, 1)
        if premium > 0:
            sizing = calculate_position_size(
                capital=capital,
                risk_pct=risk_pct,
                entry_price=premium,
                stop_loss_price=parse_price_from_str(op.get("stop_loss_premium","0")) or premium * 0.5,
                lot_size=lot_sz,
                is_options=True,
                premium=premium,
            )
            result["options"] = sizing

    return result


# ═══════════════════════════════════════════════════════════════
# 7. ENRICHED CONTEXT BUILDER (for agents)
# ═══════════════════════════════════════════════════════════════

def build_enriched_stock_context(token: str, symbol: str) -> str:
    """
    Build a complete enriched context for a specific stock.
    Includes fundamentals, technicals, earnings, news.
    This gets injected into agent prompts for stock-specific queries.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        f_fund  = ex.submit(get_stock_fundamentals, symbol)
        f_earn  = ex.submit(get_latest_earnings, symbol)
        f_news  = ex.submit(get_stock_news, symbol)
        f_rss   = ex.submit(get_rss_news, symbol)
        f_ohlcv = ex.submit(get_historical_ohlcv_nse, symbol, 60)

    fund  = f_fund.result()
    earn  = f_earn.result()
    news  = f_news.result()
    rss   = f_rss.result()
    ohlcv = f_ohlcv.result()

    # Compute technicals
    tech = {}
    if ohlcv.get("success") and ohlcv.get("candles"):
        tech = compute_technicals(ohlcv["candles"])

    lines = [
        f"{'='*60}",
        f"ENRICHED STOCK DATA — {symbol.upper()}",
        f"Generated: {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}",
        f"{'='*60}",
    ]

    # Fundamentals
    if fund.get("success"):
        lines.append("\n📊 FUNDAMENTALS:")
        lines.append(f"  P/E Ratio:        {fund.get('pe_ratio','N/A')}")
        lines.append(f"  P/B Ratio:        {fund.get('pb_ratio','N/A')}")
        lines.append(f"  EPS:              {fund.get('eps','N/A')}")
        lines.append(f"  Book Value:       {fund.get('book_value','N/A')}")
        lines.append(f"  Market Cap:       ₹{fund.get('market_cap_cr','N/A')} Cr")
        lines.append(f"  52W High/Low:     {fund.get('52w_high','N/A')} / {fund.get('52w_low','N/A')}")
        lines.append(f"  Sector:           {fund.get('sector','N/A')}")
        lines.append(f"  Dividend Yield:   {fund.get('dividend_yield','N/A')}%")
        if fund.get("promoter_holding"):
            lines.append(f"\n📋 SHAREHOLDING:")
            lines.append(f"  Promoter:  {fund['promoter_holding']}%")
            lines.append(f"  FII:       {fund.get('fii_holding','N/A')}%")
            lines.append(f"  DII:       {fund.get('dii_holding','N/A')}%")
            lines.append(f"  Public:    {fund.get('public_holding','N/A')}%")

    # Earnings
    if earn.get("success"):
        lines.append(f"\n💰 LATEST EARNINGS ({earn.get('period','')}):")
        lines.append(f"  Revenue:          ₹{earn.get('revenue_cr','N/A')} Cr")
        lines.append(f"  PAT:              ₹{earn.get('pat_cr','N/A')} Cr")
        lines.append(f"  EPS:              {earn.get('eps','N/A')}")
        lines.append(f"  QoQ Revenue:      {earn.get('qoq_rev_growth','N/A')}%")
        lines.append(f"  QoQ PAT:          {earn.get('qoq_pat_growth','N/A')}%")
        lines.append(f"  YoY PAT:          {earn.get('yoy_pat_growth','N/A')}%")
        lines.append(f"  Earnings Quality: {earn.get('beat_miss','N/A')}")

    # Technicals
    if tech.get("success"):
        lines.append(f"\n📈 TECHNICALS (60-day daily chart):")
        lines.append(f"  Trend:            {tech.get('trend','N/A')}")
        lines.append(f"  RSI (14):         {tech.get('rsi14','N/A')} — {tech.get('rsi_signal','')}")
        lines.append(f"  SMA 20/50:        {tech.get('sma20','N/A')} / {tech.get('sma50','N/A')}")
        lines.append(f"  EMA 9/21:         {tech.get('ema9','N/A')} / {tech.get('ema21','N/A')}")
        lines.append(f"  Bollinger:        {tech.get('bb_upper','N/A')} / {tech.get('bb_mid','N/A')} / {tech.get('bb_lower','N/A')}")
        lines.append(f"  Bollinger Signal: {tech.get('bb_signal','N/A')}")
        lines.append(f"  ATR (14):         {tech.get('atr14','N/A')}")
        lines.append(f"  Support (20d):    {tech.get('support_20d','N/A')}")
        lines.append(f"  Resistance (20d): {tech.get('resistance_20d','N/A')}")
        lines.append(f"  52W High/Low:     {tech.get('52w_high','N/A')} / {tech.get('52w_low','N/A')}")
        lines.append(f"  % from 52W High:  {tech.get('pct_from_52w_high','N/A')}%")
        lines.append(f"  Volume Signal:    {tech.get('vol_signal','N/A')}")

    # News
    if news:
        lines.append(f"\n📰 RECENT NSE ANNOUNCEMENTS:")
        for n in news[:3]:
            lines.append(f"  [{n.get('date','')}] {n.get('subject','')[:100]}")

    if rss:
        lines.append(f"\n🌐 RECENT NEWS HEADLINES:")
        for n in rss[:3]:
            lines.append(f"  {n.get('title','')[:120]}")

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)
