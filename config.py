import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# =========================
# BASE PATHS
# =========================
BASE_DIR = Path(__file__).parent


class Config:
    """
    تنظیمات اصلی ربات تحلیل و سیگنال رمزارز
    تمام پارامترهای قابل تغییر در این فایل متمرکز شده‌اند
    """

    # =========================
    # PATHS
    # =========================
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    CACHE_DIR = BASE_DIR / "cache"
    HISTORY_DIR = DATA_DIR / "history"
    SIGNALS_DIR = DATA_DIR / "signals"

    for dir_path in [DATA_DIR, LOGS_DIR, CACHE_DIR, HISTORY_DIR, SIGNALS_DIR]:
        dir_path.mkdir(exist_ok=True)

    # =========================
    # API KEYS (از .env)
    # =========================
    NOBITEX_API_KEY = os.getenv("NOBITEX_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # AI Settings (قابل تغییر از .env)
    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")
    AI_API_KEY = os.getenv("AI_API_KEY")
    AI_REQUIRED = os.getenv("AI_REQUIRED", "false").lower() == "true"

    # =========================
    # SYMBOLS (فقط ارزهای قابل معامله)
    # =========================
    SYMBOLS = {
        "BTC": "Bitcoin",
        "ETH": "Ethereum",
        "DOGE": "Dogecoin",
        "SOL": "Solana",
        "XRP": "XRP",
        "ADA": "Cardano",
        "TRX": "TRON",
        "ATOM": "Cosmos",
        "DOT": "Polkadot",
        "XLM": "Stellar",
        "ZEC": "Zcash",
        "CRV": "Curve DAO",
        "DEXE": "DeXe",
        "SHIB": "1000SHIB",
        "GRAM": "Gram",
        "BICO": "Biconomy",
        "DEFI": "DeFi App",
        "APT": "Aptos",
        "CRO": "Cronos",
        "PUMP": "Pump",
        "HOME": "Home",
        "PROM": "Prom",
        "BANK": "Bank",
        "HMSTR": "Hamster",
        "DOGS": "DOGS",
        "COOKIE": "COOKIE",
        "XAUT": "Tether Gold",
        "PAXG": "Pax Gold",
    }

    # =========================
    # NOBITEX SYMBOL MAPPING (فرمت بدون خط تیره - مطابق با UDF)
    # =========================
    NOBITEX_SYMBOL_MAP = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "DOGE": "DOGEUSDT",
        "SOL": "SOLUSDT",
        "XRP": "XRPUSDT",
        "ADA": "ADAUSDT",
        "TRX": "TRXUSDT",
        "ATOM": "ATOMUSDT",
        "DOT": "DOTUSDT",
        "XLM": "XLMUSDT",
        "ZEC": "ZECUSDT",
        "CRV": "CRVUSDT",
        "DEXE": "DEXEUSDT",
        "SHIB": "1000SHIBUSDT",
        "GRAM": "GRAMUSDT",
        "BICO": "BICOUSDT",
        "DEFI": "DEFIUSDT",
        "APT": "APTUSDT",
        "CRO": "CROUSDT",
        "PUMP": "PUMPUSDT",
        "HOME": "HOMEUSDT",
        "PROM": "PROMUSDT",
        "BANK": "BANKUSDT",
        "HMSTR": "HMSTRUSDT",
        "DOGS": "DOGSUSDT",
        "COOKIE": "COOKIEUSDT",
        "XAUT": "XAUTUSDT",
        "PAXG": "PAXGUSDT",
    }

    # =========================
    # ENABLE/DISABLE SYMBOLS
    # =========================
    DISABLED_SYMBOLS = []

    @classmethod
    def get_active_symbols(cls):
        """بازگرداندن لیست ارزهای فعال با بررسی وجود در Nobitex"""
        active = []
        for symbol in cls.SYMBOLS.keys():
            if symbol in cls.DISABLED_SYMBOLS:
                continue
            if symbol not in cls.NOBITEX_SYMBOL_MAP:
                print(f"⚠️ Warning: {symbol} not found in NOBITEX_SYMBOL_MAP")
                continue
            active.append(symbol)
        return active

    # =========================
    # TIMEFRAMES
    # =========================
    TIMEFRAME = "15m"
    CANDLES_LIMIT = 200
    HIGHER_TIMEFRAMES = ["1h", "4h", "1d"]

    # =========================
    # TECHNICAL INDICATORS
    # =========================
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    RSI_NEUTRAL_LOW = 45
    RSI_NEUTRAL_HIGH = 55

    EMA_FAST = 20
    EMA_SLOW = 50
    EMA_TREND = 200

    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9

    ATR_PERIOD = 14
    ADX_PERIOD = 14
    ADX_WEAK = 20
    ADX_STRONG = 25
    ADX_VERY_STRONG = 40

    BB_PERIOD = 20
    BB_STD = 2

    # =========================
    # ATR RISK MANAGEMENT
    # =========================
    ATR_SL_MULTIPLIER = 1.5
    ATR_TP1_MULTIPLIER = 2.0
    ATR_TP2_MULTIPLIER = 3.5
    ATR_SL_MULTIPLIER_HIGH_VOLATILITY = 2.0

    MIN_SL_PERCENT = 0.5
    MAX_SL_PERCENT = 10.0

    # =========================
    # VOLUME ANALYSIS
    # =========================
    VOLUME_MA_PERIOD = 20
    HIGH_VOLUME_RATIO = 1.5
    VERY_HIGH_VOLUME_RATIO = 2.5
    LOW_VOLUME_RATIO = 0.7
    VERY_LOW_VOLUME_RATIO = 0.3

    # =========================
    # SIGNAL SCORING
    # =========================
    WEIGHTS = {
        "trend": 20,
        "momentum": 20,
        "volume": 15,
        "volatility": 10,
        "market": 10,
        "breakout": 15,
        "support_resistance": 10,
    }

    MIN_SIGNAL_SCORE = 60
    WEAK_SIGNAL_SCORE = 60
    NORMAL_SIGNAL_SCORE = 70
    STRONG_SIGNAL_SCORE = 80
    VERY_STRONG_SIGNAL_SCORE = 85
    EXCEPTIONAL_SIGNAL_SCORE = 90

    EXCEPTIONAL_CONDITIONS = {
        "breakout_with_volume": True,
        "macd_strong_momentum": True,
        "support_resistance_break": True,
    }

    # =========================
    # HISTORICAL CONFIDENCE
    # =========================
    ENABLE_HISTORICAL_CONFIDENCE = True
    MIN_HISTORY_FOR_CONFIDENCE = 30
    HISTORICAL_WEIGHT = 0.3
    CURRENT_SETUP_WEIGHT = 0.7

    PERFORMANCE_CATEGORIES = {
        "symbol": True,
        "signal_type": True,
        "score_range": True,
        "timeframe": True,
    }

    # =========================
    # MARKET FILTER
    # =========================
    ENABLE_MARKET_FILTER = True
    MARKET_FILTER_THRESHOLD = 40
    MARKET_WEIGHT = 10

    # =========================
    # NEWS / NITRIMO RADAR
    # =========================
    ENABLE_NEWS_ANALYSIS = True
    NEWS_SOURCE = "https://nitrimo.com/radar"
    NEWS_REFRESH_INTERVAL = 900

    NITRIMO_QUICK_LOOK_SELECTOR = ".quick-look, .radar-quick, .summary"

    # =========================
    # AI ANALYSIS
    # =========================
    ENABLE_AI_ANALYSIS = True
    AI_REQUIRED = False

    AI_MAX_NEWS_ITEMS = 10
    AI_TIMEOUT = 30
    AI_TEMPERATURE = 0.7
    AI_MAX_TOKENS = 500

    AI_PROMPT_TEMPLATE = """
    شما یک تحلیلگر ارز دیجیتال هستید که باید بر اساس داده‌های زیر نظر بدهید:

    ### داده‌های تکنیکال {symbol}:
    - قیمت فعلی: {price}
    - RSI: {rsi}
    - MACD: {macd_status} ({macd_value})
    - EMA20: {ema20}, EMA50: {ema50}
    - روند: {trend}
    - ADX (قدرت روند): {adx}
    - نوسان (ATR): {atr}
    - نسبت حجم: {volume_ratio}
    - حمایت: {support}, مقاومت: {resistance}

    ### وضعیت کلی بازار:
    {market_regime}

    ### خلاصه اخبار (از Nitrimo Radar):
    {news_summary}

    ### سیگنال اولیه ربات:
    {robot_signal} با اطمینان {confidence}%

    لطفاً تحلیل کنید:
    1. آیا تحلیل تکنیکال منطقی است؟
    2. آیا اخبار با تحلیل تکنیکال هم‌جهت هستند؟
    3. مهم‌ترین ریسک چیست؟
    4. مهم‌ترین عامل مثبت چیست؟
    5. آیا سیگنال بیش از حد خوش‌بینانه است؟
    6. جمع‌بندی مستقل شما چیست؟

    پاسخ را به صورت ساختاریافته و در ۵-۷ خط خلاصه کنید.
    """

    # =========================
    # TELEGRAM
    # =========================
    SEND_BUY_SIGNALS = True
    SEND_SELL_SIGNALS = True
    SEND_WAIT_SIGNALS = False
    SEND_AI_ANALYSIS = True
    SEND_SUMMARY = True
    SUMMARY_SEND_TIMES = [9, 12, 18, 22]
    MESSAGE_FORMAT = "html"

    # =========================
    # SCAN & PERFORMANCE
    # =========================
    SCAN_INTERVAL = 300
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    REQUEST_TIMEOUT = 30
    MAX_WORKERS = 3

    # =========================
    # CACHE
    # =========================
    ENABLE_CACHE = True
    CACHE_TTL = 60

    # =========================
    # SAFETY
    # =========================
    MAX_DAILY_LOSS_PERCENT = 5.0
    MAX_SIGNALS_PER_DAY = 20
    MIN_SIGNAL_INTERVAL = 1800

    # =========================
    # TEST MODE
    # =========================
    TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
    INITIAL_CAPITAL = 10000
    TRADING_FEE = 0.001

    # =========================
    # VALIDATION
    # =========================
    @classmethod
    def validate(cls):
        """اعتبارسنجی تنظیمات"""
        errors = []
        warnings = []

        if not cls.TELEGRAM_BOT_TOKEN and not cls.TEST_MODE:
            errors.append("TELEGRAM_BOT_TOKEN is required (or enable TEST_MODE)")

        if not cls.TELEGRAM_CHAT_ID and not cls.TEST_MODE:
            errors.append("TELEGRAM_CHAT_ID is required (or enable TEST_MODE)")

        if not cls.NOBITEX_API_KEY:
            warnings.append("NOBITEX_API_KEY not set - may have limited access")

        total_weight = sum(cls.WEIGHTS.values())
        if total_weight != 100:
            warnings.append(f"Total weight is {total_weight}, should be 100")

        if not (cls.MIN_SIGNAL_SCORE < cls.NORMAL_SIGNAL_SCORE < cls.STRONG_SIGNAL_SCORE):
            errors.append("SCORE levels must be in increasing order")

        if cls.ENABLE_AI_ANALYSIS and cls.AI_REQUIRED and not cls.AI_API_KEY:
            errors.append("AI is required but AI_API_KEY is not set")

        for symbol in cls.SYMBOLS:
            if symbol not in cls.NOBITEX_SYMBOL_MAP:
                warnings.append(f"Symbol {symbol} has no mapping in NOBITEX_SYMBOL_MAP")

        if warnings:
            print("\n⚠️ Config Warnings:")
            for w in warnings:
                print(f"  - {w}")

        if errors:
            raise ValueError(f"Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        return True

    @classmethod
    def get_config_summary(cls):
        """خلاصه تنظیمات برای لاگ"""
        active_symbols = cls.get_active_symbols()
        return f"""
        📊 Crypto Signal Bot Config Summary
        ===================================
        ✅ Symbols: {len(active_symbols)} active
        ✅ Timeframe: {cls.TIMEFRAME}
        ✅ Scan Interval: {cls.SCAN_INTERVAL}s
        ✅ Min Score: {cls.MIN_SIGNAL_SCORE}
        ✅ AI Enabled: {cls.ENABLE_AI_ANALYSIS}
        ✅ AI Required: {cls.AI_REQUIRED}
        ✅ News Enabled: {cls.ENABLE_NEWS_ANALYSIS}
        ✅ Test Mode: {cls.TEST_MODE}
        ✅ Risk per Trade: {cls.ATR_SL_MULTIPLIER}x ATR
        ===================================
        """


# اعتبارسنجی خودکار
if not Config.TEST_MODE:
    Config.validate()
