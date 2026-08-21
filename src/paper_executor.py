"""
Paper Executor Module
Simulates trading with virtual money
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from execution_interface import ExecutionInterface
from performance_tracker import PerformanceTracker
from config import Config

logger = logging.getLogger(__name__)


class PaperExecutor(ExecutionInterface):
    """
    اجرای معاملات آزمایشی (Paper Trading)
    """
    
    def __init__(self, config=Config, initial_balance: float = 530.0):
        self.config = config
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.tracker = PerformanceTracker(config)
        self.slippage_factor = 0.0015  # ۰.۱۵٪
        self.position_size = 0.25  # ۲۵٪ سرمایه
    
    def execute_buy(self, symbol: str, price: float, stop_loss: float, take_profit: float, size: float = 0.25) -> bool:
        """
        اجرای خرید آزمایشی
        
        Args:
            symbol: نماد
            price: قیمت لحظه‌ای
            stop_loss: حد ضرر
            take_profit: هدف سود
            size: درصد سرمایه (پیش‌فرض ۲۵٪)
        """
        # بررسی موجودی
        if self.current_balance <= 0:
            logger.error(f"❌ Insufficient balance for {symbol}")
            return False
        
        # اعمال Slippage
        entry_price = price * (1 + self.slippage_factor)
        position_value = self.current_balance * size
        quantity = position_value / entry_price
        
        # ثبت موقعیت
        self.positions[symbol] = {
            'type': 'BUY',
            'entry_price': price,
            'entry_price_slippage': entry_price,
            'quantity': quantity,
            'position_value': position_value,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'size': size,
            'entry_time': datetime.now().isoformat(),
            'status': 'OPEN'
        }
        
        # کاهش موجودی
        self.current_balance -= position_value
        
        # ثبت در PerformanceTracker
        self.tracker.open_paper_trade(
            symbol=symbol,
            signal_type='BUY',
            entry_price=price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=None,
            position_size=size
        )
        
        logger.info(
            f"📈 PAPER BUY: {symbol} @ {entry_price:.4f} "
            f"(Size: {size*100}%, Value: {position_value:.2f} USDT)"
        )
        return True
    
    def execute_sell(self, symbol: str, price: float, stop_loss: float, take_profit: float, size: float = 0.25) -> bool:
        """
        اجرای فروش آزمایشی
        
        Args:
            symbol: نماد
            price: قیمت لحظه‌ای
            stop_loss: حد ضرر
            take_profit: هدف سود
            size: درصد سرمایه (پیش‌فرض ۲۵٪)
        """
        # بررسی موجودی
        if self.current_balance <= 0:
            logger.error(f"❌ Insufficient balance for {symbol}")
            return False
        
        # اعمال Slippage
        entry_price = price * (1 - self.slippage_factor)
        position_value = self.current_balance * size
        quantity = position_value / entry_price
        
        # ثبت موقعیت
        self.positions[symbol] = {
            'type': 'SELL',
            'entry_price': price,
            'entry_price_slippage': entry_price,
            'quantity': quantity,
            'position_value': position_value,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'size': size,
            'entry_time': datetime.now().isoformat(),
            'status': 'OPEN'
        }
        
        # کاهش موجودی
        self.current_balance -= position_value
        
        # ثبت در PerformanceTracker
        self.tracker.open_paper_trade(
            symbol=symbol,
            signal_type='SELL',
            entry_price=price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=None,
            position_size=size
        )
        
        logger.info(
            f"📈 PAPER SELL: {symbol} @ {entry_price:.4f} "
            f"(Size: {size*100}%, Value: {position_value:.2f} USDT)"
        )
        return True
    
    def close_position(self, symbol: str) -> bool:
        """
        بستن یک موقعیت باز
        
        Args:
            symbol: نماد
        """
        if symbol not in self.positions:
            logger.warning(f"⚠️ No position found for {symbol}")
            return False
        
        position = self.positions[symbol]
        if position['status'] != 'OPEN':
            logger.warning(f"⚠️ Position {symbol} is already closed")
            return False
        
        # دریافت قیمت لحظه‌ای (از دیتابیس یا API)
        # اینجا باید از DataFetcher قیمت بگیریم
        # فعلاً فرض می‌کنیم از بیرون قیمت می‌اد
        return True
    
    def get_balance(self) -> float:
        """دریافت موجودی فعلی"""
        total_value = self.current_balance
        
        # محاسبه ارزش موقعیت‌های باز
        for symbol, position in self.positions.items():
            if position['status'] == 'OPEN':
                # ارزش موقعیت رو به موجودی اضافه می‌کنیم
                # (قیمت فعلی رو باید از API بگیریم)
                total_value += position['position_value']
        
        return total_value
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت وضعیت یک موقعیت"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """دریافت همه موقعیت‌ها"""
        return self.positions
    
    def update_price(self, symbol: str, current_price: float):
        """
        به‌روزرسانی قیمت و بررسی خودکار بسته‌شدن
        
        Args:
            symbol: نماد
            current_price: قیمت لحظه‌ای
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        if position['status'] != 'OPEN':
            return
        
        signal_type = position['type']
        stop_loss = position['stop_loss']
        take_profit = position['take_profit']
        
        should_close = False
        exit_reason = None
        
        if signal_type == 'BUY':
            if current_price <= stop_loss:
                should_close = True
                exit_reason = 'stop_loss'
            elif current_price >= take_profit:
                should_close = True
                exit_reason = 'take_profit'
        else:  # SELL
            if current_price >= stop_loss:
                should_close = True
                exit_reason = 'stop_loss'
            elif current_price <= take_profit:
                should_close = True
                exit_reason = 'take_profit'
        
        if should_close:
            self._close_position(symbol, current_price, exit_reason)
    
    def _close_position(self, symbol: str, exit_price: float, exit_reason: str):
        """
        بستن داخلی موقعیت
        """
        position = self.positions[symbol]
        signal_type = position['type']
        entry_price = position['entry_price_slippage']
        position_value = position['position_value']
        
        # اعمال Slippage روی قیمت خروج
        if signal_type == 'BUY':
            exit_with_slippage = exit_price * (1 - self.slippage_factor)
        else:  # SELL
            exit_with_slippage = exit_price * (1 + self.slippage_factor)
        
        # محاسبه سود/ضرر
        if signal_type == 'BUY':
            price_change = (exit_with_slippage - entry_price) / entry_price
        else:  # SELL
            price_change = (entry_price - exit_with_slippage) / entry_price
        
        profit_loss = position_value * price_change
        profit_loss_percent = price_change * 100
        
        # به‌روزرسانی موجودی
        self.current_balance += position_value + profit_loss
        
        # بستن موقعیت
        position['status'] = 'CLOSED'
        position['exit_price'] = exit_price
        position['exit_price_slippage'] = exit_with_slippage
        position['exit_time'] = datetime.now().isoformat()
        position['exit_reason'] = exit_reason
        position['profit_loss'] = profit_loss
        position['profit_loss_percent'] = profit_loss_percent
        
        # ثبت در PerformanceTracker
        self.tracker.close_paper_trade(
            symbol=symbol,
            exit_price=exit_price,
            exit_reason=exit_reason
        )
        
        logger.info(
            f"📉 PAPER CLOSE: {symbol} {signal_type} "
            f"P/L={profit_loss:.2f} USDT ({profit_loss_percent:.2f}%) "
            f"Reason={exit_reason}"
        )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        دریافت خلاصه عملکرد
        """
        return self.tracker.get_performance_summary()
