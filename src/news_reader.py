"""
News Reader Module
Responsible for fetching and parsing news from Nitrimo Radar
"""

import logging
import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any

import requests
from bs4 import BeautifulSoup

from config import Config

logger = logging.getLogger(__name__)


class NewsReader:
    """
    دریافت و پردازش اخبار از Nitrimo Radar
    """
    
    def __init__(self, config=Config):
        self.config = config
        self.source_url = config.NEWS_SOURCE
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.cache = {}
        self.last_fetch_time = None
        
        self.bullish_keywords_fa = [
            'صعود', 'افزایش', 'رشد', 'جهش', 'صعودی', 'خرید', 'سبز',
            'مثبت', 'بالا', 'صرفه‌جویی', 'بازگشت', 'احیاء', 'قوی',
            'شارژ', 'پمپ', 'شکست مقاومت', 'گاوی', 'سبزپوش'
        ]
        
        self.bearish_keywords_fa = [
            'نزول', 'کاهش', 'ریزش', 'سقوط', 'نزولی', 'فروش', 'قرمز',
            'منفی', 'پایین', 'افت', 'فشار فروش', 'تحریم', 'جنگ',
            'تنش', 'حمله', 'آتش‌بس', 'ترس', 'وحشت', 'عدم اطمینان',
            'شکست حمایت', 'خرسی', 'قرمزپوش'
        ]
        
        self.bullish_keywords_en = [
            'bullish', 'uptrend', 'breakout', 'rally', 'surge',
            'positive', 'growth', 'higher', 'strong', 'gain'
        ]
        
        self.bearish_keywords_en = [
            'bearish', 'downtrend', 'recession', 'decline',
            'negative', 'lower', 'weak', 'drop', 'crash'
        ]
        
        self.strong_indicators = [
            'بسیار', 'شدید', 'قابل توجه', 'انفجاری', 'تاریخی',
            'very', 'strong', 'significant', 'massive', 'extreme'
        ]
        
        self.weak_indicators = [
            'کمی', 'ملایم', 'احتمالی', 'شاید',
            'slight', 'moderate', 'possible', 'maybe'
        ]
        
    def _word_in_text(self, word: str, text: str) -> bool:
        import re
        if any('\u0600' <= c <= '\u06FF' for c in word):
            pattern = r'(?<![آ-ی])' + re.escape(word) + r'(?![آ-ی])'
        else:
            pattern = r'\b' + re.escape(word.lower()) + r'\b'
        return bool(re.search(pattern, text.lower()))
    
    def fetch_news(self, force: bool = False) -> Optional[Dict[str, Any]]:
        if not force and self.last_fetch_time:
            time_since_last = (datetime.now() - self.last_fetch_time).total_seconds()
            if time_since_last < self.config.NEWS_REFRESH_INTERVAL:
                logger.debug(f"Using cached news data ({time_since_last:.0f}s old)")
                return self.cache.get('last_news')
        
        try:
            logger.info(f"Fetching news from {self.source_url}")
            response = self.session.get(
                self.source_url,
                timeout=self.config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                news_data = self._parse_news(response.text)
                if news_data:
                    self.cache['last_news'] = news_data
                    self.last_fetch_time = datetime.now()
                    logger.info("✅ News fetched successfully")
                    return news_data
                else:
                    logger.warning("⚠️ No news data found")
                    return None
            else:
                logger.error(f"❌ HTTP error {response.status_code} fetching news")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout fetching news")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error fetching news: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching news: {e}")
            return None
    
    def _parse_news(self, html_content: str) -> Dict[str, Any]:
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            quick_look_text = None
            selectors = self.config.NITRIMO_QUICK_LOOK_SELECTOR.split(', ')
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    quick_look_text = element.get_text(strip=True)
                    break
            
            if not quick_look_text:
                keywords = ['نگاه سریع', 'خلاصه', 'quick look', 'summary', 'radar']
                for keyword in keywords:
                    elements = soup.find_all(['div', 'section', 'article'], string=lambda x: x and keyword in str(x))
                    for el in elements:
                        parent = el.find_parent()
                        if parent:
                            text = parent.get_text(strip=True)
                            if len(text) > 100:
                                quick_look_text = text
                                break
                    if quick_look_text:
                        break
            
            news_items = []
            news_selectors = getattr(self.config, 'NEWS_ITEM_SELECTORS', 
                                     ['.news-item', '.post-item', '.article-item', '.radar-item'])
            
            for selector in news_selectors:
                elements = soup.select(selector)
                if elements:
                    for el in elements[:self.config.AI_MAX_NEWS_ITEMS]:
                        try:
                            title = el.find(['h1', 'h2', 'h3', 'h4'])
                            title_text = title.get_text(strip=True) if title else ""
                            desc = el.find(['p', 'div'], class_=lambda x: x and ('desc' in x or 'content' in x or 'text' in x or 'summary' in x))
                            desc_text = desc.get_text(strip=True) if desc else ""
                            if title_text or desc_text:
                                news_items.append({
                                    'title': title_text[:200],
                                    'summary': desc_text[:300],
                                    'source': 'Nitrimo Radar'
                                })
                        except Exception as e:
                            logger.debug(f"Error parsing news item: {e}")
                            continue
                    break
            
            result = {
                'quick_look': quick_look_text or "خلاصه اخبار در دسترس نیست",
                'news_items': news_items,
                'timestamp': datetime.now().isoformat(),
                'source': self.source_url
            }
            
            # ================================================
            # ✅ اصلاح: هش کردن با encode
            # ================================================
            content_hash = hashlib.md5(
                (quick_look_text or "").encode('utf-8') + 
                str(news_items).encode('utf-8')
            ).hexdigest()
            result['hash'] = content_hash
            
            logger.info(f"Parsed {len(news_items)} news items")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing news HTML: {e}")
            return None
    
    def get_quick_look(self) -> Optional[str]:
        news_data = self.fetch_news()
        if news_data:
            return news_data.get('quick_look')
        return None
    
    def get_news_summary(self) -> Optional[str]:
        news_data = self.fetch_news()
        if not news_data:
            return "اخبار در دسترس نیست"
        
        parts = []
        quick_look = news_data.get('quick_look')
        if quick_look and quick_look != "خلاصه اخبار در دسترس نیست":
            parts.append(f"📰 خلاصه اخبار:\n{quick_look}")
        
        news_items = news_data.get('news_items', [])
        if news_items:
            parts.append("\n📌 اخبار مهم:")
            for i, item in enumerate(news_items[:5], 1):
                title = item.get('title', '')
                summary = item.get('summary', '')
                if title:
                    parts.append(f"{i}. {title}")
                if summary and summary != title:
                    parts.append(f"   {summary[:100]}...")
        
        return "\n".join(parts) if parts else "اخبار در دسترس نیست"
    
    def get_market_sentiment(self, news_data: Dict[str, Any] = None) -> Dict[str, Any]:
        if not news_data:
            news_data = self.fetch_news()
            if not news_data:
                return {
                    'sentiment': 'neutral',
                    'score': 0.0,
                    'bullish_count': 0,
                    'bearish_count': 0,
                    'total_items': 0,
                    'details': 'No news data available'
                }
        
        text_parts = []
        quick_look = news_data.get('quick_look', '')
        if quick_look:
            text_parts.append(quick_look)
        
        for item in news_data.get('news_items', []):
            title = item.get('title', '')
            summary = item.get('summary', '')
            if title:
                text_parts.append(title)
            if summary:
                text_parts.append(summary)
        
        text = " ".join(text_parts)
        
        bullish_count = 0
        bearish_count = 0
        strong_count = 0
        weak_count = 0
        
        for word in self.bullish_keywords_fa:
            if self._word_in_text(word, text):
                bullish_count += 1
        for word in self.bullish_keywords_en:
            if self._word_in_text(word, text):
                bullish_count += 1
        
        for word in self.bearish_keywords_fa:
            if self._word_in_text(word, text):
                bearish_count += 1
        for word in self.bearish_keywords_en:
            if self._word_in_text(word, text):
                bearish_count += 1
        
        for word in self.strong_indicators:
            if self._word_in_text(word, text):
                strong_count += 1
        for word in self.weak_indicators:
            if self._word_in_text(word, text):
                weak_count += 1
        
        total_items = len(news_data.get('news_items', []))
        
        if bullish_count == 0 and bearish_count == 0:
            sentiment = 'neutral'
            score = 0.0
        else:
            raw_score = (bullish_count - bearish_count) / (bullish_count + bearish_count + 1)
            if strong_count > 0:
                raw_score = raw_score * (1 + min(strong_count * 0.1, 0.5))
            if weak_count > 0:
                raw_score = raw_score * (1 - min(weak_count * 0.05, 0.3))
            score = max(-1.0, min(1.0, raw_score))
            
            if score > 0.15:
                sentiment = 'bullish'
            elif score < -0.15:
                sentiment = 'bearish'
            else:
                sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'score': round(score, 3),
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'strong_count': strong_count,
            'weak_count': weak_count,
            'total_items': total_items,
            'details': f"{bullish_count} bullish vs {bearish_count} bearish signals"
        }
    
    def get_market_sentiment_score(self, news_data: Dict[str, Any] = None) -> float:
        result = self.get_market_sentiment(news_data)
        return result.get('score', 0.0)
    
    def clear_cache(self):
        self.cache.clear()
        self.last_fetch_time = None
        logger.info("News cache cleared")
