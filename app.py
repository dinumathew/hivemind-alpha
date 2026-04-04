"""
HIVE MIND ALPHA — Multi-Agent SENSEX Intelligence System
Zerodha Kite Connect · Real-Time Data · White + Navy Palette
Run: streamlit run app.py
"""

import streamlit as st
import anthropic
import json, time
import concurrent.futures
from threading import Lock
from datetime import datetime
import pytz

from agents import (
    AGENTS, CONSENSUS_CONFIG, TRADE_ADVISOR_CONFIG,
    ANALYTICS_CONFIG, get_agents_for_mode,
)
from groww_data import (
    get_live_indices_groww, get_stock_quote_groww, get_options_chain_groww,
    get_vix_data_groww, get_fii_dii_data, get_top_movers_nse,
    build_market_context_groww,
)
from telegram_bot import (
    test_telegram_connection, notify_and_await_approval,
)
from trade_log import log_signal, update_status, get_summary, get_all
from scanner import get_scanner, is_market_open, run_scan_cycle
from scanner import get_scanner

IST = pytz.timezone("Asia/Kolkata")

st.set_page_config(
    page_title="HIVE MIND ALPHA · SENSEX Intelligence",
    page_icon="▪", layout="wide", initial_sidebar_state="expanded",
)

# ── CSS: White + Navy ─────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg:#FFFFFF; --bg2:#F4F6FA; --panel:#FFFFFF; --panel2:#F8F9FC;
  --sidebar:#F0F3F9; --border:#DCE1EC; --border2:#B8C2D8;
  --navy:#1B2A4A; --navy2:#2C4070; --navy3:#3D5494;
  --navy-lt:#6B82B0; --navy-xlt:#C5D0E6; --navy-bg:#EEF1F8;
  --gold:#8B6914; --gold2:#A07820; --gold-lt:#C9A84C; --gold-bg:#FBF8F0;
  --green:#1A6B3C; --green-bg:#EBF5F0;
  --red:#8B1A1A; --red-bg:#FAECEC;
  --amber:#7A4A0A; --amber-bg:#FEF3E2;
}
html,body,[class*="css"]{font-family:'Inter',sans-serif;background:var(--bg)!important;color:var(--navy);}
.stApp{background:var(--bg)!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding:1.8rem 2.2rem 3rem;max-width:1440px;}

.hm-masthead{border-bottom:2px solid var(--navy);padding-bottom:14px;margin-bottom:18px;}
.hm-wordmark{font-family:'EB Garamond',serif;font-size:28px;font-weight:600;color:var(--navy);letter-spacing:4px;}
.hm-wordmark span{color:var(--gold);}
.hm-tagline{font-size:10px;font-weight:500;color:var(--navy-lt);letter-spacing:3px;text-transform:uppercase;margin-top:3px;}

[data-testid="stSidebar"]{background:var(--sidebar)!important;border-right:1px solid var(--border2)!important;}
.stTextInput>label,.stSelectbox>label{font-size:10px!important;font-weight:700!important;letter-spacing:2px!important;text-transform:uppercase!important;color:var(--navy2)!important;}
.stTextInput>div>div>input{background:var(--panel)!important;border:1px solid var(--border2)!important;border-radius:2px!important;color:var(--navy)!important;font-size:14px!important;padding:10px 14px!important;}
.stTextInput>div>div>input:focus{border-color:var(--navy)!important;box-shadow:0 0 0 2px rgba(27,42,74,0.1)!important;}
.stTextInput>div>div>input::placeholder{color:var(--navy-lt)!important;}
.stSelectbox>div>div{background:var(--panel)!important;border:1px solid var(--border2)!important;border-radius:2px!important;color:var(--navy)!important;}
.stButton>button{background:var(--navy)!important;border:none!important;color:#fff!important;font-size:11px!important;font-weight:700!important;letter-spacing:2px!important;text-transform:uppercase!important;border-radius:2px!important;padding:10px 24px!important;}
.stButton>button:hover{background:var(--navy2)!important;}
.stButton>button:disabled{background:var(--border2)!important;}
.stProgress>div>div>div{background:var(--gold)!important;}
.stProgress>div>div{background:var(--border)!important;}
hr{border-color:var(--border)!important;}

/* Live ticker bar */
.ticker-wrap{background:var(--navy);border-radius:2px;padding:10px 18px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:24px;align-items:center;}
.ticker-item{text-align:center;}
.ticker-name{font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:1px;}
.ticker-price{font-family:'EB Garamond',serif;font-size:18px;font-weight:600;color:#F0F3F9;}
.ticker-chg{font-family:'JetBrains Mono',monospace;font-size:10px;}
.tc-up{color:#4CAF82;} .tc-dn{color:#FF6B6B;}
.ticker-div{width:1px;background:#2C4070;height:32px;align-self:center;}
.kite-live{display:inline-flex;align-items:center;gap:6px;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:1px;}
.kite-dot{width:7px;height:7px;border-radius:50%;animation:pulse 1.5s infinite;}
.kite-dot.live{background:#4CAF82;box-shadow:0 0 6px #4CAF82;}
.kite-dot.off{background:#6B82B0;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}

/* Kite connect UI */
.kite-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:2px;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;border:1px solid;}
.kb-on{border-color:#A8D4BC;color:var(--green);background:var(--green-bg);}
.kb-off{border-color:#B8C2D8;color:var(--navy-lt);background:var(--bg2);}

.sec-label{font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--navy2);padding:5px 0;border-bottom:1px solid var(--border);margin:20px 0 14px;}
.sec-label::before{content:'▪  ';color:var(--gold);}

.ag-card{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--border2);border-radius:2px;padding:16px;margin-bottom:12px;}
.ag-card.active{border-left-color:var(--gold);background:var(--gold-bg);}
.ag-card.done{border-left-color:var(--green);}
.ag-head{display:flex;align-items:center;gap:12px;margin-bottom:10px;}
.ag-icon{width:34px;height:34px;border-radius:50%;background:var(--navy-bg);border:1px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0;}
.ag-name{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--navy);}
.ag-legend{font-size:11px;color:var(--navy-lt);margin-top:1px;}
.ag-role{font-size:12px;color:var(--navy2);margin-bottom:8px;}
.status-pill{display:inline-flex;align-items:center;gap:5px;padding:2px 10px;font-size:10px;letter-spacing:1px;border-radius:1px;border:1px solid;font-family:'JetBrains Mono',monospace;}
.sp-idle{border-color:var(--border);color:var(--navy-lt);}
.sp-running{border-color:var(--gold-lt);color:var(--gold);background:var(--gold-bg);}
.sp-done{border-color:#A8D4BC;color:var(--green);background:var(--green-bg);}
.sp-error{border-color:#F0BABA;color:var(--red);background:var(--red-bg);}
.ag-output{background:var(--panel2);border:1px solid var(--border);border-radius:2px;padding:12px 14px;margin-top:8px;font-size:12.5px;line-height:1.75;color:var(--navy2);white-space:pre-wrap;min-height:40px;}
.live-context-badge{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;background:var(--green-bg);border:1px solid #A8D4BC;border-radius:1px;font-size:10px;font-weight:700;letter-spacing:1px;color:var(--green);margin-top:6px;}

.debate-card{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--navy-xlt);border-radius:2px;padding:14px 16px;margin-bottom:8px;}
.debate-hdr{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--navy2);margin-bottom:6px;}
.debate-body{font-size:13px;line-height:1.75;color:var(--navy2);white-space:pre-wrap;}

.cs-panel{background:var(--panel);border:1px solid var(--border2);border-top:3px solid var(--navy);border-radius:2px;padding:24px;}
.cs-kpi-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;}
.cs-kpi{background:var(--navy-bg);border:1px solid var(--border);border-radius:2px;padding:14px 18px;min-width:120px;flex:1;text-align:center;}
.cs-kpi-label{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--navy-lt);margin-bottom:5px;}
.cs-kpi-val{font-family:'EB Garamond',serif;font-size:22px;font-weight:600;}
.cv-bull{color:var(--green);} .cv-bear{color:var(--red);} .cv-neut{color:var(--amber);}
.cv-navy{color:var(--navy);} .cv-gold{color:var(--gold);}
.cs-block{background:var(--panel2);border:1px solid var(--border);border-radius:2px;padding:12px 14px;}
.cs-block-label{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--navy-lt);margin-bottom:5px;}
.cs-block-val{font-size:13px;line-height:1.7;color:var(--navy);}
.cs-narrative{border-left:3px solid var(--navy-xlt);padding-left:16px;font-size:13.5px;line-height:1.9;color:var(--navy2);white-space:pre-wrap;}
.tag-chip{display:inline-block;padding:3px 10px;margin:2px;border:1px solid var(--navy-xlt);border-radius:1px;font-size:10px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--navy2);background:var(--navy-bg);}

.stTabs [data-baseweb="tab-list"]{background:var(--sidebar);border-radius:2px;border:1px solid var(--border2);gap:0;}
.stTabs [data-baseweb="tab"]{font-size:11px!important;font-weight:700!important;letter-spacing:2px!important;text-transform:uppercase!important;color:var(--navy-lt)!important;background:transparent!important;border-radius:0!important;padding:12px 20px!important;}
.stTabs [aria-selected="true"]{color:var(--navy)!important;border-bottom:2px solid var(--navy)!important;background:var(--navy-bg)!important;}
.streamlit-expanderHeader{font-size:11px!important;font-weight:700!important;letter-spacing:2px!important;text-transform:uppercase!important;color:var(--navy)!important;background:var(--panel)!important;border:1px solid var(--border)!important;border-radius:2px!important;}
.streamlit-expanderContent{background:var(--panel2)!important;border:1px solid var(--border)!important;border-top:none!important;}

.hero{text-align:center;padding:60px 20px;background:var(--navy-bg);border:1px solid var(--border);border-radius:2px;}
.hero-title{font-family:'EB Garamond',serif;font-size:20px;color:var(--navy);letter-spacing:3px;margin-bottom:12px;}
.hero-body{font-size:11px;color:var(--navy-lt);letter-spacing:2px;line-height:2.6;text-transform:uppercase;}
.disclaimer{text-align:center;padding:12px;font-size:10px;letter-spacing:1px;color:var(--navy-lt);line-height:2;border:1px solid var(--border);border-radius:2px;margin-top:18px;background:var(--navy-bg);}
</style>
""", unsafe_allow_html=True)

# ── Session defaults ───────────────────────────────────────────────────────────
for k, v in [("groww_token", ""), ("kite_connected", False)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Masthead ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hm-masthead">
  <div class="hm-wordmark">HIVE MIND <span>ALPHA</span></div>
  <div class="hm-tagline">Multi-Agent Investment Intelligence · SENSEX &amp; NIFTY · Zerodha Real-Time Data</div>
</div>""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-family:\'EB Garamond\',serif;font-size:18px;color:#1B2A4A;margin-bottom:14px;">Configuration</div>', unsafe_allow_html=True)

    api_key_input = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
    api_key = api_key_input or st.session_state.get("api_key","") or st.secrets.get("ANTHROPIC_API_KEY","")
    if api_key_input:
        st.session_state["api_key"] = api_key_input

    st.markdown("---")
    st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:10px;">Groww Live Data</div>', unsafe_allow_html=True)
    stored_token = st.secrets.get("GROWW_API_TOKEN","") or st.session_state.get("groww_token","")
    if stored_token:
        st.markdown('<div style="background:#EBF5F0;border:1px solid #A8D4BC;border-radius:2px;padding:8px 12px;font-size:11px;color:#1A6B3C;font-weight:700;margin-bottom:6px;">● GROWW CONNECTED</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:10px;color:#6B82B0;line-height:1.8;">Live prices, options chain, VIX, OI and FII/DII flows active. Options chain via NSE free feed.</div>', unsafe_allow_html=True)
    else:
        groww_token_input = st.text_input("Groww API Token", type="password", placeholder="Your Groww access token", key="groww_tok_input")
        if groww_token_input:
            st.session_state["groww_token"] = groww_token_input
            st.success("✅ Token saved for this session.")
        st.markdown('<div style="font-size:10px;color:#9B9B9B;line-height:1.8;margin-top:6px;">Get at <span style="color:#8B6914;">groww.in/trade-api</span> · ₹499/month<br>Or add GROWW_API_TOKEN to Streamlit Secrets.</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Autonomous Scanner ──────────────────────────────────────────────────
    st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:10px;">🤖 Autonomous Scanner</div>', unsafe_allow_html=True)

    scanner = get_scanner()

    tg_tok_sc  = st.secrets.get("TELEGRAM_BOT_TOKEN","")
    tg_cid_sc  = st.secrets.get("TELEGRAM_CHAT_ID","")
    gww_tok_sc = st.secrets.get("GROWW_API_TOKEN","")
    api_key_sc = st.secrets.get("ANTHROPIC_API_KEY","") or st.session_state.get("api_key","")

    market_open_now = is_market_open()

    if not scanner.running:
        st.markdown(f'<div style="font-size:11px;color:#9B9B9B;margin-bottom:8px;">{"🟡 Market open — ready to scan" if market_open_now else "🔴 Market closed"}</div>', unsafe_allow_html=True)
        if tg_tok_sc and tg_cid_sc and api_key_sc:
            if st.button("▶ Start Auto-Scanner", key="scanner_start", use_container_width=True):
                def get_live_ctx():
                    from groww_data import build_market_context_groww
                    return build_market_context_groww(gww_tok_sc)
                scanner.configure(api_key_sc, tg_tok_sc, tg_cid_sc, gww_tok_sc, get_live_ctx)
                scanner.start()
                st.success("✅ Scanner started! Scans every 15 min during market hours.")
                st.rerun()
        else:
            st.markdown('<div style="font-size:10px;color:#8B1A1A;">Configure API keys in Secrets first.</div>', unsafe_allow_html=True)
    else:
        s = scanner.status()
        mkt_col = "#1A6B3C" if s["market_open"] else "#8B6914"
        st.markdown(
            f'<div style="background:#EBF5F0;border:1px solid #A8D4BC;border-radius:2px;padding:10px;margin-bottom:8px;">'
            f'<div style="font-size:10px;font-weight:700;color:#1A6B3C;margin-bottom:4px;">● SCANNER ACTIVE</div>'
            f'<div style="font-size:11px;color:#2C4070;line-height:1.8;">'
            f'Scans: {s["scan_count"]}  |  Signals: {s["signals_fired"]}<br>'
            f'Last scan: {s["last_scan"]}<br>'
            f'Last signal: {s["last_instrument"]}<br>'
            f'<span style="color:{mkt_col};">{"🟢 Market OPEN" if s["market_open"] else "🟡 Market CLOSED"}</span>'
            f'{"<br><span style=color:#8B1A1A;>Error: " + s["error"][:40] + "</span>" if s.get("error") else ""}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("⏹ Stop", key="scanner_stop", use_container_width=True):
                scanner.stop()
                st.rerun()
        with col_b:
            if st.button("🔍 Scan Now", key="scanner_force", use_container_width=True):
                with st.spinner("Scanning…"):
                    r = scanner.force_scan()
                if r.get("fired"):
                    st.success(f"Signal fired: {r.get('instrument','?')} {r.get('direction','?')}")
                else:
                    st.info(f"No signal: {r.get('reason','')[:60]}")

    st.markdown("---")
    st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:8px;">Market Reference</div>', unsafe_allow_html=True)
    st.markdown("""<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:2.2;color:#2C4070;">
    SENSEX (BSE 30)<br><span style="color:#8B6914;">≈ 73,000 – 80,000</span><br><br>
    NIFTY 50 (NSE)<br><span style="color:#8B6914;">≈ 22,000 – 25,000</span><br><br>
    BANKNIFTY<br><span style="color:#8B6914;">≈ 48,000 – 52,000</span></div>""", unsafe_allow_html=True)
    st.markdown("---")
    for ag in AGENTS:
        st.markdown(f'<div style="font-size:11px;color:#2C4070;margin-bottom:5px;">{ag["icon"]} <b style="color:#1B2A4A;">{ag["name"]}</b><br><span style="color:#9B9B9B;font-size:10px;">{ag["legend"]}</span></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("---")
    st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:10px;">Telegram Alerts</div>', unsafe_allow_html=True)
    tg_tok_sb = st.secrets.get("TELEGRAM_BOT_TOKEN","")
    tg_cid_sb = st.secrets.get("TELEGRAM_CHAT_ID","")
    if tg_tok_sb and tg_cid_sb:
        st.markdown('<div style="font-size:11px;color:#1A6B3C;margin-bottom:8px;">● Connected</div>', unsafe_allow_html=True)
        if st.button("Send Test Message", key="tg_test"):
            ok = test_telegram_connection(tg_tok_sb, tg_cid_sb)
            if ok: st.success("✅ Test message sent!")
            else:  st.error("❌ Failed. Check token/chat ID.")
    else:
        st.markdown('<div style="font-size:11px;color:#9B9B9B;">Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to Streamlit Secrets.</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div style="font-size:9px;letter-spacing:1px;color:#B8C2D8;line-height:1.8;">EDUCATIONAL USE ONLY · NOT SEBI-REGISTERED · F&O INVOLVES RISK</div>', unsafe_allow_html=True)

# ── API Key guard ──────────────────────────────────────────────────────────────
if not api_key:
    st.markdown('<div class="hero"><div class="hero-title">API Key Required</div><div class="hero-body">Enter your Anthropic API key in the sidebar<br><span style="color:#8B6914;">console.anthropic.com</span></div></div>', unsafe_allow_html=True)
    st.stop()

# ── Live data helpers ──────────────────────────────────────────────────────────
def get_groww_token():
    """Return Groww API token from secrets or session state."""
    return (st.secrets.get("GROWW_API_TOKEN","") or
            st.session_state.get("groww_token",""))


def render_live_ticker(indices: dict, vix: dict):
    """Render a dark ticker bar with live index prices."""
    idx = indices.get("data", {})
    items = []
    for name in ["NIFTY 50", "SENSEX", "BANKNIFTY"]:
        d = idx.get(name, {})
        if not d: continue
        arrow = "▲" if d["change"] >= 0 else "▼"
        cls   = "tc-up" if d["change"] >= 0 else "tc-dn"
        items.append(
            f'<div class="ticker-item">'
            f'<div class="ticker-name">{name}</div>'
            f'<div class="ticker-price">{d["last_price"]:,.2f}</div>'
            f'<div class="ticker-chg {cls}">{arrow} {abs(d["change"]):.2f} ({abs(d["change_pct"]):.2f}%)</div>'
            f'</div><div class="ticker-div"></div>'
        )
    if vix.get("success"):
        arrow = "▲" if vix["change"] >= 0 else "▼"
        cls   = "tc-dn" if vix["change"] >= 0 else "tc-up"   # VIX up = bad
        items.append(
            f'<div class="ticker-item">'
            f'<div class="ticker-name">INDIA VIX</div>'
            f'<div class="ticker-price">{vix["vix"]:.2f}</div>'
            f'<div class="ticker-chg {cls}">{arrow} {abs(vix["change"]):.2f} · {vix["regime"]}</div>'
            f'</div>'
        )
    ts = indices.get("timestamp","")
    items.append(f'<div style="margin-left:auto;"><div class="kite-live"><span class="kite-dot live"></span><span style="color:#4CAF82;">LIVE</span></div><div style="font-size:9px;color:#3D5494;margin-top:2px;">{ts}</div></div>')
    st.markdown(f'<div class="ticker-wrap">{"".join(items)}</div>', unsafe_allow_html=True)


# ── Agent helpers ──────────────────────────────────────────────────────────────
def run_agent_stream(agent, user_msg, api_key, max_tokens, store, lock):
    client = anthropic.Anthropic(api_key=api_key)
    full = ""
    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514", max_tokens=max_tokens,
            system=agent["system"], messages=[{"role":"user","content":user_msg}],
        ) as stream:
            for chunk in stream.text_stream:
                full += chunk
                with lock: store[agent["id"]] = {"text":full,"done":False}
        with lock: store[agent["id"]] = {"text":full,"done":True}
    except Exception as e:
        with lock: store[agent["id"]] = {"text":f"Error: {e}","done":True,"error":True}


def render_agent_card(agent, status, text, live=False):
    if status=="thinking": state,pill = "active",'<span class="status-pill sp-running">● Analyzing</span>'
    elif status=="done":   state,pill = "done",  '<span class="status-pill sp-done">✓ Complete</span>'
    elif status=="error":  state,pill = "error", '<span class="status-pill sp-error">✗ Error</span>'
    else:                  state,pill = "",      '<span class="status-pill sp-idle">◌ Standby</span>'
    safe = (text or "").replace("<","&lt;").replace(">","&gt;")
    body = safe if safe else '<span style="color:#B8C2D8">Awaiting dispatch…</span>'
    live_badge = '<div class="live-context-badge">📡 LIVE DATA INJECTED</div>' if live else ""
    return f"""<div class="ag-card {state}">
  <div class="ag-head"><div class="ag-icon">{agent["icon"]}</div>
  <div><div class="ag-name">{agent["name"]}</div><div class="ag-legend">{agent["legend"]}</div></div></div>
  <div class="ag-role">{agent["role"]}</div>
  {pill}{live_badge}
  <div class="ag-output">{body}</div>
</div>"""


def build_query_msg(q, mode, market_ctx=""):
    now = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    ctx_block = f"\n{market_ctx}\n" if market_ctx else ""
    return f"""INVESTMENT QUERY: "{q}"
MODE: {mode.upper()} | SENSEX (BSE) / NIFTY (NSE)
TIMESTAMP: {now}
{ctx_block}
Provide your expert analysis using the live market data above as your primary context.
Structure:
1. KEY SIGNAL / OPPORTUNITY (reference specific live prices/levels above)
2. CRITICAL RISK FACTOR
3. SPECIFIC RECOMMENDATION (Bullish / Bearish / Neutral with exact levels)
4. ONE CONTRARIAN TAKE

Be specific, quantitative, and anchor every claim to the live data provided. Max 280 words."""


def build_consensus_msg(q, mode, analyses):
    summaries = "\n\n".join([
        f"=== {a['name']} ({a['legend']}) ===\n{analyses.get(a['id'],'N/A')[:400]}"
        for a in AGENTS if a["id"] in analyses
    ])
    return f"""QUERY: "{q}" | MODE: {mode.upper()}
SENSEX ≈ 73,000–80,000 | NIFTY 50 ≈ 22,000–25,000 | BANKNIFTY ≈ 48,000–52,000

AGENT ANALYSES:
{summaries}

Synthesize into a final consensus with SPECIFIC ACTIONABLE TRADES.
You MUST provide exact rupee prices — not vague ranges, not percentages alone.
Respond ONLY in valid JSON (no markdown, no backticks):
{{
  "overall_stance": "BULLISH"|"BEARISH"|"NEUTRAL",
  "conviction": "HIGH"|"MEDIUM"|"LOW",
  "time_horizon": "INTRADAY"|"SHORT-TERM (2-5 days)"|"MEDIUM-TERM (weeks)"|"LONG-TERM (months)",
  "agent_agreement_pct": <0-100>,
  "key_thesis": "<2-sentence core thesis>",
  "bull_case": "<one sentence>",
  "bear_case": "<one sentence>",
  "agents_bullish": ["names"],
  "agents_bearish": ["names"],
  "equity_trade": {{
    "applicable": true|false,
    "instrument": "<exact stock or index name e.g. HDFCBANK, NIFTY 50>",
    "direction": "BUY"|"SELL"|"AVOID",
    "entry_price": "<exact INR level e.g. ₹1,640–1,660>",
    "stop_loss": "<exact INR level e.g. ₹1,590 (below 200DMA)>",
    "target_1": "<exact INR level — conservative e.g. ₹1,720>",
    "target_2": "<exact INR level — primary e.g. ₹1,780>",
    "target_3": "<exact INR level — stretch e.g. ₹1,850>",
    "risk_reward": "<e.g. 1:2.8>",
    "position_size": "<% of portfolio e.g. 3-5% of capital>",
    "holding_period": "<e.g. Intraday only / 3-5 days / 2-4 weeks>",
    "entry_condition": "<exact trigger e.g. Buy on break above ₹1,660 with volume>",
    "exit_rule": "<exact rule e.g. Exit if closes below ₹1,590 on daily candle>",
    "invalidation": "<what kills this trade>"
  }},
  "options_trade": {{
    "applicable": true|false,
    "strategy": "<e.g. Buy CE / Buy PE / Bull Call Spread / Short Strangle / Iron Condor>",
    "underlying": "<e.g. NIFTY / BANKNIFTY / HDFCBANK>",
    "expiry": "<e.g. Current weekly / Next weekly / Monthly>",
    "leg_1": {{
      "action": "BUY"|"SELL",
      "type": "CE"|"PE",
      "strike": "<exact strike e.g. 24,500>",
      "premium": "<approximate premium range e.g. ₹80–95>",
      "delta": "<approx e.g. 0.45>"
    }},
    "leg_2": {{
      "action": "BUY"|"SELL"|"N/A",
      "type": "CE"|"PE"|"N/A",
      "strike": "<exact strike or N/A>",
      "premium": "<premium or N/A>",
      "delta": "<delta or N/A>"
    }},
    "net_premium": "<total debit or credit e.g. Net debit ₹85>",
    "max_loss": "<defined max loss e.g. ₹85 per lot = ₹4,250 for 1 lot>",
    "max_profit": "<defined or unlimited>",
    "breakeven": "<exact breakeven level(s)>",
    "target_exit_premium": "<exit when premium reaches e.g. ₹140–160>",
    "stop_loss_premium": "<exit if premium falls to e.g. ₹40>",
    "ideal_entry_time": "<e.g. First 30 min / After 10:30am / Day before expiry>",
    "theta_risk": "<e.g. Loses ₹8/day — exit by Wednesday if not working>",
    "vix_condition": "<e.g. Only enter if VIX below 16>",
    "holding_period": "<e.g. Intraday / Hold max 2 days / Till expiry>"
  }},
  "risk_management": {{
    "max_capital_at_risk": "<e.g. Never risk more than 2% of total capital on this>",
    "position_sizing_rule": "<specific rule>",
    "hedge_suggestion": "<optional hedge e.g. Buy 24,200 PE as hedge if long equity>"
  }},
  "tags": ["tag1","tag2","tag3","tag4"],
  "narrative": "<3 paragraphs: (1) what the agents agreed on and why, (2) key disagreements and how they were resolved, (3) final reasoning and what to watch that could change the view>"
}}"""


def render_cs(data, raw):
    stance    = data.get("overall_stance","NEUTRAL").upper()
    sc        = {"BULLISH":"cv-bull","BEARISH":"cv-bear"}.get(stance,"cv-neut")
    agree     = data.get("agent_agreement_pct","—")
    narrative = (data.get("narrative","") or raw).replace("<","&lt;").replace(">","&gt;")
    tags_html = "".join([f'<span class="tag-chip">{t}</span>' for t in data.get("tags",[])])
    a_bull    = ", ".join(data.get("agents_bullish",[]))
    a_bear    = ", ".join(data.get("agents_bearish",[]))
    eq        = data.get("equity_trade",{})
    op        = data.get("options_trade",{})
    rm        = data.get("risk_management",{})

    def kpi(label,val,cls="cv-navy"):
        return (f'<div class="cs-kpi"><div class="cs-kpi-label">{label}</div>'
                f'<div class="cs-kpi-val {cls}">{val}</div></div>')

    def row2(label,val,color="#1B2A4A"):
        if not val or val in ("N/A","n/a","null",""): return ""
        sv = str(val).replace("<","&lt;").replace(">","&gt;")
        return (f'<div style="display:flex;justify-content:space-between;align-items:flex-start;'
                f'padding:7px 0;border-bottom:1px solid #DCE1EC;">'
                f'<span style="font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;'
                f'color:#6B82B0;flex-shrink:0;margin-right:12px;">{label}</span>'
                f'<span style="font-size:13px;font-weight:600;color:{color};text-align:right;">{sv}</span></div>')

    # ── Equity Trade Card ──────────────────────────────────────────────────────
    eq_html = ""
    if eq.get("applicable") and eq.get("direction","AVOID") != "AVOID":
        dir_col = "#1A6B3C" if eq.get("direction")=="BUY" else "#8B1A1A"
        dir_bg  = "#EBF5F0" if eq.get("direction")=="BUY" else "#FAECEC"
        eq_html = f"""
<div style="background:#FFFFFF;border:1px solid #DCE1EC;border-top:3px solid {dir_col};border-radius:2px;padding:20px;margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
    <div>
      <div style="font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#6B82B0;margin-bottom:3px;">EQUITY TRADE</div>
      <div style="font-family:'EB Garamond',serif;font-size:20px;font-weight:600;color:#1B2A4A;">{eq.get("instrument","")}</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <div style="background:{dir_bg};border:1px solid {dir_col}44;border-radius:2px;padding:6px 16px;font-size:13px;font-weight:700;letter-spacing:2px;color:{dir_col};">{eq.get("direction","")}</div>
      <div style="background:#EEF1F8;border:1px solid #C5D0E6;border-radius:2px;padding:6px 12px;font-size:11px;font-weight:600;color:#1B2A4A;">{eq.get("holding_period","")}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">
    <div style="background:#EEF1F8;border-radius:2px;padding:12px;text-align:center;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">ENTRY</div>
      <div style="font-family:'EB Garamond',serif;font-size:17px;font-weight:600;color:#1B2A4A;">{eq.get("entry_price","—")}</div>
    </div>
    <div style="background:#FAECEC;border-radius:2px;padding:12px;text-align:center;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">STOP LOSS</div>
      <div style="font-family:'EB Garamond',serif;font-size:17px;font-weight:600;color:#8B1A1A;">{eq.get("stop_loss","—")}</div>
    </div>
    <div style="background:#FBF8F0;border-radius:2px;padding:12px;text-align:center;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">RISK:REWARD</div>
      <div style="font-family:'EB Garamond',serif;font-size:17px;font-weight:600;color:#8B6914;">{eq.get("risk_reward","—")}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">
    <div style="background:#EBF5F0;border-radius:2px;padding:10px;text-align:center;">
      <div style="font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#1A6B3C;margin-bottom:3px;">TARGET 1 (Conservative)</div>
      <div style="font-size:15px;font-weight:700;color:#1A6B3C;">{eq.get("target_1","—")}</div>
    </div>
    <div style="background:#EBF5F0;border-radius:2px;padding:10px;text-align:center;">
      <div style="font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#1A6B3C;margin-bottom:3px;">TARGET 2 (Primary)</div>
      <div style="font-size:15px;font-weight:700;color:#1A6B3C;">{eq.get("target_2","—")}</div>
    </div>
    <div style="background:#EBF5F0;border-radius:2px;padding:10px;text-align:center;">
      <div style="font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#1A6B3C;margin-bottom:3px;">TARGET 3 (Stretch)</div>
      <div style="font-size:15px;font-weight:700;color:#1A6B3C;">{eq.get("target_3","—")}</div>
    </div>
  </div>

  <div style="background:#F8F9FC;border:1px solid #DCE1EC;border-radius:2px;padding:14px;">
    {row2("Entry Condition", eq.get("entry_condition",""), "#1B2A4A")}
    {row2("Exit Rule", eq.get("exit_rule",""), "#8B1A1A")}
    {row2("Position Size", eq.get("position_size",""), "#8B6914")}
    {row2("Invalidated If", eq.get("invalidation",""), "#8B1A1A")}
  </div>
</div>"""

    # ── Options Trade Card ─────────────────────────────────────────────────────
    op_html = ""
    if op.get("applicable"):
        leg1 = op.get("leg_1",{})
        leg2 = op.get("leg_2",{})
        has_leg2 = leg2.get("action","N/A") not in ("N/A","","null",None)
        l1_col = "#1A6B3C" if leg1.get("action")=="BUY" else "#8B1A1A"
        l2_col = "#1A6B3C" if leg2.get("action")=="BUY" else "#8B1A1A"

        leg2_html = ""
        if has_leg2:
            leg2_html = f"""
    <div style="background:#F8F9FC;border:1px solid #DCE1EC;border-radius:2px;padding:14px;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:8px;">LEG 2</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <div style="background:{'#EBF5F0' if leg2.get('action')=='BUY' else '#FAECEC'};border-radius:2px;padding:5px 12px;font-size:12px;font-weight:700;color:{l2_col};">{leg2.get("action","")}</div>
        <div style="background:#EEF1F8;border-radius:2px;padding:5px 12px;font-size:12px;font-weight:700;color:#1B2A4A;">{leg2.get("type","")} {leg2.get("strike","")}</div>
        <div style="background:#FBF8F0;border-radius:2px;padding:5px 12px;font-size:12px;color:#8B6914;">Premium: {leg2.get("premium","")}</div>
        <div style="background:#EEF1F8;border-radius:2px;padding:5px 12px;font-size:12px;color:#1B2A4A;">Δ {leg2.get("delta","")}</div>
      </div>
    </div>"""

        op_html = f"""
<div style="background:#FFFFFF;border:1px solid #DCE1EC;border-top:3px solid #1B2A4A;border-radius:2px;padding:20px;margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
    <div>
      <div style="font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#6B82B0;margin-bottom:3px;">OPTIONS TRADE</div>
      <div style="font-family:'EB Garamond',serif;font-size:20px;font-weight:600;color:#1B2A4A;">{op.get("underlying","")} — {op.get("strategy","")}</div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <div style="background:#EEF1F8;border:1px solid #C5D0E6;border-radius:2px;padding:6px 12px;font-size:11px;font-weight:600;color:#1B2A4A;">Expiry: {op.get("expiry","")}</div>
      <div style="background:#EEF1F8;border:1px solid #C5D0E6;border-radius:2px;padding:6px 12px;font-size:11px;font-weight:600;color:#1B2A4A;">{op.get("holding_period","")}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;">
    <div style="background:#FAECEC;border-radius:2px;padding:12px;text-align:center;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">MAX LOSS</div>
      <div style="font-family:'EB Garamond',serif;font-size:16px;font-weight:600;color:#8B1A1A;">{op.get("max_loss","—")}</div>
    </div>
    <div style="background:#EBF5F0;border-radius:2px;padding:12px;text-align:center;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">MAX PROFIT</div>
      <div style="font-family:'EB Garamond',serif;font-size:16px;font-weight:600;color:#1A6B3C;">{op.get("max_profit","—")}</div>
    </div>
    <div style="background:#FBF8F0;border-radius:2px;padding:12px;text-align:center;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">NET PREMIUM</div>
      <div style="font-family:'EB Garamond',serif;font-size:16px;font-weight:600;color:#8B6914;">{op.get("net_premium","—")}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr{' 1fr' if has_leg2 else ''};gap:10px;margin-bottom:12px;">
    <div style="background:#F8F9FC;border:1px solid #DCE1EC;border-radius:2px;padding:14px;">
      <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:8px;">LEG 1</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <div style="background:{'#EBF5F0' if leg1.get('action')=='BUY' else '#FAECEC'};border-radius:2px;padding:5px 12px;font-size:12px;font-weight:700;color:{l1_col};">{leg1.get("action","")}</div>
        <div style="background:#EEF1F8;border-radius:2px;padding:5px 12px;font-size:12px;font-weight:700;color:#1B2A4A;">{leg1.get("type","")} {leg1.get("strike","")}</div>
        <div style="background:#FBF8F0;border-radius:2px;padding:5px 12px;font-size:12px;color:#8B6914;">Premium: {leg1.get("premium","")}</div>
        <div style="background:#EEF1F8;border-radius:2px;padding:5px 12px;font-size:12px;color:#1B2A4A;">Δ {leg1.get("delta","")}</div>
      </div>
    </div>
    {leg2_html}
  </div>

  <div style="background:#F8F9FC;border:1px solid #DCE1EC;border-radius:2px;padding:14px;">
    {row2("Breakeven", op.get("breakeven",""), "#1B2A4A")}
    {row2("Exit When Premium Hits", op.get("target_exit_premium",""), "#1A6B3C")}
    {row2("Stop Loss (Premium)", op.get("stop_loss_premium",""), "#8B1A1A")}
    {row2("Ideal Entry Time", op.get("ideal_entry_time",""), "#8B6914")}
    {row2("Theta Risk", op.get("theta_risk",""), "#8B1A1A")}
    {row2("VIX Condition", op.get("vix_condition",""), "#1B2A4A")}
  </div>
</div>"""

    # ── Risk Management ────────────────────────────────────────────────────────
    rm_html = ""
    if rm:
        rm_html = f"""
<div style="background:#EEF1F8;border:1px solid #C5D0E6;border-left:3px solid #1B2A4A;border-radius:2px;padding:14px;margin-bottom:14px;">
  <div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:8px;">⚠ RISK MANAGEMENT RULES</div>
  {row2("Max Capital at Risk", rm.get("max_capital_at_risk",""), "#8B1A1A")}
  {row2("Position Sizing Rule", rm.get("position_sizing_rule",""), "#1B2A4A")}
  {row2("Hedge Suggestion", rm.get("hedge_suggestion",""), "#8B6914")}
</div>"""

    return f"""<div class="cs-panel">
  <div style="font-family:'EB Garamond',serif;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#6B82B0;margin-bottom:14px;">HIVE MIND CONSENSUS VERDICT</div>

  <div class="cs-kpi-row">
    {kpi("Overall Stance", stance, sc)}
    {kpi("Conviction", data.get("conviction","—"), "cv-gold")}
    {kpi("Time Horizon", data.get("time_horizon","—"), "cv-navy")}
    {kpi("Agent Agreement", f"{agree}%" if agree!="—" else "—", "cv-navy")}
  </div>

  {'<div style="background:#F8F9FC;border:1px solid #DCE1EC;border-left:3px solid #1B2A4A;border-radius:2px;padding:14px;margin-bottom:14px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:6px;">CORE THESIS</div><div style="font-family:\'EB Garamond\',serif;font-size:17px;line-height:1.7;color:#1B2A4A;">'+data.get("key_thesis","")+'</div></div>' if data.get("key_thesis") else ""}

  {'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px;"><div style="background:#EBF5F0;border-radius:2px;padding:10px 14px;"><div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#1A6B3C;margin-bottom:3px;">↑ BULL CASE</div><div style="font-size:12.5px;color:#1A6B3C;">'+data.get("bull_case","")+'</div></div><div style="background:#FAECEC;border-radius:2px;padding:10px 14px;"><div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8B1A1A;margin-bottom:3px;">↓ BEAR CASE</div><div style="font-size:12.5px;color:#8B1A1A;">'+data.get("bear_case","")+'</div></div></div>' if (data.get("bull_case") or data.get("bear_case")) else ""}

  <div style="border-top:1px solid #DCE1EC;margin:16px 0;padding-top:4px;">
    <div style="font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#8B6914;margin-bottom:12px;">▪  SPECIFIC TRADE RECOMMENDATIONS</div>
    {eq_html}
    {op_html}
    {rm_html}
  </div>

  {'<div style="background:#F8F9FC;border-radius:2px;padding:10px 14px;margin-bottom:14px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">Agent Alignment</div><div style="font-size:12px;color:#1A6B3C;margin-bottom:2px;">Bullish: '+a_bull+'</div><div style="font-size:12px;color:#8B1A1A;">Bearish: '+a_bear+'</div></div>' if (a_bull or a_bear) else ""}

  <div style="border-top:1px solid #DCE1EC;margin:16px 0 12px;padding-top:4px;">
    <div style="font-size:10px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:#6B82B0;margin-bottom:10px;">▪  ANALYST NARRATIVE</div>
    <div class="cs-narrative">{narrative}</div>
  </div>

  <div>{tags_html}</div>
</div>"""


# ── TABS ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["▪  Hive Mind Analysis","▪  Daily Trade Desk","▪  Market Analytics","▪  Auto Scanner"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HIVE MIND ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    col1,col2,col3,col4 = st.columns([3,1,0.7,0.7])
    with col1:
        query = st.text_input("Investment Query",
            placeholder="e.g. HDFC Bank — buy the dip?  ·  BankNifty straddle  ·  SENSEX at 76000 — breakout?",
            key="main_query")
    with col2:
        mode = st.selectbox("Mode",["equity","fo","combined"],
            format_func=lambda x:{"equity":"Equity","fo":"F&O","combined":"Full Spectrum"}[x])
    with col3:
        depth = st.selectbox("Depth",[600,1000,1500],
            format_func=lambda x:{600:"Standard",1000:"Deep",1500:"Ultra"}[x])
    with col4:
        st.markdown("<br>",unsafe_allow_html=True)
        launch = st.button("Launch Agents",key="launch_main",use_container_width=True)

    if launch and query.strip():
        groww_tok = get_groww_token()
        market_ctx = ""
        live_data  = {}

        # Fetch live data using Groww API
        if groww_tok:
            with st.spinner("Fetching live market data from Groww…"):
                market_ctx = build_market_context_groww(groww_tok)
                # Also fetch individual components for ticker display
                import concurrent.futures as cfe
                with cfe.ThreadPoolExecutor(max_workers=3) as ex2:
                    fi2 = ex2.submit(get_live_indices_groww, groww_tok)
                    fv2 = ex2.submit(get_vix_data_groww, groww_tok)
                    live_data = {
                        "indices": fi2.result(),
                        "vix":     fv2.result(),
                    }
            if live_data.get("indices",{}).get("success"):
                render_live_ticker(live_data["indices"], live_data.get("vix",{}))
        else:
            # No broker connected — use free NSE data
            with st.spinner("Fetching market data from NSE (free feed)…"):
                from groww_data import get_fii_dii_data as _fii, get_options_chain_groww as _oc
                import concurrent.futures as cfe
                with cfe.ThreadPoolExecutor(max_workers=3) as ex2:
                    fi2  = ex2.submit(get_live_indices_groww, "")
                    fv2  = ex2.submit(get_vix_data_groww, "")
                    ffi2 = ex2.submit(get_fii_dii_data)
                    live_data = {"indices": fi2.result(), "vix": fv2.result(), "fii": ffi2.result()}
                from groww_data import build_market_context_groww as _bmc
                market_ctx = _bmc("")

        agents_to_run = get_agents_for_mode(mode)
        client_ai = anthropic.Anthropic(api_key=api_key)
        user_msg  = build_query_msg(query, mode, market_ctx)

        # Phase 1 — Parallel analysis
        st.markdown('<div class="sec-label">Phase 01 — Individual Agent Analysis</div>',unsafe_allow_html=True)
        prog = st.progress(0, text="Deploying agents…")
        result_store,lock = {},Lock()
        placeholders = {}

        for i in range(0, len(agents_to_run), 2):
            row  = agents_to_run[i:i+2]
            cols = st.columns(2)
            for j,ag in enumerate(row):
                with cols[j]:
                    ph = st.empty()
                    placeholders[ag["id"]] = ph
                    ph.markdown(render_agent_card(ag,"idle","",bool(market_ctx)),unsafe_allow_html=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(run_agent_stream,ag,user_msg,api_key,depth,result_store,lock):ag
                       for ag in agents_to_run}
            done_count = 0
            while done_count < len(agents_to_run):
                time.sleep(0.35)
                with lock: snap = dict(result_store)
                done_count = 0
                for ag in agents_to_run:
                    d = snap.get(ag["id"],{})
                    if d.get("error"):    status = "error"
                    elif d.get("done"):   status = "done"; done_count += 1
                    elif d.get("text"):   status = "thinking"
                    else:                 status = "idle"
                    placeholders[ag["id"]].markdown(
                        render_agent_card(ag,status,d.get("text",""),bool(market_ctx)),
                        unsafe_allow_html=True)
                prog.progress(int(done_count/len(agents_to_run)*40),
                              text=f"Agents analyzing… {done_count}/{len(agents_to_run)}")
            concurrent.futures.wait(futures)

        final = {aid:d["text"] for aid,d in result_store.items() if not d.get("error")}

        # Phase 2 — Debate
        st.markdown('<div class="sec-label">Phase 02 — Cross-Agent Debate</div>',unsafe_allow_html=True)
        prog.progress(45,text="Cross-agent debate…")
        n = len(agents_to_run)
        pairs = [(agents_to_run[i%n],agents_to_run[(i+1)%n]) for i in range(min(3,n-1))]
        debate_store,debate_lock,debate_phs = {},Lock(),{}

        for c,t in pairs:
            ph = st.empty()
            debate_phs[c["id"]] = (ph,c,t)
            ph.markdown(f'<div class="debate-card"><div class="debate-hdr">{c["icon"]} {c["name"]} → {t["icon"]} {t["name"]}</div><div class="debate-body" style="color:#B8C2D8">Preparing…</div></div>',unsafe_allow_html=True)

        def run_debate(c,t):
            msg = f'You are {c["name"]} ({c["legend"]}).\n{t["name"]} said about "{query}":\n"{final.get(t["id"],"")[:450]}..."\nIn 120 words, CHALLENGE or REINFORCE their key claim using your framework. Be direct.'
            cl = anthropic.Anthropic(api_key=api_key); full=""
            try:
                with cl.messages.stream(model="claude-sonnet-4-20250514",max_tokens=400,
                                        system=c["system"],messages=[{"role":"user","content":msg}]) as s:
                    for chunk in s.text_stream:
                        full+=chunk
                        with debate_lock: debate_store[c["id"]]=full
            except Exception as e:
                with debate_lock: debate_store[c["id"]]=f"Error: {e}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            dfuts = {ex.submit(run_debate,c,t):(c,t) for c,t in pairs}
            while not all(f.done() for f in dfuts):
                time.sleep(0.35)
                with debate_lock: ds=dict(debate_store)
                for f,(c,t) in dfuts.items():
                    txt=ds.get(c["id"],""); done_d=f.done()
                    safe=txt.replace("<","&lt;").replace(">","&gt;") if txt else "Formulating…"
                    lbl="✓ Complete" if done_d else "● Debating"
                    col="#1A6B3C" if done_d else "#8B6914"
                    ph,cc,tt=debate_phs[c["id"]]
                    ph.markdown(f'<div class="debate-card"><div class="debate-hdr">{cc["icon"]} {cc["name"]} → {tt["icon"]} {tt["name"]} <span style="color:{col};font-size:10px;">{lbl}</span></div><div class="debate-body">{safe}</div></div>',unsafe_allow_html=True)
                prog.progress(45+int(sum(1 for f in dfuts if f.done())/len(pairs)*30),text="Debate in progress…")
            concurrent.futures.wait(dfuts)

        # Phase 3 — Consensus
        st.markdown('<div class="sec-label">Phase 03 — Consensus Synthesis</div>',unsafe_allow_html=True)
        prog.progress(80,text="Synthesizing…")
        cs_ph = st.empty()
        cs_ph.markdown('<div class="cs-panel" style="color:#B8C2D8;font-size:12px;letter-spacing:2px;">Synthesizing…</div>',unsafe_allow_html=True)

        raw=""
        try:
            with client_ai.messages.stream(model="claude-sonnet-4-20250514",max_tokens=1500,
                                           system=CONSENSUS_CONFIG["system"],
                                           messages=[{"role":"user","content":build_consensus_msg(query,mode,final)}]) as s:
                for chunk in s.text_stream: raw+=chunk
        except Exception as e:
            raw=f'{{"overall_stance":"NEUTRAL","narrative":"Error: {e}"}}'

        prog.progress(95,text="Finalising verdict…")
        try:
            data=json.loads(raw.strip().replace("```json","").replace("```","").strip())
        except Exception:
            data={"overall_stance":"NEUTRAL","narrative":raw}

        cs_ph.markdown(render_cs(data,raw),unsafe_allow_html=True)
        prog.progress(100,text="✓ Complete")

        # Log signal
        trade_id = log_signal(query, mode, data)

        # Telegram Approval Panel
        tg_token  = st.secrets.get("TELEGRAM_BOT_TOKEN","")
        tg_chat   = st.secrets.get("TELEGRAM_CHAT_ID","")
        groww_tok = st.secrets.get("GROWW_API_TOKEN","")
        has_eq    = data.get("equity_trade",{}).get("applicable") and data.get("equity_trade",{}).get("direction","AVOID") != "AVOID"
        has_op    = data.get("options_trade",{}).get("applicable")

        if tg_token and tg_chat and (has_eq or has_op):
            st.markdown('<div class="sec-label">Send to Telegram for Approval</div>',unsafe_allow_html=True)
            st.markdown(f'<div style="background:#EEF1F8;border:1px solid #C5D0E6;border-left:3px solid #1B2A4A;border-radius:2px;padding:16px 18px;margin-bottom:12px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:8px;">TRADE ID: <code style="color:#1B2A4A;">{trade_id}</code></div><div style="font-size:13px;color:#2C4070;line-height:1.8;">A Telegram message with <b>Approve ✅</b> and <b>Reject ❌</b> buttons will be sent to your phone.<br>Approving executes on Groww via OCO (entry + SL + target). <span style="color:#8B1A1A;font-weight:600;">You have 5 minutes to respond.</span></div></div>',unsafe_allow_html=True)
            c1,c2,c3 = st.columns([2,1,1])
            with c2:
                if has_eq: eq_qty = st.number_input("Equity Qty",min_value=1,value=1,step=1,key="eq_qty")
            with c3:
                if has_op: op_qty = st.number_input("Options Lots",min_value=1,value=1,step=1,key="op_qty")
            with c1:
                st.markdown("<br>",unsafe_allow_html=True)
                send_btn = st.button("📱 Send to Telegram",key="send_tg",use_container_width=True)
            if send_btn:
                if has_eq: data["equity_trade"]["quantity"] = int(st.session_state.get("eq_qty",1))
                if has_op: data["options_trade"]["quantity"] = int(st.session_state.get("op_qty",1))
                update_status(trade_id,"SENT_TO_TELEGRAM")
                with st.spinner("⏳ Waiting for your Telegram approval (5 min timeout)…"):
                    result = notify_and_await_approval(
                        consensus=data, groww_token=groww_tok,
                        telegram_token=tg_token, telegram_chat_id=tg_chat,
                        approval_timeout=300, trade_id=trade_id,
                    )
                decision = result.get("decision","timeout")
                if decision == "approved":
                    update_status(trade_id,"EXECUTED",decision="approved",order_id=str(result.get("results",{})))
                    st.success(f"✅ Trade approved and sent to Groww! ID: {trade_id}")
                    for kind,(key) in [("Equity","equity"),("Options","options")]:
                        r = result.get("results",{}).get(key,{})
                        if r.get("success"): st.info(f"{kind}: {r['message']}")
                        elif r: st.error(f"{kind} error: {r.get('message','')}")
                elif decision == "rejected":
                    update_status(trade_id,"REJECTED",decision="rejected")
                    st.warning(f"❌ Trade rejected. No order placed. ID: {trade_id}")
                else:
                    update_status(trade_id,"TIMEOUT",decision="timeout")
                    st.warning(f"⏰ Approval timed out. No order placed. ID: {trade_id}")
        elif tg_token and tg_chat:
            st.info("No actionable trade in this analysis. No Telegram alert sent.")
        else:
            st.markdown('<div style="background:#FBF8F0;border:1px solid #C9A84C44;border-left:3px solid #8B6914;border-radius:2px;padding:12px 16px;font-size:12px;color:#8B6914;margin-top:12px;">⚡ Add TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID and GROWW_API_TOKEN to Streamlit Secrets to enable one-tap phone approval.</div>',unsafe_allow_html=True)

        st.markdown('<div class="disclaimer">FOR EDUCATIONAL PURPOSES ONLY · NOT SEBI-REGISTERED FINANCIAL ADVICE · F&O INVOLVES SUBSTANTIAL RISK · CONSULT A SEBI-REGISTERED ADVISOR</div>',unsafe_allow_html=True)

    elif launch:
        st.warning("Please enter an investment query.")
    else:
        kite_status = "● LIVE DATA ACTIVE" if get_groww_token() else "○ Add GROWW_API_TOKEN to Secrets for live data"
        kite_col    = "#1A6B3C" if get_groww_token() else "#9B9B9B"
        st.markdown(f"""<div class="hero">
          <div class="hero-title">8 Agents Standing By</div>
          <div style="font-size:11px;color:{kite_col};letter-spacing:2px;margin-bottom:12px;">{kite_status}</div>
          <div class="hero-body">
            Quant Oracle · Value Sentinel · Macro Titan · Chart Hawk<br>
            Options Architect · Sector Guru · Risk Guardian · Behavioral Lens<br>
            <span style="color:#B8C2D8;font-size:10px;">
            Try: "HDFC Bank Q4 buy?" · "BankNifty straddle" · "SENSEX at 76000 — breakout?"
            </span>
          </div>
        </div>""",unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DAILY TRADE DESK
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div style="font-size:13px;color:#6B82B0;margin-bottom:16px;">Generates 3 specific trade setups with precise entry, stop-loss, targets, risk-reward and F&O details.</div>',unsafe_allow_html=True)
    c1,c2,c3 = st.columns([2.5,1,0.8])
    with c1:
        trade_q = st.text_input("Stock / Index",placeholder="e.g. RELIANCE · BankNifty · HDFCBANK · Nifty IT",key="trade_query")
    with c2:
        trade_type = st.selectbox("Trade Type",["intraday","swing","positional","fo_options","fo_futures"],
            format_func=lambda x:{"intraday":"Intraday","swing":"Swing (2–5d)","positional":"Positional",
                                  "fo_options":"F&O Options","fo_futures":"F&O Futures"}[x],key="trade_type")
    with c3:
        st.markdown("<br>",unsafe_allow_html=True)
        trade_go = st.button("Generate Trades",key="trade_go",use_container_width=True)

    if trade_go and trade_q.strip():
        client_ai = anthropic.Anthropic(api_key=api_key)
        now = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
        groww_tok_loc = get_groww_token()
        live_ctx = ""

        if True:  # groww data always available
            with st.spinner("Fetching live quote…"):
                sym = trade_q.strip().upper().replace(" ","")
                sq  = get_stock_quote_groww(get_groww_token(), sym)
                if sq.get("success"):
                    vix_d = get_vix_data_groww(get_groww_token())
                    live_ctx = f"""LIVE MARKET DATA FOR {sym}:
LTP: ₹{sq['last_price']:,.2f}  Change: {sq['change_pct']:+.2f}%
O:{sq['open']}  H:{sq['high']}  L:{sq['low']}  PrevClose:{sq['close']}
Volume: {sq['volume']:,}  |  52W H:{sq['52w_high']}  L:{sq['52w_low']}
Bid: ₹{sq['best_bid']:,.2f}  Ask: ₹{sq['best_ask']:,.2f}
India VIX: {vix_d.get('vix',0):.2f} ({vix_d.get('regime','')}) as of {now}"""

        trade_prompt = f"""Generate 3 specific trade setups for: "{trade_q}"
Trade type: {trade_type.upper()} | Time: {now}
SENSEX ≈ 73,000–80,000 | NIFTY 50 ≈ 22,000–25,000 | BANKNIFTY ≈ 48,000–52,000
{live_ctx}

Respond ONLY as a JSON array (no markdown):
[{{"setup_name":"<n>","instrument":"<exact>","direction":"LONG"|"SHORT",
"entry_range":"<INR range>","stop_loss":"<level + reason>",
"target_1":"<conservative>","target_2":"<primary>","target_3":"<stretch>",
"risk_reward":"<e.g. 1:2.5>","position_size":"<% capital>",
"setup_probability":"HIGH"|"MEDIUM"|"LOW","time_validity":"<e.g. Today>",
"entry_logic":"<2-3 sentences>","invalidation":"<exact condition>",
"key_risks":["r1","r2","r3"],
"fo_details":{{"strike":"","expiry":"","premium_range":"","max_loss":"","margin_estimate":""}}}}]"""

        st.markdown('<div class="sec-label">Trade Setups</div>',unsafe_allow_html=True)
        if live_ctx:
            st.markdown('<div style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;background:#EBF5F0;border:1px solid #A8D4BC;border-radius:2px;font-size:10px;font-weight:700;color:#1A6B3C;margin-bottom:10px;">📡 Generated using live Zerodha price data</div>',unsafe_allow_html=True)

        with st.spinner("Generating trade setups…"):
            raw_t=""
            try:
                with client_ai.messages.stream(model="claude-sonnet-4-20250514",max_tokens=2000,
                                               system=TRADE_ADVISOR_CONFIG["system"],
                                               messages=[{"role":"user","content":trade_prompt}]) as s:
                    for chunk in s.text_stream: raw_t+=chunk
            except Exception as e:
                st.error(f"Error: {e}"); st.stop()

        try:
            trades=json.loads(raw_t.strip().replace("```json","").replace("```","").strip())
        except Exception:
            st.error("Could not parse trade data."); st.code(raw_t); st.stop()

        def mbox(label,val,color,bg):
            return (f'<div style="background:{bg};border:1px solid {color}33;border-top:2px solid {color};'
                    f'border-radius:2px;padding:12px;text-align:center;">'
                    f'<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">{label}</div>'
                    f'<div style="font-family:\'EB Garamond\',serif;font-size:19px;font-weight:600;color:{color};">{val}</div></div>')

        for i,t in enumerate(trades):
            is_long  = t.get("direction")=="LONG"
            dc,db    = ("#1A6B3C","#EBF5F0") if is_long else ("#8B1A1A","#FAECEC")
            prob     = t.get("setup_probability","MEDIUM")
            pc,pb    = {"HIGH":("#1A6B3C","#EBF5F0"),"MEDIUM":("#8B6914","#FBF8F0"),"LOW":("#8B1A1A","#FAECEC")}.get(prob,("#8B6914","#FBF8F0"))
            fo       = t.get("fo_details",{})

            with st.expander(f"{'▲' if is_long else '▼'}  Setup {i+1}: {t.get('setup_name','')} — {t.get('instrument','')}",expanded=True):
                r1,r2,r3,r4,r5=st.columns(5)
                with r1: st.markdown(mbox("Direction",t.get("direction","—"),dc,db),unsafe_allow_html=True)
                with r2: st.markdown(mbox("Entry Range",t.get("entry_range","—"),"#1B2A4A","#EEF1F8"),unsafe_allow_html=True)
                with r3: st.markdown(mbox("Stop Loss",t.get("stop_loss","—"),"#8B1A1A","#FAECEC"),unsafe_allow_html=True)
                with r4: st.markdown(mbox("Risk:Reward",t.get("risk_reward","—"),"#8B6914","#FBF8F0"),unsafe_allow_html=True)
                with r5: st.markdown(mbox("Probability",prob,pc,pb),unsafe_allow_html=True)
                st.markdown("<br>",unsafe_allow_html=True)
                ct1,ct2=st.columns(2)
                with ct1:
                    st.markdown(f'<div class="cs-block" style="border-left:3px solid #1A6B3C"><div class="cs-block-label">Targets</div><div style="font-size:13px;color:#1A6B3C;">T1: {t.get("target_1","—")}</div><div style="font-size:13px;color:#8B6914;">T2: {t.get("target_2","—")}</div><div style="font-size:13px;color:#6B82B0;">T3: {t.get("target_3","—")}</div></div>',unsafe_allow_html=True)
                with ct2:
                    st.markdown(f'<div class="cs-block" style="border-left:3px solid #1B2A4A"><div class="cs-block-label">Parameters</div><div style="font-size:12px;color:#2C4070;line-height:1.9;">Size: <b>{t.get("position_size","—")}</b><br>Valid: <b>{t.get("time_validity","—")}</b><br>Invalidated if: <span style="color:#8B1A1A;">{t.get("invalidation","—")}</span></div></div>',unsafe_allow_html=True)
                if t.get("entry_logic"):
                    st.markdown(f'<div class="cs-block" style="margin-top:10px;border-left:3px solid #C5D0E6"><div class="cs-block-label">Rationale</div><div style="font-size:13px;color:#2C4070;line-height:1.75;">{t["entry_logic"]}</div></div>',unsafe_allow_html=True)
                risks=t.get("key_risks",[])
                if risks:
                    st.markdown("<div style='margin-top:8px;font-size:11px;padding:8px 12px;background:#FAECEC;border-radius:2px;'>"+" · ".join([f'<span style="color:#8B1A1A;">⚠ {r}</span>' for r in risks])+"</div>",unsafe_allow_html=True)
                if fo.get("strike"):
                    st.markdown(f'<div class="cs-block" style="margin-top:10px;border-left:3px solid #C9A84C"><div class="cs-block-label">F&O Details</div><div style="font-size:12px;color:#2C4070;line-height:1.9;">Strike/Expiry: <b style="color:#8B6914;">{fo.get("strike","—")} / {fo.get("expiry","—")}</b><br>Premium: <b>{fo.get("premium_range","—")}</b> | Max Loss: <span style="color:#8B1A1A;">{fo.get("max_loss","—")}</span> | Margin: {fo.get("margin_estimate","—")}</div></div>',unsafe_allow_html=True)

        st.markdown('<div class="disclaimer">TRADE IDEAS FOR EDUCATIONAL PURPOSES ONLY · NOT SEBI-REGISTERED · ALWAYS USE STOP LOSSES</div>',unsafe_allow_html=True)
    elif trade_go:
        st.warning("Please enter a stock or index name.")
    else:
        st.markdown('<div class="hero"><div class="hero-title">Daily Trade Desk</div><div class="hero-body">3 specific setups with entry · stop-loss · targets · F&O details<br><span style="color:#B8C2D8;font-size:10px;">Try: RELIANCE · BankNifty · HDFCBANK · Nifty IT</span></div></div>',unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MARKET ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div style="font-size:13px;color:#6B82B0;margin-bottom:16px;">Live analytics: market breadth, OI, VIX, sector rotation, FII/DII flows, options chain.</div>',unsafe_allow_html=True)

    groww_tok3 = get_groww_token()

    # Show live analytics dashboard
    if True:  # Always show, uses Groww or free NSE data
        st.markdown('<div class="sec-label">Live Market Dashboard</div>',unsafe_allow_html=True)
        if st.button("🔄 Refresh Live Data", key="refresh_analytics"):
            st.session_state.pop("live_analytics_cache",None)

        if "live_analytics_cache" not in st.session_state:
            with st.spinner("Fetching live data…"):
                import concurrent.futures as _cfe
                from groww_data import get_live_indices_groww as _gi, get_vix_data_groww as _gv, get_options_chain_groww as _go
                with _cfe.ThreadPoolExecutor(max_workers=4) as _ex:
                    _fi = _ex.submit(_gi, groww_tok3)
                    _fv = _ex.submit(_gv, groww_tok3)
                    _fo = _ex.submit(_go, groww_tok3, "NIFTY")
                    _ff = _ex.submit(get_fii_dii_data)
                    ld = {"indices":_fi.result(),"vix":_fv.result(),"options":_fo.result(),"fii":_ff.result()}
                st.session_state["live_analytics_cache"] = ld
        ld = st.session_state["live_analytics_cache"]

        # Ticker
        if ld.get("indices",{}).get("success"):
            render_live_ticker(ld["indices"], ld.get("vix",{}))

        # Index grid
        idx = ld.get("indices",{}).get("data",{})
        if idx:
            cols = st.columns(4)
            for i,name in enumerate(["NIFTY 50","SENSEX","BANKNIFTY","INDIA VIX"]):
                d = idx.get(name,{})
                if not d: continue
                is_up = d.get("change",0) >= 0
                col_c = "#1A6B3C" if is_up else "#8B1A1A"
                col_b = "#EBF5F0" if is_up else "#FAECEC"
                with cols[i]:
                    st.markdown(f'<div style="background:{col_b};border:1px solid {col_c}33;border-top:2px solid {col_c};border-radius:2px;padding:14px;text-align:center;margin-bottom:12px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">{name}</div><div style="font-family:\'EB Garamond\',serif;font-size:22px;font-weight:600;color:{col_c};">{d["last_price"]:,.2f}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:{col_c};">{"▲" if is_up else "▼"}{abs(d["change"]):.2f} ({abs(d["change_pct"]):.2f}%)</div><div style="font-size:10px;color:#9B9B9B;margin-top:3px;">O:{d["open"]:,.0f} H:{d["high"]:,.0f} L:{d["low"]:,.0f}</div></div>',unsafe_allow_html=True)

        # Options chain & VIX
        oc = ld.get("options",{})
        vd = ld.get("vix",{})
        if oc.get("success") or vd.get("success"):
            oc1,oc2 = st.columns(2)
            if oc.get("success"):
                with oc1:
                    pcr_col = "#1A6B3C" if oc["pcr"]>1.2 else "#8B1A1A" if oc["pcr"]<0.8 else "#8B6914"
                    st.markdown(f'<div class="cs-panel"><div style="font-family:\'EB Garamond\',serif;font-size:16px;color:#1B2A4A;margin-bottom:14px;">Options Chain — {oc["underlying"]} ({oc["expiry"]})</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;"><div class="cs-kpi"><div class="cs-kpi-label">PCR</div><div class="cs-kpi-val" style="color:{pcr_col};">{oc["pcr"]}</div></div><div class="cs-kpi"><div class="cs-kpi-label">Sentiment</div><div class="cs-kpi-val" style="font-size:15px;color:{pcr_col};">{oc["sentiment"]}</div></div><div class="cs-kpi"><div class="cs-kpi-label">ATM Strike</div><div class="cs-kpi-val cv-navy">{oc["atm_strike"]:,}</div></div><div class="cs-kpi"><div class="cs-kpi-label">Spot Price</div><div class="cs-kpi-val cv-navy">{oc["spot_price"]:,.2f}</div></div></div><div style="margin-top:12px;font-size:12px;color:#2C4070;line-height:2.2;"><b style="color:#8B1A1A;">CE Wall (Resistance):</b> {oc["ce_resistance"]:,}<br><b style="color:#1A6B3C;">PE Wall (Support):</b> {oc["pe_support"]:,}<br><b style="color:#8B6914;">Max Pain:</b> {oc["max_pain"]:,}<br><b style="color:#1B2A4A;">Gamma Wall:</b> {oc["gamma_wall"]:,}</div></div>',unsafe_allow_html=True)
            if vd.get("success"):
                vc = {"RED":"#8B1A1A","AMBER":"#8B6914","GREEN":"#1A6B3C"}.get(vd["color"],"#8B6914")
                vb = {"RED":"#FAECEC","AMBER":"#FBF8F0","GREEN":"#EBF5F0"}.get(vd["color"],"#FBF8F0")
                with oc2:
                    st.markdown(f'<div class="cs-panel" style="height:100%;"><div style="font-family:\'EB Garamond\',serif;font-size:16px;color:#1B2A4A;margin-bottom:14px;">India VIX</div><div style="background:{vb};border:1px solid {vc}33;border-radius:2px;padding:20px;text-align:center;"><div style="font-family:\'EB Garamond\',serif;font-size:48px;font-weight:600;color:{vc};">{vd["vix"]:.2f}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:12px;color:{vc};margin:4px 0;">{"▲" if vd["change"]>=0 else "▼"}{abs(vd["change"]):.2f} ({abs(vd["change_pct"]):.2f}%)</div><div style="font-size:13px;font-weight:700;color:{vc};margin:8px 0;">{vd["regime"]}</div><div style="font-size:12px;color:#6B82B0;">{vd["regime_note"]}</div></div></div>',unsafe_allow_html=True)

        # FII/DII flows
        fd = ld.get("fii",{})
        if fd.get("success"):
            st.markdown('<div class="sec-label">FII / DII Flows (NSE Provisional)</div>',unsafe_allow_html=True)
            f1,f2,f3,f4 = st.columns(4)
            def flow_box(label,val,ts=None):
                color = "#1A6B3C" if val>=0 else "#8B1A1A"
                bg    = "#EBF5F0" if val>=0 else "#FAECEC"
                sign  = "+" if val>=0 else ""
                sub   = f'<div style="font-size:10px;color:#9B9B9B;margin-top:3px;">{ts}</div>' if ts else ""
                return f'<div style="background:{bg};border:1px solid {color}33;border-top:2px solid {color};border-radius:2px;padding:14px;text-align:center;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">{label}</div><div style="font-family:\'EB Garamond\',serif;font-size:18px;font-weight:600;color:{color};">{sign}₹{abs(val):,.0f} Cr</div>{sub}</div>'
            with f1: st.markdown(flow_box("FII Today",fd["fii_net_today"],fd.get("timestamp","")),unsafe_allow_html=True)
            with f2: st.markdown(flow_box("DII Today",fd["dii_net_today"]),unsafe_allow_html=True)
            with f3: st.markdown(flow_box("FII 5-Day",fd["fii_5d_net"]),unsafe_allow_html=True)
            with f4: st.markdown(flow_box("Combined Today",fd["net_flow"]),unsafe_allow_html=True)

        # Top movers
        with st.spinner("Fetching top movers…"):
            movers = get_top_movers_nse()
        if movers.get("success"):
            st.markdown('<div class="sec-label">Top Movers — Nifty 50</div>',unsafe_allow_html=True)
            m1,m2 = st.columns(2)
            with m1:
                st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#1A6B3C;margin-bottom:8px;">TOP GAINERS</div>',unsafe_allow_html=True)
                for s in movers["gainers"]:
                    st.markdown(f'<div style="display:flex;justify-content:space-between;padding:8px 12px;background:#EBF5F0;border-radius:2px;margin-bottom:4px;"><span style="font-weight:600;color:#1B2A4A;">{s["symbol"]}</span><span style="font-family:\'JetBrains Mono\',monospace;font-size:12px;color:#1A6B3C;">▲ {s["change_pct"]:.2f}%</span></div>',unsafe_allow_html=True)
            with m2:
                st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#8B1A1A;margin-bottom:8px;">TOP LOSERS</div>',unsafe_allow_html=True)
                for s in movers["losers"]:
                    st.markdown(f'<div style="display:flex;justify-content:space-between;padding:8px 12px;background:#FAECEC;border-radius:2px;margin-bottom:4px;"><span style="font-weight:600;color:#1B2A4A;">{s["symbol"]}</span><span style="font-family:\'JetBrains Mono\',monospace;font-size:12px;color:#8B1A1A;">▼ {abs(s["change_pct"]):.2f}%</span></div>',unsafe_allow_html=True)

        st.markdown("---")

    # AI-powered deep analytics (always available)
    st.markdown('<div class="sec-label">AI-Powered Deep Analytics</div>',unsafe_allow_html=True)
    ac1,ac2,ac3 = st.columns([2,1,0.8])
    with ac1:
        analytics_q = st.text_input("Analytics Query",placeholder="e.g. Nifty market breadth · BankNifty OI · India VIX · FII positioning",key="analytics_query")
    with ac2:
        analytics_focus = st.selectbox("Focus Area",
            ["market_breadth","fo_oi","sector_rotation","volatility","fii_flows","options_chain"],
            format_func=lambda x:{"market_breadth":"Market Breadth","fo_oi":"F&O Open Interest",
                                  "sector_rotation":"Sector Rotation","volatility":"VIX & Volatility",
                                  "fii_flows":"FII / DII Flows","options_chain":"Options Chain"}[x],key="analytics_focus")
    with ac3:
        st.markdown("<br>",unsafe_allow_html=True)
        analytics_go = st.button("Run Analytics",key="analytics_go",use_container_width=True)

    if analytics_go and analytics_q.strip():
        client_ai = anthropic.Anthropic(api_key=api_key)
        now = datetime.now(IST).strftime("%d %b %Y")
        focus_ctx = {"market_breadth":"Advance/decline ratios, 52W highs/lows, breadth thrust, cumulative divergences.",
                     "fo_oi":"OI buildup/unwinding, long/short changes, cost of carry, rollover, futures premium.",
                     "sector_rotation":"Relative sector performance, rotation signals, sector PE vs historical mean.",
                     "volatility":"India VIX levels (low<13/medium 13-20/high>20), realized vs implied, event premium.",
                     "fii_flows":"FII net equity flows, DII counterflow, FII derivatives positioning.",
                     "options_chain":"Max pain, PCR, gamma walls, OI at key strikes, IV skew, unusual activity."}[analytics_focus]

        live_inject = ""
        if "live_analytics_cache" in st.session_state:
            ld2 = st.session_state["live_analytics_cache"]
            live_inject = build_market_context(ld2.get("indices",{}),ld2.get("vix",{}),ld2.get("options",{}),ld2.get("fii",{}))

        prompt = f"""ANALYTICS: "{analytics_q}"
FOCUS: {analytics_focus.replace("_"," ").upper()} | DATE: {now}
SENSEX ≈ 73,000-80,000 | NIFTY 50 ≈ 22,000-25,000 | BANKNIFTY ≈ 48,000-52,000
{live_inject}
{focus_ctx}

Respond ONLY in valid JSON (no markdown):
{{"title":"<t>","headline":"<h>","regime":"<r>","regime_color":"BULLISH"|"BEARISH"|"NEUTRAL"|"CAUTION",
"key_metrics":[{{"label":"<l>","value":"<v>","signal":"POSITIVE"|"NEGATIVE"|"NEUTRAL","note":"<n>"}}],
"sections":[{{"title":"<t>","content":"<p>","bullets":["b1","b2","b3"]}}],
"actionable_signals":[{{"signal":"<s>","implication":"<i>","urgency":"HIGH"|"MEDIUM"|"LOW"}}],
"risks_to_watch":["r1","r2","r3","r4"],
"summary":"<3-sentence executive summary>"}}"""

        with st.spinner("Generating analytics…"):
            raw_a=""
            try:
                with client_ai.messages.stream(model="claude-sonnet-4-20250514",max_tokens=2000,
                                               system=ANALYTICS_CONFIG["system"],
                                               messages=[{"role":"user","content":prompt}]) as s:
                    for chunk in s.text_stream: raw_a+=chunk
            except Exception as e:
                st.error(f"Error: {e}"); st.stop()

        try:
            rpt=json.loads(raw_a.strip().replace("```json","").replace("```","").strip())
        except Exception:
            st.error("Could not parse."); st.code(raw_a); st.stop()

        rc_m={"BULLISH":"#1A6B3C","BEARISH":"#8B1A1A","NEUTRAL":"#1B2A4A","CAUTION":"#8B6914"}
        rb_m={"BULLISH":"#EBF5F0","BEARISH":"#FAECEC","NEUTRAL":"#EEF1F8","CAUTION":"#FBF8F0"}
        rc=rc_m.get(rpt.get("regime_color","NEUTRAL"),"#1B2A4A")
        rb=rb_m.get(rpt.get("regime_color","NEUTRAL"),"#EEF1F8")

        st.markdown(f'<div class="cs-panel" style="margin-bottom:16px;"><div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;"><div><div style="font-family:\'EB Garamond\',serif;font-size:22px;color:#1B2A4A;margin-bottom:4px;">{rpt.get("title","")}</div><div style="font-size:13px;color:#6B82B0;">{rpt.get("headline","")}</div></div><div style="text-align:center;background:{rb};border:1px solid {rc}44;border-radius:2px;padding:10px 18px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{rc}99;margin-bottom:3px;">Regime</div><div style="font-family:\'EB Garamond\',serif;font-size:18px;font-weight:600;color:{rc};">{rpt.get("regime","—")}</div></div></div></div>',unsafe_allow_html=True)

        metrics=rpt.get("key_metrics",[])
        if metrics:
            st.markdown('<div class="sec-label">Key Metrics</div>',unsafe_allow_html=True)
            cols=st.columns(min(len(metrics),4))
            for i,m in enumerate(metrics[:8]):
                sc2,sbg={"POSITIVE":("#1A6B3C","#EBF5F0"),"NEGATIVE":("#8B1A1A","#FAECEC")}.get(m.get("signal",""),("#1B2A4A","#EEF1F8"))
                with cols[i%4]:
                    st.markdown(f'<div style="background:{sbg};border:1px solid {sc2}33;border-top:2px solid {sc2};border-radius:2px;padding:12px;margin-bottom:10px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:4px;">{m.get("label","")}</div><div style="font-family:\'EB Garamond\',serif;font-size:20px;font-weight:600;color:{sc2};margin-bottom:2px;">{m.get("value","—")}</div><div style="font-size:11px;color:#9B9B9B;">{m.get("note","")}</div></div>',unsafe_allow_html=True)

        for sec in rpt.get("sections",[]):
            with st.expander(sec.get("title","Section"),expanded=True):
                if sec.get("content"): st.markdown(f'<div style="font-size:13.5px;color:#2C4070;line-height:1.85;margin-bottom:10px;">{sec["content"]}</div>',unsafe_allow_html=True)
                for b in sec.get("bullets",[]): st.markdown(f'<div style="font-size:12.5px;color:#6B82B0;padding-left:14px;margin-bottom:3px;">▸ {b}</div>',unsafe_allow_html=True)

        for sig in rpt.get("actionable_signals",[]):
            urg=sig.get("urgency","MEDIUM")
            uc,ub={"HIGH":("#8B1A1A","#FAECEC"),"MEDIUM":("#8B6914","#FBF8F0"),"LOW":("#1A6B3C","#EBF5F0")}.get(urg,("#1B2A4A","#EEF1F8"))
            st.markdown(f'<div style="background:{ub};border:1px solid {uc}33;border-left:3px solid {uc};border-radius:2px;padding:12px 16px;margin-bottom:8px;"><div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:{uc};margin-bottom:3px;">{urg} PRIORITY</div><div style="font-size:13px;color:#1B2A4A;font-weight:600;margin-bottom:2px;">{sig.get("signal","")}</div><div style="font-size:12px;color:#6B82B0;">{sig.get("implication","")}</div></div>',unsafe_allow_html=True)

        risks=rpt.get("risks_to_watch",[])
        if risks:
            st.markdown("<div style='padding:10px 14px;background:#FAECEC;border:1px solid #F0BABA;border-radius:2px;font-size:11px;margin-top:8px;'>"+" · ".join([f'<span style="color:#8B1A1A;">⚠ {r}</span>' for r in risks])+"</div>",unsafe_allow_html=True)

        if rpt.get("summary"):
            st.markdown(f'<div style="background:#EEF1F8;border:1px solid #1B2A4A33;border-left:3px solid #1B2A4A;border-radius:2px;padding:16px 18px;margin-top:14px;"><div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#6B82B0;margin-bottom:8px;">Executive Summary</div><div style="font-family:\'EB Garamond\',serif;font-size:15px;line-height:1.9;color:#1B2A4A;">{rpt["summary"]}</div></div>',unsafe_allow_html=True)

        st.markdown('<div class="disclaimer">FOR EDUCATIONAL PURPOSES ONLY · NOT SEBI-REGISTERED · VERIFY DATA FROM NSE · BSE · SEBI</div>',unsafe_allow_html=True)

    elif analytics_go:
        st.warning("Please enter an analytics query.")
    elif not get_groww_token():
        st.markdown('<div class="hero"><div class="hero-title">Market Analytics Engine</div><div class="hero-body">Connect Zerodha Kite in the sidebar for a live dashboard<br>or use the AI analytics query below without connection<br><span style="color:#B8C2D8;font-size:10px;">Try: "Nifty OI analysis" · "India VIX regime" · "BankNifty options chain"</span></div></div>',unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — TRADE JOURNAL
# ═══════════════════════════════════════════════════════════════════════════════
# NOTE: Add "▪  Trade Journal" to the st.tabs() call above to enable this tab.
# For now it renders as a standalone section below all tabs.

st.markdown("---")
st.markdown('<div class="sec-label">Trade Journal & Audit Trail</div>', unsafe_allow_html=True)

summary = get_summary()
j1,j2,j3,j4,j5 = st.columns(5)
def jbox(label,val,color="#1B2A4A"):
    return (f'<div style="background:#EEF1F8;border:1px solid #C5D0E6;border-top:2px solid {color};'
            f'border-radius:2px;padding:12px;text-align:center;">'
            f'<div style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;'
            f'color:#6B82B0;margin-bottom:4px;">{label}</div>'
            f'<div style="font-family:\'EB Garamond\',serif;font-size:22px;font-weight:600;color:{color};">{val}</div></div>')

with j1: st.markdown(jbox("Total Signals", summary["total_signals"]), unsafe_allow_html=True)
with j2: st.markdown(jbox("Executed", summary["executed"], "#1A6B3C"), unsafe_allow_html=True)
with j3: st.markdown(jbox("Rejected", summary["rejected"], "#8B1A1A"), unsafe_allow_html=True)
with j4: st.markdown(jbox("Win Rate", f"{summary['win_rate']}%", "#8B6914"), unsafe_allow_html=True)
with j5:
    pnl_color = "#1A6B3C" if summary["total_pnl"] >= 0 else "#8B1A1A"
    st.markdown(jbox("Total P&L", f"₹{summary['total_pnl']:,.0f}", pnl_color), unsafe_allow_html=True)

all_trades = get_all()
if all_trades:
    st.markdown("<br>", unsafe_allow_html=True)
    for t in reversed(all_trades[-20:]):  # Show last 20
        status = t.get("status","—")
        sc = {"EXECUTED":"#1A6B3C","REJECTED":"#8B1A1A","TIMEOUT":"#8B6914",
              "PENDING_APPROVAL":"#1B2A4A","SENT_TO_TELEGRAM":"#8B6914"}.get(status,"#6B82B0")
        pnl_str = f"₹{t['pnl']:,.0f}" if t.get("pnl") is not None else "—"
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:10px 14px;background:#F8F9FC;border:1px solid #DCE1EC;border-left:3px solid {sc};'
            f'border-radius:2px;margin-bottom:6px;flex-wrap:wrap;gap:8px;">'
            f'<div><span style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#1B2A4A;font-weight:700;">'
            f'{t["trade_id"]}</span>&nbsp;&nbsp;'
            f'<span style="font-size:12px;color:#2C4070;">{t.get("query","—")[:50]}</span></div>'
            f'<div style="display:flex;gap:12px;align-items:center;">'
            f'<span style="font-size:11px;color:{sc};font-weight:700;">{status}</span>'
            f'<span style="font-size:11px;color:#6B82B0;">{t["timestamp"][:16].replace("T"," ")}</span>'
            f'<span style="font-size:11px;color:{"#1A6B3C" if pnl_str!="—" and float(t.get("pnl",0))>=0 else "#8B1A1A" if pnl_str!="—" else "#9B9B9B"};">'
            f'P&L: {pnl_str}</span>'
            f'</div></div>',
            unsafe_allow_html=True
        )
else:
    st.markdown('<div style="text-align:center;padding:24px;color:#B8C2D8;font-size:12px;letter-spacing:2px;">No trades logged yet. Run an analysis to generate your first signal.</div>',
                unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — AUTO SCANNER
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div style="font-size:13px;color:#6B82B0;margin-bottom:16px;">Autonomous market scanner — watches all Nifty 50 stocks and F&O during market hours. Sends high-conviction signals to your phone automatically. No query needed.</div>', unsafe_allow_html=True)

    tg_token_sc  = st.secrets.get("TELEGRAM_BOT_TOKEN","")
    tg_chat_sc   = st.secrets.get("TELEGRAM_CHAT_ID","")
    groww_tok_sc = st.secrets.get("GROWW_API_TOKEN","")

    if not tg_token_sc or not tg_chat_sc:
        st.warning("Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to Streamlit Secrets to enable the scanner.")
    else:
        pass  # groww used directly
        scanner = get_scanner(
            api_key=api_key,
            telegram_token=tg_token_sc,
            telegram_chat_id=tg_chat_sc,
            groww_token=groww_tok_sc,
        )

        # Status display
        is_running = scanner.is_running()
        status_col = "#1A6B3C" if is_running else "#8B1A1A"
        status_bg  = "#EBF5F0" if is_running else "#FAECEC"
        status_dot = "●" if is_running else "○"

        st.markdown(f"""
        <div style="background:{status_bg};border:1px solid {status_col}33;
        border-left:3px solid {status_col};border-radius:2px;
        padding:14px 18px;margin-bottom:16px;display:flex;
        justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
          <div>
            <div style="font-size:10px;font-weight:700;letter-spacing:2px;
            text-transform:uppercase;color:{status_col};margin-bottom:4px;">
            {status_dot} SCANNER STATUS</div>
            <div style="font-size:15px;font-weight:600;color:#1B2A4A;">
            {scanner.status}</div>
            {'<div style="font-size:12px;color:#6B82B0;margin-top:3px;">Currently scanning: <b>' + scanner.current_symbol + '</b></div>' if scanner.current_symbol else ''}
          </div>
          <div style="text-align:right;">
            <div style="font-size:12px;color:#6B82B0;">Signals sent today: <b style="color:#1B2A4A;">{scanner.signals_sent}</b></div>
            {'<div style="font-size:12px;color:#6B82B0;">Last scan: <b style="color:#1B2A4A;">' + (scanner.last_scan or "—") + '</b></div>' if scanner.last_scan else ''}
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Scanner settings
        st.markdown('<div class="sec-label">Scanner Settings</div>', unsafe_allow_html=True)
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown(f'<div class="cs-block"><div class="cs-block-label">Watchlist</div><div style="font-size:13px;color:#1B2A4A;">20 Nifty 50 stocks<br>NIFTY + BANKNIFTY F&O</div></div>', unsafe_allow_html=True)
        with sc2:
            st.markdown(f'<div class="cs-block"><div class="cs-block-label">Scan Frequency</div><div style="font-size:13px;color:#1B2A4A;">Every 15 minutes<br>09:15 – 15:25 IST</div></div>', unsafe_allow_html=True)
        with sc3:
            st.markdown(f'<div class="cs-block"><div class="cs-block-label">Signal Threshold</div><div style="font-size:13px;color:#1B2A4A;">HIGH conviction only<br>60%+ agent agreement</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Start / Stop buttons
        b1, b2, b3 = st.columns([1, 1, 2])
        with b1:
            if not is_running:
                if st.button("▶ START SCANNER", key="scanner_start", use_container_width=True):
                    scanner.start()
                    st.success("✅ Scanner started! You'll receive signals on Telegram.")
                    st.rerun()
            else:
                if st.button("⏹ STOP SCANNER", key="scanner_stop", use_container_width=True):
                    scanner.stop()
                    st.warning("Scanner stopped.")
                    st.rerun()
        with b2:
            if st.button("🔄 Refresh Status", key="scanner_refresh", use_container_width=True):
                st.rerun()

        # How it works
        st.markdown('<div class="sec-label">How It Works</div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;">
          <div class="cs-block" style="border-left:3px solid #1B2A4A;">
            <div class="cs-block-label">1. Market Opens</div>
            <div style="font-size:12px;color:#2C4070;line-height:1.7;">Scanner activates at 9:15 AM IST automatically</div>
          </div>
          <div class="cs-block" style="border-left:3px solid #8B6914;">
            <div class="cs-block-label">2. Live Data Fetch</div>
            <div style="font-size:12px;color:#2C4070;line-height:1.7;">Pulls live prices, OI, VIX, FII flows from Kite/Groww</div>
          </div>
          <div class="cs-block" style="border-left:3px solid #1B2A4A;">
            <div class="cs-block-label">3. Agent Analysis</div>
            <div style="font-size:12px;color:#2C4070;line-height:1.7;">4 agents scan each stock simultaneously using live data</div>
          </div>
          <div class="cs-block" style="border-left:3px solid #8B6914;">
            <div class="cs-block-label">4. Conviction Filter</div>
            <div style="font-size:12px;color:#2C4070;line-height:1.7;">Only HIGH conviction + 60% agent agreement passes</div>
          </div>
          <div class="cs-block" style="border-left:3px solid #1A6B3C;">
            <div class="cs-block-label">5. Telegram Alert</div>
            <div style="font-size:12px;color:#2C4070;line-height:1.7;">Signal sent to your phone with exact entry, SL, targets</div>
          </div>
          <div class="cs-block" style="border-left:3px solid #1A6B3C;">
            <div class="cs-block-label">6. One-Tap Execute</div>
            <div style="font-size:12px;color:#2C4070;line-height:1.7;">Tap Approve → Groww places OCO order automatically</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Recent scan log
        if scanner.scan_log:
            st.markdown('<div class="sec-label">Recent Signals Found</div>', unsafe_allow_html=True)
            for log in reversed(scanner.scan_log[-10:]):
                dir_col = "#1A6B3C" if log.get("direction")=="LONG" else "#8B1A1A"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:8px 14px;'
                    f'background:#F8F9FC;border:1px solid #DCE1EC;border-left:3px solid {dir_col};'
                    f'border-radius:2px;margin-bottom:4px;flex-wrap:wrap;gap:8px;">'
                    f'<span style="font-weight:700;color:#1B2A4A;">{log.get("symbol","")}</span>'
                    f'<span style="color:{dir_col};font-weight:700;">{log.get("direction","")}</span>'
                    f'<span style="color:#6B82B0;font-size:11px;">{log.get("agreement","")}% agreement</span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#9B9B9B;">{log.get("trade_id","")}</span>'
                    f'<span style="color:#9B9B9B;font-size:11px;">{log.get("time","")}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        st.markdown('<div class="disclaimer">AUTONOMOUS SIGNALS ARE FOR EDUCATIONAL PURPOSES ONLY · NOT SEBI-REGISTERED · ALWAYS VERIFY BEFORE EXECUTING · F&O INVOLVES SUBSTANTIAL RISK</div>', unsafe_allow_html=True)
