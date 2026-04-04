"""
scanner.py — Autonomous Market Scanner
HIVE MIND ALPHA

Runs every 15 minutes during market hours (9:15 AM – 3:30 PM IST).
All 8 agents independently scan live data for opportunities.
Meta-agent synthesizes. If conviction threshold met, fires to Telegram.
No query needed — fully autonomous.
"""

import anthropic
import threading
import time
import json
import uuid
import concurrent.futures
from datetime import datetime
import pytz
import streamlit as st

IST = pytz.timezone("Asia/Kolkata")

SCAN_INTERVAL_MINUTES = 15
SIGNAL_COOLDOWN_HOURS = 2
MARKET_OPEN  = (9, 15)
MARKET_CLOSE = (15, 30)

# ── Per-agent scan prompts ─────────────────────────────────────────────────────
SCANNER_PROMPTS = {
    "quant_oracle": (
        "You are the QUANT ORACLE (Jim Simons). Scan the live market data for the SINGLE BEST "
        "statistical edge RIGHT NOW — momentum anomaly, mean-reversion z-score >2σ, "
        "OI imbalance, IV surface anomaly, volume spike, unusual PCR reading. "
        "SENSEX ~73-80k | NIFTY ~22-25k | BANKNIFTY ~48-52k. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "value_sentinel": (
        "You are the VALUE SENTINEL (Buffett/Munger). Scan for SENSEX/Nifty stocks showing "
        "compelling value entry RIGHT NOW — undervalued vs intrinsic value, quality stock near "
        "52W low, sector dislocation creating long-term entry. "
        "SENSEX ~73-80k | NIFTY ~22-25k | BANKNIFTY ~48-52k. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "macro_titan": (
        "You are the MACRO TITAN (Soros). Scan FII/DII flows, VIX, index levels. "
        "Identify REFLEXIVE opportunities — self-reinforcing macro trend RIGHT NOW. "
        "FII buying/selling patterns, VIX regime shifts, INR pressure, breadth divergence. "
        "SENSEX ~73-80k | NIFTY ~22-25k | BANKNIFTY ~48-52k. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "chart_hawk": (
        "You are the CHART HAWK (Livermore). Scan index levels, OI buildup, sector performance. "
        "Find the BEST technical setup RIGHT NOW — breakout above resistance, breakdown, "
        "Wyckoff spring, volume-confirmed trend resumption. Specific levels required. "
        "SENSEX ~73-80k | NIFTY ~22-25k | BANKNIFTY ~48-52k. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "options_architect": (
        "You are the OPTIONS ARCHITECT (Taleb). Scan VIX, PCR, OI chain, max pain, gamma walls. "
        "Find the BEST options trade RIGHT NOW — CE/PE buy, spread, strangle, or iron condor. "
        "Consider IV rank, skew, theta, event risk. "
        "NIFTY ~22-25k | BANKNIFTY ~48-52k. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"OPTIONS\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "sector_guru": (
        "You are the SECTOR GURU (Peter Lynch). Scan sector indices (IT, Banking, FMCG, Auto, "
        "Pharma, PSU Bank, Metal, Realty). Find the best SECTOR ROTATION opportunity RIGHT NOW — "
        "sector breakout, relative strength vs Nifty, laggard catch-up, catalyst move. "
        "NIFTY ~22-25k. Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "risk_guardian": (
        "You are the RISK GUARDIAN (Dalio). Scan VIX, breadth, FII flows, OI. "
        "Identify if conditions warrant a PROTECTIVE HEDGE now, OR if risk is so low "
        "aggressive positioning is justified. Think put protection, defensive positioning. "
        "NIFTY ~22-25k | VIX regime matters most. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
    "behavioral_lens": (
        "You are the BEHAVIORAL LENS (Kahneman). Scan VIX, PCR extremes, FII vs retail OI, "
        "index moves. Find BEHAVIORAL MISPRICINGS RIGHT NOW — extreme fear/greed creating "
        "contrarian opportunity. Extreme PCR, VIX spike/collapse, retail FOMO. "
        "NIFTY ~22-25k | BANKNIFTY ~48-52k. "
        "Respond ONLY in JSON: {\"found_opportunity\":bool,\"instrument\":str,\"type\":\"EQUITY|OPTIONS|FUTURES\","
        "\"direction\":\"LONG|SHORT\",\"conviction\":\"HIGH|MEDIUM|LOW\",\"time_frame\":\"INTRADAY|SWING|POSITIONAL\","
        "\"signal\":str,\"entry_zone\":str,\"stop_loss\":str,\"target\":str,\"key_risk\":str}"
    ),
}

META_PROMPT = (
    "You are the HIVE MIND META-SCANNER. You have 8 agent scan results on live Indian market data. "
    "Decide if there is a HIGH-CONVICTION signal worth alerting the trader. "
    "FIRE only if: 3+ agents flag SAME instrument in SAME direction, OR 2 HIGH-conviction agents agree. "
    "REJECT if agents split on same instrument. "
    "Respond ONLY in JSON: {\"fire_signal\":bool,\"reason_no_signal\":str,\"instrument\":str,"
    "\"direction\":\"LONG|SHORT\",\"overall_conviction\":\"HIGH|MEDIUM|LOW\","
    "\"timeframe\":\"INTRADAY|SWING|POSITIONAL\",\"agreeing_agents\":list,\"dissenting_agents\":list,"
    "\"entry_zone\":str,\"stop_loss\":str,\"target_1\":str,\"target_2\":str,"
    "\"options_play\":str,\"signal_summary\":str,\"urgency\":\"IMMEDIATE|NEXT_15MIN|TODAY\"}"
)


def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    op  = now.replace(hour=MARKET_OPEN[0],  minute=MARKET_OPEN[1],  second=0, microsecond=0)
    cl  = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return op <= now <= cl


def scan_agent(agent_id: str, context: str, api_key: str) -> dict:
    prompt = SCANNER_PROMPTS.get(agent_id, "")
    if not prompt:
        return {"found_opportunity": False}
    client = anthropic.Anthropic(api_key=api_key)
    try:
        r = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=500,
            system=prompt,
            messages=[{"role": "user", "content":
                f"LIVE DATA:\n{context}\n\nTime: {datetime.now(IST).strftime('%H:%M IST')}\n"
                "Scan and respond in JSON only."}],
        )
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception as e:
        return {"found_opportunity": False, "error": str(e)}


def run_meta(agent_results: dict, context: str, api_key: str) -> dict:
    summaries = []
    for aid, r in agent_results.items():
        if r.get("found_opportunity"):
            summaries.append(
                f"{aid.upper()}: {r.get('instrument','?')} {r.get('direction','?')} "
                f"({r.get('conviction','?')}) — {r.get('signal','')[:120]}"
            )
        else:
            summaries.append(f"{aid.upper()}: No opportunity.")
    client = anthropic.Anthropic(api_key=api_key)
    try:
        r = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=700,
            system=META_PROMPT,
            messages=[{"role": "user", "content":
                f"AGENT RESULTS:\n" + "\n".join(summaries) +
                f"\n\nLIVE CONTEXT:\n{context[:1000]}\n\nDecide. JSON only."}],
        )
        raw = r.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception as e:
        return {"fire_signal": False, "reason_no_signal": str(e)}


_recent: dict = {}

def is_duplicate(instrument: str) -> bool:
    ts = _recent.get(instrument)
    if not ts:
        return False
    return (datetime.now(IST) - ts).total_seconds() / 3600 < SIGNAL_COOLDOWN_HOURS


def mark_sent(instrument: str):
    _recent[instrument] = datetime.now(IST)


def format_signal(meta: dict) -> str:
    now      = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    instr    = meta.get("instrument","—")
    dirn     = meta.get("direction","—")
    conv     = meta.get("overall_conviction","—")
    tf       = meta.get("timeframe","—")
    entry    = meta.get("entry_zone","—")
    sl       = meta.get("stop_loss","—")
    t1       = meta.get("target_1","—")
    t2       = meta.get("target_2","—")
    opts     = meta.get("options_play") or ""
    summary  = meta.get("signal_summary","—")
    urgency  = meta.get("urgency","TODAY")
    agreeing = meta.get("agreeing_agents",[])
    dissent  = meta.get("dissenting_agents",[]) or ["None"]
    n        = len(agreeing)
    bar      = "█" * n + "░" * (8 - n)
    de       = "🟢" if dirn=="LONG" else "🔴"
    ue       = "🚨" if urgency=="IMMEDIATE" else "⚡" if urgency=="NEXT_15MIN" else "📊"
    return (
        f"{ue} <b>AUTONOMOUS SIGNAL — HIVE MIND ALPHA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}  |  🤖 Auto-scanned\n\n"
        f"{de} <b>{dirn} {instr}</b>\n"
        f"🔥 Conviction: <b>{conv}</b>  |  {tf}\n"
        f"📊 Agents: [{bar}] {n}/8\n\n"
        f"━━━━━━━━ LEVELS ━━━━━━━━\n"
        f"📥 Entry: {entry}\n"
        f"🛑 Stop Loss: {sl}\n"
        f"🎯 T1: {t1}  |  T2: {t2}\n"
        + (f"⚡ Options: {opts}\n" if opts else "")
        + f"\n━━━━━━━━ AGENTS ━━━━━━━━\n"
        f"✅ Agree: {', '.join(agreeing)}\n"
        f"⚠️ Dissent: {', '.join(dissent)}\n\n"
        f"💡 <i>{summary}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Auto-signal. Educational only. Not SEBI advice.</i>"
    )


def run_scan_cycle(api_key: str, telegram_token: str, telegram_chat_id: str,
                   groww_token: str, market_context: str) -> dict:
    from agents import AGENTS
    from telegram_bot import send_telegram_message, build_approval_keyboard
    from trade_log import log_signal

    agent_ids = [a["id"] for a in AGENTS]

    # All 8 agents scan in parallel
    agent_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(scan_agent, aid, market_context, api_key): aid
                for aid in agent_ids}
        for fut, aid in futs.items():
            try:
                agent_results[aid] = fut.result(timeout=30)
            except Exception:
                agent_results[aid] = {"found_opportunity": False}

    opps = sum(1 for r in agent_results.values() if r.get("found_opportunity"))
    if opps < 2:
        return {"fired": False, "reason": f"Only {opps} agent(s) found opportunities",
                "agent_results": agent_results,
                "timestamp": datetime.now(IST).isoformat()}

    meta = run_meta(agent_results, market_context, api_key)

    if not meta.get("fire_signal"):
        return {"fired": False, "reason": meta.get("reason_no_signal","Meta rejected"),
                "agent_results": agent_results, "meta": meta,
                "timestamp": datetime.now(IST).isoformat()}

    instrument = meta.get("instrument","")
    if is_duplicate(instrument):
        return {"fired": False, "reason": f"Cooldown active for {instrument}",
                "agent_results": agent_results, "meta": meta,
                "timestamp": datetime.now(IST).isoformat()}

    trade_id = str(uuid.uuid4())[:8].upper()
    text     = format_signal(meta)
    keyboard = build_approval_keyboard(trade_id)
    tg_resp  = send_telegram_message(telegram_token, telegram_chat_id, text, keyboard)
    mark_sent(instrument)

    consensus = {
        "overall_stance":      meta.get("direction","NEUTRAL"),
        "conviction":          meta.get("overall_conviction","MEDIUM"),
        "time_horizon":        meta.get("timeframe","SWING"),
        "agent_agreement_pct": len(meta.get("agreeing_agents",[])) * 12,
        "key_thesis":          meta.get("signal_summary",""),
        "equity_trade": {
            "applicable":    True,
            "instrument":    instrument,
            "direction":     meta.get("direction","BUY"),
            "entry_price":   meta.get("entry_zone",""),
            "stop_loss":     meta.get("stop_loss",""),
            "target_1":      meta.get("target_1",""),
            "target_2":      meta.get("target_2",""),
            "holding_period":meta.get("timeframe",""),
            "quantity":      1,
        },
        "options_trade": {"applicable": False},
    }

    if "pending_scanner_trades" not in st.session_state:
        st.session_state["pending_scanner_trades"] = {}
    st.session_state["pending_scanner_trades"][trade_id] = {
        "consensus": consensus, "groww_token": groww_token,
        "timestamp": datetime.now(IST).isoformat(), "instrument": instrument,
    }

    log_signal(f"[AUTO] {instrument}", "scanner", consensus)

    return {"fired": True, "trade_id": trade_id, "instrument": instrument,
            "direction": meta.get("direction"), "conviction": meta.get("overall_conviction"),
            "agent_results": agent_results, "meta": meta,
            "telegram_ok": tg_resp.get("ok", False),
            "timestamp": datetime.now(IST).isoformat()}


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

    def configure(self, api_key, telegram_token, telegram_chat_id,
                  groww_token, get_context_fn):
        self.api_key        = api_key
        self.telegram_token = telegram_token
        self.telegram_chat  = telegram_chat_id
        self.groww_token    = groww_token
        self._ctx_fn        = get_context_fn

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
            if not ctx:
                return
            result = run_scan_cycle(
                self.api_key, self.telegram_token,
                self.telegram_chat, self.groww_token, ctx,
            )
            with self._lock:
                self.last_scan   = datetime.now(IST)
                self.last_result = result
                self.scan_count += 1
                if result.get("fired"):
                    self.signals_fired += 1
        except Exception as e:
            with self._lock:
                self.last_result = {"error": str(e), "fired": False}

    def force_scan(self) -> dict:
        self._do_scan()
        return self.last_result or {}

    def status(self) -> dict:
        with self._lock:
            return {
                "running":        self.running,
                "scan_count":     self.scan_count,
                "signals_fired":  self.signals_fired,
                "last_scan":      self.last_scan.strftime("%H:%M:%S IST") if self.last_scan else "Never",
                "last_instrument":self.last_result.get("instrument","—") if self.last_result else "—",
                "last_fired":     self.last_result.get("fired", False) if self.last_result else False,
                "market_open":    is_market_open(),
                "error":          self.last_result.get("error","") if self.last_result else "",
            }


@st.cache_resource
def get_scanner() -> MarketScanner:
    return MarketScanner()
