"""
Data Fetcher Module
Responsible for fetching OHLCV and current price from Nobitex API
Based on Nobitex official API documentation
"""

import time
import logging
from datetime import datetime
from typing import Optional, Dict, List

import requests
import pandas as pd

from config import Config

logger = logging.getLogger(__name__)


class NobitexDataFetcher:
    """
    دریافت داده از API نوبیتکس
    مطابق با مستندات رسمی: https://api.nobitex.ir
    """
    
    def __init__(self):
        # =========================
        # آدرس‌های API بر اساس مستندات فعلی
        # =========================
        self.base_url_public = "https://apiv2.nobitex.ir"  # برای OHLC (UDF)
        self.base_url_stats = "https://api.nobitex.ir"     # برای Stats (بدون /v2)
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        
        self.cache = {}
        
        # =========================
        # Rate Limit برای هر endpoint
        # =========================
        # Stats: 20 درخواست در دقیقه → حداقل 3 ثانیه بین درخواست‌ها
        # UDF: محدودیت بالاتر، اما برای احتیاط 1 ثانیه
        self.rate_limits = {
            'stats': {
                'min_interval': 3.0,      # 3 ثانیه بین درخواست‌ها (20 درخواست/دقیقه)
                'last_request_time': 0
            },
            'udf': {
                'min_interval': 1.0,      # 1 ثانیه بین درخواست‌ها (محافظه‌کارانه)
                'last_request_time': 0
            }
        }
        
        # =========================
        # تبدیل تایم‌فریم به فرمت نوبیتکس
        # =========================
        self.resolution_map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "3h": "180",
            "4h": "240",
            "1d": "D",
            "1w": "W",
            "1M": "M"
        }
        
    def _rate_limit(self, endpoint_type: str = 'udf'):
        """
        مدیریت نرخ درخواست‌ها بر اساس نوع endpoint
        
        Args:
            endpoint_type: 'udf' یا 'stats'
        """
        if endpoint_type not in self.rate_limits:
            endpoint_type = 'udf'
        
        limit = self.rate_limits[endpoint_type]
        now = time.time()
        time_since_last = now - limit['last_request_time']
        
        if time_since_last < limit['min_interval']:
            sleep_time = limit['min_interval'] - time_since_last
            logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s for {endpoint_type}")
            time.sleep(sleep_time)
        
        limit['last_request_time'] = time.time()
    
    def _get_nobitex_symbol(self, symbol: str) -> Optional[str]:
        """تبدیل اسم ارز به فرمت نوبیتکس (USDT) از Config"""
        return Config.NOBITEX_SYMBOL_MAP.get(symbol)
    
    def _get_resolution(self, timeframe: str) -> Optional[str]:
        """تبدیل تایم‌فریم به فرمت نوبیتکس"""
        return self.resolution_map.get(timeframe)
    
    def get_ohlcv(
        self, 
        symbol: str, 
        timeframe: Optional[str] = None, 
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        دریافت داده OHLCV از نوبیتکس
        از endpoint: https://apiv2.nobitex.ir/market/udf/history
        
        Args:
            symbol: اسم ارز (مثل BTC)
            timeframe: تایم‌فریم (مثل 15m, 1h, 4h, 1d)
            limit: تعداد کندل‌ها (حداکثر 500)
            
        Returns:
            DataFrame با ستون‌های: timestamp, open, high, low, close, volume
        """
        timeframe = timeframe or Config.TIMEFRAME
        limit = limit or Config.CANDLES_LIMIT
        
        # =========================
        # ۱. تبدیل نماد به فرمت نوبیتکس
        # =========================
        nobitex_symbol = self._get_nobitex_symbol(symbol)
        if not nobitex_symbol:
            logger.warning(f"⚠️ Symbol {symbol} not found in mapping")
            return None
        
        # =========================
        # ۲. تبدیل تایم‌فریم به فرمت نوبیتکس
        # =========================
        resolution = self._get_resolution(timeframe)
        if not resolution:
            logger.warning(f"⚠️ Timeframe {timeframe} not supported")
            return None
        
        # =========================
        # ۳. کلید کش
        # =========================
        cache_key = f"{symbol}_{timeframe}_{limit}"
        if Config.ENABLE_CACHE and cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if (datetime.now() - cache_time).seconds < Config.CACHE_TTL:
                logger.debug(f"Cache hit for {symbol}")
                return data.copy() if data is not None else None
        
        try:
            # =========================
            # ۴. درخواست به API نوبیتکس با to + countback
            # =========================
            self._rate_limit('udf')
            url = f"{self.base_url_public}/market/udf/history"
            params = {
                'symbol': nobitex_symbol,
                'resolution': resolution,
                'to': int(datetime.now().timestamp()),
                'countback': limit
            }
            
            logger.debug(f"Fetching {symbol} with countback={limit}")
            
            response = self.session.get(
                url, 
                params=params,
                timeout=Config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # =========================
                # ۵. بررسی پاسخ API
                # =========================
                if data.get('s') == 'ok':
                    timestamps = data.get('t', [])
                    opens = data.get('o', [])
                    highs = data.get('h', [])
                    lows = data.get('l', [])
                    closes = data.get('c', [])
                    volumes = data.get('v', [])
                    
                    if not timestamps:
                        logger.warning(f"⚠️ No data for {symbol}")
                        return None
                    
                    # ساخت DataFrame
                    df = pd.DataFrame({
                        'timestamp': pd.to_datetime(timestamps, unit='s'),
                        'open': opens,
                        'high': highs,
                        'low': lows,
                        'close': closes,
                        'volume': volumes
                    })
                    
                    df.set_index('timestamp', inplace=True)
                    
                    # تبدیل به عدد
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    # حذف ردیف‌های خالی
                    df = df.dropna()
                    
                    # =========================
                    # ۶. بررسی تعداد کندل‌ها
                    # حداقل مورد نیاز برای اندیکاتورها:
                    # - EMA_TREND = 200
                    # - MACD_SLOW = 26
                    # - ATR = 14
                    # - ADX = 14
                    # با حاشیه امن 50 کندل اضافی
                    # =========================
                    min_required = max(Config.EMA_TREND, 200) + 50  # 250
                    
                    if len(df) < min_required:
                        logger.warning(
                            f"⚠️ Insufficient data for {symbol}: "
                            f"{len(df)} candles (need at least {min_required})"
                        )
                        return None
                    
                    logger.info(f"✅ Fetched {len(df)} candles for {symbol}")
                    
                    # ذخیره در کش
                    if Config.ENABLE_CACHE:
                        self.cache[cache_key] = (datetime.now(), df.copy())
                    
                    return df
                    
                else:
                    error_msg = data.get('s', 'unknown error')
                    logger.error(f"❌ API Error for {symbol}: {error_msg}")
                    return None
            else:
                logger.error(f"❌ HTTP Error {response.status_code} for {symbol}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout fetching {symbol}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error for {symbol}: {e}")
            return None
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        دریافت قیمت لحظه‌ای از نوبیتکس
        از endpoint: https://api.nobitex.ir/market/stats
        
        Args:
            symbol: اسم ارز (مثل BTC)
            
        Returns:
            قیمت لحظه‌ای یا None در صورت خطا
        """
        nobitex_symbol = self._get_nobitex_symbol(symbol)
        if not nobitex_symbol:
            return None
        
        # =========================
        # قیمت لحظه‌ای کش نمی‌شود (برای دقت سیگنال)
        # =========================
        try:
            self._rate_limit('stats')
            url = f"{self.base_url_stats}/market/stats"
            
            # طبق مستندات نوبیتکس
            params = {
                'srcCurrency': symbol,
                'dstCurrency': 'USDT'
            }
            
            response = self.session.get(
                url, 
                params=params,
                timeout=Config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'ok':
                    stats = data.get('stats', {})
                    
                    # کلید بازار به فرمت مثلاً btc-usdt
                    market_key = f"{symbol.lower()}-usdt"
                    ticker = stats.get(market_key, {})
                    price = float(ticker.get('latest', 0))
                    
                    if price > 0:
                        return price
                    else:
                        logger.warning(f"⚠️ Invalid price for {symbol}")
                        return None
                else:
                    logger.error(f"❌ API Error getting price for {symbol}: {data}")
                    return None
            else:
                logger.error(f"❌ HTTP Error {response.status_code} getting price for {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting price for {symbol}: {e}")
            return None
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        """
        دریافت قیمت چند ارز به صورت همزمان با یک درخواست
        
        Args:
            symbols: لیست اسم ارزها
            
        Returns:
            دیکشنری {symbol: price}
        """
        if not symbols:
            return {}
        
        try:
            self._rate_limit('stats')
            url = f"{self.base_url_stats}/market/stats"
            
            # =========================
            # ارسال تمام ارزها به صورت comma-separated
            # =========================
            src_currency = ",".join(symbols)
            params = {
                'srcCurrency': src_currency,
                'dstCurrency': 'USDT'
            }
            
            response = self.session.get(
                url, 
                params=params,
                timeout=Config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'ok':
                    stats = data.get('stats', {})
                    prices = {}
                    
                    for symbol in symbols:
                        market_key = f"{symbol.lower()}-usdt"
                        ticker = stats.get(market_key, {})
                        price = float(ticker.get('latest', 0))
                        prices[symbol] = price if price > 0 else None
                    
                    return prices
                else:
                    logger.error(f"❌ API Error getting multiple prices: {data}")
                    return {}
            else:
                logger.error(f"❌ HTTP Error {response.status_code} getting multiple prices")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error getting multiple prices: {e}")
            return {}
    
    def clear_cache(self):
        """پاک کردن کش"""
        self.cache.clear()
        logger.info("Cache cleared")
