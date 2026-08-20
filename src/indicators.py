"""
Technical Indicators Module
Calculates all technical indicators using the 'ta' library
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict, Union, List, Tuple

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, ADXIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from config import Config

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """
    محاسبه تمام اندیکاتورهای تکنیکال مورد نیاز
    """
    
    def __init__(self, config=Config):
        self.config = config
        
        # =========================
        # حداقل کندل‌های مورد نیاز برای هر اندیکاتور
        # =========================
        self.min_candles = max(
            config.EMA_TREND,          # 200 برای EMA200
            config.VOLUME_MA_PERIOD,   # 20 برای حجم
            config.BB_PERIOD,          # 20 برای بولینگر
            config.MACD_SLOW,          # 26 برای MACD
            config.ATR_PERIOD,         # 14 برای ATR
            config.ADX_PERIOD,         # 14 برای ADX
            490                        # 490 برای هماهنگی با DataFetcher (که 499 برمی‌گردونه)
        )
        
    def calculate_all(
        self, 
        df: pd.DataFrame
    ) -> Dict[str, Union[pd.Series, float, None]]:
        """
        محاسبه همه اندیکاتورها به صورت یکجا
        
        Args:
            df: DataFrame با ستون‌های open, high, low, close, volume
            
        Returns:
            دیکشنری شامل تمام اندیکاتورها (سری‌های pandas یا مقادیر عددی)
        """
        if df is None or len(df) < self.min_candles:
            logger.error(
                f"Insufficient data: need {self.min_candles} candles, "
                f"got {len(df) if df is not None else 0}"
            )
            return {}
        
        indicators: Dict[str, Union[pd.Series, float, None]] = {}
        
        try:
            # =========================
            # RSI
            # =========================
            indicators['rsi'] = self.calculate_rsi(df)
            
            # =========================
            # EMA
            # =========================
            indicators['ema_fast'] = self.calculate_ema(df, self.config.EMA_FAST)
            indicators['ema_slow'] = self.calculate_ema(df, self.config.EMA_SLOW)
            indicators['ema_trend'] = self.calculate_ema(df, self.config.EMA_TREND)
            
            # =========================
            # SMA (از Config خوانده می‌شود)
            # =========================
            indicators['sma_fast'] = self.calculate_sma(df, self.config.SMA_FAST)
            indicators['sma_slow'] = self.calculate_sma(df, self.config.SMA_SLOW)
            
            # =========================
            # MACD
            # =========================
            macd_result = self.calculate_macd(df)
            indicators['macd_line'] = macd_result['macd']
            indicators['macd_signal'] = macd_result['signal']
            indicators['macd_histogram'] = macd_result['histogram']
            
            # =========================
            # ADX + DI+ + DI-
            # =========================
            adx_result = self.calculate_adx_full(df)
            indicators['adx'] = adx_result['adx']
            indicators['di_plus'] = adx_result['di_plus']
            indicators['di_minus'] = adx_result['di_minus']
            
            # =========================
            # ATR
            # =========================
            indicators['atr'] = self.calculate_atr(df)
            
            # =========================
            # Bollinger Bands
            # =========================
            bb_result = self.calculate_bollinger(df)
            indicators['bb_upper'] = bb_result['upper']
            indicators['bb_middle'] = bb_result['middle']
            indicators['bb_lower'] = bb_result['lower']
            indicators['bb_width'] = bb_result['width']
            
            # =========================
            # Volume Analysis
            # =========================
            indicators['volume_ma'] = self.calculate_volume_ma(df)
            indicators['volume_ratio'] = self.calculate_volume_ratio(df)
            
            logger.debug("All indicators calculated successfully")
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return {}
        
        return indicators
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = None) -> Optional[pd.Series]:
        """محاسبه RSI"""
        try:
            period = period or self.config.RSI_PERIOD
            rsi = RSIIndicator(df['close'], window=period)
            return rsi.rsi()
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None
    
    def calculate_ema(self, df: pd.DataFrame, period: int) -> Optional[pd.Series]:
        """محاسبه EMA"""
        try:
            ema = EMAIndicator(df['close'], window=period)
            return ema.ema_indicator()
        except Exception as e:
            logger.error(f"Error calculating EMA {period}: {e}")
            return None
    
    def calculate_sma(self, df: pd.DataFrame, period: int) -> Optional[pd.Series]:
        """محاسبه SMA"""
        try:
            sma = SMAIndicator(df['close'], window=period)
            return sma.sma_indicator()
        except Exception as e:
            logger.error(f"Error calculating SMA {period}: {e}")
            return None
    
    def calculate_macd(
        self, 
        df: pd.DataFrame
    ) -> Dict[str, Optional[pd.Series]]:
        """محاسبه MACD"""
        try:
            macd = MACD(
                df['close'],
                window_slow=self.config.MACD_SLOW,
                window_fast=self.config.MACD_FAST,
                window_sign=self.config.MACD_SIGNAL
            )
            return {
                'macd': macd.macd(),
                'signal': macd.macd_signal(),
                'histogram': macd.macd_diff()
            }
        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            return {'macd': None, 'signal': None, 'histogram': None}
    
    def calculate_adx_full(
        self, 
        df: pd.DataFrame, 
        period: int = None
    ) -> Dict[str, Optional[pd.Series]]:
        """
        محاسبه کامل ADX شامل DI+ و DI-
        
        Returns:
            دیکشنری شامل adx, di_plus, di_minus
        """
        try:
            period = period or self.config.ADX_PERIOD
            adx = ADXIndicator(df['high'], df['low'], df['close'], window=period)
            return {
                'adx': adx.adx(),
                'di_plus': adx.adx_pos(),
                'di_minus': adx.adx_neg()
            }
        except Exception as e:
            logger.error(f"Error calculating ADX: {e}")
            return {'adx': None, 'di_plus': None, 'di_minus': None}
    
    def calculate_adx(self, df: pd.DataFrame, period: int = None) -> Optional[pd.Series]:
        """محاسبه ADX (فقط برای سازگاری با نسخه‌های قدیمی)"""
        result = self.calculate_adx_full(df, period)
        return result['adx']
    
    def calculate_atr(self, df: pd.DataFrame, period: int = None) -> Optional[pd.Series]:
        """محاسبه ATR"""
        try:
            period = period or self.config.ATR_PERIOD
            atr = AverageTrueRange(df['high'], df['low'], df['close'], window=period)
            return atr.average_true_range()
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None
    
    def calculate_bollinger(
        self, 
        df: pd.DataFrame, 
        period: int = None,
        std: int = None
    ) -> Dict[str, Optional[pd.Series]]:
        """محاسبه باندهای بولینگر"""
        try:
            period = period or self.config.BB_PERIOD
            std = std or self.config.BB_STD
            
            bb = BollingerBands(df['close'], window=period, window_dev=std)
            
            return {
                'upper': bb.bollinger_hband(),
                'middle': bb.bollinger_mavg(),
                'lower': bb.bollinger_lband(),
                'width': bb.bollinger_wband()
            }
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            return {'upper': None, 'middle': None, 'lower': None, 'width': None}
    
    def calculate_volume_ma(self, df: pd.DataFrame, period: int = None) -> Optional[pd.Series]:
        """محاسبه میانگین متحرک حجم"""
        try:
            period = period or self.config.VOLUME_MA_PERIOD
            return df['volume'].rolling(window=period).mean()
        except Exception as e:
            logger.error(f"Error calculating Volume MA: {e}")
            return None
    
    def calculate_volume_ratio(self, df: pd.DataFrame) -> Optional[float]:
        """
        محاسبه نسبت حجم فعلی به میانگین حجم ۲۰ کندل قبلی
        
        Returns:
            نسبت حجم یا None در صورت خطا
        """
        try:
            current_volume = df['volume'].iloc[-1]
            
            # =========================
            # میانگین ۲۰ کندل قبل از کندل فعلی
            # =========================
            avg_volume = df['volume'].shift(1).rolling(
                window=self.config.VOLUME_MA_PERIOD
            ).mean().iloc[-1]
            
            if avg_volume == 0 or pd.isna(avg_volume):
                return 1.0
                
            return current_volume / avg_volume
            
        except Exception as e:
            logger.error(f"Error calculating Volume Ratio: {e}")
            return None
    
    def _clean_nan(self, value) -> Optional[float]:
        """تمیز کردن مقادیر NaN"""
        if value is None:
            return None
        if pd.isna(value):
            return None
        return float(value)
    
    def get_latest_values(self, df: pd.DataFrame) -> Dict[str, Optional[float]]:
        """
        دریافت آخرین مقادیر تمام اندیکاتورها به صورت دیکشنری
        
        Args:
            df: DataFrame با داده‌های قیمت
            
        Returns:
            دیکشنری شامل آخرین مقادیر اندیکاتورها (بدون NaN)
        """
        indicators = self.calculate_all(df)
        
        latest: Dict[str, Optional[float]] = {}
        for key, value in indicators.items():
            if isinstance(value, pd.Series) and len(value) > 0:
                latest[key] = self._clean_nan(value.iloc[-1])
            elif isinstance(value, float):
                latest[key] = self._clean_nan(value)
            else:
                latest[key] = None
        
        # اضافه کردن قیمت‌ها
        latest['price'] = self._clean_nan(df['close'].iloc[-1])
        latest['high'] = self._clean_nan(df['high'].iloc[-1])
        latest['low'] = self._clean_nan(df['low'].iloc[-1])
        latest['open'] = self._clean_nan(df['open'].iloc[-1])
        latest['volume'] = self._clean_nan(df['volume'].iloc[-1])
        
        return latest
    
    def get_support_resistance(
        self, 
        df: pd.DataFrame, 
        lookback: int = 50
    ) -> Dict[str, Optional[float]]:
        """
        شناسایی سطوح حمایت و مقاومت
        
        Args:
            df: DataFrame با داده‌های قیمت
            lookback: تعداد کندل‌های گذشته برای بررسی
            
        Returns:
            دیکشنری شامل support, resistance, dynamic_support, dynamic_resistance
        """
        try:
            current_price = df['close'].iloc[-1]
            
            # =========================
            # ❌ کندل فعلی را حذف می‌کنیم تا Breakout واقعی تشخیص داده شود
            # =========================
            if len(df) > lookback:
                recent_data = df.iloc[-(lookback + 1):-1]
            else:
                recent_data = df.iloc[:-1]
            
            if len(recent_data) == 0:
                return {
                    'support': None,
                    'resistance': None,
                    'dynamic_support': None,
                    'dynamic_resistance': None
                }
            
            # =========================
            # حمایت و مقاومت ساده (بالاترین و پایین‌ترین)
            # =========================
            resistance = float(recent_data['high'].max())
            support = float(recent_data['low'].min())
            
            # =========================
            # حمایت و مقاومت پویا با EMA (از Config خوانده می‌شود)
            # =========================
            ema_slow = self.calculate_ema(df, self.config.EMA_SLOW)
            dynamic_support = None
            dynamic_resistance = None
            
            if ema_slow is not None and len(ema_slow) > 0:
                ema_value = float(ema_slow.iloc[-1])
                
                # اگر قیمت بالای EMA باشد، EMA می‌تواند حمایت باشد
                if current_price > ema_value:
                    dynamic_support = ema_value
                # اگر قیمت زیر EMA باشد، EMA می‌تواند مقاومت باشد
                else:
                    dynamic_resistance = ema_value
            
            # =========================
            # خوشه‌بندی سطوح نزدیک به هم (برای دقت بیشتر)
            # =========================
            support, resistance = self._cluster_sr_levels(
                recent_data, support, resistance
            )
            
            return {
                'support': support,
                'resistance': resistance,
                'dynamic_support': dynamic_support,
                'dynamic_resistance': dynamic_resistance
            }
            
        except Exception as e:
            logger.error(f"Error calculating Support/Resistance: {e}")
            return {
                'support': None,
                'resistance': None,
                'dynamic_support': None,
                'dynamic_resistance': None
            }
    
    def _cluster_sr_levels(
        self, 
        df: pd.DataFrame, 
        support: float, 
        resistance: float,
        tolerance_pct: float = 0.5
    ) -> Tuple[float, float]:
        """
        خوشه‌بندی سطوح حمایت و مقاومت نزدیک به هم
        
        Args:
            df: DataFrame داده‌ها
            support: سطح حمایت اولیه
            resistance: سطح مقاومت اولیه
            tolerance_pct: درصد تحمل برای خوشه‌بندی (0.5%)
            
        Returns:
            (support, resistance) خوشه‌بندی شده
        """
        try:
            # =========================
            # پیدا کردن سطوح نزدیک به حمایت
            # =========================
            support_levels = []
            for i in range(len(df)):
                low = df['low'].iloc[i]
                if abs(low - support) / support * 100 < tolerance_pct:
                    support_levels.append(low)
            
            if support_levels:
                support = float(np.median(support_levels))
            
            # =========================
            # پیدا کردن سطوح نزدیک به مقاومت
            # =========================
            resistance_levels = []
            for i in range(len(df)):
                high = df['high'].iloc[i]
                if abs(high - resistance) / resistance * 100 < tolerance_pct:
                    resistance_levels.append(high)
            
            if resistance_levels:
                resistance = float(np.median(resistance_levels))
            
            return support, resistance
            
        except Exception as e:
            logger.debug(f"SR clustering failed: {e}")
            return support, resistance
    
    def calculate_heikin_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        محاسبه کندل‌های Heikin Ashi
        
        Args:
            df: DataFrame با ستون‌های open, high, low, close
            
        Returns:
            DataFrame با ستون‌های ha_open, ha_high, ha_low, ha_close
        """
        try:
            ha_df = pd.DataFrame(index=df.index)
            
            ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
            
            ha_df['ha_open'] = 0.0
            ha_df.loc[ha_df.index[0], 'ha_open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
            
            for i in range(1, len(df)):
                ha_df.loc[ha_df.index[i], 'ha_open'] = (
                    ha_df['ha_open'].iloc[i-1] + ha_df['ha_close'].iloc[i-1]
                ) / 2
            
            ha_df['ha_high'] = df[['high', 'open', 'close']].max(axis=1)
            ha_df['ha_low'] = df[['low', 'open', 'close']].min(axis=1)
            
            return ha_df
            
        except Exception as e:
            logger.error(f"Error calculating Heikin Ashi: {e}")
            return pd.DataFrame()
    
    def get_ha_trend(self, df: pd.DataFrame) -> str:
        """
        تشخیص روند با استفاده از Heikin Ashi
        
        Returns:
            'BULLISH', 'BEARISH', یا 'NEUTRAL'
        """
        try:
            ha_df = self.calculate_heikin_ashi(df)
            if ha_df.empty:
                return 'NEUTRAL'
            
            last_ha_open = ha_df['ha_open'].iloc[-1]
            last_ha_close = ha_df['ha_close'].iloc[-1]
            prev_ha_open = ha_df['ha_open'].iloc[-2] if len(ha_df) > 1 else last_ha_open
            prev_ha_close = ha_df['ha_close'].iloc[-2] if len(ha_df) > 1 else last_ha_close
            
            # =========================
            # تشخیص روند
            # =========================
            is_bullish = (
                last_ha_close > last_ha_open and
                last_ha_open > prev_ha_open and
                last_ha_close > prev_ha_close
            )
            
            is_bearish = (
                last_ha_close < last_ha_open and
                last_ha_open < prev_ha_open and
                last_ha_close < prev_ha_close
            )
            
            if is_bullish:
                return 'BULLISH'
            elif is_bearish:
                return 'BEARISH'
            else:
                return 'NEUTRAL'
                
        except Exception as e:
            logger.error(f"Error calculating HA trend: {e}")
            return 'NEUTRAL'
