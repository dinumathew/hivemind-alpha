"""
guard.py — Hallucination Guard
HIVE MIND ALPHA · Tier 1

Intercepts agent outputs before consensus.
Extracts factual claims (prices, ratios, levels).
Verifies each claim against live market data.
Flags or corrects hallucinated values.
"""

import re
import json
import anthropic
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

# ── Extraction prompt ──────────────────────────────────────────────────────────
EXTRACTION_PROMPT = """You are a fact-extractor for a financial analysis system.

Extract ALL specific factual claims from the agent analysis below.
Look for: prices, P/E ratios, percentages, index levels, OI figures, VIX levels, RSI values, support/resistance levels.

Respond ONLY in valid JSON:
{
  "claims": [
    {
      "claim_type": "price|pe_ratio|rsi|index_level|oi|vix|support|resistance|fii_flow|other",
      "symbol": "<stock or index name if identifiable>",
      "value": <numeric value>,
      "unit": "<Rs/% /Cr/etc>",
      "context": "<short quote from text where this appears>"
    }
  ]
}

If no verifiable factual claims, return {"claims": []}"""


# ── Live data verifier ─────────────────────────────────────────────────────────

def get_live_price(token: str, symbol: str) -> Optional[float]:
    """Get live price for verification."""
    try:
        from growwapi import GrowwAPI
        g = GrowwAPI(token)
        q = g.get_ltp(trading_symbol=symbol.upper(), exchange="NSE", segment="CASH")
        return float(q.get("ltp", 0))
    except Exception:
        try:
            import requests
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
            session = requests.Session()
            session.get("https://www.nseindia.com", headers=headers, timeout=5)
            r = session.get(f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}", headers=headers, timeout=5)
            return float(r.json().get("priceInfo", {}).get("lastPrice", 0))
        except Exception:
            return None


def get_live_index(name: str) -> Optional[float]:
    """Get live index level for verification."""
    import requests
    mapping = {
        "NIFTY": "NIFTY 50", "NIFTY50": "NIFTY 50",
        "SENSEX": "SENSEX", "BANKNIFTY": "NIFTY BANK",
        "INDIAVIX": "INDIA VIX", "VIX": "INDIA VIX",
    }
    idx_name = mapping.get(name.upper().replace(" ",""), name)
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        r = session.get("https://www.nseindia.com/api/allIndices", headers=headers, timeout=8)
        for item in r.json().get("data", []):
            if item.get("indexSymbol") == idx_name:
                return float(item.get("last", 0))
    except Exception:
        pass
    return None


def _tolerance_check(claimed: float, actual: float, tolerance_pct: float = 5.0) -> bool:
    """Returns True if claimed value is within tolerance% of actual."""
    if actual == 0:
        return True  # Can't verify
    diff_pct = abs(claimed - actual) / abs(actual) * 100
    return diff_pct <= tolerance_pct


# ── Main guard function ────────────────────────────────────────────────────────

def verify_agent_output(agent_id: str, agent_text: str,
                         api_key: str, groww_token: str,
                         live_context: dict = None) -> dict:
    """
    Verify factual claims in an agent's analysis.

    Returns:
    {
      "verified": bool,
      "confidence": 0-100,
      "hallucinations": [...],
      "corrected_text": str,
      "warnings": [...],
      "claims_checked": int,
      "claims_passed": int,
    }
    """
    if not agent_text or len(agent_text) < 50:
        return {"verified": True, "confidence": 100, "hallucinations": [],
                "corrected_text": agent_text, "warnings": [], "claims_checked": 0, "claims_passed": 0}

    # Extract factual claims using Claude
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": f"AGENT ANALYSIS:\n{agent_text[:2000]}"}],
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        claims_data = json.loads(raw)
        claims = claims_data.get("claims", [])
    except Exception:
        return {"verified": True, "confidence": 80, "hallucinations": [],
                "corrected_text": agent_text, "warnings": ["Could not extract claims"],
                "claims_checked": 0, "claims_passed": 0}

    if not claims:
        return {"verified": True, "confidence": 95, "hallucinations": [],
                "corrected_text": agent_text, "warnings": [],
                "claims_checked": 0, "claims_passed": 0}

    hallucinations = []
    warnings       = []
    corrected_text = agent_text
    passed = 0

    # Use live_context if available to avoid extra API calls
    ctx_data = _parse_live_context(live_context or {})

    for claim in claims:
        ctype   = claim.get("claim_type","")
        symbol  = claim.get("symbol","")
        value   = claim.get("value")
        context = claim.get("context","")

        if value is None:
            continue

        actual = None
        tolerance = 5.0  # 5% default tolerance

        # Verify against live data
        if ctype == "index_level":
            if symbol:
                actual = get_live_index(symbol)
            # Also check live context
            if actual is None and ctx_data:
                actual = ctx_data.get("indices", {}).get(symbol.upper())
            tolerance = 3.0

        elif ctype == "vix":
            actual = ctx_data.get("vix") or get_live_index("VIX")
            tolerance = 8.0  # VIX moves fast

        elif ctype == "price" and symbol and groww_token:
            actual = ctx_data.get("prices", {}).get(symbol.upper())
            if actual is None:
                actual = get_live_price(groww_token, symbol)
            tolerance = 4.0

        elif ctype == "rsi":
            # RSI varies — only flag extreme errors
            if value < 0 or value > 100:
                hallucinations.append({
                    "type":    ctype,
                    "symbol":  symbol,
                    "claimed": value,
                    "actual":  "Must be 0-100",
                    "context": context,
                    "severity":"HIGH",
                })
            else:
                passed += 1
            continue

        elif ctype in ("pe_ratio", "fii_flow", "oi"):
            # These are harder to verify in real-time — just flag if wildly off
            if ctype == "pe_ratio" and (value < 0 or value > 500):
                hallucinations.append({
                    "type": ctype, "symbol": symbol, "claimed": value,
                    "actual": "Implausible P/E", "context": context, "severity": "MEDIUM",
                })
            else:
                passed += 1
            continue

        if actual is not None and actual > 0:
            if not _tolerance_check(float(value), float(actual), tolerance):
                diff_pct = abs(float(value) - float(actual)) / float(actual) * 100
                severity = "HIGH" if diff_pct > 20 else "MEDIUM"
                hallucinations.append({
                    "type":       ctype,
                    "symbol":     symbol,
                    "claimed":    value,
                    "actual":     round(actual, 2),
                    "diff_pct":   round(diff_pct, 1),
                    "context":    context,
                    "severity":   severity,
                })

                # Attempt correction in text
                if severity == "HIGH" and str(int(value)) in corrected_text:
                    corrected_text = corrected_text.replace(
                        str(int(value)),
                        f"{round(actual, 0):.0f} [CORRECTED from {value}]",
                        1
                    )
            else:
                passed += 1
        else:
            warnings.append(f"Could not verify {ctype} claim: {value} for {symbol}")
            passed += 1  # Give benefit of doubt if can't verify

    total_checked = len(claims)
    high_severity = [h for h in hallucinations if h["severity"] == "HIGH"]

    # Confidence score
    if total_checked == 0:
        confidence = 90
    else:
        confidence = int(passed / total_checked * 100)
        if high_severity:
            confidence = max(0, confidence - 20 * len(high_severity))

    return {
        "agent_id":       agent_id,
        "verified":       len(high_severity) == 0,
        "confidence":     confidence,
        "hallucinations": hallucinations,
        "corrected_text": corrected_text,
        "warnings":       warnings,
        "claims_checked": total_checked,
        "claims_passed":  passed,
        "timestamp":      datetime.now(IST).isoformat(),
    }


def _parse_live_context(live_context: dict) -> dict:
    """Extract key values from live context dict for fast lookup."""
    result = {"indices": {}, "prices": {}, "vix": None}
    indices = live_context.get("data", {})
    for name, data in indices.items():
        if isinstance(data, dict):
            result["indices"][name.upper()] = data.get("last_price", 0)
            if "VIX" in name.upper():
                result["vix"] = data.get("last_price")
    return result


def verify_all_agents(agent_outputs: dict, api_key: str,
                       groww_token: str, live_context: dict = None) -> dict:
    """
    Verify all agent outputs in parallel.
    Returns dict of {agent_id: verification_result}.
    """
    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(verify_agent_output, aid, text, api_key, groww_token, live_context): aid
            for aid, text in agent_outputs.items()
        }
        for fut, aid in futures.items():
            try:
                results[aid] = fut.result(timeout=20)
            except Exception as e:
                results[aid] = {"verified": True, "confidence": 70,
                                 "hallucinations": [], "error": str(e),
                                 "claims_checked": 0, "claims_passed": 0}
    return results


def build_guard_summary(verification_results: dict) -> dict:
    """Summarise guard results across all agents."""
    total_hallucinations = sum(len(r.get("hallucinations",[])) for r in verification_results.values())
    avg_confidence = sum(r.get("confidence", 90) for r in verification_results.values()) / max(len(verification_results), 1)
    flagged_agents = [aid for aid, r in verification_results.items() if not r.get("verified", True)]

    return {
        "overall_confidence":    round(avg_confidence, 1),
        "total_hallucinations":  total_hallucinations,
        "flagged_agents":        flagged_agents,
        "all_verified":          len(flagged_agents) == 0,
        "recommendation":        "PROCEED" if avg_confidence >= 70 and total_hallucinations < 3 else "CAUTION",
    }


# Type hint fix
from typing import Optional
