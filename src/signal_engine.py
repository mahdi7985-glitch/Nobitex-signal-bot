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
        self.MIN_ACCEPTABLE_RR = 1.5

    def analyze_symbol(
        self,
        df: pd.DataFrame,
        symbol: str,
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        try:
            indicators = self.indicators.get_latest_values(df)
            if not indicators:
                logger.warning(f"⚠️ No indicators for {symbol}")
                return None

            indicators['price'] = current_price

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

            signal = self._determine_signal(
                score_result['total'],
                indicators,
                df
            )

            if signal['action'] in ['BUY', 'SELL']:
                risk_levels = self._calculate_risk_levels(
                    indicators, df, signal['action']
                )

                logger.info(
                    f"🎯 {symbol}: "
                    f"Action={signal['action']} | "
                    f"Score={score_result['total']:.1f} | "
                    f"SL={risk_levels.get('stop_loss')} | "
                    f"TP1={risk_levels.get('tp1')} | "
                    f"TP2={risk_levels.get('tp2')} | "
                    f"RR={risk_levels.get('risk_reward')}"
                )

                if risk_levels.get('risk_reward', 0) < self.MIN_ACCEPTABLE_RR:
                    logger.info(
                        f"❌ {symbol}: Rejected by R/R | "
                        f"Score={score_result['total']:.1f} | "
                        f"RR={risk_levels.get('risk_reward', 0):.2f} | "
                        f"Required={self.MIN_ACCEPTABLE_RR}"
                    )
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

            sr_levels = self.indicators.get_support_resistance(df)

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

    # Trend
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

    # Momentum
    momentum_score = 0

    if trend_score > 0:
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
    elif trend_score < 0:
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

    # Volume
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

    # Volatility
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

    # Breakout
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

    # Support/Resistance
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

    # ADX
    adx_score = 0
    adx = indicators.get('adx') or 0
    di_plus = indicators.get('di_plus') or 0
    di_minus = indicators.get('di_minus') or 0
    trend_direction = 1 if trend_score > 0 else (-1 if trend_score < 0 else 0)

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
    exceptional = False
    exceptional_reason = None
    exceptional_direction = None

    adx = indicators.get('adx') or 0
    di_plus = indicators.get('di_plus') or 0
    di_minus = indicators.get('di_minus') or 0
    volume_ratio = indicators.get('volume_ratio') or 1.0
    macd_hist = indicators.get('macd_histogram') or 0
    macd_line = indicators.get('macd_line')
    macd_signal = indicators.get('macd_signal')
    price = indicators.get('price') or 0

    if (adx > 40 and
        di_plus > di_minus and
        macd_line is not None and macd_signal is not None and
        macd_line > macd_signal and
        volume_ratio > 1.5):
        exceptional = True
        exceptional_reason = "very_strong_uptrend_confirmed"
        exceptional_direction = "BUY"

    elif (adx > 40 and
          di_minus > di_plus and
          macd_line is not None and macd_signal is not None and
          macd_line < macd_signal and
          volume_ratio > 1.5):
        exceptional = True
        exceptional_reason = "very_strong_downtrend_confirmed"
        exceptional_direction = "SELL"

    else:
        sr_levels = self.indicators.get_support_resistance(df)
        resistance = sr_levels.get('resistance')
        support = sr_levels.get('support')

        if (resistance is not None and
            price > resistance and
            volume_ratio > 2.5 and
            macd_hist > 0 and
            di_plus > di_minus and
            adx > 25):
            exceptional = True
            exceptional_reason = "breakout_resistance_with_high_volume"
            exceptional_direction = "BUY"

        elif (support is not None and
              price < support and
              volume_ratio > 2.5 and
              macd_hist < 0 and
              di_minus > di_plus and
              adx > 25):
            exceptional = True
            exceptional_reason = "breakout_support_with_high_volume"
            exceptional_direction = "SELL"

    if exceptional and exceptional_direction:
        if exceptional_direction == "BUY" and score >= 55:
            return self._create_signal(
                score, "BUY", "EXCEPTIONAL", exceptional, exceptional_reason
            )
        elif exceptional_direction == "SELL" and score <= 45:
            return self._create_signal(
                score, "SELL", "EXCEPTIONAL", exceptional, exceptional_reason
            )
        else:
            logger.debug(f"Exceptional {exceptional_direction} ignored due to score {score}")

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
    if action == "BUY":
        confidence = min(95, 50 + (score - 50) * 0.9)
    else:
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

    sl_multiplier = self.config.ATR_SL_MULTIPLIER
    if indicators.get('bb_width', 0) > 0.15:
        sl_multiplier = self.config.ATR_SL_MULTIPLIER_HIGH_VOLATILITY

    if action == 'BUY':
        final_sl = price - (atr * sl_multiplier)
    else:
        final_sl = price + (atr * sl_multiplier)

    # ================================================
    # ❌ S/R Adjustment کاملاً حذف شد
    # ================================================

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
    # محاسبه اهداف
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
        'stop_loss': round(final_sl, 2),
        'tp1': round(tp1, 2),
        'tp2': round(tp2, 2),
        'risk_reward': round(risk_reward, 2)
    }

def get_top_opportunities(
    self,
    results: List[Dict[str, Any]],
    limit: int = 5
) -> List[Dict[str, Any]]:
    active_signals = [r for r in results if r and r['signal'] != 'WAIT']

    def calculate_priority(signal: Dict[str, Any]) -> float:
        score = signal.get('score', 50)
        confidence = signal.get('confidence', 50)
        risk_reward = signal.get('risk_reward') or 0
        signal_type = signal.get('signal', 'WAIT')

        if signal_type == 'BUY':
            normalized_score = score
        else:
            normalized_score = 100 - score

        strength_boost = {
            'WEAK': 0,
            'NORMAL': 5,
            'STRONG': 10,
            'VERY_STRONG': 15,
            'EXCEPTIONAL': 20
        }.get(signal.get('strength'), 0)

        rr_score = min(risk_reward, 5) * 5

        priority = (
            (normalized_score * 0.35) +
            (confidence * 0.25) +
            (rr_score) +
            (strength_boost)
        )

        return priority

    sorted_signals = sorted(
        active_signals,
        key=calculate_priority,
        reverse=True
    )

    return sorted_signals[:limit]

