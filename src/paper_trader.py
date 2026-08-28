"""
Paper Trader Module
مدیریت پیشرفته معاملات کاغذی با ذخیره‌سازی خودکار
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.execution_manager import ExecutionManager
from src.balance_manager import BalanceManager
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
        
        # 🔥 استفاده از get() با مقدار پیش‌فرض
        total_trades = summary.get('total_trades', 0)
        winning_trades = summary.get('winning_trades', 0)
        win_rate = summary.get('win_rate', 0) * 100
        
        logger.info(f"📊 وضعیت قبلی:")
        logger.info(f"   💰 موجودی: {summary.get('current_balance', 0):.2f} USDT")
        logger.info(f"   💎 کل دارایی: {summary.get('total_equity', 0):.2f} USDT")
        logger.info(f"   📈 معاملات: {total_trades} (برد: {winning_trades})")
        logger.info(f"   🎯 نرخ برد: {win_rate:.1f}%")
    
    def process_signal(self, signal: Dict[str, Any]) -> bool:
        """
        پردازش سیگنال با مدیریت دارایی
        
        🔥 اصلاح: جلوگیری از ثبت دوباره معامله
        """
        # ۱. بررسی امکان ورود
        if not self.balance_manager.can_open_new_position():
            logger.warning("⛔ امکان ورود به معامله جدید وجود ندارد")
            return False
        
        # ۲. محاسبه حجم معامله
        position_size = self.balance_manager.get_position_size()
        
        # ۳. اضافه کردن حجم به سیگنال
        signal['position_size'] = position_size
        signal['position_value'] = position_size
        
        # ================================================
        # 🔥 بررسی اینکه آیا همین سیگنال قبلاً پردازش شده
        # ================================================
        symbol = signal.get('symbol')
        open_positions = self.balance_manager.get_open_positions()
        
        for pos in open_positions:
            if pos.get('symbol') == symbol:
                logger.info(f"⏭️ {symbol} در حال حاضر در معامله باز است، رد شد")
                return False
        
        # ۴. پردازش سیگنال توسط Execution Manager
        result = self.manager.process_signal(signal)
        
        # ================================================
        # 🔥 حذف ثبت دوباره معامله (ExecutionManager خودش ثبت میکنه)
        # ================================================
        # دیگر اینجا دوباره ثبت نمی‌کنیم چون ExecutionManager قبلاً ثبت کرده
        # if result:
        #     position = self.balance_manager.open_position(...)
        
        if result:
            logger.info(f"✅ سیگنال پردازش شد: {symbol}")
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
            
            # محاسبه درصد تغییر با استفاده از stop_loss و take_profit واقعی
            stop_loss = position.get('stop_loss')
            take_profit = position.get('take_profit')
            
            # بررسی حد سود
            if take_profit and current_price >= take_profit:
                logger.info(f"🎯 حد سود {symbol}: {current_price:.4f} >= {take_profit:.4f}")
                self._close_position(symbol, current_price, "take_profit")
                continue
            
            # بررسی حد ضرر
            if stop_loss and current_price <= stop_loss:
                logger.info(f"🛑 حد ضرر {symbol}: {current_price:.4f} <= {stop_loss:.4f}")
                self._close_position(symbol, current_price, "stop_loss")
                continue
    
    def _close_position(self, symbol: str, exit_price: float, reason: str):
        """
        بستن معامله و ثبت در تاریخچه
        """
        # ۱. بستن در Execution Manager
        self.manager.close_position(symbol, exit_price, reason)
        
        # ۲. بستن در Balance Manager (توسط ExecutionManager انجام میشه)
        # اما برای هماهنگی، دوباره نمی‌بندیم
        
        # به‌روزرسانی آمار روزانه
        self.daily_trades += 1
        self.daily_pnl += 0  # مقدار دقیق از trade_record گرفته میشه
        
        logger.info(f"📊 معامله {symbol} بسته شد: {reason}")
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت کامل"""
        summary = self.balance_manager.get_performance_summary()
        open_positions = self.balance_manager.get_open_positions()
        
        return {
            'balance': summary.get('current_balance', 0),
            'total_equity': summary.get('total_equity', 0),
            'initial_balance': self.balance_manager.initial_balance,
            'total_pnl': summary.get('total_pnl', 0),
            'win_rate': summary.get('win_rate', 0),
            'total_trades': summary.get('total_trades', 0),
            'winning_trades': summary.get('winning_trades', 0),
            'losing_trades': summary.get('losing_trades', 0),
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
        """اجرای مداوم با بررسی خودکار"""
        self.is_running = True
        logger.info(f"🚀 شروع Paper Trader (بررسی هر {check_interval} ثانیه)")
        
        while self.is_running:
            try:
                status = self.get_status()
                
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
        print(f"💰 سرمایه فعلی: {summary.get('total_equity', 0):.2f} USDT")
        print(f"📈 سود/زیان کل: {summary.get('total_pnl', 0):.2f} USDT")
        print(f"📊 تعداد معاملات: {summary.get('total_trades', 0)}")
        print(f"✅ معاملات برنده: {summary.get('winning_trades', 0)}")
        print(f"❌ معاملات بازنده: {summary.get('losing_trades', 0)}")
        print(f"🎯 نرخ برد: {summary.get('win_rate', 0)*100:.1f}%")
        print(f"💵 میانگین سود: {summary.get('avg_pnl', 0):.2f} USDT")
        
        best_trade = summary.get('best_trade')
        worst_trade = summary.get('worst_trade')
        if best_trade:
            print(f"🏆 بهترین معامله: {best_trade['realized_pnl']:.2f} USDT ({best_trade['symbol']})")
        if worst_trade:
            print(f"💔 بدترین معامله: {worst_trade['realized_pnl']:.2f} USDT ({worst_trade['symbol']})")
        
        print(f"📈 معاملات باز: {summary.get('open_positions', 0)}")
        print("="*60)
    
    def reset(self, new_balance: Optional[float] = None):
        """بازنشانی کامل ربات"""
        self.balance_manager.reset(new_balance)
        self.daily_trades = 0
        self.daily_pnl = 0.0
        logger.info("🔄 Paper Trader بازنشانی شد")
