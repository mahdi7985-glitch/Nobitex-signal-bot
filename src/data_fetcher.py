"""
Data Fetcher Module
Responsible for fetching OHLCV and current price from Nobitex API
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
    دریافت داده OHLCV و قیمت لحظه‌ای از API نوبیتکس
    """

    def __init__(self):
        # =========================
        # API URLs
        # =========================
        self.base_url_public = "https://apiv2.nobitex.ir"
        self.base_url_stats = "https://api.nobitex.ir"

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            ),
            "Content-Type": "application/json"
        })

        # =========================
        # CACHE
        # =========================
        self.cache = {}

        # =========================
        # RATE LIMIT
        # =========================
        self.rate_limits = {
            "stats": {
                "min_interval": 0.5,
                "last_request_time": 0
            },
            "udf": {
                "min_interval": 1.0,
                "last_request_time": 0
            }
        }

        # =========================
        # TIMEFRAME -> NOBITEX RESOLUTION
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

    # =========================================================
    # RATE LIMIT
    # =========================================================

    def _rate_limit(self, endpoint_type: str = "udf"):
        """مدیریت نرخ درخواست‌ها"""

        if endpoint_type not in self.rate_limits:
            endpoint_type = "udf"

        limit = self.rate_limits[endpoint_type]

        now = time.time()
        elapsed = now - limit["last_request_time"]

        if elapsed < limit["min_interval"]:
            sleep_time = limit["min_interval"] - elapsed

            logger.debug(
                f"Rate limit: sleeping "
                f"{sleep_time:.2f}s for {endpoint_type}"
            )

            time.sleep(sleep_time)

        limit["last_request_time"] = time.time()

    # =========================================================
    # SYMBOL / TIMEFRAME HELPERS
    # =========================================================

    def _get_nobitex_symbol(self, symbol: str) -> Optional[str]:
        """
        دریافت نماد بازار برای UDF (بدون خط تیره)
        """
        return Config.NOBITEX_SYMBOL_MAP.get(symbol)

    def _get_stats_symbol(self, symbol: str) -> Optional[str]:
        """
        دریافت نماد بازار برای Stats (با خط تیره)
        """
        return Config.NOBITEX_STATS_MAP.get(symbol)

    def _get_resolution(self, timeframe: str) -> Optional[str]:
        """
        تبدیل تایم‌فریم داخلی به resolution نوبیتکس
        """

        return self.resolution_map.get(timeframe)

    # =========================================================
    # OHLCV
    # =========================================================

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        دریافت داده OHLCV از نوبیتکس
        """

        timeframe = timeframe or Config.TIMEFRAME
        limit = limit or Config.CANDLES_LIMIT

        # -------------------------
        # Symbol mapping (UDF)
        # -------------------------

        nobitex_symbol = self._get_nobitex_symbol(symbol)

        if not nobitex_symbol:
            logger.warning(
                f"⚠️ Symbol {symbol} not found in mapping"
            )
            return None

        # -------------------------
        # Resolution
        # -------------------------

        resolution = self._get_resolution(timeframe)

        if not resolution:
            logger.warning(
                f"⚠️ Timeframe {timeframe} not supported"
            )
            return None

        # -------------------------
        # Cache
        # -------------------------

        cache_key = f"{symbol}_{timeframe}_{limit}"

        if Config.ENABLE_CACHE and cache_key in self.cache:

            cache_time, cached_data = self.cache[cache_key]

            age = (datetime.now() - cache_time).total_seconds()

            if age < Config.CACHE_TTL:

                logger.debug(
                    f"Cache hit for {symbol}"
                )

                return (
                    cached_data.copy()
                    if cached_data is not None
                    else None
                )

        # -------------------------
        # API request
        # -------------------------

        try:

            self._rate_limit("udf")

            url = (
                f"{self.base_url_public}"
                f"/market/udf/history"
            )

            params = {
                "symbol": nobitex_symbol,
                "resolution": resolution,
                "to": int(datetime.now().timestamp()),
                "countback": limit
            }

            logger.debug(
                f"Fetching {symbol}: "
                f"symbol={nobitex_symbol}, "
                f"resolution={resolution}, "
                f"countback={limit}"
            )

            response = self.session.get(
                url,
                params=params,
                timeout=Config.REQUEST_TIMEOUT
            )

            if response.status_code != 200:

                logger.error(
                    f"❌ HTTP Error "
                    f"{response.status_code} for {symbol}: "
                    f"{response.text}"
                )

                return None

            try:
                data = response.json()

            except ValueError:

                logger.error(
                    f"❌ Invalid JSON response for {symbol}: "
                    f"{response.text}"
                )

                return None

            if data.get("s") != "ok":

                logger.error(
                    f"❌ API Error for {symbol}: "
                    f"{data}"
                )

                return None

            timestamps = data.get("t", [])
            opens = data.get("o", [])
            highs = data.get("h", [])
            lows = data.get("l", [])
            closes = data.get("c", [])
            volumes = data.get("v", [])

            if not timestamps:

                logger.warning(
                    f"⚠️ No OHLCV data for {symbol}"
                )

                return None

            df = pd.DataFrame({
                "timestamp": pd.to_datetime(
                    timestamps,
                    unit="s"
                ),
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes
            })

            df.set_index(
                "timestamp",
                inplace=True
            )

            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]

            for column in numeric_columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce"
                )

            df.dropna(
                subset=numeric_columns,
                inplace=True
            )

            min_required = max(
                Config.EMA_TREND,
                200
            ) + 50

            if len(df) < min_required:

                logger.warning(
                    f"⚠️ Insufficient data for {symbol}: "
                    f"{len(df)} candles "
                    f"(need {min_required})"
                )

                return None

            df.sort_index(inplace=True)

            if Config.ENABLE_CACHE:

                self.cache[cache_key] = (
                    datetime.now(),
                    df.copy()
                )

            logger.info(
                f"✅ Fetched {len(df)} candles for {symbol}"
            )

            return df

        except requests.exceptions.Timeout:

            logger.error(
                f"❌ Timeout fetching {symbol}"
            )

            return None

        except requests.exceptions.RequestException as e:

            logger.error(
                f"❌ Request error fetching {symbol}: {e}"
            )

            return None

        except Exception as e:

            logger.error(
                f"❌ Unexpected error fetching "
                f"{symbol}: {e}"
            )

            return None

    # =========================================================
    # CURRENT PRICE
    # =========================================================

    def get_current_price(
        self,
        symbol: str
    ) -> Optional[float]:
        """
        دریافت قیمت لحظه‌ای از نوبیتکس
        """

        # برای Stats از mapping جداگانه استفاده کن (با خط تیره)
        stats_key = self._get_stats_symbol(symbol)

        if not stats_key:

            logger.warning(
                f"⚠️ No stats mapping for {symbol}"
            )

            return None

        try:

            self._rate_limit("stats")

            url = (
                f"{self.base_url_stats}"
                f"/market/stats"
            )

            params = {
                "srcCurrency": symbol,
                "dstCurrency": "USDT"
            }

            logger.debug(
                f"Fetching price for {symbol}"
            )

            response = self.session.get(
                url,
                params=params,
                timeout=Config.REQUEST_TIMEOUT
            )

            if response.status_code != 200:

                logger.error(
                    f"❌ HTTP Error "
                    f"{response.status_code} for {symbol}: "
                    f"{response.text}"
                )

                return None

            data = response.json()

            if data.get("status") != "ok":

                logger.error(
                    f"❌ API Error for {symbol}: "
                    f"{data}"
                )

                return None

            stats = data.get(
                "stats",
                {}
            )

            ticker = stats.get(
                stats_key,
                {}
            )

            if not ticker:

                logger.warning(
                    f"⚠️ No ticker found for {symbol}. "
                    f"Expected: {stats_key}, "
                    f"Available: {list(stats.keys())}"
                )

                return None

            price = ticker.get("latest")

            if price is None:

                logger.warning(
                    f"⚠️ No latest price for {symbol}"
                )

                return None

            return float(price)

        except requests.exceptions.Timeout:

            logger.error(
                f"❌ Timeout getting price for {symbol}"
            )

            return None

        except requests.exceptions.RequestException as e:

            logger.error(
                f"❌ Request error getting price "
                f"for {symbol}: {e}"
            )

            return None

        except (ValueError, TypeError) as e:

            logger.error(
                f"❌ Invalid price data for "
                f"{symbol}: {e}"
            )

            return None

        except Exception as e:

            logger.error(
                f"❌ Unexpected error getting price "
                f"for {symbol}: {e}"
            )

            return None

    # =========================================================
    # MULTIPLE PRICES
    # =========================================================

    def get_multiple_prices(
        self,
        symbols: List[str]
    ) -> Dict[str, Optional[float]]:
        """
        دریافت قیمت چند ارز
        """

        if not symbols:
            return {}

        prices = {}

        for symbol in symbols:

            prices[symbol] = (
                self.get_current_price(symbol)
            )

        return prices

    # =========================================================
    # CACHE
    # =========================================================

    def clear_cache(self):
        """
        پاک کردن کش
        """

        self.cache.clear()

        logger.info(
            "Cache cleared"
        )
