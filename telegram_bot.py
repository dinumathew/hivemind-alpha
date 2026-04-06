"""
telegram_bot.py — Telegram notification + non-blocking approval + Groww execution
HIVE MIND ALPHA

APPROVAL ARCHITECTURE (non-blocking):
Step 1: send_trade_alert() — fires message to Telegram, returns immediately
Step 2: check_for_approval() — called by user clicking "Check Approval" button in app
        Polls Telegram getUpdates once, looks for approve/reject callback
        If found: executes on Groww immediately
        
This two-step pattern is required for Streamlit Cloud which cannot hold
a blocking thread for 5 minutes.
"""

import requests
import json
import time
import threading
from datetime import datetime
import pytz
import uuid

IST = pytz.timezone("Asia/Kolkata")

# ── Telegram API helpers ───────────────────────────────────────────────────────

def send_telegram_message(token: str, chat_id: str, text: str,
                          reply_markup: dict = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":   chat_id,
        "text":      text,
        "parse_mode":"HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(url, json=payload, timeout=15)
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def edit_telegram_message(token: str, chat_id: str, message_id: int, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id, "message_id": message_id,
            "text": text, "parse_mode": "HTML",
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def answer_callback_query(token: str, callback_query_id: str, text: str = "") -> dict:
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        resp = requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text,
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_updates(token: str, offset: int = 0, timeout: int = 3) -> list:
    """Short-poll for updates. timeout=3 for non-blocking use."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, params={
            "offset":  offset,
            "timeout": timeout,
            "allowed_updates": ["callback_query", "message"],
        }, timeout=timeout + 5)
        data = resp.json()
        return data.get("result", [])
    except Exception:
        return []


def get_latest_offset(token: str) -> int:
    """Get the current latest update_id so we only see NEW updates after this point."""
    updates = get_updates(token, offset=0, timeout=1)
    if updates:
        return updates[-1]["update_id"] + 1
    return 0


# ── Trade alert formatting ─────────────────────────────────────────────────────

def format_equity_alert(trade_id: str, consensus: dict, eq: dict) -> str:
    stance     = consensus.get("overall_stance", "NEUTRAL")
    conviction = consensus.get("conviction", "—")
    agree      = consensus.get("agent_agreement_pct", "—")
    thesis     = consensus.get("key_thesis", "")
    now        = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    direction  = eq.get("direction", "BUY")
    instrument = eq.get("instrument", "—")
    entry      = eq.get("entry_price", "—")
    sl         = eq.get("stop_loss", "—")
    t1         = eq.get("target_1", "—")
    t2         = eq.get("target_2", "—")
    t3         = eq.get("target_3", "—")
    rr         = eq.get("risk_reward", "—")
    size       = eq.get("position_size", "—")
    holding    = eq.get("holding_period", "—")
    entry_cond = eq.get("entry_condition", "—")
    inv        = eq.get("invalidation", "—")
    de = "🟢" if direction in ("BUY","LONG") else "🔴"
    se = "🚀" if stance in ("BULLISH","LONG") else "⬇️" if stance in ("BEARISH","SHORT") else "⚖️"
    return (
        f"🧠 <b>HIVE MIND ALPHA — TRADE SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n"
        f"📋 Trade ID: <code>{trade_id}</code>\n\n"
        f"{se} <b>Stance:</b> {stance}  |  <b>{conviction}</b> conviction\n"
        f"🤝 Agent Agreement: <b>{agree}%</b>\n\n"
        f"━━━━━━━━ EQUITY TRADE ━━━━━━━━\n"
        f"{de} <b>{direction} {instrument}</b>\n\n"
        f"📥 <b>Entry:</b> {entry}\n"
        f"🛑 <b>Stop Loss:</b> {sl}\n"
        f"🎯 <b>T1:</b> {t1}  |  <b>T2:</b> {t2}  |  <b>T3:</b> {t3}\n"
        f"⚖️ <b>Risk:Reward:</b> {rr}\n"
        f"💼 <b>Size:</b> {size}\n"
        f"⏱ <b>Hold:</b> {holding}\n\n"
        f"📌 <b>Entry When:</b> {entry_cond}\n"
        f"❌ <b>Invalidated If:</b> {inv}\n\n"
        f"💡 <i>{thesis[:200]}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <b>Tap a button to decide:</b>"
    )


def format_options_alert(trade_id: str, consensus: dict, op: dict) -> str:
    stance    = consensus.get("overall_stance", "NEUTRAL")
    conviction= consensus.get("conviction", "—")
    agree     = consensus.get("agent_agreement_pct", "—")
    now       = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    strategy  = op.get("strategy", "—")
    underlying= op.get("underlying", "—")
    expiry    = op.get("expiry", "—")
    leg1      = op.get("leg_1", {})
    l1a = leg1.get("action","BUY"); l1t = leg1.get("type","CE")
    l1s = leg1.get("strike","—");   l1p = leg1.get("premium","—")
    l1d = leg1.get("delta","—")
    leg2     = op.get("leg_2", {})
    leg2_txt = ""
    if leg2.get("action") not in ("N/A","",None):
        leg2_txt = (f"\n🔸 Leg 2: {leg2.get('action','—')} {leg2.get('type','—')} "
                    f"{leg2.get('strike','—')} @ {leg2.get('premium','—')}")
    return (
        f"🧠 <b>HIVE MIND ALPHA — OPTIONS SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n"
        f"📋 Trade ID: <code>{trade_id}</code>\n\n"
        f"⚡ <b>{strategy}</b> on {underlying}  |  {conviction} conviction\n"
        f"🤝 Agreement: <b>{agree}%</b>  |  Expiry: {expiry}\n\n"
        f"🔹 Leg 1: {l1a} {l1t} {l1s} @ {l1p} (Δ {l1d})"
        f"{leg2_txt}\n\n"
        f"💰 Net Premium: {op.get('net_premium','—')}\n"
        f"🛑 Max Loss: {op.get('max_loss','—')}\n"
        f"🎯 Max Profit: {op.get('max_profit','—')}\n"
        f"⚖️ Breakeven: {op.get('breakeven','—')}\n"
        f"✅ Exit at: {op.get('target_exit_premium','—')}\n"
        f"❌ Stop at: {op.get('stop_loss_premium','—')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <b>Tap a button to decide:</b>"
    )


def build_approval_keyboard(trade_id: str) -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✅ APPROVE & EXECUTE", "callback_data": f"approve_{trade_id}"},
            {"text": "❌ REJECT",            "callback_data": f"reject_{trade_id}"},
        ], [
            {"text": "📊 View Analysis",     "callback_data": f"details_{trade_id}"},
        ]]
    }


# ── Step 1: Send alert (non-blocking) ─────────────────────────────────────────

def send_trade_alert(token: str, chat_id: str, trade_id: str,
                     consensus: dict, trade_type: str) -> dict:
    """
    Send trade alert to Telegram. Returns immediately.
    Also returns the offset to use when checking for approval later.
    """
    eq = consensus.get("equity_trade", {})
    op = consensus.get("options_trade", {})
    keyboard = build_approval_keyboard(trade_id)

    # Get offset BEFORE sending so we only catch NEW responses
    offset_before = get_latest_offset(token)

    msg_id = None
    if trade_type in ("equity", "both") and eq.get("applicable"):
        text   = format_equity_alert(trade_id, consensus, eq)
        result = send_telegram_message(token, chat_id, text, keyboard)
        if result.get("ok"):
            msg_id = result["result"]["message_id"]

    if trade_type in ("options", "both") and op.get("applicable"):
        text   = format_options_alert(trade_id, consensus, op)
        result = send_telegram_message(token, chat_id, text, keyboard)
        if result.get("ok"):
            msg_id = result["result"]["message_id"]

    return {
        "sent":          True,
        "message_id":    msg_id,
        "offset_before": offset_before,
        "trade_id":      trade_id,
    }


# ── Step 2: Check for approval (called by user clicking button) ────────────────

def check_for_approval(token: str, chat_id: str, trade_id: str,
                       offset: int = 0) -> dict:
    """
    Poll Telegram once for approve/reject callback for this trade_id.
    Returns {decision: 'approved'|'rejected'|'pending', new_offset: int}
    Call this when user clicks "Check Approval" button in the app.
    """
    updates = get_updates(token, offset=offset, timeout=3)
    new_offset = offset

    for update in updates:
        new_offset = update["update_id"] + 1
        cq = update.get("callback_query")
        if not cq:
            continue

        data      = cq.get("data", "")
        from_chat = str(cq.get("message", {}).get("chat", {}).get("id", ""))

        if from_chat != str(chat_id):
            continue

        if data == f"approve_{trade_id}":
            answer_callback_query(token, cq["id"], "✅ Processing…")
            return {"decision": "approved", "new_offset": new_offset,
                    "callback_id": cq["id"]}

        elif data == f"reject_{trade_id}":
            answer_callback_query(token, cq["id"], "❌ Rejected.")
            return {"decision": "rejected", "new_offset": new_offset}

        elif data == f"details_{trade_id}":
            answer_callback_query(token, cq["id"],
                                  "Open the Hive Mind Alpha app for full analysis.")

    return {"decision": "pending", "new_offset": new_offset}


# ── Groww execution ────────────────────────────────────────────────────────────

def execute_on_groww(access_token: str, trade: dict, trade_kind: str) -> dict:
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(access_token)
    except ImportError:
        return {"success": False, "message": "growwapi not installed. Run: pip install growwapi"}

    try:
        if trade_kind == "equity":
            symbol    = trade.get("instrument", "").upper().replace(" ", "")
            direction = trade.get("direction", "BUY")
            qty       = int(trade.get("quantity", 1))
            entry_raw = trade.get("entry_price", "0")
            sl_raw    = trade.get("stop_loss", "0")
            tgt_raw   = trade.get("target_2", "0")
            entry_price = _parse_price(entry_raw)
            sl_price    = _parse_price(sl_raw)
            tgt_price   = _parse_price(tgt_raw)
            holding     = trade.get("holding_period", "").lower()
            product     = groww.PRODUCT_MIS if "intraday" in holding else groww.PRODUCT_CNC

            order_resp = groww.place_order(
                trading_symbol   = symbol,
                quantity         = qty,
                validity         = groww.VALIDITY_DAY,
                exchange         = groww.EXCHANGE_NSE,
                segment          = groww.SEGMENT_CASH,
                product          = product,
                order_type       = groww.ORDER_TYPE_LIMIT,
                transaction_type = (groww.TRANSACTION_TYPE_BUY
                                    if direction in ("BUY","LONG")
                                    else groww.TRANSACTION_TYPE_SELL),
                price            = entry_price,
            )
            order_id = order_resp.get("groww_order_id", "")

            oco_id = None
            if product == groww.PRODUCT_MIS and sl_price and tgt_price:
                try:
                    oco_resp = groww.create_smart_order_oco(
                        trading_symbol = symbol,
                        quantity       = qty,
                        exchange       = groww.EXCHANGE_NSE,
                        segment        = groww.SEGMENT_CASH,
                        product        = product,
                        target   = {"trigger_price": tgt_price,
                                    "order_type": groww.ORDER_TYPE_LIMIT,
                                    "price": tgt_price},
                        stop_loss= {"trigger_price": sl_price,
                                    "order_type": "SL_M", "price": None},
                    )
                    oco_id = oco_resp.get("smart_order_id", "")
                except Exception:
                    pass

            return {
                "success":  True,
                "order_id": order_id,
                "oco_id":   oco_id,
                "message":  f"{direction} {qty} {symbol} @ ₹{entry_price:.2f}",
            }

        elif trade_kind == "options":
            leg1    = trade.get("leg_1", {})
            symbol  = _build_options_symbol(trade, leg1)
            action  = leg1.get("action", "BUY")
            premium = _parse_price(leg1.get("premium", "0"))
            qty     = int(trade.get("quantity", 1))

            order_resp = groww.place_order(
                trading_symbol   = symbol,
                quantity         = qty,
                validity         = groww.VALIDITY_DAY,
                exchange         = groww.EXCHANGE_NSE,
                segment          = groww.SEGMENT_FNO,
                product          = groww.PRODUCT_MIS,
                order_type       = groww.ORDER_TYPE_LIMIT,
                transaction_type = (groww.TRANSACTION_TYPE_BUY
                                    if action == "BUY"
                                    else groww.TRANSACTION_TYPE_SELL),
                price            = premium,
            )
            return {
                "success":  True,
                "order_id": order_resp.get("groww_order_id", ""),
                "message":  f"{action} {symbol} @ ₹{premium:.2f}",
            }

    except Exception as e:
        return {"success": False, "message": str(e)}

    return {"success": False, "message": "Unknown trade_kind"}


def _parse_price(raw: str) -> float:
    import re
    nums = re.findall(r"[\d.]+", str(raw).replace(",","").replace("₹","").replace(" ",""))
    if not nums:
        return 0.0
    return sum(float(x) for x in nums) / len(nums)


def _build_options_symbol(trade: dict, leg1: dict) -> str:
    import re
    from datetime import date
    underlying = trade.get("underlying", "NIFTY").upper()
    expiry_raw = trade.get("expiry", "")
    strike     = str(leg1.get("strike","")).replace(",","").replace(" ","")
    opt_type   = leg1.get("type","CE").upper()
    months = {"jan":"JAN","feb":"FEB","mar":"MAR","apr":"APR","may":"MAY",
              "jun":"JUN","jul":"JUL","aug":"AUG","sep":"SEP","oct":"OCT",
              "nov":"NOV","dec":"DEC"}
    expiry_str = ""
    for mo_k, mo_v in months.items():
        if mo_k in expiry_raw.lower():
            yr = re.search(r"\d{4}", expiry_raw)
            y  = yr.group()[-2:] if yr else str(date.today().year)[-2:]
            expiry_str = y + mo_v
            break
    if not expiry_str:
        from datetime import datetime as dt2
        import pytz as tz2
        now2 = dt2.now(tz2.timezone("Asia/Kolkata"))
        expiry_str = now2.strftime("%y") + now2.strftime("%b").upper()
    return f"{underlying}{expiry_str}{strike}{opt_type}"


# ── Execution confirmation messages ───────────────────────────────────────────

def send_execution_confirmation(token: str, chat_id: str,
                                 order_result: dict, trade_id: str):
    if order_result.get("success"):
        text = (
            f"✅ <b>ORDER EXECUTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 <code>{trade_id}</code>\n"
            f"🏦 Groww Order ID: <code>{order_result.get('order_id','—')}</code>\n"
            f"📝 {order_result.get('message','')}\n"
        )
        if order_result.get("oco_id"):
            text += f"🔗 OCO ID: <code>{order_result['oco_id']}</code>\n"
        text += (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Check your Groww app for order status."
        )
    else:
        text = (
            f"❌ <b>ORDER FAILED</b>\n"
            f"📋 <code>{trade_id}</code>\n"
            f"Error: {order_result.get('message','Unknown')}\n"
            f"Please place manually in Groww if needed."
        )
    send_telegram_message(token, chat_id, text)


def send_rejection_confirmation(token: str, chat_id: str, trade_id: str):
    send_telegram_message(token, chat_id,
        f"❌ <b>TRADE REJECTED</b>\n"
        f"<code>{trade_id}</code> — No order placed.")


def send_timeout_notification(token: str, chat_id: str, trade_id: str):
    send_telegram_message(token, chat_id,
        f"⏰ <b>APPROVAL WINDOW EXPIRED</b>\n"
        f"<code>{trade_id}</code> — No order placed.\n"
        f"Signal may still be valid. Check the app.")


def test_telegram_connection(token: str, chat_id: str) -> bool:
    result = send_telegram_message(
        token, chat_id,
        "✅ <b>HIVE MIND ALPHA</b> — Telegram connected!\n"
        "Trade alerts with Approve/Reject buttons will appear here."
    )
    return result.get("ok", False)


# ── Legacy blocking function (kept for backward compat, now shorter timeout) ───

def notify_and_await_approval(consensus: dict, groww_token: str,
                               telegram_token: str, telegram_chat_id: str,
                               approval_timeout: int = 120,
                               trade_id: str = None) -> dict:
    """
    Legacy blocking approval. Now deprecated — use send_trade_alert +
    check_for_approval instead. Kept for backward compatibility with
    scanner autonomous flow which runs in background thread.
    """
    if not trade_id:
        trade_id = str(uuid.uuid4())[:8].upper()

    eq = consensus.get("equity_trade", {})
    op = consensus.get("options_trade", {})
    has_equity  = eq.get("applicable") and eq.get("direction","AVOID") != "AVOID"
    has_options = op.get("applicable")

    if not has_equity and not has_options:
        return {"success": False, "message": "No actionable trade"}

    trade_type = ("both" if (has_equity and has_options)
                  else "equity" if has_equity else "options")

    alert_info = send_trade_alert(telegram_token, telegram_chat_id,
                                   trade_id, consensus, trade_type)
    offset = alert_info.get("offset_before", 0)

    # Poll for up to approval_timeout seconds
    start   = time.time()
    decision = "timeout"
    while time.time() - start < approval_timeout:
        check = check_for_approval(telegram_token, telegram_chat_id,
                                    trade_id, offset)
        offset = check.get("new_offset", offset)
        if check["decision"] in ("approved", "rejected"):
            decision = check["decision"]
            break
        time.sleep(4)

    if decision == "approved":
        results = {}
        if has_equity:
            r = execute_on_groww(groww_token, eq, "equity")
            results["equity"] = r
            send_execution_confirmation(telegram_token, telegram_chat_id,
                                         r, trade_id + "_EQ")
        if has_options:
            r = execute_on_groww(groww_token, op, "options")
            results["options"] = r
            send_execution_confirmation(telegram_token, telegram_chat_id,
                                         r, trade_id + "_OP")
        return {"success": True, "decision": "approved",
                "trade_id": trade_id, "results": results}

    elif decision == "rejected":
        send_rejection_confirmation(telegram_token, telegram_chat_id, trade_id)
        return {"success": True, "decision": "rejected", "trade_id": trade_id}

    else:
        send_timeout_notification(telegram_token, telegram_chat_id, trade_id)
        return {"success": True, "decision": "timeout", "trade_id": trade_id}
