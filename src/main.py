"""
Main Application Module
Orchestrates all components: data fetching, analysis, AI, and messaging
"""

import logging
import time
import sys
from datetime import datetime
from typing import Dict, Any, List

from config import Config
from src.data_fetcher import NobitexDataFetcher
from src.signal_engine import SignalEngine
from src.news_reader import NewsReader
from src.ai_analyzer import AIAnalyzer
from src.bale_bot import BaleBot
from src.formatter import MessageFormatter
from src.performance_tracker import PerformanceTracker

logger = logging.getLogger(__name__)


class CryptoSignalBot:
    """
    ربات اصلی سیگنال‌دهی رمزارز
    """
    
    def __init__(self, config=Config):
        self.config = config
        
        # =========================
        # راه‌اندازی ماژول‌ها
        # =========================
        self.data_fetcher = NobitexDataFetcher(config.NOBITEX_API_KEY)
        self.signal_engine = SignalEngine(config)
        self.news_reader = NewsReader(config)
        self.ai_analyzer = AIAnalyzer(config)
        self.bale_bot = BaleBot(config)
        self.formatter = MessageFormatter(config)
        self.performance_tracker = PerformanceTracker(config)
        
        # =========================
        # وضعیت ربات
        # =========================
        self.last_run_time = None
        self.last_signals = {}          # آخرین تحلیل هر ارز
        self.last_sent_signals = {}     # آخرین سیگنال ارسال‌شده برای هر ارز
        self.last_sent_times = {}       # زمان آخرین ارسال برای هر ارز
        self.running = False
        
        # تنظیم لاگ
        self._setup_logging()
        
    def _setup_logging(self):
        """تنظیم لاگ‌گیری"""
        log_level = getattr(logging, self.config.LOG_LEVEL.upper(), logging.INFO)
        
        logging.basicConfig(
            level=log_level,
            format=self.config.LOG_FORMAT,
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
        
        logger.info("🚀 Crypto Signal Bot initialized")
        logger.info(self.config.get_config_summary())
    
    def run_once(self) -> bool:
        """
        یک بار اجرای کامل ربات
        """
        logger.info("=" * 50)
        logger.info(f"🔄 Starting scan at {datetime.now()}")
        
        try:
            # =========================
            # ۱. دریافت ارزهای فعال
            # =========================
            symbols = self.config.get_active_symbols()
            if not symbols:
                logger.error("❌ No active symbols found")
                return False
            
            logger.info(f"📊 Analyzing {len(symbols)} symbols")
            
            # =========================
            # ۲. دریافت داده بازار
            # =========================
            market_data = self._fetch_market_data(symbols)
            if not market_data:
                logger.error("❌ No market data available")
                return False
            
            # =========================
            # ۳. دریافت اخبار (یک بار برای کل اجرا)
            # =========================
            news_data = None
            news_summary = None
            news_sentiment = None
            
            if self.config.ENABLE_NEWS_ANALYSIS:
                news_data = self.news_reader.fetch_news()
                if news_data:
                    news_summary = self.news_reader.get_news_summary()
                    news_sentiment = self.news_reader.get_market_sentiment(news_data)
                    logger.info(f"✅ News fetched: {news_sentiment.get('sentiment', 'neutral')}")
                else:
                    logger.warning("⚠️ News not available")
            
            # =========================
            # ۴. تحلیل همه ارزها
            # =========================
            all_results = []
            for symbol, data in market_data.items():
                if data is None:
                    continue
                    
                try:
                    result = self.signal_engine.analyze_symbol(
                        data['df'], 
                        symbol, 
                        data['price']
                    )
                    
                    if result:
                        all_results.append(result)
                        # ذخیره آخرین تحلیل
                        self.last_signals[symbol] = {
                            'signal': result.get('signal'),
                            'score': result.get('score'),
                            'confidence': result.get('confidence'),
                            'timestamp': datetime.now()
                        }
                        
                except Exception as e:
                    logger.error(f"❌ Error analyzing {symbol}: {e}")
                    continue
            
            if not all_results:
                logger.warning("⚠️ No analysis results")
                return False
            
            # =========================
            # ۵. تشخیص وضعیت کلی بازار (بر اساس همه نتایج)
            # =========================
            market_regime = self._detect_market_regime(all_results)
            logger.info(f"📈 Market regime: {market_regime}")
            
            # =========================
            # ۶. انتخاب بهترین سیگنال‌ها
            # =========================
            top_signals = self.signal_engine.get_top_opportunities(all_results, limit=5)
            
            # =========================
            # ۷. فیلتر سیگنال‌هایی که باید ارسال شوند
            # =========================
            signals_to_send = []
            for signal in top_signals:
                if self._should_send_signal(signal):
                    signals_to_send.append(signal)
            
            logger.info(f"📤 {len(signals_to_send)} signals to send out of {len(top_signals)} top signals")
            
            # =========================
            # ۸. AI برای سیگنال‌های قابل ارسال
            # =========================
            ai_results = {}
            if self.config.ENABLE_AI_ANALYSIS and signals_to_send:
                for signal in signals_to_send:
                    ai_result = self.ai_analyzer.analyze(
                        signal_data=signal,
                        news_summary=news_summary,
                        news_sentiment=news_sentiment,
                        market_regime=market_regime
                    )
                    ai_results[signal.get('symbol')] = ai_result
                    # فاصله بین درخواست‌های AI
                    time.sleep(0.3)
            
            # =========================
            # ۹. ارسال پیام‌ها (با ارسال all_results برای خلاصه)
            # =========================
            self._send_messages(all_results, signals_to_send, ai_results)
            
            # =========================
            # ۱۰. ذخیره عملکرد
            # =========================
            if all_results:
                self.performance_tracker.save_signals(all_results)
            
            logger.info(f"✅ Scan completed. {len(all_results)} signals generated, {len(signals_to_send)} sent.")
            logger.info("=" * 50)
            
            self.last_run_time = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"❌ Critical error in run_once: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _fetch_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        دریافت داده بازار برای همه ارزها
        """
        market_data = {}
        
        for symbol in symbols:
            try:
                df = self.data_fetcher.get_ohlcv(
                    symbol,
                    timeframe=self.config.TIMEFRAME,
                    limit=self.config.CANDLES_LIMIT
                )
                
                if df is None or len(df) < self.config.CANDLES_LIMIT:
                    logger.warning(f"⚠️ Insufficient data for {symbol}")
                    continue
                
                price = self.data_fetcher.get_current_price(symbol)
                if not price:
                    logger.warning(f"⚠️ No price for {symbol}")
                    continue
                
                market_data[symbol] = {
                    'df': df,
                    'price': price
                }
                
            except Exception as e:
                logger.error(f"❌ Error fetching data for {symbol}: {e}")
                continue
        
        # دریافت قیمت‌های چندگانه
        if len(market_data) > 1:
            symbols_with_data = list(market_data.keys())
            prices = self.data_fetcher.get_multiple_prices(symbols_with_data)
            for symbol, price in prices.items():
                if symbol in market_data and price:
                    market_data[symbol]['price'] = price
        
        logger.info(f"✅ Fetched data for {len(market_data)} symbols")
        return market_data
    
    def _should_send_signal(self, signal: Dict[str, Any]) -> bool:
        """
        بررسی اینکه آیا سیگنال باید ارسال شود
        
        Args:
            signal: دیکشنری سیگنال فعلی
            
        Returns:
            True اگر باید ارسال شود، False در غیر این صورت
        """
        symbol = signal.get('symbol')
        current_signal = signal.get('signal')
        current_score = signal.get('score', 0)
        
        # =========================
        # ۱. اگر WAIT باشد، ارسال نکن
        # =========================
        if current_signal == 'WAIT':
            return False
        
        # =========================
        # ۲. اگر قبلاً سیگنالی ارسال نشده، ارسال کن
        # =========================
        if symbol not in self.last_sent_signals:
            return True
        
        # =========================
        # ۳. اگر سیگنال تغییر کرده باشد، ارسال کن
        # =========================
        last_sent = self.last_sent_signals.get(symbol, {})
        if last_sent.get('signal') != current_signal:
            return True
        
        # =========================
        # ۴. اگر امتیاز تغییر قابل توجهی داشته باشد (بیش از ۱۰ واحد)
        # =========================
        last_score = last_sent.get('score', 0)
        if abs(current_score - last_score) > 10:
            return True
        
        # =========================
        # ۵. بررسی فاصله زمانی
        # =========================
        last_time = self.last_sent_times.get(symbol)
        if last_time:
            time_diff = (datetime.now() - last_time).total_seconds()
            if time_diff >= self.config.MIN_SIGNAL_INTERVAL:
                return True
        
        return False
    
    def _send_messages(
        self, 
        all_results: List[Dict[str, Any]],
        signals_to_send: List[Dict[str, Any]],
        ai_results: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        ارسال پیام‌ها
        
        Args:
            all_results: نتایج کامل تحلیل همه ارزها
            signals_to_send: سیگنال‌هایی که باید ارسال شوند
            ai_results: نتایج AI برای سیگنال‌های ارسال‌شده
        """
        if self.config.TEST_MODE:
            logger.info("🧪 TEST MODE: Messages not sent")
            return
        
        if not signals_to_send:
            logger.info("📭 No signals to send")
            return
        
        # =========================
        # ارسال سیگنال‌ها
        # =========================
        sent_count = 0
        for signal in signals_to_send:
            symbol = signal.get('symbol')
            ai_result = ai_results.get(symbol)
            
            message = self.formatter.format_signal(signal, ai_result)
            success = self.bale_bot.send_message(message)
            
            if success:
                # ذخیره سیگنال ارسال‌شده
                self.last_sent_signals[symbol] = {
                    'signal': signal.get('signal'),
                    'score': signal.get('score'),
                    'confidence': signal.get('confidence')
                }
                self.last_sent_times[symbol] = datetime.now()
                sent_count += 1
                logger.info(f"📤 Sent signal for {symbol}")
            else:
                logger.error(f"❌ Failed to send message for {symbol}")
            
            # فاصله بین پیام‌ها
            time.sleep(0.5)
        
        # =========================
        # ارسال خلاصه کلی (بر اساس all_results)
        # =========================
        if self.config.SEND_SUMMARY and sent_count > 0:
            # استخراج خلاصه AI
            ai_summary = None
            if self.config.ENABLE_AI_ANALYSIS:
                for ai_result in ai_results.values():
                    if ai_result.get('summary'):
                        ai_summary = ai_result.get('summary')
                        break
            
            # استفاده از all_results برای خلاصه کامل بازار
            summary = self.formatter.format_summary(
                signals=all_results,
                market_regime=self._detect_market_regime(all_results),
                ai_summary=ai_summary
            )
            self.bale_bot.send_message(summary)
            
        elif sent_count == 0:
            logger.info("📭 No new signals to send")
    
    def _detect_market_regime(self, results: List[Dict[str, Any]]) -> str:
        """
        تشخیص وضعیت کلی بازار
        """
        if not results:
            return 'neutral'
        
        buy_count = sum(1 for r in results if r.get('signal') == 'BUY')
        sell_count = sum(1 for r in results if r.get('signal') == 'SELL')
        total = len(results)
        
        if total == 0:
            return 'neutral'
        
        buy_ratio = buy_count / total
        sell_ratio = sell_count / total
        
        if buy_ratio > 0.6:
            return 'bullish'
        elif sell_ratio > 0.6:
            return 'bearish'
        elif buy_ratio > 0.55 and sell_ratio < 0.3:
            return 'bullish'
        elif sell_ratio > 0.55 and buy_ratio < 0.3:
            return 'bearish'
        else:
            return 'neutral'
    
    def run_forever(self):
        """اجرای مداوم ربات"""
        self.running = True
        logger.info("🔄 Starting continuous mode...")
        
        while self.running:
            try:
                self.run_once()
                
                logger.info(f"⏳ Waiting {self.config.SCAN_INTERVAL} seconds...")
                time.sleep(self.config.SCAN_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("👋 Bot stopped by user")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Critical error: {e}")
                time.sleep(60)
    
    def stop(self):
        """متوقف کردن ربات"""
        self.running = False
        logger.info("🛑 Bot stopped")


def main():
    """نقطه ورود اصلی"""
    try:
        Config.validate()
        
        bot = CryptoSignalBot()
        
        if len(sys.argv) > 1 and sys.argv[1] == '--once':
            bot.run_once()
        else:
            bot.run_forever()
            
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
