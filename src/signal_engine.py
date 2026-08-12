"""
Signal Engine Module
Core signal generation based on technical indicators and scoring
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd

from config import Config
from .indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    موتور تولید سیگنال بر اساس اندیکاتورها و امتیازدهی
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.indicators = TechnicalIndicators(config)
        
    def analyze_symbol(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        تحلیل کامل یک نماد و تولید سیگنال
        
        Args:
            df: DataFrame با داده‌های OHLCV (کندل‌های بسته شده)
            symbol: اسم ارز
            current_price: قیمت لحظه‌ای (از API جداگانه)
            
        Returns:
            دیکشنری شامل سیگنال و اطلاعات مربوطه
        """
        try:
            # =========================
            # ۱. محاسبه اندیکاتورها (بر اساس کندل‌های بسته شده)
            # =========================
            indicators = self.indicators.get_latest_values(df)
            if not indicators:
                logger.warning(f"⚠️ No indicators for {symbol}")
                return None
            
            # =========================
            # ۲. جایگزینی قیمت کندل با قیمت لحظه‌ای
            # =========================
            indicators['price'] = current_price
            
            # =========================
            # ۳. محاسبه امتیاز
            # =========================
            score_result = self._calculate_score(indicators, df)
            
            # =========================
            # ۴. تعیین سیگنال (با ارسال df)
            # =========================
            signal = self._determine_signal(
                score_result['total'], 
                indicators, 
                df
            )
            
            # =========================
            # ۵. محاسبه حد ضرر و اهداف (فقط برای BUY/SELL)
            # =========================
            if signal['action'] in ['BUY', 'SELL']:
                risk_levels = self._calculate_risk_levels(
                    indicators, df, signal['action']
                )
                
                # =========================
                # ۶. بررسی حداقل R/R از Config
                # =========================
                min_rr = getattr(self.config, 'MIN_ACCEPTABLE_RR', 1.5)
                if risk_levels.get('risk_reward', 0) < min_rr:
                    signal = {
                        'action': 'WAIT',
                        'strength': 'NEUTRAL',
                        'confidence': 50,
                        'exceptional': False,
                        'exceptional_reason': f'Low R/R: {risk_levels.get("risk_reward", 0):.2f}'
                    }
                    risk_levels = {
                        'stop_loss': None,
                        'tp1': None,
                        'tp2': None,
                        'risk_reward': None
                    }
            else:
                risk_levels = {
                    'stop_loss': None,
                    'tp1': None,
                    'tp2': None,
                    'risk_reward': None
                }
            
            # =========================
            # ۷. شناسایی حمایت و مقاومت (بدون کندل فعلی)
            # =========================
            sr_levels = self._get_support_resistance_without_current(df, indicators)
            
            return {
                'symbol': symbol,
                'price': current_price,
                'signal': signal['action'],
                'strength': signal['strength'],
                'score': score_result['total'],
                'score_breakdown': score_result['breakdown'],
                'confidence': signal['confidence'],
                'rsi': indicators.get('rsi', 50),
                'macd': indicators.get('macd_line', 0),
                'macd_signal': indicators.get('macd_signal', 0),
                'macd_histogram': indicators.get('macd_histogram', 0),
                'adx': indicators.get('adx', 20),
                'di_plus': indicators.get('di_plus', 0),
                'di_minus': indicators.get('di_minus', 0),
                'atr': indicators.get('atr', 0),
                'volume_ratio': indicators.get('volume_ratio', 1.0),
                'ema_fast': indicators.get('ema_fast', current_price),
                'ema_slow': indicators.get('ema_slow', current_price),
                'bb_upper': indicators.get('bb_upper', current_price * 1.1),
                'bb_lower': indicators.get('bb_lower', current_price * 0.9),
                'support': sr_levels.get('support'),
                'resistance': sr_levels.get('resistance'),
                'support_zone': sr_levels.get('support_zone'),
                'resistance_zone': sr_levels.get('resistance_zone'),
                'stop_loss': risk_levels['stop_loss'],
                'tp1': risk_levels['tp1'],
                'tp2': risk_levels['tp2'],
                'risk_reward': risk_levels['risk_reward'],
                'timestamp': pd.Timestamp.now()
            }
            
        except Exception as e:
            logger.error(f"❌ Error analyzing {symbol}: {e}")
            return None
    
    def _calculate_score(
        self, 
        indicators: Dict[str, Optional[float]], 
        df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        محاسبه امتیاز نهایی بر اساس اندیکاتورها
        با کنترل هم‌پوشانی عوامل
        """
        raw_score = 0
        max_possible = 0
        breakdown = {}
        
        # امن‌سازی مقادیر
        ema_fast = indicators.get('ema_fast') or 0
        ema_slow = indicators.get('ema_slow') or 0
        ema_trend = indicators.get('ema_trend') or 0
        price = indicators.get('price') or 0
        rsi = indicators.get('rsi') or 50
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_hist = indicators.get('macd_histogram') or 0
        
        # =========================
        # ۱. روند (Trend) - وزن: ۲۰
        # =========================
        trend_score = 0
        
        if ema_fast and ema_slow:
            if ema_fast > ema_slow:
                trend_score += 12
            else:
                trend_score -= 12
        
        if ema_trend and price:
            if price > ema_trend:
                trend_score += 8
            else:
                trend_score -= 8
        
        trend_score = max(-20, min(20, trend_score))
        breakdown['trend'] = trend_score
        raw_score += trend_score
        max_possible += 20
        
        # =========================
        # ۲. مومنتوم (Momentum) - وزن: ۲۰
        # =========================
        momentum_score = 0
        
        # RSI - وابسته به روند
        if trend_score > 0:  # روند صعودی
            if rsi < 30:
                momentum_score += 4
            elif rsi < 45:
                momentum_score += 2
            elif rsi < 55:
                momentum_score += 0
            elif rsi < 70:
                momentum_score += 6
            else:
                momentum_score += 3
        elif trend_score < 0:  # روند نزولی
            if rsi < 30:
                momentum_score -= 2
            elif rsi < 45:
                momentum_score -= 6
            elif rsi < 55:
                momentum_score += 0
            elif rsi < 70:
                momentum_score -= 2
            else:
                momentum_score += 1
        else:  # بدون روند مشخص
            if rsi < 30:
                momentum_score += 5
            elif rsi < 45:
                momentum_score += 3
            elif rsi < 55:
                momentum_score += 0
            elif rsi < 70:
                momentum_score -= 3
            else:
                momentum_score -= 5
        
        # MACD - با بررسی None
        if macd_line is not None and macd_signal is not None:
            if macd_line > macd_signal:
                momentum_score += 10
                if macd_hist > 0:
                    momentum_score += 2
            else:
                momentum_score -= 10
                if macd_hist < 0:
                    momentum_score -= 2
        
        momentum_score = max(-20, min(20, momentum_score))
        breakdown['momentum'] = momentum_score
        raw_score += momentum_score
        max_possible += 20
        
        # =========================
        # ۳. حجم (Volume) - وزن: ۱۵
        # =========================
        volume_score = 0
        volume_ratio = indicators.get('volume_ratio') or 1.0
        trend_direction = 1 if trend_score > 0 else (-1 if trend_score < 0 else 0)
        
        if volume_ratio < self.config.VERY_LOW_VOLUME_RATIO:
            volume_score -= 5
        elif volume_ratio < self.config.LOW_VOLUME_RATIO:
            volume_score -= 2
        elif volume_ratio > self.config.VERY_HIGH_VOLUME_RATIO:
            if trend_direction > 0:
                volume_score += 15
            elif trend_direction < 0:
                volume_score -= 15
            else:
                volume_score += 5
        elif volume_ratio > self.config.HIGH_VOLUME_RATIO:
            if trend_direction > 0:
                volume_score += 10
            elif trend_direction < 0:
                volume_score -= 10
            else:
                volume_score += 3
        
        volume_score = max(-15, min(15, volume_score))
        breakdown['volume'] = volume_score
        raw_score += volume_score
        max_possible += 15
        
        # =========================
        # ۴. نوسان (Volatility) - وزن: ۱۰
        # =========================
        volatility_score = 0
        bb_width = indicators.get('bb_width') or 0
        bb_upper = indicators.get('bb_upper') or 0
        bb_lower = indicators.get('bb_lower') or 0
        
        if bb_width:
            if bb_width < 0.05:
                volatility_score += 3
            elif bb_width > 0.20:
                volatility_score -= 3
        
        if bb_upper and bb_lower and price:
            if price <= bb_lower and trend_score > 0:
                volatility_score += 5
            elif price >= bb_upper and trend_score < 0:
                volatility_score -= 5
            elif price <= bb_lower:
                volatility_score += 2
            elif price >= bb_upper:
                volatility_score -= 2
        
        volatility_score = max(-10, min(10, volatility_score))
        breakdown['volatility'] = volatility_score
        raw_score += volatility_score
        max_possible += 10
        
        # =========================
        # ۵. شکست (Breakout) - وزن: ۱۵
        # =========================
        breakout_score = 0
        prev_data = df.iloc[:-1].tail(50)
        
        if len(prev_data) > 20:
            prev_high = prev_data['high'].max()
            prev_low = prev_data['low'].min()
            volume_ratio = indicators.get('volume_ratio') or 1.0
            
            if price > prev_high:
                if volume_ratio > self.config.HIGH_VOLUME_RATIO:
                    breakout_score += 15
                else:
                    breakout_score += 8
            elif price < prev_low:
                if volume_ratio > self.config.HIGH_VOLUME_RATIO:
                    breakout_score -= 15
                else:
                    breakout_score -= 8
            
            if prev_high and price:
                distance_to_resistance = (prev_high - price) / price * 100
                if 0 < distance_to_resistance < 2:
                    breakout_score += 3
        
        breakout_score = max(-15, min(15, breakout_score))
        breakdown['breakout'] = breakout_score
        raw_score += breakout_score
        max_possible += 15
        
        # =========================
        # ۶. حمایت و مقاومت (Support/Resistance) - وزن: ۱۰
        # =========================
        sr_score = 0
        sr_levels = self._get_support_resistance_without_current(df, indicators)
        support = sr_levels.get('support')
        resistance = sr_levels.get('resistance')
        
        if support and price:
            support_distance = (price - support) / price * 100
            if support_distance < 0:
                sr_score -= 5
            elif support_distance < 2:
                sr_score += 5
            elif support_distance < 5:
                sr_score += 2
        
        if resistance and price:
            resistance_distance = (resistance - price) / price * 100
            if resistance_distance < 0:
                sr_score += 5
            elif resistance_distance < 2:
                sr_score -= 5
            elif resistance_distance < 5:
                sr_score -= 2
        
        sr_score = max(-10, min(10, sr_score))
        breakdown['support_resistance'] = sr_score
        raw_score += sr_score
        max_possible += 10
        
        # =========================
        # ۷. ADX و جهت (اضافی) - وزن: ۱۰
        # با کنترل هم‌پوشانی با Trend
        # =========================
        adx_score = 0
        adx = indicators.get('adx') or 0
        di_plus = indicators.get('di_plus') or 0
        di_minus = indicators.get('di_minus') or 0
        trend_direction = 1 if trend_score > 0 else (-1 if trend_score < 0 else 0)
        
        # فقط اگر روند ضعیف باشد، ADX می‌تواند کمک کند
        # اگر روند قوی است، ADX فقط تأیید می‌کند نه امتیاز جدید
        if abs(trend_score) < 10:  # روند ضعیف یا متوسط
            if adx > self.config.ADX_VERY_STRONG:
                if trend_direction > 0:
                    adx_score += 4
                elif trend_direction < 0:
                    adx_score -= 4
            elif adx > self.config.ADX_STRONG:
                if trend_direction > 0:
                    adx_score += 2
                elif trend_direction < 0:
                    adx_score -= 2
        else:  # روند قوی - ADX فقط تأیید می‌کند
            if adx > self.config.ADX_VERY_STRONG:
                if trend_direction > 0:
                    adx_score += 2
                elif trend_direction < 0:
                    adx_score -= 2
        
        # جهت روند با DI - فقط در صورت عدم وجود جهت مشخص
        if di_plus and di_minus and abs(trend_score) < 5:
            if di_plus > di_minus:
                adx_score += 3
            elif di_minus > di_plus:
                adx_score -= 3
        
        adx_score = max(-10, min(10, adx_score))
        breakdown['adx'] = adx_score
        raw_score += adx_score
        max_possible += 10
        
        # =========================
        # نرمالایز کردن امتیاز نهایی به بازه 0-100
        # =========================
        normalized_score = 50 + (raw_score / max_possible) * 50 if max_possible > 0 else 50
        total_score = max(0, min(100, normalized_score))
        
        return {
            'total': round(total_score, 1),
            'breakdown': breakdown,
            'raw_score': raw_score,
            'max_possible': max_possible
        }
      def _determine_signal(
    self, 
    score: float, 
    indicators: Dict[str, Optional[float]],
    df: pd.DataFrame
) -> Dict[str, Any]:
    """
    تعیین سیگنال نهایی بر اساس امتیاز و شرایط استثنایی
    
    Args:
        score: امتیاز نهایی
        indicators: دیکشنری اندیکاتورها
        df: DataFrame اصلی برای محاسبه سطوح
    """
    # =========================
    # بررسی شرایط استثنایی - نیازمند چند تأیید همزمان
    # =========================
    exceptional = False
    exceptional_reason = None
    exceptional_direction = None
    
    # امن‌سازی مقادیر
    adx = indicators.get('adx') or 0
    di_plus = indicators.get('di_plus') or 0
    di_minus = indicators.get('di_minus') or 0
    volume_ratio = indicators.get('volume_ratio') or 1.0
    macd_hist = indicators.get('macd_histogram') or 0
    macd_line = indicators.get('macd_line')
    macd_signal = indicators.get('macd_signal')
    price = indicators.get('price') or 0
    
    # =========================
    # ۱. شرط Exceptional صعودی: 
    # ADX بسیار قوی + DI+ بالاتر + MACD صعودی + حجم بالا
    # =========================
    if (adx > 40 and 
        di_plus > di_minus and 
        macd_line is not None and macd_signal is not None and
        macd_line > macd_signal and 
        volume_ratio > 1.5):
        exceptional = True
        exceptional_reason = "very_strong_uptrend_confirmed"
        exceptional_direction = "BUY"
    
    # =========================
    # ۲. شرط Exceptional نزولی:
    # ADX بسیار قوی + DI- بالاتر + MACD نزولی + حجم بالا
    # =========================
    elif (adx > 40 and 
          di_minus > di_plus and 
          macd_line is not None and macd_signal is not None and
          macd_line < macd_signal and 
          volume_ratio > 1.5):
        exceptional = True
        exceptional_reason = "very_strong_downtrend_confirmed"
        exceptional_direction = "SELL"
    
    # =========================
    # ۳. شرط Exceptional سوم: شکست واقعی با حجم بسیار بالا
    # قیمت باید مقاومت/حمایت قبلی را شکسته باشد
    # =========================
    else:
        # دریافت سطوح مقاومت و حمایت قبلی با استفاده از df
        sr_levels = self._get_support_resistance_without_current(df, indicators)
        resistance = sr_levels.get('resistance')
        support = sr_levels.get('support')
        
        # شکست مقاومت با حجم بالا + ADX تأیید
        if (resistance is not None and 
            price > resistance and 
            volume_ratio > 2.5 and 
            macd_hist > 0 and 
            di_plus > di_minus and
            adx > 25):
            exceptional = True
            exceptional_reason = "breakout_resistance_with_high_volume"
            exceptional_direction = "BUY"
        
        # شکست حمایت با حجم بالا + ADX تأیید
        elif (support is not None and 
              price < support and 
              volume_ratio > 2.5 and 
              macd_hist < 0 and 
              di_minus > di_plus and
              adx > 25):
            exceptional = True
            exceptional_reason = "breakout_support_with_high_volume"
            exceptional_direction = "SELL"
    
    # =========================
    # اعمال Exceptional - فقط در صورت هماهنگی با امتیاز
    # =========================
    if exceptional and exceptional_direction:
        # Exceptional BUY: فقط اگر score >= 55 باشد
        if exceptional_direction == "BUY" and score >= 55:
            return self._create_signal(
                score, 
                "BUY", 
                "EXCEPTIONAL", 
                exceptional, 
                exceptional_reason
            )
        # Exceptional SELL: فقط اگر score <= 45 باشد
        elif exceptional_direction == "SELL" and score <= 45:
            return self._create_signal(
                score, 
                "SELL", 
                "EXCEPTIONAL", 
                exceptional, 
                exceptional_reason
            )
        # اگر Exceptional با امتیاز هماهنگ نبود، به حالت عادی برگرد
        else:
            logger.debug(f"Exceptional {exceptional_direction} ignored due to score {score}")
    
    # =========================
    # تعیین سیگنال عادی بر اساس محدوده امتیاز
    # =========================
    if score < 40:
        return self._create_signal(score, "SELL", "STRONG", False, None)
    elif score < 45:
        return self._create_signal(score, "SELL", "NORMAL", False, None)
    elif score < 50:
        return self._create_signal(score, "SELL", "WEAK", False, None)
    elif score <= 55:
        return {
            'action': 'WAIT',
            'strength': 'NEUTRAL',
            'confidence': 50,
            'exceptional': False,
            'exceptional_reason': None
        }
    elif score < 60:
        return self._create_signal(score, "BUY", "WEAK", False, None)
    elif score < 70:
        return self._create_signal(score, "BUY", "NORMAL", False, None)
    elif score < 80:
        return self._create_signal(score, "BUY", "STRONG", False, None)
    else:
        return self._create_signal(score, "BUY", "VERY_STRONG", False, None)

def _create_signal(
    self, 
    score: float, 
    action: str, 
    strength: str,
    exceptional: bool,
    exceptional_reason: Optional[str]
) -> Dict[str, Any]:
    """ساخت دیکشنری سیگنال با اطمینان مناسب"""
    if action == "BUY":
        confidence = min(95, 50 + (score - 50) * 0.9)
    else:  # SELL
        confidence = min(95, 50 + (50 - score) * 0.9)
    
    return {
        'action': action,
        'strength': strength,
        'confidence': round(confidence, 1),
        'exceptional': exceptional,
        'exceptional_reason': exceptional_reason
    }

def _calculate_risk_levels(
    self, 
    indicators: Dict[str, Optional[float]], 
    df: pd.DataFrame,
    action: str
) -> Dict[str, Optional[float]]:
    """
    محاسبه حد ضرر و اهداف بر اساس ATR و جهت سیگنال
    با استفاده از حمایت/مقاومت به عنوان فیلتر
    """
    if action not in ['BUY', 'SELL']:
        return {
            'stop_loss': None,
            'tp1': None,
            'tp2': None,
            'risk_reward': None
        }
    
    price = indicators.get('price') or 0
    atr = indicators.get('atr') or (price * 0.02)
    
    if atr is None or atr == 0:
        atr = price * 0.02
    
    # =========================
    # ۱. محاسبه SL پایه بر اساس ATR
    # =========================
    sl_multiplier = self.config.ATR_SL_MULTIPLIER
    if indicators.get('bb_width', 0) > 0.15:
        sl_multiplier = self.config.ATR_SL_MULTIPLIER_HIGH_VOLATILITY
    
    if action == 'BUY':
        base_sl = price - (atr * sl_multiplier)
    else:  # SELL
        base_sl = price + (atr * sl_multiplier)
    
    # =========================
    # ۲. دریافت سطوح S/R برای فیلتر کردن
    # =========================
    sr_levels = self._get_support_resistance_without_current(df, indicators)
    support = sr_levels.get('support')
    resistance = sr_levels.get('resistance')
    
    # =========================
    # ۳. اعمال فیلتر S/R (نه جایگزینی کامل)
    # =========================
    final_sl = base_sl
    
    if action == 'BUY' and support is not None:
        # اگر حمایت از SL پایه پایین‌تر است، از حمایت استفاده کن
        # اما با یک بافر کوچک (0.5% پایین‌تر از حمایت)
        if support > base_sl:
            # بررسی فاصله حمایت تا SL پایه
            distance_pct = (support - base_sl) / price * 100
            if distance_pct < 2:  # اگر خیلی نزدیک است، از حمایت استفاده کن
                final_sl = support * 0.995
            else:
                # اگر فاصله زیاد است، به حمایت نزدیک‌تر شو ولی نه کاملاً
                final_sl = base_sl + (support - base_sl) * 0.5
    
    elif action == 'SELL' and resistance is not None:
        if resistance < base_sl:
            distance_pct = (base_sl - resistance) / price * 100
            if distance_pct < 2:
                final_sl = resistance * 1.005
            else:
                final_sl = base_sl - (base_sl - resistance) * 0.5
    
    # =========================
    # ۴. اعمال محدودیت درصدی (فقط به عنوان sanity check)
    # =========================
    if action == 'BUY':
        sl_percent = (price - final_sl) / price * 100
        if sl_percent < self.config.MIN_SL_PERCENT:
            # اگر SL خیلی نزدیک است، آن را به حداقل برسان
            final_sl = price * (1 - self.config.MIN_SL_PERCENT / 100)
            logger.debug(f"SL adjusted to minimum: {self.config.MIN_SL_PERCENT}%")
        elif sl_percent > self.config.MAX_SL_PERCENT:
            # اگر SL خیلی دور است، سیگنال را خطرناک در نظر بگیر
            # اما SL را به حداکثر نرسان - بهتر است WAIT شود
            logger.warning(f"SL too wide: {sl_percent:.2f}% > {self.config.MAX_SL_PERCENT}%")
            # برگرداندن SL با حداکثر فاصله
            final_sl = price * (1 - self.config.MAX_SL_PERCENT / 100)
    
    else:  # SELL
        sl_percent = (final_sl - price) / price * 100
        if sl_percent < self.config.MIN_SL_PERCENT:
            final_sl = price * (1 + self.config.MIN_SL_PERCENT / 100)
            logger.debug(f"SL adjusted to minimum: {self.config.MIN_SL_PERCENT}%")
        elif sl_percent > self.config.MAX_SL_PERCENT:
            logger.warning(f"SL too wide: {sl_percent:.2f}% > {self.config.MAX_SL_PERCENT}%")
            final_sl = price * (1 + self.config.MAX_SL_PERCENT / 100)
    
    # =========================
    # ۵. محاسبه اهداف
    # =========================
    if action == 'BUY':
        tp1 = price + (atr * self.config.ATR_TP1_MULTIPLIER)
        tp2 = price + (atr * self.config.ATR_TP2_MULTIPLIER)
        risk = price - final_sl
        reward_1 = tp1 - price
    else:  # SELL
        tp1 = price - (atr * self.config.ATR_TP1_MULTIPLIER)
        tp2 = price - (atr * self.config.ATR_TP2_MULTIPLIER)
        risk = final_sl - price
        reward_1 = price - tp1
    
    risk_reward = reward_1 / risk if risk > 0 else 0
    
    return {
        'stop_loss': round(final_sl, 2),
        'tp1': round(tp1, 2),
        'tp2': round(tp2, 2),
        'risk_reward': round(risk_reward, 2)
    }

def _get_support_resistance_without_current(
    self, 
    df: pd.DataFrame,
    indicators: Dict[str, Optional[float]]
) -> Dict[str, Optional[float]]:
    """
    شناسایی سطوح حمایت و مقاومت بدون استفاده از کندل فعلی
    با مناطق پویا بر اساس ATR
    """
    try:
        # استفاده از کندل‌های قبلی (به جز آخرین کندل)
        prev_data = df.iloc[:-1].tail(50)
        
        # اگر داده کافی نیست، None برگردان
        if len(prev_data) < 20:
            return {
                'support': None,
                'resistance': None,
                'support_zone': None,
                'resistance_zone': None
            }
        
        # =========================
        # ۱. محاسبه سطوح ساده
        # =========================
        resistance = float(prev_data['high'].max())
        support = float(prev_data['low'].min())
        price = indicators.get('price') or 0
        
        # =========================
        # ۲. محاسبه مناطق پویا بر اساس ATR
        # =========================
        if price > 0:
            atr = indicators.get('atr') or (price * 0.02)
            if atr is None or atr == 0:
                atr = price * 0.02
            
            atr_percent = (atr / price) * 100
            zone_percent = max(0.5, min(3.0, atr_percent * 0.5))
        else:
            zone_percent = 1.0
        
        # =========================
        # ۳. ساخت مناطق
        # =========================
        support_zone = (support * (1 - zone_percent / 100), 
                       support * (1 + zone_percent / 100))
        resistance_zone = (resistance * (1 - zone_percent / 100), 
                           resistance * (1 + zone_percent / 100))
        
        return {
            'support': support,
            'resistance': resistance,
            'support_zone': support_zone,
            'resistance_zone': resistance_zone
        }
        
    except Exception as e:
        logger.error(f"Error calculating Support/Resistance without current: {e}")
        return {
            'support': None,
            'resistance': None,
            'support_zone': None,
            'resistance_zone': None
        }

def get_top_opportunities(
    self, 
    results: List[Dict[str, Any]], 
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    انتخاب بهترین فرصت‌های معاملاتی از بین نتایج
    """
    # فیلتر سیگنال‌های WAIT
    active_signals = [r for r in results if r and r['signal'] != 'WAIT']
    
    def calculate_priority(signal: Dict[str, Any]) -> float:
        """محاسبه امتیاز اولویت برای یک سیگنال"""
        score = signal.get('score', 50)
        confidence = signal.get('confidence', 50)
        risk_reward = signal.get('risk_reward') or 0
        signal_type = signal.get('signal', 'WAIT')
        
        # =========================
        # ۱. نرمالایز کردن امتیاز بر اساس جهت سیگنال
        # =========================
        if signal_type == 'BUY':
            normalized_score = score
        else:  # SELL
            normalized_score = 100 - score
        
        # =========================
        # ۲. قدرت سیگنال
        # =========================
        strength_boost = {
            'WEAK': 0,
            'NORMAL': 5,
            'STRONG': 10,
            'VERY_STRONG': 15,
            'EXCEPTIONAL': 20
        }.get(signal.get('strength'), 0)
        
        # =========================
        # ۳. محاسبه اولویت نهایی
        # =========================
        # محدود کردن R/R به 5 برای جلوگیری از اعداد بسیار بزرگ
        rr_score = min(risk_reward, 5) * 5  # حداکثر 25 امتیاز
        
        priority = (
            (normalized_score * 0.35) +   # 35% امتیاز (حداکثر 35)
            (confidence * 0.25) +          # 25% اطمینان (حداکثر 23.75)
            (rr_score) +                   # 25% نسبت ریسک/بازده (حداکثر 25)
            (strength_boost)               # 15% قدرت سیگنال (حداکثر 20)
        )
        
        return priority
    
    sorted_signals = sorted(
        active_signals,
        key=calculate_priority,
        reverse=True
    )
    
    return sorted_signals[:limit]
