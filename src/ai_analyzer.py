"""
AI Analyzer Module - نسخه ۲.۰ (مستقل با داده کامل + Cache)
Responsible for independent market analysis based on raw OHLCV data
"""

import logging
import re
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta  # 🔥 اضافه شد

import requests

# ✅ اضافه کردن پشتیبانی از Gemini
try:
    import google.generativeai as genai
except ImportError:
    genai = None
    logging.warning("google-generativeai not installed. Run: pip install google-generativeai")

from config import Config

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """
    تحلیلگر هوش مصنوعی مستقل
    فقط داده خام OHLCV را دریافت کرده و تحلیل خود را ارائه می‌دهد
    """

    def __init__(self, config=Config):
        self.config = config
        self.api_key = config.AI_API_KEY
        self.provider = config.AI_PROVIDER
        self.model = config.AI_MODEL
        self.timeout = config.AI_TIMEOUT

        # =========================
        # 🔥 کش برای کاهش درخواست‌های تکراری
        # =========================
        self.cache = {}  # کش برای ذخیره نتایج
        self.cache_ttl = 300  # ۵ دقیقه اعتبار کش

        # =========================
        # راه‌اندازی Gemini در صورت انتخاب
        # =========================
        self.gemini_model = None
        if self.provider == 'gemini' and self.api_key and genai:
            try:
                genai.configure(api_key=self.api_key)
                self.gemini_model = genai.GenerativeModel(self.model or "gemini-2.5-flash")
                logger.info(f"✅ Gemini AI initialized with model: {self.model}")
            except Exception as e:
                logger.error(f"❌ Gemini initialization failed: {e}")
                self.gemini_model = None

        # =========================
        # بررسی پشتیبانی مدل از JSON mode
        # =========================
        self.supports_json_mode = self._check_json_mode_support()

    def _check_json_mode_support(self) -> bool:
        """بررسی اینکه مدل انتخابی از JSON mode پشتیبانی می‌کند"""
        if self.provider != 'openai':
            return False

        json_supported_models = [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-turbo-preview",
            "gpt-4-0125-preview", "gpt-4-1106-preview",
            "gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106"
        ]

        if self.model in json_supported_models:
            logger.info(f"✅ JSON mode supported for model: {self.model}")
            return True

        if self.model.startswith("gpt-4"):
            logger.info(f"⚠️ Assuming JSON mode support for {self.model} (GPT-4 family)")
            return True

        logger.info(f"❌ JSON mode NOT supported for model: {self.model}")
        return False

    def _get_cache_key(self, symbol: str, timeframe: str, data_hash: str = "") -> str:
        """
        ساخت کلید کش بر اساس نماد، تایم‌فریم و هش داده‌ها
        """
        return f"{symbol}_{timeframe}_{data_hash[:20]}"

    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        دریافت نتیجه از کش
        """
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            # بررسی انقضای کش
            if (datetime.now() - cached['timestamp']).total_seconds() < self.cache_ttl:
                logger.info(f"✅ AI Cache hit for {cache_key}")
                return cached['result']
            else:
                logger.debug(f"⏰ AI Cache expired for {cache_key}")
                del self.cache[cache_key]
        return None

    def _set_cache_result(self, cache_key: str, result: Dict[str, Any]):
        """
        ذخیره نتیجه در کش
        """
        self.cache[cache_key] = {
            'result': result,
            'timestamp': datetime.now()
        }
        logger.info(f"💾 AI Cache set for {cache_key}")

    def _clear_expired_cache(self):
        """
        پاک کردن کش‌های منقضی‌شده
        """
        expired_keys = []
        now = datetime.now()
        for key, value in self.cache.items():
            if (now - value['timestamp']).total_seconds() >= self.cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            logger.debug(f"🗑️ AI Cache cleared: {key}")

    def analyze(
        self, 
        ohlcv_data: List[Dict[str, Any]],
        symbol: str,
        current_price: float,
        timeframe: str = "15m"
    ) -> Dict[str, Any]:
        """
        تحلیل مستقل بازار توسط هوش مصنوعی بر اساس داده خام
        
        Args:
            ohlcv_data: لیستی از کندل‌ها با کلیدهای timestamp, open, high, low, close, volume
            symbol: نماد دارایی (مثلاً BTC)
            current_price: قیمت فعلی
            timeframe: تایم‌فریم داده‌ها (پیش‌فرض: 15m)
            
        Returns:
            دیکشنری شامل تحلیل مستقل AI
        """
        # اگر AI غیرفعال است
        if not self.config.ENABLE_AI_ANALYSIS:
            return self._create_fallback_response("AI analysis is disabled")

        # اگر API Key موجود نیست
        if not self.api_key:
            logger.warning("⚠️ AI_API_KEY not set")
            return self._create_fallback_response("AI API key not configured")

        # اگر داده خام وجود ندارد
        if not ohlcv_data or len(ohlcv_data) < 50:
            logger.warning(f"⚠️ Insufficient OHLCV data: {len(ohlcv_data) if ohlcv_data else 0} candles")
            return self._create_fallback_response("Insufficient OHLCV data for analysis")

        # ================================================
        # 🔥 بررسی کش قبل از درخواست به API
        # ================================================
        # پاک کردن کش‌های منقضی‌شده
        self._clear_expired_cache()

        # ایجاد هش از داده‌ها برای تشخیص تغییرات
        if ohlcv_data:
            last_candle = ohlcv_data[-1]
            data_hash = f"{last_candle.get('close', 0)}_{last_candle.get('volume', 0)}_{len(ohlcv_data)}"
        else:
            data_hash = "no_data"

        cache_key = self._get_cache_key(symbol, timeframe, data_hash)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            return cached_result

        try:
            # =========================
            # ساخت پرامپت با داده کامل
            # =========================
            prompt = self._build_prompt(ohlcv_data, symbol, current_price, timeframe)

            # =========================
            # ارسال به AI بر اساس provider
            # =========================
            if self.provider == 'openai':
                response = self._call_openai(prompt)
            elif self.provider == 'gemini':
                response = self._call_gemini(prompt)
            else:
                logger.warning(f"⚠️ Unknown AI provider: {self.provider}")
                return self._create_fallback_response(f"Unknown AI provider: {self.provider}")

            # =========================
            # پردازش پاسخ
            # =========================
            if response:
                result = self._parse_response(response)
                # ================================================
                # 🔥 ذخیره نتیجه در کش (فقط در صورت معتبر بودن)
                # ================================================
                if result and result.get('direction') != 'INVALID' and not result.get('parse_error', False):
                    self._set_cache_result(cache_key, result)
                return result
            else:
                return self._create_fallback_response("AI returned empty response")

        except requests.exceptions.Timeout:
            logger.error("❌ AI request timeout")
            return self._create_fallback_response("AI request timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ AI request error: {e}")
            return self._create_fallback_response(f"AI request error: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"❌ AI analysis error: {e}")
            return self._create_fallback_response(f"AI error: {str(e)[:100]}")

    def _create_fallback_response(self, reason: str) -> Dict[str, Any]:
        """
        ایجاد پاسخ پیش‌فرض در صورت خطا
        """
        return {
            'enabled': True,
            'direction': 'INVALID',
            'confidence': 0,
            'trend': 'UNKNOWN',
            'trend_strength': 0,
            'momentum': 'NEUTRAL',
            'volume_confirmation': 'UNKNOWN',
            'market_structure': 'UNKNOWN',
            'breakout_status': 'UNKNOWN',
            'entry_quality': 'POOR',
            'main_positive_factors': [],
            'main_risks': [reason],
            'invalidation_reason': reason,
            'summary': f'Analysis failed: {reason}',
            'reason_codes': ['ANALYSIS_FAILED'],
            'parse_error': True
        }

    def _format_candles_compact(self, ohlcv_data: List[Dict[str, Any]]) -> str:
        """
        تبدیل کندل‌ها به رشته فشرده برای کاهش حجم پرامپت
        فرمت: باز,بالا,پایین,بسته,حجم
        """
        if not ohlcv_data:
            return "No data"

        # محدود کردن به ۵۰۰ کندل برای کنترل حجم
        if len(ohlcv_data) > 500:
            ohlcv_data = ohlcv_data[-500:]
            logger.info(f"📊 استفاده از ۵۰۰ کندل آخر از کل داده‌ها")

        # ساخت رشته فشرده
        lines = []
        for c in ohlcv_data:
            lines.append(
                f"{c['open']:.2f},{c['high']:.2f},{c['low']:.2f},{c['close']:.2f},{c['volume']:.0f}"
            )

        return "\n".join(lines)

    def _build_prompt(
        self, 
        ohlcv_data: List[Dict[str, Any]],
        symbol: str,
        current_price: float,
        timeframe: str
    ) -> str:
        """
        ساخت پرامپت با داده کامل OHLCV
        """
        if not ohlcv_data:
            return "No data available"

        # =========================
        # فرمت کردن داده‌ها (فشرده)
        # =========================
        candles_text = self._format_candles_compact(ohlcv_data)

        # =========================
        # محاسبات آماری برای کمک به AI
        # =========================
        closes = [c['close'] for c in ohlcv_data if c.get('close')]
        highs = [c['high'] for c in ohlcv_data if c.get('high')]
        lows = [c['low'] for c in ohlcv_data if c.get('low')]
        volumes = [c['volume'] for c in ohlcv_data if c.get('volume')]

        if not closes:
            return "No valid price data"

        # محاسبات پایه
        highest = max(highs)
        lowest = min(lows)
        avg_volume = sum(volumes) / len(volumes) if volumes else 0
        first_close = closes[0]
        last_close = closes[-1]
        price_change = last_close - first_close
        price_change_percent = (price_change / first_close) * 100 if first_close != 0 else 0

        # محاسبه میانگین متحرک ساده
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None

        # محاسبه نوسان (حداکثر - حداقل)
        volatility = ((highest - lowest) / ((highest + lowest) / 2)) * 100 if (highest + lowest) > 0 else 0

        # =========================
        # ساخت پرامپت نهایی
        # =========================
        prompt = f"""شما یک تحلیلگر مستقل و حرفه‌ای بازارهای مالی هستید.

### ⚠️ قانون مهم:
- **هیچ اطلاعاتی درباره تصمیم، امتیاز یا تحلیل سیستم معاملاتی دیگری در اختیار ندارید.**
- **صرفاً بر اساس داده‌های خام قیمت و حجم، تحلیل خود را ارائه دهید.**
- **داده‌های کامل OHLCV برای {len(ohlcv_data)} کندل در اختیار شماست.**
- **اگر داده برای نتیجه‌گیری کافی نیست، direction را INVALID بگذارید.**

---

### 📊 اطلاعات پایه:
- **نماد:** {symbol}
- **تایم‌فریم:** {timeframe}
- **تعداد کندل‌ها:** {len(ohlcv_data)}
- **قیمت فعلی:** {current_price:.2f}
- **بیشترین قیمت (کل دوره):** {highest:.2f}
- **کمترین قیمت (کل دوره):** {lowest:.2f}
- **نوسان کل دوره:** {volatility:.2f}%
- **تغییر قیمت کل:** {price_change:+.2f} ({price_change_percent:+.2f}%)
- **میانگین حجم:** {avg_volume:.0f}
"""

        # اضافه کردن میانگین متحرک در صورت وجود
        if sma_20:
            prompt += f"- **میانگین متحرک ۲۰ دوره:** {sma_20:.2f}\n"
        if sma_50:
            prompt += f"- **میانگین متحرک ۵۰ دوره:** {sma_50:.2f}\n"

        prompt += f"""
---

### 📈 داده‌های کامل OHLCV (فرمت: باز,بالا,پایین,بسته,حجم):
{candles_text}

---

### 🔍 وظیفه شما:
۱. **روند (Trend):** بازار در چه وضعیتی است؟ (صعودی، نزولی، خنثی)
۲. **ساختار بازار (Market Structure):** آیا ساختار HH/HL (صعودی) یا LH/LL (نزولی) یا رنج است؟
۳. **مومنتوم (Momentum):** قدرت حرکت قیمت چگونه است؟
۴. **حجم (Volume):** آیا حجم معاملات تاییدکننده حرکت است؟
۵. **حمایت و مقاومت (S/R):** سطوح کلیدی کدام‌اند؟
۶. **شرایط ورود (Entry Quality):** آیا الان زمان مناسبی برای ورود است؟
۷. **شکست‌ها (Breakouts):** آیا شکست معتبری رخ داده است؟

---

### 📤 خروجی مورد نظر (JSON):
{{
    "direction": "BUY | SELL | WAIT | INVALID",
    "confidence": 0-10,
    "trend": "BULLISH | BEARISH | SIDEWAYS",
    "trend_strength": 0-10,
    "momentum": "BULLISH | BEARISH | NEUTRAL",
    "volume_confirmation": "YES | NO | UNKNOWN",
    "market_structure": "HH_HL | LH_LL | RANGE | UNKNOWN",
    "breakout_status": "BREAKOUT | BREAKDOWN | NONE | UNKNOWN",
    "entry_quality": "GOOD | FAIR | POOR",
    "main_positive_factors": ["عامل مثبت ۱", "عامل مثبت ۲"],
    "main_risks": ["ریسک ۱", "ریسک ۲"],
    "invalidation_reason": "شرط ابطال تحلیل (در صورت INVALID بودن)",
    "summary": "خلاصه تحلیل شما در ۱-۲ جمله",
    "reason_codes": ["CODE1", "CODE2"]
}}

### قوانین خروجی:
- **فقط JSON را برگردانید. هیچ متن دیگری.**
- **confidence از ۰ تا ۱۰ باشد.** (۰=کمترین، ۱۰=بالاترین)
- **اگر مطمئن نیستید، direction را WAIT بگذارید.**
- **اگر داده کافی نیست، direction را INVALID بگذارید.**
- **تحلیل خود را مستقل و بی‌طرفانه ارائه دهید.**
"""
        return prompt

    def _call_gemini(self, prompt: str) -> Optional[str]:
        """فراخوانی Gemini API"""
        if not self.gemini_model:
            logger.error("❌ Gemini model not initialized")
            return None

        try:
            response = self.gemini_model.generate_content(prompt)

            if response and response.text:
                text = response.text.strip()
                # تلاش برای استخراج JSON از پاسخ
                json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
                if json_match:
                    return json_match.group()
                else:
                    logger.warning("⚠️ Gemini response did not contain JSON, treating as invalid")
                    return None
            else:
                logger.warning("⚠️ Gemini returned empty response")
                return None

        except Exception as e:
            logger.error(f"❌ Gemini call error: {e}")
            return None

    def _call_openai(self, prompt: str) -> Optional[str]:
        """فراخوانی OpenAI API"""
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "شما یک تحلیلگر مستقل بازارهای مالی هستید. همیشه به صورت JSON با ساختار مشخص پاسخ دهید."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.config.AI_TEMPERATURE,
                "max_tokens": self.config.AI_MAX_TOKENS
            }

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
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

                # تلاش برای استخراج JSON از محتوا
                json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if json_match:
                    return json_match.group()
                else:
                    logger.warning("⚠️ OpenAI response did not contain JSON")
                    return None
            else:
                logger.error(f"❌ OpenAI error {response.status_code}: {response.text[:200]}")
                return None

        except Exception as e:
            logger.error(f"❌ OpenAI call error: {e}")
            return None

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        پردازش پاسخ JSON از AI
        
        ساختار خروجی جدید:
        - direction: BUY/SELL/WAIT/INVALID
        - confidence: 0-10
        - trend: BULLISH/BEARISH/SIDEWAYS
        - و ...
        """
        try:
            # =========================
            # استخراج JSON از پاسخ
            # =========================
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in AI response")
                return self._create_fallback_response("No JSON found in response")

            json_str = json_match.group()
            data = json.loads(json_str)

            # =========================
            # استخراج و اعتبارسنجی فیلدها
            # =========================
            direction = data.get('direction', 'WAIT').upper()
            if direction not in ['BUY', 'SELL', 'WAIT', 'INVALID']:
                direction = 'WAIT'

            # اعتبارسنجی confidence (۰-۱۰)
            confidence = data.get('confidence', 5)
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 10:
                confidence = 5
            confidence = int(confidence)

            # اعتبارسنجی trend
            trend = data.get('trend', 'SIDEWAYS').upper()
            if trend not in ['BULLISH', 'BEARISH', 'SIDEWAYS']:
                trend = 'SIDEWAYS'

            # اعتبارسنجی trend_strength (۰-۱۰)
            trend_strength = data.get('trend_strength', 5)
            if not isinstance(trend_strength, (int, float)) or trend_strength < 0 or trend_strength > 10:
                trend_strength = 5
            trend_strength = int(trend_strength)

            # اعتبارسنجی momentum
            momentum = data.get('momentum', 'NEUTRAL').upper()
            if momentum not in ['BULLISH', 'BEARISH', 'NEUTRAL']:
                momentum = 'NEUTRAL'

            # اعتبارسنجی volume_confirmation
            volume_confirmation = data.get('volume_confirmation', 'UNKNOWN').upper()
            if volume_confirmation not in ['YES', 'NO', 'UNKNOWN']:
                volume_confirmation = 'UNKNOWN'

            # اعتبارسنجی market_structure
            market_structure = data.get('market_structure', 'UNKNOWN').upper()
            if market_structure not in ['HH_HL', 'LH_LL', 'RANGE', 'UNKNOWN']:
                market_structure = 'UNKNOWN'

            # اعتبارسنجی breakout_status
            breakout_status = data.get('breakout_status', 'UNKNOWN').upper()
            if breakout_status not in ['BREAKOUT', 'BREAKDOWN', 'NONE', 'UNKNOWN']:
                breakout_status = 'UNKNOWN'

            # اعتبارسنجی entry_quality
            entry_quality = data.get('entry_quality', 'POOR').upper()
            if entry_quality not in ['GOOD', 'FAIR', 'POOR']:
                entry_quality = 'POOR'


            # استخراج لیست‌ها با اعتبارسنجی
            positive_factors = data.get('main_positive_factors', [])
            if not isinstance(positive_factors, list):
                positive_factors = []

            risks = data.get('main_risks', [])
            if not isinstance(risks, list):
                risks = []

            reason_codes = data.get('reason_codes', [])
            if not isinstance(reason_codes, list):
                reason_codes = []

            invalidation_reason = data.get('invalidation_reason', '')
            if not isinstance(invalidation_reason, str):
                invalidation_reason = ''

            summary = data.get('summary', 'تحلیل AI در دسترس نیست')
            if not isinstance(summary, str):
                summary = str(summary)

            # =========================
            # ساخت پاسخ نهایی
            # =========================
            return {
                'enabled': True,
                'direction': direction,
                'confidence': confidence,
                'trend': trend,
                'trend_strength': trend_strength,
                'momentum': momentum,
                'volume_confirmation': volume_confirmation,
                'market_structure': market_structure,
                'breakout_status': breakout_status,
                'entry_quality': entry_quality,
                'main_positive_factors': positive_factors[:5],
                'main_risks': risks[:5],
                'invalidation_reason': invalidation_reason,
                'summary': summary,
                'reason_codes': reason_codes[:5],
                'parse_error': False
            }

        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON decode error: {e}")
            return self._create_fallback_response(f"JSON decode error: {str(e)[:50]}")
        except Exception as e:
            logger.error(f"❌ Error parsing AI response: {e}")
            return self._create_fallback_response(f"Parse error: {str(e)[:50]}")

    def get_analysis_text(self, ai_result: Dict[str, Any]) -> str:
        """
        تولید متن قابل نمایش برای پیام نهایی (نسخه جدید)
        """
        if not ai_result.get('enabled', False):
            return "🤖 AI: غیرفعال"

        if ai_result.get('parse_error', False):
            return f"🤖 AI: تحلیل نامعتبر - {ai_result.get('summary', 'خطای ناشناخته')}"

        direction = ai_result.get('direction', 'WAIT')
        confidence = ai_result.get('confidence', 0)
        summary = ai_result.get('summary', '')
        trend = ai_result.get('trend', 'UNKNOWN')
        entry_quality = ai_result.get('entry_quality', 'POOR')
        trend_strength = ai_result.get('trend_strength', 0)

        direction_emoji = {
            'BUY': '🟢',
            'SELL': '🔴',
            'WAIT': '🟡',
            'INVALID': '⚪'
        }.get(direction, '⚪')

        trend_emoji = {
            'BULLISH': '📈',
            'BEARISH': '📉',
            'SIDEWAYS': '➡️',
            'UNKNOWN': '❓'
        }.get(trend, '❓')

        quality_emoji = {
            'GOOD': '✅',
            'FAIR': '⚠️',
            'POOR': '🔻'
        }.get(entry_quality, '❓')

        parts = [
            "━━━━━━━━━━━━━━━━━━━━",
            "🤖 <b>تحلیل مستقل هوش مصنوعی</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        if summary:
            parts.append(f"📌 {summary}")
            parts.append("")

        parts.append(f"🎯 <b>جهت‌گیری:</b> {direction_emoji} {direction}")
        parts.append(f"📊 <b>اطمینان:</b> {confidence}/10")
        parts.append(f"{trend_emoji} <b>روند:</b> {trend} (قدرت: {trend_strength}/10)")
        parts.append(f"{quality_emoji} <b>کیفیت ورود:</b> {entry_quality}")

        # عوامل مثبت
        positive = ai_result.get('main_positive_factors', [])
        if positive:
            parts.append("")
            parts.append("🟢 <b>عوامل مثبت:</b>")
            for factor in positive[:3]:
                parts.append(f"• {factor}")

        # ریسک‌ها
        risks = ai_result.get('main_risks', [])
        if risks:
            parts.append("")
            parts.append("🔴 <b>ریسک‌ها:</b>")
            for risk in risks[:3]:
                parts.append(f"• {risk}")

        # کدهای دلیل
        codes = ai_result.get('reason_codes', [])
        if codes:
            parts.append("")
            parts.append(f"🏷️ <b>کدها:</b> {', '.join(codes[:3])}")

        # دلیل ابطال (در صورت وجود)
        invalidation = ai_result.get('invalidation_reason')
        if invalidation and direction == 'INVALID':
            parts.append("")
            parts.append(f"⚠️ <b>دلیل ابطال:</b> {invalidation}")

        return "\n".join(parts)

    # ================================================
    # 🔥 تابع کمکی برای مدیریت کش
    # ================================================
    def clear_cache(self):
        """
        پاک کردن تمام کش
        """
        self.cache.clear()
        logger.info("🗑️ AI Cache cleared completely")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار کش
        """
        return {
            'total_entries': len(self.cache),
            'cache_ttl': self.cache_ttl,
            'entries': list(self.cache.keys())
        }


# =========================
# تابع کمکی برای استفاده خارج از کلاس
# =========================
def create_ai_analyzer(config=Config) -> AIAnalyzer:
    """ساخت نمونه از AIAnalyzer با تنظیمات پیش‌فرض"""
    return AIAnalyzer(config)