"""
Data Fetcher Module
Responsible for fetching OHLCV and current price from Nobitex API
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple, Any
import pandas as pd
import requests

from config import Config

logger = logging.getLogger(__name__)


class DataQuality:
    """
    Data quality report for OHLCV data
    Tracks raw and cleaned data statistics with categorized issue tracking
    
    IMPORTANT: DataQuality is ONLY about data quality, NOT signal confidence.
    This should never be used as signal confidence directly.
    """
    
    def __init__(
        self,
        raw_df: pd.DataFrame,
        cleaned_df: pd.DataFrame,
        cleaned_before_incomplete_df: pd.DataFrame,
        final_closed_df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        removal_stats: Dict[str, int],
        incomplete_candle_removed: bool = False,
        gap_events: int = 0,
        missing_candles: int = 0,
        raw_max_gap_seconds: int = 0,
        requested_candles: int = 0,
        fetch_timestamp_utc: Optional[datetime] = None,
        alignment_issues: int = 0,
        out_of_order_count: int = 0,
        invalid_timestamp_count: int = 0
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.requested_candles = requested_candles
        self.raw_candles = len(raw_df)
        self.cleaned_candles = len(cleaned_df)
        self.valid_candles = len(final_closed_df)
        self.removal_stats = removal_stats
        self.incomplete_candle_removed = incomplete_candle_removed
        self.fetch_timestamp_utc = fetch_timestamp_utc or datetime.now(timezone.utc)
        self.alignment_issues = alignment_issues
        self.out_of_order_count = out_of_order_count
        self.invalid_timestamp_count = invalid_timestamp_count
        
        # total_excluded = raw - cleaned BEFORE incomplete removal
        self.total_excluded = len(raw_df) - len(cleaned_before_incomplete_df)
        
        self.gap_events = gap_events
        self.missing_candles = missing_candles
        self.raw_max_gap_seconds = raw_max_gap_seconds
        
        # Individual removal counts
        self.removed_nan = removal_stats.get('nan', 0)
        self.removed_zero = removal_stats.get('zero', 0)
        self.removed_invalid_ohlc = removal_stats.get('invalid_ohlc', 0)
        self.removed_negative = removal_stats.get('negative', 0)
        self.removed_duplicate = removal_stats.get('duplicate', 0)
        
        # Requested vs Received vs Cleaned vs Final
        self.candle_mismatch = self.requested_candles - self.raw_candles
        self.cleaning_loss = self.raw_candles - self.cleaned_candles
        self.incomplete_removed = 1 if incomplete_candle_removed else 0
        self.final_loss = self.raw_candles - self.valid_candles
        
        # Check stale
        self.is_stale = self._check_stale_data(final_closed_df)
        
        # Validate - PURE DATA QUALITY ONLY
        self.is_valid = self._validate_data(final_closed_df)
        
        # Quality score - PURE DATA QUALITY ONLY (0-100)
        self.quality_score = self._calculate_quality_score()
        
        # Quality gate result - based ONLY on data quality
        self.gate_result = self._evaluate_gate()
        self.reject_reason = self._get_reject_reason() if self.gate_result['status'] == 'REJECT' else None
    
    def _get_duration_seconds(self, timeframe: str) -> int:
        """Get expected candle duration in seconds"""
        if timeframe.endswith('m'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 3600
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 86400
        elif timeframe.endswith('w'):
            return int(timeframe[:-1]) * 604800
        elif timeframe.endswith('M'):
            # For monthly, use actual days in current month
            now = datetime.now(timezone.utc)
            if now.month == 12:
                next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
            days_in_month = (next_month - datetime(now.year, now.month, 1, tzinfo=timezone.utc)).days
            return int(timeframe[:-1]) * days_in_month * 86400
        return 60
    
    def _check_stale_data(self, df: pd.DataFrame) -> bool:
        """Check if data is stale based on timeframe"""
        if len(df) == 0:
            return True
            
        latest = df.index[-1]
        now = datetime.now(timezone.utc)
        diff = (now - latest).total_seconds()
        
        # Different thresholds for different timeframe types
        if self.timeframe.endswith('m'):
            minutes = int(self.timeframe[:-1])
            threshold = minutes * 120  # 2x in seconds
        elif self.timeframe.endswith('h'):
            hours = int(self.timeframe[:-1])
            threshold = hours * 3600 * 2
        elif self.timeframe.endswith('d'):
            days = int(self.timeframe[:-1])
            threshold = days * 86400 * 2
        elif self.timeframe.endswith('w'):
            weeks = int(self.timeframe[:-1])
            threshold = weeks * 604800 * 2
        elif self.timeframe.endswith('M'):
            # For monthly: 2x the actual month length
            duration = self._get_duration_seconds(self.timeframe)
            threshold = duration * 2
        else:
            threshold = 300  # Default 5 minutes
            
        return diff > threshold
    
    def _validate_data(self, df: pd.DataFrame) -> bool:
        """Validate data quality for analysis - PURE DATA QUALITY ONLY"""
        # Minimum candles check (based on warm-up)
        min_required = self._get_min_required_candles()
        if len(df) < min_required:
            return False
        
        # Too many invalid candles removed
        if self.total_excluded > self.raw_candles * 0.2:
            return False
        
        # Too many gap events
        if self.gap_events > self.raw_candles * 0.05:
            return False
        
        # Gap too large
        if self.raw_max_gap_seconds > self._get_duration_seconds(self.timeframe) * 10:
            return False
        
        # Stale data
        if self.is_stale:
            return False
        
        # Candle mismatch
        if abs(self.candle_mismatch) > self.requested_candles * 0.1:
            return False
        
        # Too many alignment issues
        if self.alignment_issues > self.raw_candles * 0.1:
            return False
        
        # Out of order
        if self.out_of_order_count > 0:
            return False
        
        # Invalid timestamps
        if self.invalid_timestamp_count > 0:
            return False
        
        return True
    
    def _get_min_required_candles(self) -> int:
        """Calculate minimum candles needed based on indicators"""
        # Base minimum from config
        base = Config.MIN_CANDLES_REQUIRED
        
        # Add buffer for EMA/SMA
        ema_period = getattr(Config, 'EMA_TREND', 200)
        buffer = 50
        
        # Check for other indicators
        rsi_period = getattr(Config, 'RSI_PERIOD', 14)
        macd_slow = getattr(Config, 'MACD_SLOW', 26)
        adx_period = getattr(Config, 'ADX_PERIOD', 14)
        
        max_lookback = max(
            ema_period,
            rsi_period,
            macd_slow,
            adx_period
        )
        
        # Need: max_lookback + buffer for calculations
        required = max_lookback + buffer
        
        # Also ensure we have enough for requested limit
        if self.requested_candles > 0:
            required = min(required, self.requested_candles)
        
        return max(base, required)
    
    def _calculate_quality_score(self) -> float:
        """
        Calculate data quality score (0-100).
        PURE DATA QUALITY ONLY - NOT SIGNAL CONFIDENCE.
        Each category deducted separately.
        """
        if self.raw_candles == 0:
            return 0.0
            
        score = 100.0
        
        # Each category has separate max deduction
        score -= (self.removed_nan / self.raw_candles) * 15
        score -= (self.removed_zero / self.raw_candles) * 15
        score -= (self.removed_invalid_ohlc / self.raw_candles) * 20
        score -= (self.removed_negative / self.raw_candles) * 10
        score -= (self.removed_duplicate / self.raw_candles) * 10
        score -= (self.missing_candles / self.raw_candles) * 15
        
        # Alignment issues penalty
        if self.raw_candles > 0:
            alignment_rate = self.alignment_issues / self.raw_candles
            score -= alignment_rate * 10
        
        # Candle mismatch penalty
        if self.requested_candles > 0:
            mismatch_rate = abs(self.candle_mismatch) / self.requested_candles
            score -= mismatch_rate * 10
        
        # Invalid timestamps penalty
        if self.raw_candles > 0:
            invalid_rate = self.invalid_timestamp_count / self.raw_candles
            score -= invalid_rate * 15
        
        # Large gap penalty
        if self.raw_max_gap_seconds > self._get_duration_seconds(self.timeframe) * 3:
            score -= 5
        
        # Stale penalty
        if self.is_stale:
            score -= 20
        
        # Out of order penalty
        if self.out_of_order_count > 0:
            score -= 15
            
        return max(0.0, min(100.0, score))
    
    def _evaluate_gate(self) -> Dict[str, Any]:
        """
        Evaluate data quality gate with hard/soft failure.
        This is a PURE DATA QUALITY GATE - not signal confidence.
        """
        score = self.quality_score
        
        # Hard failures (immediate reject regardless of score)
        hard_failures = []
        
        if self.raw_candles == 0:
            hard_failures.append('NO_DATA')
        
        if self.out_of_order_count > 0:
            hard_failures.append('OUT_OF_ORDER')
        
        if self.is_stale:
            hard_failures.append('STALE_DATA')
        
        if self.gap_events > self.raw_candles * 0.1:
            hard_failures.append('EXCESSIVE_GAPS')
        
        if abs(self.candle_mismatch) > self.requested_candles * 0.2:
            hard_failures.append('CANDLE_MISMATCH')
        
        if self.invalid_timestamp_count > 0:
            hard_failures.append('INVALID_TIMESTAMPS')
        
        if len(self.final_valid_candles) < self._get_min_required_candles():
            hard_failures.append('INSUFFICIENT_CANDLES')
        
        if hard_failures:
            return {
                'status': 'REJECT',
                'level': 'HARD_FAIL',
                'score': score,
                'hard_failures': hard_failures,
                'description': f"Hard failure: {', '.join(hard_failures)}"
            }
        
        # Soft failures (based on score)
        if score >= 80:
            return {
                'status': 'PASS',
                'level': 'GOOD',
                'score': score,
                'hard_failures': [],
                'description': 'Data quality is excellent'
            }
        elif score >= 70:
            return {
                'status': 'PASS_WITH_WARNING',
                'level': 'ACCEPTABLE',
                'score': score,
                'hard_failures': [],
                'description': 'Data quality is acceptable but has minor issues'
            }
        else:
            return {
                'status': 'REJECT',
                'level': 'SOFT_FAIL',
                'score': score,
                'hard_failures': [],
                'description': f'Data quality is insufficient (score: {score:.1f}%)'
            }
    
    def _get_reject_reason(self) -> str:
        """Get detailed reject reason"""
        if not self.gate_result:
            return None
        
        if self.gate_result['hard_failures']:
            return f"HARD_FAIL: {', '.join(self.gate_result['hard_failures'])}"
        
        return f"SOFT_FAIL: Score={self.quality_score:.1f}% < 70%"
    
    def to_dict(self) -> Dict:
        """Convert quality report to dictionary"""
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'requested_candles': self.requested_candles,
            'raw_candles': self.raw_candles,
            'cleaned_candles': self.cleaned_candles,
            'valid_candles': self.valid_candles,
            'candle_mismatch': self.candle_mismatch,
            'cleaning_loss': self.cleaning_loss,
            'incomplete_removed': self.incomplete_removed,
            'final_loss': self.final_loss,
            'removal_stats': self.removal_stats,
            'total_excluded': self.total_excluded,
            'incomplete_candle_removed': self.incomplete_candle_removed,
            'gap_events': self.gap_events,
            'missing_candles': self.missing_candles,
            'raw_max_gap_seconds': self.raw_max_gap_seconds,
            'alignment_issues': self.alignment_issues,
            'out_of_order_count': self.out_of_order_count,
            'invalid_timestamp_count': self.invalid_timestamp_count,
            'quality_score': round(self.quality_score, 1),
            'is_stale': self.is_stale,
            'is_valid': self.is_valid,
            'gate_result': self.gate_result,
            'reject_reason': self.reject_reason,
            'fetch_timestamp_utc': self.fetch_timestamp_utc.isoformat() if self.fetch_timestamp_utc else None,
            'fetch_timestamp_tehran': self._utc_to_tehran(self.fetch_timestamp_utc) if self.fetch_timestamp_utc else None,
            'raw_issues': {
                'nan': self.removed_nan,
                'zero': self.removed_zero,
                'invalid_ohlc': self.removed_invalid_ohlc,
                'negative': self.removed_negative,
                'duplicate': self.removed_duplicate,
                'alignment': self.alignment_issues,
                'out_of_order': self.out_of_order_count,
                'invalid_timestamps': self.invalid_timestamp_count
            }
        }
    
    def _utc_to_tehran(self, dt: datetime) -> str:
        """Convert UTC to Tehran timezone for display"""
        if dt is None:
            return None
        tehran = dt + timedelta(hours=3, minutes=30)
        return tehran.strftime('%Y-%m-%d %H:%M:%S')


class NobitexDataFetcher:
    """
    دریافت داده OHLCV و قیمت لحظهای از API نوبیتکس
    """

    def __init__(self):
        self.base_url = "https://apiv2.nobitex.ir"

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        })

        self.cache = {}
        self.data_quality_cache = {}

        # Rate limits: stats = 20/min, udf = 60/min
        self.rate_limits = {
            "stats": {"min_interval": 3.1, "last_request_time": 0},
            "udf": {"min_interval": 1.1, "last_request_time": 0}
        }

        self.resolution_map = {
            "1m": "1", "5m": "5", "15m": "15", "30m": "30",
            "1h": "60", "3h": "180", "4h": "240",
            "1d": "D", "1w": "W", "1M": "M"
        }

    # ============================================================
    # HELPERS
    # ============================================================

    def _rate_limit(self, endpoint_type: str = "udf"):
        if endpoint_type not in self.rate_limits:
            endpoint_type = "udf"
        limit = self.rate_limits[endpoint_type]
        now = time.time()
        elapsed = now - limit["last_request_time"]
        if elapsed < limit["min_interval"]:
            time.sleep(limit["min_interval"] - elapsed)
        limit["last_request_time"] = time.time()

    def _get_nobitex_symbol(self, symbol: str) -> Optional[str]:
        return Config.NOBITEX_SYMBOL_MAP.get(symbol)

    def _get_stats_key(self, symbol: str) -> Optional[str]:
        return Config.NOBITEX_STATS_MAP.get(symbol)

    def _get_src_currency(self, symbol: str) -> Optional[str]:
        return Config.SRC_CURRENCY_MAP.get(symbol, symbol)

    def _get_resolution(self, timeframe: str) -> Optional[str]:
        return self.resolution_map.get(timeframe)

    def _get_duration_seconds(self, timeframe: str) -> int:
        """Get expected candle duration in seconds"""
        if timeframe.endswith('m'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 3600
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 86400
        elif timeframe.endswith('w'):
            return int(timeframe[:-1]) * 604800
        elif timeframe.endswith('M'):
            # For monthly, use actual days in current month
            now = datetime.now(timezone.utc)
            if now.month == 12:
                next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
            days_in_month = (next_month - datetime(now.year, now.month, 1, tzinfo=timezone.utc)).days
            return int(timeframe[:-1]) * days_in_month * 86400
        return 60

    def _validate_timestamp(self, ts: datetime) -> bool:
        """Validate a single timestamp"""
        # Check if timestamp is valid (not nan, not inf, not in future)
        if ts is None:
            return False
        
        # Check if timestamp is not in future (allow 5 seconds tolerance)
        now = datetime.now(timezone.utc)
        if ts > now + timedelta(seconds=5):
            return False
        
        # Check if timestamp is not too old (older than 10 years)
        if ts < now - timedelta(days=3650):
            return False
        
        return True

    def _check_alignment(self, df: pd.DataFrame, timeframe: str) -> int:
        """
        Check timestamp alignment to candle boundaries.
        Returns: number of unaligned candles
        """
        if len(df) == 0:
            return 0
            
        unaligned = 0
        
        for ts in df.index:
            # --- Minute-based timeframes ---
            if timeframe.endswith('m'):
                minutes = int(timeframe[:-1])
                # Check: second=0, microsecond=0, minute is multiple of timeframe
                if ts.second != 0 or ts.microsecond != 0 or ts.minute % minutes != 0:
                    unaligned += 1
                    
            # --- Hour-based timeframes ---
            elif timeframe.endswith('h'):
                hours = int(timeframe[:-1])
                # Check: second=0, microsecond=0, minute=0, hour is multiple of timeframe
                if ts.second != 0 or ts.microsecond != 0 or ts.minute != 0 or ts.hour % hours != 0:
                    unaligned += 1
                    
            # --- Day-based timeframes ---
            elif timeframe.endswith('d'):
                days = int(timeframe[:-1])
                # For 1d: check midnight (00:00:00)
                if days == 1:
                    if ts.second != 0 or ts.microsecond != 0 or ts.minute != 0 or ts.hour != 0:
                        unaligned += 1
                else:
                    # For multi-day: check midnight only
                    # Don't check day % days as anchor depends on exchange
                    if ts.second != 0 or ts.microsecond != 0 or ts.minute != 0 or ts.hour != 0:
                        unaligned += 1
                    
            # --- Week-based timeframes ---
            elif timeframe.endswith('w'):
                # Check: Monday 00:00:00
                if ts.second != 0 or ts.microsecond != 0 or ts.minute != 0 or ts.hour != 0 or ts.weekday() != 0:
                    unaligned += 1
                    
            # --- Month-based timeframes ---
            elif timeframe.endswith('M'):
                # Check: 1st 00:00:00
                if ts.second != 0 or ts.microsecond != 0 or ts.minute != 0 or ts.hour != 0 or ts.day != 1:
                    unaligned += 1
                    
        return unaligned

    def _detect_gaps(self, df: pd.DataFrame, timeframe: str) -> Tuple[int, int, int]:
        """
        Detect gaps in data.
        Returns: (gap_events, missing_candles, max_gap_seconds)
        """
        if len(df) < 2:
            return 0, 0, 0

        expected = self._get_duration_seconds(timeframe)
        gap_events = 0
        missing_candles = 0
        max_gap = 0

        for i in range(1, len(df)):
            interval = (df.index[i] - df.index[i-1]).total_seconds()
            
            # For small timeframes, use tighter tolerance (1.05x)
            # For larger timeframes, use 1.1x
            if timeframe.endswith('m') and int(timeframe[:-1]) <= 5:
                tolerance = 1.05
            else:
                tolerance = 1.1
            
            if interval > expected * tolerance:
                gap_events += 1
                # Calculate how many candles are missing
                missing = int(interval / expected + 0.5) - 1
                missing_candles += max(0, missing)
                
                if interval > max_gap:
                    max_gap = interval

        return gap_events, missing_candles, max_gap

    def _clean_ohlcv_staged(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
        """
        Clean data in stages. Each stage tracked separately.
        Returns: (cleaned_df, removal_stats)
        """
        if df.empty:
            return df, {}

        cleaned = df.copy()
        stats = {'nan': 0, 'zero': 0, 'invalid_ohlc': 0, 'negative': 0, 'duplicate': 0}

        # Stage 1: Convert to numeric, remove NaN
        for col in ["open", "high", "low", "close", "volume"]:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
        before = len(cleaned)
        cleaned.dropna(subset=["open", "high", "low", "close", "volume"], inplace=True)
        stats['nan'] = before - len(cleaned)

        # Stage 2: Remove zero prices
        before = len(cleaned)
        cleaned = cleaned[
            (cleaned['open'] != 0) & (cleaned['high'] != 0) &
            (cleaned['low'] != 0) & (cleaned['close'] != 0)
        ]
        stats['zero'] = before - len(cleaned)

        # Stage 3: Remove invalid OHLC
        before = len(cleaned)
        cleaned = cleaned[
            (cleaned['high'] >= cleaned['low']) &
            (cleaned['high'] >= cleaned['open']) &
            (cleaned['high'] >= cleaned['close']) &
            (cleaned['low'] <= cleaned['open']) &
            (cleaned['low'] <= cleaned['close'])
        ]
        stats['invalid_ohlc'] = before - len(cleaned)

        # Stage 4: Remove negative values
        before = len(cleaned)
        cleaned = cleaned[
            (cleaned['open'] > 0) & (cleaned['high'] > 0) &
            (cleaned['low'] > 0) & (cleaned['close'] > 0) &
            (cleaned['volume'] >= 0)
        ]
        stats['negative'] = before - len(cleaned)

        # Stage 5: Sort and remove duplicates
        cleaned.sort_index(inplace=True)
        before = len(cleaned)
        cleaned = cleaned[~cleaned.index.duplicated(keep='first')]
        stats['duplicate'] = before - len(cleaned)

        return cleaned, stats

    def _remove_incomplete_candle(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Remove last candle if still forming"""
        if len(df) == 0:
            return df

        duration = self._get_duration_seconds(timeframe)
        last_ts = df.index[-1]
        now = datetime.now(timezone.utc)

        # Candle is complete if: (start + duration) <= now
        candle_end = last_ts + timedelta(seconds=duration)
        
        if candle_end > now:
            # Candle is still forming
            return df.iloc[:-1]

        return df

    # ============================================================
    # GET OHLCV
    # ============================================================

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        timeframe = timeframe or Config.TIMEFRAME
        limit = limit or Config.CANDLES_LIMIT

        # Validate timeframe
        if timeframe not in self.resolution_map:
            logger.warning(f"⚠️ UNSUPPORTED_TIMEFRAME: {timeframe}")
            return None

        nobitex_symbol = self._get_nobitex_symbol(symbol)
        if not nobitex_symbol:
            logger.warning(f"⚠️ NO_MAPPING: {symbol}")
            return None

        resolution = self._get_resolution(timeframe)
        if not resolution:
            logger.warning(f"⚠️ UNSUPPORTED_TIMEFRAME: {timeframe}")
            return None

        cache_key = f"{symbol}_{timeframe}_{limit}"
        
        # Cache check with validation
        if Config.ENABLE_CACHE and cache_key in self.cache:
            cache_time, cached_data = self.cache[cache_key]
            cache_age = (datetime.now() - cache_time).total_seconds()
            
            if cache_age < Config.CACHE_TTL:
                # Validate cached data
                if cached_data is not None and len(cached_data) > 0:
                    # Check if cached data is still valid (not stale)
                    latest_ts = cached_data.index[-1]
                    duration = self._get_duration_seconds(timeframe)
                    now = datetime.now(timezone.utc)
                    
                    # Cache is valid if latest candle is still incomplete or recently closed
                    # Allow 2x timeframe for freshness
                    stale_threshold = duration * 2
                    if (now - latest_ts).total_seconds() <= stale_threshold:
                        logger.debug(f"Cache hit (valid): {symbol}")
                        return cached_data.copy()
                    else:
                        logger.debug(f"Cache expired (stale): {symbol}")
                else:
                    logger.debug(f"Cache invalid (empty): {symbol}")

        fetch_timestamp = datetime.now(timezone.utc)
        requested_candles = limit

        try:
            self._rate_limit("udf")
            url = f"{self.base_url}/market/udf/history"
            params = {
                "symbol": nobitex_symbol,
                "resolution": resolution,
                "to": int(datetime.now().timestamp()),
                "countback": limit
            }

            logger.debug(f"Fetching {symbol}: symbol={nobitex_symbol}, resolution={resolution}, countback={limit}")

            response = self.session.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)

            # Handle rate limit
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after) + 0.5
                        logger.warning(f"RATE_LIMIT: {symbol}, waiting {wait_time}s")
                        time.sleep(wait_time)
                        # Retry once after rate limit
                        response = self.session.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
                    except ValueError:
                        pass

            if response.status_code != 200:
                logger.error(f"❌ HTTP_{response.status_code}: {symbol}")
                return None

            try:
                data = response.json()
            except ValueError:
                logger.error(f"❌ INVALID_JSON: {symbol}")
                return None

            if data.get("s") != "ok":
                logger.error(f"❌ API_ERROR: {symbol} - {data}")
                return None

            timestamps = data.get("t", [])
            if not timestamps:
                logger.warning(f"⚠️ NO_DATA: {symbol}")
                return None

            # Build raw DataFrame with UTC timestamps
            raw_df = pd.DataFrame({
                "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
                "open": data.get("o", []),
                "high": data.get("h", []),
                "low": data.get("l", []),
                "close": data.get("c", []),
                "volume": data.get("v", [])
            })
            raw_df.set_index("timestamp", inplace=True)

            # --- TIMESTAMP VALIDATION ---
            invalid_timestamps = []
            for ts in raw_df.index:
                if not self._validate_timestamp(ts):
                    invalid_timestamps.append(ts)
            
            invalid_timestamp_count = len(invalid_timestamps)
            
            if invalid_timestamps:
                logger.warning(f"⚠️ INVALID_TIMESTAMPS: {symbol} - {invalid_timestamp_count} invalid timestamps")
                # Remove invalid timestamps
                raw_df = raw_df[~raw_df.index.isin(invalid_timestamps)]
                if raw_df.empty:
                    logger.error(f"❌ NO_VALID_TIMESTAMPS: {symbol}")
                    return None

            # --- OUT OF ORDER DETECTION (BEFORE SORT) ---
            out_of_order_count = 0
            if len(raw_df) > 1:
                # Check if index is monotonic increasing
                if not raw_df.index.is_monotonic_increasing:
                    # Count out-of-order entries
                    sorted_indices = raw_df.index.sort_values()
                    out_of_order_count = len(raw_df) - len(raw_df.loc[sorted_indices].drop_duplicates())
                    logger.warning(f"⚠️ OUT_OF_ORDER: {symbol} - {out_of_order_count} out-of-order timestamps")

            # Sort raw data before any temporal analysis
            raw_df.sort_index(inplace=True)

            # --- 1. DETECT GAPS (on raw data) ---
            gap_events, missing_candles, raw_max_gap = self._detect_gaps(raw_df, timeframe)

            # --- 2. CHECK ALIGNMENT ---
            alignment_issues = self._check_alignment(raw_df, timeframe)

            # --- 3. CLEAN (staged) ---
            cleaned_before_incomplete, removal_stats = self._clean_ohlcv_staged(raw_df)

            # --- 4. REMOVE INCOMPLETE CANDLE ---
            cleaned_df = self._remove_incomplete_candle(cleaned_before_incomplete, timeframe)
            incomplete_removed = len(cleaned_df) < len(cleaned_before_incomplete)

            # --- 5. FINAL CLOSED CANDLES ---
            final_closed_df = cleaned_df.copy()

            # --- 6. QUALITY REPORT ---
            quality = DataQuality(
                raw_df=raw_df,
                cleaned_df=cleaned_df,
                cleaned_before_incomplete_df=cleaned_before_incomplete,
                final_closed_df=final_closed_df,
                symbol=symbol,
                timeframe=timeframe,
                removal_stats=removal_stats,
                incomplete_candle_removed=incomplete_removed,
                gap_events=gap_events,
                missing_candles=missing_candles,
                raw_max_gap_seconds=raw_max_gap,
                requested_candles=requested_candles,
                fetch_timestamp_utc=fetch_timestamp,
                alignment_issues=alignment_issues,
                out_of_order_count=out_of_order_count,
                invalid_timestamp_count=invalid_timestamp_count
            )

            self.data_quality_cache[symbol] = quality

            qdict = quality.to_dict()
            
            # Log quality report
            log_msg = (
                f"📊 {symbol} ({timeframe}): "
                f"Score={qdict['quality_score']:.1f}% "
                f"Gate={qdict['gate_result']['status']} "
                f"Req={qdict['requested_candles']} "
                f"Raw={qdict['raw_candles']} "
                f"Clean={qdict['cleaned_candles']} "
                f"Final={qdict['valid_candles']} "
                f"Gaps={qdict['gap_events']} "
                f"Missing={qdict['missing_candles']}"
            )
            
            if qdict['gate_result']['status'] == 'REJECT':
                log_msg += f" REJECTED: {qdict['reject_reason']}"
                logger.warning(log_msg)
                return None
            else:
                logger.info(log_msg)

            # --- 7. CACHE ---
            if Config.ENABLE_CACHE:
                self.cache[cache_key] = (datetime.now(), final_closed_df.copy())

            logger.info(f"✅ {symbol}: {len(final_closed_df)} valid closed candles")
            return final_closed_df

        except requests.exceptions.Timeout:
            logger.error(f"❌ TIMEOUT: {symbol}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ REQUEST_ERROR: {symbol} - {e}")
            return None
        except Exception as e:
            logger.error(f"❌ UNEXPECTED: {symbol} - {e}")
            return None

    # ============================================================
    # GET CURRENT PRICE (SINGLE)
    # ============================================================

    def get_current_price(self, symbol: str) -> Optional[float]:
        stats_key = self._get_stats_key(symbol)
        if not stats_key:
            logger.warning(f"⚠️ NO_STATS_MAPPING: {symbol}")
            return None

        try:
            self._rate_limit("stats")
            src = self._get_src_currency(symbol)
            url = f"{self.base_url}/market/stats"
            params = {"srcCurrency": src, "dstCurrency": "USDT"}

            response = self.session.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)

            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after) + 0.5
                        logger.warning(f"RATE_LIMIT: {symbol}, waiting {wait_time}s")
                        time.sleep(wait_time)
                        response = self.session.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
                    except ValueError:
                        pass

            if response.status_code != 200:
                logger.error(f"❌ HTTP_{response.status_code}: {symbol}")
                return None

            data = response.json()
            if data.get("status") != "ok":
                logger.error(f"❌ API_ERROR: {symbol}")
                return None

            stats = data.get("stats", {})
            ticker = stats.get(src) or stats.get(stats_key)

            if not ticker:
                logger.warning(f"⚠️ NO_TICKER: {symbol}")
                return None

            price = ticker.get("latest")
            if price is None:
                logger.warning(f"⚠️ NO_PRICE: {symbol}")
                return None

            # NO ROUNDING - preserve precision
            return float(price)

        except requests.exceptions.Timeout:
            logger.error(f"❌ TIMEOUT: {symbol}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ REQUEST_ERROR: {symbol} - {e}")
            return None
        except Exception as e:
            logger.error(f"❌ ERROR: {symbol} - {e}")
            return None

    # ============================================================
    # GET MULTIPLE PRICES (BATCH)
    # ============================================================

    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        if not symbols:
            return {}

        for attempt in range(3):
            try:
                self._rate_limit("stats")

                src_currencies = []
                valid_symbols = []

                for symbol in symbols:
                    src = self._get_src_currency(symbol)
                    if src:
                        src_currencies.append(src)
                        valid_symbols.append(symbol)

                if not src_currencies:
                    return {}

                url = f"{self.base_url}/market/stats"
                params = {
                    "srcCurrency": ",".join(src_currencies),
                    "dstCurrency": "USDT"
                }

                response = self.session.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)

                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            time.sleep(int(retry_after) + 0.5)
                            continue
                        except ValueError:
                            pass

                if response.status_code != 200:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    return {}

                data = response.json()
                if data.get("status") != "ok":
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    return {}

                stats = data.get("stats", {})
                prices = {}

                for i, symbol in enumerate(valid_symbols):
                    src = src_currencies[i]
                    ticker = stats.get(src, {})
                    if ticker:
                        price = ticker.get("latest")
                        prices[symbol] = float(price) if price is not None else None
                    else:
                        prices[symbol] = None

                for symbol in symbols:
                    if symbol not in prices:
                        prices[symbol] = None

                return prices

            except Exception as e:
                logger.error(f"❌ BATCH_ERROR (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue

        logger.error(f"❌ BATCH_FAILED: {len(symbols)} symbols")
        return {}

    # ============================================================
    # UTILITY METHODS
    # ============================================================

    def get_data_quality(self, symbol: str) -> Optional[Dict]:
        quality = self.data_quality_cache.get(symbol)
        return quality.to_dict() if quality else None

    def get_all_data_quality(self) -> Dict[str, Dict]:
        return {
            symbol: quality.to_dict()
            for symbol, quality in self.data_quality_cache.items()
        }

    def clear_cache(self):
        self.cache.clear()
        self.data_quality_cache.clear()
        logger.info("Cache cleared")
