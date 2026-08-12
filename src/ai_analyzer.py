"""
AI Analyzer Module
Responsible for sending data to AI and receiving analysis
"""

import logging
import re
import json
from typing import Optional, Dict, Any, List

import requests

from config import Config

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """
    تحلیلگر هوش مصنوعی برای بررسی سیگنال‌ها و اخبار
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.api_key = config.AI_API_KEY
        self.provider = config.AI_PROVIDER
        self.model = config.AI_MODEL
        self.timeout = config.AI_TIMEOUT
        
        # =========================
        # بررسی پشتیبانی مدل از JSON mode
        # =========================
        self.supports_json_mode = self._check_json_mode_support()
        
    def _check_json_mode_support(self) -> bool:
        """
        بررسی اینکه مدل انتخابی از JSON mode پشتیبانی می‌کند
        """
        # مدل‌های پشتیبانی‌کننده از JSON mode (بر اساس نام دقیق)
        json_supported_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4-0125-preview",
            "gpt-4-1106-preview",
            "gpt-3.5-turbo-0125",
            "gpt-3.5-turbo-1106"
        ]
        
        # بررسی تطابق دقیق مدل
        if self.model in json_supported_models:
            logger.info(f"✅ JSON mode supported for model: {self.model}")
            return True
        
        # اگر مدل با gpt-4 شروع شود و در لیست نباشد، احتمالاً پشتیبانی می‌کند
        if self.model.startswith("gpt-4"):
            logger.info(f"⚠️ Assuming JSON mode support for {self.model} (GPT-4 family)")
            return True
        
        logger.info(f"❌ JSON mode NOT supported for model: {self.model}")
        return False
    
    def analyze(
        self, 
        signal_data: Dict[str, Any],
        news_summary: Optional[str] = None,
        news_sentiment: Optional[Dict[str, Any]] = None,
        market_regime: str = "خنثی"
    ) -> Dict[str, Any]:
        """
        تحلیل سیگنال توسط هوش مصنوعی
        
        Args:
            signal_data: دیکشنری سیگنال تولید شده توسط SignalEngine
            news_summary: خلاصه اخبار از NewsReader
            news_sentiment: دیکشنری احساسات اخبار (اختیاری)
            market_regime: وضعیت کلی بازار
            
        Returns:
            دیکشنری شامل نظر AI
        """
        # اگر AI غیرفعال است
        if not self.config.ENABLE_AI_ANALYSIS:
            return {
                'enabled': False,
                'analysis': 'AI analysis is disabled',
                'opinion': 'NEUTRAL',
                'confidence': 0,
                'summary': 'AI analysis is disabled'
            }
        
        # اگر API Key موجود نیست
        if not self.api_key:
            logger.warning("⚠️ AI_API_KEY not set")
            return {
                'enabled': True,
                'analysis': 'AI API key not configured',
                'opinion': 'NEUTRAL',
                'confidence': 0,
                'summary': 'AI API key not configured'
            }
        
        try:
            # =========================
            # ساخت پرامپت با درخواست خروجی JSON
            # =========================
            prompt = self._build_prompt(
                signal_data, 
                news_summary, 
                news_sentiment,
                market_regime
            )
            
            # =========================
            # ارسال به AI بر اساس provider
            # =========================
            if self.provider == 'openai':
                response = self._call_openai(prompt)
            else:
                logger.warning(f"⚠️ Unknown AI provider: {self.provider}")
                return {
                    'enabled': True,
                    'analysis': f'Unknown AI provider: {self.provider}',
                    'opinion': 'NEUTRAL',
                    'confidence': 0,
                    'summary': f'Unknown AI provider: {self.provider}'
                }
            
            # =========================
            # پردازش پاسخ
            # =========================
            if response:
                return self._parse_response(response, signal_data)
            else:
                return {
                    'enabled': True,
                    'analysis': 'AI returned empty response',
                    'opinion': 'NEUTRAL',
                    'confidence': 0,
                    'summary': 'AI returned empty response'
                }
                
        except requests.exceptions.Timeout:
            logger.error("❌ AI request timeout")
            return {
                'enabled': True,
                'analysis': 'AI request timeout',
                'opinion': 'NEUTRAL',
                'confidence': 0,
                'summary': 'AI request timeout'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ AI request error: {e}")
            return {
                'enabled': True,
                'analysis': f'AI request error: {str(e)[:100]}',
                'opinion': 'NEUTRAL',
                'confidence': 0,
                'summary': f'AI request error: {str(e)[:100]}'
            }
        except Exception as e:
            logger.error(f"❌ AI analysis error: {e}")
            return {
                'enabled': True,
                'analysis': f'AI error: {str(e)[:100]}',
                'opinion': 'NEUTRAL',
                'confidence': 0,
                'summary': f'AI error: {str(e)[:100]}'
            }
    
    def _format_number(self, value: Optional[float], default: str = "نامشخص") -> str:
        """
        فرمت کردن عدد با جداکننده هزارگان
        
        Args:
            value: عدد مورد نظر
            default: مقدار پیش‌فرض در صورت None بودن
            
        Returns:
            رشته فرمت شده
        """
        if value is None:
            return default
        try:
            return f"{value:,.0f}"
        except (TypeError, ValueError):
            return default
    
    def _build_prompt(
        self, 
        signal_data: Dict[str, Any],
        news_summary: Optional[str] = None,
        news_sentiment: Optional[Dict[str, Any]] = None,
        market_regime: str = "خنثی"
    ) -> str:
        """
        ساخت پرامپت برای AI با درخواست خروجی JSON
        """
        # استخراج اطلاعات از سیگنال
        symbol = signal_data.get('symbol', 'Unknown')
        price = signal_data.get('price', 0)
        signal_type = signal_data.get('signal', 'WAIT')
        strength = signal_data.get('strength', 'NEUTRAL')
        score = signal_data.get('score', 50)
        confidence = signal_data.get('confidence', 50)
        
        rsi = signal_data.get('rsi', 50)
        macd = signal_data.get('macd', 0)
        macd_signal = signal_data.get('macd_signal', 0)
        adx = signal_data.get('adx', 20)
        di_plus = signal_data.get('di_plus', 0)
        di_minus = signal_data.get('di_minus', 0)
        atr = signal_data.get('atr', 0)
        volume_ratio = signal_data.get('volume_ratio', 1.0)
        ema_fast = signal_data.get('ema_fast', price)
        ema_slow = signal_data.get('ema_slow', price)
        
        support = signal_data.get('support')
        resistance = signal_data.get('resistance')
        stop_loss = signal_data.get('stop_loss')
        tp1 = signal_data.get('tp1')
        tp2 = signal_data.get('tp2')
        risk_reward = signal_data.get('risk_reward', 0)
        
        macd_status = "صعودی" if macd > macd_signal else "نزولی"
        trend = "صعودی" if ema_fast > ema_slow else ("نزولی" if ema_fast < ema_slow else "خنثی")
        
        # تشخیص نوع دارایی
        asset_type = "رمززارز"
        if symbol in ['XAUT', 'PAXG']:
            asset_type = "طلا"
        
        # =========================
        # فرمت کردن اعداد با شرط
        # =========================
        price_text = self._format_number(price)
        support_text = self._format_number(support)
        resistance_text = self._format_number(resistance)
        stop_loss_text = self._format_number(stop_loss)
        tp1_text = self._format_number(tp1)
        tp2_text = self._format_number(tp2)
        atr_text = self._format_number(atr)
        ema_fast_text = self._format_number(ema_fast)
        ema_slow_text = self._format_number(ema_slow)
        
        # =========================
        # ساخت بخش احساسات اخبار
        # =========================
        news_section = ""
        if news_sentiment:
            sentiment = news_sentiment.get('sentiment', 'neutral')
            sentiment_score = news_sentiment.get('score', 0)
            bullish_count = news_sentiment.get('bullish_count', 0)
            bearish_count = news_sentiment.get('bearish_count', 0)
            
            sentiment_emoji = {
                'bullish': '🟢 صعودی',
                'bearish': '🔴 نزولی',
                'neutral': '🟡 خنثی'
            }.get(sentiment, '🟡 خنثی')
            
            news_section = f"""
### احساسات اخبار (تحلیل شده توسط سیستم):
- جهت کلی: {sentiment_emoji}
- امتیاز احساسات: {sentiment_score:+.2f} (از -1 تا +1)
- سیگنال‌های صعودی: {bullish_count}
- سیگنال‌های نزولی: {bearish_count}
"""
        
        # =========================
        # ساخت پرامپت با درخواست JSON
        # =========================
        prompt = f"""شما یک تحلیلگر حرفه‌ای بازارهای مالی و دارایی‌های دیجیتال هستید.

لطفاً بر اساس داده‌های زیر تحلیل خود را ارائه دهید و در قالب JSON پاسخ دهید.

### داده‌های تکنیکال {symbol} ({asset_type}):
- قیمت فعلی: {price_text}
- RSI: {rsi:.1f}
- MACD: {macd_status} (مقدار: {macd:.2f})
- EMA20: {ema_fast_text}, EMA50: {ema_slow_text}
- روند: {trend}
- ADX (قدرت روند): {adx:.1f}
- DI+ (جهت صعودی): {di_plus:.1f}, DI- (جهت نزولی): {di_minus:.1f}
- نوسان (ATR): {atr_text}
- نسبت حجم: {volume_ratio:.2f}x
- حمایت: {support_text}, مقاومت: {resistance_text}

### امتیاز سیستم ربات:
- امتیاز کلی: {score:.1f}/100
- سیگنال: {signal_type} ({strength})
- اطمینان ربات: {confidence:.1f}%

### مدیریت ریسک:
- حد ضرر: {stop_loss_text}
- هدف ۱: {tp1_text}
- هدف ۲: {tp2_text}
- نسبت ریسک/بازده: {risk_reward:.2f}

### وضعیت کلی بازار:
{market_regime}
{news_section}
### خلاصه اخبار:
{news_summary or "اخبار در دسترس نیست"}

---
لطفاً پاسخ خود را دقیقاً در قالب JSON زیر بنویسید:

{{
    "opinion": "BUY یا SELL یا WAIT یا NEUTRAL",
    "confidence": 0-100,
    "summary": "خلاصه تحلیل شما در ۲-۳ جمله",
    "positive_factors": ["عامل مثبت ۱", "عامل مثبت ۲"],
    "negative_factors": ["عامل منفی ۱", "عامل منفی ۲"],
    "risk_assessment": "کم یا متوسط یا زیاد",
    "recommendation": "توصیه نهایی شما"
}}

فقط JSON را برگردانید، هیچ متن دیگری. باید به فارسی باشد."""
        
        return prompt
    
    def _call_openai(self, prompt: str) -> Optional[str]:
        """
        فراخوانی OpenAI API
        """
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "شما یک تحلیلگر حرفه‌ای بازارهای مالی هستید. همیشه به صورت JSON و با ساختار مشخص پاسخ دهید."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.config.AI_TEMPERATURE,
                "max_tokens": self.config.AI_MAX_TOKENS
            }
            
            # =========================
            # فقط در صورت پشتیبانی مدل، JSON mode را فعال کن
            # =========================
            if self.supports_json_mode:
                payload["response_format"] = {"type": "json_object"}
                logger.debug("Using JSON mode for OpenAI request")
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('choices', [{}])[0].get('message', {}).get('content', '')
            else:
                logger.error(f"❌ OpenAI error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ OpenAI call error: {e}")
            return None
    
    def _parse_response(
        self, 
        response: str,
        signal_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        پردازش پاسخ JSON از AI
        """
        try:
            # =========================
            # تلاش برای استخراج JSON از پاسخ
            # =========================
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
            else:
                logger.warning("No JSON found in response, falling back to text parsing")
                return self._parse_text_response(response, signal_data)
            
            # =========================
            # استخراج فیلدها با مقدار پیش‌فرض
            # =========================
            opinion = data.get('opinion', 'NEUTRAL').upper()
            if opinion not in ['BUY', 'SELL', 'WAIT', 'NEUTRAL']:
                opinion = 'NEUTRAL'
            
            confidence = data.get('confidence', 50)
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 100:
                confidence = 50
            
            summary = data.get('summary', 'تحلیل AI در دسترس نیست')
            positive_factors = data.get('positive_factors', [])
            if not isinstance(positive_factors, list):
                positive_factors = []
            negative_factors = data.get('negative_factors', [])
            if not isinstance(negative_factors, list):
                negative_factors = []
            risk_assessment = data.get('risk_assessment', 'متوسط')
            recommendation = data.get('recommendation', '')
            
            # =========================
            # تشخیص اختلاف نظر با ربات (نرمال‌سازی شده)
            # =========================
            robot_signal = self._normalize_signal(signal_data.get('signal', 'WAIT'))
            disagreement = False
            if robot_signal != opinion and opinion != 'NEUTRAL':
                disagreement = True
            
            return {
                'enabled': True,
                'raw_response': response,
                'opinion': opinion,
                'confidence': int(confidence),
                'summary': summary,
                'positive_factors': positive_factors[:5],
                'negative_factors': negative_factors[:5],
                'risk_assessment': risk_assessment,
                'recommendation': recommendation,
                'disagreement': disagreement
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON decode error: {e}, falling back to text parsing")
            return self._parse_text_response(response, signal_data)
        except Exception as e:
            logger.error(f"❌ Error parsing AI response: {e}")
            return self._parse_text_response(response, signal_data)
    
    def _normalize_signal(self, signal: str) -> str:
        """
        نرمال‌سازی سیگنال ربات برای مقایسه با AI
        """
        signal = signal.upper()
        if 'BUY' in signal:
            return 'BUY'
        elif 'SELL' in signal:
            return 'SELL'
        elif 'WAIT' in signal:
            return 'WAIT'
        else:
            return 'NEUTRAL'
    
    def _parse_text_response(
        self, 
        response: str,
        signal_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        پردازش پاسخ متنی AI (Fallback در صورت عدم دریافت JSON)
        """
        # تشخیص نظر
        opinion = 'NEUTRAL'
        text_lower = response.lower()
        
        buy_words = ['buy', 'خرید', 'صعود', 'رشد']
        sell_words = ['sell', 'فروش', 'نزول', 'کاهش', 'سقوط']
        wait_words = ['wait', 'صبر', 'منتظر', 'انتظار']
        
        buy_count = sum(1 for word in buy_words if word in text_lower)
        sell_count = sum(1 for word in sell_words if word in text_lower)
        wait_count = sum(1 for word in wait_words if word in text_lower)
        
        if buy_count > sell_count and buy_count > wait_count:
            opinion = 'BUY'
        elif sell_count > buy_count and sell_count > wait_count:
            opinion = 'SELL'
        elif wait_count > buy_count and wait_count > sell_count:
            opinion = 'WAIT'
        
        # استخراج confidence
        confidence = 50
        conf_match = re.search(r'اطمینان\s*[:=]\s*(\d+)', response)
        if not conf_match:
            conf_match = re.search(r'confidence\s*[:=]\s*(\d+)', text_lower)
        if conf_match:
            confidence = int(conf_match.group(1))
        
        # استخراج خلاصه
        summary = response[:200] + ('...' if len(response) > 200 else '')
        
        robot_signal = self._normalize_signal(signal_data.get('signal', 'WAIT'))
        disagreement = False
        if robot_signal != opinion and opinion != 'NEUTRAL':
            disagreement = True
        
        return {
            'enabled': True,
            'raw_response': response,
            'opinion': opinion,
            'confidence': confidence,
            'summary': summary,
            'positive_factors': [],
            'negative_factors': [],
            'risk_assessment': 'متوسط',
            'recommendation': '',
            'disagreement': disagreement
        }
    
    def get_analysis_text(self, ai_result: Dict[str, Any]) -> str:
        """
        تولید متن قابل نمایش برای پیام نهایی
        """
        if not ai_result.get('enabled', False):
            return "🤖 AI: غیرفعال"
        
        if ai_result.get('analysis'):
            return f"🤖 AI: {ai_result.get('analysis')}"
        
        opinion = ai_result.get('opinion', 'NEUTRAL')
        confidence = ai_result.get('confidence', 0)
        summary = ai_result.get('summary', '')
        risk = ai_result.get('risk_assessment', 'متوسط')
        recommendation = ai_result.get('recommendation', '')
        
        opinion_emoji = {
            'BUY': '🟢',
            'SELL': '🔴',
            'WAIT': '🟡',
            'NEUTRAL': '⚪'
        }.get(opinion, '⚪')
        
        parts = [
            "━━━━━━━━━━━━━━━━━━━━",
            "🤖 <b>تحلیل هوش مصنوعی</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        
        if summary:
            parts.append(f"📌 {summary}")
            parts.append("")
        
        positive = ai_result.get('positive_factors', [])
        if positive:
            parts.append("🟢 <b>عوامل مثبت:</b>")
            for factor in positive[:3]:
                parts.append(f"• {factor}")
            parts.append("")
        
        negative = ai_result.get('negative_factors', [])
        if negative:
            parts.append("🔴 <b>عوامل منفی/ریسک‌ها:</b>")
            for factor in negative[:3]:
                parts.append(f"• {factor}")
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
        parts.append(f"📊 <b>اطمینان AI:</b> {confidence}%")
        
        if ai_result.get('disagreement', False):
            parts.append("")
            parts.append("⚠️ <b>اختلاف نظر با ربات وجود دارد</b>")
        
        return "\n".join(parts)
