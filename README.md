# ⬡ HIVE MIND ALPHA
### Multi-Agent SENSEX Investment Intelligence System

> **8 legendary investor frameworks, running in parallel, debating each other, reaching consensus — powered by Claude AI**

![Python](https://img.shields.io/badge/Python-3.9+-blue?style=flat-square)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red?style=flat-square)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude%20Sonnet-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## 🧠 What Is This?

HIVE MIND ALPHA is a multi-agent AI system where **8 specialized agents** — each embodying a legendary investor's philosophy — simultaneously analyze any SENSEX/NSE investment query, debate each other's conclusions, and synthesize a final consensus verdict.

### The 8 Agents

| Agent | Legend | Specialty |
|-------|--------|-----------|
| ⚛ QUANT ORACLE | Jim Simons | Statistical arbitrage, momentum signals, mean-reversion |
| 🏛 VALUE SENTINEL | Warren Buffett / Charlie Munger | Fundamental value, moats, FCF, intrinsic value |
| 🌐 MACRO TITAN | George Soros | Reflexivity, FII flows, RBI cycles, macro regimes |
| 📈 CHART HAWK | Jesse Livermore / Stan Weinstein | Technical analysis, Wyckoff, Elliott Wave, OI |
| ⚡ OPTIONS ARCHITECT | Nassim Taleb / Sheldon Natenberg | F&O strategy, Greeks, IV surface, tail risk |
| 🔭 SECTOR GURU | Peter Lynch | Sector rotation, PLI schemes, industry dynamics |
| 🛡 RISK GUARDIAN | Ray Dalio | Risk parity, VaR, drawdown, portfolio construction |
| 🧠 BEHAVIORAL LENS | Daniel Kahneman / Richard Thaler | Behavioral biases, market psychology, sentiment |

### The 3-Phase Process

```
Phase 1 → Parallel Analysis    All 8 agents analyze simultaneously (streaming)
Phase 2 → Cross-Agent Debate   Agents challenge each other's conclusions
Phase 3 → Consensus Synthesis  Meta-agent produces final actionable verdict
```

### What You Get in the Final Verdict

- **Overall Stance**: BULLISH / BEARISH / NEUTRAL
- **Conviction Level**: HIGH / MEDIUM / LOW  
- **Time Horizon**: Intraday → Long-term
- **Agent Agreement %**: How aligned the agents are
- **Core Thesis**: 2-sentence investment thesis
- **Action**: Specific actionable recommendation
- **Entry Trigger**: Exact condition to wait for
- **Stop Loss Logic**: Risk management rule
- **Target**: Price target or % move
- **Bull Case / Bear Case**: One sentence each
- **Rich Narrative**: 3-paragraph synthesis of debates and reasoning

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/hivemind-alpha.git
cd hivemind-alpha
```

### 2. Create a virtual environment
```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up your API key
```bash
cp .env.example .env
# Edit .env and add your Anthropic API key
```

Or you can enter it directly in the app's sidebar.

### 5. Run the app
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

---

## 🔑 Getting an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Navigate to **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-...`)

---

## 📁 Project Structure

```
hivemind-alpha/
├── app.py                  # Main Streamlit application
├── agents.py               # All 8 agent definitions & prompts
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── config.toml         # Streamlit theme configuration
├── .env.example            # Environment variables template
├── .gitignore
└── README.md
```

---

## 💡 Example Queries

**Equity Analysis:**
- `"HDFC Bank Q4 results — buy the dip or wait?"`
- `"Reliance Industries — long-term hold or trim at current levels?"`
- `"Nifty50 at 25000 — is this a top or the start of a breakout?"`
- `"TCS vs Infosys — which is the better buy for FY26?"`

**F&O Analysis:**
- `"BankNifty weekly straddle — buy or sell this expiry?"`
- `"Nifty 25000 CE — momentum play or IV trap?"`
- `"India VIX at 14 — short strangles or buy convexity?"`

**Combined / Thematic:**
- `"PSU Banks — structural bull market or value trap?"`
- `"India small cap index — time to add or reduce exposure?"`
- `"Defence sector PLI stocks — overvalued or justified premium?"`

---

## ⚙️ Configuration

### Changing the AI Model
In `app.py`, find `model="claude-sonnet-4-20250514"` and change to your preferred Claude model.

### Adjusting Analysis Depth
The app offers three depths:
- **Quick** (600 tokens) — Faster, concise analysis
- **Deep** (1000 tokens) — Balanced (recommended)
- **Ultra** (1500 tokens) — Most detailed, slowest

### Adding New Agents
Edit `agents.py` — add a new dict to the `AGENTS` list with:
```python
{
    "id": "unique_id",
    "name": "DISPLAY NAME",
    "legend": "Legendary investor name",
    "role": "Short role description",
    "icon": "emoji",
    "color": "#hexcolor",
    "specialty": ["equity", "fo", "combined"],  # which modes to include in
    "system": "Full system prompt...",
}
```

---

## 🌐 Deployment

### Deploy on Streamlit Cloud (Free)

1. Push your repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app** → select your repo → `app.py`
4. In **Advanced settings** → **Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-your-key-here"
   ```
5. Click **Deploy**

Then in `app.py`, change the API key loading to:
```python
import os
api_key = st.secrets.get("ANTHROPIC_API_KEY") or st.session_state.get("api_key", "")
```

### Deploy on Railway / Render / Fly.io

Set environment variable `ANTHROPIC_API_KEY` in your platform's dashboard, and use the same secret-loading pattern above.

---

## ⚠️ Disclaimer

**This application is for educational and research purposes only.**

- This is NOT financial advice
- This is NOT a SEBI-registered investment advisory service
- Past analysis patterns do not guarantee future returns
- F&O (Futures & Options) trading involves substantial risk of loss
- Always consult a SEBI-registered investment advisor before making investment decisions
- The "legendary investor" personas are AI simulations, not actual systems used by those investors

---

## 🤝 Contributing

Pull requests welcome. For major changes, please open an issue first to discuss.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/new-agent`)
3. Commit your changes (`git commit -m 'Add ESG analyst agent'`)
4. Push to the branch (`git push origin feature/new-agent`)
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

<div align="center">
Built with ❤️ using Streamlit + Anthropic Claude
</div>
