"""
Data Validator Module
بررسی کیفیت و سلامت داده‌های OHLCV قبل از تحلیل
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DataValidator:
    """
    تأییدکننده داده‌های OHLCV
    """

    def __init__(self, config):
        self.config = config
        self.MIN_CANDLES = getattr(config, 'MIN_CANDLES_REQUIRED', 200)
        self.MAX_CANDLE_AGE_MINUTES = getattr(config, 'MAX_CANDLE_AGE_MINUTES', 30)

    def validate(self, df: pd.DataFrame, symbol: str, timeframe: str = "15m") -> Dict[str, Any]:
        """
        اعتبارسنجی کامل داده‌ها

        Returns:
            {
                "valid": bool,
                "reason": str,
                "candles_received": int,
                "candles_required": int,
                "missing_candles": int,
                "duplicate_candles": int,
                "stale_data": bool,
                "quality_score": float,
                "issues": list,
                "gaps": list
            }
        """
        result = {
            'valid': True,
            'reason': None,
            'candles_received': len(df) if df is not None else 0,
            'candles_required': self.MIN_CANDLES,
            'missing_candles': 0,
            'duplicate_candles': 0,
            'stale_data': False,
            'quality_score': 100.0,
            'issues': [],
            'gaps': []
        }

        # ================================================
        # 1. بررسی وجود داده
        # ================================================
        if df is None or len(df) == 0:
            result['valid'] = False
            result['reason'] = 'No data received'
            result['quality_score'] = 0
            return result

        # ================================================
        # 2. بررسی تعداد کندل‌ها
        # ================================================
        if len(df) < self.MIN_CANDLES:
            result['valid'] = False
            result['reason'] = f'Insufficient candles: {len(df)} < {self.MIN_CANDLES}'
            result['quality_score'] = 0
            return result

        # ================================================
        # 3. بررسی ستون‌های مورد نیاز
        # ================================================
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_columns if col not in df.columns]

        if missing_cols:
            result['valid'] = False
            result['reason'] = f'Missing columns: {missing_cols}'
            result['quality_score'] = 0
            return result

        # ================================================
        # 4. بررسی مقادیر نامعتبر (NaN و صفر)
        # ================================================
        for col in required_columns:
            nan_count = df[col].isna().sum()
            if nan_count > 0:
                result['issues'].append(f'{nan_count} NaN in {col}')
                result['quality_score'] -= (nan_count / len(df)) * 10

        # بررسی قیمت‌های صفر یا منفی
        for col in ['open', 'high', 'low', 'close']:
            invalid_count = (df[col] <= 0).sum()
            if invalid_count > 0:
                result['issues'].append(f'{invalid_count} invalid prices (<=0) in {col}')
                result['quality_score'] -= (invalid_count / len(df)) * 10

        # بررسی حجم منفی
        invalid_volume = (df['volume'] < 0).sum()
        if invalid_volume > 0:
            result['issues'].append(f'{invalid_volume} negative volumes')
            result['quality_score'] -= (invalid_volume / len(df)) * 10

        # ================================================
        # 5. بررسی منطقی بودن OHLC (high >= max(open, close) و low <= min(open, close))
        # ================================================
        invalid_high = (df['high'] < df[['open', 'close']].max(axis=1)).sum()
        if invalid_high > 0:
            result['issues'].append(f'{invalid_high} invalid high (high < max(open, close))')
            result['quality_score'] -= (invalid_high / len(df)) * 10

        invalid_low = (df['low'] > df[['open', 'close']].min(axis=1)).sum()
        if invalid_low > 0:
            result['issues'].append(f'{invalid_low} invalid low (low > min(open, close))')
            result['quality_score'] -= (invalid_low / len(df)) * 10

        # ================================================
        # 6. بررسی timestamp (اگر وجود داشته باشد)
        # ================================================
        if 'timestamp' in df.columns:
            try:
                # تبدیل به datetime
                timestamps = pd.to_datetime(df['timestamp'])

                # بررسی مرتب بودن
                if not timestamps.is_monotonic_increasing:
                    result['issues'].append('Timestamps are not sorted')
                    result['quality_score'] -= 15

                # بررسی تکراری‌ها
                duplicate_count = timestamps.duplicated().sum()
                if duplicate_count > 0:
                    result['duplicate_candles'] = duplicate_count
                    result['issues'].append(f'{duplicate_count} duplicate timestamps')
                    result['quality_score'] -= (duplicate_count / len(df)) * 5

                # ================================================
                # 7. بررسی فاصله زمانی و کندل‌های گمشده
                # ================================================
                expected_gap = self._get_expected_gap(timeframe)
                gaps = timestamps.diff().dt.total_seconds().dropna()

                # شناسایی gaps بزرگتر از expected_gap
                large_gaps = gaps[gaps > expected_gap * 1.5]
                if len(large_gaps) > 0:
                    result['gaps'] = []
                    for idx, gap in large_gaps.items():
                        missing_count = int(gap // expected_gap) - 1
                        result['missing_candles'] += missing_count
                        result['gaps'].append({
                            'from': timestamps.iloc[idx - 1].isoformat(),
                            'to': timestamps.iloc[idx].isoformat(),
                            'gap_seconds': gap,
                            'missing_candles': missing_count
                        })
                    result['issues'].append(f'{len(large_gaps)} gaps detected, {result["missing_candles"]} missing candles')
                    result['quality_score'] -= min(30, len(large_gaps) * 3)

                # ================================================
                # 8. بررسی تاریخ آخرین کندل (Stale Data)
                # ================================================
                last_timestamp = timestamps.iloc[-1]
                now = datetime.now(last_timestamp.tzinfo) if last_timestamp.tzinfo else datetime.now()
                age_minutes = (now - last_timestamp).total_seconds() / 60

                if age_minutes > self.MAX_CANDLE_AGE_MINUTES:
                    result['stale_data'] = True
                    result['issues'].append(f'Last candle is {age_minutes:.1f} minutes old')
                    result['quality_score'] -= 20

                    # اگر داده خیلی قدیمی باشد، رد می‌شود
                    if age_minutes > self.MAX_CANDLE_AGE_MINUTES * 2:
                        result['valid'] = False
                        result['reason'] = f'Data too stale: {age_minutes:.1f} minutes old'
                        return result

            except Exception as e:
                result['issues'].append(f'Timestamp processing error: {e}')
                result['quality_score'] -= 10

        # ================================================
        # 9. محاسبه کیفیت نهایی
        # ================================================
        result['quality_score'] = max(0, min(100, result['quality_score']))

        # اگر نمره کیفیت خیلی پایین است، داده را رد کن
        if result['quality_score'] < 70:
            result['valid'] = False
            result['reason'] = f'Quality score too low: {result["quality_score"]:.1f}%'

        return result

    def _get_expected_gap(self, timeframe: str) -> int:
        """محاسبه فاصله زمانی مورد انتظار بر حسب ثانیه"""
        timeframe_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400
        }
        return timeframe_map.get(timeframe, 900)

    def is_valid_for_analysis(self, validation_result: Dict[str, Any]) -> bool:
        """بررسی سریع اینکه آیا داده برای تحلیل مناسب است"""
        return validation_result.get('valid', False) and validation_result.get('quality_score', 0) >= 70