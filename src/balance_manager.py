"""
Balance Manager Module
مدیریت پیشرفته دارایی با قابلیت ذخیره‌سازی موقعیت‌های باز
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """مدل موقعیت معاملاتی"""
    symbol: str
    entry_price: float
    position_size: float
    entry_time: str
    stop_loss: float
    take_profit: float
    side: str = "LONG"
    unrealized_pnl: float = 0.0
    status: str = "open"


@dataclass
class PortfolioState:
    """وضعیت کامل پورتفوی"""
    current_balance: float
    total_equity: float
    initial_balance: float
    open_positions: List[Dict]
    closed_trades: List[Dict]
    updated_at: str
    
    def to_dict(self):
        return {
            'current_balance': self.current_balance,
            'total_equity': self.total_equity,
            'initial_balance': self.initial_balance,
            'open_positions': self.open_positions,
            'closed_trades': self.closed_trades[-100:],  # فقط ۱۰۰ معامله آخر
            'updated_at': self.updated_at
        }


class BalanceManager:
    """
    مدیریت پیشرفته دارایی با پشتیبانی از:
    - ذخیره و بازیابی خودکار
    - مدیریت موقعیت‌های باز
    - محاسبه سود/زیان تحقق‌نیافته
    - جلوگیری از ریست شدن دارایی
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.balance_file = config.DATA_DIR / "portfolio_state.json"
        self.initial_balance = 530.0
        
        # تنظیمات مدیریت سرمایه
        self.max_positions = 3  # حداکثر معاملات همزمان
        self.position_size_ratio = 0.2  # ۲۰٪ از کل دارایی برای هر معامله
        
        # بارگذاری وضعیت
        self._load_or_initialize()
    
    def _load_or_initialize(self):
        """بارگذاری وضعیت یا مقداردهی اولیه"""
        if self.balance_file.exists():
            try:
                with open(self.balance_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    self._balance = data.get('current_balance', self.initial_balance)
                    self._total_equity = data.get('total_equity', self._balance)
                    self._open_positions = data.get('open_positions', [])
                    self._closed_trades = data.get('closed_trades', [])
                    
                    logger.info(f"✅ وضعیت بازیابی شد:")
                    logger.info(f"   💰 موجودی نقد: {self._balance:.2f} USDT")
                    logger.info(f"   📊 کل دارایی: {self._total_equity:.2f} USDT")
                    logger.info(f"   📈 معاملات باز: {len(self._open_positions)}")
                    logger.info(f"   📉 تاریخچه: {len(self._closed_trades)} معامله")
                    return
            except Exception as e:
                logger.error(f"❌ خطا در بارگذاری: {e}")
        
        # مقداردهی اولیه
        self._balance = self.initial_balance
        self._total_equity = self.initial_balance
        self._open_positions = []
        self._closed_trades = []
        logger.info(f"💰 شروع با سرمایه: {self.initial_balance:.2f} USDT")
        self._save_state()
    
    def _save_state(self):
        """ذخیره وضعیت کامل پورتفوی"""
        try:
            self.balance_file.parent.mkdir(parents=True, exist_ok=True)
            
            state = PortfolioState(
                current_balance=self._balance,
                total_equity=self._total_equity,
                initial_balance=self.initial_balance,
                open_positions=self._open_positions,
                closed_trades=self._closed_trades,
                updated_at=datetime.now().isoformat()
            )
            
            with open(self.balance_file, 'w', encoding='utf-8') as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره وضعیت: {e}")
    
    # ============ متدهای عمومی ============
    
    def get_balance(self) -> float:
        """دریافت موجودی نقد"""
        return self._balance
    
    def get_total_equity(self) -> float:
        """دریافت کل دارایی (با احتساب سود/زیان موقعیت‌های باز)"""
        return self._total_equity
    
    def get_open_positions(self) -> List[Dict]:
        """دریافت لیست موقعیت‌های باز"""
        return self._open_positions
    
    def can_open_new_position(self) -> bool:
        """
        بررسی امکان باز کردن معامله جدید
        
        🔥 اصلاح شده:
        - بررسی دقیق موجودی نقد
        - جلوگیری از موجودی منفی
        - بررسی حداقل موجودی مورد نیاز
        """
        # ۱. بررسی تعداد معاملات باز
        if len(self._open_positions) >= self.max_positions:
            logger.warning(f"⛔ حداکثر معاملات همزمان ({self.max_positions}) پر شده")
            return False
        
        # ۲. محاسبه حجم معامله پیشنهادی
        position_size = self.get_position_size()
        
        # ۳. بررسی موجودی نقد کافی
        if self._balance < position_size:
            logger.warning(f"⛔ موجودی ناکافی: {self._balance:.2f} < نیاز {position_size:.2f}")
            return False
        
        # ۴. بررسی موجودی بعد از معامله (نباید منفی بشه)
        if self._balance - position_size < 0:
            logger.warning(f"⛔ موجودی کافی برای معامله جدید نیست: {self._balance:.2f}")
            return False
        
        # ۵. بررسی حداقل موجودی باقی‌مانده (اختیاری)
        min_reserve = 10.0  # حداقل ۱۰ USDT باید بمونه
        if self._balance - position_size < min_reserve:
            logger.warning(f"⛔ موجودی باقی‌مانده کمتر از {min_reserve} USDT خواهد شد")
            return False
        
        return True
    
    def get_position_size(self) -> float:
        """
        محاسبه حجم معامله بر اساس موجودی نقد
        
        🔥 اصلاح شده:
        - استفاده از موجودی نقد به جای کل دارایی
        - محدود کردن به موجودی موجود
        """
        # محاسبه حجم بر اساس کل دارایی
        calculated_size = self._total_equity * self.position_size_ratio
        
        # محدود کردن به موجودی نقد (نمیشه بیشتر از موجودی خرج کرد)
        max_usable = self._balance
        
        # حجم نهایی: حداقل بین حجم محاسبه شده و موجودی نقد
        final_size = min(calculated_size, max_usable)
        
        # اگر حجم خیلی کم بود، حداقل رو رعایت کن
        min_size = 5.0  # حداقل ۵ USDT
        if final_size < min_size and self._balance >= min_size:
            final_size = min_size
        
        return final_size
    
    def open_position(self, symbol: str, entry_price: float, 
                     stop_loss: float, take_profit: float) -> Dict:
        """
        باز کردن معامله جدید
        
        🔥 اصلاح شده:
        - بررسی نهایی موجودی قبل از باز کردن
        - جلوگیری از موجودی منفی
        """
        # بررسی امکان ورود
        if not self.can_open_new_position():
            return None
        
        # محاسبه حجم معامله
        position_size = self.get_position_size()
        
        # 🔥 بررسی نهایی: موجودی نباید منفی بشه
        if self._balance - position_size < 0:
            logger.error(f"❌ موجودی کافی نیست: {self._balance:.2f} < {position_size:.2f}")
            return None
        
        # 🔥 بررسی نهایی: موجودی نباید کمتر از حداقل باشه
        min_reserve = 10.0
        if self._balance - position_size < min_reserve:
            logger.error(f"❌ موجودی باقی‌مانده کمتر از {min_reserve} USDT خواهد شد")
            return None
        
        position = {
            'symbol': symbol,
            'entry_price': entry_price,
            'position_size': position_size,
            'entry_time': datetime.now().isoformat(),
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'side': 'LONG',
            'unrealized_pnl': 0.0,
            'status': 'open'
        }
        
        # کاهش موجودی نقد
        self._balance -= position_size
        
        # اضافه به موقعیت‌های باز
        self._open_positions.append(position)
        
        # ذخیره وضعیت
        self._save_state()
        
        logger.info(f"✅ معامله جدید باز شد:")
        logger.info(f"   📊 {symbol} - حجم: {position_size:.2f} USDT")
        logger.info(f"   💰 موجودی باقیمانده: {self._balance:.2f} USDT")
        logger.info(f"   📈 تعداد معاملات باز: {len(self._open_positions)}")
        
        return position
    
    def update_position_pnl(self, symbol: str, current_price: float):
        """
        به‌روزرسانی سود/زیان تحقق‌نیافته یک موقعیت
        """
        for position in self._open_positions:
            if position['symbol'] == symbol:
                pnl_percent = (current_price - position['entry_price']) / position['entry_price']
                position['unrealized_pnl'] = position['position_size'] * pnl_percent
                
                # به‌روزرسانی کل دارایی
                self._total_equity = self._balance + sum(p['unrealized_pnl'] for p in self._open_positions)
                
                self._save_state()
                return position['unrealized_pnl']
        
        return 0.0
    
    def close_position(self, symbol: str, exit_price: float, reason: str = "manual") -> Dict:
        """
        بستن معامله و ثبت سود/زیان
        """
        for i, position in enumerate(self._open_positions):
            if position['symbol'] == symbol:
                # محاسبه سود/زیان
                pnl_percent = (exit_price - position['entry_price']) / position['entry_price']
                realized_pnl = position['position_size'] * pnl_percent
                
                # به‌روزرسانی موجودی نقد
                self._balance += position['position_size'] + realized_pnl
                
                # ثبت در تاریخچه
                trade_record = {
                    'symbol': symbol,
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'position_size': position['position_size'],
                    'realized_pnl': realized_pnl,
                    'pnl_percent': pnl_percent * 100,
                    'entry_time': position['entry_time'],
                    'exit_time': datetime.now().isoformat(),
                    'close_reason': reason,
                    'status': 'closed'
                }
                self._closed_trades.append(trade_record)
                
                # حذف از موقعیت‌های باز
                self._open_positions.pop(i)
                
                # به‌روزرسانی کل دارایی
                self._total_equity = self._balance + sum(p['unrealized_pnl'] for p in self._open_positions)
                
                # ذخیره وضعیت
                self._save_state()
                
                logger.info(f"✅ معامله {symbol} بسته شد:")
                logger.info(f"   💰 سود/زیان: {realized_pnl:.2f} USDT ({pnl_percent*100:.2f}%)")
                logger.info(f"   💳 موجودی جدید: {self._balance:.2f} USDT")
                logger.info(f"   📊 کل دارایی: {self._total_equity:.2f} USDT")
                
                return trade_record
        
        logger.warning(f"⚠️ موقعیت {symbol} یافت نشد")
        return None
    
    def get_performance_summary(self) -> Dict:
        """گزارش خلاصه عملکرد"""
        closed_trades = self._closed_trades
        total_trades = len(closed_trades)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'current_balance': self._balance,
                'total_equity': self._total_equity,
                'winning_trades': 0,
                'losing_trades': 0,
                'open_positions': len(self._open_positions)
            }
        
        winning_trades = [t for t in closed_trades if t['realized_pnl'] > 0]
        losing_trades = [t for t in closed_trades if t['realized_pnl'] < 0]
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / total_trades if total_trades > 0 else 0,
            'total_pnl': sum(t['realized_pnl'] for t in closed_trades),
            'avg_pnl': sum(t['realized_pnl'] for t in closed_trades) / total_trades if total_trades > 0 else 0,
            'best_trade': max(closed_trades, key=lambda x: x['realized_pnl']) if winning_trades else None,
            'worst_trade': min(closed_trades, key=lambda x: x['realized_pnl']) if losing_trades else None,
            'current_balance': self._balance,
            'total_equity': self._total_equity,
            'open_positions': len(self._open_positions)
        }
    
    def reset(self, new_balance: Optional[float] = None):
        """بازنشانی کامل"""
        if new_balance is None:
            new_balance = self.initial_balance
        
        self._balance = new_balance
        self._total_equity = new_balance
        self._open_positions = []
        self._closed_trades = []
        self._save_state()
        
        logger.info(f"🔄 پورتفوی بازنشانی شد به: {new_balance:.2f} USDT")
