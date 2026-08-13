"""
Bale Messenger Module
Responsible for sending signals and messages to Bale messenger
"""

import requests
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import jdatetime

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
            
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"https://tapi.bale.ai/v1/bot{self.token}/sendMessage",
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
                elif response.status_code == 503:
                    logger.warning(f"⚠️ خطای ۵۰۳، تلاش {attempt+1}/{max_retries}")
                    time.sleep(5)
                else:
                    logger.error(f"❌ HTTP error {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                logger.error(f"❌ Timeout (تلاش {attempt+1}/{max_retries})")
                time.sleep(3)
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ خطای شبکه: {e}")
                time.sleep(3)
            except Exception as e:
                logger.error(f"❌ خطای غیرمنتظره: {e}")
                time.sleep(3)
        
        logger.error("❌ ارسال به بله پس از تلاش‌های مجدد ناموفق بود.")
        return False
    
    def send_signal(self, signal: Dict[str, Any]) -> bool:
        """
        ارسال سیگنال معاملاتی به بله
        """
        if not signal:
            return False
            
        message = self._format_signal_message(signal)
        return self.send_message(message)
    
    def send_summary(self, signals: List[Dict[str, Any]]) -> bool:
        """
        ارسال خلاصه بازار
        """
        if not signals:
            return False
            
        message = self._format_summary_message(signals)
        return self.send_message(message)
    
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
    
    def _get_persian_datetime(self) -> str:
        """
        دریافت تاریخ و زمان به فارسی
        """
        utc_now = datetime.now(timezone.utc)
        iran_now = utc_now + jdatetime.timedelta(hours=3, minutes=30)
        now = jdatetime.datetime.fromgregorian(datetime=iran_now)
        
        weekday_map = {
            'Saturday': 'شنبه', 'Sunday': 'یکشنبه', 'Monday': 'دوشنبه',
            'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه',
            'Thursday': 'پنجشنبه', 'Friday': 'جمعه'
        }
        
        month_map = {
            'Farvardin': 'فروردین', 'Ordibehesht': 'اردیبهشت', 'Khordad': 'خرداد',
            'Tir': 'تیر', 'Mordad': 'مرداد', 'Shahrivar': 'شهریور',
            'Mehr': 'مهر', 'Aban': 'آبان', 'Azar': 'آذر',
            'Dey': 'دی', 'Bahman': 'بهمن', 'Esfand': 'اسفند'
        }
        
        weekday = weekday_map.get(now.strftime('%A'), '')
        month = month_map.get(now.strftime('%B'), '')
        
        return f"{weekday} {now.strftime('%d')} {month} {now.strftime('%Y')} - ساعت {now.strftime('%H:%M')}"
    
    def _format_signal_message(self, signal: Dict[str, Any]) -> str:
        """
        فرمت کردن پیام سیگنال به سبک ربات قبلی
        """
        symbol = signal.get('symbol', 'Unknown')
        price = signal.get('price', 0)
        signal_type = signal.get('signal', 'WAIT')
        strength = signal.get('strength', 'NEUTRAL')
        score = signal.get('score', 50)
        confidence = signal.get('confidence', 50)
        persian_date = self._get_persian_datetime()
        
        # تعیین وضعیت کلی
        status_map = {
            (70, 100): ("🔥", "خرید قوی", "فرصت عالی برای خرید"),
            (60, 69): ("📈", "خرید ملایم", "احتمال رشد وجود دارد"),
            (50, 59): ("⏸️", "نگهداری", "فعلاً دست نگه دار"),
            (40, 49): ("📉", "فروش ملایم", "احتمال ریزش وجود دارد"),
            (0, 39): ("💀", "فروش قوی", "ریسک بالاست، احتیاط کن")
        }
        
        status_emoji, status_text, advice = "⏸️", "نامشخص", ""
        for (low, high), (emoji, status, adv) in status_map.items():
            if low <= score <= high:
                status_emoji, status_text, advice = emoji, status, adv
                break
        
        # ساخت پیام
        lines = [
            f"{status_emoji} تحلیل {symbol}",
            f"📅 {persian_date}",
            "",
            "---",
            f"وضعیت کلی: {status_text} - {advice}",
            f"امتیاز سیستم: {score:.1f} از ۱۰۰",
            f"اطمینان: {confidence:.1f}%",
            f"قدرت سیگنال: {strength}",
            "",
        ]
        
        # اندیکاتورها
        rsi = signal.get('rsi', 50)
        macd = signal.get('macd', 0)
        macd_signal = signal.get('macd_signal', 0)
        adx = signal.get('adx', 20)
        volume_ratio = signal.get('volume_ratio', 1.0)
        
        macd_status = "صعودی" if macd > macd_signal else "نزولی"
        
        lines.extend([
            "📊 اندیکاتورها:",
            f"🔸 RSI: {rsi:.1f}",
            f"🔸 MACD: {macd_status}",
            f"🔸 ADX: {adx:.1f}",
            f"🔸 حجم: {volume_ratio:.2f}x",
            "",
        ])
        
        # مدیریت ریسک
        stop_loss = signal.get('stop_loss')
        tp1 = signal.get('tp1')
        tp2 = signal.get('tp2')
        risk_reward = signal.get('risk_reward', 0)
        
        if stop_loss and tp1:
            lines.extend([
                "🎯 مدیریت ریسک:",
                f"🛑 حد ضرر: {stop_loss:,.2f}",
                f"🎯 هدف ۱: {tp1:,.2f}",
                f"🎯 هدف ۲: {tp2:,.2f}" if tp2 else "",
                f"⚖️ نسبت ریسک/بازده: {risk_reward:.2f}",
                "",
            ])
        
        # حمایت و مقاومت
        support = signal.get('support')
        resistance = signal.get('resistance')
        
        if support and resistance:
            lines.extend([
                "📐 سطوح کلیدی:",
                f"🟢 حمایت: {support:,.2f}",
                f"🔴 مقاومت: {resistance:,.2f}",
                "",
            ])
        
        # قیمت
        lines.extend([
            "---",
            f"💰 قیمت لحظه‌ای: {price:,.2f} USDT",
        ])
        
        return "\n".join(lines)
    
    def _format_summary_message(self, signals: List[Dict[str, Any]]) -> str:
        """
        فرمت کردن پیام خلاصه به سبک ربات قبلی
        """
        persian_date = self._get_persian_datetime()
        
        total = len(signals)
        buy_signals = [s for s in signals if s.get('signal') == 'BUY']
        sell_signals = [s for s in signals if s.get('signal') == 'SELL']
        wait_signals = [s for s in signals if s.get('signal') == 'WAIT']
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            f"📊 خلاصه بازار - {persian_date}",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🟢 خرید: {len(buy_signals)}",
            f"🔴 فروش: {len(sell_signals)}",
            f"🟡 صبر: {len(wait_signals)}",
            f"📊 کل: {total}",
            "",
        ]
        
        if buy_signals:
            best_buy = max(buy_signals, key=lambda x: x.get('score', 0))
            lines.append(f"🔥 بهترین خرید: {best_buy.get('symbol')} ({best_buy.get('score', 0):.1f}%)")
            
        if sell_signals:
            best_sell = max(sell_signals, key=lambda x: x.get('score', 0))
            lines.append(f"⚠️ بهترین فروش: {best_sell.get('symbol')} ({best_sell.get('score', 0):.1f}%)")
        
        lines.append("")
        lines.append(f"⏰ {persian_date}")
        
        return "\n".join(lines)
    
    def send_error(self, error_message: str) -> bool:
        """
        ارسال پیام خطا
        """
        message = f"❌ خطا\n\n{error_message}"
        return self.send_message(message)
