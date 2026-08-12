"""
Crypto Signal Bot - Package Initialization
"""

__version__ = "1.0.0"
__author__ = "Crypto Signal Bot Team"

# =========================
# All modules will be imported here as they are built
# =========================
from .data_fetcher import NobitexDataFetcher
from .indicators import TechnicalIndicators
from .signal_engine import SignalEngine
from .bale_bot import BaleBot
from .news_reader import NewsReader
from .ai_analyzer import AIAnalyzer
from .confidence import ConfidenceEngine
from .performance_tracker import PerformanceTracker
from .market_regime import MarketRegime
from .scoring import ScoringEngine
from .risk_manager import RiskManager
from .formatter import MessageFormatter

__all__ = [
    "NobitexDataFetcher",
    "TechnicalIndicators",
    "SignalEngine",
    "BaleBot",
    "NewsReader",
    "AIAnalyzer",
    "ConfidenceEngine",
    "PerformanceTracker",
    "MarketRegime",
    "ScoringEngine",
    "RiskManager",
    "MessageFormatter",
]
