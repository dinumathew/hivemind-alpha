"""
order_monitor.py — Order Monitor for HIVE MIND ALPHA
Polls Groww every 5 minutes for open order status.
Sends Telegram notification when SL or Target is hit.
Updates Trade Journal with exit price and P&L.
"""

import threading
import time
import json
from datetime import datetime
import pytz
import streamlit as st

IST = pytz.timezone("Asia/Kolkata")
POLL_INTERVAL_SECONDS = 300   # 5 minutes
MARKET_OPEN  = (9, 15)
MARKET_CLOSE = (15, 35)       # Slightly after 3:30 to catch final executions


def is_market_hours() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    op = now.replace(hour=MARKET_OPEN[0],  minute=MARKET_OPEN[1],  second=0, microsecond=0)
    cl = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return op <= now <= cl


# ── Groww order status fetcher ─────────────────────────────────────────────────
def get_order_status_groww(access_token: str, groww_order_id: str,
                            segment: str = "CASH") -> dict:
    """Fetch current status of a specific order from Groww."""
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(access_token)
        seg = groww.SEGMENT_CASH if segment == "CASH" else groww.SEGMENT_FNO
        resp = groww.get_order_status(
            groww_order_id=groww_order_id,
            segment=seg,
        )
        return {"success": True, "data": resp}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_all_open_orders_groww(access_token: str) -> list:
    """Fetch all open/pending orders from Groww."""
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(access_token)
        orders = []
        for seg in [groww.SEGMENT_CASH, groww.SEGMENT_FNO]:
            try:
                resp = groww.get_order_list(segment=seg)
                order_list = resp.get("order_list", []) if isinstance(resp, dict) else resp
                orders.extend(order_list or [])
            except Exception:
                pass
        return orders
    except Exception as e:
        return []


def get_smart_orders_groww(access_token: str) -> list:
    """Fetch OCO/GTT smart orders from Groww."""
    try:
        from growwapi import GrowwAPI
        groww = GrowwAPI(access_token)
        result = []
        for seg in [groww.SEGMENT_CASH, groww.SEGMENT_FNO]:
            try:
                resp = groww.get_smart_order_list(
                    segment=seg,
                    smart_order_type=groww.SMART_ORDER_TYPE_OCO,
                    status=groww.SMART_ORDER_STATUS_ACTIVE,
                    page=0,
                    page_size=50,
                )
                items = resp.get("smart_order_list", []) if isinstance(resp, dict) else resp
                result.extend(items or [])
            except Exception:
                pass
        return result
    except Exception as e:
        return []


# ── Telegram notifications ─────────────────────────────────────────────────────
def send_sl_notification(telegram_token: str, chat_id: str,
                          trade: dict, exit_price: float, pnl: float):
    """Send stop-loss hit notification to Telegram."""
    from telegram_bot import send_telegram_message
    held = _held_duration(trade.get("timestamp",""))
    pnl_pct = (pnl / max(abs(trade.get("entry_value", pnl * 10)), 1)) * 100

    text = (
        f"🛑 <b>STOP LOSS HIT — HIVE MIND ALPHA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Trade ID: <code>{trade.get('trade_id','—')}</code>\n"
        f"📊 <b>{trade.get('instrument','—')}</b> — "
        f"{'LONG' if trade.get('direction','')=='LONG' else 'SHORT'} position closed\n\n"
        f"❌ <b>SL triggered at ₹{exit_price:,.2f}</b>\n"
        f"📉 P&L: <b style='color:red'>₹{pnl:,.0f}</b> ({pnl_pct:.1f}%)\n"
        f"📥 Entry was: ₹{trade.get('entry_price','—')}\n"
        f"⏱ Held for: {held}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡 Capital protected. Max loss rule enforced.\n"
        f"🤖 <i>Next scan in 15 minutes.</i>"
    )
    send_telegram_message(telegram_token, chat_id, text)


def send_target_notification(telegram_token: str, chat_id: str,
                              trade: dict, exit_price: float,
                              pnl: float, target_level: str = "T2"):
    """Send target hit notification to Telegram."""
    from telegram_bot import send_telegram_message
    held = _held_duration(trade.get("timestamp",""))
    pnl_pct = (pnl / max(abs(trade.get("entry_value", pnl * 10)), 1)) * 100

    text = (
        f"🎯 <b>TARGET HIT — HIVE MIND ALPHA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Trade ID: <code>{trade.get('trade_id','—')}</code>\n"
        f"📊 <b>{trade.get('instrument','—')}</b> — "
        f"{'LONG' if trade.get('direction','')=='LONG' else 'SHORT'} position closed\n\n"
        f"✅ <b>{target_level} hit at ₹{exit_price:,.2f}</b>\n"
        f"📈 P&L: <b>+₹{pnl:,.0f}</b> ({pnl_pct:.1f}%)\n"
        f"📥 Entry was: ₹{trade.get('entry_price','—')}\n"
        f"⏱ Held for: {held}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Profit booked. Trade journal updated.\n"
        f"🤖 <i>Scanner continues watching for next opportunity.</i>"
    )
    send_telegram_message(telegram_token, chat_id, text)


def send_partial_exit_notification(telegram_token: str, chat_id: str,
                                    trade: dict, exit_price: float,
                                    pnl: float, target_level: str = "T1"):
    """Send T1 partial exit suggestion to Telegram with action buttons."""
    from telegram_bot import send_telegram_message, build_approval_keyboard
    import uuid
    action_id = str(uuid.uuid4())[:8].upper()
    held = _held_duration(trade.get("timestamp",""))

    text = (
        f"⚡ <b>T1 REACHED — HIVE MIND ALPHA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Trade ID: <code>{trade.get('trade_id','—')}</code>\n"
        f"📊 <b>{trade.get('instrument','—')}</b>\n\n"
        f"🎯 <b>T1 reached at ₹{exit_price:,.2f}</b>\n"
        f"📈 Unrealised P&L: <b>+₹{pnl:,.0f}</b>\n"
        f"⏱ Held for: {held}\n\n"
        f"💡 Suggestion: Book 50% here, trail SL to breakeven for remaining.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>OCO order still active. T2 and SL standing on exchange.</i>"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "📊 Keep Full Position", "callback_data": f"keep_{action_id}"},
            {"text": "💰 Book 50% Now",       "callback_data": f"partial_{action_id}"},
        ]]
    }
    send_telegram_message(telegram_token, chat_id, text, keyboard)


def send_eod_summary(telegram_token: str, chat_id: str, summary: dict):
    """Send end-of-day P&L summary."""
    from telegram_bot import send_telegram_message
    now = datetime.now(IST).strftime("%d %b %Y")
    trades_today = summary.get("trades_today", 0)
    winners = summary.get("winners", 0)
    losers  = summary.get("losers", 0)
    total_pnl = summary.get("total_pnl", 0)
    win_rate  = summary.get("win_rate", 0)
    best  = summary.get("best_trade", "—")
    worst = summary.get("worst_trade", "—")

    pnl_emoji = "📈" if total_pnl >= 0 else "📉"
    pnl_sign  = "+" if total_pnl >= 0 else ""

    text = (
        f"📊 <b>END OF DAY SUMMARY — {now}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>HIVE MIND ALPHA</b> Daily Report\n\n"
        f"📋 Trades Today: <b>{trades_today}</b>\n"
        f"✅ Winners: <b>{winners}</b>  ❌ Losers: <b>{losers}</b>\n"
        f"🎯 Win Rate: <b>{win_rate:.0f}%</b>\n\n"
        f"{pnl_emoji} <b>Total P&L: {pnl_sign}₹{abs(total_pnl):,.0f}</b>\n\n"
        f"🏆 Best Trade: {best}\n"
        f"💔 Worst Trade: {worst}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 Market opens again at 9:15 AM IST tomorrow.\n"
        f"🤖 <i>Scanner will resume automatically.</i>"
    )
    send_telegram_message(telegram_token, chat_id, text)


def _held_duration(timestamp_str: str) -> str:
    """Calculate how long a trade was held."""
    try:
        from datetime import datetime as dt
        entry_time = dt.fromisoformat(timestamp_str).replace(tzinfo=IST)
        delta = datetime.now(IST) - entry_time
        hours   = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours > 24:
            days = hours // 24
            return f"{days}d {hours % 24}h"
        elif hours > 0:
            return f"{hours}h {minutes}min"
        else:
            return f"{minutes}min"
    except Exception:
        return "—"


# ── P&L Calculator ─────────────────────────────────────────────────────────────
def calculate_pnl(entry_price: float, exit_price: float,
                  quantity: int, direction: str) -> float:
    """Calculate P&L for a closed trade."""
    if direction == "LONG":
        return (exit_price - entry_price) * quantity
    else:  # SHORT
        return (entry_price - exit_price) * quantity


def parse_price(price_str) -> float:
    """Parse price from string or float."""
    if isinstance(price_str, (int, float)):
        return float(price_str)
    import re
    nums = re.findall(r"[\d.]+", str(price_str).replace(",",""))
    if nums:
        vals = [float(n) for n in nums]
        return sum(vals) / len(vals)
    return 0.0


# ── Main monitor class ─────────────────────────────────────────────────────────
class OrderMonitor:
    """
    Background thread that polls Groww every 5 minutes.
    Monitors all executed trades from the Trade Journal.
    Sends Telegram notifications on SL or Target hit.
    """

    def __init__(self):
        self._thread        = None
        self._stop          = threading.Event()
        self.running        = False
        self.groww_token    = ""
        self.telegram_token = ""
        self.telegram_chat  = ""
        self.checks_done    = 0
        self.alerts_sent    = 0
        self.last_check     = None
        self._lock          = threading.Lock()
        self._eod_sent      = False
        self._eod_date      = None

    def configure(self, groww_token: str, telegram_token: str, telegram_chat: str):
        self.groww_token    = groww_token
        self.telegram_token = telegram_token
        self.telegram_chat  = telegram_chat

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._eod_sent = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.running = True

    def stop(self):
        self._stop.set()
        self.running = False

    def _loop(self):
        while not self._stop.is_set():
            now = datetime.now(IST)

            if is_market_hours():
                self._check_orders()
                self._eod_sent = False  # Reset for next day

            # Send EOD summary at 3:35 PM if not already sent
            eod_time = now.replace(hour=15, minute=35, second=0, microsecond=0)
            if (not self._eod_sent and
                now >= eod_time and
                now.weekday() < 5 and
                self._eod_date != now.date()):
                self._send_eod()
                self._eod_sent = True
                self._eod_date = now.date()

            # Sleep in small increments
            for _ in range(POLL_INTERVAL_SECONDS // 5):
                if self._stop.is_set():
                    break
                time.sleep(5)

    def _check_orders(self):
        """Main check — compare open trades against Groww order statuses."""
        from trade_log import get_open, update_status, update_pnl

        open_trades = get_open()
        if not open_trades:
            with self._lock:
                self.last_check = datetime.now(IST).strftime("%H:%M:%S IST")
                self.checks_done += 1
            return

        # Fetch all orders from Groww
        all_orders = get_all_open_orders_groww(self.groww_token)
        smart_orders = get_smart_orders_groww(self.groww_token)

        # Build lookup by order ID
        order_map = {}
        for o in all_orders:
            oid = o.get("groww_order_id","")
            if oid:
                order_map[oid] = o

        for trade in open_trades:
            try:
                self._check_single_trade(trade, order_map, smart_orders)
            except Exception as e:
                pass

        with self._lock:
            self.last_check  = datetime.now(IST).strftime("%H:%M:%S IST")
            self.checks_done += 1

    def _check_single_trade(self, trade: dict, order_map: dict, smart_orders: list):
        """Check one trade's order status and fire notification if needed."""
        from trade_log import update_pnl, update_status

        trade_id   = trade.get("trade_id","")
        eq         = trade.get("equity",{})
        instrument = eq.get("instrument","") or trade.get("instrument","")
        direction  = eq.get("direction","LONG")
        entry_raw  = eq.get("entry_price","0")
        sl_raw     = eq.get("stop_loss","0")
        t1_raw     = eq.get("target_1","0")
        t2_raw     = eq.get("target_2","0")
        qty        = int(eq.get("quantity", 1) or 1)
        order_id   = trade.get("order_id","")

        entry_price = parse_price(entry_raw)
        sl_price    = parse_price(sl_raw)
        t1_price    = parse_price(t1_raw)
        t2_price    = parse_price(t2_raw)

        # Check main order
        if order_id and order_id in order_map:
            order = order_map[order_id]
            status = order.get("order_status","").upper()

            if status == "COMPLETE":
                avg_fill = float(order.get("average_fill_price", entry_price) or entry_price)
                pnl = calculate_pnl(entry_price, avg_fill, qty, direction)

                # Determine if SL or target
                if direction == "LONG":
                    is_sl = avg_fill <= sl_price * 1.005  # within 0.5% of SL
                    is_t2 = t2_price > 0 and avg_fill >= t2_price * 0.995
                    is_t1 = t1_price > 0 and avg_fill >= t1_price * 0.995
                else:
                    is_sl = avg_fill >= sl_price * 0.995
                    is_t2 = t2_price > 0 and avg_fill <= t2_price * 1.005
                    is_t1 = t1_price > 0 and avg_fill <= t1_price * 1.005

                trade_info = {
                    "trade_id":    trade_id,
                    "instrument":  instrument,
                    "direction":   direction,
                    "entry_price": entry_raw,
                    "timestamp":   trade.get("timestamp",""),
                    "entry_value": entry_price * qty,
                }

                if is_sl:
                    send_sl_notification(
                        self.telegram_token, self.telegram_chat,
                        trade_info, avg_fill, pnl,
                    )
                    update_pnl(trade_id, pnl, f"₹{avg_fill:,.2f}")
                    update_status(trade_id, "CLOSED_SL", notes=f"SL hit at ₹{avg_fill:,.2f}")
                    with self._lock:
                        self.alerts_sent += 1

                elif is_t2:
                    send_target_notification(
                        self.telegram_token, self.telegram_chat,
                        trade_info, avg_fill, pnl, "T2",
                    )
                    update_pnl(trade_id, pnl, f"₹{avg_fill:,.2f}")
                    update_status(trade_id, "CLOSED_TARGET", notes=f"T2 hit at ₹{avg_fill:,.2f}")
                    with self._lock:
                        self.alerts_sent += 1

                elif is_t1 and not trade.get("t1_notified"):
                    send_partial_exit_notification(
                        self.telegram_token, self.telegram_chat,
                        trade_info, avg_fill, pnl, "T1",
                    )
                    update_status(trade_id, "EXECUTED",
                                  notes=f"T1 reached at ₹{avg_fill:,.2f} — monitoring T2")
                    with self._lock:
                        self.alerts_sent += 1

        # Also check smart OCO orders
        for smart in smart_orders:
            if smart.get("trading_symbol","").startswith(instrument[:4]):
                smart_status = smart.get("status","").upper()
                if smart_status == "TRIGGERED":
                    triggered_leg = smart.get("triggered_leg","")
                    fill = float(smart.get("trigger_price", 0) or 0)
                    if fill > 0:
                        pnl = calculate_pnl(entry_price, fill, qty, direction)
                        trade_info = {
                            "trade_id":    trade_id,
                            "instrument":  instrument,
                            "direction":   direction,
                            "entry_price": entry_raw,
                            "timestamp":   trade.get("timestamp",""),
                            "entry_value": entry_price * qty,
                        }
                        if "stop" in triggered_leg.lower() or "sl" in triggered_leg.lower():
                            send_sl_notification(self.telegram_token, self.telegram_chat,
                                                  trade_info, fill, pnl)
                            update_pnl(trade_id, pnl, f"₹{fill:,.2f}")
                        else:
                            send_target_notification(self.telegram_token, self.telegram_chat,
                                                      trade_info, fill, pnl)
                            update_pnl(trade_id, pnl, f"₹{fill:,.2f}")
                        with self._lock:
                            self.alerts_sent += 1

    def _send_eod(self):
        """Send end-of-day summary."""
        try:
            from trade_log import get_all
            today = datetime.now(IST).date()
            all_trades = get_all()
            today_trades = [
                t for t in all_trades
                if t.get("timestamp","")[:10] == str(today)
                and t.get("decision") == "approved"
            ]
            closed = [t for t in today_trades if t.get("pnl") is not None]
            winners = [t for t in closed if t.get("pnl",0) > 0]
            losers  = [t for t in closed if t.get("pnl",0) < 0]
            total_pnl = sum(t.get("pnl",0) for t in closed)

            best  = max(closed, key=lambda x: x.get("pnl",0), default=None)
            worst = min(closed, key=lambda x: x.get("pnl",0), default=None)

            summary = {
                "trades_today": len(today_trades),
                "winners":      len(winners),
                "losers":       len(losers),
                "total_pnl":    total_pnl,
                "win_rate":     len(winners)/max(len(closed),1)*100,
                "best_trade":   (f"{best.get('query','?')[:30]} +₹{best['pnl']:,.0f}" if best else "—"),
                "worst_trade":  (f"{worst.get('query','?')[:30]} ₹{worst['pnl']:,.0f}" if worst else "—"),
            }
            send_eod_summary(self.telegram_token, self.telegram_chat, summary)
        except Exception:
            pass

    def force_check(self) -> dict:
        """Run an immediate check outside the schedule."""
        self._check_orders()
        return self.status()

    def status(self) -> dict:
        with self._lock:
            return {
                "running":      self.running,
                "checks_done":  self.checks_done,
                "alerts_sent":  self.alerts_sent,
                "last_check":   self.last_check or "Never",
            }


@st.cache_resource
def get_order_monitor() -> OrderMonitor:
    return OrderMonitor()
