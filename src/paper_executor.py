"""
Paper Executor Module
Simulates trading with virtual money
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from src.execution_interface import ExecutionInterface
from src.performance_tracker import PerformanceTracker
from src.bale_bot import BaleBot
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
        self.bale_bot = BaleBot(config)  # <-- اضافه شده برای ارسال پیام
        self.slippage_factor = 0.0015  # ۰.۱۵٪
        self.position_size = 0.25  # ۲۵٪ سرمایه
        self.timeframe = config.TIMEFRAME  # تایم‌فریم از تنظیمات
        self.total_closed_trades = 0
        self.win_count = 0
        self.loss_count = 0
    
    def execute_buy(self, symbol: str, price: float, stop_loss: float, take_profit: float, size: float = 0.25, signal_data: Optional[Dict] = None) -> bool:
        """
        اجرای خرید آزمایشی
        
        Args:
            symbol: نماد
            price: قیمت لحظه‌ای
            stop_loss: حد ضرر
            take_profit: هدف سود
            size: درصد سرمایه (پیش‌فرض ۲۵٪)
            signal_data: اطلاعات کامل سیگنال (اختیاری)
        """
        if self.current_balance <= 0:
            logger.error(f"❌ Insufficient balance for {symbol}")
            return False
        
        # اعمال Slippage
        entry_price = price * (1 + self.slippage_factor)
        position_value = self.current_balance * size
        quantity = position_value / entry_price
        
        # استخراج اطلاعات از signal_data (در صورت وجود)
        score = signal_data.get('score', 0) if signal_data else 0
        confidence = signal_data.get('confidence', 0) if signal_data else 0
        indicator_scores = signal_data.get('score_breakdown', {}) if signal_data else {}
        timeframe = self.timeframe
        
        # ثبت موقعیت با اطلاعات کامل
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
            'status': 'OPEN',
            'score': score,
            'confidence': confidence,
            'indicator_scores': indicator_scores,
            'timeframe': timeframe,
            'signal_data': signal_data  # ذخیره کامل برای استفاده بعدی
        }
        
        self.current_balance -= position_value
        
        # ثبت در PerformanceTracker با اطلاعات کامل
        self.tracker.open_paper_trade(
            symbol=symbol,
            signal_type='BUY',
            entry_price=price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=None,
            position_size=size,
            score=score,
            confidence=confidence,
            indicator_scores=indicator_scores,
            timeframe=timeframe
        )
        
        # ارسال پیام باز شدن معامله
        remaining_balance = self.current_balance
        self.bale_bot.send_trade_open(
            symbol=symbol,
            signal_type='BUY',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=None,
            risk_reward=((take_profit - entry_price) / (entry_price - stop_loss)) if (entry_price - stop_loss) > 0 else 0,
            position_size=size,
            remaining_balance=remaining_balance,
            score=score,
            timeframe=timeframe,
            confidence=confidence,
            indicator_scores=indicator_scores
        )
        
        logger.info(
            f"📈 PAPER BUY: {symbol} @ {entry_price:.4f} "
            f"(Size: {size*100}%, Value: {position_value:.2f} USDT)"
        )
        return True
    
    def execute_sell(self, symbol: str, price: float, stop_loss: float, take_profit: float, size: float = 0.25, signal_data: Optional[Dict] = None) -> bool:
        """
        اجرای فروش آزمایشی
        
        Args:
            symbol: نماد
            price: قیمت لحظه‌ای
            stop_loss: حد ضرر
            take_profit: هدف سود
            size: درصد سرمایه (پیش‌فرض ۲۵٪)
            signal_data: اطلاعات کامل سیگنال (اختیاری)
        """
        if self.current_balance <= 0:
            logger.error(f"❌ Insufficient balance for {symbol}")
            return False
        
        # اعمال Slippage
        entry_price = price * (1 - self.slippage_factor)
        position_value = self.current_balance * size
        quantity = position_value / entry_price
        
        # استخراج اطلاعات از signal_data (در صورت وجود)
        score = signal_data.get('score', 0) if signal_data else 0
        confidence = signal_data.get('confidence', 0) if signal_data else 0
        indicator_scores = signal_data.get('score_breakdown', {}) if signal_data else {}
        timeframe = self.timeframe
        
        # ثبت موقعیت با اطلاعات کامل
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
            'status': 'OPEN',
            'score': score,
            'confidence': confidence,
            'indicator_scores': indicator_scores,
            'timeframe': timeframe,
            'signal_data': signal_data
        }
        
        self.current_balance -= position_value
        
        # ثبت در PerformanceTracker با اطلاعات کامل
        self.tracker.open_paper_trade(
            symbol=symbol,
            signal_type='SELL',
            entry_price=price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=None,
            position_size=size,
            score=score,
            confidence=confidence,
            indicator_scores=indicator_scores,
            timeframe=timeframe
        )
        
        # ارسال پیام باز شدن معامله
        remaining_balance = self.current_balance
        self.bale_bot.send_trade_open(
            symbol=symbol,
            signal_type='SELL',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=None,
            risk_reward=((entry_price - take_profit) / (stop_loss - entry_price)) if (stop_loss - entry_price) > 0 else 0,
            position_size=size,
            remaining_balance=remaining_balance,
            score=score,
            timeframe=timeframe,
            confidence=confidence,
            indicator_scores=indicator_scores
        )
        
        logger.info(
            f"📈 PAPER SELL: {symbol} @ {entry_price:.4f} "
            f"(Size: {size*100}%, Value: {position_value:.2f} USDT)"
        )
        return True
    
    def close_position(self, symbol: str) -> bool:
        """بستن یک موقعیت باز"""
        if symbol not in self.positions:
            logger.warning(f"⚠️ No position found for {symbol}")
            return False
        
        position = self.positions[symbol]
        if position['status'] != 'OPEN':
            logger.warning(f"⚠️ Position {symbol} is already closed")
            return False
        
        return True
    
    def get_balance(self) -> float:
        """دریافت موجودی فعلی"""
        total_value = self.current_balance
        
        for symbol, position in self.positions.items():
            if position['status'] == 'OPEN':
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
        بستن داخلی موقعیت با محاسبه کامل سود/ضرر و کارمزد
        """
        position = self.positions[symbol]
        signal_type = position['type']
        entry_price = position['entry_price_slippage']
        position_value = position['position_value']
        
        # ================================================
        # محاسبه با احتساب کارمزد
        # ================================================
        fee_rate = 0.0015  # ۰.۱۵٪ کارمزد (می‌توان از config خواند)
        
        # قیمت خروج با Slippage
        if signal_type == 'BUY':
            exit_with_slippage = exit_price * (1 - self.slippage_factor)
        else:
            exit_with_slippage = exit_price * (1 + self.slippage_factor)
        
        # محاسبه سود/ضرر ناخالص (بدون کارمزد)
        if signal_type == 'BUY':
            price_change = (exit_with_slippage - entry_price) / entry_price
        else:
            price_change = (entry_price - exit_with_slippage) / entry_price
        
        gross_profit = position_value * price_change
        
        # ================================================
        # محاسبه کارمزد
        # ================================================
        buy_fee = position_value * fee_rate  # کارمزد خرید
        sell_fee = (position_value + gross_profit) * fee_rate  # کارمزد فروش
        total_fee = buy_fee + sell_fee
        
        # ================================================
        # محاسبه سود/ضرر خالص
        # ================================================
        net_profit = gross_profit - total_fee
        net_profit_percent = (net_profit / position_value) * 100
        
        # ================================================
        # به‌روزرسانی موجودی
        # ================================================
        self.current_balance += position_value + net_profit
        
        # ================================================
        # ثبت اطلاعات در position
        # ================================================
        position['status'] = 'CLOSED'
        position['exit_price'] = exit_price
        position['exit_price_slippage'] = exit_with_slippage
        position['exit_time'] = datetime.now().isoformat()
        position['exit_reason'] = exit_reason
        position['gross_profit'] = gross_profit
        position['net_profit'] = net_profit
        position['net_profit_percent'] = net_profit_percent
        position['total_fee'] = total_fee
        position['buy_fee'] = buy_fee
        position['sell_fee'] = sell_fee
        
        # ================================================
        # به‌روزرسانی آمار
        # ================================================
        self.total_closed_trades += 1
        if net_profit > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        
        win_rate = (self.win_count / self.total_closed_trades * 100) if self.total_closed_trades > 0 else 0
        
        # ================================================
        # محاسبه مدت زمان باز بودن
        # ================================================
        entry_time_str = position.get('entry_time')
        hold_time = "نامشخص"
        if entry_time_str:
            try:
                entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                exit_dt = datetime.now()
                delta = exit_dt - entry_dt
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                if delta.days > 0:
                    hold_time = f"{delta.days}d {hours}h {minutes}m"
                else:
                    hold_time = f"{hours}h {minutes}m"
            except Exception:
                hold_time = "نامشخص"
        
        # ================================================
        # ثبت در PerformanceTracker با اطلاعات کامل مالی
        # ================================================
        outcome = 'WIN' if net_profit > 0 else 'LOSS'
        self.tracker.close_paper_trade(
            symbol=symbol,
            exit_price=exit_price,
            exit_reason=exit_reason,
            net_profit=net_profit,
            net_profit_percent=net_profit_percent,
            total_fee=total_fee,
            gross_profit=gross_profit,
            buy_fee=buy_fee,
            sell_fee=sell_fee,
            hold_time=hold_time,
            outcome=outcome
        )
        
        # ================================================
        # ارسال پیام بسته شدن معامله
        # ================================================
        entry_time = position.get('entry_time', '')
        if entry_time:
            try:
                entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                entry_time_fa = entry_dt.strftime('%Y-%m-%d %H:%M')
            except:
                entry_time_fa = entry_time
        else:
            entry_time_fa = "نامشخص"
        
        exit_time_fa = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        self.bale_bot.send_trade_close(
            symbol=symbol,
            signal_type=signal_type,
            entry_price=entry_price,
            exit_price=exit_with_slippage,
            entry_time=entry_time_fa,
            exit_time=exit_time_fa,
            hold_time=hold_time,
            timeframe=position.get('timeframe', self.timeframe),
            gross_profit=gross_profit,
            net_profit=net_profit,
            net_profit_percent=net_profit_percent,
            total_fee=total_fee,
            buy_fee=buy_fee,
            sell_fee=sell_fee,
            exit_reason=exit_reason,
            current_balance=self.current_balance,
            total_trades=self.total_closed_trades,
            win_rate=win_rate,
            score=position.get('score', 0),
            indicator_scores=position.get('indicator_scores', {}),
            outcome=outcome
        )
        
        logger.info(
            f"📉 PAPER CLOSE: {symbol} {signal_type} "
            f"Gross: {gross_profit:.2f} USDT | "
            f"Fee: {total_fee:.2f} USDT | "
            f"Net: {net_profit:.2f} USDT ({net_profit_percent:.2f}%) "
            f"Reason={exit_reason}"
        )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """دریافت خلاصه عملکرد"""
        return self.tracker.get_performance_summary()
