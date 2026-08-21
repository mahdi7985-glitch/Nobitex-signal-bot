"""
Paper Trader Module
Simple wrapper for paper trading with auto-check loop
"""

import logging
import time
from typing import Optional, Dict, Any

from execution_manager import ExecutionManager
from config import Config

logger = logging.getLogger(__name__)


class PaperTrader:
    """
    مدیریت ساده Paper Trading با حلقه خودکار
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.manager = ExecutionManager(config, mode='paper')
        self.is_running = False
    
    def process_signal(self, signal: Dict[str, Any]) -> bool:
        """پردازش یک سیگنال"""
        return self.manager.process_signal(signal)
    
    def update_price(self, symbol: str, price: float):
        """به‌روزرسانی قیمت یک نماد"""
        self.manager.update_prices({symbol: price})
    
    def update_prices(self, prices: Dict[str, float]):
        """به‌روزرسانی قیمت‌ها"""
        self.manager.update_prices(prices)
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت"""
        return self.manager.get_status()
    
    def get_balance(self) -> float:
        """دریافت موجودی"""
        return self.manager.get_balance()
    
    def run_continuous(self, check_interval: int = 60):
        """
        اجرای مداوم با بررسی خودکار
        
        Args:
            check_interval: فاصله زمانی بین بررسی‌ها (ثانیه)
        """
        self.is_running = True
        logger.info(f"🚀 Starting Paper Trader (check every {check_interval}s)")
        
        while self.is_running:
            try:
                # اینجا باید قیمت‌ها رو از DataFetcher بگیریم
                # فعلاً فقط وضعیت رو نمایش می‌دهیم
                status = self.get_status()
                
                if status.get('open_positions_count', 0) > 0:
                    logger.info(
                        f"📊 Balance: {status['balance']:.2f} USDT "
                        f"| Open: {status['open_positions_count']}"
                    )
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Paper Trader stopped by user")
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"❌ Error in paper trader: {e}")
                time.sleep(check_interval)
    
    def stop(self):
        """توقف اجرا"""
        self.is_running = False
