"""
sentiment.py — NLP Sentiment Engine
HIVE MIND ALPHA · Tier 3

Uses Claude to analyse:
1. NSE corporate announcements (FinBERT-style sentiment)
2. Earnings call transcript tone (CEO/CFO language analysis)
3. Bulk deal pattern interpretation
4. News headline sentiment aggregation

Returns structured sentiment scores injected into agent context.
"""

import anthropic
import json
import requests
from datetime import datetime, date, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")

SENTIMENT_SYSTEM = """You are a financial NLP analyst specialising in Indian equity markets.
Analyse the provided text and extract structured sentiment signals.

For each piece of text:
- Determine BULLISH / BEARISH / NEUTRAL sentiment
- Extract specific forward-looking statements
- Identify management tone (confident/cautious/defensive)
- Flag any profit warnings, guidance changes, or risk factors
- Score overall sentiment -100 (most bearish) to +100 (most bullish)

Be precise and data-driven. Focus on language that affects near-term stock price."""


def analyse_announcement_sentiment(api_key: str,
                                    announcements: list,
                                    symbol: str) -> dict:
    """
    Analyse NSE corporate announcements for sentiment.
    announcements: list of {date, subject, desc, category}
    """
    if not announcements:
        return {"success": False, "error": "No announcements to analyse"}

    combined_text = "\n\n".join([
        f"[{a.get('date','')}] {a.get('subject','')}: {a.get('desc','')[:300]}"
        for a in announcements[:5]
    ])

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system=SENTIMENT_SYSTEM,
            messages=[{"role": "user", "content": f"""
Analyse these NSE corporate announcements for {symbol.upper()}:

{combined_text}

Respond ONLY in valid JSON:
{{
  "overall_sentiment": "BULLISH"|"BEARISH"|"NEUTRAL",
  "sentiment_score": <-100 to 100>,
  "key_signals": ["signal1", "signal2", "signal3"],
  "forward_looking": "<any guidance or forward statements>",
  "risk_flags": ["risk1", "risk2"],
  "management_tone": "CONFIDENT"|"CAUTIOUS"|"DEFENSIVE"|"NEUTRAL",
  "price_impact": "POSITIVE"|"NEGATIVE"|"NEUTRAL",
  "summary": "<2-sentence summary of what this means for the stock>"
}}"""}],
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        data["success"] = True
        data["symbol"]  = symbol.upper()
        data["source"]  = "NSE Announcements"
        data["analysed_count"] = len(announcements)
        return data
    except Exception as e:
        return {"success": False, "error": str(e)}


def analyse_earnings_sentiment(api_key: str,
                                earnings_data: dict,
                                symbol: str) -> dict:
    """
    Analyse quarterly earnings data for sentiment signals.
    earnings_data: from get_latest_earnings()
    """
    if not earnings_data.get("success"):
        return {"success": False, "error": "No earnings data"}

    summary = f"""
Company: {symbol.upper()}
Period: {earnings_data.get('period','')}
Revenue: ₹{earnings_data.get('revenue_cr','N/A')} Cr
PAT: ₹{earnings_data.get('pat_cr','N/A')} Cr
EPS: {earnings_data.get('eps','N/A')}
QoQ Revenue Growth: {earnings_data.get('qoq_rev_growth','N/A')}%
QoQ PAT Growth: {earnings_data.get('qoq_pat_growth','N/A')}%
YoY Revenue Growth: {earnings_data.get('yoy_rev_growth','N/A')}%
YoY PAT Growth: {earnings_data.get('yoy_pat_growth','N/A')}%
Beat/Miss: {earnings_data.get('beat_miss','N/A')}
"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=SENTIMENT_SYSTEM,
            messages=[{"role": "user", "content": f"""
Analyse these earnings results for {symbol.upper()}:

{summary}

Based on the growth trajectory and beat/miss, assess:
1. Is this a re-rating event (big positive/negative surprise)?
2. What does the momentum suggest about next quarter?
3. Is the stock likely to gap up/down on this?

Respond ONLY in valid JSON:
{{
  "overall_sentiment": "BULLISH"|"BEARISH"|"NEUTRAL",
  "sentiment_score": <-100 to 100>,
  "earnings_quality": "STRONG_BEAT"|"BEAT"|"IN_LINE"|"MISS"|"STRONG_MISS",
  "momentum": "ACCELERATING"|"STABLE"|"DECELERATING"|"REVERSAL",
  "expected_price_reaction": "GAP_UP"|"MILD_UP"|"FLAT"|"MILD_DOWN"|"GAP_DOWN",
  "key_positives": ["p1","p2"],
  "key_negatives": ["n1","n2"],
  "summary": "<2-sentence assessment for a trader>"
}}"""}],
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        data["success"] = True
        data["symbol"]  = symbol.upper()
        data["source"]  = "Earnings Analysis"
        return data
    except Exception as e:
        return {"success": False, "error": str(e)}


def analyse_news_sentiment(api_key: str,
                            news_items: list,
                            symbol: str) -> dict:
    """
    Aggregate sentiment from news headlines using Claude.
    """
    if not news_items:
        return {"success": False, "error": "No news items"}

    headlines = "\n".join([
        f"- {n.get('title',n.get('subject',''))[:150]}"
        for n in news_items[:8]
    ])

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=SENTIMENT_SYSTEM,
            messages=[{"role": "user", "content": f"""
Analyse these news headlines about {symbol.upper()} in Indian markets:

{headlines}

Respond ONLY in valid JSON:
{{
  "overall_sentiment": "BULLISH"|"BEARISH"|"NEUTRAL",
  "sentiment_score": <-100 to 100>,
  "dominant_theme": "<main story driving sentiment>",
  "catalyst_detected": true|false,
  "catalyst_type": "EARNINGS"|"DEAL"|"REGULATORY"|"MANAGEMENT"|"MACRO"|"OTHER"|null,
  "urgency": "HIGH"|"MEDIUM"|"LOW",
  "summary": "<2-sentence assessment>"
}}"""}],
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        data["success"] = True
        data["symbol"]  = symbol.upper()
        data["items_analysed"] = len(news_items)
        return data
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_market_wide_sentiment(api_key: str) -> dict:
    """
    Aggregate market-wide sentiment from NSE announcements + economic events.
    """
    try:
        from live_data import get_market_news_today
        news = get_market_news_today()

        if not news:
            return {"success": False, "error": "No market news today"}

        headlines = "\n".join([
            f"- [{n.get('symbol','')}] {n.get('subject','')[:100]}"
            for n in news[:12]
        ])

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=SENTIMENT_SYSTEM,
            messages=[{"role": "user", "content": f"""
Today's NSE corporate announcements across the market:
{headlines}

Assess overall market sentiment from these announcements.
Respond ONLY in valid JSON:
{{
  "market_sentiment": "RISK_ON"|"RISK_OFF"|"NEUTRAL",
  "sentiment_score": <-100 to 100>,
  "sector_signals": {{"BANKING": "BULLISH/BEARISH/NEUTRAL", "IT": "...", "PHARMA": "..."}},
  "key_theme": "<dominant market theme today>",
  "summary": "<2 sentences>"
}}"""}],
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        data["success"] = True
        data["announcements_scanned"] = len(news)
        return data
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_sentiment_context(api_key: str, symbol: str = None) -> str:
    """
    Build full sentiment context string for agent injection.
    """
    import concurrent.futures
    lines = ["=" * 50, "NLP SENTIMENT ANALYSIS", "=" * 50]

    # Market-wide sentiment
    mkt_sent = get_market_wide_sentiment(api_key)
    if mkt_sent.get("success"):
        score = mkt_sent.get("sentiment_score", 0)
        emoji = "📈" if score > 20 else "📉" if score < -20 else "➡️"
        lines.append(f"\n{emoji} MARKET SENTIMENT: {mkt_sent.get('market_sentiment','N/A')} (Score: {score})")
        lines.append(f"   Theme: {mkt_sent.get('key_theme','N/A')}")
        lines.append(f"   Summary: {mkt_sent.get('summary','')}")

        sector_sigs = mkt_sent.get("sector_signals", {})
        if sector_sigs:
            lines.append("   Sector signals:")
            for sec, sig in sector_sigs.items():
                lines.append(f"     {sec}: {sig}")

    # Stock-specific if symbol provided
    if symbol:
        from live_data import get_stock_news, get_rss_news, get_latest_earnings
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            fn  = ex.submit(get_stock_news, symbol, 5)
            frss= ex.submit(get_rss_news, symbol, 5)
            fe  = ex.submit(get_latest_earnings, symbol)
        nse_news = fn.result()
        rss_news = frss.result()
        earn     = fe.result()

        all_news = nse_news + [{"subject": n["title"]} for n in rss_news]

        if all_news:
            news_sent = analyse_news_sentiment(api_key, all_news, symbol)
            if news_sent.get("success"):
                score = news_sent.get("sentiment_score", 0)
                emoji = "📈" if score > 20 else "📉" if score < -20 else "➡️"
                lines.append(f"\n{emoji} {symbol.upper()} NEWS SENTIMENT: {news_sent.get('overall_sentiment','N/A')} (Score: {score})")
                if news_sent.get("catalyst_detected"):
                    lines.append(f"   ⚡ CATALYST DETECTED: {news_sent.get('catalyst_type','')}")
                lines.append(f"   {news_sent.get('summary','')}")

        if earn.get("success"):
            earn_sent = analyse_earnings_sentiment(api_key, earn, symbol)
            if earn_sent.get("success"):
                score = earn_sent.get("sentiment_score", 0)
                emoji = "📈" if score > 20 else "📉" if score < -20 else "➡️"
                lines.append(f"\n{emoji} {symbol.upper()} EARNINGS SENTIMENT: {earn_sent.get('earnings_quality','N/A')}")
                lines.append(f"   Momentum: {earn_sent.get('momentum','N/A')}")
                lines.append(f"   Expected reaction: {earn_sent.get('expected_price_reaction','N/A')}")
                if earn_sent.get("key_positives"):
                    lines.append(f"   Positives: {', '.join(earn_sent['key_positives'][:2])}")
                if earn_sent.get("key_negatives"):
                    lines.append(f"   Risks: {', '.join(earn_sent['key_negatives'][:2])}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
