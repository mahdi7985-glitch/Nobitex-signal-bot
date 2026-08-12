"""
Technical Indicators Module
Calculates all technical indicators using the 'ta' library
"""

import logging
import pandas as pd
from typing import Optional, Dict, Union

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
            config.CANDLES_LIMIT       # 300 برای هماهنگی با DataFetcher
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
            # SMA
            # =========================
            indicators['sma_fast'] = self.calculate_sma(df, 20)
            indicators['sma_slow'] = self.calculate_sma(df, 50)
            
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
                'di_plus': adx.di_plus(),
                'di_minus': adx.di_minus()
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
            recent_data = df.tail(lookback)
            current_price = df['close'].iloc[-1]
            
            # =========================
            # حمایت و مقاومت ساده (بالاترین و پایین‌ترین)
            # =========================
            resistance = float(recent_data['high'].max())
            support = float(recent_data['low'].min())
            
            # =========================
            # حمایت و مقاومت پویا با EMA50
            # =========================
            ema_50 = self.calculate_ema(df, 50)
            dynamic_support = None
            dynamic_resistance = None
            
            if ema_50 is not None and len(ema_50) > 0:
                ema_value = float(ema_50.iloc[-1])
                
                # اگر قیمت بالای EMA50 باشد، EMA50 می‌تواند حمایت باشد
                if current_price > ema_value:
                    dynamic_support = ema_value
                # اگر قیمت زیر EMA50 باشد، EMA50 می‌تواند مقاومت باشد
                else:
                    dynamic_resistance = ema_value
            
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
