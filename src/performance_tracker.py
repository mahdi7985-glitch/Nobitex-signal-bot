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
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.signals_file = config.SIGNALS_DIR / "signals_history.json"
        self.performance_file = config.SIGNALS_DIR / "performance.json"
        
        # بارگذاری داده‌های قبلی
        self.signals = self._load_signals()
        self.performance = self._load_performance()
        
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
    
    def save_signals(self, new_signals: List[Dict[str, Any]]):
        """ذخیره سیگنال‌های جدید"""
        if not new_signals:
            return
        
        for signal in new_signals:
            signal['_saved_at'] = datetime.now().isoformat()
        
        self.signals.extend(new_signals)
        
        if len(self.signals) > 1000:
            self.signals = self.signals[-1000:]
        
        try:
            with open(self.signals_file, 'w') as f:
                json.dump(self.signals, f, indent=2, default=str)
            logger.info(f"✅ Saved {len(new_signals)} signals")
        except Exception as e:
            logger.error(f"Error saving signals: {e}")
    
    def update_performance(self, symbol: str, signal_type: str, result: str):
        """به‌روزرسانی عملکرد یک سیگنال"""
        key = f"{symbol}_{signal_type}"
        
        if key not in self.performance:
            self.performance[key] = {
                'symbol': symbol,
                'signal_type': signal_type,
                'total': 0,
                'tp1_hit': 0,
                'tp2_hit': 0,
                'sl_hit': 0,
                'pending': 0
            }
        
        perf = self.performance[key]
        perf['total'] += 1
        
        if result == 'TP1_HIT':
            perf['tp1_hit'] += 1
        elif result == 'TP2_HIT':
            perf['tp2_hit'] += 1
        elif result == 'SL_HIT':
            perf['sl_hit'] += 1
        else:
            perf['pending'] += 1
        
        self._save_performance()
    
    def _save_performance(self):
        """ذخیره داده‌های عملکرد"""
        try:
            with open(self.performance_file, 'w') as f:
                json.dump(self.performance, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving performance: {e}")
    
    def get_win_rate(self, symbol: str, signal_type: str) -> float:
        """دریافت نرخ موفقیت برای یک نوع سیگنال"""
        key = f"{symbol}_{signal_type}"
        if key not in self.performance:
            return 0.0
        
        perf = self.performance[key]
        total = perf.get('total', 0)
        if total == 0:
            return 0.0
        
        successful = perf.get('tp1_hit', 0) + perf.get('tp2_hit', 0)
        return (successful / total) * 100
    
    def get_confidence_boost(self, symbol: str, signal_type: str) -> float:
        """دریافت ضریب اطمینان بر اساس عملکرد تاریخی"""
        win_rate = self.get_win_rate(symbol, signal_type)
        
        if win_rate > 60:
            return 0.1
        elif win_rate > 50:
            return 0.0
        elif win_rate > 40:
            return -0.1
        else:
            return -0.2
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """دریافت خلاصه عملکرد کلی"""
        total = 0
        total_tp1 = 0
        total_tp2 = 0
        total_sl = 0
        
        for key, perf in self.performance.items():
            total += perf.get('total', 0)
            total_tp1 += perf.get('tp1_hit', 0)
            total_tp2 += perf.get('tp2_hit', 0)
            total_sl += perf.get('sl_hit', 0)
        
        if total == 0:
            return {
                'total': 0,
                'win_rate': 0,
                'tp1_rate': 0,
                'tp2_rate': 0,
                'sl_rate': 0
            }
        
        return {
            'total': total,
            'win_rate': ((total_tp1 + total_tp2) / total) * 100,
            'tp1_rate': (total_tp1 / total) * 100,
            'tp2_rate': (total_tp2 / total) * 100,
            'sl_rate': (total_sl / total) * 100
        }
