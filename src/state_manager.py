"""
State Manager for GitHub Actions
مدیریت وضعیت بین اجراهای مختلف در GitHub Actions
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

STATE_FILE = Path("state.json")


def load_state() -> Dict[str, Any]:
    """
    بارگذاری وضعیت از فایل state.json
    
    Returns:
        Dictionary containing current state
    """
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                logger.info("✅ وضعیت از فایل بارگذاری شد")
                logger.info(f"   📊 در پوزیشن: {state.get('in_position', False)}")
                if state.get('in_position'):
                    logger.info(f"   📈 نماد: {state.get('symbol')}")
                    logger.info(f"   💰 قیمت ورود: {state.get('entry_price')}")
                logger.info(f"   💳 موجودی: {state.get('balance', 530.0):.2f} USDT")
                logger.info(f"   📊 سود/زیان کل: {state.get('total_pnl', 0.0):.2f} USDT")
                return state
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری وضعیت: {e}")
    
    # مقداردهی اولیه
    logger.info("🆕 فایل وضعیت وجود ندارد، مقداردهی اولیه...")
    return get_initial_state()


def get_initial_state() -> Dict[str, Any]:
    """ایجاد وضعیت اولیه"""
    return {
        "in_position": False,
        "symbol": None,
        "entry_price": 0.0,
        "position_size": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "entry_time": None,
        "history": [],
        "total_pnl": 0.0,
        "balance": 530.0,
        "initial_balance": 530.0,
        "updated_at": datetime.now().isoformat()
    }


def save_state(state: Dict[str, Any]) -> None:
    """
    ذخیره وضعیت در فایل state.json
    """
    try:
        state["updated_at"] = datetime.now().isoformat()
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info("✅ وضعیت ذخیره شد")
        logger.info(f"   📊 در پوزیشن: {state.get('in_position', False)}")
        logger.info(f"   💳 موجودی: {state.get('balance', 530.0):.2f} USDT")
        logger.info(f"   📊 سود/زیان کل: {state.get('total_pnl', 0.0):.2f} USDT")
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره وضعیت: {e}")


def open_position(
    state: Dict[str, Any],
    symbol: str,
    price: float,
    amount: float,
    stop_loss: float,
    take_profit: float
) -> Dict[str, Any]:
    """
    باز کردن پوزیشن جدید
    
    Args:
        state: وضعیت فعلی
        symbol: نماد معاملاتی
        price: قیمت ورود
        amount: حجم معامله به USDT
        stop_loss: قیمت حد ضرر
        take_profit: قیمت حد سود
    
    Returns:
        وضعیت به‌روزرسانی شده
    """
    if state.get("in_position", False):
        logger.warning("⚠️ پوزیشن باز است! نمی‌توان پوزیشن جدید باز کرد")
        return state
    
    # بررسی موجودی کافی
    balance = state.get("balance", 530.0)
    if balance < amount:
        logger.warning(f"⛔ موجودی ناکافی: {balance:.2f} < {amount:.2f}")
        return state
    
    # بررسی حداقل موجودی باقیمانده
    min_reserve = 10.0
    if balance - amount < min_reserve:
        logger.warning(f"⛔ موجودی باقیمانده کمتر از {min_reserve} USDT خواهد شد")
        return state
    
    # باز کردن پوزیشن
    state["in_position"] = True
    state["symbol"] = symbol
    state["entry_price"] = price
    state["position_size"] = amount
    state["stop_loss"] = stop_loss
    state["take_profit"] = take_profit
    state["entry_time"] = datetime.now().isoformat()
    state["balance"] -= amount
    
    logger.info(f"✅ پوزیشن باز شد:")
    logger.info(f"   📊 {symbol} @ {price:.4f}")
    logger.info(f"   💰 حجم: {amount:.2f} USDT")
    logger.info(f"   🛑 حد ضرر: {stop_loss:.4f}")
    logger.info(f"   🎯 حد سود: {take_profit:.4f}")
    logger.info(f"   💳 موجودی باقیمانده: {state['balance']:.2f} USDT")
    
    return state


def close_position(
    state: Dict[str, Any],
    exit_price: float,
    reason: str = "manual"
) -> Dict[str, Any]:
    """
    بستن پوزیشن و ثبت سود/زیان
    
    Args:
        state: وضعیت فعلی
        exit_price: قیمت خروج
        reason: دلیل خروج (take_profit, stop_loss, signal_sell, manual)
    
    Returns:
        وضعیت به‌روزرسانی شده
    """
    if not state.get("in_position", False):
        logger.warning("⚠️ پوزیشنی برای بستن وجود ندارد")
        return state
    
    entry_price = state["entry_price"]
    position_size = state["position_size"]
    symbol = state["symbol"]
    
    # محاسبه سود/زیان
    pnl_percent = (exit_price - entry_price) / entry_price
    realized_pnl = position_size * pnl_percent
    
    # به‌روزرسانی موجودی
    state["balance"] += position_size + realized_pnl
    
    # ثبت در تاریخچه
    trade = {
        "symbol": symbol,
        "entry_price": round(entry_price, 8),
        "exit_price": round(exit_price, 8),
        "position_size": position_size,
        "realized_pnl": round(realized_pnl, 4),
        "pnl_percent": round(pnl_percent * 100, 2),
        "entry_time": state["entry_time"],
        "exit_time": datetime.now().isoformat(),
        "close_reason": reason
    }
    
    state["history"].append(trade)
    state["total_pnl"] += realized_pnl
    
    # بازنشانی وضعیت پوزیشن
    state["in_position"] = False
    state["symbol"] = None
    state["entry_price"] = 0.0
    state["position_size"] = 0.0
    state["stop_loss"] = 0.0
    state["take_profit"] = 0.0
    state["entry_time"] = None
    
    # محاسبه درصد سود/زیان نسبت به سرمایه اولیه
    initial = state.get("initial_balance", 530.0)
    total_return = ((state["balance"] - initial) / initial) * 100
    
    logger.info(f"✅ پوزیشن بسته شد:")
    logger.info(f"   📊 {symbol}")
    logger.info(f"   💰 سود/زیان: {realized_pnl:+.2f} USDT ({pnl_percent*100:+.2f}%)")
    logger.info(f"   💳 موجودی جدید: {state['balance']:.2f} USDT")
    logger.info(f"   📊 بازده کل: {total_return:+.2f}%")
    logger.info(f"   📝 دلیل: {reason}")
    
    return state


def check_exit_conditions(state: Dict[str, Any], current_price: float) -> Tuple[bool, Optional[str]]:
    """
    بررسی شرایط خروج (حد سود/ضرر)
    
    Args:
        state: وضعیت فعلی
        current_price: قیمت فعلی
    
    Returns:
        (should_close, reason)
    """
    if not state.get("in_position", False):
        return False, None
    
    stop_loss = state.get("stop_loss")
    take_profit = state.get("take_profit")
    
    if stop_loss and current_price <= stop_loss:
        return True, "stop_loss"
    elif take_profit and current_price >= take_profit:
        return True, "take_profit"
    
    return False, None


def get_total_pnl(state: Dict[str, Any]) -> float:
    """دریافت سود/زیان کل"""
    return state.get("total_pnl", 0.0)


def get_performance_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """گزارش خلاصه عملکرد"""
    history = state.get("history", [])
    total_trades = len(history)
    balance = state.get("balance", 530.0)
    initial = state.get("initial_balance", 530.0)
    
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
            "in_position": state.get("in_position", False)
        }
    
    winning_trades = [t for t in history if t.get("realized_pnl", 0) > 0]
    losing_trades = [t for t in history if t.get("realized_pnl", 0) < 0]
    total_pnl = sum(t.get("realized_pnl", 0) for t in history)
    
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
        "in_position": state.get("in_position", False),
        "symbol": state.get("symbol") if state.get("in_position") else None
    }


def get_position_info(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """دریافت اطلاعات پوزیشن باز"""
    if not state.get("in_position", False):
        return None
    
    return {
        "symbol": state.get("symbol"),
        "entry_price": state.get("entry_price"),
        "position_size": state.get("position_size"),
        "stop_loss": state.get("stop_loss"),
        "take_profit": state.get("take_profit"),
        "entry_time": state.get("entry_time"),
        "current_pnl": state.get("unrealized_pnl", 0.0)
    }


def update_unrealized_pnl(state: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    """به‌روزرسانی سود/زیان تحقق‌نیافته"""
    if not state.get("in_position", False):
        return state
    
    entry_price = state["entry_price"]
    position_size = state["position_size"]
    
    pnl_percent = (current_price - entry_price) / entry_price
    state["unrealized_pnl"] = position_size * pnl_percent
    
    return state
