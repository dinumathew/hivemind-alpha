"""
HIVE MIND ALPHA — Multi-Agent SENSEX Investment Intelligence System
A Streamlit web application that simulates legendary investor frameworks
analyzing Indian equity and F&O markets through AI agents.

Run: streamlit run app.py
"""

import streamlit as st
import anthropic
import json
import time
import concurrent.futures
from threading import Lock
from agents import AGENTS, CONSENSUS_CONFIG, get_agents_for_mode

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HIVE MIND ALPHA · SENSEX Intelligence",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Orbitron:wght@700;900&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Rajdhani', sans-serif;
    background-color: #020408;
    color: #c8e0f0;
}
.stApp { background: #020408; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 2rem; max-width: 1400px; }

/* ── Header ── */
.hm-header {
    background: rgba(0,0,0,0.6);
    border: 1px solid #1a3a50;
    border-radius: 6px;
    padding: 20px 28px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}
.hm-header::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, #00d4ff, transparent);
}
.hm-title {
    font-family: 'Orbitron', monospace;
    font-size: 26px; font-weight: 900;
    color: #00d4ff;
    letter-spacing: 6px;
    text-shadow: 0 0 30px rgba(0,212,255,0.5);
    margin: 0;
}
.hm-subtitle {
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px; color: #2a5a7a;
    letter-spacing: 3px; margin-top: 4px;
}

/* ── Input panel ── */
.stTextInput > div > div > input {
    background: #0a1520 !important;
    border: 1px solid #1a3a50 !important;
    border-radius: 4px !important;
    color: #c8e0f0 !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-size: 15px !important;
    padding: 10px 14px !important;
}
.stTextInput > div > div > input:focus {
    border-color: #00d4ff !important;
    box-shadow: 0 0 0 2px rgba(0,212,255,0.15) !important;
}
.stSelectbox > div > div {
    background: #0a1520 !important;
    border: 1px solid #1a3a50 !important;
    border-radius: 4px !important;
    color: #c8e0f0 !important;
}
.stTextInput > label, .stSelectbox > label {
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important;
    letter-spacing: 2px !important;
    color: #5a8aaa !important;
    text-transform: uppercase;
}

/* ── Buttons ── */
.stButton > button {
    background: transparent !important;
    border: 1px solid #00d4ff !important;
    color: #00d4ff !important;
    font-family: 'Orbitron', monospace !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 3px !important;
    border-radius: 4px !important;
    padding: 10px 28px !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: rgba(0,212,255,0.1) !important;
    box-shadow: 0 0 20px rgba(0,212,255,0.3) !important;
}

/* ── Agent cards ── */
.agent-card {
    background: #060d14;
    border: 1px solid #0d2235;
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 14px;
    position: relative;
    transition: border-color 0.3s;
}
.agent-card.streaming { border-color: rgba(0,212,255,0.4); }
.agent-card.done { border-color: #0d2235; }

.agent-header {
    display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
}
.agent-icon-wrap {
    width: 38px; height: 38px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.2);
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    background: rgba(0,0,0,0.3);
    flex-shrink: 0;
}
.agent-name {
    font-family: 'Orbitron', monospace;
    font-size: 11px; font-weight: 700;
    letter-spacing: 2px;
}
.agent-legend {
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px; color: #5a8aaa;
}
.agent-role {
    font-size: 12px; color: #5a8aaa;
    margin-bottom: 10px;
}
.agent-output-box {
    background: #0a1520;
    border: 1px solid #0d2235;
    border-radius: 4px;
    padding: 12px;
    font-size: 13px;
    line-height: 1.7;
    color: #8ab0c8;
    min-height: 60px;
    font-family: 'Rajdhani', sans-serif;
    white-space: pre-wrap;
}

/* ── Section headers ── */
.section-hdr {
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px; letter-spacing: 3px;
    color: #5a8aaa;
    padding: 8px 0;
    border-bottom: 1px solid #0d2235;
    margin: 24px 0 16px;
    display: flex; align-items: center; gap: 10px;
}

/* ── Debate messages ── */
.debate-msg {
    background: #060d14;
    border: 1px solid #0d2235;
    border-left: 3px solid;
    border-radius: 4px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.debate-agent-name {
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px; letter-spacing: 2px;
    margin-bottom: 6px;
}
.debate-text {
    font-size: 13px; line-height: 1.7;
    color: #8ab0c8;
    white-space: pre-wrap;
}

/* ── Consensus panel ── */
.consensus-panel {
    background: #060d14;
    border: 1px solid #1a3a50;
    border-radius: 6px;
    padding: 24px;
    position: relative;
    margin-top: 8px;
}
.consensus-panel::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, #00d4ff, transparent);
}
.verdict-row {
    display: flex; gap: 12px; flex-wrap: wrap;
    margin-bottom: 20px;
}
.verdict-box {
    background: #0a1520;
    border: 1px solid #1a3a50;
    border-radius: 4px;
    padding: 14px 18px;
    min-width: 140px; text-align: center;
    flex: 1;
}
.verdict-label {
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px; letter-spacing: 2px;
    color: #2a5a7a; margin-bottom: 6px;
}
.verdict-val {
    font-family: 'Orbitron', monospace;
    font-size: 20px; font-weight: 700;
}
.v-bullish { color: #00ff88; }
.v-bearish { color: #ff4444; }
.v-neutral { color: #f5c842; }
.v-accent  { color: #00d4ff; }
.v-purple  { color: #a78bfa; }

/* ── Progress ── */
.stProgress > div > div > div { background: #00d4ff !important; }

/* ── Status badge ── */
.status-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 2px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px; letter-spacing: 2px;
    border: 1px solid;
}
.sb-idle    { border-color: #1a3a50; color: #2a5a7a; }
.sb-running { border-color: #00d4ff; color: #00d4ff; background: rgba(0,212,255,0.08); }
.sb-done    { border-color: #00ff88; color: #00ff88; background: rgba(0,255,136,0.08); }
.sb-error   { border-color: #ff4444; color: #ff4444; }

/* ── Divider ── */
hr { border-color: #0d2235 !important; margin: 16px 0 !important; }

/* ── Sidebar ── */
.css-1d391kg, [data-testid="stSidebar"] {
    background: #060d14 !important;
    border-right: 1px solid #1a3a50;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #060d14;
    border-radius: 4px;
    gap: 2px;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important; letter-spacing: 2px !important;
    color: #2a5a7a !important;
    background: transparent !important;
    border-radius: 3px !important;
}
.stTabs [aria-selected="true"] {
    color: #00d4ff !important;
    background: rgba(0,212,255,0.08) !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 11px !important; letter-spacing: 2px !important;
    color: #5a8aaa !important;
    background: #060d14 !important;
    border: 1px solid #0d2235 !important;
    border-radius: 4px !important;
}
.streamlit-expanderContent {
    background: #060d14 !important;
    border: 1px solid #0d2235 !important;
    border-top: none !important;
}

/* ── Disclaimer ── */
.disclaimer {
    text-align: center;
    padding: 14px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px; letter-spacing: 1px;
    color: #2a5a7a; line-height: 2;
    border: 1px solid #0d2235;
    border-radius: 4px;
    margin-top: 20px;
}

/* ── Key input ── */
.stTextInput[data-testid="apiKeyInput"] > div > div > input {
    font-family: 'Share Tech Mono', monospace !important;
    letter-spacing: 2px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hm-header">
  <div class="hm-title">⬡ HIVE MIND ALPHA</div>
  <div class="hm-subtitle">
    MULTI-AGENT SENSEX INTELLIGENCE SYSTEM &nbsp;·&nbsp; 8 LEGENDARY INVESTOR FRAMEWORKS &nbsp;·&nbsp; REAL-TIME AI ANALYSIS
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar — API Key & Settings ─────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="hm-title" style="font-size:14px;letter-spacing:3px;">⬡ SETTINGS</div>', unsafe_allow_html=True)
    st.markdown("---")

    api_key_input = st.text_input(
        "ANTHROPIC API KEY",
        type="password",
        placeholder="sk-ant-...",
        help="Get your key at console.anthropic.com",
        key="apiKeyInput",
    )

    st.markdown("---")
    st.markdown('<div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;color:#2a5a7a;letter-spacing:2px;">AGENT ROSTER</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    for agent in AGENTS:
        st.markdown(
            f'<div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;color:{agent["color"]};'
            f'margin-bottom:6px;">{agent["icon"]} {agent["name"]}<br>'
            f'<span style="color:#2a5a7a;font-size:9px;">{agent["legend"]}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        '<div style="font-family:\'Share Tech Mono\',monospace;font-size:9px;color:#1a3a50;'
        'line-height:1.8;">⚠ FOR EDUCATIONAL PURPOSES ONLY<br>NOT SEBI-REGISTERED ADVICE<br>'
        'F&O INVOLVES SUBSTANTIAL RISK</div>',
        unsafe_allow_html=True,
    )

# ── API Key guard ─────────────────────────────────────────────────────────────
api_key = api_key_input or st.session_state.get("api_key", "") or st.secrets.get("ANTHROPIC_API_KEY", "")
if api_key_input:
    st.session_state["api_key"] = api_key_input

if not api_key:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;">
      <div style="font-size:48px;margin-bottom:16px;">🔐</div>
      <div style="font-family:'Orbitron',monospace;font-size:16px;color:#00d4ff;letter-spacing:4px;margin-bottom:12px;">
        API KEY REQUIRED
      </div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:12px;color:#2a5a7a;letter-spacing:2px;line-height:2;">
        ENTER YOUR ANTHROPIC API KEY IN THE SIDEBAR TO ACTIVATE ALL 8 AGENTS<br>
        GET YOUR KEY AT <span style="color:#00d4ff;">CONSOLE.ANTHROPIC.COM</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Query Input ───────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns([3, 1, 0.6, 0.6])

with col1:
    query = st.text_input(
        "INVESTMENT QUERY",
        placeholder="e.g. HDFC Bank Q4 results — buy the dip?  ·  BankNifty weekly straddle  ·  Nifty at 25000 — top or breakout?",
        key="query",
    )

with col2:
    mode = st.selectbox(
        "MODE",
        options=["equity", "fo", "combined"],
        format_func=lambda x: {"equity": "📊 Equity", "fo": "⚡ F&O Only", "combined": "🔮 Full Spectrum"}[x],
        key="mode",
    )

with col3:
    max_tokens = st.selectbox("DEPTH", options=[600, 1000, 1500],
                              format_func=lambda x: {600: "Quick", 1000: "Deep", 1500: "Ultra"}[x])

with col4:
    st.markdown("<br>", unsafe_allow_html=True)
    launch = st.button("▶ LAUNCH", use_container_width=True)

st.markdown("---")

# ── Agent runner ──────────────────────────────────────────────────────────────

def run_agent_streaming(agent: dict, user_message: str, api_key: str, max_tokens: int,
                        result_store: dict, lock: Lock):
    """Run a single agent with streaming, storing chunks as they arrive."""
    client = anthropic.Anthropic(api_key=api_key)
    full_text = ""
    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=agent["system"],
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text_chunk in stream.text_stream:
                full_text += text_chunk
                with lock:
                    result_store[agent["id"]] = {"text": full_text, "done": False}
        with lock:
            result_store[agent["id"]] = {"text": full_text, "done": True}
    except Exception as e:
        with lock:
            result_store[agent["id"]] = {"text": f"[ERROR] {str(e)}", "done": True, "error": True}
    return agent["id"], full_text


def build_agent_message(query: str, mode: str) -> str:
    from datetime import datetime
    import pytz
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).strftime("%d %b %Y %H:%M IST")
    return f"""INVESTMENT QUERY: "{query}"
MODE: {mode.upper()} ANALYSIS (SENSEX / NSE / BSE)
TIMESTAMP: {now}

Provide your deep expert analysis on this investment query. Stay strictly within your legendary framework.

Structure your response as:
1. KEY SIGNAL / OPPORTUNITY (what stands out to you)
2. CRITICAL RISK FACTOR (what could go wrong from your lens)  
3. SPECIFIC RECOMMENDATION (Bullish / Bearish / Neutral with exact reasoning)
4. ONE CONTRARIAN TAKE (challenge the consensus view)

Be specific, quantitative where possible, and true to your legendary investor persona.
Limit: 250 words. No generic advice."""


def build_debate_message(challenger: dict, target: dict, target_analysis: str, query: str) -> str:
    return f"""You are {challenger["name"]} ({challenger["legend"]}).

The analysis from {target["name"]} ({target["legend"]}) on "{query}" concluded:

"{target_analysis[:500]}..."

In exactly 150 words, directly CHALLENGE or REINFORCE their single most important claim using your own framework.
- If challenging: Name them, cite their exact claim, and explain why your framework contradicts it with evidence.
- If reinforcing: Name them, cite their claim, and add a dimension they missed from your perspective.

Be direct, sharp, and specific. No pleasantries."""


def build_consensus_message(query: str, mode: str, all_analyses: dict) -> str:
    analyses_text = "\n\n".join([
        f"=== {a['name']} ({a['legend']}) ===\n{all_analyses.get(a['id'], 'N/A')[:400]}"
        for a in AGENTS if a["id"] in all_analyses
    ])
    return f"""INVESTMENT QUERY: "{query}"
MODE: {mode.upper()} | SENSEX/NSE/BSE MARKETS

MULTI-AGENT ANALYSIS RESULTS:
{analyses_text}

Synthesize all agent analyses into a final consensus verdict. 

Respond ONLY in valid JSON (no markdown, no backticks):
{{
  "overall_stance": "BULLISH" or "BEARISH" or "NEUTRAL",
  "conviction": "HIGH" or "MEDIUM" or "LOW",
  "time_horizon": "INTRADAY" or "SHORT-TERM (days-weeks)" or "MEDIUM-TERM (1-6 months)" or "LONG-TERM (1+ years)",
  "agent_agreement_pct": <number 0-100>,
  "key_thesis": "<2-sentence core investment thesis>",
  "action": "<specific actionable recommendation>",
  "entry_trigger": "<exact condition to wait for before entering>",
  "stop_loss_logic": "<specific risk management rule>",
  "target": "<price target or % move expected>",
  "bull_case": "<one sentence — what makes this work>",
  "bear_case": "<one sentence — what kills this trade>",
  "agents_bullish": ["agent names"],
  "agents_bearish": ["agent names"],
  "agents_neutral": ["agent names"],
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "narrative": "<3 rich paragraphs: (1) synthesis of where agents agreed, (2) key debates and disagreements, (3) final reasoning and conditions for conviction change>"
}}"""


# ── Main execution flow ────────────────────────────────────────────────────────
if launch and query.strip():

    agents_to_run = get_agents_for_mode(mode)
    client = anthropic.Anthropic(api_key=api_key)

    # ── PHASE 1: Individual Analysis ─────────────────────────────────────────
    st.markdown(
        '<div class="section-hdr">⬡ PHASE 01 — INDIVIDUAL AGENT ANALYSIS</div>',
        unsafe_allow_html=True
    )

    progress_bar = st.progress(0, text="Deploying agents...")
    result_store: dict = {}
    lock = Lock()
    user_message = build_agent_message(query, mode)

    # Create placeholder grid — 2 columns
    num_agents = len(agents_to_run)
    cols_per_row = 2
    placeholders = {}
    card_rows = []

    for i in range(0, num_agents, cols_per_row):
        row_agents = agents_to_run[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, agent in enumerate(row_agents):
            with cols[j]:
                ph = st.empty()
                placeholders[agent["id"]] = ph
                ph.markdown(
                    f'<div class="agent-card">'
                    f'<div class="agent-header">'
                    f'<div class="agent-icon-wrap">{agent["icon"]}</div>'
                    f'<div><div class="agent-name" style="color:{agent["color"]}">{agent["name"]}</div>'
                    f'<div class="agent-legend">∿ {agent["legend"]}</div></div>'
                    f'</div>'
                    f'<div class="agent-role">{agent["role"]}</div>'
                    f'<span class="status-badge sb-idle">STANDBY</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Launch all agents in parallel threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, num_agents)) as executor:
        futures = {
            executor.submit(run_agent_streaming, agent, user_message, api_key, max_tokens, result_store, lock): agent
            for agent in agents_to_run
        }

        completed = 0
        while completed < num_agents:
            time.sleep(0.4)
            with lock:
                current_store = dict(result_store)

            completed = 0
            for agent in agents_to_run:
                aid = agent["id"]
                data = current_store.get(aid, {})
                text = data.get("text", "")
                done = data.get("done", False)
                is_error = data.get("error", False)

                if done:
                    completed += 1
                    status_html = '<span class="status-badge sb-done">✓ COMPLETE</span>'
                    card_class = "agent-card done"
                else:
                    status_html = '<span class="status-badge sb-running">▶ ANALYZING</span>'
                    card_class = "agent-card streaming"

                output_text = text if text else '<span style="color:#1a3a50">Awaiting signal...</span>'
                safe_text = output_text.replace("<", "&lt;").replace(">", "&gt;") if text else output_text

                placeholders[aid].markdown(
                    f'<div class="{card_class}" style="--agent-color:{agent["color"]}">'
                    f'<div class="agent-header">'
                    f'<div class="agent-icon-wrap" style="border-color:{agent["color"]}66">{agent["icon"]}</div>'
                    f'<div><div class="agent-name" style="color:{agent["color"]}">{agent["name"]}</div>'
                    f'<div class="agent-legend">∿ {agent["legend"]}</div></div>'
                    f'</div>'
                    f'<div class="agent-role">{agent["role"]}</div>'
                    f'{status_html}'
                    f'<div class="agent-output-box" style="margin-top:10px">{safe_text}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            progress_pct = int((completed / num_agents) * 40)
            progress_bar.progress(progress_pct, text=f"Agents analyzing... {completed}/{num_agents} complete")

        # Collect final results
        concurrent.futures.wait(futures)

    final_analyses = {aid: d["text"] for aid, d in result_store.items() if not d.get("error")}

    # ── PHASE 2: Cross-Agent Debate ───────────────────────────────────────────
    st.markdown(
        '<div class="section-hdr">⬡ PHASE 02 — CROSS-AGENT DEBATE</div>',
        unsafe_allow_html=True
    )
    progress_bar.progress(45, text="Initiating cross-agent debate...")

    debate_pairs = []
    n = len(agents_to_run)
    if n >= 2:
        debate_pairs = [
            (agents_to_run[0], agents_to_run[1]),
            (agents_to_run[2 % n], agents_to_run[3 % n]),
        ]
        if n >= 6:
            debate_pairs.append((agents_to_run[4], agents_to_run[5]))

    debate_results = {}
    debate_store: dict = {}
    debate_lock = Lock()

    def run_debate(challenger, target):
        msg = build_debate_message(challenger, target, final_analyses.get(target["id"], ""), query)
        c = anthropic.Anthropic(api_key=api_key)
        full = ""
        try:
            with c.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                system=challenger["system"],
                messages=[{"role": "user", "content": msg}],
            ) as stream:
                for chunk in stream.text_stream:
                    full += chunk
                    with debate_lock:
                        debate_store[challenger["id"]] = full
        except Exception as e:
            with debate_lock:
                debate_store[challenger["id"]] = f"[ERROR] {e}"
        return challenger["id"], full

    debate_placeholders = {}
    for challenger, target in debate_pairs:
        ph = st.empty()
        debate_placeholders[challenger["id"]] = (ph, challenger, target)
        ph.markdown(
            f'<div class="debate-msg" style="border-left-color:{challenger["color"]}">'
            f'<div class="debate-agent-name" style="color:{challenger["color"]}">'
            f'{challenger["icon"]} {challenger["name"]} challenges {target["icon"]} {target["name"]}'
            f'</div><div class="debate-text" style="color:#1a3a50">Preparing challenge...</div></div>',
            unsafe_allow_html=True,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        dfutures = {executor.submit(run_debate, c, t): (c, t) for c, t in debate_pairs}

        completed_debates = 0
        while completed_debates < len(debate_pairs):
            time.sleep(0.4)
            with debate_lock:
                ds = dict(debate_store)

            completed_debates = 0
            for fut, (challenger, target) in dfutures.items():
                text = ds.get(challenger["id"], "")
                done = fut.done()
                if done:
                    completed_debates += 1
                    debate_results[challenger["id"]] = text

                ph, c, t = debate_placeholders[challenger["id"]]
                safe = text.replace("<", "&lt;").replace(">", "&gt;") if text else "Formulating challenge..."
                ph.markdown(
                    f'<div class="debate-msg" style="border-left-color:{c["color"]}">'
                    f'<div class="debate-agent-name" style="color:{c["color"]}">'
                    f'{c["icon"]} {c["name"]} → challenges → {t["icon"]} {t["name"]}'
                    f'{"&nbsp;&nbsp;<span class=\'status-badge sb-done\'>✓</span>" if done else "&nbsp;&nbsp;<span class=\'status-badge sb-running\'>▶ DEBATING</span>"}'
                    f'</div><div class="debate-text">{safe}</div></div>',
                    unsafe_allow_html=True,
                )

            p = 45 + int((completed_debates / max(len(debate_pairs), 1)) * 30)
            progress_bar.progress(p, text=f"Debate in progress... {completed_debates}/{len(debate_pairs)} exchanges")

        concurrent.futures.wait(dfutures)

    # ── PHASE 3: Consensus ────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-hdr">⬡ PHASE 03 — CONSENSUS SYNTHESIS</div>',
        unsafe_allow_html=True
    )
    progress_bar.progress(80, text="Synthesizing consensus...")

    consensus_ph = st.empty()
    consensus_ph.markdown(
        '<div class="consensus-panel"><div style="font-family:\'Share Tech Mono\',monospace;'
        'font-size:12px;color:#5a8aaa;letter-spacing:2px;">SYNTHESIZING HIVE MIND CONSENSUS...</div></div>',
        unsafe_allow_html=True,
    )

    consensus_msg = build_consensus_message(query, mode, final_analyses)
    raw_consensus = ""
    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=CONSENSUS_CONFIG["system"],
            messages=[{"role": "user", "content": consensus_msg}],
        ) as stream:
            for chunk in stream.text_stream:
                raw_consensus += chunk
    except Exception as e:
        raw_consensus = f'{{"overall_stance": "ERROR", "key_thesis": "{str(e)}"}}'

    progress_bar.progress(95, text="Finalizing verdict...")

    # Parse consensus JSON
    try:
        cleaned = raw_consensus.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
    except Exception:
        data = {"overall_stance": "NEUTRAL", "narrative": raw_consensus, "parse_error": True}

    # Render consensus
    stance = data.get("overall_stance", "NEUTRAL").upper()
    stance_class = {"BULLISH": "v-bullish", "BEARISH": "v-bearish"}.get(stance, "v-neutral")
    conviction = data.get("conviction", "—")
    horizon = data.get("time_horizon", "—")
    agreement = data.get("agent_agreement_pct", "—")
    thesis = data.get("key_thesis", "")
    action = data.get("action", "")
    entry = data.get("entry_trigger", "")
    stop = data.get("stop_loss_logic", "")
    target_val = data.get("target", "")
    bull = data.get("bull_case", "")
    bear = data.get("bear_case", "")
    narrative = data.get("narrative", "")
    tags = data.get("tags", [])
    agents_bull = ", ".join(data.get("agents_bullish", []))
    agents_bear = ", ".join(data.get("agents_bearish", []))

    tags_html = "".join([
        f'<span style="display:inline-block;padding:3px 10px;margin:2px;border:1px solid #1a3a50;'
        f'border-radius:2px;font-family:\'Share Tech Mono\',monospace;font-size:10px;'
        f'letter-spacing:1px;color:#5a8aaa;">{t}</span>'
        for t in tags
    ])

    consensus_ph.markdown(f"""
<div class="consensus-panel">
  <div class="verdict-row">
    <div class="verdict-box">
      <div class="verdict-label">OVERALL STANCE</div>
      <div class="verdict-val {stance_class}">{stance}</div>
    </div>
    <div class="verdict-box">
      <div class="verdict-label">CONVICTION</div>
      <div class="verdict-val v-accent">{conviction}</div>
    </div>
    <div class="verdict-box">
      <div class="verdict-label">TIME HORIZON</div>
      <div class="verdict-val" style="font-size:13px;color:#f5c842;font-family:'Rajdhani',sans-serif;">{horizon}</div>
    </div>
    <div class="verdict-box">
      <div class="verdict-label">AGENT AGREEMENT</div>
      <div class="verdict-val v-purple">{agreement}%</div>
    </div>
  </div>

  {'<div style="margin-bottom:16px;padding:14px;background:#0a1520;border:1px solid #1a3a50;border-radius:4px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#2a5a7a;margin-bottom:6px;">CORE THESIS</div><div style="font-size:15px;line-height:1.7;color:#c8e0f0;font-weight:600;">' + thesis + '</div></div>' if thesis else ''}

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
    {'<div style="background:#0a1520;border:1px solid #1a3a50;border-radius:4px;padding:12px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#00ff88;margin-bottom:4px;">ACTION</div><div style="font-size:13px;color:#c8e0f0;line-height:1.6;">' + action + '</div></div>' if action else ''}
    {'<div style="background:#0a1520;border:1px solid #1a3a50;border-radius:4px;padding:12px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#00d4ff;margin-bottom:4px;">ENTRY TRIGGER</div><div style="font-size:13px;color:#c8e0f0;line-height:1.6;">' + entry + '</div></div>' if entry else ''}
    {'<div style="background:#0a1520;border:1px solid #1a3a50;border-radius:4px;padding:12px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#ff6b35;margin-bottom:4px;">STOP LOSS LOGIC</div><div style="font-size:13px;color:#c8e0f0;line-height:1.6;">' + stop + '</div></div>' if stop else ''}
    {'<div style="background:#0a1520;border:1px solid #1a3a50;border-radius:4px;padding:12px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#f5c842;margin-bottom:4px;">TARGET</div><div style="font-size:13px;color:#c8e0f0;line-height:1.6;">' + target_val + '</div></div>' if target_val else ''}
  </div>

  {'<div style="background:#0a1520;border:1px solid #1a3a50;border-radius:4px;padding:12px;margin-bottom:16px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#f472b6;margin-bottom:6px;">BULL / BEAR SCENARIOS</div><div style="font-size:12px;color:#00ff88;margin-bottom:4px;">↑ ' + bull + '</div><div style="font-size:12px;color:#ff4444;">↓ ' + bear + '</div></div>' if (bull or bear) else ''}

  {'<div style="background:#0a1520;border:1px solid #1a3a50;border-radius:4px;padding:12px;margin-bottom:16px;"><div style="font-family:\'Share Tech Mono\',monospace;font-size:10px;letter-spacing:2px;color:#2a5a7a;margin-bottom:4px;">AGENT ALIGNMENT</div><div style="font-size:12px;color:#00ff88;margin-bottom:2px;">BULLISH: ' + agents_bull + '</div><div style="font-size:12px;color:#ff4444;">BEARISH: ' + agents_bear + '</div></div>' if (agents_bull or agents_bear) else ''}

  <div style="border-left:2px solid #00d4ff;padding-left:16px;font-size:14px;line-height:1.9;color:#c8e0f0;margin-bottom:16px;white-space:pre-wrap;">{narrative}</div>

  <div>{tags_html}</div>
</div>
""", unsafe_allow_html=True)

    progress_bar.progress(100, text="✓ Analysis complete")

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="disclaimer">
      ⚠ DISCLAIMER: THIS IS AN AI SIMULATION FOR EDUCATIONAL AND RESEARCH PURPOSES ONLY.<br>
      NOT FINANCIAL ADVICE · NOT SEBI-REGISTERED · PAST PATTERNS DO NOT GUARANTEE FUTURE RETURNS<br>
      F&O TRADING INVOLVES SUBSTANTIAL RISK OF LOSS · ALWAYS CONSULT A SEBI-REGISTERED INVESTMENT ADVISOR
    </div>
    """, unsafe_allow_html=True)

elif launch and not query.strip():
    st.warning("⚠ Please enter an investment query before launching.")

else:
    # ── Landing state ─────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center;padding:48px 20px;">
      <div style="font-size:52px;margin-bottom:16px;opacity:0.4;">🧠</div>
      <div style="font-family:'Orbitron',monospace;font-size:15px;color:#5a8aaa;letter-spacing:4px;margin-bottom:12px;">
        8 AGENTS STANDING BY
      </div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:11px;color:#2a5a7a;letter-spacing:2px;line-height:2.4;">
        QUANT ORACLE · VALUE SENTINEL · MACRO TITAN · CHART HAWK<br>
        OPTIONS ARCHITECT · SECTOR GURU · RISK GUARDIAN · BEHAVIORAL LENS<br>
        <br>
        ENTER A QUERY ABOVE AND HIT LAUNCH<br>
        <span style="color:#1a3a50;font-size:10px;">
        TRY: "HDFC Bank — buy after Q4 results?" · "BankNifty weekly short straddle" · "Nifty at 25000 — top or breakout?"
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)
