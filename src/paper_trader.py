"""
Paper Trader Module
مدیریت پیشرفته معاملات کاغذی با ذخیره‌سازی خودکار
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.execution_manager import ExecutionManager
from src.balance_manager import BalanceManager  # استفاده از نسخه جدید
from config import Config

logger = logging.getLogger(__name__)


class PaperTrader:
    """
    مدیریت پیشرفته Paper Trading با:
    - ذخیره و بازیابی خودکار وضعیت
    - مدیریت هوشمند دارایی
    - بررسی خودکار سیگنال‌ها
    - گزارش عملکرد
    """
    
    def __init__(self, config=Config):
        self.config = config
        
        # استفاده از BalanceManager جدید
        self.balance_manager = BalanceManager(config)
        
        # Execution Manager با حالت paper
        self.manager = ExecutionManager(config, mode='paper')
        
        # وضعیت اجرا
        self.is_running = False
        self.last_check_time = None
        self.daily_trades = 0
        self.daily_pnl = 0.0
        
        # بارگذاری وضعیت قبلی
        self._load_previous_state()
        
        logger.info("✅ Paper Trader initialized with persistence")
    
    def _load_previous_state(self):
        """بارگذاری وضعیت قبلی از BalanceManager"""
        summary = self.balance_manager.get_performance_summary()
        logger.info(f"📊 وضعیت قبلی:")
        logger.info(f"   💰 موجودی: {summary['current_balance']:.2f} USDT")
        logger.info(f"   💎 کل دارایی: {summary['total_equity']:.2f} USDT")
        logger.info(f"   📈 معاملات: {summary['total_trades']} (برد: {summary['winning_trades']})")
        logger.info(f"   🎯 نرخ برد: {summary['win_rate']*100:.1f}%")
    
    def process_signal(self, signal: Dict[str, Any]) -> bool:
        """
        پردازش سیگنال با مدیریت دارایی
        """
        # ۱. بررسی امکان ورود
        if not self.balance_manager.can_open_new_position():
            logger.warning("⛔ امکان ورود به معامله جدید وجود ندارد")
            return False
        
        # ۲. محاسبه حجم معامله
        position_size = self.balance_manager.get_position_size()
        
        # ۳. اضافه کردن حجم به سیگنال
        signal['position_size'] = position_size
        signal['position_value'] = position_size  # برای paper trading
        
        # ۴. پردازش سیگنال توسط Execution Manager
        result = self.manager.process_signal(signal)
        
        if result:
            # ۵. ثبت معامله در BalanceManager
            position = self.balance_manager.open_position(
                symbol=signal['symbol'],
                entry_price=signal['price'],
                stop_loss=signal.get('stop_loss', signal['price'] * 0.95),
                take_profit=signal.get('take_profit', signal['price'] * 1.05)
            )
            
            if position:
                logger.info(f"✅ سیگنال پردازش شد: {signal['symbol']}")
                return True
        
        return False
    
    def update_prices(self, prices: Dict[str, float]):
        """
        به‌روزرسانی قیمت‌ها و بررسی موقعیت‌های باز
        """
        # ۱. به‌روزرسانی در Execution Manager
        self.manager.update_prices(prices)
        
        # ۲. به‌روزرسانی سود/زیان موقعیت‌های باز
        for symbol, price in prices.items():
            pnl = self.balance_manager.update_position_pnl(symbol, price)
            if pnl is not None and abs(pnl) > 0.01:
                logger.debug(f"📊 {symbol}: P&L = {pnl:.2f} USDT")
        
        # ۳. بررسی خودکار برای بستن معاملات
        self._check_open_positions(prices)
    
    def _check_open_positions(self, prices: Dict[str, float]):
        """
        بررسی موقعیت‌های باز برای رسیدن به حد سود یا ضرر
        """
        open_positions = self.balance_manager.get_open_positions()
        
        for position in open_positions:
            symbol = position['symbol']
            if symbol not in prices:
                continue
            
            current_price = prices[symbol]
            entry_price = position['entry_price']
            
            # محاسبه درصد تغییر
            change_percent = (current_price - entry_price) / entry_price * 100
            
            # بررسی حد سود
            if change_percent >= position.get('take_profit_percent', 5.0):
                logger.info(f"🎯 حد سود {symbol}: {change_percent:.2f}%")
                self._close_position(symbol, current_price, "take_profit")
            
            # بررسی حد ضرر
            elif change_percent <= position.get('stop_loss_percent', -5.0):
                logger.info(f"🛑 حد ضرر {symbol}: {change_percent:.2f}%")
                self._close_position(symbol, current_price, "stop_loss")
    
    def _close_position(self, symbol: str, exit_price: float, reason: str):
        """
        بستن معامله و ثبت در تاریخچه
        """
        # ۱. بستن در Execution Manager
        self.manager.close_position(symbol, exit_price)
        
        # ۲. بستن در Balance Manager
        trade_record = self.balance_manager.close_position(symbol, exit_price, reason)
        
        if trade_record:
            # ۳. به‌روزرسانی آمار روزانه
            self.daily_trades += 1
            self.daily_pnl += trade_record['realized_pnl']
            
            logger.info(f"📊 معامله {symbol} بسته شد: {reason}")
            logger.info(f"   💰 سود/زیان: {trade_record['realized_pnl']:.2f} USDT")
    
    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت کامل
        """
        summary = self.balance_manager.get_performance_summary()
        open_positions = self.balance_manager.get_open_positions()
        
        return {
            'balance': summary['current_balance'],
            'total_equity': summary['total_equity'],
            'initial_balance': self.balance_manager.initial_balance,
            'total_pnl': summary['total_pnl'],
            'win_rate': summary['win_rate'],
            'total_trades': summary['total_trades'],
            'winning_trades': summary['winning_trades'],
            'losing_trades': summary['losing_trades'],
            'open_positions_count': len(open_positions),
            'open_positions': open_positions,
            'is_running': self.is_running,
            'daily_trades': self.daily_trades,
            'daily_pnl': self.daily_pnl
        }
    
    def get_balance(self) -> float:
        """دریافت موجودی"""
        return self.balance_manager.get_balance()
    
    def get_total_equity(self) -> float:
        """دریافت کل دارایی"""
        return self.balance_manager.get_total_equity()
    
    def run_continuous(self, check_interval: int = 60):
        """
        اجرای مداوم با بررسی خودکار
        """
        self.is_running = True
        logger.info(f"🚀 شروع Paper Trader (بررسی هر {check_interval} ثانیه)")
        
        while self.is_running:
            try:
                # ۱. دریافت وضعیت
                status = self.get_status()
                
                # ۲. نمایش خلاصه وضعیت
                if status['open_positions_count'] > 0:
                    logger.info(
                        f"📊 موجودی: {status['balance']:.2f} USDT "
                        f"| کل: {status['total_equity']:.2f} USDT "
                        f"| معاملات باز: {status['open_positions_count']}"
                    )
                else:
                    logger.info(
                        f"💤 بدون معامله باز | موجودی: {status['balance']:.2f} USDT"
                    )
                
                # ۳. بررسی معاملات (در صورت وجود سیگنال)
                # اینجا می‌تونید سیگنال‌های جدید رو چک کنید
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Paper Trader متوقف شد")
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"❌ خطا در Paper Trader: {e}")
                time.sleep(check_interval)
    
    def stop(self):
        """توقف اجرا"""
        self.is_running = False
        logger.info("🛑 توقف Paper Trader")
    
    def show_performance(self):
        """نمایش گزارش عملکرد کامل"""
        summary = self.balance_manager.get_performance_summary()
        
        print("\n" + "="*60)
        print("📊 گزارش عملکرد Paper Trader")
        print("="*60)
        print(f"💰 سرمایه اولیه: {self.balance_manager.initial_balance:.2f} USDT")
        print(f"💰 سرمایه فعلی: {summary['total_equity']:.2f} USDT")
        print(f"📈 سود/زیان کل: {summary['total_pnl']:.2f} USDT")
        print(f"📊 تعداد معاملات: {summary['total_trades']}")
        print(f"✅ معاملات برنده: {summary['winning_trades']}")
        print(f"❌ معاملات بازنده: {summary['losing_trades']}")
        print(f"🎯 نرخ برد: {summary['win_rate']*100:.1f}%")
        print(f"💵 میانگین سود: {summary['avg_pnl']:.2f} USDT")
        
        if summary.get('best_trade'):
            print(f"🏆 بهترین معامله: {summary['best_trade']['realized_pnl']:.2f} USDT ({summary['best_trade']['symbol']})")
        if summary.get('worst_trade'):
            print(f"💔 بدترین معامله: {summary['worst_trade']['realized_pnl']:.2f} USDT ({summary['worst_trade']['symbol']})")
        
        print(f"📈 معاملات باز: {summary['open_positions']}")
        print("="*60)
    
    def reset(self, new_balance: Optional[float] = None):
        """
        بازنشانی کامل ربات
        """
        self.balance_manager.reset(new_balance)
        self.daily_trades = 0
        self.daily_pnl = 0.0
        logger.info("🔄 Paper Trader بازنشانی شد")
