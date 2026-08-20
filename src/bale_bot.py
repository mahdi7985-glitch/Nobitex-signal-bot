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
