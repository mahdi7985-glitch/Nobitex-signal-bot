"""
Crypto Signal Bot - Package Initialization
"""

__version__ = "2.0.0"
__author__ = "Crypto Signal Bot Team"

# =========================
# ماژول‌های اصلی
# =========================
from .data_fetcher import NobitexDataFetcher
from .indicators import TechnicalIndicators
from .signal_engine import SignalEngine
from .bale_bot import BaleBot
from .news_reader import NewsReader
from .ai_analyzer import AIAnalyzer
from .formatter import MessageFormatter
from .performance_tracker import PerformanceTracker

# =========================
# ماژول‌های جدید (مدیریت سرمایه و معاملات)
# =========================
from .balance_manager import BalanceManager
from .paper_trader import PaperTrader
from .execution_manager import ExecutionManager

# =========================
# لیست ماژول‌های قابل دسترس
# =========================
__all__ = [
    # ماژول‌های قدیمی
    "NobitexDataFetcher",
    "TechnicalIndicators",
    "SignalEngine",
    "BaleBot",
    "NewsReader",
    "AIAnalyzer",
    "MessageFormatter",
    "PerformanceTracker",
    
    # ماژول‌های جدید
    "BalanceManager",
    "PaperTrader",
    "ExecutionManager",
]
