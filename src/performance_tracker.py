"""
Performance Tracker Module
Tracks and stores signal performance for historical confidence
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from config import Config

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    ثبت و پیگیری عملکرد سیگنال‌ها
    
    ساختار:
    - Outcome: WIN / LOSS / OPEN
    - Average R: میانگین ریسک
    - Profit Factor: سود کل / ضرر کل
    - Max Drawdown: حداکثر افت
    - Error Analysis: دلیل شکست
    - Indicator Performance: Effectiveness هر اندیکاتور
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.signals_file = config.SIGNALS_DIR / "signals_history.json"
        self.performance_file = config.SIGNALS_DIR / "performance.json"
        self.indicator_performance_file = config.SIGNALS_DIR / "indicator_performance.json"
        
        # بارگذاری داده‌های قبلی
        self.signals = self._load_signals()
        self.performance = self._load_performance()
        self.indicator_performance = self._load_indicator_performance()
        self.closed_signals = [s for s in self.signals if s.get('outcome') in ['WIN', 'LOSS']]
        
    def _load_signals(self) -> List[Dict[str, Any]]:
        """بارگذاری تاریخچه سیگنال‌ها"""
        if self.signals_file.exists():
            try:
                with open(self.signals_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading signals: {e}")
        return []
    
    def _load_performance(self) -> Dict[str, Any]:
        """بارگذاری داده‌های عملکرد"""
        if self.performance_file.exists():
            try:
                with open(self.performance_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading performance: {e}")
        return {}
    
    def _load_indicator_performance(self) -> Dict[str, Any]:
        """بارگذاری داده‌های عملکرد اندیکاتورها"""
        if self.indicator_performance_file.exists():
            try:
                with open(self.indicator_performance_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading indicator performance: {e}")
        return {}
    
    def save_signals(self, new_signals: List[Dict[str, Any]]):
        """ذخیره سیگنال‌های جدید"""
        if not new_signals:
            return
        
        for signal in new_signals:
            signal['_saved_at'] = datetime.now().isoformat()
            # مقداردهی اولیه برای سیگنال‌های جدید
            if 'outcome' not in signal:
                signal['outcome'] = 'OPEN'
            if 'r_value' not in signal:
                signal['r_value'] = 0.0
            if 'failure_reason' not in signal:
                signal['failure_reason'] = None
            if 'indicator_scores' not in signal:
                signal['indicator_scores'] = {}
        
        self.signals.extend(new_signals)
        
        if len(self.signals) > 1000:
            self.signals = self.signals[-1000:]
        
        self._update_closed_signals()
        self._save_performance()
        self._update_indicator_performance()
        
        try:
            with open(self.signals_file, 'w') as f:
                json.dump(self.signals, f, indent=2, default=str)
            logger.info(f"✅ Saved {len(new_signals)} signals")
        except Exception as e:
            logger.error(f"Error saving signals: {e}")
    
    def _update_closed_signals(self):
        """به‌روزرسانی لیست سیگنال‌های بسته‌شده"""
        self.closed_signals = [s for s in self.signals if s.get('outcome') in ['WIN', 'LOSS']]
    
    def close_signal(
        self, 
        symbol: str, 
        signal_type: str, 
        entry_time: str,
        outcome: str,
        r_value: float = 0.0,
        failure_reason: Optional[str] = None
    ):
        """
        بستن یک سیگنال و ثبت نتیجه
        
        Args:
            symbol: نماد
            signal_type: BUY / SELL
            entry_time: زمان ورود (برای پیدا کردن سیگنال)
            outcome: WIN / LOSS
            r_value: مقدار R (ریسک)
            failure_reason: دلیل شکست (برای LOSS)
        """
        # پیدا کردن سیگنال متناظر
        for signal in self.signals:
            if (signal.get('symbol') == symbol and 
                signal.get('signal') == signal_type and
                signal.get('timestamp') == entry_time and
                signal.get('outcome') == 'OPEN'):
                
                signal['outcome'] = outcome
                signal['r_value'] = r_value
                signal['failure_reason'] = failure_reason if outcome == 'LOSS' else None
                signal['closed_at'] = datetime.now().isoformat()
                
                self._update_closed_signals()
                self._save_performance()
                self._update_indicator_performance()
                self._save_signals()
                
                logger.info(f"✅ Closed {symbol} {signal_type}: {outcome} (R={r_value:.2f})")
                return
        
        logger.warning(f"⚠️ Signal not found for {symbol} {signal_type} at {entry_time}")
    
    def _save_signals(self):
        """ذخیره سیگنال‌ها"""
        try:
            with open(self.signals_file, 'w') as f:
                json.dump(self.signals, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving signals: {e}")
    
    def _save_performance(self):
        """ذخیره داده‌های عملکرد"""
        perf = self._calculate_performance()
        try:
            with open(self.performance_file, 'w') as f:
                json.dump(perf, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving performance: {e}")
    
    def _update_indicator_performance(self):
        """به‌روزرسانی عملکرد اندیکاتورها"""
        if len(self.closed_signals) < 10:
            return
        
        # گروه‌بندی بر اساس نام اندیکاتور
        indicator_data = {}
        
        for signal in self.closed_signals:
            scores = signal.get('indicator_scores', {})
            outcome = signal.get('outcome', 'LOSS')
            r_value = signal.get('r_value', 0)
            
            for indicator, score in scores.items():
                if indicator not in indicator_data:
                    indicator_data[indicator] = {
                        'wins': [],
                        'losses': [],
                        'total_win_r': 0,
                        'total_loss_r': 0,
                        'win_count': 0,
                        'loss_count': 0
                    }
                
                if outcome == 'WIN':
                    indicator_data[indicator]['wins'].append(score)
                    indicator_data[indicator]['win_count'] += 1
                    indicator_data[indicator]['total_win_r'] += r_value
                else:
                    indicator_data[indicator]['losses'].append(score)
                    indicator_data[indicator]['loss_count'] += 1
                    indicator_data[indicator]['total_loss_r'] += abs(r_value)
        
        # محاسبه effectiveness هر اندیکاتور
        result = {}
        for indicator, data in indicator_data.items():
            win_avg = sum(data['wins']) / len(data['wins']) if data['wins'] else 0
            loss_avg = sum(data['losses']) / len(data['losses']) if data['losses'] else 0
            win_rate = data['win_count'] / (data['win_count'] + data['loss_count']) if (data['win_count'] + data['loss_count']) > 0 else 0
            
            # معیارهای effectiveness
            score_diff = win_avg - loss_avg
            normalized_score = score_diff / 20  # نرمال‌سازی (چون حداکثر امتیاز هر اندیکاتور 20 است)
            
            # R-adjusted effectiveness
            avg_r_win = data['total_win_r'] / data['win_count'] if data['win_count'] > 0 else 0
            avg_r_loss = data['total_loss_r'] / data['loss_count'] if data['loss_count'] > 0 else 0
            r_effectiveness = avg_r_win - avg_r_loss
            
            result[indicator] = {
                'win_avg_score': round(win_avg, 2),
                'loss_avg_score': round(loss_avg, 2),
                'score_effectiveness': round(normalized_score, 3),
                'win_count': data['win_count'],
                'loss_count': data['loss_count'],
                'win_rate': round(win_rate * 100, 1),
                'avg_r_win': round(avg_r_win, 2),
                'avg_r_loss': round(avg_r_loss, 2),
                'r_effectiveness': round(r_effectiveness, 2),
                'total_signals': data['win_count'] + data['loss_count']
            }
        
        self.indicator_performance = result
        
        try:
            with open(self.indicator_performance_file, 'w') as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving indicator performance: {e}")
    
    def _calculate_performance(self) -> Dict[str, Any]:
        """محاسبه آمار عملکرد از سیگنال‌های بسته‌شده"""
        if not self.closed_signals:
            return {
                'total': 0,
                'wins': 0,
                'losses': 0,
                'open': len([s for s in self.signals if s.get('outcome') == 'OPEN']),
                'win_rate': 0.0,
                'avg_r': 0.0,
                'profit_factor': 0.0,
                'max_drawdown': 0.0,
                'total_profit': 0.0,
                'total_loss': 0.0,
                'failure_reasons': {}
            }
        
        total = len(self.closed_signals)
        wins = [s for s in self.closed_signals if s.get('outcome') == 'WIN']
        losses = [s for s in self.closed_signals if s.get('outcome') == 'LOSS']
        open_signals = [s for s in self.signals if s.get('outcome') == 'OPEN']
        
        # Win Rate
        win_rate = (len(wins) / total * 100) if total > 0 else 0
        
        # Average R
        total_r = sum(s.get('r_value', 0) for s in self.closed_signals)
        avg_r = total_r / total if total > 0 else 0
        
        # Profit Factor
        total_profit = sum(s.get('r_value', 0) for s in wins)
        total_loss = abs(sum(s.get('r_value', 0) for s in losses))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # Max Drawdown
        max_drawdown = self._calculate_max_drawdown()
        
        # Failure Reasons
        failure_reasons = {}
        for s in losses:
            reason = s.get('failure_reason', 'Unknown')
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        
        return {
            'total': total,
            'wins': len(wins),
            'losses': len(losses),
            'open': len(open_signals),
            'win_rate': round(win_rate, 1),
            'avg_r': round(avg_r, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 0,
            'max_drawdown': round(max_drawdown, 2),
            'total_profit': round(total_profit, 2),
            'total_loss': round(total_loss, 2),
            'failure_reasons': failure_reasons
        }
    
    def _calculate_max_drawdown(self) -> float:
        """محاسبه حداکثر افت (ساده)"""
        if not self.closed_signals:
            return 0.0
        
        sorted_signals = sorted(
            self.closed_signals, 
            key=lambda x: x.get('_saved_at', '')
        )
        
        cumulative = 0
        peak = 0
        max_dd = 0
        
        for s in sorted_signals:
            if s.get('outcome') == 'WIN':
                cumulative += s.get('r_value', 0)
            else:
                cumulative -= abs(s.get('r_value', 0))
            
            if cumulative > peak:
                peak = cumulative
            
            dd = (peak - cumulative) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        return max_dd * 100
    
    def get_win_rate(self, symbol: Optional[str] = None, signal_type: Optional[str] = None) -> float:
        """دریافت نرخ موفقیت"""
        filtered = self.closed_signals
        
        if symbol:
            filtered = [s for s in filtered if s.get('symbol') == symbol]
        
        if signal_type:
            filtered = [s for s in filtered if s.get('signal') == signal_type]
        
        if not filtered:
            return 0.0
        
        wins = len([s for s in filtered if s.get('outcome') == 'WIN'])
        return (wins / len(filtered)) * 100
    
    def get_confidence_boost(self, symbol: str, signal_type: str) -> float:
        """دریافت ضریب اطمینان بر اساس عملکرد تاریخی"""
        filtered = [s for s in self.closed_signals 
                   if s.get('symbol') == symbol and s.get('signal') == signal_type]
        
        if not filtered:
            return 0.0
        
        total = len(filtered)
        wins = len([s for s in filtered if s.get('outcome') == 'WIN'])
        win_rate = wins / total if total > 0 else 0
        
        weight = min(1.0, total / 30)
        
        if win_rate > 0.6:
            boost = 0.1
        elif win_rate > 0.5:
            boost = 0.0
        elif win_rate > 0.4:
            boost = -0.1
        else:
            boost = -0.2
        
        return round(boost * weight, 2)
    
    def get_indicator_effectiveness(self) -> Dict[str, Any]:
        """
        دریافت effectiveness هر اندیکاتور
        
        Returns:
            دیکشنری با effectiveness هر اندیکاتور
        """
        if not self.indicator_performance:
            return {}
        
        # مرتب‌سازی بر اساس score_effectiveness
        sorted_indicators = sorted(
            self.indicator_performance.items(),
            key=lambda x: x[1].get('score_effectiveness', 0),
            reverse=True
        )
        
        result = {}
        for indicator, data in sorted_indicators:
            result[indicator] = {
                'effectiveness': data.get('score_effectiveness', 0),
                'r_effectiveness': data.get('r_effectiveness', 0),
                'win_rate': data.get('win_rate', 0),
                'signals': data.get('total_signals', 0),
                'score_diff': round(data.get('win_avg_score', 0) - data.get('loss_avg_score', 0), 2)
            }
        
        return result
    
    def get_best_indicators(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        دریافت بهترین اندیکاتورها بر اساس effectiveness
        
        Args:
            limit: تعداد اندیکاتورهای برتر
            
        Returns:
            لیست اندیکاتورهای برتر
        """
        effectiveness = self.get_indicator_effectiveness()
        
        if not effectiveness:
            return []
        
        sorted_items = sorted(
            effectiveness.items(),
            key=lambda x: x[1].get('effectiveness', 0),
            reverse=True
        )
        
        result = []
        for indicator, data in sorted_items[:limit]:
            result.append({
                'indicator': indicator,
                'effectiveness': data.get('effectiveness', 0),
                'r_effectiveness': data.get('r_effectiveness', 0),
                'win_rate': data.get('win_rate', 0),
                'signals': data.get('signals', 0)
            })
        
        return result
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """دریافت خلاصه عملکرد کلی"""
        perf = self._calculate_performance()
        return {
            'total': perf['total'],
            'wins': perf['wins'],
            'losses': perf['losses'],
            'open': perf['open'],
            'win_rate': perf['win_rate'],
            'avg_r': perf['avg_r'],
            'profit_factor': perf['profit_factor'],
            'max_drawdown': perf['max_drawdown'],
            'failure_reasons': perf['failure_reasons']
        }
    
    def get_symbol_performance(self, symbol: str) -> Dict[str, Any]:
        """دریافت عملکرد یک نماد خاص"""
        filtered = [s for s in self.closed_signals if s.get('symbol') == symbol]
        
        if not filtered:
            return {
                'symbol': symbol,
                'total': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'avg_r': 0.0
            }
        
        wins = len([s for s in filtered if s.get('outcome') == 'WIN'])
        total_r = sum(s.get('r_value', 0) for s in filtered)
        
        return {
            'symbol': symbol,
            'total': len(filtered),
            'wins': wins,
            'losses': len(filtered) - wins,
            'win_rate': (wins / len(filtered)) * 100,
            'avg_r': total_r / len(filtered) if len(filtered) > 0 else 0
        }
    
    def get_failure_analysis(self) -> Dict[str, Any]:
        """تحلیل دلایل شکست"""
        perf = self._calculate_performance()
        failure_reasons = perf.get('failure_reasons', {})
        
        if not failure_reasons:
            return {'total_failures': 0, 'reasons': {}}
        
        total_failures = sum(failure_reasons.values())
        
        return {
            'total_failures': total_failures,
            'reasons': failure_reasons,
            'top_reasons': sorted(
                failure_reasons.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]
        }
    
    def reset_performance(self):
        """بازنشانی داده‌های عملکرد (برای تست)"""
        self.signals = []
        self.closed_signals = []
        self.performance = {}
        self.indicator_performance = {}
        
        if self.signals_file.exists():
            self.signals_file.unlink()
        if self.performance_file.exists():
            self.performance_file.unlink()
        if self.indicator_performance_file.exists():
            self.indicator_performance_file.unlink()
        
        logger.info("🔄 Performance data reset")
