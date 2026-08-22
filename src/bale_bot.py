"""
Bale Messenger Module
Responsible for sending signals and messages to Bale messenger
"""

import requests
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from config import Config

logger = logging.getLogger(__name__)


class BaleBot:
    """
    ارسال پیام به ربات بله
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.token = config.BALE_BOT_TOKEN
        self.chat_id = config.BALE_CHAT_ID
        self.max_retries = 3
        self.base_url = "https://tapi.bale.ai"
        
        # =========================
        # نام روزها به فارسی
        # =========================
        self.DAYS_FA = {
            0: 'دوشنبه',
            1: 'سه‌شنبه',
            2: 'چهارشنبه',
            3: 'پنجشنبه',
            4: 'جمعه',
            5: 'شنبه',
            6: 'یکشنبه'
        }
        
        # =========================
        # نام ماه‌ها به فارسی
        # =========================
        self.MONTHS_FA = [
            'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
            'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
        ]
        
        # =========================
        # نگاشت سیگنال به فارسی
        # =========================
        self.SIGNAL_MAP = {
            'BUY': {'fa': 'خرید', 'emoji': '🟢'},
            'SELL': {'fa': 'فروش', 'emoji': '🔴'},
            'WAIT': {'fa': 'انتظار', 'emoji': '⚪'},
            'STRONG_BUY': {'fa': 'خرید قوی', 'emoji': '🟢'},
            'STRONG_SELL': {'fa': 'فروش قوی', 'emoji': '🔴'},
            'EXCEPTIONAL_BUY': {'fa': '🔥 خرید استثنایی', 'emoji': '🔥'},
            'EXCEPTIONAL_SELL': {'fa': '🔥 فروش استثنایی', 'emoji': '🔥'},
        }
        
    # ============================================================
    # زمان و تاریخ
    # ============================================================
    
    def _utc_to_tehran(self, dt: Optional[datetime] = None) -> datetime:
        """تبدیل UTC به Asia/Tehran (UTC+3:30)"""
        if dt is None:
            dt = datetime.now(timezone.utc)
        return dt + timedelta(hours=3, minutes=30)
    
    def _to_jalali(self, dt: datetime) -> tuple:
        """تبدیل تاریخ میلادی به شمسی (تقریبی)"""
        year = dt.year - 621
        month = dt.month
        day = dt.day
        
        if month > 3:
            year += 1
            month -= 3
        else:
            month += 9
        
        if month > 6:
            day_offset = 31
        else:
            day_offset = 30
        
        if day > day_offset:
            day -= day_offset
            month += 1
        
        if month > 12:
            month -= 12
            year += 1
        
        return year, month, day
    
    def _get_persian_datetime(self) -> str:
        """دریافت تاریخ و زمان به فارسی"""
        tehran = self._utc_to_tehran()
        year, month, day = self._to_jalali(tehran)
        weekday = self.DAYS_FA.get(tehran.weekday(), '')
        
        return f"{weekday} {day} {self.MONTHS_FA[month-1]} {year} - ساعت {tehran.strftime('%H:%M')}"
    
    def _format_number_fa(self, num: float) -> str:
        """
        تبدیل عدد به فارسی با جداکننده هزارگان و تشخیص خودکار تعداد ارقام اعشار
        
        - قیمت‌های بالای ۱۰۰۰: ۲ رقم اعشار
        - قیمت‌های بالای ۱: ۴ رقم اعشار
        - قیمت‌های بالای ۰.۰۱: ۶ رقم اعشار
        - قیمت‌های بالای ۰.۰۰۰۱: ۸ رقم اعشار
        - بقیه: ۱۰ رقم اعشار
        """
        if num is None:
            return '—'
        
        # =========================
        # تشخیص تعداد ارقام اعشار بر اساس قیمت
        # =========================
        if num >= 1000:
            decimals = 2
        elif num >= 1:
            decimals = 4
        elif num >= 0.01:
            decimals = 6
        elif num >= 0.0001:
            decimals = 8
        else:
            decimals = 10
        
        # فرمت با اعشار مشخص
        parts = f"{num:,.{decimals}f}".split('.')
        integer_part = parts[0]
        decimal_part = parts[1] if len(parts) > 1 else ''
        
        # حذف صفرهای بی‌مورد از انتهای اعشار
        decimal_part = decimal_part.rstrip('0')
        if not decimal_part:
            decimal_part = '0'
        
        # تبدیل به فارسی
        fa_digits = {'0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
                     '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'}
        
        integer_fa = ''.join(fa_digits.get(c, c) for c in integer_part)
        decimal_fa = ''.join(fa_digits.get(c, c) for c in decimal_part)
        
        if decimal_part == '0':
            return integer_fa
        return f"{integer_fa}.{decimal_fa}"
    
    # ============================================================
    # ارسال پیام
    # ============================================================
    
    def send_message(self, text: str, parse_mode: str = "HTML", max_retries: int = 3) -> bool:
        """
        ارسال پیام به بله با قابلیت تلاش مجدد
        
        Args:
            text: متن پیام
            parse_mode: حالت پارس (HTML یا Markdown)
            max_retries: تعداد تلاش مجدد
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        if self.config.TEST_MODE:
            logger.info(f"[TEST MODE] Would send: {text[:100]}...")
            return True
            
        if not self.token or not self.chat_id:
            logger.warning("⚠️ توکن یا آیدی بله تنظیم نشده")
            return False
        
        url = f"{self.base_url}/bot{self.token}/sendMessage"
            
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url,
                    json={
                        'chat_id': self.chat_id,
                        'text': text,
                        'parse_mode': parse_mode
                    },
                    timeout=self.config.REQUEST_TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        logger.info("✅ پیام به بله ارسال شد")
                        return True
                    else:
                        logger.error(f"❌ خطای API بله: {data}")
                        return False
                elif response.status_code == 404:
                    logger.error(f"❌ آدرس API اشتباه است: {url}")
                    return False
                elif response.status_code == 503:
                    logger.warning(f"⚠️ خطای ۵۰۳، تلاش {attempt+1}/{max_retries}")
                    time.sleep(5)
                else:
                    logger.error(f"❌ HTTP error {response.status_code}: {response.text}")
                    if attempt < max_retries - 1:
                        time.sleep(3)
                    
            except requests.exceptions.Timeout:
                logger.error(f"❌ Timeout (تلاش {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(3)
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ خطای شبکه: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
            except Exception as e:
                logger.error(f"❌ خطای غیرمنتظره: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
        
        logger.error("❌ ارسال به بله پس از تلاش‌های مجدد ناموفق بود.")
        return False
    
    # ============================================================
    # فرمت‌کننده پیام سیگنال (با ⭐ تا 🔥)
    # ============================================================
    
    def _format_signal_message(self, signal: Dict[str, Any]) -> str:
        """
        فرمت کردن پیام سیگنال با ساختار جدید
        """
        symbol = signal.get('symbol', 'Unknown')
        price = signal.get('price', 0)
        signal_type = signal.get('signal', 'WAIT')
        strength = signal.get('strength', 'NEUTRAL')
        score = signal.get('score', 50)
        confidence = signal.get('confidence', 50)
        signal_importance = signal.get('signal_importance', '⚪')
        risk_reward = signal.get('risk_reward', 0)
        persian_date = self._get_persian_datetime()
        
        # =========================
        # نام سیگنال به فارسی
        # =========================
        signal_fa = self.SIGNAL_MAP.get(signal_type, {}).get('fa', 'نامشخص')
        signal_emoji = self.SIGNAL_MAP.get(signal_type, {}).get('emoji', '⚪')
        
        # =========================
        # ساخت پیام با HTML
        # =========================
        lines = []
        
        # عنوان با Importance
        lines.append(f"<b>{signal_importance} سیگنال {symbol}</b>")
        lines.append("")
        
        # اقدام
        lines.append(f"<b>اقدام:</b> {signal_emoji} {signal_fa}")
        
        # قیمت
        lines.append(f"<b>💰 قیمت:</b> {self._format_number_fa(price)} USDT")
        
        # امتیاز و اطمینان
        lines.append(f"<b>📈 امتیاز:</b> {score:.1f}/۱۰۰")
        lines.append(f"<b>🎯 اطمینان:</b> {confidence:.1f}%")
        lines.append(f"<b>قدرت سیگنال:</b> {strength}")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # =========================
        # مدیریت ریسک
        # =========================
        stop_loss = signal.get('stop_loss')
        tp1 = signal.get('tp1')
        tp2 = signal.get('tp2')
        
        if stop_loss:
            lines.append("<b>🎯 مدیریت ریسک:</b>")
            lines.append(f"🛑 <b>حد ضرر:</b> {self._format_number_fa(stop_loss)}")
            if tp1:
                lines.append(f"🎯 <b>هدف ۱:</b> {self._format_number_fa(tp1)}")
            if tp2:
                lines.append(f"🎯 <b>هدف ۲:</b> {self._format_number_fa(tp2)}")
            if risk_reward:
                lines.append(f"⚖️ <b>نسبت ریسک/بازده:</b> {risk_reward:.2f}")
            lines.append("")
        
        # =========================
        # اندیکاتورها
        # =========================
        rsi = signal.get('rsi', 50)
        macd = signal.get('macd', 0)
        macd_signal = signal.get('macd_signal', 0)
        adx = signal.get('adx', 20)
        volume_ratio = signal.get('volume_ratio', 1.0)
        
        macd_status = "صعودی" if macd > macd_signal else "نزولی"
        
        lines.append("<b>📊 اندیکاتورها:</b>")
        lines.append(f"🔸 RSI: {rsi:.1f}")
        lines.append(f"🔸 MACD: {macd_status}")
        lines.append(f"🔸 ADX: {adx:.1f}")
        lines.append(f"🔸 حجم: {volume_ratio:.2f}x")
        lines.append("")
        
        # =========================
        # حمایت و مقاومت
        # =========================
        support = signal.get('support')
        resistance = signal.get('resistance')
        
        if support or resistance:
            lines.append("<b>📐 سطوح کلیدی:</b>")
            if support:
                lines.append(f"🟢 <b>حمایت:</b> {self._format_number_fa(support)}")
            if resistance:
                lines.append(f"🔴 <b>مقاومت:</b> {self._format_number_fa(resistance)}")
            lines.append("")
        
        # =========================
        # زمان
        # =========================
        lines.append("---")
        lines.append(f"<i>🕐 {persian_date}</i>")
        
        return "\n".join(lines)
    
    def send_signal(self, signal: Dict[str, Any]) -> bool:
        """
        ارسال سیگنال معاملاتی به بله
        """
        if not signal:
            return False
        
        # اگر سیگنال WAIT است و تنظیمات ارسال WAIT غیرفعال است
        if signal.get('signal') == 'WAIT' and not self.config.SEND_WAIT_SIGNALS:
            return True
            
        message = self._format_signal_message(signal)
        return self.send_message(message)
    
    # ============================================================
    # خلاصه بازار
    # ============================================================
    
    def _format_summary_message(self, signals: List[Dict[str, Any]], market_regime: str = 'neutral') -> str:
        """
        فرمت کردن پیام خلاصه بازار
        """
        persian_date = self._get_persian_datetime()
        
        total = len(signals)
        buy_signals = [s for s in signals if s.get('signal') == 'BUY']
        sell_signals = [s for s in signals if s.get('signal') == 'SELL']
        wait_signals = [s for s in signals if s.get('signal') == 'WAIT']
        
        # وضعیت بازار
        regime_map = {
            'bullish': ('📈', 'صعودی', '🟢'),
            'bearish': ('📉', 'نزولی', '🔴'),
            'neutral': ('📊', 'خنثی', '🟡')
        }
        regime_emoji, regime_fa, regime_color = regime_map.get(market_regime, ('📊', 'نامشخص', '🟡'))
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            f"<b>📊 خلاصه بازار</b>",
            f"<i>{persian_date}</i>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"<b>وضعیت کلی:</b> {regime_emoji} {regime_fa}",
            "",
            f"🟢 <b>خرید:</b> {len(buy_signals)}",
            f"🔴 <b>فروش:</b> {len(sell_signals)}",
            f"⚪ <b>انتظار:</b> {len(wait_signals)}",
            f"📊 <b>کل:</b> {total}",
            "",
        ]
        
        # بهترین خرید
        if buy_signals:
            best_buy = max(buy_signals, key=lambda x: x.get('score', 0))
            importance = best_buy.get('signal_importance', '⭐')
            lines.append(f"🔥 <b>بهترین خرید:</b> {importance} {best_buy.get('symbol')} ({best_buy.get('score', 0):.1f}%)")
        
        # بهترین فروش
        if sell_signals:
            best_sell = max(sell_signals, key=lambda x: x.get('score', 0))
            importance = best_sell.get('signal_importance', '⭐')
            lines.append(f"⚠️ <b>بهترین فروش:</b> {importance} {best_sell.get('symbol')} ({best_sell.get('score', 0):.1f}%)")
        
        lines.append("")
        lines.append(f"<i>🕐 {persian_date}</i>")
        
        return "\n".join(lines)
    
    def send_summary(self, signals: List[Dict[str, Any]], market_regime: str = 'neutral') -> bool:
        """
        ارسال خلاصه بازار
        """
        if not signals:
            return False
            
        message = self._format_summary_message(signals, market_regime)
        return self.send_message(message)
    
    # ============================================================
    # گزارش عملکرد
    # ============================================================
    
    def _format_performance_message(self, performance: Dict[str, Any]) -> str:
        """
        فرمت کردن پیام گزارش عملکرد
        """
        persian_date = self._get_persian_datetime()
        
        total = performance.get('total', 0)
        wins = performance.get('wins', 0)
        losses = performance.get('losses', 0)
        open_signals = performance.get('open', 0)
        win_rate = performance.get('win_rate', 0)
        avg_r = performance.get('avg_r', 0)
        profit_factor = performance.get('profit_factor', 0)
        max_drawdown = performance.get('max_drawdown', 0)
        failure_reasons = performance.get('failure_reasons', {})
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            f"<b>📊 گزارش عملکرد</b>",
            f"<i>{persian_date}</i>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"📊 <b>کل سیگنال‌ها:</b> {total}",
            f"🟢 <b>برد:</b> {wins}",
            f"🔴 <b>باخت:</b> {losses}",
            f"⏳ <b>باز:</b> {open_signals}",
            "",
            f"🎯 <b>نرخ موفقیت:</b> {win_rate:.1f}%",
            f"📈 <b>میانگین R:</b> {avg_r:.2f}",
            f"💰 <b>ضریب سود:</b> {profit_factor:.2f}",
            f"📉 <b>حداکثر افت:</b> {max_drawdown:.1f}%",
            "",
        ]
        
        # دلایل شکست
        if failure_reasons:
            lines.append("<b>🔍 تحلیل شکست‌ها:</b>")
            for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)[:3]:
                lines.append(f"  • {reason}: {count} بار")
            lines.append("")
        
        lines.append(f"<i>🕐 {persian_date}</i>")
        
        return "\n".join(lines)
    
    def send_performance(self, performance: Dict[str, Any]) -> bool:
        """
        ارسال گزارش عملکرد
        """
        if not performance:
            return False
            
        message = self._format_performance_message(performance)
        return self.send_message(message)
    
    # ============================================================
    # ارسال چند سیگنال
    # ============================================================
    
    def send_multiple_signals(self, signals: List[Dict[str, Any]], limit: int = 5) -> bool:
        """
        ارسال چند سیگنال برتر
        """
        if not signals:
            return False
            
        top_signals = sorted(
            [s for s in signals if s.get('signal') != 'WAIT'],
            key=lambda x: x.get('score', 0),
            reverse=True
        )[:limit]
        
        if not top_signals:
            return False
            
        success = True
        for signal in top_signals:
            if not self.send_signal(signal):
                success = False
                
        return success
    
    # ============================================================
    # پیام‌های خطا
    # ============================================================
    
    def send_error(self, error_message: str) -> bool:
        """
        ارسال پیام خطا
        """
        message = f"❌ <b>خطا</b>\n\n{error_message}"
        return self.send_message(message)

    # ============================================================
    # پیام‌های باز و بسته شدن معامله (اضافه شده)
    # ============================================================

    def _format_indicator_analysis(self, indicator_scores: Dict[str, float], outcome: str) -> str:
        """
        فرمت کردن تحلیل اندیکاتورها با پیشنهاد بهبود
        
        Args:
            indicator_scores: دیکشنری امتیاز اندیکاتورها {'trend': 20, 'momentum': 18, ...}
            outcome: 'WIN' یا 'LOSS'
        
        Returns:
            متن تحلیل فرمت شده
        """
        if not indicator_scores:
            return "📊 اطلاعات اندیکاتورها در دسترس نیست."
        
        lines = []
        lines.append("<b>📊 تحلیل اندیکاتورها:</b>")
        lines.append("")
        
        # تعیین آستانه‌های بهینه برای هر اندیکاتور
        optimal_thresholds = {
            'trend': {'min': 15, 'optimal': 20, 'name': 'روند (Trend)'},
            'momentum': {'min': 12, 'optimal': 18, 'name': 'مومنتوم (Momentum)'},
            'volume': {'min': 8, 'optimal': 15, 'name': 'حجم (Volume)'},
            'volatility': {'min': -5, 'optimal': 5, 'name': 'نوسان (Volatility)'},
            'breakout': {'min': 5, 'optimal': 10, 'name': 'شکست (Breakout)'},
            'support_resistance': {'min': 5, 'optimal': 10, 'name': 'حمایت/مقاومت (S/R)'},
            'adx': {'min': 2, 'optimal': 8, 'name': 'قدرت روند (ADX)'}
        }
        
        emoji_map = {
            'trend': '📈',
            'momentum': '⚡',
            'volume': '📊',
            'volatility': '📉',
            'breakout': '🚀',
            'support_resistance': '🛡️',
            'adx': '📏'
        }
        
        for key, value in indicator_scores.items():
            if key not in optimal_thresholds:
                continue
            
            info = optimal_thresholds[key]
            emoji = emoji_map.get(key, '🔹')
            status = "✅" if value >= info['min'] else "⚠️"
            
                        # تعیین وضعیت
            if outcome == 'WIN':
                if value >= info['optimal']:
                    status_text = "عالی ✅"
                elif value >= info['min']:
                    status_text = "خوب ✔️"
                else:
                    status_text = "ضعیف ⚠️"
            else:  # LOSS
                if value < info['min']:
                    status_text = "ضعیف ❌"
                elif value < info['optimal']:
                    status_text = "متوسط ⚠️"
                else:
                    status_text = "خوب ولی کافی نبود 🤔"
            
            # پیشنهاد بهبود
            if value < info['min']:
                suggestion = f"➜ اگر {info['optimal']} بود، نتیجه بهتری داشت"
            elif value < info['optimal']:
                suggestion = f"➜ اگر به {info['optimal']} می‌رسید، وضعیت بهینه‌تر می‌شد"
            else:
                suggestion = "➜ در وضعیت مطلوب ✅"
            
            lines.append(
                f"{emoji} <b>{info['name']}:</b> {value:+.1f} ({status_text})"
            )
            lines.append(f"   {suggestion}")
            lines.append("")
        
        return "\n".join(lines)

    def send_trade_open(
        self,
        symbol: str,
        signal_type: str,  # 'BUY' یا 'SELL'
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: Optional[float],
        risk_reward: float,
        position_size: float,
        remaining_balance: float,
        score: float,
        timeframe: str = "15m",
        confidence: float = 0.0,
        indicator_scores: Optional[Dict[str, float]] = None,
        position_value: Optional[float] = None  # <-- پارامتر جدید
    ) -> bool:
        """
        ارسال پیام باز شدن معامله (خرید/فروش)
        
        Args:
            symbol: نماد
            signal_type: 'BUY' یا 'SELL'
            entry_price: قیمت ورود
            stop_loss: حد ضرر
            take_profit_1: هدف اول
            take_profit_2: هدف دوم (اختیاری)
            risk_reward: نسبت ریسک به بازده
            position_size: درصد سرمایه (مثلاً 0.25)
            remaining_balance: موجودی باقی‌مانده
            score: امتیاز سیگنال
            timeframe: تایم‌فریم
            confidence: درصد اطمینان
            indicator_scores: دیکشنری امتیاز اندیکاتورها
            position_value: مقدار واقعی سرمایه معامله (اختیاری)
        """
        persian_date = self._get_persian_datetime()
        
        # نام و ایموجی
        signal_fa = self.SIGNAL_MAP.get(signal_type, {}).get('fa', 'نامشخص')
        signal_emoji = self.SIGNAL_MAP.get(signal_type, {}).get('emoji', '⚪')
        action_text = "باز شد" if signal_type == 'BUY' else "باز شد"
        
        position_percent = position_size * 100
        # اگر position_value ارسال نشده، از مقدار پیش‌فرض استفاده کن
        if position_value is None:
            position_value = 530 * position_size
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            f"{signal_emoji} <b>معامله {action_text}!</b> ({signal_fa})",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"📊 <b>{symbol}</b> (USDT)",
            f"⏰ <b>زمان:</b> {persian_date}",
            f"📈 <b>تایم‌فریم:</b> {timeframe}",
            "",
            f"💰 <b>قیمت ورود:</b> {self._format_number_fa(entry_price)} USDT",
            f"🛑 <b>حد ضرر:</b> {self._format_number_fa(stop_loss)} USDT",
            f"🎯 <b>هدف ۱:</b> {self._format_number_fa(take_profit_1)} USDT",
        ]
        
        if take_profit_2:
            lines.append(f"🎯 <b>هدف ۲:</b> {self._format_number_fa(take_profit_2)} USDT")
        
        lines.append(f"⚖️ <b>نسبت ریسک/بازده:</b> {risk_reward:.2f}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("<b>💰 جزئیات سرمایه:</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💵 <b>سرمایه‌ی معامله:</b> {position_value:.2f} USDT ({position_percent:.0f}%)")
        lines.append(f"💰 <b>موجودی باقی‌مانده:</b> {self._format_number_fa(remaining_balance)} USDT")
        lines.append("")
        
        # نمایش اندیکاتورهای کلیدی
        if indicator_scores:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("<b>📊 اندیکاتورهای کلیدی:</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"📈 <b>امتیاز کلی:</b> {score:.1f}/۱۰۰")
            lines.append("")
            
            # نمایش ۳-۴ اندیکاتور برتر
            sorted_scores = sorted(indicator_scores.items(), key=lambda x: x[1], reverse=True)[:4]
            emoji_map = {
                'trend': '📈',
                'momentum': '⚡',
                'volume': '📊',
                'breakout': '🚀',
                'support_resistance': '🛡️',
                'adx': '📏',
                'volatility': '📉'
            }
            name_map = {
                'trend': 'روند',
                'momentum': 'مومنتوم',
                'volume': 'حجم',
                'breakout': 'شکست',
                'support_resistance': 'حمایت/مقاومت',
                'adx': 'قدرت روند',
                'volatility': 'نوسان'
            }
            
            for key, value in sorted_scores:
                emoji = emoji_map.get(key, '🔹')
                name = name_map.get(key, key)
                lines.append(f"{emoji} <b>{name}:</b> {value:+.1f}")
            
            lines.append("")
        
        lines.append("---")
        lines.append(f"<i>🕐 {persian_date}</i>")
        
        return self.send_message("\n".join(lines))

    def send_trade_close(
        self,
        symbol: str,
        signal_type: str,  # 'BUY' یا 'SELL'
        entry_price: float,
        exit_price: float,
        entry_time: str,
        exit_time: str,
        hold_time: str,
        timeframe: str,
        gross_profit: float,
        net_profit: float,
        net_profit_percent: float,
        total_fee: float,
        buy_fee: float,
        sell_fee: float,
        exit_reason: str,
        current_balance: float,
        total_trades: int,
        win_rate: float,
        score: float,
        indicator_scores: Dict[str, float],
        outcome: str,  # 'WIN' یا 'LOSS'
        position_value: Optional[float] = None  # <-- پارامتر جدید
    ) -> bool:
        """
        ارسال پیام بسته شدن معامله با تحلیل اندیکاتورها
        
        Args:
            symbol: نماد
            signal_type: 'BUY' یا 'SELL'
            entry_price: قیمت ورود
            exit_price: قیمت خروج
            entry_time: زمان ورود
            exit_time: زمان خروج
            hold_time: مدت باز بودن
            timeframe: تایم‌فریم
            gross_profit: سود ناخالص
            net_profit: سود خالص
            net_profit_percent: سود درصدی خالص
            total_fee: کارمزد کل
            buy_fee: کارمزد خرید
            sell_fee: کارمزد فروش
            exit_reason: دلیل خروج ('stop_loss', 'take_profit_1', 'take_profit_2')
            current_balance: موجودی فعلی
            total_trades: تعداد کل معاملات بسته
            win_rate: نرخ موفقیت
            score: امتیاز سیگنال
            indicator_scores: دیکشنری امتیاز اندیکاتورها
            outcome: 'WIN' یا 'LOSS'
            position_value: مقدار واقعی سرمایه معامله (اختیاری)
        """
        persian_date = self._get_persian_datetime()
        
        # ایموجی و نتیجه
        is_win = net_profit > 0
        emoji = "✅" if is_win else "❌"
        result_text = "سود" if is_win else "ضرر"
        sign = "+" if is_win else ""
        
        # دلیل خروج به فارسی
        exit_reason_map = {
            'stop_loss': 'حد ضرر',
            'take_profit_1': 'هدف ۱',
            'take_profit_2': 'هدف ۲',
            'manual': 'دستی'
        }
        exit_reason_fa = exit_reason_map.get(exit_reason, exit_reason)
        
        signal_fa = self.SIGNAL_MAP.get(signal_type, {}).get('fa', 'نامشخص')
        signal_emoji = self.SIGNAL_MAP.get(signal_type, {}).get('emoji', '⚪')
        
        # تغییر قیمت
        if signal_type == 'BUY':
            price_change = ((exit_price - entry_price) / entry_price) * 100
        else:  # SELL
            price_change = ((entry_price - exit_price) / entry_price) * 100
        
        # اگر position_value ارسال نشده، از مقدار پیش‌فرض استفاده کن
        if position_value is None:
            position_value = 132.50  # مقدار ثابت قبلی برای سازگاری
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            f"{emoji} <b>معامله بسته شد!</b> ({signal_fa})",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"📊 <b>{symbol}</b> (USDT)",
            f"⏰ <b>زمان ورود:</b> {entry_time}",
            f"⏰ <b>زمان خروج:</b> {exit_time}",
            f"⏱️ <b>مدت باز بودن:</b> {hold_time}",
            f"📈 <b>تایم‌فریم:</b> {timeframe}",
            "",
            f"💰 <b>قیمت ورود:</b> {self._format_number_fa(entry_price)} USDT",
            f"💰 <b>قیمت خروج:</b> {self._format_number_fa(exit_price)} USDT",
            f"📈 <b>تغییر قیمت:</b> {sign}{price_change:.2f}%",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "<b>💰 جزئیات مالی:</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💵 <b>سرمایه‌ی معامله:</b> {position_value:.2f} USDT",
            f"💵 <b>سرمایه‌ی نهایی:</b> {self._format_number_fa(abs(net_profit))} USDT",
            "",
            f"📊 <b>{result_text} خالص:</b> {sign}{net_profit:.2f} USDT {emoji}",
            f"📊 <b>{result_text} درصدی:</b> {sign}{net_profit_percent:.2f}%",
            "",
            f"💳 <b>کارمزد خرید:</b> -{self._format_number_fa(buy_fee)} USDT",
            f"💳 <b>کارمزد فروش:</b> -{self._format_number_fa(sell_fee)} USDT",
            f"💳 <b>کارمزد کل:</b> -{self._format_number_fa(total_fee)} USDT",
            "",
            f"💰 <b>{result_text} ناخالص:</b> {sign}{(abs(net_profit) + total_fee):.2f} USDT",
            f"📉 <b>دلیل خروج:</b> {exit_reason_fa}",
            "",
        ]
        
        # تحلیل اندیکاتورها
        if indicator_scores:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(self._format_indicator_analysis(indicator_scores, outcome))
            lines.append("")
        
        # وضعیت کلی
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("<b>📊 وضعیت کلی:</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 <b>موجودی کل:</b> {self._format_number_fa(current_balance)} USDT")
        lines.append(f"📈 <b>تغییر کل:</b> {sign}{(current_balance - 530):.2f} USDT ({((current_balance / 530) - 1) * 100:.2f}%)")
        lines.append(f"🔄 <b>معاملات بسته:</b> {total_trades}")
        lines.append(f"📊 <b>نرخ موفقیت:</b> {win_rate:.1f}%")
        lines.append("")
        lines.append("---")
        lines.append(f"<i>🕐 {persian_date}</i>")
        
        return self.send_message("\n".join(lines))

    def send_performance_report(
        self,
        report_type: str,  # 'daily' یا 'weekly'
        start_date: str,
        end_date: str,
        initial_balance: float,
        current_balance: float,
        total_trades: int,
        wins: int,
        losses: int,
        win_rate: float,
        total_profit: float,
        total_loss: float,
        profit_factor: float,
        best_trade: Dict[str, Any],
        worst_trade: Dict[str, Any],
        indicator_performance: Dict[str, Dict[str, Any]]
    ) -> bool:
        """
        ارسال گزارش عملکرد روزانه/هفتگی
        
        Args:
            report_type: 'daily' یا 'weekly'
            start_date: تاریخ شروع
            end_date: تاریخ پایان
            initial_balance: سرمایه اولیه
            current_balance: سرمایه فعلی
            total_trades: کل معاملات
            wins: تعداد برد
            losses: تعداد باخت
            win_rate: نرخ موفقیت
            total_profit: کل سود
            total_loss: کل ضرر
            profit_factor: ضریب سود
            best_trade: بهترین معامله
            worst_trade: بدترین معامله
            indicator_performance: عملکرد اندیکاتورها
        """
        persian_date = self._get_persian_datetime()
        
        report_name = "گزارش روزانه" if report_type == 'daily' else "گزارش هفتگی"
        total_change = current_balance - initial_balance
        sign = "+" if total_change > 0 else ""
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            f"<b>📊 {report_name}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📅 <b>دوره:</b> {start_date} تا {end_date}",
            "",
            f"💰 <b>سرمایه اولیه:</b> {self._format_number_fa(initial_balance)} USDT",
            f"💰 <b>سرمایه فعلی:</b> {self._format_number_fa(current_balance)} USDT",
            f"📈 <b>تغییر کل:</b> {sign}{total_change:.2f} USDT ({((current_balance / initial_balance) - 1) * 100:.2f}%)",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "<b>📊 آمار معاملات:</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🔄 <b>کل معاملات:</b> {total_trades}",
            f"✅ <b>موفق:</b> {wins} ({win_rate:.1f}%)",
            f"❌ <b>ناموفق:</b> {losses} ({100 - win_rate:.1f}%)",
            f"💰 <b>کل سود:</b> {total_profit:.2f} USDT",
            f"💰 <b>کل ضرر:</b> {total_loss:.2f} USDT",
            f"📊 <b>ضریب سود:</b> {profit_factor:.2f}",
            "",
        ]
        
        # عملکرد اندیکاتورها
        if indicator_performance:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("<b>📊 عملکرد اندیکاتورها:</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            
            sorted_indicators = sorted(
                indicator_performance.items(),
                key=lambda x: x[1].get('win_rate', 0),
                reverse=True
            )
            
            medals = ['🥇', '🥈', '🥉']
            for i, (indicator, data) in enumerate(sorted_indicators[:5]):
                medal = medals[i] if i < 3 else '🔹'
                win_rate_ind = data.get('win_rate', 0)
                lines.append(f"{medal} <b>{indicator}:</b> {win_rate_ind:.1f}% موفقیت")
            
            # پیشنهاد بهبود
            if sorted_indicators:
                best = sorted_indicators[0]
                worst = sorted_indicators[-1]
                lines.append("")
                lines.append(f"💡 <b>نکته:</b> اندیکاتور <b>{best[0]}</b> بهترین عملکرد رو داشته.")
                if worst[1].get('win_rate', 0) < 50:
                    lines.append(f"⚠️ اندیکاتور <b>{worst[0]}</b> عملکرد ضعیفی داشته، بهتره بررسی بشه.")
            lines.append("")
        
        # بهترین و بدترین معامله
        if best_trade:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("🏆 <b>بهترین معامله:</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"📊 {best_trade.get('symbol')} | {best_trade.get('signal_type')}")
            lines.append(f"💰 سود: +{best_trade.get('profit', 0):.2f} USDT")
            lines.append(f"📅 {best_trade.get('date', '')}")
            lines.append("")
        
        if worst_trade:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("📉 <b>بدترین معامله:</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"📊 {worst_trade.get('symbol')} | {worst_trade.get('signal_type')}")
            lines.append(f"💰 ضرر: {worst_trade.get('profit', 0):.2f} USDT")
            lines.append(f"📅 {worst_trade.get('date', '')}")
            lines.append("")
        
        lines.append("---")
        lines.append(f"<i>🕐 {persian_date}</i>")
        
        return self.send_message("\n".join(lines))
