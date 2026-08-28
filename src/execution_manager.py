"""
Execution Manager Module
مدیریت اجرای معاملات (Paper یا Live) با هماهنگی BalanceManager
"""

import logging
from typing import Optional, Dict, Any
from decimal import Decimal

from src.execution_interface import ExecutionInterface
from src.paper_executor import PaperExecutor
from src.balance_manager import BalanceManager  # اضافه شد
from config import Config

logger = logging.getLogger(__name__)


class ExecutionManager:
    """
    مدیر اجرای معاملات با هماهنگی کامل BalanceManager
    """
    
    def __init__(self, config=Config, mode: str = 'paper'):
        self.config = config
        self.mode = mode
        self.executor: Optional[ExecutionInterface] = None
        
        # 🔥 استفاده از BalanceManager جدید
        self.balance_manager = BalanceManager(config)
        
        self._init_executor()
    
    def _init_executor(self):
        """راه‌اندازی executor بر اساس mode"""
        if self.mode == 'paper':
            self.executor = PaperExecutor(
                config=self.config,
                initial_balance=self.balance_manager.get_balance()  # از BalanceManager بگیر
            )
            logger.info(f"✅ Paper Executor initialized (Balance: {self.balance_manager.get_balance():.2f} USDT)")
        elif self.mode == 'live':
            logger.warning("⚠️ Live Executor not implemented yet")
        else:
            raise ValueError(f"Invalid mode: {self.mode}")
    
    def process_signal(self, signal: Dict[str, Any]) -> bool:
        """
        پردازش سیگنال و اجرای معامله با مدیریت سرمایه
        
        Args:
            signal: سیگنال کامل از SignalEngine
        
        Returns:
            True در صورت موفقیت
        """
        if not signal or not self.executor:
            return False
        
        action = signal.get('signal')
        if action not in ['BUY', 'SELL']:
            return False
        
        symbol = signal.get('symbol')
        price = signal.get('price', 0)
        stop_loss = signal.get('stop_loss_raw')
        take_profit = signal.get('tp1_raw')
        
        # ================================================
        # 🔥 اصلاح: محاسبه پویای حجم معامله
        # ================================================
        
        # ۱. بررسی امکان ورود به معامله
        if not self.balance_manager.can_open_new_position():
            logger.warning(f"⛔ امکان ورود به معامله {symbol} وجود ندارد")
            return False
        
        # ۲. محاسبه حجم معامله بر اساس دارایی
        position_size = self.balance_manager.get_position_size()
        
        # ۳. تنظیم حداقل و حداکثر حجم (برای امنیت)
        min_size = 0.01  # حداقل حجم
        max_size = 1.0   # حداکثر حجم
        
        if position_size < min_size:
            logger.warning(f"⚠️ حجم معامله خیلی کم است: {position_size:.4f} (حداقل: {min_size})")
            position_size = min_size
        elif position_size > max_size:
            logger.warning(f"⚠️ حجم معامله خیلی زیاد است: {position_size:.4f} (حداکثر: {max_size})")
            position_size = max_size
        
        # ۴. بررسی موجودی کافی
        if not self.executor.has_sufficient_balance(position_size):
            logger.error(f"❌ موجودی کافی برای معامله {symbol} وجود ندارد")
            return False
        
        # ================================================
        # اجرای معامله با حجم محاسبه شده
        # ================================================
        
        if action == 'BUY':
            result = self.executor.execute_buy(
                symbol=symbol,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=position_size,  # 🔥 حجم پویا
                signal_data=signal
            )
        else:  # SELL
            result = self.executor.execute_sell(
                symbol=symbol,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=position_size,  # 🔥 حجم پویا
                signal_data=signal
            )
        
        # ================================================
        # ثبت معامله در BalanceManager
        # ================================================
        if result:
            # ثبت موقعیت باز در BalanceManager
            position = self.balance_manager.open_position(
                symbol=symbol,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if position:
                logger.info(f"✅ معامله {symbol} با حجم {position_size:.4f} ثبت شد")
                return True
            else:
                logger.error(f"❌ ثبت معامله در BalanceManager ناموفق بود")
                return False
        
        return False
    
    def update_prices(self, prices: Dict[str, float]):
        """
        به‌روزرسانی قیمت‌ها و بررسی خودکار بسته‌شدن
        🔥 هماهنگ با BalanceManager
        """
        if not self.executor or self.mode != 'paper':
            return
        
        # ۱. به‌روزرسانی در PaperExecutor
        if isinstance(self.executor, PaperExecutor):
            for symbol, price in prices.items():
                self.executor.update_price(symbol, price)
        
        # ۲. به‌روزرسانی سود/زیان در BalanceManager
        for symbol, price in prices.items():
            pnl = self.balance_manager.update_position_pnl(symbol, price)
            if pnl is not None and abs(pnl) > 0.01:
                logger.debug(f"📊 {symbol}: P&L = {pnl:.2f} USDT")
        
        # ۳. بررسی خودکار برای بستن معاملات
        self._check_and_close_positions(prices)
    
    def _check_and_close_positions(self, prices: Dict[str, float]):
        """
        بررسی موقعیت‌های باز و بستن خودکار در صورت رسیدن به هدف
        """
        open_positions = self.balance_manager.get_open_positions()
        
        for position in open_positions:
            symbol = position['symbol']
            if symbol not in prices:
                continue
            
            current_price = prices[symbol]
            entry_price = position['entry_price']
            stop_loss = position.get('stop_loss')
            take_profit = position.get('take_profit')
            
            # بررسی حد ضرر
            if stop_loss and current_price <= stop_loss:
                logger.info(f"🛑 حد ضرر {symbol}: {current_price:.2f} <= {stop_loss:.2f}")
                self.close_position(symbol, current_price, "stop_loss")
                continue
            
            # بررسی حد سود
            if take_profit and current_price >= take_profit:
                logger.info(f"🎯 حد سود {symbol}: {current_price:.2f} >= {take_profit:.2f}")
                self.close_position(symbol, current_price, "take_profit")
                continue
            
            # بررسی درصدی (اختیاری)
            change_percent = (current_price - entry_price) / entry_price * 100
            
            # اگر ۱۵٪ سود کرده بود، حد سود رو به‌روز کن (Trailing Stop)
            if change_percent > 10 and position.get('trailing_activated', False) == False:
                logger.info(f"📈 {symbol}: {change_percent:.1f}% سود - فعال‌سازی Trailing Stop")
                # می‌تونید اینجا حد ضرر رو به‌روز کنید
                position['trailing_activated'] = True
                position['trailing_stop'] = current_price * 0.95  # ۵٪ پایین‌تر
    
    def close_position(self, symbol: str, exit_price: float, reason: str = "manual"):
        """
        بستن معامله و هماهنگ‌سازی با BalanceManager
        """
        # ۱. بستن در PaperExecutor
        if isinstance(self.executor, PaperExecutor):
            self.executor.close_position(symbol, exit_price)
        
        # ۲. بستن در BalanceManager
        trade_record = self.balance_manager.close_position(symbol, exit_price, reason)
        
        if trade_record:
            logger.info(f"✅ معامله {symbol} بسته شد: {reason}")
            logger.info(f"   💰 سود/زیان: {trade_record['realized_pnl']:.2f} USDT")
            logger.info(f"   💳 موجودی جدید: {self.balance_manager.get_balance():.2f} USDT")
            return trade_record
        
        return None
    
    def get_balance(self) -> float:
        """
        دریافت موجودی از BalanceManager
        🔥 اصلاح: دیگر از PaperExecutor نمی‌گیریم
        """
        return self.balance_manager.get_balance()
    
    def get_total_equity(self) -> float:
        """دریافت کل دارایی"""
        return self.balance_manager.get_total_equity()
    
    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """دریافت موقعیت‌های باز"""
        if not self.executor:
            return {}
        return self.executor.get_all_positions()
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت کامل"""
        if not self.executor:
            return {
                'mode': self.mode,
                'status': 'NOT_INITIALIZED'
            }
        
        # 🔥 دریافت وضعیت از BalanceManager
        performance_summary = self.balance_manager.get_performance_summary()
        open_positions = self.balance_manager.get_open_positions()
        
        return {
            'mode': self.mode,
            'balance': self.balance_manager.get_balance(),
            'total_equity': self.balance_manager.get_total_equity(),
            'open_positions_count': len(open_positions),
            'open_positions': [p['symbol'] for p in open_positions],
            'performance': performance_summary,
            'is_running': True
        }
    
    def switch_mode(self, mode: str):
        """تغییر حالت"""
        if mode == self.mode:
            return
        
        self.mode = mode
        self._init_executor()
        logger.info(f"🔄 Switched to {mode} mode")
    
    def reset(self, new_balance: Optional[float] = None):
        """بازنشانی کامل"""
        self.balance_manager.reset(new_balance)
        if isinstance(self.executor, PaperExecutor):
            self.executor.reset_balance(self.balance_manager.get_balance())
        logger.info("🔄 ExecutionManager reset completed")
