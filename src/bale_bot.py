"""
Bale Messenger Module
Responsible for sending signals and messages to Bale messenger
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

import requests

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
        self.base_url = f"https://tapi.bale.ai/v1/bot{token}"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        ارسال پیام به بله
        
        Args:
            text: متن پیام
            parse_mode: حالت پارس (HTML یا Markdown)
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        if self.config.TEST_MODE:
            logger.info(f"[TEST MODE] Would send: {text[:100]}...")
            return True
            
        if not self.token or not self.chat_id:
            logger.error("❌ Bale token or chat_id not configured")
            return False
            
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            
            response = self.session.post(
                url,
                json=payload,
                timeout=self.config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    logger.info("✅ Message sent to Bale successfully")
                    return True
                else:
                    logger.error(f"❌ Bale API error: {data}")
                    return False
            else:
                logger.error(f"❌ HTTP error {response.status_code}: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout sending message to Bale")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error sending to Bale: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error sending to Bale: {e}")
            return False
    
    def send_signal(self, signal: Dict[str, Any]) -> bool:
        """
        ارسال سیگنال معاملاتی به بله
        
        Args:
            signal: دیکشنری سیگنال تولید شده توسط SignalEngine
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        if not signal:
            return False
            
        message = self._format_signal_message(signal)
        return self.send_message(message)
    
    def send_summary(self, signals: List[Dict[str, Any]]) -> bool:
        """
        ارسال خلاصه بازار
        
        Args:
            signals: لیست سیگنال‌ها
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        if not signals:
            return False
            
        message = self._format_summary_message(signals)
        return self.send_message(message)
    
    def send_multiple_signals(self, signals: List[Dict[str, Any]], limit: int = 5) -> bool:
        """
        ارسال چند سیگنال برتر
        
        Args:
            signals: لیست سیگنال‌ها
            limit: تعداد سیگنال‌های برتر
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        if not signals:
            return False
            
        # انتخاب بهترین سیگنال‌ها
        top_signals = sorted(
            [s for s in signals if s.get('signal') != 'WAIT'],
            key=lambda x: x.get('score', 0),
            reverse=True
        )[:limit]
        
        if not top_signals:
            return False
            
        # ارسال هر سیگنال به صورت جداگانه
        success = True
        for signal in top_signals:
            if not self.send_signal(signal):
                success = False
                
        return success
    
    def _format_signal_message(self, signal: Dict[str, Any]) -> str:
        """
        فرمت کردن پیام سیگنال
        """
        symbol = signal.get('symbol', 'Unknown')
        price = signal.get('price', 0)
        signal_type = signal.get('signal', 'WAIT')
        strength = signal.get('strength', 'NEUTRAL')
        score = signal.get('score', 50)
        confidence = signal.get('confidence', 50)
        
        # ایموجی بر اساس نوع سیگنال
        emoji_map = {
            'BUY': '🟢',
            'SELL': '🔴',
            'WAIT': '🟡'
        }
        emoji = emoji_map.get(signal_type, '⚪')
        
        # ایموجی قدرت
        strength_emoji = {
            'WEAK': '💤',
            'NORMAL': '📈',
            'STRONG': '🔥',
            'VERY_STRONG': '💪',
            'EXCEPTIONAL': '🌟'
        }.get(strength, '')
        
        # =========================
        # ساخت پیام
        # =========================
        lines = [
            f"{emoji} <b>{symbol}</b>",
            f"💰 قیمت: {price:,.2f} USDT",
            f"📊 سیگنال: <b>{signal_type}</b> {strength_emoji}",
            f"🔥 قدرت: {strength}",
            f"🎯 اطمینان: {confidence:.1f}%",
            f"📈 امتیاز: {score:.1f}/100",
            ""
        ]
        
        # اندیکاتورها
        rsi = signal.get('rsi', 50)
        macd = signal.get('macd', 0)
        macd_signal = signal.get('macd_signal', 0)
        adx = signal.get('adx', 20)
        volume_ratio = signal.get('volume_ratio', 1.0)
        
        macd_status = "صعودی" if macd > macd_signal else "نزولی"
        
        lines.extend([
            "📊 <b>اندیکاتورها:</b>",
            f"• RSI: {rsi:.1f}",
            f"• MACD: {macd_status}",
            f"• ADX: {adx:.1f}",
            f"• حجم: {volume_ratio:.2f}x",
            ""
        ])
        
        # مدیریت ریسک
        stop_loss = signal.get('stop_loss')
        tp1 = signal.get('tp1')
        tp2 = signal.get('tp2')
        risk_reward = signal.get('risk_reward', 0)
        
        if stop_loss and tp1:
            lines.extend([
                "🎯 <b>مدیریت ریسک:</b>",
                f"🛑 حد ضرر: {stop_loss:,.2f}",
                f"🎯 هدف ۱: {tp1:,.2f}",
                f"🎯 هدف ۲: {tp2:,.2f}" if tp2 else "",
                f"⚖️ R/R: {risk_reward:.2f}",
                ""
            ])
        
        # حمایت و مقاومت
        support = signal.get('support')
        resistance = signal.get('resistance')
        
        if support and resistance:
            lines.extend([
                "📐 <b>سطوح کلیدی:</b>",
                f"🟢 حمایت: {support:,.2f}",
                f"🔴 مقاومت: {resistance:,.2f}",
                ""
            ])
        
        # زمان
        timestamp = signal.get('timestamp')
        if timestamp:
            time_str = timestamp.strftime('%Y-%m-%d %H:%M')
            lines.append(f"⏰ {time_str}")
        
        return "\n".join(lines)
    
    def _format_summary_message(self, signals: List[Dict[str, Any]]) -> str:
        """
        فرمت کردن پیام خلاصه
        """
        # آمار کلی
        total = len(signals)
        buy_signals = [s for s in signals if s.get('signal') == 'BUY']
        sell_signals = [s for s in signals if s.get('signal') == 'SELL']
        wait_signals = [s for s in signals if s.get('signal') == 'WAIT']
        
        lines = [
            "━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>خلاصه بازار</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🟢 خرید: {len(buy_signals)}",
            f"🔴 فروش: {len(sell_signals)}",
            f"🟡 صبر: {len(wait_signals)}",
            f"📊 کل: {total}",
            ""
        ]
        
        # بهترین فرصت‌ها
        if buy_signals:
            best_buy = max(buy_signals, key=lambda x: x.get('score', 0))
            lines.append(f"🔥 بهترین خرید: {best_buy.get('symbol')} ({best_buy.get('score', 0):.1f}%)")
            
        if sell_signals:
            best_sell = max(sell_signals, key=lambda x: x.get('score', 0))
            lines.append(f"⚠️ بهترین فروش: {best_sell.get('symbol')} ({best_sell.get('score', 0):.1f}%)")
        
        lines.append("")
        lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        return "\n".join(lines)
    
    def send_error(self, error_message: str) -> bool:
        """
        ارسال پیام خطا
        
        Args:
            error_message: متن خطا
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        message = f"❌ <b>خطا</b>\n\n{error_message}"
        return self.send_message(message)
