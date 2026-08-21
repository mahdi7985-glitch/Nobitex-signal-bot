"""
Execution Manager Module
Manages trading execution (Paper or Live)
"""

import logging
from typing import Optional, Dict, Any

from src.execution_interface import ExecutionInterface  # <-- اصلاح شده
from src.paper_executor import PaperExecutor  # <-- اصلاح شده
from config import Config

logger = logging.getLogger(__name__)


class ExecutionManager:
    """
    مدیر اجرای معاملات (Paper یا Live)
    """
    
    def __init__(self, config=Config, mode: str = 'paper'):
        self.config = config
        self.mode = mode
        self.executor: Optional[ExecutionInterface] = None
        
        self._init_executor()
    
    def _init_executor(self):
        """راه‌اندازی executor بر اساس mode"""
        if self.mode == 'paper':
            self.executor = PaperExecutor(
                config=self.config,
                initial_balance=530.0
            )
            logger.info("✅ Paper Executor initialized (Balance: 530 USDT)")
        elif self.mode == 'live':
            logger.warning("⚠️ Live Executor not implemented yet")
        else:
            raise ValueError(f"Invalid mode: {self.mode}")
    
    def process_signal(self, signal: Dict[str, Any]) -> bool:
        """پردازش سیگنال و اجرای معامله"""
        if not signal or not self.executor:
            return False
        
        action = signal.get('signal')
        if action not in ['BUY', 'SELL']:
            return False
        
        symbol = signal.get('symbol')
        price = signal.get('price', 0)
        stop_loss = signal.get('stop_loss_raw')
        take_profit = signal.get('tp1_raw')
        size = 0.25
        
        if not all([symbol, price, stop_loss, take_profit]):
            logger.error(f"❌ Invalid signal for execution: {signal}")
            return False
        
        if action == 'BUY':
            return self.executor.execute_buy(
                symbol=symbol,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=size
            )
        else:
            return self.executor.execute_sell(
                symbol=symbol,
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=size
            )
    
    def update_prices(self, prices: Dict[str, float]):
        """به‌روزرسانی قیمت‌ها و بررسی خودکار بسته‌شدن"""
        if not self.executor or self.mode != 'paper':
            return
        
        if isinstance(self.executor, PaperExecutor):
            for symbol, price in prices.items():
                self.executor.update_price(symbol, price)
    
    def get_balance(self) -> float:
        """دریافت موجودی"""
        if not self.executor:
            return 0.0
        return self.executor.get_balance()
    
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
        
        balance = self.executor.get_balance()
        positions = self.executor.get_all_positions()
        open_positions = [s for s, p in positions.items() if p.get('status') == 'OPEN']
        
        performance = {}
        if isinstance(self.executor, PaperExecutor):
            performance = self.executor.get_performance_summary()
        
        return {
            'mode': self.mode,
            'balance': balance,
            'open_positions_count': len(open_positions),
            'open_positions': open_positions,
            'performance': performance
        }
    
    def switch_mode(self, mode: str):
        """تغییر حالت (برای آینده)"""
        if mode == self.mode:
            return
        
        self.mode = mode
        self._init_executor()
        logger.info(f"🔄 Switched to {mode} mode")
