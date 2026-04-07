"""
scanner.py — Autonomous Market Scanner  (Quant-First Architecture)
HIVE MIND ALPHA

NEW ARCHITECTURE (replaces LLM-agent scanning):

  Step 1 — Fetch live OHLCV + options + FII + VIX for each instrument
  Step 2 — quant_core.run_full_signal_analysis() computes all signals
            deterministically (no LLM involved)
  Step 3 — Filter: P(Win) >= threshold AND n_independent_groups >= 2
  Step 4 — Claude NLP filter reads today's NSE announcements + news
            and outputs CONFIRM / CAUTIOUS / SUPPRESS
  Step 5 — Fire to Telegram if CONFIRM or CAUTIOUS

Claude is now a text filter, not a signal generator.
Signals come from mathematics. Claude reads unstructured text.
"""

import threading
import time
import json
import uuid
import concurrent.futures
from datetime import datetime
import pytz
import streamlit as st
from market_data_store import (collect_daily_snapshot, upsert_daily_ohlcv,
                                get_daily_ohlcv, get_pcr_history,
                                get_vix_history, get_fii_history,
                                get_calibrated_rates, log_signal_fired)
from paper_trade import record_paper_trade

IST = pytz.timezone("Asia/Kolkata")

SCAN_INTERVAL_MINUTES = 15
SIGNAL_COOLDOWN_HOURS = 2
MARKET_OPEN  = (9, 15)
MARKET_CLOSE = (15, 30)

# Instruments to scan every cycle
SCAN_UNIVERSE = {
    "indices": ["NIFTY", "BANKNIFTY"],
    "stocks": [
        "RELIANCE", "HDFCBANK", "INFY", "TCS", "ICICIBANK",
        "SBIN", "BAJFINANCE", "KOTAKBANK", "LT", "AXISBANK",
        "WIPRO", "MARUTI", "TITAN", "ASIANPAINT", "SUNPHARMA",
        "HCLTECH", "NTPC", "POWERGRID", "DIVISLAB", "ULTRACEMCO",
    ],
}

# Minimum thresholds to fire a signal
MIN_PROBABILITY    = 0.60    # P(Win) must exceed this
MIN_GROUPS         = 2       # Must have signals from 2+ independent groups
MIN_FIRED_SIGNALS  = 2       # Must have at least 2 signals fired


# ── NLP filter — Claude reads news/announcements ───────────────────────────────

NLP_FILTER_PROMPT = """You are a financial news analyst. A quantitative signal has fired on {symbol}.

The mathematical signal says: {direction} with P(Win)={prob:.0%}
Signals triggered: {signals}

Your job: read the recent news and announcements below and decide whether
to CONFIRM, flag as CAUTIOUS, or SUPPRESS this signal.

CONFIRM  — News is neutral or supportive. No red flags. Signal can proceed.
CAUTIOUS — Mixed news. Signal can proceed but include a specific warning.
SUPPRESS — Active negative catalyst (earnings miss, SEBI action, promoter
           selling, major litigation, RBI action on the sector). Block signal.

RECENT NEWS AND ANNOUNCEMENTS:
{news_text}

Respond ONLY in this exact JSON format:
{{
  "verdict": "CONFIRM" | "CAUTIOUS" | "SUPPRESS",
  "reason": "<one sentence explaining your verdict>",
  "risk_flag": "<specific risk if CAUTIOUS/SUPPRESS, else null>"
}}"""


def claude_nlp_filter(symbol: str, direction: str, probability: float,
                       signals_fired: list, api_key: str) -> dict:
    """
    Run Claude NLP filter on recent news for this instrument.
    Returns {verdict, reason, risk_flag}.
    """
    import anthropic
    from live_data import get_stock_news, get_rss_news

    # Fetch recent news — no LLM needed for this step
    nse_news = get_stock_news(symbol, max_items=4)
    rss_news = get_rss_news(symbol, max_items=3)

    news_lines = []
    for n in nse_news:
        news_lines.append(f"[NSE {n.get('date','')}] {n.get('subject','')} — {n.get('desc','')[:150]}")
    for n in rss_news:
        news_lines.append(f"[NEWS] {n.get('title','')}")

    if not news_lines:
        # No news available — default CONFIRM
        return {"verdict": "CONFIRM", "reason": "No news found. Proceeding on signal strength.",
                "risk_flag": None}

    news_text = "\n".join(news_lines[:7])
    signal_names = [s.get("signal", "") for s in signals_fired[:5]]

    prompt = NLP_FILTER_PROMPT.format(
        symbol    = symbol,
        direction = direction,
        prob      = probability,
        signals   = ", ".join(signal_names),
        news_text = news_text,
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp   = client.messages.create(
            model     = "claude-sonnet-4-20250514",
            max_tokens= 200,
            messages  = [{"role": "user", "content": prompt}],
        )
        raw  = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        # Validate
        if data.get("verdict") not in ("CONFIRM","CAUTIOUS","SUPPRESS"):
            data["verdict"] = "CONFIRM"
        return data
    except Exception as e:
        return {"verdict": "CONFIRM",
                "reason": f"NLP filter unavailable ({str(e)[:60]}). Proceeding.",
                "risk_flag": None}


# ── Data fetcher for one instrument ───────────────────────────────────────────

def fetch_instrument_data(symbol: str, groww_token: str,
                           is_index: bool = False) -> dict:
    """
    Fetch all data needed by quant_core for one instrument.
    Returns dict ready to pass to run_full_signal_analysis().
    """
    from live_data import get_historical_ohlcv_nse, get_historical_ohlcv_groww
    from groww_data import (get_options_chain_groww, get_fii_dii_data,
                             get_vix_data_groww)

    result = {"symbol": symbol, "success": False}

    # OHLCV — use SQLite DB first (most complete), then Groww/NSE
    ohlcv = get_daily_ohlcv(symbol, days=500)

    if len(ohlcv) < 30:
        # DB empty or insufficient — fetch from API and store
        from live_data import get_historical_ohlcv_nse, get_historical_ohlcv_groww
        ohlcv_data = {}
        if groww_token and not is_index:
            ohlcv_data = get_historical_ohlcv_groww(groww_token, symbol, "1d", 500)
        if not ohlcv_data.get("candles"):
            ohlcv_data = get_historical_ohlcv_nse(symbol, 500)
        if ohlcv_data.get("candles"):
            upsert_daily_ohlcv(symbol, ohlcv_data["candles"])
            ohlcv = ohlcv_data["candles"]

    if len(ohlcv) < 30:
        result["error"] = f"Insufficient OHLCV data for {symbol}"
        return result

    # Convert DB format to expected format
    for c in ohlcv:
        if "datetime" not in c and "date" in c:
            c["datetime"] = c["date"]

    # Options chain (NIFTY or BANKNIFTY for indices, else skip)
    opts = {}
    underlying = symbol if symbol in ("NIFTY","BANKNIFTY","SENSEX") else "NIFTY"
    try:
        opts_raw = get_options_chain_groww(groww_token, underlying)
        if opts_raw.get("success"):
            # Calculate days to expiry
            expiry_str = opts_raw.get("expiry", "")
            try:
                from datetime import datetime as dt2
                exp_dt = dt2.strptime(expiry_str, "%d-%b-%Y")
                dte = max((exp_dt.date() - datetime.now(IST).date()).days, 0)
            except Exception:
                dte = 3  # default to mid-week

            # Get previous OI from session state or default
            prev_ce = float(opts_raw.get("total_ce_oi", 0)) * 0.98
            prev_pe = float(opts_raw.get("total_pe_oi", 0)) * 0.98

            opts = {
                "pcr":           opts_raw.get("pcr", 1.0),
                "max_pain":      opts_raw.get("max_pain", 0),
                "ce_resistance": opts_raw.get("ce_resistance", 0),
                "pe_support":    opts_raw.get("pe_support", 0),
                "gamma_wall":    opts_raw.get("gamma_wall", 0),
                "spot_price":    opts_raw.get("spot_price", ohlcv[-1]["close"]),
                "total_ce_oi":   opts_raw.get("total_ce_oi", 0),
                "total_pe_oi":   opts_raw.get("total_pe_oi", 0),
                "prev_ce_oi":    prev_ce,
                "prev_pe_oi":    prev_pe,
                "days_to_expiry":dte,
            }
    except Exception:
        opts = {
            "pcr": 1.0, "max_pain": 0, "ce_resistance": 0, "pe_support": 0,
            "gamma_wall": 0, "spot_price": ohlcv[-1]["close"],
            "total_ce_oi": 0, "total_pe_oi": 0,
            "prev_ce_oi": 0, "prev_pe_oi": 0, "days_to_expiry": 5,
        }

    # FII history from SQLite DB (real data)
    fii_hist = get_fii_history(days=30)
    if len(fii_hist) < 5:
        try:
            from groww_data import get_fii_dii_data
            fii_raw = get_fii_dii_data()
            if fii_raw.get("success"):
                fii_hist = [d.get("fii_net",0) for d in fii_raw.get("last_5_days",[])]
        except Exception:
            fii_hist = [0.0] * 5
    if len(fii_hist) < 5:
        fii_hist = [0.0] * 5

    # VIX history from SQLite DB (real data)
    vix_hist = get_vix_history(days=60)
    if len(vix_hist) < 5:
        try:
            from groww_data import get_vix_data_groww
            vix_raw = get_vix_data_groww(groww_token)
            vix_now = vix_raw.get("vix", 16.0) if vix_raw.get("success") else 16.0
        except Exception:
            vix_now = 16.0
        vix_hist = [vix_now] * 5

    # PCR/VIX/FII history from SQLite DB (real data)
    pcr_hist = get_pcr_history("NIFTY", days=60)
    if len(pcr_hist) < 5:
        # Fall back to synthetic if DB is empty (first run)
        pcr_now  = opts.get("pcr", 1.0)
        pcr_hist = [pcr_now * 0.95, pcr_now * 0.98, pcr_now, pcr_now * 1.02, pcr_now]

    result.update({
        "success":  True,
        "ohlcv":    ohlcv,
        "options":  opts,
        "fii_hist": fii_hist,
        "vix_hist": vix_hist,
        "pcr_hist": pcr_hist,
        "spot":     opts.get("spot_price", ohlcv[-1]["close"]),
    })
    return result


# ── Single instrument scan ─────────────────────────────────────────────────────

def scan_instrument(symbol: str, groww_token: str, api_key: str,
                     capital: float, regime: str) -> dict:
    """
    Run full quant analysis on one instrument.
    Returns signal dict or no-signal dict.
    """
    from quant_core import run_full_signal_analysis

    # Fetch data
    data = fetch_instrument_data(symbol, groww_token,
                                  is_index=symbol in ("NIFTY","BANKNIFTY","SENSEX"))
    if not data.get("success"):
        return {"fired": False, "symbol": symbol,
                "reason": data.get("error", "Data fetch failed")}

    # Run quant analysis
    analysis = run_full_signal_analysis(
        ohlcv    = data["ohlcv"],
        options_data = data["options"],
        fii_history  = data["fii_hist"],
        vix_history  = data["vix_hist"],
        pcr_history  = data["pcr_hist"],
        capital      = capital,
        regime       = regime,
    )

    p_win        = analysis.get("probability", 0)
    n_groups     = analysis.get("combination", {}).get("n_groups", 0)
    n_fired      = analysis.get("fired_count", 0)
    direction    = analysis.get("direction", "NEUTRAL")
    recommendation = analysis.get("recommendation", "AVOID")

    # Threshold check
    if (p_win < MIN_PROBABILITY or
            n_groups < MIN_GROUPS or
            n_fired < MIN_FIRED_SIGNALS or
            direction == "NEUTRAL" or
            recommendation == "AVOID"):
        return {
            "fired":     False,
            "symbol":    symbol,
            "reason":    (f"Below threshold: P={p_win:.1%} groups={n_groups} "
                          f"signals={n_fired} rec={recommendation}"),
            "analysis":  analysis,
        }

    return {
        "fired":      True,
        "symbol":     symbol,
        "direction":  direction,
        "probability":p_win,
        "n_groups":   n_groups,
        "n_fired":    n_fired,
        "recommendation": recommendation,
        "analysis":   analysis,
        "spot":       data["spot"],
        "entry":      analysis.get("entry"),
        "stop_loss":  analysis.get("stop_loss"),
        "target_1":   analysis.get("target_1"),
        "target_2":   analysis.get("target_2"),
        "atr":        analysis.get("atr"),
        "sizing":     analysis.get("sizing", {}),
        "indicators": analysis.get("indicators", {}),
        "fired_signals": analysis.get("fired_signals", []),
    }


# ── Signal deduplication ───────────────────────────────────────────────────────

_recent_signals: dict = {}

def is_duplicate(symbol: str) -> bool:
    ts = _recent_signals.get(symbol)
    if not ts:
        return False
    return (datetime.now(IST) - ts).total_seconds() / 3600 < SIGNAL_COOLDOWN_HOURS

def mark_sent(symbol: str):
    _recent_signals[symbol] = datetime.now(IST)


# ── Telegram message formatting ────────────────────────────────────────────────

def format_quant_signal(result: dict, nlp: dict, trade_id: str) -> str:
    """Format the Telegram message showing computed signal details."""
    now       = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    symbol    = result["symbol"]
    direction = result["direction"]
    prob      = result["probability"]
    rec       = result["recommendation"]
    entry     = result["entry"]
    sl        = result["stop_loss"]
    t1        = result["target_1"]
    t2        = result["target_2"]
    atr       = result["atr"]
    sizing    = result["sizing"]
    ind       = result["indicators"]
    fired     = result["fired_signals"]
    n_groups  = result["n_groups"]
    verdict   = nlp.get("verdict", "CONFIRM")
    nlp_reason = nlp.get("reason", "")
    risk_flag  = nlp.get("risk_flag", "")

    de = "🟢" if direction == "LONG" else "🔴"
    ve = "✅" if verdict == "CONFIRM" else "⚡" if verdict == "CAUTIOUS" else "⚠️"

    # Signal list with groups
    sig_lines = []
    for s in fired[:6]:
        sig_lines.append(f"  • {s['signal']} ({s.get('direction','?')}) "
                          f"str={s.get('strength',0):.2f}")
    sig_text = "\n".join(sig_lines) if sig_lines else "  • (see app for details)"

    # Indicator snapshot
    ind_parts = []
    if ind.get("rsi"):    ind_parts.append(f"RSI={ind['rsi']:.0f}")
    if ind.get("adx"):    ind_parts.append(f"ADX={ind['adx']:.0f}")
    if ind.get("macd"):   ind_parts.append(f"MACD={ind['macd']:.2f}")
    if ind.get("hurst_H"):ind_parts.append(f"H={ind['hurst_H']:.3f}")
    ind_str = "  ".join(ind_parts)

    qty   = sizing.get("quantity", "—")
    val   = sizing.get("order_value", 0)
    kelly = sizing.get("kelly", {})
    frac  = kelly.get("fraction_pct", "—")

    text = (
        f"📐 <b>QUANT SIGNAL — HIVE MIND ALPHA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n"
        f"📋 Trade ID: <code>{trade_id}</code>\n\n"
        f"{de} <b>{direction} {symbol}</b>\n"
        f"📊 P(Win) = <b>{prob:.1%}</b>  |  {n_groups} independent signal groups\n"
        f"⭐ Recommendation: <b>{rec}</b>\n\n"
        f"━━━━━━━━ COMPUTED LEVELS ━━━━━━━━\n"
        f"📥 Entry:      ₹{entry:,.2f}\n"
        f"🛑 Stop Loss:  ₹{sl:,.2f}  (1.5× ATR = {atr:.2f})\n"
        f"🎯 Target 1:   ₹{t1:,.2f}  (3.0× ATR)\n"
        f"🎯 Target 2:   ₹{t2:,.2f}  (4.5× ATR)\n"
        f"⚖️ R:R = 1:{round(abs(t1-entry)/max(abs(entry-sl),0.01),1)}\n\n"
        f"💼 Kelly Sizing: {qty} shares  "
        f"₹{val:,.0f}  ({frac}% of capital)\n\n"
        f"━━━━━━━━ FIRED SIGNALS ━━━━━━━━\n"
        f"{sig_text}\n\n"
        f"📈 Indicators: {ind_str}\n\n"
        f"━━━━━━━━ NLP FILTER ━━━━━━━━\n"
        f"{ve} <b>{verdict}</b>: {nlp_reason}\n"
    )
    if risk_flag:
        text += f"⚠️ Risk: {risk_flag}\n"

    text += (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Computed signal. Educational only. Not SEBI advice.</i>"
    )
    return text


# ── Main scan cycle ────────────────────────────────────────────────────────────

def run_scan_cycle(api_key: str, telegram_token: str, telegram_chat_id: str,
                   groww_token: str, market_context: str,
                   capital: float = 500000) -> dict:
    """
    Full scan cycle on all instruments in universe.
    Uses quant_core for signal computation.
    Uses Claude only for NLP news filtering.
    """
    from telegram_bot import send_telegram_message, build_approval_keyboard
    from trade_log import log_signal
    from regime import detect_regime
    from groww_data import get_live_indices_groww, get_vix_data_groww, get_fii_dii_data

    # Collect and store today's PCR, VIX, FII to database (Action 3)
    try:
        collect_daily_snapshot(groww_token)
    except Exception:
        pass

    # Load calibrated win rates and update SignalCombiner (Action 1)
    try:
        from quant_core import SignalCombiner
        cal_rates = get_calibrated_rates()
        for sig_name, regime_stats in cal_rates.items():
            all_stats = regime_stats.get("ALL")
            if all_stats and all_stats.get("n_observations", 0) >= 20:
                SignalCombiner.WIN_RATES[sig_name] = float(all_stats["win_rate"])
    except Exception:
        pass

    # Detect current regime
    regime = "UNKNOWN"
    try:
        fi = get_live_indices_groww(groww_token)
        fv = get_vix_data_groww(groww_token)
        ff = get_fii_dii_data()
        regime_result = detect_regime(fi, fv, ff)
        if regime_result.get("success"):
            regime = regime_result.get("regime", "UNKNOWN")
    except Exception:
        pass

    # Build full instrument list
    instruments = (
        [(s, False) for s in SCAN_UNIVERSE["stocks"]] +
        [(s, True)  for s in SCAN_UNIVERSE["indices"]]
    )

    # Scan all instruments in parallel (max 6 workers to avoid rate limits)
    scan_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {
            ex.submit(scan_instrument, sym, groww_token, api_key,
                       capital, regime): sym
            for sym, _ in instruments
        }
        for fut, sym in futs.items():
            try:
                scan_results[sym] = fut.result(timeout=45)
            except Exception as e:
                scan_results[sym] = {"fired": False, "symbol": sym,
                                      "reason": str(e)}

    # Collect fired signals
    fired_instruments = {
        sym: r for sym, r in scan_results.items() if r.get("fired")
    }

    if not fired_instruments:
        reasons = {sym: r.get("reason","") for sym, r in scan_results.items()
                   if not r.get("fired")}
        # Summarise top reasons
        return {
            "fired":      False,
            "reason":     f"No instruments cleared threshold. Checked {len(instruments)}.",
            "scan_count": len(instruments),
            "top_reasons":dict(list(reasons.items())[:5]),
            "regime":     regime,
            "timestamp":  datetime.now(IST).isoformat(),
        }

    # For each fired instrument, run NLP filter
    signals_sent = []
    for sym, result in fired_instruments.items():
        if is_duplicate(sym):
            continue

        # NLP filter (Claude reads news — this is the ONLY Claude call)
        nlp = claude_nlp_filter(
            symbol     = sym,
            direction  = result["direction"],
            probability= result["probability"],
            signals_fired = result.get("fired_signals", []),
            api_key    = api_key,
        )

        # SUPPRESS = skip entirely
        if nlp.get("verdict") == "SUPPRESS":
            continue

        # Build trade
        trade_id = str(uuid.uuid4())[:8].upper()
        text     = format_quant_signal(result, nlp, trade_id)
        keyboard = build_approval_keyboard(trade_id)

        tg_resp  = send_telegram_message(telegram_token, telegram_chat_id,
                                          text, keyboard)
        if not tg_resp.get("ok"):
            continue

        mark_sent(sym)

        # Build consensus dict for approval flow
        entry = result.get("entry", 0)
        sl    = result.get("stop_loss", 0)
        t1    = result.get("target_1", 0)
        t2    = result.get("target_2", 0)
        qty   = result.get("sizing", {}).get("quantity", 1)

        consensus = {
            "overall_stance":      result["direction"],
            "conviction":          result["recommendation"],
            "time_horizon":        "SWING",
            "agent_agreement_pct": round(result["probability"] * 100),
            "key_thesis": (f"P(Win)={result['probability']:.1%}. "
                           f"Signals: {[s['signal'] for s in result.get('fired_signals',[])[:3]]}. "
                           f"NLP: {nlp.get('verdict')} — {nlp.get('reason','')}"),
            "equity_trade": {
                "applicable":    True,
                "instrument":    sym,
                "direction":     result["direction"],
                "entry_price":   f"₹{entry:,.2f}",
                "stop_loss":     f"₹{sl:,.2f}",
                "target_1":      f"₹{t1:,.2f}",
                "target_2":      f"₹{t2:,.2f}",
                "holding_period":"SWING (2-5 days)",
                "quantity":      qty,
                "position_size": (f"{qty} shares (₹{result.get('sizing',{}).get('order_value',0):,.0f} "
                                   f"| Kelly={result.get('sizing',{}).get('kelly',{}).get('fraction_pct',0):.1f}%)"),
            },
            "options_trade": {"applicable": False},
        }

        if "pending_scanner_trades" not in st.session_state:
            st.session_state["pending_scanner_trades"] = {}
        st.session_state["pending_scanner_trades"][trade_id] = {
            "consensus":   consensus,
            "groww_token": groww_token,
            "timestamp":   datetime.now(IST).isoformat(),
            "instrument":  sym,
            "result":      result,
            "nlp":         nlp,
        }

        log_signal(f"[QUANT] {sym}", "scanner", consensus)

        # Action 2: Record as paper trade for outcome tracking
        try:
            record_paper_trade(result, nlp, trade_id, regime)
        except Exception:
            pass

        # Record agent votes for walk-forward tracker
        try:
            from agent_tracker import record_votes_from_scan
            synthetic_votes = {
                s["signal"]: {
                    "found_opportunity": True,
                    "direction": s.get("direction", result["direction"]),
                    "conviction": ("HIGH"   if s.get("strength", 0) > 0.7
                                   else "MEDIUM" if s.get("strength", 0) > 0.4
                                   else "LOW"),
                }
                for s in result.get("fired_signals", [])
            }
            record_votes_from_scan(trade_id, synthetic_votes, sym,
                                    result["direction"])
        except Exception:
            pass

        signals_sent.append({
            "trade_id":    trade_id,
            "symbol":      sym,
            "direction":   result["direction"],
            "probability": result["probability"],
            "n_fired":     result["n_fired"],
            "n_groups":    result["n_groups"],
            "nlp_verdict": nlp.get("verdict"),
        })

    return {
        "fired":         len(signals_sent) > 0,
        "signals_sent":  signals_sent,
        "total_scanned": len(instruments),
        "fired_count":   len(fired_instruments),
        "suppressed":    len(fired_instruments) - len(signals_sent),
        "regime":        regime,
        "timestamp":     datetime.now(IST).isoformat(),
    }


# ── Market hours ───────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    op = now.replace(hour=MARKET_OPEN[0],  minute=MARKET_OPEN[1],  second=0, microsecond=0)
    cl = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return op <= now <= cl


# ── Background scanner thread ──────────────────────────────────────────────────

class MarketScanner:
    def __init__(self):
        self._thread        = None
        self._stop          = threading.Event()
        self.running        = False
        self.last_scan      = None
        self.last_result    = None
        self.scan_count     = 0
        self.signals_fired  = 0
        self._lock          = threading.Lock()
        self._ctx_fn        = None
        self.api_key        = ""
        self.telegram_token = ""
        self.telegram_chat  = ""
        self.groww_token    = ""
        self.capital        = 500000

    def configure(self, api_key, telegram_token, telegram_chat_id,
                  groww_token, get_context_fn=None, capital=500000):
        self.api_key        = api_key
        self.telegram_token = telegram_token
        self.telegram_chat  = telegram_chat_id
        self.groww_token    = groww_token
        self._ctx_fn        = get_context_fn
        self.capital        = capital

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.running = True

    def stop(self):
        self._stop.set()
        self.running = False

    def _loop(self):
        while not self._stop.is_set():
            if is_market_open():
                self._do_scan()
            interval = SCAN_INTERVAL_MINUTES * 60
            for _ in range(interval // 5):
                if self._stop.is_set():
                    break
                time.sleep(5)

    def _do_scan(self):
        try:
            ctx = self._ctx_fn() if self._ctx_fn else ""
            result = run_scan_cycle(
                self.api_key, self.telegram_token,
                self.telegram_chat, self.groww_token,
                ctx, self.capital,
            )
            with self._lock:
                self.last_scan   = datetime.now(IST)
                self.last_result = result
                self.scan_count += 1
                if result.get("fired"):
                    self.signals_fired += len(result.get("signals_sent", []))
        except Exception as e:
            with self._lock:
                self.last_result = {"error": str(e), "fired": False}

    def force_scan(self) -> dict:
        self._do_scan()
        return self.last_result or {}

    def status(self) -> dict:
        with self._lock:
            last_syms = []
            if self.last_result and self.last_result.get("signals_sent"):
                last_syms = [s["symbol"] for s in self.last_result["signals_sent"]]
            return {
                "running":        self.running,
                "scan_count":     self.scan_count,
                "signals_fired":  self.signals_fired,
                "last_scan":      (self.last_scan.strftime("%H:%M:%S IST")
                                   if self.last_scan else "Never"),
                "last_instrument":(", ".join(last_syms) if last_syms else "—"),
                "last_fired":     bool(last_syms),
                "market_open":    is_market_open(),
                "error":          (self.last_result.get("error","")
                                   if self.last_result else ""),
                "regime":         (self.last_result.get("regime","UNKNOWN")
                                   if self.last_result else "UNKNOWN"),
                "total_scanned":  (self.last_result.get("total_scanned",0)
                                   if self.last_result else 0),
            }


@st.cache_resource
def get_scanner() -> MarketScanner:
    return MarketScanner()
