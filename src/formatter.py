"""
Message Formatter Module
Responsible for formatting signal data and AI analysis into readable messages
"""

import logging
import html
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
import pytz

from config import Config

logger = logging.getLogger(__name__)


class MessageFormatter:
    """
    فرمت‌کننده پیام‌ها برای ارسال به Bale
    """
    
    def __init__(self, config=Config):
        self.config = config
        
        # =========================
        # تنظیمات زمان
        # =========================
        self.timezone = pytz.timezone('Asia/Tehran')
        
    def _get_current_time(self) -> str:
        """
        دریافت زمان فعلی با منطقه زمانی ایران
        """
        now = datetime.now(self.timezone)
        return now.strftime('%Y-%m-%d %H:%M')
    
    def _safe_text(self, text: Any) -> str:
        """
        ایمن‌سازی متن برای HTML (مقاوم در برابر انواع داده)
        
        Args:
            text: هر نوع داده (str, int, float, None, etc)
            
        Returns:
            رشته ایمن شده برای HTML
        """
        if text is None:
            return ""
        return html.escape(str(text))
    
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """
        تبدیل مقدار به float با مدیریت خطا
        
        Args:
            value: مقدار ورودی
            default: مقدار پیش‌فرض در صورت خطا
            
        Returns:
            float معتبر
        """
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    
    def _format_number_fa(self, num: float) -> str:
        """
        تبدیل عدد به فارسی با جداکننده هزارگان - بدون گرد کردن
        نمایش دقیق همان عدد دریافتی از نوبیتکس
        """
        if num is None:
            return '—'
        
        # تبدیل به رشته با دقت بالا و حذف صفرهای اضافی
        num_str = f"{num:.10f}".rstrip('0').rstrip('.')
        
        # جدا کردن قسمت صحیح و اعشار
        if '.' in num_str:
            integer_part, decimal_part = num_str.split('.')
        else:
            integer_part, decimal_part = num_str, ''
        
        # جداکننده هزارگان برای قسمت صحیح
        integer_parts = []
        for i, char in enumerate(reversed(integer_part)):
            if i > 0 and i % 3 == 0:
                integer_parts.append(',')
            integer_parts.append(char)
        integer_formatted = ''.join(reversed(integer_parts))
        
        # تبدیل به فارسی
        fa_digits = {'0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
                     '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'}
        
        integer_fa = ''.join(fa_digits.get(c, c) for c in integer_formatted)
        
        if decimal_part:
            decimal_fa = ''.join(fa_digits.get(c, c) for c in decimal_part)
            return f"{integer_fa}.{decimal_fa}"
        return integer_fa
    
    def _format_price(self, price: Union[float, int, str, None], unit: str = 'USDT') -> str:
        """
        فرمت کردن قیمت با واحد - بدون گرد کردن
        """
        price_float = self._safe_float(price, 0)
        return f"{self._format_number_fa(price_float)} {unit}"
    
    def _format_score_for_sell(self, score: float) -> float:
        """
        تبدیل امتیاز به قدرت فروش
        
        در SignalEngine، امتیاز 0-100 است که:
        - 0-50: منطقه فروش (هرچه پایین‌تر، فروش قوی‌تر)
        - 50: خنثی
        - 50-100: منطقه خرید (هرچه بالاتر، خرید قوی‌تر)
        
        برای فروش، قدرت فروش = 100 - score
        """
        safe_score = self._safe_float(score, 50)
        return max(0, min(100, 100 - safe_score))
    
    def _format_macd_status(self, macd: float, macd_signal: float) -> str:
        """
        فرمت کردن وضعیت MACD
        """
        macd = self._safe_float(macd)
        macd_signal = self._safe_float(macd_signal)
        
        if macd > macd_signal:
            return "صعودی"
        elif macd < macd_signal:
            return "نزولی"
        else:
            return "خنثی"
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """
        تبدیل انواع مختلف timestamp به datetime با timezone ایران
        
        Args:
            timestamp: datetime, str, یا هر نوع دیگر
            
        Returns:
            datetime با timezone ایران یا None در صورت خطا
        """
        if timestamp is None:
            return None
        
        # اگر datetime است
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=pytz.UTC)
            return timestamp.astimezone(self.timezone)
        
        # اگر رشته است
        if isinstance(timestamp, str):
            # فرمت‌های مختلف را امتحان کن
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%S%z',
                '%Y-%m-%dT%H:%M:%S.%f%z',
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.UTC)
                    return dt.astimezone(self.timezone)
                except ValueError:
                    continue
            
            logger.warning(f"⚠️ Could not parse timestamp string: {timestamp}")
            return None
        
        # سایر انواع
        try:
            dt = datetime.fromisoformat(str(timestamp))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt.astimezone(self.timezone)
        except Exception:
            logger.warning(f"⚠️ Could not parse timestamp: {timestamp}")
            return None
    
    def format_signal(
        self, 
        signal: Dict[str, Any],
        ai_result: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        فرمت کردن یک سیگنال کامل با AI
        
        Args:
            signal: دیکشنری سیگنال از SignalEngine
            ai_result: دیکشنری نتیجه AI از AIAnalyzer (اختیاری)
            
        Returns:
            متن فرمت شده برای ارسال
        """
        if not signal:
            return "⚠️ داده‌ای برای نمایش وجود ندارد"
        
        lines = []
        
        # =========================
        # هدر
        # =========================
        symbol = signal.get('symbol', 'Unknown')
        price = signal.get('price', 0)
        price_unit = signal.get('price_unit', 'USDT')
        signal_type = signal.get('signal', 'WAIT')
        strength = signal.get('strength', 'NEUTRAL')
        score = self._safe_float(signal.get('score', 50), 50)
        confidence = self._safe_float(signal.get('confidence', 50), 50)
        
        emoji_map = {
            'BUY': '🟢',
            'SELL': '🔴',
            'WAIT': '🟡'
        }
        emoji = emoji_map.get(signal_type, '⚪')
        
        lines.append(f"{emoji} <b>{self._safe_text(symbol)}</b>")
        lines.append(f"💰 قیمت: {self._format_price(price, price_unit)}")
        lines.append(f"📊 سیگنال: <b>{self._safe_text(signal_type)}</b>")
        lines.append(f"🔥 قدرت: {self._safe_text(strength)}")
        lines.append(f"🎯 اطمینان: {confidence:.1f}%")
        lines.append(f"📈 امتیاز: {score:.1f}/100")
        lines.append("")
        
        # =========================
        # اندیکاتورها
        # =========================
        rsi = self._safe_float(signal.get('rsi', 50), 50)
        macd = self._safe_float(signal.get('macd', 0))
        macd_signal = self._safe_float(signal.get('macd_signal', 0))
        adx = self._safe_float(signal.get('adx', 20), 20)
        volume_ratio = self._safe_float(signal.get('volume_ratio', 1.0), 1.0)
        
        macd_status = self._format_macd_status(macd, macd_signal)
        
        lines.append("📊 <b>اندیکاتورها:</b>")
        lines.append(f"• RSI: {rsi:.1f}")
        lines.append(f"• MACD: {macd_status}")
        lines.append(f"• ADX: {adx:.1f}")
        lines.append(f"• حجم: {volume_ratio:.2f}x")
        lines.append("")
        
        # =========================
        # مدیریت ریسک
        # =========================
        stop_loss = signal.get('stop_loss')
        tp1 = signal.get('tp1')
        tp2 = signal.get('tp2')
        risk_reward = self._safe_float(signal.get('risk_reward', 0))
        
        if stop_loss is not None and tp1 is not None:
            lines.append("🎯 <b>مدیریت ریسک:</b>")
            lines.append(f"🛑 حد ضرر: {self._format_price(stop_loss, price_unit)}")
            lines.append(f"🎯 هدف ۱: {self._format_price(tp1, price_unit)}")
            if tp2:
                lines.append(f"🎯 هدف ۲: {self._format_price(tp2, price_unit)}")
            lines.append(f"⚖️ R/R: {risk_reward:.2f}")
            lines.append("")
        
        # =========================
        # حمایت و مقاومت
        # =========================
        support = signal.get('support')
        resistance = signal.get('resistance')
        
        if support and resistance:
            lines.append("📐 <b>سطوح کلیدی:</b>")
            lines.append(f"🟢 حمایت: {self._format_price(support, price_unit)}")
            lines.append(f"🔴 مقاومت: {self._format_price(resistance, price_unit)}")
            lines.append("")
        
        # =========================
        # تحلیل AI
        # =========================
        if ai_result and ai_result.get('enabled', False):
            lines.append(self._format_ai_section(ai_result))
            lines.append("")
        
        # =========================
        # زمان
        # =========================
        timestamp = signal.get('timestamp')
        if timestamp:
            dt = self._parse_timestamp(timestamp)
            if dt:
                time_str = dt.strftime('%Y-%m-%d %H:%M')
            else:
                time_str = str(timestamp)
            lines.append(f"⏰ {time_str}")
        else:
            lines.append(f"⏰ {self._get_current_time()}")
        
        return "\n".join(lines)
    
    def _format_ai_section(self, ai_result: Dict[str, Any]) -> str:
        """
        فرمت کردن بخش AI
        """
        parts = []
        
        opinion = ai_result.get('opinion', 'NEUTRAL')
        confidence = self._safe_float(ai_result.get('confidence', 0))
        summary = ai_result.get('summary', '')
        risk = ai_result.get('risk_assessment', 'متوسط')
        recommendation = ai_result.get('recommendation', '')
        
        summary = self._safe_text(summary)
        recommendation = self._safe_text(recommendation)
        risk = self._safe_text(risk)
        
        opinion_emoji = {
            'BUY': '🟢',
            'SELL': '🔴',
            'WAIT': '🟡',
            'NEUTRAL': '⚪'
        }.get(opinion, '⚪')
        
        parts.append("━━━━━━━━━━━━━━━━━━━━")
        parts.append("🤖 <b>تحلیل هوش مصنوعی</b>")
        parts.append("━━━━━━━━━━━━━━━━━━━━")
        
        if summary:
            parts.append(f"📌 {summary}")
            parts.append("")
        
        positive = ai_result.get('positive_factors', [])
        if positive:
            parts.append("🟢 <b>عوامل مثبت:</b>")
            for factor in positive[:3]:
                parts.append(f"• {self._safe_text(factor)}")
            parts.append("")
        
        negative = ai_result.get('negative_factors', [])
        if negative:
            parts.append("🔴 <b>عوامل منفی/ریسک‌ها:</b>")
            for factor in negative[:3]:
                parts.append(f"• {self._safe_text(factor)}")
            parts.append("")
        
        risk_emoji = {
            'کم': '🟢',
            'متوسط': '🟡',
            'زیاد': '🔴'
        }.get(risk, '🟡')
        parts.append(f"⚠️ <b>سطح ریسک:</b> {risk_emoji} {risk}")
        
        if recommendation:
            parts.append(f"💡 <b>توصیه:</b> {recommendation}")
        
        parts.append(f"🎯 <b>نظر AI:</b> {opinion_emoji} {opinion}")
        parts.append(f"📊 <b>اطمینان AI:</b> {confidence:.0f}%")
        
        if ai_result.get('disagreement', False):
            parts.append("")
            parts.append("⚠️ <b>اختلاف نظر با ربات وجود دارد</b>")
        
        return "\n".join(parts)
    
    def format_summary(
        self, 
        signals: List[Dict[str, Any]],
        market_regime: Optional[str] = None,
        ai_summary: Optional[str] = None
    ) -> str:
        """
        فرمت کردن خلاصه کلی بازار
        
        Args:
            signals: لیست سیگنال‌ها
            market_regime: وضعیت کلی بازار (اختیاری)
            ai_summary: خلاصه تحلیل AI (اختیاری)
            
        Returns:
            متن فرمت شده برای ارسال
        """
        if not signals:
            return "📊 داده‌ای برای نمایش وجود ندارد"
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>خلاصه بازار</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        
        total = len(signals)
        buy_signals = [s for s in signals if s.get('signal') == 'BUY']
        sell_signals = [s for s in signals if s.get('signal') == 'SELL']
        wait_signals = [s for s in signals if s.get('signal') == 'WAIT']
        
        lines.append(f"🟢 خرید: {len(buy_signals)}")
        lines.append(f"🔴 فروش: {len(sell_signals)}")
        lines.append(f"🟡 صبر: {len(wait_signals)}")
        lines.append(f"📊 کل: {total}")
        lines.append("")
        
        if market_regime:
            regime_emoji = {
                'bullish': '🐂',
                'bearish': '🐻',
                'neutral': '⚖️',
                'صعودی': '🐂',
                'نزولی': '🐻',
                'خنثی': '⚖️'
            }.get(market_regime.lower(), '⚖️')
            
            regime_display = {
                'bullish': 'صعودی',
                'bearish': 'نزولی',
                'neutral': 'خنثی',
                'صعودی': 'صعودی',
                'نزولی': 'نزولی',
                'خنثی': 'خنثی'
            }.get(market_regime.lower(), market_regime)
            
            lines.append(f"📈 وضعیت بازار: {regime_emoji} {regime_display}")
            lines.append("")
        
        buy_signals_sorted = sorted(
            buy_signals,
            key=lambda x: self._safe_float(x.get('score', 0)),
            reverse=True
        )
        
        sell_signals_sorted = sorted(
            sell_signals,
            key=lambda x: self._format_score_for_sell(x.get('score', 50)),
            reverse=True
        )
        
        if buy_signals_sorted:
            lines.append("🔥 <b>بهترین فرصت‌های خرید:</b>")
            for s in buy_signals_sorted[:3]:
                score = self._safe_float(s.get('score', 0))
                lines.append(f"• {s.get('symbol')} — {score:.0f}%")
            lines.append("")
        
        if sell_signals_sorted:
            lines.append("⚠️ <b>بهترین فرصت‌های فروش:</b>")
            for s in sell_signals_sorted[:3]:
                sell_power = self._format_score_for_sell(s.get('score', 50))
                lines.append(f"• {s.get('symbol')} — {sell_power:.0f}% قدرت فروش")
            lines.append("")
        
        if ai_summary:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("🤖 <b>خلاصه AI</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(self._safe_text(ai_summary))
            lines.append("")
        
        lines.append(f"⏰ {self._get_current_time()}")
        
        return "\n".join(lines)
    
    def format_error(self, error_message: str) -> str:
        """
        فرمت کردن پیام خطا
        
        Args:
            error_message: متن خطا
            
        Returns:
            متن فرمت شده
        """
        return f"❌ <b>خطا</b>\n\n{self._safe_text(error_message)}"
    
    def format_info(self, info_message: str) -> str:
        """
        فرمت کردن پیام اطلاع‌رسانی
        
        Args:
            info_message: متن اطلاع‌رسانی
            
        Returns:
            متن فرمت شده
        """
        return f"ℹ️ <b>اطلاعیه</b>\n\n{self._safe_text(info_message)}"
    
    def format_warning(self, warning_message: str) -> str:
        """
        فرمت کردن پیام هشدار
        
        Args:
            warning_message: متن هشدار
            
        Returns:
            متن فرمت شده
        """
        return f"⚠️ <b>هشدار</b>\n\n{self._safe_text(warning_message)}"
