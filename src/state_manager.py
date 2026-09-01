"""
State Manager for GitHub Actions
مدیریت وضعیت بین اجراهای مختلف در GitHub Actions
با پشتیبانی از چند پوزیشن همزمان
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import uuid

logger = logging.getLogger(__name__)

STATE_FILE = Path("state.json")
MAX_POSITIONS = 5
POSITION_SIZE_RATIO = 0.2  # ۲۰٪ از موجودی برای هر معامله


def get_initial_state() -> Dict[str, Any]:
    """ایجاد وضعیت اولیه"""
    return {
        "positions": [],  # لیست پوزیشن‌های باز
        "balance": 530.0,
        "initial_balance": 530.0,
        "max_positions": MAX_POSITIONS,
        "history": [],
        "total_pnl": 0.0,
        "total_trades": 0,
        "updated_at": datetime.now().isoformat()
    }


def load_state() -> Dict[str, Any]:
    """
    بارگذاری وضعیت از فایل state.json
    """
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                
                # 🔥 تبدیل حالت قدیمی به جدید (اگه لازم باشه)
                if "in_position" in state and not "positions" in state:
                    state = _migrate_old_state(state)
                
                logger.info("✅ وضعیت از فایل بارگذاری شد")
                logger.info(f"   📊 تعداد پوزیشن‌های باز: {len(state.get('positions', []))}")
                logger.info(f"   💳 موجودی: {state.get('balance', 530.0):.2f} USDT")
                logger.info(f"   📊 سود/زیان کل: {state.get('total_pnl', 0.0):.2f} USDT")
                return state
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری وضعیت: {e}")
    
    logger.info("🆕 فایل وضعیت وجود ندارد، مقداردهی اولیه...")
    return get_initial_state()


def _migrate_old_state(old_state: Dict[str, Any]) -> Dict[str, Any]:
    """تبدیل حالت قدیمی (تک پوزیشن) به حالت جدید (چند پوزیشن)"""
    new_state = get_initial_state()
    
    # انتقال موجودی
    new_state["balance"] = old_state.get("balance", 530.0)
    new_state["initial_balance"] = old_state.get("initial_balance", 530.0)
    new_state["total_pnl"] = old_state.get("total_pnl", 0.0)
    new_state["history"] = old_state.get("history", [])
    new_state["total_trades"] = len(new_state["history"])
    
    # اگه پوزیشن باز بود، به لیست اضافه کن
    if old_state.get("in_position", False):
        position = {
            "id": str(uuid.uuid4())[:8],
            "symbol": old_state.get("symbol"),
            "side": "LONG",
            "entry_price": old_state.get("entry_price", 0),
            "position_size": old_state.get("position_size", 0),
            "stop_loss": old_state.get("stop_loss", 0),
            "take_profit": old_state.get("take_profit", 0),
            "entry_time": old_state.get("entry_time", datetime.now().isoformat()),
            "signal_data": None,
            "unrealized_pnl": 0.0,
            "status": "OPEN"
        }
        new_state["positions"].append(position)
        # موجودی قبلاً کم شده، پس نیازی به تغییر نیست
    
    logger.info("🔄 حالت قدیمی به جدید تبدیل شد")
    return new_state


def save_state(state: Dict[str, Any]) -> None:
    """ذخیره وضعیت در فایل state.json"""
    try:
        state["updated_at"] = datetime.now().isoformat()
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info("✅ وضعیت ذخیره شد")
        logger.info(f"   📊 پوزیشن‌های باز: {len(state.get('positions', []))}")
        logger.info(f"   💳 موجودی: {state.get('balance', 530.0):.2f} USDT")
        logger.info(f"   📊 سود/زیان کل: {state.get('total_pnl', 0.0):.2f} USDT")
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره وضعیت: {e}")


def can_open_new_position(state: Dict[str, Any]) -> bool:
    """بررسی امکان باز کردن پوزیشن جدید"""
    positions = state.get("positions", [])
    
    # ۱. بررسی تعداد پوزیشن‌های باز
    if len(positions) >= MAX_POSITIONS:
        logger.warning(f"⛔ حداکثر پوزیشن‌های همزمان ({MAX_POSITIONS}) پر شده")
        return False
    
    # ۲. بررسی موجودی کافی
    balance = state.get("balance", 530.0)
    min_required = balance * POSITION_SIZE_RATIO
    
    if balance < min_required:
        logger.warning(f"⛔ موجودی ناکافی: {balance:.2f} < نیاز {min_required:.2f}")
        return False
    
    # ۳. حداقل موجودی باقیمانده
    min_reserve = 10.0
    if balance - min_required < min_reserve:
        logger.warning(f"⛔ موجودی باقیمانده کمتر از {min_reserve} USDT خواهد شد")
        return False
    
    return True


def get_position_size(state: Dict[str, Any]) -> float:
    """محاسبه حجم هر پوزیشن"""
    balance = state.get("balance", 530.0)
    size = balance * POSITION_SIZE_RATIO
    return min(size, 106.0)  # حداکثر ۱۰۶ USDT


def is_symbol_in_positions(state: Dict[str, Any], symbol: str) -> bool:
    """بررسی اینکه آیا نماد در پوزیشن‌های باز وجود داره"""
    positions = state.get("positions", [])
    for pos in positions:
        if pos.get("symbol") == symbol:
            return True
    return False


def open_position(
    state: Dict[str, Any],
    symbol: str,
    price: float,
    stop_loss: float,
    take_profit: float,
    signal_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    باز کردن پوزیشن جدید
    """
    if not can_open_new_position(state):
        return state
    
    # بررسی اینکه آیا این نماد قبلاً باز شده
    if is_symbol_in_positions(state, symbol):
        logger.info(f"⏭️ {symbol} در حال حاضر در پوزیشن باز است، رد شد")
        return state
    
    position_size = get_position_size(state)
    
    # بررسی موجودی کافی
    if state["balance"] < position_size:
        logger.warning(f"⛔ موجودی ناکافی: {state['balance']:.2f} < {position_size:.2f}")
        return state
    
    # ایجاد پوزیشن جدید
    position = {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "side": "LONG",
        "entry_price": price,
        "position_size": position_size,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "entry_time": datetime.now().isoformat(),
        "signal_data": signal_data,  # 🔥 اینجا ذخیره میشه
        "unrealized_pnl": 0.0,
        "status": "OPEN"
    }
    
    # کاهش موجودی
    state["balance"] -= position_size
    
    # اضافه به لیست پوزیشن‌ها
    state["positions"].append(position)
    
    logger.info(f"✅ پوزیشن جدید باز شد:")
    logger.info(f"   📊 {symbol} @ {price:.8f}")
    logger.info(f"   💰 حجم: {position_size:.2f} USDT")
    logger.info(f"   🛑 حد ضرر: {stop_loss:.8f}")
    logger.info(f"   🎯 حد سود: {take_profit:.8f}")
    logger.info(f"   💳 موجودی باقیمانده: {state['balance']:.2f} USDT")
    logger.info(f"   📈 تعداد پوزیشن‌های باز: {len(state['positions'])}")
    
    save_state(state)
    return state


def close_position(
    state: Dict[str, Any],
    position_id: str,
    exit_price: float,
    reason: str = "manual"
) -> Dict[str, Any]:
    """
    بستن یک پوزیشن با ID مشخص
    """
    positions = state.get("positions", [])
    
    # پیدا کردن پوزیشن
    position = None
    index = -1
    for i, p in enumerate(positions):
        if p.get("id") == position_id:
            position = p
            index = i
            break
    
    if position is None:
        logger.warning(f"⚠️ پوزیشن با ID {position_id} یافت نشد")
        return state
    
    symbol = position["symbol"]
    entry_price = position["entry_price"]
    position_size = position["position_size"]
    signal_data = position.get("signal_data", {})
    
    # ================================================
    # 🔥 استخراج اطلاعات AI از signal_data
    # ================================================
    ai_signal = signal_data.get("ai_signal", "")
    ai_confidence = signal_data.get("ai_confidence", 0)
    ai_summary = signal_data.get("ai_summary", "")
    
    # محاسبه توافق AI با ربات
    side = position.get("side", "LONG")
    ai_agreement = None
    if ai_signal:
        if side == "LONG" and ai_signal.upper() == "BUY":
            ai_agreement = True
        elif side == "LONG" and ai_signal.upper() == "SELL":
            ai_agreement = False
        elif side == "SHORT" and ai_signal.upper() == "SELL":
            ai_agreement = True
        elif side == "SHORT" and ai_signal.upper() == "BUY":
            ai_agreement = False
    
    # محاسبه سود/زیان
    pnl_percent = (exit_price - entry_price) / entry_price
    gross_pnl = position_size * pnl_percent
    
    # محاسبه کارمزد (۰.۱۵٪)
    fee_rate = 0.0015
    fees = (position_size * fee_rate) + ((position_size + gross_pnl) * fee_rate)
    net_pnl = gross_pnl - fees
    
    # محاسبه مدت زمان
    duration_minutes = 0
    entry_time_str = position.get("entry_time")
    if entry_time_str:
        try:
            entry_dt = datetime.fromisoformat(entry_time_str)
            duration_minutes = (datetime.now() - entry_dt).total_seconds() / 60
        except:
            pass
    
    # به‌روزرسانی موجودی
    state["balance"] += position_size + net_pnl
    state["total_pnl"] += net_pnl
    state["total_trades"] = state.get("total_trades", 0) + 1
    
    # ثبت در تاریخچه
    trade_record = {
        "id": position_id,
        "symbol": symbol,
        "side": position["side"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "position_size": position_size,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "fees": fees,
        "pnl_percent": pnl_percent * 100,
        "entry_time": position["entry_time"],
        "exit_time": datetime.now().isoformat(),
        "close_reason": reason,
        "duration_minutes": duration_minutes,
        "signal_data": signal_data
    }
    state["history"].append(trade_record)
    
    # حذف از پوزیشن‌های باز
    state["positions"].pop(index)
    
    logger.info(f"✅ پوزیشن {symbol} بسته شد:")
    logger.info(f"   💰 سود ناخالص: {gross_pnl:+.2f} USDT")
    logger.info(f"   💰 کارمزد: {fees:.2f} USDT")
    logger.info(f"   💰 سود خالص: {net_pnl:+.2f} USDT")
    logger.info(f"   💳 موجودی جدید: {state['balance']:.2f} USDT")
    logger.info(f"   📝 دلیل: {reason}")
    logger.info(f"   📈 پوزیشن‌های باقیمانده: {len(state['positions'])}")
    
    # ================================================
    # 🔥 ثبت در CSV با اطلاعات AI
    # ================================================
    try:
        from src.trade_logger import log_trade
        log_trade(
            symbol=symbol,
            side=position["side"],
            entry_price=entry_price,
            exit_price=exit_price,
            stop_loss=position.get("stop_loss", 0),
            take_profit=position.get("take_profit", 0),
            entry_time=position["entry_time"],
            exit_time=datetime.now(),
            exit_reason=reason,
            quantity=position_size / entry_price if entry_price > 0 else 0,
            risk_amount=position_size * 0.02,
            gross_pnl=gross_pnl,
            fees=fees,
            net_pnl=net_pnl,
            rr_planned=((position.get("take_profit", 0) - entry_price) / (entry_price - position.get("stop_loss", entry_price * 0.98))) if entry_price > 0 else 0,
            rr_actual=net_pnl / (position_size * 0.02) if position_size > 0 else 0,
            duration_minutes=duration_minutes,
            signal_score=signal_data.get('score', 0) if signal_data else 0,
            rsi=signal_data.get('rsi', 0) if signal_data else 0,
            macd_line=signal_data.get('macd', 0) if signal_data else 0,
            macd_signal=signal_data.get('macd_signal', 0) if signal_data else 0,
            adx=signal_data.get('adx', 0) if signal_data else 0,
            strategy_version="v1.0",
            notes=f"Stop Loss: {position.get('stop_loss', 0)}, Take Profit: {position.get('take_profit', 0)}",
            # ================================================
            # 🔥 اطلاعات AI
            # ================================================
            ai_signal=ai_signal,
            ai_confidence=ai_confidence,
            ai_agreement=ai_agreement,
            ai_summary=ai_summary
        )
    except Exception as e:
        logger.warning(f"⚠️ خطا در ثبت CSV: {e}")
    
    save_state(state)
    return state


def check_exit_conditions(state: Dict[str, Any], symbol: str, current_price: float) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    بررسی شرایط خروج برای یک نماد خاص
    
    Returns:
        (should_close, position_id, reason)
    """
    positions = state.get("positions", [])
    
    for position in positions:
        if position.get("symbol") == symbol:
            stop_loss = position.get("stop_loss")
            take_profit = position.get("take_profit")
            
            if stop_loss and current_price <= stop_loss:
                return True, position.get("id"), "stop_loss"
            elif take_profit and current_price >= take_profit:
                return True, position.get("id"), "take_profit"
    
    return False, None, None


def check_all_positions(state: Dict[str, Any], prices: Dict[str, float]) -> List[Dict]:
    """
    بررسی همه پوزیشن‌ها و برگرداندن لیست پوزیشن‌هایی که باید بسته بشن
    """
    to_close = []
    positions = state.get("positions", [])
    
    for position in positions:
        symbol = position.get("symbol")
        if symbol not in prices:
            continue
        
        current_price = prices[symbol]
        should_close, pos_id, reason = check_exit_conditions(state, symbol, current_price)
        
        if should_close:
            to_close.append({
                "position": position,
                "position_id": pos_id,
                "exit_price": current_price,
                "reason": reason
            })
    
    return to_close


def update_unrealized_pnl(state: Dict[str, Any], prices: Dict[str, float]) -> Dict[str, Any]:
    """به‌روزرسانی سود/زیان تحقق‌نیافته همه پوزیشن‌ها"""
    positions = state.get("positions", [])
    
    for position in positions:
        symbol = position.get("symbol")
        if symbol not in prices:
            continue
        
        current_price = prices[symbol]
        entry_price = position["entry_price"]
        position_size = position["position_size"]
        
        pnl_percent = (current_price - entry_price) / entry_price
        position["unrealized_pnl"] = position_size * pnl_percent
    
    return state


def get_position_info(state: Dict[str, Any]) -> List[Dict]:
    """دریافت اطلاعات همه پوزیشن‌های باز"""
    return state.get("positions", [])


def get_performance_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """گزارش خلاصه عملکرد"""
    history = state.get("history", [])
    total_trades = len(history)
    balance = state.get("balance", 530.0)
    initial = state.get("initial_balance", 530.0)
    open_positions = state.get("positions", [])
    
    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "total_return": 0.0,
            "balance": balance,
            "initial_balance": initial,
            "open_positions": len(open_positions),
            "positions": open_positions
        }
    
    winning_trades = [t for t in history if t.get("net_pnl", t.get("realized_pnl", 0)) > 0]
    losing_trades = [t for t in history if t.get("net_pnl", t.get("realized_pnl", 0)) < 0]
    total_pnl = sum(t.get("net_pnl", t.get("realized_pnl", 0)) for t in history)
    
    return {
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": len(winning_trades) / total_trades if total_trades > 0 else 0.0,
        "total_pnl": total_pnl,
        "avg_pnl": total_pnl / total_trades if total_trades > 0 else 0.0,
        "total_return": ((balance - initial) / initial) * 100 if initial > 0 else 0.0,
        "balance": balance,
        "initial_balance": initial,
        "open_positions": len(open_positions),
        "positions": open_positions
    }


def get_total_pnl(state: Dict[str, Any]) -> float:
    """دریافت سود/زیان کل"""
    return state.get("total_pnl", 0.0)
