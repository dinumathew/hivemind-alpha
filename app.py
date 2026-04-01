"""
HIVE MIND ALPHA — Multi-Agent SENSEX Intelligence System
Blackstone-inspired institutional design palette
Run: streamlit run app.py
"""

import streamlit as st
import anthropic
import json
import time
import concurrent.futures
from threading import Lock
from agents import AGENTS, CONSENSUS_CONFIG, get_agents_for_mode

st.set_page_config(
    page_title="HIVE MIND ALPHA · SENSEX Intelligence",
    page_icon="▪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Blackstone Palette CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --black:    #0A0A0A;
  --ink:      #111111;
  --panel:    #161616;
  --panel2:   #1C1C1C;
  --border:   #2A2A2A;
  --border2:  #333333;
  --gold:     #C9A84C;
  --gold2:    #E8C96A;
  --gold-dim: #7A6330;
  --white:    #F5F5F0;
  --gray1:    #AAAAAA;
  --gray2:    #666666;
  --gray3:    #3A3A3A;
  --green:    #4CAF82;
  --red:      #C94C4C;
  --amber:    #C9844C;
}

html, body, [class*="css"] {
  font-family: 'Inter', sans-serif;
  background: var(--black);
  color: var(--white);
}
.stApp { background: var(--black); }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 2rem 2.5rem 3rem; max-width: 1440px; }

/* ── Header ── */
.hm-masthead {
  border-bottom: 1px solid var(--border2);
  padding-bottom: 20px;
  margin-bottom: 28px;
}
.hm-wordmark {
  font-family: 'EB Garamond', serif;
  font-size: 32px; font-weight: 500;
  color: var(--white); letter-spacing: 4px;
  margin: 0;
}
.hm-wordmark span { color: var(--gold); }
.hm-tagline {
  font-family: 'Inter', sans-serif;
  font-size: 11px; font-weight: 400;
  color: var(--gray2); letter-spacing: 3px;
  text-transform: uppercase; margin-top: 4px;
}
.hm-rule {
  height: 1px;
  background: linear-gradient(90deg, var(--gold) 0%, var(--border) 60%, transparent 100%);
  margin-top: 16px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--ink) !important;
  border-right: 1px solid var(--border2) !important;
}
[data-testid="stSidebar"] .block-container { padding: 1.5rem 1.2rem; }

/* ── Inputs ── */
.stTextInput > label, .stSelectbox > label {
  font-family: 'Inter', sans-serif !important;
  font-size: 10px !important; font-weight: 600 !important;
  letter-spacing: 2px !important; text-transform: uppercase !important;
  color: var(--gray2) !important;
}
.stTextInput > div > div > input {
  background: var(--panel) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 2px !important;
  color: var(--white) !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 14px !important;
  padding: 10px 14px !important;
  transition: border-color 0.2s !important;
}
.stTextInput > div > div > input:focus {
  border-color: var(--gold) !important;
  box-shadow: 0 0 0 1px rgba(201,168,76,0.2) !important;
}
.stTextInput > div > div > input::placeholder { color: var(--gray3) !important; }
.stSelectbox > div > div {
  background: var(--panel) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 2px !important;
  color: var(--white) !important;
}

/* ── Buttons ── */
.stButton > button {
  background: var(--gold) !important;
  border: none !important;
  color: var(--black) !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 12px !important; font-weight: 600 !important;
  letter-spacing: 2px !important; text-transform: uppercase !important;
  border-radius: 2px !important;
  padding: 10px 28px !important;
  transition: background 0.2s !important;
}
.stButton > button:hover { background: var(--gold2) !important; }
.stButton > button:disabled { background: var(--gray3) !important; color: var(--gray2) !important; }

/* ── Progress ── */
.stProgress > div > div > div { background: var(--gold) !important; }
.stProgress > div > div { background: var(--border) !important; }

/* ── Divider ── */
hr { border-color: var(--border) !important; }

/* ── Section label ── */
.sec-label {
  font-family: 'Inter', sans-serif;
  font-size: 10px; font-weight: 600;
  letter-spacing: 3px; text-transform: uppercase;
  color: var(--gold-dim);
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  margin: 28px 0 18px;
  display: flex; align-items: center; gap: 10px;
}
.sec-label::before { content: '▪'; color: var(--gold); }

/* ── Agent cards ── */
.ag-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--gold-dim);
  border-radius: 2px;
  padding: 18px;
  margin-bottom: 14px;
  transition: border-left-color 0.3s;
}
.ag-card.active { border-left-color: var(--gold); }
.ag-card.done   { border-left-color: var(--green); }
.ag-card.error  { border-left-color: var(--red); }

.ag-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.ag-icon {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--panel2); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; flex-shrink: 0;
}
.ag-name {
  font-family: 'Inter', sans-serif;
  font-size: 12px; font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase;
  color: var(--gold);
}
.ag-legend { font-size: 11px; color: var(--gray2); margin-top: 1px; }
.ag-role   { font-size: 12px; color: var(--gray1); margin-bottom: 10px; }

.status-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; letter-spacing: 1px;
  border-radius: 1px;
  border: 1px solid;
}
.sp-idle    { border-color: var(--border2); color: var(--gray3); }
.sp-running { border-color: var(--gold-dim); color: var(--gold); background: rgba(201,168,76,0.05); }
.sp-done    { border-color: #2A5A40; color: var(--green); background: rgba(76,175,130,0.05); }
.sp-error   { border-color: #5A2A2A; color: var(--red); }

.ag-output {
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 12px 14px;
  margin-top: 10px;
  font-family: 'Inter', sans-serif;
  font-size: 12.5px; line-height: 1.75;
  color: var(--gray1);
  white-space: pre-wrap;
  min-height: 50px;
}

/* ── Debate ── */
.debate-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--gold-dim);
  border-radius: 2px;
  padding: 16px 18px;
  margin-bottom: 10px;
}
.debate-hdr {
  font-family: 'Inter', sans-serif;
  font-size: 11px; font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase;
  color: var(--gold-dim); margin-bottom: 8px;
}
.debate-body {
  font-size: 13px; line-height: 1.75;
  color: var(--gray1); white-space: pre-wrap;
}

/* ── Consensus ── */
.cs-panel {
  background: var(--panel);
  border: 1px solid var(--border2);
  border-top: 2px solid var(--gold);
  border-radius: 2px;
  padding: 28px;
}
.cs-kpi-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.cs-kpi {
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 16px 20px;
  min-width: 130px; flex: 1; text-align: center;
}
.cs-kpi-label {
  font-size: 10px; font-weight: 600;
  letter-spacing: 2px; text-transform: uppercase;
  color: var(--gray2); margin-bottom: 6px;
}
.cs-kpi-val {
  font-family: 'EB Garamond', serif;
  font-size: 24px; font-weight: 500;
}
.cv-bull  { color: var(--green); }
.cv-bear  { color: var(--red); }
.cv-neut  { color: var(--amber); }
.cv-gold  { color: var(--gold); }
.cv-white { color: var(--white); font-size: 16px; font-family: 'Inter', sans-serif; }

.cs-block {
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 14px 16px;
}
.cs-block-label {
  font-size: 10px; font-weight: 600;
  letter-spacing: 2px; text-transform: uppercase;
  color: var(--gray2); margin-bottom: 6px;
}
.cs-block-val { font-size: 13px; line-height: 1.7; color: var(--white); }

.cs-narrative {
  border-left: 2px solid var(--gold-dim);
  padding-left: 18px;
  font-family: 'Inter', sans-serif;
  font-size: 13.5px; line-height: 1.9;
  color: var(--gray1); white-space: pre-wrap;
}

.tag-chip {
  display: inline-block;
  padding: 3px 10px; margin: 2px;
  border: 1px solid var(--border2);
  border-radius: 1px;
  font-size: 10px; font-weight: 500;
  letter-spacing: 1px; text-transform: uppercase;
  color: var(--gray2);
}

/* ── Disclaimer ── */
.disclaimer {
  text-align: center; padding: 14px;
  font-size: 10px; letter-spacing: 1px;
  color: var(--gray3); line-height: 2;
  border: 1px solid var(--border);
  border-radius: 2px; margin-top: 24px;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { background: var(--panel); border-radius: 2px; gap: 0; }
.stTabs [data-baseweb="tab"] {
  font-family: 'Inter', sans-serif !important;
  font-size: 11px !important; font-weight: 600 !important;
  letter-spacing: 2px !important; text-transform: uppercase !important;
  color: var(--gray2) !important; background: transparent !important;
  border-radius: 0 !important; padding: 12px 20px !important;
}
.stTabs [aria-selected="true"] {
  color: var(--gold) !important;
  border-bottom: 2px solid var(--gold) !important;
  background: rgba(201,168,76,0.04) !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
  font-family: 'Inter', sans-serif !important;
  font-size: 11px !important; font-weight: 600 !important;
  letter-spacing: 2px !important; text-transform: uppercase !important;
  color: var(--gray1) !important;
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
}
.streamlit-expanderContent {
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  border-top: none !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important; padding: 14px !important;
}
[data-testid="metric-container"] label {
  font-size: 10px !important; font-weight: 600 !important;
  letter-spacing: 2px !important; text-transform: uppercase !important;
  color: var(--gray2) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: 'EB Garamond', serif !important;
  font-size: 26px !important; color: var(--white) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Masthead ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hm-masthead">
  <div class="hm-wordmark">HIVE MIND <span>ALPHA</span></div>
  <div class="hm-tagline">Multi-Agent Investment Intelligence &nbsp;·&nbsp; SENSEX &amp; NIFTY &nbsp;·&nbsp; Equity &amp; F&amp;O</div>
  <div class="hm-rule"></div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-family:\'EB Garamond\',serif;font-size:20px;color:#C9A84C;letter-spacing:2px;margin-bottom:16px;">Configuration</div>', unsafe_allow_html=True)

    api_key_input = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="Get your key at console.anthropic.com",
    )

    st.markdown("---")
    st.markdown('<div style="font-size:10px;font-weight:600;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:12px;">Market Reference</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:2.2;color:#AAAAAA;">
    SENSEX (BSE 30)<br>
    <span style="color:#C9A84C;">≈ 73,000 – 80,000</span><br><br>
    NIFTY 50 (NSE)<br>
    <span style="color:#C9A84C;">≈ 22,000 – 25,000</span><br><br>
    BANKNIFTY (NSE)<br>
    <span style="color:#C9A84C;">≈ 48,000 – 52,000</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div style="font-size:10px;font-weight:600;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:12px;">Active Agents</div>', unsafe_allow_html=True)
    for agent in AGENTS:
        st.markdown(
            f'<div style="font-size:11px;color:#AAAAAA;margin-bottom:5px;">'
            f'{agent["icon"]} <span style="color:#C9A84C;font-weight:600;">{agent["name"]}</span><br>'
            f'<span style="color:#3A3A3A;font-size:10px;">{agent["legend"]}</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.markdown('<div style="font-size:9px;letter-spacing:1px;color:#3A3A3A;line-height:1.8;">FOR EDUCATIONAL USE ONLY<br>NOT SEBI-REGISTERED ADVICE<br>F&O INVOLVES RISK OF LOSS</div>', unsafe_allow_html=True)

# ── API Key guard ─────────────────────────────────────────────────────────────
api_key = (
    api_key_input
    or st.session_state.get("api_key", "")
    or st.secrets.get("ANTHROPIC_API_KEY", "")
)
if api_key_input:
    st.session_state["api_key"] = api_key_input

if not api_key:
    st.markdown("""
    <div style="text-align:center;padding:80px 20px;">
      <div style="font-family:'EB Garamond',serif;font-size:48px;color:#2A2A2A;margin-bottom:20px;">▪</div>
      <div style="font-family:'EB Garamond',serif;font-size:24px;color:#C9A84C;letter-spacing:4px;margin-bottom:12px;">
        API Key Required
      </div>
      <div style="font-size:12px;color:#3A3A3A;letter-spacing:2px;line-height:2.4;text-transform:uppercase;">
        Enter your Anthropic API key in the sidebar to activate<br>
        all 8 legendary investor intelligence agents<br>
        <span style="color:#C9A84C;">console.anthropic.com</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Navigation Tabs ───────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "▪  HIVE MIND ANALYSIS",
    "▪  DAILY TRADE DESK",
    "▪  MARKET ANALYTICS",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HIVE MIND ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    col1, col2, col3, col4 = st.columns([3, 1, 0.7, 0.7])
    with col1:
        query = st.text_input(
            "Investment Query",
            placeholder="e.g. HDFC Bank — buy the dip after Q4?  ·  BankNifty weekly straddle  ·  SENSEX at 75000 — top or breakout?",
            key="main_query",
        )
    with col2:
        mode = st.selectbox(
            "Mode",
            options=["equity", "fo", "combined"],
            format_func=lambda x: {"equity": "Equity", "fo": "F&O", "combined": "Full Spectrum"}[x],
        )
    with col3:
        depth = st.selectbox("Depth", options=[600, 1000, 1500],
                             format_func=lambda x: {600: "Standard", 1000: "Deep", 1500: "Ultra"}[x])
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        launch = st.button("Launch Agents", key="launch_main", use_container_width=True)

    # ── Helper functions ───────────────────────────────────────────────────────
    def run_agent_stream(agent, user_msg, api_key, max_tokens, store, lock):
        client = anthropic.Anthropic(api_key=api_key)
        full = ""
        try:
            with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=agent["system"],
                messages=[{"role": "user", "content": user_msg}],
            ) as stream:
                for chunk in stream.text_stream:
                    full += chunk
                    with lock:
                        store[agent["id"]] = {"text": full, "done": False}
            with lock:
                store[agent["id"]] = {"text": full, "done": True}
        except Exception as e:
            with lock:
                store[agent["id"]] = {"text": f"Error: {e}", "done": True, "error": True}
        return agent["id"], full

    def build_query_msg(q, mode):
        from datetime import datetime
        import pytz
        now = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y %H:%M IST")
        return f"""INVESTMENT QUERY: "{q}"
MODE: {mode.upper()} | SENSEX (BSE) / NIFTY (NSE) MARKETS
TIMESTAMP: {now}

Provide your deep expert analysis. Stay strictly within your legendary framework.

Structure:
1. KEY SIGNAL / OPPORTUNITY
2. CRITICAL RISK FACTOR
3. SPECIFIC RECOMMENDATION (Bullish/Bearish/Neutral with exact reasoning)
4. ONE CONTRARIAN TAKE

Be specific, quantitative where possible. Max 250 words."""

    def build_debate_msg(challenger, target, target_text, q):
        return f"""You are {challenger["name"]} ({challenger["legend"]}).

{target["name"]} ({target["legend"]}) said about "{q}":
"{target_text[:450]}..."

In 120 words, CHALLENGE or REINFORCE their single most important claim using your framework.
Name them directly. Be sharp and specific."""

    def build_consensus_msg(q, mode, analyses):
        summaries = "\n\n".join([
            f"=== {a['name']} ({a['legend']}) ===\n{analyses.get(a['id'], 'N/A')[:380]}"
            for a in AGENTS if a["id"] in analyses
        ])
        return f"""QUERY: "{q}" | MODE: {mode.upper()}

AGENT ANALYSES:
{summaries}

Synthesize into a final consensus. Respond ONLY in valid JSON (no markdown):
{{
  "overall_stance": "BULLISH"|"BEARISH"|"NEUTRAL",
  "conviction": "HIGH"|"MEDIUM"|"LOW",
  "time_horizon": "INTRADAY"|"SHORT-TERM"|"MEDIUM-TERM"|"LONG-TERM",
  "agent_agreement_pct": <0-100>,
  "key_thesis": "<2-sentence thesis>",
  "action": "<specific actionable recommendation>",
  "entry_trigger": "<exact condition before entering>",
  "stop_loss_logic": "<specific risk rule>",
  "target": "<price target or % move>",
  "bull_case": "<one sentence>",
  "bear_case": "<one sentence>",
  "agents_bullish": ["names"],
  "agents_bearish": ["names"],
  "agents_neutral": ["names"],
  "tags": ["tag1","tag2","tag3","tag4"],
  "narrative": "<3 rich paragraphs: agent agreements, key debates, final reasoning>"
}}"""

    def render_agent_card(agent, status, text):
        if status == "thinking":
            state, pill = "active", '<span class="status-pill sp-running">● ANALYZING</span>'
        elif status == "done":
            state, pill = "done", '<span class="status-pill sp-done">✓ COMPLETE</span>'
        elif status == "error":
            state, pill = "error", '<span class="status-pill sp-error">✗ ERROR</span>'
        else:
            state, pill = "", '<span class="status-pill sp-idle">◌ STANDBY</span>'

        safe = (text or "").replace("<", "&lt;").replace(">", "&gt;")
        placeholder_txt = '<span style="color:#3A3A3A">Awaiting dispatch...</span>' if not text else safe

        return f"""<div class="ag-card {state}">
  <div class="ag-head">
    <div class="ag-icon">{agent["icon"]}</div>
    <div>
      <div class="ag-name">{agent["name"]}</div>
      <div class="ag-legend">{agent["legend"]}</div>
    </div>
  </div>
  <div class="ag-role">{agent["role"]}</div>
  {pill}
  <div class="ag-output">{placeholder_txt}</div>
</div>"""

    # ── Launch logic ───────────────────────────────────────────────────────────
    if launch and query.strip():
        agents_to_run = get_agents_for_mode(mode)
        client = anthropic.Anthropic(api_key=api_key)
        user_msg = build_query_msg(query, mode)

        # PHASE 1
        st.markdown('<div class="sec-label">Phase 01 &nbsp;—&nbsp; Individual Agent Analysis</div>', unsafe_allow_html=True)
        prog = st.progress(0, text="Deploying agents...")
        result_store, lock = {}, Lock()
        placeholders = {}

        cols_per_row = 2
        for i in range(0, len(agents_to_run), cols_per_row):
            row = agents_to_run[i:i + cols_per_row]
            cols = st.columns(cols_per_row)
            for j, ag in enumerate(row):
                with cols[j]:
                    ph = st.empty()
                    placeholders[ag["id"]] = ph
                    ph.markdown(render_agent_card(ag, "idle", ""), unsafe_allow_html=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(run_agent_stream, ag, user_msg, api_key, depth, result_store, lock): ag
                       for ag in agents_to_run}
            done_count = 0
            while done_count < len(agents_to_run):
                time.sleep(0.35)
                with lock:
                    snap = dict(result_store)
                done_count = 0
                for ag in agents_to_run:
                    d = snap.get(ag["id"], {})
                    status = "idle"
                    if d.get("error"):    status = "error"
                    elif d.get("done"):   status = "done"; done_count += 1
                    elif d.get("text"):   status = "thinking"
                    placeholders[ag["id"]].markdown(
                        render_agent_card(ag, status, d.get("text", "")),
                        unsafe_allow_html=True,
                    )
                prog.progress(int(done_count / len(agents_to_run) * 40),
                              text=f"Agents analyzing… {done_count}/{len(agents_to_run)}")
            concurrent.futures.wait(futures)

        final = {aid: d["text"] for aid, d in result_store.items() if not d.get("error")}

        # PHASE 2 — Debate
        st.markdown('<div class="sec-label">Phase 02 &nbsp;—&nbsp; Cross-Agent Debate</div>', unsafe_allow_html=True)
        prog.progress(45, text="Cross-agent debate...")

        n = len(agents_to_run)
        pairs = [(agents_to_run[i % n], agents_to_run[(i + 1) % n])
                 for i in range(min(3, n - 1))]

        debate_store, debate_lock, debate_phs = {}, Lock(), {}
        for c, t in pairs:
            ph = st.empty()
            debate_phs[c["id"]] = (ph, c, t)
            ph.markdown(
                f'<div class="debate-card"><div class="debate-hdr">'
                f'{c["icon"]} {c["name"]} → {t["icon"]} {t["name"]}</div>'
                f'<div class="debate-body" style="color:#3A3A3A">Preparing challenge…</div></div>',
                unsafe_allow_html=True,
            )

        def run_debate(c, t):
            msg = build_debate_msg(c, t, final.get(t["id"], ""), query)
            cl = anthropic.Anthropic(api_key=api_key)
            full = ""
            try:
                with cl.messages.stream(
                    model="claude-sonnet-4-20250514", max_tokens=400,
                    system=c["system"], messages=[{"role": "user", "content": msg}],
                ) as s:
                    for chunk in s.text_stream:
                        full += chunk
                        with debate_lock:
                            debate_store[c["id"]] = full
            except Exception as e:
                with debate_lock:
                    debate_store[c["id"]] = f"Error: {e}"
            return c["id"], full

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            dfuts = {ex.submit(run_debate, c, t): (c, t) for c, t in pairs}
            while not all(f.done() for f in dfuts):
                time.sleep(0.35)
                with debate_lock:
                    ds = dict(debate_store)
                for f, (c, t) in dfuts.items():
                    txt = ds.get(c["id"], "")
                    done_d = f.done()
                    safe = txt.replace("<", "&lt;").replace(">", "&gt;") if txt else "Formulating challenge…"
                    status_lbl = "✓ COMPLETE" if done_d else "● DEBATING"
                    status_col = "#4CAF82" if done_d else "#C9A84C"
                    ph, cc, tt = debate_phs[c["id"]]
                    ph.markdown(
                        f'<div class="debate-card"><div class="debate-hdr">'
                        f'{cc["icon"]} {cc["name"]} → {tt["icon"]} {tt["name"]} &nbsp;'
                        f'<span style="color:{status_col};font-size:10px;">{status_lbl}</span></div>'
                        f'<div class="debate-body">{safe}</div></div>',
                        unsafe_allow_html=True,
                    )
                p = 45 + int(sum(1 for f in dfuts if f.done()) / len(pairs) * 30)
                prog.progress(p, text="Debate in progress…")
            concurrent.futures.wait(dfuts)

        # PHASE 3 — Consensus
        st.markdown('<div class="sec-label">Phase 03 &nbsp;—&nbsp; Consensus Synthesis</div>', unsafe_allow_html=True)
        prog.progress(80, text="Synthesizing consensus…")
        cs_ph = st.empty()
        cs_ph.markdown('<div class="cs-panel" style="color:#3A3A3A;font-size:12px;letter-spacing:2px;">SYNTHESIZING…</div>', unsafe_allow_html=True)

        raw = ""
        try:
            with client.messages.stream(
                model="claude-sonnet-4-20250514", max_tokens=1500,
                system=CONSENSUS_CONFIG["system"],
                messages=[{"role": "user", "content": build_consensus_msg(query, mode, final)}],
            ) as s:
                for chunk in s.text_stream:
                    raw += chunk
        except Exception as e:
            raw = f'{{"overall_stance":"NEUTRAL","narrative":"Error: {e}"}}'

        prog.progress(95, text="Finalising verdict…")

        try:
            data = json.loads(raw.strip().replace("```json", "").replace("```", "").strip())
        except Exception:
            data = {"overall_stance": "NEUTRAL", "narrative": raw, "parse_error": True}

        stance = data.get("overall_stance", "NEUTRAL").upper()
        sc = {"BULLISH": "cv-bull", "BEARISH": "cv-bear"}.get(stance, "cv-neut")
        conv = data.get("conviction", "—")
        horiz = data.get("time_horizon", "—")
        agree = data.get("agent_agreement_pct", "—")
        thesis = data.get("key_thesis", "")
        action = data.get("action", "")
        entry = data.get("entry_trigger", "")
        stop = data.get("stop_loss_logic", "")
        tgt = data.get("target", "")
        bull = data.get("bull_case", "")
        bear = data.get("bear_case", "")
        narrative = data.get("narrative", raw)
        tags = data.get("tags", [])
        a_bull = ", ".join(data.get("agents_bullish", []))
        a_bear = ", ".join(data.get("agents_bearish", []))

        tags_html = "".join([f'<span class="tag-chip">{t}</span>' for t in tags])

        def kpi(label, val, cls="cv-white"):
            return f'<div class="cs-kpi"><div class="cs-kpi-label">{label}</div><div class="cs-kpi-val {cls}">{val}</div></div>'

        def block(label, val, col="#FFFFFF"):
            if not val: return ""
            safe_v = str(val).replace("<", "&lt;").replace(">", "&gt;")
            return (f'<div class="cs-block"><div class="cs-block-label" style="color:{col}66">{label}</div>'
                    f'<div class="cs-block-val">{safe_v}</div></div>')

        cs_ph.markdown(f"""
<div class="cs-panel">
  <div class="cs-kpi-row">
    {kpi("Overall Stance", stance, sc)}
    {kpi("Conviction", conv, "cv-gold")}
    {kpi("Time Horizon", horiz, "cv-white")}
    {kpi("Agent Agreement", f"{agree}%" if agree != "—" else "—", "cv-gold")}
  </div>

  {'<div class="cs-block" style="margin-bottom:16px"><div class="cs-block-label">Core Investment Thesis</div><div style="font-family:\'EB Garamond\',serif;font-size:17px;line-height:1.7;color:#F5F5F0;">' + thesis + '</div></div>' if thesis else ''}

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
    {block("Recommended Action", action, "#4CAF82")}
    {block("Entry Trigger", entry, "#C9A84C")}
    {block("Stop Loss Logic", stop, "#C94C4C")}
    {block("Price Target", tgt, "#C9A84C")}
  </div>

  {'<div class="cs-block" style="margin-bottom:16px"><div class="cs-block-label">Bull / Bear Scenarios</div><div style="font-size:12.5px;color:#4CAF82;margin-bottom:4px;">↑ ' + bull + '</div><div style="font-size:12.5px;color:#C94C4C;">↓ ' + bear + '</div></div>' if (bull or bear) else ''}

  {'<div class="cs-block" style="margin-bottom:16px"><div class="cs-block-label">Agent Alignment</div><div style="font-size:12px;color:#4CAF82;margin-bottom:3px;">Bullish: ' + a_bull + '</div><div style="font-size:12px;color:#C94C4C;">Bearish: ' + a_bear + '</div></div>' if (a_bull or a_bear) else ''}

  <div class="cs-narrative" style="margin-bottom:20px;">{narrative.replace("<","&lt;").replace(">","&gt;")}</div>

  <div>{tags_html}</div>
</div>
""", unsafe_allow_html=True)

        prog.progress(100, text="✓ Analysis complete")
        st.markdown('<div class="disclaimer">FOR EDUCATIONAL PURPOSES ONLY &nbsp;·&nbsp; NOT SEBI-REGISTERED FINANCIAL ADVICE &nbsp;·&nbsp; F&O INVOLVES SUBSTANTIAL RISK OF LOSS<br>ALWAYS CONSULT A SEBI-REGISTERED INVESTMENT ADVISOR BEFORE MAKING ANY INVESTMENT DECISION</div>', unsafe_allow_html=True)

    elif launch and not query.strip():
        st.warning("Please enter an investment query.")
    else:
        st.markdown("""
        <div style="text-align:center;padding:64px 20px;">
          <div style="font-family:'EB Garamond',serif;font-size:64px;color:#1C1C1C;margin-bottom:16px;">▪</div>
          <div style="font-family:'EB Garamond',serif;font-size:20px;color:#C9A84C;letter-spacing:4px;margin-bottom:14px;">8 Agents Standing By</div>
          <div style="font-size:11px;color:#3A3A3A;letter-spacing:2px;line-height:2.6;text-transform:uppercase;">
            Quant Oracle &nbsp;·&nbsp; Value Sentinel &nbsp;·&nbsp; Macro Titan &nbsp;·&nbsp; Chart Hawk<br>
            Options Architect &nbsp;·&nbsp; Sector Guru &nbsp;·&nbsp; Risk Guardian &nbsp;·&nbsp; Behavioral Lens<br>
            <span style="color:#2A2A2A;font-size:10px;">
            Try: "HDFC Bank — buy after Q4?" &nbsp;·&nbsp; "BankNifty weekly straddle" &nbsp;·&nbsp; "SENSEX at 76000 — breakout or fakeout?"
            </span>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — DAILY TRADE DESK
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    from agents import TRADE_ADVISOR_CONFIG

    st.markdown("""
    <div style="font-family:'EB Garamond',serif;font-size:14px;color:#666;letter-spacing:2px;margin-bottom:20px;">
    Generates specific intraday and swing trade setups with precise entry, targets, stop-loss, and risk parameters.
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2.5, 1, 0.8])
    with c1:
        trade_q = st.text_input(
            "Stock / Index / Sector",
            placeholder="e.g. RELIANCE  ·  BankNifty  ·  NIFTY IT sector  ·  HDFCBANK options",
            key="trade_query",
        )
    with c2:
        trade_type = st.selectbox(
            "Trade Type",
            options=["intraday", "swing", "positional", "fo_options", "fo_futures"],
            format_func=lambda x: {
                "intraday": "Intraday",
                "swing": "Swing (2–5 days)",
                "positional": "Positional (weeks)",
                "fo_options": "F&O — Options",
                "fo_futures": "F&O — Futures",
            }[x],
            key="trade_type",
        )
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        trade_go = st.button("Generate Trades", key="trade_go", use_container_width=True)

    if trade_go and trade_q.strip():
        client = anthropic.Anthropic(api_key=api_key)
        from datetime import datetime
        import pytz
        now = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y %H:%M IST")

        trade_prompt = f"""Generate 3 specific trade setups for: "{trade_q}"
Trade type requested: {trade_type.upper()}
Current IST time: {now}

SENSEX ≈ 73,000–80,000 | NIFTY 50 ≈ 22,000–25,000 | BANKNIFTY ≈ 48,000–52,000

For EACH of the 3 setups, provide in this EXACT JSON format (respond with JSON array only, no markdown):
[
  {{
    "setup_name": "<descriptive name>",
    "instrument": "<exact stock/index/contract>",
    "direction": "LONG" | "SHORT",
    "trade_type": "{trade_type}",
    "entry_range": "<exact INR range e.g. 2340–2360>",
    "stop_loss": "<exact level with reason>",
    "target_1": "<conservative target>",
    "target_2": "<primary target>",
    "target_3": "<stretch target>",
    "risk_reward": "<e.g. 1:2.5>",
    "position_size": "<% of capital, max 2% risk>",
    "setup_probability": "HIGH" | "MEDIUM" | "LOW",
    "time_validity": "<e.g. Today only / 3-5 days / 2 weeks>",
    "entry_logic": "<2-3 sentences explaining the technical/fundamental setup>",
    "invalidation": "<exact condition that kills this trade>",
    "key_risks": ["risk1", "risk2", "risk3"],
    "fo_details": {{
      "strike": "<if applicable>",
      "expiry": "<if applicable>",
      "premium_range": "<buy/sell at>",
      "max_loss": "<defined>",
      "margin_estimate": "<approx INR>"
    }}
  }}
]"""

        st.markdown('<div class="sec-label">Trade Setups — Generated by AI</div>', unsafe_allow_html=True)

        with st.spinner("Generating trade setups…"):
            raw_trades = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    system=TRADE_ADVISOR_CONFIG["system"],
                    messages=[{"role": "user", "content": trade_prompt}],
                ) as s:
                    for chunk in s.text_stream:
                        raw_trades += chunk
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

        try:
            trades = json.loads(raw_trades.strip().replace("```json", "").replace("```", "").strip())
        except Exception:
            st.error("Could not parse trade data. Raw output shown below.")
            st.code(raw_trades)
            st.stop()

        for i, t in enumerate(trades):
            dir_col = "#4CAF82" if t.get("direction") == "LONG" else "#C94C4C"
            prob = t.get("setup_probability", "MEDIUM")
            prob_col = {"HIGH": "#4CAF82", "MEDIUM": "#C9A84C", "LOW": "#C94C4C"}.get(prob, "#C9A84C")
            fo = t.get("fo_details", {})

            with st.expander(f"{'▲' if t.get('direction')=='LONG' else '▼'} Setup {i+1}: {t.get('setup_name','Trade Setup')} — {t.get('instrument','')}", expanded=True):

                r1, r2, r3, r4, r5 = st.columns(5)
                with r1:
                    st.markdown(f'<div style="background:#161616;border:1px solid #2A2A2A;border-top:2px solid {dir_col};border-radius:2px;padding:12px;text-align:center"><div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:4px;">Direction</div><div style="font-family:\'EB Garamond\',serif;font-size:22px;color:{dir_col};">{t.get("direction","—")}</div></div>', unsafe_allow_html=True)
                with r2:
                    st.markdown(f'<div style="background:#161616;border:1px solid #2A2A2A;border-radius:2px;padding:12px;text-align:center"><div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:4px;">Entry Range</div><div style="font-family:\'EB Garamond\',serif;font-size:16px;color:#F5F5F0;">{t.get("entry_range","—")}</div></div>', unsafe_allow_html=True)
                with r3:
                    st.markdown(f'<div style="background:#161616;border:1px solid #2A2A2A;border-radius:2px;padding:12px;text-align:center"><div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:4px;">Stop Loss</div><div style="font-family:\'EB Garamond\',serif;font-size:16px;color:#C94C4C;">{t.get("stop_loss","—")}</div></div>', unsafe_allow_html=True)
                with r4:
                    st.markdown(f'<div style="background:#161616;border:1px solid #2A2A2A;border-radius:2px;padding:12px;text-align:center"><div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:4px;">Risk : Reward</div><div style="font-family:\'EB Garamond\',serif;font-size:22px;color:#C9A84C;">{t.get("risk_reward","—")}</div></div>', unsafe_allow_html=True)
                with r5:
                    st.markdown(f'<div style="background:#161616;border:1px solid #2A2A2A;border-radius:2px;padding:12px;text-align:center"><div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:4px;">Probability</div><div style="font-family:\'EB Garamond\',serif;font-size:22px;color:{prob_col};">{prob}</div></div>', unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                c1t, c2t = st.columns(2)
                with c1t:
                    st.markdown(f"""
                    <div class="cs-block">
                    <div class="cs-block-label" style="color:#4CAF8266">Targets</div>
                    <div style="font-size:13px;color:#4CAF82;">T1: {t.get("target_1","—")}</div>
                    <div style="font-size:13px;color:#C9A84C;">T2: {t.get("target_2","—")}</div>
                    <div style="font-size:13px;color:#AAAAAA;">T3: {t.get("target_3","—")}</div>
                    </div>""", unsafe_allow_html=True)
                with c2t:
                    st.markdown(f"""
                    <div class="cs-block">
                    <div class="cs-block-label" style="color:#C94C4C66">Trade Parameters</div>
                    <div style="font-size:12px;color:#AAAAAA;line-height:1.8;">
                    Position Size: <span style="color:#F5F5F0;">{t.get("position_size","—")}</span><br>
                    Valid Until: <span style="color:#F5F5F0;">{t.get("time_validity","—")}</span><br>
                    Invalidated If: <span style="color:#C94C4C;">{t.get("invalidation","—")}</span>
                    </div>
                    </div>""", unsafe_allow_html=True)

                if t.get("entry_logic"):
                    st.markdown(f'<div class="cs-block" style="margin-top:10px"><div class="cs-block-label">Setup Rationale</div><div style="font-size:13px;color:#AAAAAA;line-height:1.7;">{t["entry_logic"]}</div></div>', unsafe_allow_html=True)

                risks = t.get("key_risks", [])
                if risks:
                    risk_items = " &nbsp;·&nbsp; ".join([f'<span style="color:#C94C4C">⚠ {r}</span>' for r in risks])
                    st.markdown(f'<div style="margin-top:10px;font-size:11px;letter-spacing:1px;">{risk_items}</div>', unsafe_allow_html=True)

                if fo.get("strike"):
                    st.markdown(f"""
                    <div class="cs-block" style="margin-top:10px;border-left:2px solid #C9A84C;">
                    <div class="cs-block-label" style="color:#C9A84C66">F&O Details</div>
                    <div style="font-size:12px;color:#AAAAAA;line-height:1.8;">
                    Strike / Expiry: <span style="color:#C9A84C;">{fo.get("strike","—")} / {fo.get("expiry","—")}</span><br>
                    Premium: <span style="color:#F5F5F0;">{fo.get("premium_range","—")}</span> &nbsp;|&nbsp;
                    Max Loss: <span style="color:#C94C4C;">{fo.get("max_loss","—")}</span> &nbsp;|&nbsp;
                    Margin Est.: <span style="color:#AAAAAA;">{fo.get("margin_estimate","—")}</span>
                    </div>
                    </div>""", unsafe_allow_html=True)

        st.markdown('<div class="disclaimer">TRADE IDEAS ARE AI-GENERATED FOR EDUCATIONAL PURPOSES ONLY · NOT SEBI-REGISTERED ADVICE · ALWAYS USE STOP LOSSES · NEVER RISK MORE THAN YOU CAN AFFORD TO LOSE</div>', unsafe_allow_html=True)

    elif trade_go:
        st.warning("Please enter a stock or index name.")
    else:
        st.markdown("""
        <div style="text-align:center;padding:48px 20px;">
          <div style="font-family:'EB Garamond',serif;font-size:18px;color:#3A3A3A;letter-spacing:3px;margin-bottom:12px;">Daily Trade Desk</div>
          <div style="font-size:11px;color:#2A2A2A;letter-spacing:2px;line-height:2.4;text-transform:uppercase;">
            Enter a stock or index above to generate 3 specific trade setups<br>
            with precise entry · stop-loss · targets · risk-reward<br>
            <span style="color:#1C1C1C;">Try: RELIANCE · BankNifty · HDFCBANK · Nifty IT</span>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MARKET ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    from agents import ANALYTICS_CONFIG

    st.markdown("""
    <div style="font-family:'EB Garamond',serif;font-size:14px;color:#666;letter-spacing:2px;margin-bottom:20px;">
    Deep analytics across Equity and F&O — market breadth, OI analysis, VIX regime, sector rotation, and derivatives positioning.
    </div>
    """, unsafe_allow_html=True)

    ac1, ac2, ac3 = st.columns([2, 1, 0.8])
    with ac1:
        analytics_q = st.text_input(
            "Analytics Query",
            placeholder="e.g. Nifty market breadth today  ·  BankNifty OI analysis  ·  India VIX regime  ·  FII derivatives positioning",
            key="analytics_query",
        )
    with ac2:
        analytics_focus = st.selectbox(
            "Focus Area",
            options=["market_breadth", "fo_oi", "sector_rotation", "volatility", "fii_flows", "options_chain"],
            format_func=lambda x: {
                "market_breadth": "Market Breadth (Equity)",
                "fo_oi": "F&O Open Interest",
                "sector_rotation": "Sector Rotation",
                "volatility": "VIX & Volatility",
                "fii_flows": "FII / DII Flows",
                "options_chain": "Options Chain Analysis",
            }[x],
            key="analytics_focus",
        )
    with ac3:
        st.markdown("<br>", unsafe_allow_html=True)
        analytics_go = st.button("Run Analytics", key="analytics_go", use_container_width=True)

    if analytics_go and analytics_q.strip():
        client = anthropic.Anthropic(api_key=api_key)
        from datetime import datetime
        import pytz
        now = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y")

        focus_context = {
            "market_breadth": "Focus on advance/decline ratios, 52-week high/low counts, market internals, breadth thrust signals, cumulative breadth divergences.",
            "fo_oi": "Focus on open interest buildup and unwinding, long/short OI changes, cost of carry, rollover analysis, futures premium/discount.",
            "sector_rotation": "Focus on relative sector performance, Nifty sector indices comparison, rotation signals, leadership changes, sector PE vs historical mean.",
            "volatility": "Focus on India VIX levels and regime (low <13 / medium 13-20 / high >20), realized vs implied vol, historical vol cones, event vol premium.",
            "fii_flows": "Focus on FII net equity flows, DII counterflow, FII index futures and stock futures positioning, institutional activity patterns.",
            "options_chain": "Focus on max pain calculation, PCR (put-call ratio), gamma walls, OI concentration at key strikes, IV skew, unusual options activity.",
        }[analytics_focus]

        analytics_prompt = f"""ANALYTICS REQUEST: "{analytics_q}"
FOCUS: {analytics_focus.upper().replace("_"," ")}
DATE: {now}

SENSEX ≈ 73,000–80,000 | NIFTY 50 ≈ 22,000–25,000 | BANKNIFTY ≈ 48,000–52,000

{focus_context}

Provide a comprehensive analytical report. Respond in this EXACT JSON format (no markdown):
{{
  "title": "<concise report title>",
  "headline": "<one-line key finding>",
  "regime": "<current market regime classification>",
  "regime_color": "BULLISH"|"BEARISH"|"NEUTRAL"|"CAUTION",
  "key_metrics": [
    {{"label": "<metric name>", "value": "<value>", "signal": "POSITIVE"|"NEGATIVE"|"NEUTRAL", "note": "<brief interpretation>"}}
  ],
  "sections": [
    {{"title": "<section title>", "content": "<detailed analytical paragraph>", "bullets": ["point1","point2","point3"]}}
  ],
  "actionable_signals": [
    {{"signal": "<specific signal>", "implication": "<what to do>", "urgency": "HIGH"|"MEDIUM"|"LOW"}}
  ],
  "risks_to_watch": ["risk1", "risk2", "risk3", "risk4"],
  "summary": "<3-sentence executive summary of all findings>"
}}"""

        st.markdown('<div class="sec-label">Analytics Report</div>', unsafe_allow_html=True)

        with st.spinner("Generating analytics…"):
            raw_analytics = ""
            try:
                with client.messages.stream(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    system=ANALYTICS_CONFIG["system"],
                    messages=[{"role": "user", "content": analytics_prompt}],
                ) as s:
                    for chunk in s.text_stream:
                        raw_analytics += chunk
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

        try:
            rpt = json.loads(raw_analytics.strip().replace("```json", "").replace("```", "").strip())
        except Exception:
            st.error("Could not parse analytics. Raw output shown below.")
            st.code(raw_analytics)
            st.stop()

        rc = {"BULLISH": "#4CAF82", "BEARISH": "#C94C4C", "NEUTRAL": "#C9A84C", "CAUTION": "#C9844C"}.get(
            rpt.get("regime_color", "NEUTRAL"), "#C9A84C"
        )

        # Header
        st.markdown(f"""
        <div class="cs-panel" style="margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
            <div>
              <div style="font-family:'EB Garamond',serif;font-size:22px;color:#F5F5F0;margin-bottom:4px;">{rpt.get("title","Analytics Report")}</div>
              <div style="font-size:13px;color:#AAAAAA;">{rpt.get("headline","")}</div>
            </div>
            <div style="text-align:center;background:{rc}11;border:1px solid {rc}44;border-radius:2px;padding:10px 18px;">
              <div style="font-size:10px;letter-spacing:2px;color:{rc}99;text-transform:uppercase;margin-bottom:3px;">Regime</div>
              <div style="font-family:'EB Garamond',serif;font-size:18px;color:{rc};">{rpt.get("regime","—")}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Key Metrics
        metrics = rpt.get("key_metrics", [])
        if metrics:
            st.markdown('<div class="sec-label">Key Metrics</div>', unsafe_allow_html=True)
            cols = st.columns(min(len(metrics), 4))
            for i, m in enumerate(metrics[:8]):
                sig_col = {"POSITIVE": "#4CAF82", "NEGATIVE": "#C94C4C"}.get(m.get("signal", ""), "#C9A84C")
                with cols[i % 4]:
                    st.markdown(f"""
                    <div style="background:#161616;border:1px solid #2A2A2A;border-top:2px solid {sig_col};border-radius:2px;padding:14px;margin-bottom:10px;">
                    <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:6px;">{m.get("label","")}</div>
                    <div style="font-family:'EB Garamond',serif;font-size:20px;color:{sig_col};margin-bottom:4px;">{m.get("value","—")}</div>
                    <div style="font-size:11px;color:#3A3A3A;">{m.get("note","")}</div>
                    </div>""", unsafe_allow_html=True)

        # Sections
        sections = rpt.get("sections", [])
        if sections:
            st.markdown('<div class="sec-label">Detailed Analysis</div>', unsafe_allow_html=True)
            for sec in sections:
                with st.expander(sec.get("title", "Section"), expanded=True):
                    if sec.get("content"):
                        st.markdown(f'<div style="font-size:13.5px;color:#AAAAAA;line-height:1.8;margin-bottom:12px;">{sec["content"]}</div>', unsafe_allow_html=True)
                    for b in sec.get("bullets", []):
                        st.markdown(f'<div style="font-size:12.5px;color:#666;line-height:1.7;padding-left:14px;">▸ {b}</div>', unsafe_allow_html=True)

        # Actionable Signals
        signals = rpt.get("actionable_signals", [])
        if signals:
            st.markdown('<div class="sec-label">Actionable Signals</div>', unsafe_allow_html=True)
            for sig in signals:
                urg = sig.get("urgency", "MEDIUM")
                uc = {"HIGH": "#C94C4C", "MEDIUM": "#C9A84C", "LOW": "#4CAF82"}.get(urg, "#C9A84C")
                st.markdown(f"""
                <div style="background:#161616;border:1px solid #2A2A2A;border-left:3px solid {uc};border-radius:2px;padding:12px 16px;margin-bottom:8px;display:flex;gap:12px;align-items:flex-start;">
                  <span style="color:{uc};font-size:10px;letter-spacing:1px;white-space:nowrap;margin-top:2px;">{urg}</span>
                  <div>
                    <div style="font-size:13px;color:#F5F5F0;font-weight:600;margin-bottom:2px;">{sig.get("signal","")}</div>
                    <div style="font-size:12px;color:#666;">{sig.get("implication","")}</div>
                  </div>
                </div>""", unsafe_allow_html=True)

        # Risks
        risks = rpt.get("risks_to_watch", [])
        if risks:
            risk_str = " &nbsp;·&nbsp; ".join([f'<span style="color:#C94C4C66">⚠</span> <span style="color:#666">{r}</span>' for r in risks])
            st.markdown(f'<div style="margin-top:12px;padding:12px 14px;background:#161616;border:1px solid #2A2A2A;border-radius:2px;font-size:11px;letter-spacing:1px;">{risk_str}</div>', unsafe_allow_html=True)

        # Summary
        if rpt.get("summary"):
            st.markdown(f"""
            <div style="background:#161616;border:1px solid #C9A84C33;border-left:3px solid #C9A84C;border-radius:2px;padding:16px 18px;margin-top:16px;">
            <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#7A6330;margin-bottom:8px;">Executive Summary</div>
            <div style="font-family:'EB Garamond',serif;font-size:15px;line-height:1.9;color:#AAAAAA;">{rpt["summary"]}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div class="disclaimer">FOR EDUCATIONAL PURPOSES ONLY · NOT SEBI-REGISTERED FINANCIAL ADVICE · ALWAYS VERIFY DATA FROM OFFICIAL SOURCES · NSE · BSE · SEBI</div>', unsafe_allow_html=True)

    elif analytics_go:
        st.warning("Please enter an analytics query.")
    else:
        st.markdown("""
        <div style="text-align:center;padding:48px 20px;">
          <div style="font-family:'EB Garamond',serif;font-size:18px;color:#3A3A3A;letter-spacing:3px;margin-bottom:12px;">Market Analytics Engine</div>
          <div style="font-size:11px;color:#2A2A2A;letter-spacing:2px;line-height:2.6;text-transform:uppercase;">
            Equity: Market Breadth · Sector Rotation · FII/DII Flows<br>
            F&O: Open Interest · PCR · India VIX · Options Chain · Max Pain<br>
            <span style="color:#1C1C1C;">Try: "Nifty OI analysis" · "India VIX regime" · "BankNifty options chain"</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
