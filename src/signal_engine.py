"""
Signal Engine Module
Core signal generation based on technical indicators and scoring
"""

import logging
from typing import Optional, Dict, Any, List

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

        # ================================================
        # آستانهها از Config
        # ================================================
        self.MIN_ACCEPTABLE_RR = config.MIN_ACCEPTABLE_RR
        self.MIN_SCORE = config.MIN_SCORE
        self.MIN_DATA_QUALITY = config.MIN_DATA_QUALITY
        self.MAX_RR_FOR_PRIORITY = config.MAX_RR_FOR_PRIORITY
        self.MIN_SELL_CONFIDENCE = config.MIN_SELL_CONFIDENCE
        
        # ================================================
        # آستانههای متقارن BUY/SELL (اضافه شده)
        # ================================================
        self.BUY_THRESHOLD = config.BUY_THRESHOLD
        self.SELL_THRESHOLD = config.SELL_THRESHOLD

    def _format_price(self, price: float) -> float:
        """
        فرمت قیمت بر اساس اندازه آن.
        فقط برای خروجی نهایی است؛ محاسبات داخلی با مقدار کامل انجام میشوند.
        """
        if price == 0:
            return 0.0

        if price >= 1000:
            decimals = 2
        elif price >= 1:
            decimals = 3
        elif price >= 0.01:
            decimals = 4
        elif price >= 0.0001:
            decimals = 6
        else:
            decimals = 8

        return round(price, decimals)

    def _get_signal_rating(self, score: float) -> Dict[str, Any]:
        """
        تعیین رتبهبندی سیگنال بر اساس Score
        """
        if score < 80:
            return {
                'rating': 'WAIT',
                'stars': '⚪',
                'level': 'NO_TRADE',
                'description': 'Score below minimum threshold'
            }
        elif score < 85:
            return {
                'rating': '⭐',
                'stars': '⭐',
                'level': 'WEAK',
                'description': 'Weak signal, low confidence'
            }
        elif score < 90:
            return {
                'rating': '⭐⭐',
                'stars': '⭐⭐',
                'level': 'MODERATE',
                'description': 'Moderate signal, acceptable'
            }
        elif score < 93:
            return {
                'rating': '⭐⭐⭐',
                'stars': '⭐⭐⭐',
                'level': 'GOOD',
                'description': 'Good signal, high confidence'
            }
        elif score < 96:
            return {
                'rating': '⭐⭐⭐⭐',
                'stars': '⭐⭐⭐⭐',
                'level': 'STRONG',
                'description': 'Strong signal, very high confidence'
            }
        else:
            return {
                'rating': '🔥⭐⭐⭐⭐⭐🔥',
                'stars': '🔥⭐⭐⭐⭐⭐🔥',
                'level': 'EXCEPTIONAL',
                'description': 'Exceptional signal, maximum confidence'
            }

    def analyze_symbol(
        self,
        df: pd.DataFrame,
        symbol: str,
        current_price: float,
        data_quality: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        تحلیل کامل یک نماد و تولید سیگنال

        Args:
            df: DataFrame OHLCV
            symbol: نام نماد
            current_price: قیمت لحظهای
            data_quality: گزارش کیفیت داده از DataFetcher (اجباری)
        """
        # ================================================
        # STEP 1: DATA QUALITY GATE (HARD GATE - اجباری)
        # ================================================
        if not data_quality:
            logger.error(f"🚫 {symbol}: No Data Quality report provided - REJECTED")
            return None

        quality_score = data_quality.get('quality_score', 0)
        gate_status = data_quality.get('gate_result', {}).get('status', 'REJECT')

        if gate_status == 'REJECT':
            logger.warning(
                f"🚫 {symbol}: Data Quality REJECTED - "
                f"Gate Status: {gate_status}"
            )
            return None

        if quality_score < self.MIN_DATA_QUALITY:
            logger.warning(
                f"🚫 {symbol}: Data Quality too low - "
                f"Score={quality_score:.1f}% < {self.MIN_DATA_QUALITY}%"
            )
            return None

        try:
            # ================================================
            # STEP 2: INDICATORS
            # ================================================
            indicators = self.indicators.get_latest_values(df)
            if not indicators:
                logger.warning(f"⚠️ No indicators for {symbol}")
                return None

            indicators['price'] = current_price

            # ================================================
            # STEP 3: SCORE
            # ================================================
            score_result = self._calculate_score(indicators, df)

            logger.info(
                f"📊 {symbol}: "
                f"Score={score_result['total']:.1f} | "
                f"Trend={score_result['breakdown'].get('trend', 0)} | "
                f"Momentum={score_result['breakdown'].get('momentum', 0)} | "
                f"Volume={score_result['breakdown'].get('volume', 0)} | "
                f"Volatility={score_result['breakdown'].get('volatility', 0)} | "
                f"Breakout={score_result['breakdown'].get('breakout', 0)} | "
                f"S/R={score_result['breakdown'].get('support_resistance', 0)} | "
                f"ADX={score_result['breakdown'].get('adx', 0)}"
            )

            # ================================================
            # STEP 4: SIGNAL RATING (⭐ SYSTEM)
            # ================================================
            signal_rating = self._get_signal_rating(score_result['total'])

            # اگر امتیاز زیر MIN_SCORE باشد، سیگنال معاملاتی تولید نمیشود
            if score_result['total'] < self.MIN_SCORE:
                logger.info(
                    f"⚪ {symbol}: Score={score_result['total']:.1f} < {self.MIN_SCORE} - WAIT"
                )
                return {
                    'symbol': symbol,
                    'price': current_price,
                    'signal': 'WAIT',
                    'strength': 'NO_TRADE',
                    'score': score_result['total'],
                    'score_breakdown': score_result['breakdown'],
                    'confidence': 0,
                    'signal_rating': signal_rating,
                    'exceptional': False,
                    'exceptional_reason': None,
                    'timestamp': pd.Timestamp.now(),
                    'data_quality': data_quality,
                    'position_size': 0.0,
                    'position_value': 0.0
                }

            # ================================================
            # STEP 5: DETERMINE SIGNAL
            # ================================================
            signal = self._determine_signal(
                score_result['total'],
                indicators,
                df
            )

            # ================================================
            # STEP 6: RISK LEVELS (با قیمت خام)
            # ================================================
            # مقداردهی اولیه risk_levels برای همه مسیرها
            risk_levels = {
                'stop_loss_raw': None,
                'tp1_raw': None,
                'tp2_raw': None,
                'risk_reward': 0
            }
            risk_levels_display = {
                'stop_loss': None,
                'tp1': None,
                'tp2': None,
                'risk_reward': None
            }

            if signal['action'] in ['BUY', 'SELL']:
                risk_levels = self._calculate_risk_levels(
                    indicators, df, signal['action']
                )

                logger.info(
                    f"🎯 {symbol}: "
                    f"Action={signal['action']} | "
                    f"Score={score_result['total']:.1f} | "
                    f"SL={risk_levels.get('stop_loss_raw')} | "
                    f"TP1={risk_levels.get('tp1_raw')} | "
                    f"TP2={risk_levels.get('tp2_raw')} | "
                    f"RR={risk_levels.get('risk_reward')}"
                )

                # بررسی R/R
                if risk_levels.get('risk_reward', 0) < self.MIN_ACCEPTABLE_RR:
                    logger.info(
                        f"❌ {symbol}: Rejected by R/R | "
                        f"Score={score_result['total']:.1f} | "
                        f"RR={risk_levels.get('risk_reward', 0):.2f} | "
                        f"Required={self.MIN_ACCEPTABLE_RR}"
                    )
                    return {
                        'symbol': symbol,
                        'price': current_price,
                        'signal': 'WAIT',
                        'strength': 'NEUTRAL',
                        'score': score_result['total'],
                        'score_breakdown': score_result['breakdown'],
                        'confidence': signal.get('confidence', 0),
                        'signal_rating': signal_rating,
                        'exceptional': signal.get('exceptional', False),
                        'exceptional_reason': signal.get('exceptional_reason'),
                        'reason': f'Low R/R: {risk_levels.get("risk_reward", 0):.2f}',
                        'timestamp': pd.Timestamp.now(),
                        'data_quality': data_quality,
                        'position_size': 0.0,
                        'position_value': 0.0
                    }

                # تبدیل قیمتها برای نمایش (فقط خروجی)
                risk_levels_display = {
                    'stop_loss': self._format_price(risk_levels.get('stop_loss_raw')),
                    'tp1': self._format_price(risk_levels.get('tp1_raw')),
                    'tp2': self._format_price(risk_levels.get('tp2_raw')),
                    'risk_reward': risk_levels.get('risk_reward')
                }

            # ================================================
            # STEP 7: CONFIDENCE (چندعاملی)
            # ================================================
            confidence = self._calculate_confidence(
                score_result['total'],
                indicators,
                signal,
                risk_levels.get('risk_reward', 0),
                data_quality
            )

            # ================================================
            # STEP 8: SELL CONFIDENCE CHECK
            # ================================================
            if signal['action'] == 'SELL' and confidence < self.MIN_SELL_CONFIDENCE:
                logger.info(
                    f"❌ {symbol}: SELL rejected by Confidence | "
                    f"Confidence={confidence:.1f}% < {self.MIN_SELL_CONFIDENCE}%"
                )
                return {
                    'symbol': symbol,
                    'price': current_price,
                    'signal': 'WAIT',
                    'strength': 'NEUTRAL',
                    'score': score_result['total'],
                    'score_breakdown': score_result['breakdown'],
                    'confidence': confidence,
                    'signal_rating': signal_rating,
                    'exceptional': signal.get('exceptional', False),
                    'exceptional_reason': signal.get('exceptional_reason'),
                    'reason': f'Low confidence for SELL: {confidence:.1f}%',
                    'timestamp': pd.Timestamp.now(),
                    'data_quality': data_quality,
                    'position_size': 0.0,
                    'position_value': 0.0
                }

            # ================================================
            # STEP 9: SUPPORT/RESISTANCE
            # ================================================
            sr_levels = self.indicators.get_support_resistance(df)

            # ================================================
            # STEP 10: RESULT
            # ================================================
            return {
                'symbol': symbol,
                'price': current_price,
                'signal': signal['action'],
                'strength': signal['strength'],
                'score': score_result['total'],
                'score_breakdown': score_result['breakdown'],
                'confidence': confidence,
                'signal_rating': signal_rating,
                'signal_importance': signal_rating['stars'],
                'exceptional': signal.get('exceptional', False),
                'exceptional_reason': signal.get('exceptional_reason'),
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
                'stop_loss': risk_levels_display['stop_loss'],
                'stop_loss_raw': risk_levels.get('stop_loss_raw'),
                'tp1': risk_levels_display['tp1'],
                'tp1_raw': risk_levels.get('tp1_raw'),
                'tp2': risk_levels_display['tp2'],
                'tp2_raw': risk_levels.get('tp2_raw'),
                'risk_reward': risk_levels_display['risk_reward'],
                'timestamp': pd.Timestamp.now(),
                'data_quality': data_quality,
                # ================================================
                # 🔥 اضافه شده برای هماهنگی با ExecutionManager
                # ================================================
                'position_size': 0.25,  # مقدار پیشفرض (ExecutionManager بازنویسی میکنه)
                'position_value': 0.25,  # برای Paper Trading
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
        محاسبه امتیاز سیگنال (0-100)
        """
        raw_score = 0
        max_possible = 0
        breakdown = {}

        ema_fast = indicators.get('ema_fast') or 0
        ema_slow = indicators.get('ema_slow') or 0
        ema_trend = indicators.get('ema_trend') or 0
        price = indicators.get('price') or 0
        rsi = indicators.get('rsi') or 50
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_hist = indicators.get('macd_histogram') or 0

        # ================================================
        # TREND (متقارن)
        # ================================================
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

        # ================================================
        # MOMENTUM (متقارن)
        # ================================================
        momentum_score = 0
        trend_direction = 1 if trend_score > 0 else (-1 if trend_score < 0 else 0)

        if trend_direction > 0:
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
        elif trend_direction < 0:
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
        else:
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

        # ================================================
        # VOLUME (متقارن)
        # ================================================
        volume_score = 0
        volume_ratio = indicators.get('volume_ratio') or 1.0

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

        # ================================================
        # VOLATILITY
        # ================================================
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
            if price <= bb_lower and trend_direction > 0:
                volatility_score += 5
            elif price >= bb_upper and trend_direction < 0:
                volatility_score -= 5
            elif price <= bb_lower:
                volatility_score += 2
            elif price >= bb_upper:
                volatility_score -= 2

        volatility_score = max(-10, min(10, volatility_score))
        breakdown['volatility'] = volatility_score
        raw_score += volatility_score
        max_possible += 10

        # ================================================
        # BREAKOUT (متقارن)
        # ================================================
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

        # ================================================
        # SUPPORT/RESISTANCE (متقارن)
        # ================================================
        sr_score = 0
        sr_levels = self.indicators.get_support_resistance(df)
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

        # ================================================
        # ADX (متقارن)
        # ================================================
        adx_score = 0
        adx = indicators.get('adx') or 0
        di_plus = indicators.get('di_plus') or 0
        di_minus = indicators.get('di_minus') or 0

        if abs(trend_score) < 10:
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
        else:
            if adx > self.config.ADX_VERY_STRONG:
                if trend_direction > 0:
                    adx_score += 2
                elif trend_direction < 0:
                    adx_score -= 2

        if di_plus and di_minus and abs(trend_score) < 5:
            if di_plus > di_minus:
                adx_score += 3
            elif di_minus > di_plus:
                adx_score -= 3

        adx_score = max(-10, min(10, adx_score))
        breakdown['adx'] = adx_score
        raw_score += adx_score
        max_possible += 10

        # ================================================
        # NORMALIZE
        # ================================================
        normalized_score = 50 + (raw_score / max_possible) * 50 if max_possible > 0 else 50
        total_score = max(0, min(100, normalized_score))

        return {
            'total': round(total_score, 1),
            'breakdown': breakdown,
            'raw_score': raw_score,
            'max_possible': max_possible,
            'trend_direction': trend_direction
        }

    def _calculate_confidence(
        self,
        score: float,
        indicators: Dict[str, Optional[float]],
        signal: Dict[str, Any],
        rr: float,
        data_quality: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        محاسبه Confidence بر اساس چند عامل مستقل
        """
        # شروع از Score
        confidence = score

        # ================================================
        # 1. Trend Strength
        # ================================================
        adx = indicators.get('adx') or 0
        if adx > 40:
            confidence += 3
        elif adx > 25:
            confidence += 1
        elif adx < 20:
            confidence -= 3

        # ================================================
        # 2. DI Alignment
        # ================================================
        di_plus = indicators.get('di_plus') or 0
        di_minus = indicators.get('di_minus') or 0
        if signal['action'] == 'BUY' and di_plus > di_minus:
            confidence += 2
        elif signal['action'] == 'SELL' and di_minus > di_plus:
            confidence += 2
        elif abs(di_plus - di_minus) < 5:
            confidence -= 2

        # ================================================
        # 3. MACD Alignment
        # ================================================
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_hist = indicators.get('macd_histogram') or 0

        if macd_line is not None and macd_signal is not None:
            if signal['action'] == 'BUY' and macd_line > macd_signal:
                confidence += 3
                if macd_hist > 0:
                    confidence += 1
            elif signal['action'] == 'SELL' and macd_line < macd_signal:
                confidence += 3
                if macd_hist < 0:
                    confidence += 1
            else:
                confidence -= 2

        # ================================================
        # 4. Volume Confirmation
        # ================================================
        volume_ratio = indicators.get('volume_ratio') or 1.0
        if volume_ratio > 2.0:
            confidence += 3
        elif volume_ratio > 1.5:
            confidence += 1
        elif volume_ratio < 0.7:
            confidence -= 2

        # ================================================
        # 5. Exceptional Bonus
        # ================================================
        if signal.get('exceptional', False):
            confidence += 5

        # ================================================
        # 6. Risk/Reward
        # ================================================
        if rr >= 3.0:
            confidence += 3
        elif rr >= 2.0:
            confidence += 1
        elif rr < 1.5:
            confidence -= 3

        # ================================================
        # 7. Data Quality
        # ================================================
        if data_quality:
            dq_score = data_quality.get('quality_score', 0)
            if dq_score >= 90:
                confidence += 2
            elif dq_score >= 80:
                confidence += 1
            elif dq_score < 70:
                confidence -= 3

        # ================================================
        # محدود کردن نهایی
        # ================================================
        # اگر Score پایین است، Confidence نمیتواند خیلی بالا باشد
        if score < self.BUY_THRESHOLD and score > self.SELL_THRESHOLD:
            confidence = min(confidence, score + 10)

        # اگر Score بالا است، Confidence را محدود نمیکنیم
        confidence = max(0, min(100, confidence))

        return round(confidence, 1)

    def _determine_signal(
        self,
        score: float,
        indicators: Dict[str, Optional[float]],
        df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        تعیین جهت سیگنال و قدرت آن
        """
        exceptional = False
        exceptional_reason = None

        # تعریف متغیرها در scope تابع
        adx = indicators.get('adx') or 0
        di_plus = indicators.get('di_plus') or 0
        di_minus = indicators.get('di_minus') or 0
        volume_ratio = indicators.get('volume_ratio') or 1.0
        macd_hist = indicators.get('macd_histogram') or 0
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        price = indicators.get('price') or 0

        # ================================================
        # EXCEPTIONAL BUY
        # ================================================
        if (
            score >= self.config.EXCEPTIONAL_SIGNAL_SCORE and
            adx > 40 and
            di_plus > di_minus and
            macd_line is not None and macd_signal is not None and
            macd_line > macd_signal and
            volume_ratio > 1.5
        ):
            exceptional = True
            exceptional_reason = "very_strong_uptrend_confirmed"
        # ================================================
        # EXCEPTIONAL SELL (متقارن + تأییدات اضافی)
        # ================================================
        elif (
            score <= (100 - self.config.EXCEPTIONAL_SIGNAL_SCORE) and  # 10
            adx > 40 and
            di_minus > di_plus and
            macd_line is not None and macd_signal is not None and
            macd_line < macd_signal and
            macd_hist < 0 and
            volume_ratio > 1.5
        ):
            exceptional = True
            exceptional_reason = "very_strong_downtrend_confirmed"

        # ================================================
        # BREAKOUT EXCEPTIONAL BUY
        # ================================================
        else:
            sr_levels = self.indicators.get_support_resistance(df)
            resistance = sr_levels.get('resistance')
            support = sr_levels.get('support')

            if (
                score >= (self.BUY_THRESHOLD + 15) and  # 80
                resistance is not None and
                price > resistance and
                volume_ratio > 2.5 and
                macd_hist > 0 and
                di_plus > di_minus and
                adx > 25
            ):
                exceptional = True
                exceptional_reason = "breakout_resistance_with_high_volume"

            # ================================================
            # BREAKOUT EXCEPTIONAL SELL (متقارن + تأییدات اضافی)
            # ================================================
            elif (
                score <= (self.SELL_THRESHOLD - 15) and  # 20
                support is not None and
                price < support and
                volume_ratio > 2.5 and
                macd_hist < 0 and
                di_minus > di_plus and
                adx > 25
            ):
                exceptional = True
                exceptional_reason = "breakout_support_with_high_volume"

        # ================================================
        # تعیین سیگنال اصلی (متقارن با آستانههای جدید)
        # ================================================
        if score >= self.BUY_THRESHOLD:
            action = "BUY"
            if score >= self.config.EXCEPTIONAL_SIGNAL_SCORE:
                strength = "VERY_STRONG"
            elif score >= self.config.STRONG_SIGNAL_SCORE:
                strength = "STRONG"
            else:
                strength = "NORMAL"
        elif score <= self.SELL_THRESHOLD:
            action = "SELL"
            if score <= (100 - self.config.EXCEPTIONAL_SIGNAL_SCORE):  # 10
                strength = "VERY_STRONG"
            elif score <= (100 - self.config.STRONG_SIGNAL_SCORE):  # 20
                strength = "STRONG"
            else:
                strength = "NORMAL"
        else:
            return {
                'action': 'WAIT',
                'strength': 'NEUTRAL',
                'confidence': 50,
                'exceptional': False,
                'exceptional_reason': None
            }

        # ================================================
        # بررسی تأییدات اضافی برای SELL
        # ================================================
        if action == "SELL":
            sell_conditions_met = (
                di_minus > di_plus and
                macd_line is not None and
                macd_signal is not None and
                macd_line < macd_signal and
                macd_hist < 0 and
                adx >= 25
            )
            
            if not sell_conditions_met:
                macd_condition = (
                    macd_line is not None and
                    macd_signal is not None and
                    macd_line < macd_signal
                )
                logger.debug(
                    f"SELL conditions not met: "
                    f"DI-={di_minus:.1f} > DI+={di_plus:.1f} = {di_minus > di_plus}, "
                    f"MACD={macd_line} < Signal={macd_signal} = {macd_condition}, "
                    f"Hist={macd_hist} < 0 = {macd_hist < 0}, "
                    f"ADX={adx:.1f} >= 25 = {adx >= 25}"
                )
                return {
                    'action': 'WAIT',
                    'strength': 'NEUTRAL',
                    'confidence': 50,
                    'exceptional': False,
                    'exceptional_reason': 'SELL conditions not met'
                }

        # اگر Exceptional است و شرایطش برقرار است
        if exceptional:
            return {
                'action': action,
                'strength': f"EXCEPTIONAL_{strength}",
                'confidence': min(98, 90 + (score - 50) * 0.2),
                'exceptional': True,
                'exceptional_reason': exceptional_reason
            }

        return {
            'action': action,
            'strength': strength,
            'confidence': min(90, 50 + (abs(score - 50) * 0.8)),
            'exceptional': False,
            'exceptional_reason': None
        }

    def _calculate_risk_levels(
        self,
        indicators: Dict[str, Optional[float]],
        df: pd.DataFrame,
        action: str
    ) -> Dict[str, Optional[float]]:
        """
        محاسبه حد ضرر و اهداف بر اساس ATR و جهت سیگنال
        با استفاده از قیمت خام (بدون گرد کردن)
        """
        if action not in ['BUY', 'SELL']:
            return {
                'stop_loss_raw': None,
                'tp1_raw': None,
                'tp2_raw': None,
                'risk_reward': None
            }

        price = indicators.get('price') or 0
        atr = indicators.get('atr') or (price * 0.02)

        if atr is None or atr == 0:
            atr = price * 0.02

        sl_multiplier = self.config.ATR_SL_MULTIPLIER
        if indicators.get('bb_width', 0) > 0.15:
            sl_multiplier = self.config.ATR_SL_MULTIPLIER_HIGH_VOLATILITY

        # ================================================
        # محاسبه SL با قیمت خام (بدون گرد کردن)
        # ================================================
        if action == 'BUY':
            final_sl = price - (atr * sl_multiplier)
        else:
            final_sl = price + (atr * sl_multiplier)

        # ================================================
        # اعمال محدودیت درصدی
        # ================================================
        if action == 'BUY':
            sl_percent = (price - final_sl) / price * 100
            if sl_percent < self.config.MIN_SL_PERCENT:
                final_sl = price * (1 - self.config.MIN_SL_PERCENT / 100)
                logger.debug(f"SL adjusted to minimum: {self.config.MIN_SL_PERCENT}%")
            elif sl_percent > self.config.MAX_SL_PERCENT:
                logger.warning(f"SL too wide: {sl_percent:.2f}% > {self.config.MAX_SL_PERCENT}%")
                final_sl = price * (1 - self.config.MAX_SL_PERCENT / 100)

        else:
            sl_percent = (final_sl - price) / price * 100
            if sl_percent < self.config.MIN_SL_PERCENT:
                final_sl = price * (1 + self.config.MIN_SL_PERCENT / 100)
                logger.debug(f"SL adjusted to minimum: {self.config.MIN_SL_PERCENT}%")
            elif sl_percent > self.config.MAX_SL_PERCENT:
                logger.warning(f"SL too wide: {sl_percent:.2f}% > {self.config.MAX_SL_PERCENT}%")
                final_sl = price * (1 + self.config.MAX_SL_PERCENT / 100)

        # ================================================
        # محاسبه اهداف با قیمت خام
        # ================================================
        if action == 'BUY':
            tp1 = price + (atr * self.config.ATR_TP1_MULTIPLIER)
            tp2 = price + (atr * self.config.ATR_TP2_MULTIPLIER)
            risk = price - final_sl
            reward_1 = tp1 - price
        else:
            tp1 = price - (atr * self.config.ATR_TP1_MULTIPLIER)
            tp2 = price - (atr * self.config.ATR_TP2_MULTIPLIER)
            risk = final_sl - price
            reward_1 = price - tp1

        risk_reward = reward_1 / risk if risk > 0 else 0

        return {
            'stop_loss_raw': final_sl,
            'tp1_raw': tp1,
            'tp2_raw': tp2,
            'risk_reward': round(risk_reward, 2)
        }

    def get_top_opportunities(
        self,
        results: List[Dict[str, Any]],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        انتخاب بهترین فرصتهای معاملاتی از بین نتایج

        معماری:
        1. فیلتر: حذف WAIT و RR<1.5 و Score<MIN_SCORE و بدون Data Quality
        2. Priority = Score * 2 + Confidence * 0.5 + RR * 10 + Exceptional Bonus + Quality Bonus
        3. مرتبسازی نزولی و انتخاب TOP N
        """
        # ================================================
        # STEP 1: FILTER
        # ================================================
        filtered_signals = []

        for r in results:
            if not r:
                continue

            # شرط ۱: Action نباید WAIT باشد
            if r.get('signal') == 'WAIT':
                logger.debug(f"⏭️ {r.get('symbol')}: Filtered (WAIT)")
                continue

            # شرط ۲: Score باید >= MIN_SCORE باشد
            score = r.get('score', 0)
            if score < self.MIN_SCORE:
                logger.debug(f"⏭️ {r.get('symbol')}: Filtered (Score={score:.1f} < {self.MIN_SCORE})")
                continue

            # شرط ۳: RR باید >= MIN_ACCEPTABLE_RR باشد
            rr = r.get('risk_reward')
            if rr is None or rr < self.MIN_ACCEPTABLE_RR:
                rr_display = f"{rr:.2f}" if rr is not None else "None"
                logger.debug(f"⏭️ {r.get('symbol')}: Filtered (RR={rr_display} < {self.MIN_ACCEPTABLE_RR})")
                continue

            # شرط ۴: Data Quality باید وجود داشته باشد
            if not r.get('data_quality'):
                logger.debug(f"⏭️ {r.get('symbol')}: Filtered (No Data Quality)")
                continue

            # شرط ۵: برای SELL، Confidence باید >= MIN_SELL_CONFIDENCE باشد
            if r.get('signal') == 'SELL':
                confidence = r.get('confidence', 0)
                if confidence < self.MIN_SELL_CONFIDENCE:
                    logger.debug(
                        f"⏭️ {r.get('symbol')}: Filtered (SELL Confidence={confidence:.1f}% < {self.MIN_SELL_CONFIDENCE}%)"
                    )
                    continue

            filtered_signals.append(r)

        if not filtered_signals:
            logger.info("📭 No signals passed the filter")
            return []

        # ================================================
        # STEP 2: PRIORITY CALCULATION
        # ================================================
        def calculate_priority(signal: Dict[str, Any]) -> float:
            score = signal.get('score', 50)
            confidence = signal.get('confidence', 50)
            rr = signal.get('risk_reward', 0)
            exceptional = signal.get('exceptional', False)
            dq_score = signal.get('data_quality', {}).get('quality_score', 0)

            # Score Weight (بیشترین اهمیت)
            priority = score * 2.0

            # Confidence Weight
            priority += confidence * 0.5

            # RR Weight (محدود به MAX_RR_FOR_PRIORITY)
            rr_score = min(rr, self.MAX_RR_FOR_PRIORITY) * 10
            priority += rr_score

            # Exceptional Bonus
            if exceptional:
                priority += 15

            # Data Quality Bonus
            if dq_score >= 90:
                priority += 5
            elif dq_score >= 80:
                priority += 2

            return priority

        # ================================================
        # STEP 3: SORT & SELECT TOP N
        # ================================================
        sorted_signals = sorted(
            filtered_signals,
            key=calculate_priority,
            reverse=True
        )

        top_signals = sorted_signals[:limit]

        # ================================================
        # STEP 4: LOG TOP SIGNALS
        # ================================================
        if top_signals:
            logger.info(f"📤 Top {len(top_signals)} signals after filter:")
            for i, s in enumerate(top_signals, 1):
                priority = calculate_priority(s)
                rr = s.get('risk_reward', 0)
                signal_rating = s.get('signal_rating', {}).get('stars', '⚪')
                logger.info(
                    f"  {i}. {signal_rating} {s.get('symbol')}: "
                    f"Score={s.get('score'):.1f} | "
                    f"Confidence={s.get('confidence'):.1f} | "
                    f"RR={rr:.2f} | "
                    f"Priority={priority:.2f} | "
                    f"{s.get('signal')}"
                )

        return top_signals
