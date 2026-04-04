"""
telegram_bot.py — Telegram trade alerts + human approval + Groww execution
HIVE MIND ALPHA
"""

import requests
import json
import time
import threading
from datetime import datetime
import pytz
import streamlit as st

IST = pytz.timezone("Asia/Kolkata")


# ── Telegram API helpers ───────────────────────────────────────────────────────

def send_telegram_message(token: str, chat_id: str, text: str,
                           reply_markup: dict = None) -> dict:
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def edit_telegram_message(token: str, chat_id: str, message_id: int,
                           text: str) -> dict:
    """Edit an existing Telegram message."""
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def answer_callback_query(token: str, callback_query_id: str, text: str = "") -> dict:
    """Acknowledge a button press so the loading spinner disappears."""
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        resp = requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text,
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_updates(token: str, offset: int = 0, timeout: int = 20) -> list:
    """Long-poll for new updates (button presses)."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, params={
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": ["callback_query"],
        }, timeout=timeout + 5)
        data = resp.json()
        return data.get("result", [])
    except Exception:
        return []


# ── Trade alert formatting ─────────────────────────────────────────────────────

def format_equity_alert(trade_id: str, consensus: dict, eq: dict) -> str:
    """Format a rich equity trade alert message for Telegram."""
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

    dir_emoji  = "🟢" if direction == "BUY" else "🔴"
    st_emoji   = "🚀" if stance == "BULLISH" else "⬇️" if stance == "BEARISH" else "⚖️"

    return (
        f"🧠 <b>HIVE MIND ALPHA — TRADE SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n"
        f"📋 Trade ID: <code>{trade_id}</code>\n\n"
        f"{st_emoji} <b>Stance:</b> {stance}  |  Conviction: <b>{conviction}</b>\n"
        f"🤝 Agent Agreement: <b>{agree}%</b>\n\n"
        f"━━━━━━━━ EQUITY TRADE ━━━━━━━━\n"
        f"{dir_emoji} <b>{direction} {instrument}</b>\n\n"
        f"📥 <b>Entry:</b> {entry}\n"
        f"🛑 <b>Stop Loss:</b> {sl}\n"
        f"🎯 <b>T1 (Conservative):</b> {t1}\n"
        f"🎯 <b>T2 (Primary):</b> {t2}\n"
        f"🎯 <b>T3 (Stretch):</b> {t3}\n"
        f"⚖️ <b>Risk:Reward:</b> {rr}\n"
        f"💼 <b>Position Size:</b> {size}\n"
        f"⏱ <b>Holding Period:</b> {holding}\n\n"
        f"📌 <b>Entry Condition:</b>\n{entry_cond}\n\n"
        f"❌ <b>Invalidated If:</b>\n{inv}\n\n"
        f"💡 <b>Thesis:</b>\n<i>{thesis}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Educational purposes only. Not SEBI-registered advice.</i>"
    )


def format_options_alert(trade_id: str, consensus: dict, op: dict) -> str:
    """Format a rich options trade alert for Telegram."""
    stance     = consensus.get("overall_stance", "NEUTRAL")
    conviction = consensus.get("conviction", "—")
    agree      = consensus.get("agent_agreement_pct", "—")
    now        = datetime.now(IST).strftime("%d %b %Y %H:%M IST")

    strategy   = op.get("strategy", "—")
    underlying = op.get("underlying", "—")
    expiry     = op.get("expiry", "—")
    holding    = op.get("holding_period", "—")
    leg1       = op.get("leg_1", {})
    net_prem   = op.get("net_premium", "—")
    max_loss   = op.get("max_loss", "—")
    max_profit = op.get("max_profit", "—")
    breakeven  = op.get("breakeven", "—")
    exit_prem  = op.get("target_exit_premium", "—")
    sl_prem    = op.get("stop_loss_premium", "—")
    entry_time = op.get("ideal_entry_time", "—")
    theta      = op.get("theta_risk", "—")
    vix_cond   = op.get("vix_condition", "—")

    l1_action  = leg1.get("action", "BUY")
    l1_type    = leg1.get("type", "CE")
    l1_strike  = leg1.get("strike", "—")
    l1_prem    = leg1.get("premium", "—")
    l1_delta   = leg1.get("delta", "—")

    leg2       = op.get("leg_2", {})
    leg2_html  = ""
    if leg2.get("action") not in ("N/A", "", None):
        leg2_html = (
            f"\n🔸 <b>Leg 2:</b> {leg2.get('action','—')} "
            f"{leg2.get('type','—')} {leg2.get('strike','—')} "
            f"@ {leg2.get('premium','—')} (Δ {leg2.get('delta','—')})"
        )

    st_emoji = "🚀" if stance == "BULLISH" else "⬇️" if stance == "BEARISH" else "⚖️"

    return (
        f"🧠 <b>HIVE MIND ALPHA — OPTIONS SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n"
        f"📋 Trade ID: <code>{trade_id}</code>\n\n"
        f"{st_emoji} <b>Stance:</b> {stance}  |  Conviction: <b>{conviction}</b>\n"
        f"🤝 Agent Agreement: <b>{agree}%</b>\n\n"
        f"━━━━━━━━ OPTIONS TRADE ━━━━━━━━\n"
        f"⚡ <b>{strategy}</b>\n"
        f"📊 <b>Underlying:</b> {underlying}\n"
        f"📅 <b>Expiry:</b> {expiry}  |  Hold: {holding}\n\n"
        f"🔹 <b>Leg 1:</b> {l1_action} {l1_type} {l1_strike} "
        f"@ {l1_prem} (Δ {l1_delta})"
        f"{leg2_html}\n\n"
        f"💰 <b>Net Premium:</b> {net_prem}\n"
        f"🛑 <b>Max Loss:</b> {max_loss}\n"
        f"🎯 <b>Max Profit:</b> {max_profit}\n"
        f"⚖️ <b>Breakeven:</b> {breakeven}\n\n"
        f"✅ <b>Exit at Premium:</b> {exit_prem}\n"
        f"❌ <b>Stop at Premium:</b> {sl_prem}\n"
        f"⏰ <b>Best Entry Time:</b> {entry_time}\n"
        f"📉 <b>Theta Risk:</b> {theta}\n"
        f"📊 <b>VIX Condition:</b> {vix_cond}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Educational purposes only. Not SEBI-registered advice.</i>"
    )


def build_approval_keyboard(trade_id: str) -> dict:
    """Build inline keyboard with Approve / Reject / Details buttons."""
    return {
        "inline_keyboard": [[
            {"text": "✅ APPROVE & EXECUTE", "callback_data": f"approve_{trade_id}"},
            {"text": "❌ REJECT",           "callback_data": f"reject_{trade_id}"},
        ], [
            {"text": "📊 View Full Analysis", "callback_data": f"details_{trade_id}"},
        ]]
    }


# ── Trade sender ───────────────────────────────────────────────────────────────

def send_trade_alert(token: str, chat_id: str, trade_id: str,
                     consensus: dict, trade_type: str) -> int:
    """
    Send the appropriate trade alert and return the Telegram message_id.
    trade_type: 'equity' | 'options' | 'both'
    """
    eq = consensus.get("equity_trade", {})
    op = consensus.get("options_trade", {})
    keyboard = build_approval_keyboard(trade_id)

    # Send equity alert
    eq_msg_id = None
    if trade_type in ("equity", "both") and eq.get("applicable"):
        text = format_equity_alert(trade_id, consensus, eq)
        result = send_telegram_message(token, chat_id, text, keyboard)
        if result.get("ok"):
            eq_msg_id = result["result"]["message_id"]

    # Send options alert
    op_msg_id = None
    if trade_type in ("options", "both") and op.get("applicable"):
        text = format_options_alert(trade_id, consensus, op)
        result = send_telegram_message(token, chat_id, text, keyboard)
        if result.get("ok"):
            op_msg_id = result["result"]["message_id"]

    return eq_msg_id or op_msg_id or 0


# ── Approval poller ────────────────────────────────────────────────────────────

class ApprovalPoller:
    """
    Polls Telegram for callback_query (button press) responses.
    Run in a background thread.
    """

    def __init__(self, token: str, chat_id: str, trade_id: str,
                 timeout_seconds: int = 300):
        self.token       = token
        self.chat_id     = str(chat_id)
        self.trade_id    = trade_id
        self.timeout     = timeout_seconds
        self.result      = None          # 'approved' | 'rejected' | 'timeout'
        self.callback_id = None
        self._stop       = threading.Event()

    def poll(self):
        offset   = 0
        start    = time.time()
        while not self._stop.is_set():
            if time.time() - start > self.timeout:
                self.result = "timeout"
                break

            updates = get_updates(self.token, offset=offset, timeout=10)
            for update in updates:
                offset = update["update_id"] + 1
                cq = update.get("callback_query")
                if not cq:
                    continue

                data = cq.get("data", "")
                from_chat = str(cq.get("message", {}).get("chat", {}).get("id", ""))

                # Only process responses from our chat
                if from_chat != self.chat_id:
                    continue

                if data == f"approve_{self.trade_id}":
                    self.result      = "approved"
                    self.callback_id = cq["id"]
                    answer_callback_query(self.token, cq["id"], "✅ Executing trade…")
                    self._stop.set()
                    break

                elif data == f"reject_{self.trade_id}":
                    self.result      = "rejected"
                    self.callback_id = cq["id"]
                    answer_callback_query(self.token, cq["id"], "❌ Trade rejected.")
                    self._stop.set()
                    break

                elif data == f"details_{self.trade_id}":
                    answer_callback_query(self.token, cq["id"],
                                         "Open the Streamlit app for full analysis.")

    def start(self):
        t = threading.Thread(target=self.poll, daemon=True)
        t.start()
        return t

    def wait_for_decision(self, check_interval: float = 0.5) -> str:
        """Block until decision or timeout. Returns 'approved'|'rejected'|'timeout'."""
        start = time.time()
        while self.result is None:
            if time.time() - start > self.timeout:
                self.result = "timeout"
                break
            time.sleep(check_interval)
        return self.result


# ── Groww execution ────────────────────────────────────────────────────────────

def execute_on_groww(access_token: str, trade: dict,
                     trade_kind: str) -> dict:
    """
    Place an order on Groww via their official Python SDK.
    trade_kind: 'equity' | 'options'
    Returns dict with success, order_id, message.
    """
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(access_token)
    except ImportError:
        return {"success": False, "message": "growwapi SDK not installed. Run: pip install growwapi"}

    try:
        if trade_kind == "equity":
            symbol    = trade.get("instrument", "").upper().replace(" ", "")
            direction = trade.get("direction", "BUY")
            size_str  = trade.get("position_size", "1 share")

            # Parse quantity — user sets this; default to 1 for safety
            qty = int(trade.get("quantity", 1))

            # Parse entry price (take midpoint of range if range given)
            entry_raw = trade.get("entry_price", "0")
            entry_price = _parse_price(entry_raw)

            # Parse stop loss
            sl_raw    = trade.get("stop_loss", "0")
            sl_price  = _parse_price(sl_raw)

            # Parse target (use T2 as primary target)
            tgt_raw   = trade.get("target_2", "0")
            tgt_price = _parse_price(tgt_raw)

            # Determine product type based on holding period
            holding = trade.get("holding_period", "").lower()
            product = groww.PRODUCT_MIS if "intraday" in holding else groww.PRODUCT_CNC

            # Place main entry order
            order_resp = groww.place_order(
                trading_symbol=symbol,
                quantity=qty,
                validity=groww.VALIDITY_DAY,
                exchange=groww.EXCHANGE_NSE,
                segment=groww.SEGMENT_CASH,
                product=product,
                order_type=groww.ORDER_TYPE_LIMIT,
                transaction_type=groww.TRANSACTION_TYPE_BUY if direction == "BUY"
                                 else groww.TRANSACTION_TYPE_SELL,
                price=entry_price,
            )

            order_id = order_resp.get("groww_order_id", "")

            # Place OCO (One-Cancels-the-Other) for SL + Target if intraday
            oco_id = None
            if product == groww.PRODUCT_MIS and sl_price and tgt_price:
                oco_resp = groww.create_smart_order_oco(
                    trading_symbol=symbol,
                    quantity=qty,
                    exchange=groww.EXCHANGE_NSE,
                    segment=groww.SEGMENT_CASH,
                    product=product,
                    target={
                        "trigger_price": tgt_price,
                        "order_type": groww.ORDER_TYPE_LIMIT,
                        "price": tgt_price,
                    },
                    stop_loss={
                        "trigger_price": sl_price,
                        "order_type": "SL_M",
                        "price": None,
                    },
                )
                oco_id = oco_resp.get("smart_order_id", "")

            return {
                "success":  True,
                "order_id": order_id,
                "oco_id":   oco_id,
                "message":  f"Order placed: {direction} {qty} {symbol} @ ₹{entry_price:.2f}",
            }

        elif trade_kind == "options":
            leg1   = trade.get("leg_1", {})
            symbol = _build_options_symbol(trade, leg1)
            action = leg1.get("action", "BUY")
            prem_raw = leg1.get("premium", "0")
            premium = _parse_price(prem_raw)
            qty = int(trade.get("quantity", 1))  # in lots

            order_resp = groww.place_order(
                trading_symbol=symbol,
                quantity=qty,
                validity=groww.VALIDITY_DAY,
                exchange=groww.EXCHANGE_NSE,
                segment=groww.SEGMENT_FNO,
                product=groww.PRODUCT_MIS,
                order_type=groww.ORDER_TYPE_LIMIT,
                transaction_type=groww.TRANSACTION_TYPE_BUY if action == "BUY"
                                 else groww.TRANSACTION_TYPE_SELL,
                price=premium,
            )

            return {
                "success":  True,
                "order_id": order_resp.get("groww_order_id", ""),
                "message":  f"Options order: {action} {symbol} @ ₹{premium:.2f}",
            }

    except Exception as e:
        return {"success": False, "message": str(e)}


def _parse_price(raw: str) -> float:
    """Extract a float price from strings like '₹1,640–1,660' or '₹85–95'."""
    import re
    raw = str(raw).replace(",", "").replace("₹", "").replace(" ", "")
    # If it's a range like 1640-1660, take the midpoint
    match = re.findall(r"[\d.]+", raw)
    if not match:
        return 0.0
    nums = [float(x) for x in match]
    return sum(nums) / len(nums)


def _build_options_symbol(trade: dict, leg1: dict) -> str:
    """
    Build NSE F&O trading symbol.
    e.g. NIFTY25APR24500CE
    """
    underlying = trade.get("underlying", "NIFTY").upper()
    expiry_raw = trade.get("expiry", "")
    strike     = str(leg1.get("strike", "")).replace(",", "").replace(" ", "")
    opt_type   = leg1.get("type", "CE").upper()

    # Parse expiry to YYMMMDD format
    # Accepts formats like "24 Apr 2025", "Weekly Apr 24", "Current weekly"
    import re
    from datetime import date
    months = {"jan":"JAN","feb":"FEB","mar":"MAR","apr":"APR","may":"MAY",
              "jun":"JUN","jul":"JUL","aug":"AUG","sep":"SEP","oct":"OCT",
              "nov":"NOV","dec":"DEC"}

    expiry_str = ""
    expiry_raw_lower = expiry_raw.lower()
    for mo_key, mo_val in months.items():
        if mo_key in expiry_raw_lower:
            year_match = re.search(r"\d{4}", expiry_raw)
            yr = year_match.group()[-2:] if year_match else str(date.today().year)[-2:]
            expiry_str = yr + mo_val
            break

    if not expiry_str:
        # Default to current month
        now = datetime.now(IST)
        expiry_str = now.strftime("%y") + now.strftime("%b").upper()

    return f"{underlying}{expiry_str}{strike}{opt_type}"


# ── Confirmation messages ──────────────────────────────────────────────────────

def send_execution_confirmation(token: str, chat_id: str,
                                 order_result: dict, trade_id: str):
    """Send order execution result back to Telegram."""
    if order_result.get("success"):
        text = (
            f"✅ <b>ORDER EXECUTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 Trade ID: <code>{trade_id}</code>\n"
            f"🏦 Order ID: <code>{order_result.get('order_id','—')}</code>\n"
            f"📝 {order_result.get('message','')}\n"
        )
        if order_result.get("oco_id"):
            text += f"🔗 OCO (SL+Target): <code>{order_result['oco_id']}</code>\n"
        text += (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <i>Monitor your Groww app for order status.</i>"
        )
    else:
        text = (
            f"❌ <b>ORDER FAILED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 Trade ID: <code>{trade_id}</code>\n"
            f"💥 Error: {order_result.get('message','Unknown error')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Please check your Groww app and place manually if needed."
        )
    send_telegram_message(token, chat_id, text)


def send_rejection_confirmation(token: str, chat_id: str, trade_id: str):
    """Notify that trade was rejected."""
    text = (
        f"❌ <b>TRADE REJECTED</b>\n"
        f"Trade ID <code>{trade_id}</code> was rejected by you.\n"
        f"No order has been placed."
    )
    send_telegram_message(token, chat_id, text)


def send_timeout_notification(token: str, chat_id: str, trade_id: str):
    """Notify that approval window expired."""
    text = (
        f"⏰ <b>APPROVAL TIMEOUT</b>\n"
        f"Trade ID <code>{trade_id}</code> expired with no response.\n"
        f"No order was placed. The signal may still be valid — check the app."
    )
    send_telegram_message(token, chat_id, text)


# ── Full orchestration function ────────────────────────────────────────────────

def notify_and_await_approval(consensus: dict, groww_token: str,
                               telegram_token: str, telegram_chat_id: str,
                               approval_timeout: int = 300,
                               trade_id: str = None) -> dict:
    """
    Complete flow:
    1. Send trade alert to Telegram with Approve/Reject buttons
    2. Wait up to approval_timeout seconds for response
    3. If approved: execute on Groww, send confirmation
    4. If rejected/timeout: send notification
    Returns result dict.
    """
    import uuid
    if not trade_id:
        trade_id = str(uuid.uuid4())[:8].upper()

    eq = consensus.get("equity_trade", {})
    op = consensus.get("options_trade", {})

    has_equity  = eq.get("applicable") and eq.get("direction", "AVOID") != "AVOID"
    has_options = op.get("applicable")

    if not has_equity and not has_options:
        return {"success": False, "message": "No actionable trade in consensus"}

    trade_type = "both" if (has_equity and has_options) else \
                 "equity" if has_equity else "options"

    # Send alert
    send_trade_alert(telegram_token, telegram_chat_id, trade_id, consensus, trade_type)

    # Poll for approval
    poller = ApprovalPoller(telegram_token, telegram_chat_id,
                             trade_id, timeout_seconds=approval_timeout)
    poller.start()
    decision = poller.wait_for_decision()

    if decision == "approved":
        results = {}

        if has_equity:
            eq["quantity"] = eq.get("quantity", 1)
            r = execute_on_groww(groww_token, eq, "equity")
            results["equity"] = r
            send_execution_confirmation(telegram_token, telegram_chat_id,
                                         r, trade_id + "_EQ")

        if has_options:
            op["quantity"] = op.get("quantity", 1)
            r = execute_on_groww(groww_token, op, "options")
            results["options"] = r
            send_execution_confirmation(telegram_token, telegram_chat_id,
                                         r, trade_id + "_OP")

        return {"success": True, "decision": "approved",
                "trade_id": trade_id, "results": results}

    elif decision == "rejected":
        send_rejection_confirmation(telegram_token, telegram_chat_id, trade_id)
        return {"success": True, "decision": "rejected", "trade_id": trade_id}

    else:  # timeout
        send_timeout_notification(telegram_token, telegram_chat_id, trade_id)
        return {"success": True, "decision": "timeout", "trade_id": trade_id}


# ── Simple test function ───────────────────────────────────────────────────────

def test_telegram_connection(token: str, chat_id: str) -> bool:
    """Send a test message to verify bot connection."""
    result = send_telegram_message(
        token, chat_id,
        "✅ <b>HIVE MIND ALPHA</b> — Telegram connection confirmed!\n"
        "You will receive trade alerts here with Approve/Reject buttons."
    )
    return result.get("ok", False)
